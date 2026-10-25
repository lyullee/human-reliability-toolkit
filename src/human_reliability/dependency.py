"""Conditional dependence and recovery are specified at the event boundary."""

from __future__ import annotations

from typing import Literal

from .contracts import Estimate
from .probability import probability


def conditional_dependency(baseline: float, level: Literal["zero", "low", "moderate", "high", "complete"]):
    """THERP/SPAR-H dependency arithmetic conditional on a preceding failure.

    Selecting the level requires a separate assessment. These are not Pearson
    correlations and the adjusted number is not an unconditional HEP.
    """
    p = probability(baseline)
    equations = {
        "zero": p,
        "low": (1 + 19 * p) / 20,
        "moderate": (1 + 6 * p) / 7,
        "high": (1 + p) / 2,
        "complete": 1.0,
    }
    if level not in equations:
        raise ValueError("unrecognized dependency level")
    return equations[level]


def joint_two_failures(first: float, second_given_first_failure: float) -> float:
    return probability(first) * probability(second_given_first_failure)


def apply_recovery(initial: Estimate, failure_to_recover_given_error: float, *, evidence_id: str) -> Estimate:
    """Retain only initial errors not recovered under the stated conditional model."""
    if "recovery" in initial.includes:
        raise ValueError("recovery is already included in the input estimate")
    if evidence_id in initial.evidence_ids:
        evidence_ids = initial.evidence_ids
    else:
        evidence_ids = initial.evidence_ids + (evidence_id,)
    q = probability(failure_to_recover_given_error)
    return Estimate(
        event_id=initial.event_id,
        method="conditional_recovery",
        probability=initial.probability * q,
        conditioning=initial.conditioning,
        evidence_ids=evidence_ids,
        includes=initial.includes + ("recovery",),
        status="research",
        trace={"initial": initial.model_dump(mode="json"), "failure_to_recover_given_error": q},
    )


def series_response_failure(
    detection_failure: float,
    diagnosis_failure_given_detection: float,
    action_failure_given_correct_diagnosis: float,
) -> float:
    return 1 - (1 - probability(detection_failure)) * (1 - probability(diagnosis_failure_given_detection)) * (
        1 - probability(action_failure_given_correct_diagnosis)
    )
