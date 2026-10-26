"""Interchangeable estimators; coefficients and event scope remain explicit."""

from __future__ import annotations

import math
from typing import Protocol

from .contracts import Estimate, MethodInput
from .probability import probability


class Estimator(Protocol):
    def __call__(self, request: MethodInput) -> Estimate: ...


class MethodRegistry:
    """Register application-specific estimators without changing the calculation core."""

    def __init__(self):
        self._methods: dict[str, Estimator] = {}

    def register(self, name: str, estimator: Estimator, *, replace=False):
        if not name.strip() or not callable(estimator):
            raise ValueError("method name and callable estimator required")
        if name in self._methods and not replace:
            raise ValueError("method already registered")
        self._methods[name] = estimator

    def evaluate(self, name: str, request: MethodInput) -> Estimate:
        if name not in self._methods:
            raise ValueError(f"unregistered method: {name}")
        result = self._methods[name](request)
        if not isinstance(result, Estimate) or result.event_id != request.event.id:
            raise ValueError("estimator must return an Estimate for the requested event")
        if result.conditioning != request.event.conditioning:
            raise ValueError("estimator returned a different conditioning definition")
        evidence = {item.id for item in request.evidence}
        if set(result.evidence_ids) - evidence:
            raise ValueError("estimator cites evidence absent from the request")
        if request.event.includes_timing and "timing" not in result.includes:
            raise ValueError("event requires timing but estimator did not include it")
        if request.event.includes_recovery and "recovery" not in result.includes:
            raise ValueError("event requires recovery but estimator did not include it")
        return result

    @property
    def names(self):
        return tuple(sorted(self._methods))


def declared_estimator(value: float, evidence_id: str, *, includes=()) -> Estimator:
    """Bind an explicitly justified probability; no hidden generic HEP is supplied."""
    p = probability(value)

    def evaluate(request):
        return Estimate(
            event_id=request.event.id,
            method="declared",
            probability=p,
            conditioning=request.event.conditioning,
            evidence_ids=(evidence_id,),
            includes=tuple(includes),
            status="assumed",
        )

    return evaluate


def cognitive_chain(
    event_id: str, conditional_failures: dict[str, float], *, conditioning: str, evidence_ids: tuple[str, ...]
) -> Estimate:
    """Combine failures conditioned on all earlier stages succeeding.

    Supports cognition-informed event decomposition, not official IDHEAS-ECA
    quantification. Each stage needs its own data or elicitation basis.
    """
    if not conditional_failures:
        raise ValueError("nonempty stage probabilities required")
    survival, first_failure = 1.0, {}
    for stage, value in conditional_failures.items():
        if not stage.strip():
            raise ValueError("stage name required")
        p = probability(value)
        first_failure[stage] = survival * p
        survival *= 1 - p
    return Estimate(
        event_id=event_id,
        method="conditional_cognitive_chain",
        probability=1 - survival,
        conditioning=conditioning,
        evidence_ids=evidence_ids,
        status="research",
        trace={
            "first_failure_probabilities": first_failure,
            "all_stages_succeed": survival,
            "stage_order": list(conditional_failures),
        },
    )


def multiplier_probability(
    nominal: float, multipliers: dict[str, float], *, normalization="bounded_odds"
) -> tuple[float, dict]:
    """Explicit multiplier model with a selected, documented saturation policy."""
    p0 = probability(nominal)
    if not multipliers or any(
        isinstance(x, (bool, str)) or not math.isfinite(x) or x <= 0 for x in multipliers.values()
    ):
        raise ValueError("nonempty positive finite multipliers required")
    multiplier = math.prod(multipliers.values())
    if not math.isfinite(multiplier):
        raise ValueError("multiplier overflow")
    raw = p0 * multiplier
    if normalization == "bounded_odds":
        value = raw / (1 + p0 * (multiplier - 1))
    elif normalization == "cap":
        value = min(1.0, raw)
    else:
        raise ValueError("normalization must be bounded_odds or cap")
    return value, {
        "nominal": p0,
        "multipliers": multipliers,
        "normalization": normalization,
        "unbounded_product": raw,
    }


SPAR_H_FACTORS = frozenset(
    {
        "available_time",
        "stress",
        "complexity",
        "experience_training",
        "procedures",
        "ergonomics",
        "fitness",
        "work_processes",
    }
)


def spar_h_probability(
    stage: str, factors: dict[str, float], *, insufficient_time=False, nominal: float | None = None
) -> tuple[float, dict]:
    """SPAR-H arithmetic with caller-supplied factors from a reviewed profile.

    The function supplies no PSF lookup table. It normalizes when at least three
    supplied factors are adverse, following NUREG/CR-6883. Dependency is separate.
    """
    if stage not in {"diagnosis", "action"} or set(factors) != SPAR_H_FACTORS:
        raise ValueError("diagnosis/action and all eight explicitly named factors required")
    p0 = (0.01 if stage == "diagnosis" else 0.001) if nominal is None else probability(nominal)
    if type(insufficient_time) is not bool:
        raise ValueError("insufficient_time must be a boolean")
    if any(
        isinstance(value, (bool, str)) or not math.isfinite(value) or value <= 0 for value in factors.values()
    ):
        raise ValueError("positive finite factor values required")
    if insufficient_time:
        return 1.0, {"stage": stage, "insufficient_time": True}
    adverse = sum(value > 1 for value in factors.values())
    value, trace = multiplier_probability(
        p0, factors, normalization="bounded_odds" if adverse >= 3 else "cap"
    )
    return value, trace | {
        "stage": stage,
        "adverse_factors": adverse,
        "method_reference": "NUREG/CR-6883",
        "profile_owned_by_caller": True,
    }


def heart_probability(nominal: float, effects: tuple[tuple[float, float], ...]) -> tuple[float, dict]:
    """HEART-style effect arithmetic using externally justified nominal/effect inputs.

    This kernel accepts supplied coefficients; source-linked profiles live in
    reference_methods and method_workflows. Values above one are capped and the
    original product remains in the calculation trace.
    """
    p0 = probability(nominal)
    if any(
        isinstance(effect, (bool, str))
        or not math.isfinite(effect)
        or effect < 1
        or not 0 <= probability(weight) <= 1
        for effect, weight in effects
    ):
        raise ValueError("maximum effects >= 1 and assessed proportions within [0,1] required")
    product = math.prod(1 + (effect - 1) * weight for effect, weight in effects)
    raw = p0 * product
    if not math.isfinite(raw):
        raise ValueError("effect product overflow")
    return min(1.0, raw), {"nominal": p0, "effects": effects, "uncapped": raw}


def scenario_mixture(event_id: str, scenarios: tuple[tuple[float, Estimate], ...], *, conditioning: str):
    """Mix exclusive contextual states; estimates must concern the same event."""
    if not scenarios or any(estimate.event_id != event_id for _, estimate in scenarios):
        raise ValueError("nonempty estimates for the same event required")
    weights = [probability(weight) for weight, _ in scenarios]
    if not math.isclose(sum(weights), 1, abs_tol=1e-12, rel_tol=0):
        raise ValueError("exclusive scenario weights must sum to one")
    scope = {estimate.includes for _, estimate in scenarios}
    if len(scope) != 1:
        raise ValueError("cannot mix estimates with different failure scopes")
    evidence = tuple(dict.fromkeys(e for _, estimate in scenarios for e in estimate.evidence_ids))
    return Estimate(
        event_id=event_id,
        method="context_mixture",
        probability=sum(weight * estimate.probability for weight, estimate in scenarios),
        conditioning=conditioning,
        evidence_ids=evidence,
        includes=scenarios[0][1].includes,
        status="research",
        trace={
            "components": [
                dict(weight=weight, estimate=estimate.model_dump(mode="json"))
                for weight, estimate in scenarios
            ]
        },
    )
