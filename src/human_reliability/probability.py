"""Probability primitives with explicit event meaning and evidence boundaries."""

from __future__ import annotations

import math
from collections.abc import Iterable
import numpy as np
from scipy.stats import beta

from .contracts import Contract, Estimate, Name, Positive


def probability(value: float) -> float:
    if isinstance(value, (bool, str)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("probability must be finite and within [0,1]")
    return float(value)


def nonnegative(value: float, name="value") -> float:
    if isinstance(value, (bool, str)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def union_independent(values: Iterable[float]) -> float:
    """At least one of distinct independent events, evaluated without rare-event approximation."""
    p = [probability(value) for value in values]
    if not p:
        raise ValueError("at least one event required")
    return float(-math.expm1(math.fsum(math.log1p(-value) for value in p))) if max(p) < 1 else 1.0


def intersection_independent(values: Iterable[float]) -> float:
    p = [probability(value) for value in values]
    if not p:
        raise ValueError("at least one event required")
    return math.prod(p)


class BetaPrior(Contract):
    alpha: Positive
    beta: Positive
    evidence_id: Name

    def posterior(
        self,
        failures: int,
        opportunities: int,
        *,
        event_id: str,
        observation_id: str,
        conditioning: str,
        credibility=0.95,
    ) -> Estimate:
        """Recompute from the original prior and a complete, nonoverlapping observation snapshot."""
        if type(failures) is not int or type(opportunities) is not int or not 0 <= failures <= opportunities:
            raise ValueError(
                "integer failures and opportunities with 0 <= failures <= opportunities required"
            )
        if not observation_id.strip() or not 0 < credibility < 1:
            raise ValueError("observation ID and credibility in (0,1) required")
        a, b = self.alpha + failures, self.beta + opportunities - failures
        low, high = beta.ppf([(1 - credibility) / 2, (1 + credibility) / 2], a, b)
        return Estimate(
            event_id=event_id,
            method="beta_binomial",
            probability=a / (a + b),
            conditioning=conditioning,
            evidence_ids=(self.evidence_id, observation_id),
            uncertainty={
                "distribution": "beta",
                "alpha": a,
                "beta": b,
                "lower": float(low),
                "upper": float(high),
                "credibility": credibility,
            },
            status="empirical",
            trace={
                "failures": failures,
                "opportunities": opportunities,
                "snapshot_id": observation_id,
                "independent_bernoulli_assumption": True,
            },
        )


def sample_estimate(estimate: Estimate, size: int, rng: np.random.Generator) -> np.ndarray:
    if type(size) is not int or size <= 0:
        raise ValueError("positive sample count required")
    uncertainty = estimate.uncertainty
    if uncertainty.get("distribution") == "beta":
        return rng.beta(float(uncertainty["alpha"]), float(uncertainty["beta"]), size)
    if uncertainty:
        raise ValueError("unsupported uncertainty distribution; declare a sampling adapter")
    return np.full(size, estimate.probability)


def demand_frequency(
    demands_per_year: float, failure_probability: float, initiation_given_failure: float = 1.0
) -> float:
    return (
        nonnegative(demands_per_year, "demands/year")
        * probability(failure_probability)
        * probability(initiation_given_failure)
    )


def interval_probability(frequency_per_year: float, horizon_s: float) -> float:
    intensity = nonnegative(frequency_per_year) / (365.25 * 86400)
    return -math.expm1(-intensity * nonnegative(horizon_s))
