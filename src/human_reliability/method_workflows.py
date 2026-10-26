"""Evidence-bound reference calculations with explicit stage, recovery and dependence scope."""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import Field, model_validator

from .contracts import (
    Contract,
    Estimate,
    Evidence,
    HumanFailureEvent,
    Name,
    Positive,
    Probability,
    canonical_digest,
)
from .dependency import apply_recovery, conditional_dependency
from .evidence_catalog import ApplicabilityReview, EvidenceBinding, builtin_evidence_catalog
from .reference_methods import heart_profile_probability, idheas_cfm_probability, spar_h_profile_probability

Effects = tuple[Literal["timing", "recovery", "dependency"], ...]


class StageSelection(Contract):
    stage: Literal["diagnosis", "action"]
    levels: dict[str, Name]
    conditioning: Name
    allow_unknown: bool = False


class SparWorkflowParameters(Contract):
    stages: tuple[StageSelection, ...] = Field(min_length=1, max_length=2)
    base_includes: Effects = ("timing",)

    @model_validator(mode="after")
    def order(self):
        stages = [s.stage for s in self.stages]
        if len(set(stages)) != len(stages) or len(stages) == 2 and stages != ["diagnosis", "action"]:
            raise ValueError("unique stages in diagnosis-then-action order required")
        if "timing" not in self.base_includes:
            raise ValueError("SPAR-H available-time selection already contributes timing")
        return self


class AssessedEffect(Contract):
    record_id: Name
    proportion: Probability


class HeartWorkflowParameters(Contract):
    task_code: Name
    effects: tuple[AssessedEffect, ...]
    base_includes: Effects


class IdheasWorkflowParameters(Contract):
    function: Literal["detection", "understanding", "decision", "action", "coordination"]
    base_records: dict[str, str | None]
    modifier_records: tuple[Name, ...] = ()
    recovery_divisor: Positive = 1.0
    recovery_evidence: str | None = None
    base_includes: Effects


class CreamRangeParameters(Contract):
    record_id: Name
    selected_value: Probability
    base_includes: Effects


class RecoveryAdjustment(Contract):
    failure_to_recover_given_error: Probability
    evidence: Name


class DependencyAdjustment(Contract):
    level: Literal["zero", "low", "moderate", "high", "complete"]
    preceding_failure_id: Name
    conditioning: Name
    evidence: Name


class MethodWorkflowCase(Contract):
    method: Literal["spar_h_profile", "heart_profile", "idheas_function", "cream_range"]
    event: HumanFailureEvent
    review: ApplicabilityReview
    parameters: dict[str, Any]
    recovery: RecoveryAdjustment | None = None
    dependency: DependencyAdjustment | None = None


def run_method_workflow(case: MethodWorkflowCase, *, catalog=None) -> EvidenceBinding:
    catalog = catalog or builtin_evidence_catalog()
    models = {
        "spar_h_profile": SparWorkflowParameters,
        "heart_profile": HeartWorkflowParameters,
        "idheas_function": IdheasWorkflowParameters,
        "cream_range": CreamRangeParameters,
    }
    p = models[case.method].model_validate_json(json.dumps(case.parameters, allow_nan=False))
    record_ids, trace, custom_evidence = [], {}, []
    includes = tuple(p.base_includes)
    if len(includes) != len(set(includes)):
        raise ValueError("failure-scope effects must be unique")
    if case.method == "spar_h_profile":
        components = []
        for stage in p.stages:
            value, details = spar_h_profile_probability(
                stage.stage, stage.levels, allow_unknown=stage.allow_unknown, catalog=catalog
            )
            components.append(value)
            record_ids += details["record_ids"]
            trace[stage.stage] = details | {"conditioning": stage.conditioning}
        value = 1 - math.prod(1 - q for q in components)
        trace["stage_meaning"] = "Each later-stage failure is conditional on earlier stages succeeding."
    elif case.method == "heart_profile":
        value, trace = heart_profile_probability(
            p.task_code, tuple((e.record_id, e.proportion) for e in p.effects), catalog=catalog
        )
        record_ids += trace["record_ids"]
    elif case.method == "idheas_function":
        bases = {}
        if set(p.base_records) != {"scenario_familiarity", "information", "task_complexity"}:
            raise ValueError("explicit selection for all three base influences required")
        for family, identity in p.base_records.items():
            if identity is None:
                bases[family] = 0.0
            else:
                row = catalog.get(identity)
                if (
                    row.source_id != "idheas_eca_2022"
                    or row.kind != "method_component"
                    or row.function != p.function
                    or row.conditions.get("pif_family") != family
                ):
                    raise ValueError("base record does not match the function and influence family")
                bases[family] = row.value
                record_ids.append(identity)
        if len(p.modifier_records) != len(set(p.modifier_records)):
            raise ValueError("modifier references must not repeat")
        weights, codes = {}, set()
        for identity in p.modifier_records:
            row = catalog.get(identity)
            if (
                row.source_id != "idheas_eca_2022"
                or row.kind != "method_multiplier"
                or row.function != p.function
                or row.basis == "placeholder"
            ):
                raise ValueError("calibrated matching function modifier required; placeholders are withheld")
            code = row.conditions.get("pif_code")
            if code in codes:
                raise ValueError("alternative levels of one influence cannot be combined")
            codes.add(code)
            weights[identity] = row.value
            record_ids.append(identity)
        value, trace = idheas_cfm_probability(p.function, bases, weights, recovery_divisor=p.recovery_divisor)
        if trace["all_base_factors_inactive_floor_used"]:
            record_ids.append("eca.minimum." + p.function)
        if p.recovery_divisor > 1:
            if not (p.recovery_evidence or "").strip() or "recovery" in includes:
                raise ValueError("recovery divisor requires separate evidence and no prior recovery credit")
            includes += ("recovery",)
            custom_evidence.append(
                Evidence(
                    id=p.recovery_evidence,
                    reference="Explicit function recovery divisor",
                    origin="assumed",
                    applicability=case.review.scope_rationale,
                )
            )
        trace["scope"] = "Source-referenced single-function arithmetic; no full IDHEAS HFE/timing workflow"
    else:
        row = catalog.get(p.record_id)
        if row.method != "cream_control_mode" or row.kind != "method_interval":
            raise ValueError("reviewed CREAM control-mode interval required")
        base_review = case.review.model_copy(update={"included_effects": includes})
        base_event = case.event.model_copy(
            update={"includes_timing": "timing" in includes, "includes_recovery": "recovery" in includes}
        )
        binding = catalog.bind(p.record_id, base_event, review=base_review, selected_value=p.selected_value)
        value, trace = binding.estimate.probability, binding.estimate.trace
        record_ids.append(row.id)
        trace["scope"] = "Explicit point selection inside a reported CREAM mode interval; mode not inferred"
    record_ids = list(dict.fromkeys(record_ids))
    for identity in record_ids:
        if catalog.sources[catalog.get(identity).source_id].rights.numeric_reuse == "not_cleared":
            raise ValueError("numeric reference reuse is not cleared")
    evidence = [catalog.evidence_for(identity) for identity in record_ids] + custom_evidence
    if not evidence:
        raise ValueError("workflow calculation has no numerical provenance")
    estimate = Estimate(
        event_id=case.event.id,
        method=case.method,
        probability=value,
        conditioning=case.event.conditioning,
        evidence_ids=tuple(e.id for e in evidence),
        includes=includes,
        status="research"
        if any(catalog.get(key).basis == "placeholder" for key in record_ids)
        else "method_estimate",
        trace=trace
        | {
            "workflow_input_digest": canonical_digest(case),
            "review": case.review.model_dump(mode="json"),
            "record_ids": record_ids,
            "field_validation_claim": False,
        },
    )
    if case.recovery:
        estimate = apply_recovery(
            estimate, case.recovery.failure_to_recover_given_error, evidence_id=case.recovery.evidence
        )
        evidence.append(
            Evidence(
                id=case.recovery.evidence,
                reference="Declared conditional recovery model",
                origin="assumed",
                applicability=case.review.scope_rationale,
            )
        )
    if case.dependency:
        if "dependency" in estimate.includes or case.dependency.conditioning != case.event.conditioning:
            raise ValueError("dependency scope already applied or conditioning disagrees")
        value = conditional_dependency(estimate.probability, case.dependency.level)
        estimate = estimate.model_copy(
            update={
                "probability": value,
                "includes": estimate.includes + ("dependency",),
                "evidence_ids": estimate.evidence_ids + (case.dependency.evidence,),
                "trace": estimate.trace
                | {
                    "preceding_failure_id": case.dependency.preceding_failure_id,
                    "dependency_level": case.dependency.level,
                },
            }
        )
        evidence.append(
            Evidence(
                id=case.dependency.evidence,
                reference="Declared conditional dependence review",
                origin="elicited",
                applicability=case.dependency.conditioning,
            )
        )
    if len({e.id for e in evidence}) != len(evidence):
        raise ValueError("workflow evidence identities collide")
    if set(estimate.includes) != set(case.review.included_effects):
        raise ValueError("workflow effects must exactly match the final application-scope review")
    if (
        case.event.includes_timing
        and "timing" not in estimate.includes
        or case.event.includes_recovery
        and "recovery" not in estimate.includes
    ):
        raise ValueError("workflow does not cover the target event's failure scope")
    return EvidenceBinding(estimate=estimate, evidence=tuple(evidence))


def workflow_estimator(case: MethodWorkflowCase, *, catalog=None):
    def evaluate(request):
        if request.event != case.event:
            raise ValueError("registered workflow belongs to another event definition")
        return run_method_workflow(case, catalog=catalog).estimate

    return evaluate


def method_workflow_schema():
    """Expose method-specific parameter schemas without restricting the native registry API."""
    schema = MethodWorkflowCase.model_json_schema()
    definitions = schema.setdefault("$defs", {})
    conditions = []
    for method, model in {
        "spar_h_profile": SparWorkflowParameters,
        "heart_profile": HeartWorkflowParameters,
        "idheas_function": IdheasWorkflowParameters,
        "cream_range": CreamRangeParameters,
    }.items():
        parameters = model.model_json_schema()
        for name, value in parameters.pop("$defs", {}).items():
            if name in definitions and definitions[name] != value:
                raise ValueError("workflow parameter schema identity conflict")
            definitions[name] = value
        definitions[model.__name__] = parameters
        conditions.append(
            {
                "if": {"properties": {"method": {"const": method}}, "required": ["method"]},
                "then": {"properties": {"parameters": {"$ref": "#/$defs/" + model.__name__}}},
            }
        )
    schema["allOf"] = conditions
    return schema
