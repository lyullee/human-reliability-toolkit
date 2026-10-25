"""Response-time models retain censoring and the meaning of completion."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

import numpy as np
from scipy.stats import lognorm, weibull_min

from .contracts import Estimate
from .probability import nonnegative, probability


def _observations(durations, completed):
    values = np.asarray(durations, dtype=float)
    events = np.asarray(completed)
    if values.ndim != 1 or len(values) == 0 or events.shape != values.shape:
        raise ValueError("matched nonempty observation vectors required")
    if events.dtype.kind != "b" or not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("finite nonnegative durations and boolean completion flags required")
    return values, events


class TimeModel(Protocol):
    def cdf(self, time_s: float) -> float: ...
    def sample(self, size: int, rng: np.random.Generator) -> np.ndarray: ...


@dataclass(frozen=True)
class LognormalTime:
    median_s: float
    log_sigma: float

    def __post_init__(self):
        if nonnegative(self.median_s) == 0 or nonnegative(self.log_sigma) == 0:
            raise ValueError("positive median and log standard deviation required")

    def cdf(self, time_s):
        return float(lognorm.cdf(nonnegative(time_s), self.log_sigma, scale=self.median_s))

    def sample(self, size, rng):
        return rng.lognormal(math.log(self.median_s), self.log_sigma, size)


@dataclass(frozen=True)
class WeibullTime:
    scale_s: float
    shape: float

    def __post_init__(self):
        if nonnegative(self.scale_s) == 0 or nonnegative(self.shape) == 0:
            raise ValueError("positive scale and shape required")

    def cdf(self, time_s):
        return float(weibull_min.cdf(nonnegative(time_s), self.shape, scale=self.scale_s))

    def sample(self, size, rng):
        return self.scale_s * rng.weibull(self.shape, size)


class KaplanMeierTime:
    """Nonparametric time to completion with right censoring and exact tie handling.

    A terminal wrong action is a competing failure, not an ordinary censored
    completion time. Supply those outcomes separately through a failure model.
    """

    def __init__(self, durations, completed):
        self.durations, self.completed = _observations(durations, completed)
        self.times = np.unique(self.durations)
        survival, values = 1.0, []
        for time in self.times:
            at_risk = int(np.count_nonzero(self.durations >= time))
            events = int(np.count_nonzero((self.durations == time) & self.completed))
            survival *= 1 - events / at_risk
            values.append(survival)
        self.survival = np.asarray(values)

    def cdf(self, time_s):
        t = nonnegative(time_s)
        if t > self.times[-1] and self.survival[-1] > 0:
            raise ValueError("completion probability beyond censored support is unidentified")
        index = np.searchsorted(self.times, t, side="right") - 1
        return 0.0 if index < 0 else float(1 - self.survival[index])

    def sample(self, size, rng):
        if self.survival[-1] > 0:
            raise ValueError("cannot sample an unidentified censored tail")
        indices = np.searchsorted(1 - self.survival, rng.random(size), side="left")
        return self.times[indices]


def fit_weibull_censored(durations, completed) -> WeibullTime:
    """Use lifelines' censored likelihood rather than replacing censor times with completions."""
    from lifelines import WeibullFitter

    values, events = _observations(durations, completed)
    if np.any(values <= 0) or np.count_nonzero(events) < 2:
        raise ValueError("Weibull fit requires positive times and at least two completions")
    fit = WeibullFitter().fit(values, event_observed=events)
    return WeibullTime(float(fit.lambda_), float(fit.rho_))


def apply_deadline(
    initial: Estimate, completion_given_no_initial_failure: TimeModel, deadline_s: float, *, evidence_id: str
) -> Estimate:
    """Count wrong responses and otherwise-correct responses completed too late."""
    if "timing" in initial.includes:
        raise ValueError("timing is already included in the input estimate")
    success_in_time = probability(completion_given_no_initial_failure.cdf(deadline_s))
    q = 1 - (1 - initial.probability) * success_in_time
    evidence = tuple(dict.fromkeys(initial.evidence_ids + (evidence_id,)))
    return Estimate(
        event_id=initial.event_id,
        method="conditional_deadline",
        probability=q,
        conditioning=initial.conditioning,
        evidence_ids=evidence,
        includes=initial.includes + ("timing",),
        status="research",
        trace={
            "initial": initial.model_dump(mode="json"),
            "deadline_s": deadline_s,
            "completion_probability_given_no_initial_failure": success_in_time,
        },
    )


def response_bins(model: TimeModel, boundaries_s, structural_failure=0.0):
    """Disjoint finite completion bins plus an explicit unresolved/failed branch."""
    edges = np.asarray(boundaries_s, dtype=float)
    if (
        edges.ndim != 1
        or len(edges) == 0
        or np.any(np.diff(edges) <= 0)
        or not np.all(np.isfinite(edges))
        or edges[0] <= 0
    ):
        raise ValueError("positive strictly increasing finite boundaries required")
    q = probability(structural_failure)
    cumulative = np.asarray([probability(model.cdf(float(time))) for time in edges])
    if np.any(np.diff(cumulative) < 0):
        raise ValueError("time model CDF is not monotone")
    masses = (1 - q) * np.diff(np.r_[0.0, cumulative])
    rows = [
        {
            "id": f"complete_by_{upper:g}s",
            "lower_s": float(lower),
            "upper_s": float(upper),
            "probability": float(mass),
        }
        for lower, upper, mass in zip(np.r_[0.0, edges[:-1]], edges, masses)
    ]
    rows.append(
        {
            "id": "not_completed_within_horizon",
            "lower_s": float(edges[-1]),
            "upper_s": None,
            "probability": float(q + (1 - q) * (1 - cumulative[-1])),
        }
    )
    return rows


class CensoredRegression:
    """Optional lifelines AFT or Cox model for declared task covariates.

    Callers must map native durations to seconds and identify genuine
    right-censoring before fitting. A wrong action is not a censoring event.
    """

    def __init__(self, model="weibull_aft"):
        if model not in {"weibull_aft", "cox_ph"}:
            raise ValueError("supported survival regression models are weibull_aft and cox_ph")
        self.model_name = model
        self.model = None

    def fit(self, frame, *, duration_col, completed_col, covariates, time_unit, evidence_id):
        from lifelines import CoxPHFitter, WeibullAFTFitter

        if time_unit != "s" or not evidence_id.strip() or not covariates:
            raise ValueError("explicit seconds, evidence and covariate columns required")
        if {duration_col, completed_col} & set(covariates):
            raise ValueError("duration and outcome cannot be predictor columns")
        chosen = [duration_col, completed_col, *covariates]
        if (
            len(set(chosen)) != len(chosen)
            or not set(chosen) <= set(frame)
            or frame[chosen].isna().any().any()
        ):
            raise ValueError("nonmissing distinct duration, outcome and covariates required")
        values, events = _observations(frame[duration_col], frame[completed_col])
        if np.any(values <= 0) or np.count_nonzero(events) < 2:
            raise ValueError("positive times and at least two genuine completions required")
        model = WeibullAFTFitter() if self.model_name == "weibull_aft" else CoxPHFitter()
        model.fit(frame[chosen].copy(), duration_col=duration_col, event_col=completed_col)
        self.model, self.covariates, self.evidence_id = model, tuple(covariates), evidence_id
        return self

    def completion_probability(self, time_s, context):
        if self.model is None or not set(self.covariates) <= set(context):
            raise ValueError("fit model and required context predictors needed")
        result = self.model.predict_survival_function(
            context[list(self.covariates)], times=[nonnegative(time_s)]
        )
        return 1 - result.iloc[0].to_numpy(float)


def first_threshold_crossing(time_s, values, threshold, *, direction="above"):
    """Linear interpolation of a declared physical trajectory, not a human-time estimate."""
    t, y = np.asarray(time_s, float), np.asarray(values, float)
    if (
        t.ndim != 1
        or y.shape != t.shape
        or len(t) < 2
        or np.any(np.diff(t) <= 0)
        or not np.all(np.isfinite(t))
        or not np.all(np.isfinite(y))
    ):
        raise ValueError("finite matched increasing trajectory required")
    if direction not in {"above", "below"} or not math.isfinite(threshold):
        raise ValueError("finite threshold and above/below direction required")
    reached = y >= threshold if direction == "above" else y <= threshold
    indices = np.flatnonzero(reached)
    if not len(indices):
        return None
    index = indices[0]
    if index == 0:
        return float(t[0])
    fraction = (threshold - y[index - 1]) / (y[index] - y[index - 1])
    return float(t[index - 1] + fraction * (t[index] - t[index - 1]))
