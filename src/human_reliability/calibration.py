"""Explicit finite-grid partial pooling, held-out scores and calibrated elicitation."""

from __future__ import annotations

import math

import numpy as np
from pydantic import Field, model_validator
from scipy.special import betaln, gammaln, logsumexp
from scipy.stats import beta
from scipy.optimize import least_squares

from .contracts import Contract, Name, Positive, Probability
from .probability import probability


class BinomialGroup(Contract):
    id: Name
    group_id: Name
    failures: int = Field(ge=0)
    opportunities: int = Field(gt=0)
    opportunity_definition: Name
    domain: Name
    evidence: Name

    @model_validator(mode="after")
    def counts(self):
        if self.failures > self.opportunities:
            raise ValueError("failures exceed opportunities")
        return self


class BetaHyperPoint(Contract):
    alpha: Positive
    beta: Positive
    prior_weight: Positive


class PartialPoolingPosterior:
    def __init__(self, groups, hypergrid, weights, review):
        self.groups = {g.id: g for g in groups}
        self.hypergrid, self.weights, self.review = tuple(hypergrid), np.asarray(weights), review

    def sample(self, group_id, *, size, seed):
        if group_id not in self.groups or type(size) is not int or size < 1:
            raise ValueError("known group and positive draw count required")
        group, rng = self.groups[group_id], np.random.default_rng(seed)
        indices = rng.choice(len(self.hypergrid), size=size, p=self.weights)
        a = np.asarray([h.alpha for h in self.hypergrid])[indices] + group.failures
        b = np.asarray([h.beta for h in self.hypergrid])[indices] + group.opportunities - group.failures
        return rng.beta(a, b)

    def summary(self, group_id, *, credibility=0.95):
        if not 0 < credibility < 1:
            raise ValueError("credibility must be in (0,1)")
        group = self.groups[group_id]
        a = np.asarray([h.alpha for h in self.hypergrid]) + group.failures
        b = np.asarray([h.beta for h in self.hypergrid]) + group.opportunities - group.failures
        mean = float(np.dot(self.weights, a / (a + b)))

        def quantile(q):
            low, high = 0.0, 1.0
            for _ in range(70):
                mid = (low + high) / 2
                if np.dot(self.weights, beta.cdf(mid, a, b)) < q:
                    low = mid
                else:
                    high = mid
            return (low + high) / 2

        return {
            "group_id": group_id,
            "posterior_mean": mean,
            "lower": quantile((1 - credibility) / 2),
            "upper": quantile((1 + credibility) / 2),
            "credibility": credibility,
            "hyper_weights": self.weights.tolist(),
            "model": "finite_hyperprior_beta_binomial",
            "exchangeability_review": self.review,
            "field_transfer_validated": False,
        }

    def predictive_counts(self, group_id, opportunities, *, size, seed):
        if type(opportunities) is not int or opportunities < 1:
            raise ValueError("positive predictive exposure required")
        rng = np.random.default_rng(seed)
        return rng.binomial(opportunities, self.sample(group_id, size=size, seed=seed + 1))


def fit_partial_pooling(groups, hypergrid, *, exchangeability_review, maximum_grid_points=10_000):
    """Enumerate an explicitly supplied discrete hyperprior; do not infer missing crew IDs."""
    if (
        not groups
        or len({g.id for g in groups}) != len(groups)
        or len({g.group_id for g in groups}) != len(groups)
    ):
        raise ValueError("unique disjoint group identities required")
    if len({(g.domain, g.opportunity_definition) for g in groups}) != 1:
        raise ValueError("groups need compatible domains and opportunity definitions")
    if not hypergrid or len(hypergrid) > maximum_grid_points or not exchangeability_review.strip():
        raise ValueError("bounded nonempty hyperprior grid and exchangeability review required")
    logweights = np.log([h.prior_weight for h in hypergrid])
    for group in groups:
        n, k = group.opportunities, group.failures
        logweights += np.asarray(
            [
                betaln(h.alpha + k, h.beta + n - k)
                - betaln(h.alpha, h.beta)
                + gammaln(n + 1)
                - gammaln(k + 1)
                - gammaln(n - k + 1)
                for h in hypergrid
            ]
        )
    weights = np.exp(logweights - logsumexp(logweights))
    if not np.all(np.isfinite(weights)):
        raise ValueError("hyperposterior calculation is not finite")
    return PartialPoolingPosterior(groups, hypergrid, weights, exchangeability_review)


def heldout_binomial_scores(training_groups, heldout_groups, predictions, *, split_review):
    if not split_review.strip() or not heldout_groups:
        raise ValueError("held-out groups and a split review required")
    if {g.id for g in training_groups} & {g.id for g in heldout_groups} or (
        {g.group_id for g in training_groups} & {g.group_id for g in heldout_groups}
    ):
        raise ValueError("training and held-out observation/group identities overlap")
    if len({g.id for g in heldout_groups}) != len(heldout_groups) or set(predictions) != {
        g.id for g in heldout_groups
    }:
        raise ValueError("one prediction for each unique held-out group required")
    n, brier, log_score, bins = 0, 0.0, 0.0, []
    for group in heldout_groups:
        p = probability(predictions[group.id])
        k, count = group.failures, group.opportunities
        n += count
        brier += k * (1 - p) ** 2 + (count - k) * p * p
        if p == 0 and k or p == 1 and count - k:
            log_score = float("inf")
        elif math.isfinite(log_score):
            log_score -= (k * math.log(p) if k else 0) + ((count - k) * math.log1p(-p) if count - k else 0)
        bins.append({"id": group.id, "prediction": p, "observed_fraction": k / count, "opportunities": count})
    return {
        "brier": brier / n,
        "mean_negative_log_score": log_score / n if math.isfinite(log_score) else None,
        "impossible_observation": not math.isfinite(log_score),
        "opportunities": n,
        "calibration_rows": bins,
        "split_review": split_review,
    }


def posterior_predictive_check(posterior: PartialPoolingPosterior, group_id, *, size, seed):
    group = posterior.groups[group_id]
    draws = posterior.predictive_counts(group_id, group.opportunities, size=size, seed=seed)
    return {
        "observed_failures": group.failures,
        "predictive_p05_p50_p95": np.quantile(draws, [0.05, 0.5, 0.95]).tolist(),
        "replicate_fraction_ge_observed": float(np.mean(draws >= group.failures)),
        "independent_validation": False,
        "draws": size,
        "seed": seed,
    }


def transfer_sensitivity(groups, candidate_hyperpriors, *, exchangeability_review):
    if not candidate_hyperpriors:
        raise ValueError("named alternative priors required")
    result = {}
    for name, grid in candidate_hyperpriors.items():
        posterior = fit_partial_pooling(groups, grid, exchangeability_review=exchangeability_review)
        result[name] = {g.id: posterior.summary(g.id) for g in groups}
    return result


class ExpertJudgment(Contract):
    expert_id: Name
    quantile_probabilities: tuple[Probability, Probability, Probability]
    quantile_values: tuple[Probability, Probability, Probability]
    evidence: Name

    @model_validator(mode="after")
    def quantiles(self):
        if not all(
            0 < a < b < 1 for a, b in zip(self.quantile_probabilities, self.quantile_probabilities[1:])
        ):
            raise ValueError("strictly increasing interior quantile probabilities required")
        if not all(0 < a < b < 1 for a, b in zip(self.quantile_values, self.quantile_values[1:])):
            raise ValueError("strictly increasing interior quantile values required")
        return self


def fit_elicited_beta(judgment: ExpertJudgment, *, maximum_quantile_error=0.03):
    if not 0 < maximum_quantile_error < 1:
        raise ValueError("quantile fit tolerance must be in (0,1)")
    q, values = np.asarray(judgment.quantile_probabilities), np.asarray(judgment.quantile_values)

    def residual(parameters):
        a, b = np.exp(parameters)
        return beta.ppf(q, a, b) - values

    result = least_squares(residual, np.log([1.0, 10.0]), bounds=(-10, 15), max_nfev=2000)
    error = float(np.max(np.abs(residual(result.x))))
    if not result.success or error > maximum_quantile_error:
        raise ValueError("elicited quantiles do not fit a beta within the declared tolerance")
    a, b = np.exp(result.x)
    return {
        "expert_id": judgment.expert_id,
        "alpha": float(a),
        "beta": float(b),
        "maximum_quantile_error": error,
        "evidence": judgment.evidence,
        "origin": "elicited_not_observed",
    }


def expert_calibration_weights(predictions, outcomes, *, temperature, seed_evidence):
    if (
        not seed_evidence.strip()
        or not math.isfinite(temperature)
        or temperature <= 0
        or not outcomes
        or not predictions
    ):
        raise ValueError("positive temperature and independently known seed outcomes required")
    if any(type(value) is not bool for value in outcomes.values()):
        raise ValueError("seed outcomes must be binary observations")
    scores = {}
    for expert, values in predictions.items():
        if set(values) != set(outcomes):
            raise ValueError("every expert must assess the same seed items")
        scores[expert] = math.fsum(
            (probability(values[key]) - float(outcome)) ** 2 for key, outcome in outcomes.items()
        ) / len(outcomes)
    logits = -np.asarray(list(scores.values())) / temperature
    weights = np.exp(logits - logsumexp(logits))
    return {
        "weights": dict(zip(scores, weights.tolist())),
        "seed_brier": scores,
        "seed_evidence": seed_evidence,
        "target_domain_calibrated": False,
    }


def sample_expert_mixture(fitted, weights, *, size, seed):
    if not fitted or set(weights) != {row["expert_id"] for row in fitted} or len(fitted) != len(weights):
        raise ValueError("one explicit weight per fitted expert required")
    if (
        type(size) is not int
        or size < 1
        or not math.isclose(sum(probability(w) for w in weights.values()), 1, abs_tol=1e-12, rel_tol=0)
    ):
        raise ValueError("positive size and normalized weights required")
    rng = np.random.default_rng(seed)
    choices = rng.choice(len(fitted), size=size, p=[weights[row["expert_id"]] for row in fitted])
    a, b = np.asarray([row["alpha"] for row in fitted]), np.asarray([row["beta"] for row in fitted])
    if np.any(a <= 0) or np.any(b <= 0) or not np.all(np.isfinite(a + b)):
        raise ValueError("valid fitted beta parameters required")
    return rng.beta(a[choices], b[choices])
