"""Paired prediction checks and causal monitoring metrics with explicit missingness."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


def _pair(observed, predicted):
    y, p = np.asarray(observed, float), np.asarray(predicted, float)
    if (
        y.ndim != 1
        or not len(y)
        or y.shape != p.shape
        or not np.isfinite(y).all()
        or not np.isfinite(p).all()
    ):
        raise ValueError("matched nonempty finite observed/predicted arrays required")
    return y, p


def regression_metrics(observed, predicted):
    y, p = _pair(observed, predicted)
    residual = p - y
    total = float(np.sum((y - y.mean()) ** 2))
    return {
        "observations": len(y),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "bias": float(residual.mean()),
        "r2": 1.0 - float(np.sum(residual**2)) / total if total > 0 else None,
        "observation_kind": "observed_measurement",
        "prediction_kind": "model_estimate",
    }


def calibration_width(observed, predicted, *, nominal_coverage=0.9):
    y, p = _pair(observed, predicted)
    if not 0 < nominal_coverage < 1:
        raise ValueError("interior nominal coverage required")
    rank = math.ceil((len(y) + 1) * nominal_coverage)
    if rank > len(y):
        return None
    return float(np.partition(np.abs(y - p), rank - 1)[rank - 1])


def interval_metrics(observed, predicted, *, half_width):
    y, p = _pair(observed, predicted)
    if half_width is None:
        return {
            "coverage": None,
            "width": None,
            "reason": "calibration sample too small for finite order statistic",
        }
    if not np.isfinite(half_width) or half_width < 0:
        raise ValueError("finite nonnegative interval half-width required")
    return {
        "coverage": float(np.mean(np.abs(y - p) <= half_width)),
        "width": float(2 * half_width),
        "exchangeability_guarantee": False,
    }


def paired_block_rmse(observed, predicted, baseline, *, block_rows, repeats=1000, seed=20261026):
    y, p = _pair(observed, predicted)
    _, b = _pair(observed, baseline)
    if type(block_rows) is not int or block_rows < 1 or type(repeats) is not int or repeats < 100:
        raise ValueError("positive block rows and at least 100 replicates required")
    size = min(block_rows, len(y))
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(repeats):
        starts = rng.integers(0, len(y) - size + 1, math.ceil(len(y) / size))
        indices = (starts[:, None] + np.arange(size)).ravel()[: len(y)]
        differences.append(
            np.sqrt(np.mean((p[indices] - y[indices]) ** 2))
            - np.sqrt(np.mean((b[indices] - y[indices]) ** 2))
        )
    return {
        "model_minus_baseline_rmse": float(np.sqrt(np.mean((p - y) ** 2)) - np.sqrt(np.mean((b - y) ** 2))),
        "descriptive_block_95_interval": list(map(float, np.quantile(differences, [0.025, 0.975]))),
        "block_rows": size,
        "repeats": repeats,
        "interpretation": "Paired moving-block resampling; no IID or field-transfer coverage guarantee",
    }


@dataclass(frozen=True)
class RobustReference:
    center: tuple[float, ...]
    scale: tuple[float, ...]

    def __post_init__(self):
        c, s = np.asarray(self.center), np.asarray(self.scale)
        if (
            c.ndim != 1
            or not len(c)
            or c.shape != s.shape
            or not np.isfinite(c).all()
            or not np.isfinite(s).all()
            or np.any(s <= 0)
        ):
            raise ValueError("finite location and positive matched scales required")

    def score(self, values):
        x = np.asarray(values, float)
        if x.ndim != 2 or x.shape[1] != len(self.center):
            raise ValueError("measurement columns do not match fitted reference")
        complete = np.isfinite(x).all(axis=1)
        result = np.full(len(x), np.nan)
        result[complete] = np.max(np.abs((x[complete] - self.center) / self.scale), axis=1)
        return result


def fit_robust_reference(values, *, scale_floors):
    x, floors = np.asarray(values, float), np.asarray(scale_floors, float)
    if x.ndim != 2 or len(x) < 2 or floors.shape != (x.shape[1],) or not np.isfinite(x).all():
        raise ValueError("complete training matrix and explicit per-column scale floors required")
    if not np.isfinite(floors).all() or np.any(floors <= 0):
        raise ValueError("positive finite scale floors required")
    center = np.median(x, axis=0)
    scale = np.maximum(1.4826 * np.median(np.abs(x - center), axis=0), floors)
    return RobustReference(tuple(map(float, center)), tuple(map(float, scale)))


@dataclass(frozen=True)
class SampleAlarmPolicy:
    trigger: float
    reset: float
    persistence_samples: int = 3
    recovery_samples: int = 2

    def __post_init__(self):
        if not np.isfinite(self.trigger) or not np.isfinite(self.reset) or self.reset > self.trigger:
            raise ValueError("finite ordered sample-alarm thresholds required")
        if any(type(v) is not int or v < 1 for v in (self.persistence_samples, self.recovery_samples)):
            raise ValueError("positive integer persistence/recovery samples required")

    def evaluate(self, scores):
        x = np.asarray(scores, float)
        if x.ndim != 1 or not len(x):
            raise ValueError("nonempty one-dimensional score sequence required")
        active, high, low = False, 0, 0
        flags, valid, starts = [], [], []
        for i, value in enumerate(x):
            known = bool(np.isfinite(value))
            valid.append(known)
            if not known:
                high = low = 0
            elif not active:
                high = high + 1 if value >= self.trigger else 0
                if high >= self.persistence_samples:
                    active, low = True, 0
                    starts.append(i)
            else:
                low = low + 1 if value <= self.reset else 0
                if low >= self.recovery_samples:
                    active, high = False, 0
            flags.append(active)
        return {
            "alarms": np.asarray(flags),
            "valid": np.asarray(valid),
            "activation_indices": starts,
            "persistence_unit": "source_samples",
            "human_error_probability": None,
        }


def _segments(flags):
    flags = np.asarray(flags, bool)
    changes = np.diff(np.r_[False, flags, False].astype(int))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def detection_metrics(labels, alarm_result, *, elapsed_s=None, clock_qualified=False):
    raw = np.asarray(labels)
    a, valid = np.asarray(alarm_result["alarms"]), np.asarray(alarm_result["valid"])
    if raw.ndim != 1 or not len(raw) or raw.shape != a.shape or raw.shape != valid.shape:
        raise ValueError("matched nonempty annotation/alarm/missingness arrays required")
    if not np.isin(raw, [0, 1]).all() or a.dtype != bool or valid.dtype != bool:
        raise ValueError("binary source labels and boolean alarm/validity masks required")
    if type(clock_qualified) is not bool:
        raise ValueError("explicit boolean clock qualification required")
    times = None
    if clock_qualified:
        times = np.asarray(elapsed_s, float)
        if times.shape != raw.shape or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
            raise ValueError("qualified physical time must strictly increase")
    y = raw.astype(bool)
    tp, fp = int(np.sum(y & a & valid)), int(np.sum(~y & a & valid))
    fn, tn = int(np.sum(y & ~a & valid)), int(np.sum(~y & ~a & valid))
    truth_events = _segments(y)
    starts = alarm_result.get("activation_indices", [])
    if any(
        type(i) is not int or not 0 <= i < len(y) or not (a[i] and valid[i]) for i in starts
    ) or starts != sorted(set(starts)):
        raise ValueError("ordered unique valid alarm activation indices required")
    if any(i > 0 and a[i - 1] for i in starts):
        raise ValueError("an activation cannot be invented inside a continuing alarm")
    used, events = set(), []
    for start, end in truth_events:
        match = next((i for i in starts if i not in used and start <= i < end), None)
        if match is not None:
            used.add(match)
        events.append(
            {
                "start_index": int(start),
                "end_index_exclusive": int(end),
                "detected": match is not None,
                "delay_samples": int(match - start) if match is not None else None,
                "delay_s": float(times[match] - times[start])
                if times is not None and match is not None
                else None,
                "unknown_sensor_samples": int(np.sum(~valid[start:end])),
            }
        )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "unknown_samples": int(np.sum(~valid)),
        "unknown_positive_samples": int(np.sum(y & ~valid)),
        "known_positive_samples": int(np.sum(y & valid)),
        "overall_measurement_coverage_fraction": float(np.mean(valid)),
        "point_precision": tp / (tp + fp) if tp + fp else None,
        "point_recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_fraction_of_known_normal_samples": fp / (fp + tn) if fp + tn else None,
        "anomaly_events": len(events),
        "alarm_activations": len(starts),
        "detected_events": len(used),
        "false_alarm_activations": len(starts) - len(used),
        "event_recall": len(used) / len(events) if events else None,
        "event_precision": len(used) / len(starts) if starts else None,
        "physical_delay_qualified": clock_qualified,
        "events": events,
        "point_adjustment_applied": False,
        "human_error_probability": None,
    }


def aggregate_binomial_metrics(failures, opportunities, probabilities):
    k, n, p = np.asarray(failures), np.asarray(opportunities), np.asarray(probabilities, float)
    if k.ndim != 1 or not len(k) or k.shape != n.shape or k.shape != p.shape:
        raise ValueError("matched count and prediction vectors required")
    if (
        k.dtype.kind not in "iu"
        or n.dtype.kind not in "iu"
        or np.any(k < 0)
        or np.any(n <= 0)
        or np.any(k > n)
    ):
        raise ValueError("verified nonnegative integer errors and positive opportunities required")
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("finite probability predictions required")
    impossible = bool(np.any(((p == 0) & (k > 0)) | ((p == 1) & (k < n))))
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(k > 0, -k * np.log(p), 0) + np.where(n - k > 0, -(n - k) * np.log1p(-p), 0)
    total = int(n.sum())
    return {
        "contexts": len(n),
        "opportunities": total,
        "failures": int(k.sum()),
        "brier": float(np.sum(k * (1 - p) ** 2 + (n - k) * p**2) / total),
        "log_loss": None if impossible else float(np.sum(terms) / total),
        "impossible_prediction": impossible,
        "observed_rate": float(k.sum() / total),
        "predicted_rate": float(np.sum(n * p) / total),
        "independent_crew_validation": False,
    }
