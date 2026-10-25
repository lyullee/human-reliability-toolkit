"""Pure payload/object adapters; no remote calls or physical actuator execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from .contracts import Estimate, SignalSeries, canonical_digest
from .probability import nonnegative, probability


def prism_demand(estimate: Estimate, demands_per_year: float, *, factory=None):
    """Build the existing PRISM DemandFailure contract, not a literature FrequencyEvent."""
    payload = {
        "id": estimate.event_id,
        "demands_per_year": nonnegative(demands_per_year),
        "failure_probability_per_demand": estimate.probability,
        "provenance": "human-reliability:" + canonical_digest(estimate),
    }
    return factory(**payload) if factory is not None else payload


def human_initiator(
    estimate: Estimate, demands_per_year: float, *, task_id: str, component_id: str, release_binding: str
):
    """Versioned extension payload; the legacy PRISM literature-only schema cannot accept it."""
    if not all(value.strip() for value in (task_id, component_id, release_binding)):
        raise ValueError("explicit task, equipment and release binding required")
    demand = prism_demand(estimate, demands_per_year)
    return {
        "schema": "human_reliability.initiator.v1",
        "demand": demand,
        "annual_frequency_per_year": demand["demands_per_year"] * estimate.probability,
        "task_id": task_id,
        "component_id": component_id,
        "release_binding": release_binding,
        "failure_definition_owner": "human assessment",
        "physical_validation_claim": False,
        "requires_prism_initiator_extension": True,
    }


def prism_branches(probabilities: Mapping[str, float], *, evidence: str, factory=None):
    if (
        not evidence.strip()
        or not probabilities
        or not np.isclose(sum(probability(p) for p in probabilities.values()), 1, atol=1e-12, rtol=0)
    ):
        raise ValueError("exclusive probabilities summing to one and evidence required")
    rows = (
        {"id": key, "probability_given_initiation": value, "provenance": evidence}
        for key, value in probabilities.items()
    )
    return tuple(factory(**row) if factory is not None else row for row in rows)


def dynasense_scenario(scenario: Any, physical_completion_time_s: float | None, *, factory=None):
    """Bind a completion time while keeping human evidence outside strict physical inputs.

    None means no isolation during this declared horizon, represented by a time
    beyond it. It does not assert permanent failure after the horizon ends.
    """
    payload = scenario.model_dump() if hasattr(scenario, "model_dump") else dict(scenario)
    horizon = nonnegative(payload["horizon_s"])
    payload["isolation_time_s"] = (
        horizon + max(1.0, horizon)
        if physical_completion_time_s is None
        else nonnegative(physical_completion_time_s)
    )
    chosen = factory or (type(scenario) if hasattr(scenario, "model_dump") else None)
    return chosen.model_validate(payload) if chosen is not None else payload


def station_stop_requested(time_s: float, timeline: Mapping[str, Any]) -> bool:
    """Map a correct human command to SafetyPLC.update's manual-stop argument."""
    time = nonnegative(time_s)
    if timeline["status"] == "wrong_action":
        return False
    return time >= nonnegative(timeline["command_time_s"])


def monitoring_context(result: Any, index: int):
    """Consume a DetectionResult-like protocol without treating scores as probabilities."""
    if not 0 <= index < len(result.time_s):
        raise ValueError("monitoring index outside history")
    valid = bool(result.valid[index])
    score = float(result.scores[index])
    if valid and not np.isfinite(score):
        raise ValueError("valid detector result has a nonfinite score")
    return {
        "time_s": float(result.time_s[index]),
        "valid": valid,
        "score": score if valid else None,
        "alarm": bool(result.alarms[index]) if valid else None,
        "detector": result.detector,
        "threshold": float(result.threshold),
        "evidence_type": "monitoring_context",
        "hep_inferred": False,
    }


def observation_series(table: Any, channel: str, *, unit: str, clock_id: str, origin="measured_observation"):
    """Accept lh2dt ObservationTable-compatible fields with explicit quantity meaning."""
    if channel not in table.values or channel not in table.valid_masks:
        raise ValueError("observation channel or validity mask missing")
    values = np.asarray(table.values[channel], float)
    valid = np.asarray(table.valid_masks[channel], bool) & np.isfinite(values)
    return SignalSeries(
        time_s=tuple(map(float, table.time_s)),
        values=tuple(float(value) if ok else None for value, ok in zip(values, valid)),
        valid=tuple(map(bool, valid)),
        clock_id=clock_id,
        unit=unit,
        origin=origin,
    )


def saga_context(
    assessment: Mapping[str, Any],
    *,
    station_id: str,
    scenario_id: str,
    readings: list[dict] | None = None,
    factory=None,
):
    """Attach analysis as explicit context to SAGA's existing HAZOP evaluation request."""
    import json

    text = json.dumps(
        {
            "human_reliability": assessment,
            "meaning": "declared assessment evidence; no automated action authorization",
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    payload = {
        "station_id": station_id,
        "scenario_id": scenario_id,
        "readings": readings or [],
        "context_text": text,
    }
    return factory.model_validate(payload) if factory is not None else payload


def qsafety_frequency_mixture(annual_frequencies, conditional_probabilities, *, factory=None):
    """Preserve total frequency separately from a normalized conditional probability model."""
    rates = np.asarray([nonnegative(value) for value in annual_frequencies], float)
    probabilities = np.asarray([probability(value) for value in conditional_probabilities], float)
    if rates.ndim != 1 or probabilities.shape != rates.shape or len(rates) == 0 or rates.sum() <= 0:
        raise ValueError("matching nonempty rates/probabilities with positive total required")
    total = float(rates.sum())
    weights = rates / total
    payload = {"weights": weights, "probabilities": probabilities}
    model = factory(**payload) if factory is not None else payload
    return {
        "conditional_model": model,
        "total_frequency_per_year": total,
        "weighted_event_rate_per_year": float(np.dot(rates, probabilities)),
    }


def psa_trace(path, *, channel: str, unit: str, clock_id: str, time_column="time_s"):
    """Select one explicitly named process variable; cycle/slot labels stay as context."""
    import pandas as pd

    frame = pd.read_csv(path)
    if not {channel, time_column} <= set(frame):
        raise ValueError("trace clock or channel missing")
    values = frame[channel].to_numpy(float)
    valid = np.isfinite(values)
    return SignalSeries(
        time_s=tuple(map(float, frame[time_column])),
        values=tuple(float(value) if ok else None for value, ok in zip(values, valid)),
        valid=tuple(map(bool, valid)),
        clock_id=clock_id,
        unit=unit,
        origin="process_simulation",
    )
