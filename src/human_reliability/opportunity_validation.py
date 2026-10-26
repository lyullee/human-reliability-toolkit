"""Denominator-aware evaluation with frozen predictions and explicit dependence limits."""

from __future__ import annotations

from importlib.resources import files
import json
import math
from typing import Literal

import numpy as np
from scipy.stats import beta

from .contracts import Contract, Name, Nonnegative, canonical_digest
from .field_validation import aggregate_binomial_metrics


class ValidationPlan(Contract):
    id: Name
    model_id: Name
    estimand: Literal["initial", "final"]
    evaluation_window_ids: tuple[Name, ...]
    training_demand_ids: tuple[Name, ...] = ()
    training_group_ids: tuple[Name, ...] = ()
    frozen_at_s: Nonnegative
    training_manifest_digest: Name
    external_training_review: Name


def exact_binomial_interval(failures, opportunities, *, confidence=0.95, independence_review):
    """Clopper-Pearson interval, conditional on a reviewed independent Bernoulli model."""
    if type(opportunities) is not int or type(failures) is not int or not 0 <= failures <= opportunities:
        raise ValueError("integer binomial counts required")
    if not opportunities or isinstance(confidence, bool) or not 0 < confidence < 1:
        raise ValueError("positive denominator and confidence in (0,1) required")
    if not independence_review.strip():
        raise ValueError("independence review required for binomial uncertainty")
    tail = (1 - confidence) / 2
    return {
        "lower": float(beta.ppf(tail, failures, opportunities - failures + 1)) if failures else 0.0,
        "upper": float(beta.ppf(1 - tail, failures + 1, opportunities - failures))
        if failures < opportunities else 1.0,
        "confidence": confidence, "independence_review": independence_review,
    }


def zero_error_plan(target_upper, *, confidence=0.95, independence_review):
    if any(isinstance(x, bool) or not math.isfinite(x) or not 0 < x < 1
           for x in (target_upper, confidence)) or not independence_review.strip():
        raise ValueError("probabilities in (0,1) and independence review required")
    n = math.ceil(math.log1p(-confidence) / math.log1p(-target_upper))
    return {"independent_opportunities_required": n, "target_one_sided_upper": target_upper,
            "confidence": confidence, "assumes_zero_failures": True,
            "independence_review": independence_review,
            "upper_at_n": -math.expm1(math.log1p(-confidence) / n)}


def validate_collection(bundle, plan: ValidationPlan, *, bin_edges=(0.0, 0.01, 0.1, 0.5, 1.0),
                        bootstrap_replicates=0, seed=1729):
    """Evaluate every eligible demand in preselected windows; complete cases retain bounds."""
    ValidationPlan.model_validate(plan.model_dump())
    audit = bundle.require_reconciled()
    ledger = bundle.ledger()
    windows = set(plan.evaluation_window_ids)
    if not windows or len(windows) != len(plan.evaluation_window_ids) or not windows <= set(ledger.windows):
        raise ValueError("unique known evaluation windows required")
    selected = [r for r in ledger.opportunities.values() if r.window_id in windows]
    if not selected:
        raise ValueError("nonempty evaluation cohort required")
    start = min(r.start_s for r in selected)
    if plan.frozen_at_s >= start:
        raise ValueError("validation plan must precede evaluation opportunities")
    train_ids, train_groups = set(plan.training_demand_ids), set(plan.training_group_ids)
    # Known training IDs also reveal their groups, even if the manifest omitted them.
    train_groups |= {r.group_id for r in ledger.opportunities.values() if r.id in train_ids}
    if any(r.id in train_ids or r.group_id in train_groups for r in selected):
        raise ValueError("training/evaluation demand or group leakage")
    if any(r.end_s > plan.frozen_at_s for r in ledger.opportunities.values() if r.id in train_ids):
        raise ValueError("known training outcomes must precede the frozen model plan")
    predictions = {r.demand_id: r for r in bundle.predictions if r.model_id == plan.model_id}
    if any(r.id not in predictions for r in selected):
        raise ValueError("prediction required for EVERY eligible evaluation demand, including unknown outcomes")
    if any(predictions[r.id].issued_s >= r.start_s for r in selected):
        raise ValueError("prediction must be issued before opportunity onset")
    if any(predictions[r.id].issued_s < plan.frozen_at_s for r in selected):
        raise ValueError("evaluation predictions must follow the frozen validation plan")
    edges = np.asarray(bin_edges, float)
    if (edges.ndim != 1 or len(edges) < 2 or edges[0] != 0 or edges[-1] != 1
            or not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0)):
        raise ValueError("strictly increasing calibration edges spanning [0,1] required")
    snapshot = ledger.snapshot(bundle.protocol.event_id, estimand=plan.estimand, window_ids=windows)
    known = set(snapshot["counted_ids"])
    rows = [r for r in selected if r.id in known]
    if not rows:
        raise ValueError("no adjudicated evaluation outcomes")
    y = np.asarray([r.initial_error if plan.estimand == "initial" else r.final_failure for r in rows], int)
    p = np.asarray([predictions[r.id].probability for r in rows])
    metrics = aggregate_binomial_metrics(y, np.ones(len(y), int), p)
    bins = []
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (p >= low) & ((p <= high) if index == len(edges) - 2 else (p < high))
        bins.append({"lower": float(low), "upper": float(high), "n": int(mask.sum()),
                     "failures": int(y[mask].sum()), "predicted_mean": float(p[mask].mean())
                     if mask.any() else None, "observed_fraction": float(y[mask].mean())
                     if mask.any() else None})
    bootstrap = None
    if type(bootstrap_replicates) is not int or bootstrap_replicates < 0:
        raise ValueError("nonnegative integer bootstrap replicate count required")
    if bootstrap_replicates:
        groups = sorted({r.group_id for r in rows})
        if len(groups) < 2 or bootstrap_replicates < 200:
            raise ValueError("at least two observed groups and 200 bootstrap replicates required")
        rng = np.random.default_rng(seed)
        group_rows = [np.array([i for i, r in enumerate(rows) if r.group_id == g]) for g in groups]
        values = []
        for _ in range(bootstrap_replicates):
            index = np.concatenate([group_rows[i] for i in rng.integers(0, len(groups), len(groups))])
            values.append(float(np.mean((y[index] - p[index]) ** 2)))
        bootstrap = {"unit": "declared_group", "groups": len(groups), "replicates": bootstrap_replicates,
                     "seed": seed, "brier_percentile_95": np.quantile(values, [0.025, 0.975]).tolist(),
                     "qualification": "Requires representative independent groups; not certified by resampling."}
    return {"plan_digest": canonical_digest(plan), "collection_audit": audit,
            "evaluation_snapshot": snapshot, "metrics_complete_cases": metrics, "calibration_bins": bins,
            "eligible_evaluation_demands": len(selected), "unknown_outcomes": len(selected) - len(rows),
            "failure_fraction_bounds": [int(y.sum()) / len(selected),
                                        (int(y.sum()) + len(selected) - len(rows)) / len(selected)],
            "cluster_bootstrap": bootstrap, "prospective_prediction_timing_checked": True,
            "training_manifest_digest": plan.training_manifest_digest,
            "external_training_review": plan.external_training_review,
            "setting": bundle.protocol.setting, "industrial_hep_validated": False}


def opportunity_benchmarks():
    """Separate aggregate endpoint benchmarks from the reusable human-HEP catalog."""
    return json.loads(files("human_reliability").joinpath("data/opportunity_benchmarks.json").read_text("utf-8"))
