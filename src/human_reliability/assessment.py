"""Configurable assessment orchestration with a public method extension point."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .contracts import (
    Contract,
    Context,
    Estimate,
    HumanFailureEvent,
    MethodInput,
    Name,
    Task,
    canonical_digest,
)
from .methods import (
    MethodRegistry,
    cognitive_chain,
    declared_estimator,
    heart_probability,
    spar_h_probability,
)
from .probability import BetaPrior
from .qualitative import analyze_task, DeviationRule


class ModelSpec(Contract):
    method: Name
    parameters: dict[str, Any]
    evidence_ids: tuple[Name, ...]


class AssessmentCase(Contract):
    schema_version: str = "1"
    task: Task
    context: Context
    events: tuple[HumanFailureEvent, ...]
    models: dict[str, ModelSpec]
    exclusions: dict[str, str] = Field(default_factory=dict)
    deviation_rules: tuple[DeviationRule, ...] | None = None

    @model_validator(mode="after")
    def validate_bindings(self):
        if self.schema_version != "1":
            raise ValueError("unsupported case schema version")
        if not self.events or len({event.id for event in self.events}) != len(self.events):
            raise ValueError("nonempty unique event IDs required")
        if {event.id for event in self.events} != set(self.models):
            raise ValueError("each failure event requires exactly one model specification")
        ids = {step.id for step in self.task.steps}
        evidence = {record.id for record in self.task.evidence}
        if any(
            event.task_id != self.task.id or not event.step_ids or set(event.step_ids) - ids
            for event in self.events
        ):
            raise ValueError("failure event is not bound to this task's steps")
        if any(not spec.evidence_ids or set(spec.evidence_ids) - evidence for spec in self.models.values()):
            raise ValueError("every method must cite available evidence")
        if any(value.evidence_id not in evidence for value in self.context.factors.values()):
            raise ValueError("context references unavailable evidence")
        return self


class AssessmentEngine:
    """Application methods receive the same typed event/context/evidence request."""

    def __init__(self, *, evidence_catalog=None):
        self.registry = MethodRegistry()
        self._evidence_catalog = evidence_catalog

    def register(self, name, method, *, replace=False):
        self.registry.register(name, method, replace=replace)

    def assess(self, case: AssessmentCase):
        estimates = []
        for event in case.events:
            spec = case.models[event.id]
            request = MethodInput(
                event=event, context=case.context, evidence=case.task.evidence, parameters=spec.parameters
            )
            if spec.method in self.registry.names:
                result = self.registry.evaluate(spec.method, request)
            else:
                result = self._builtin(request, spec)
                # Builtins obey the same event/evidence/scope checks as plugins.
                guard = MethodRegistry()
                guard.register("builtin", lambda _: result)
                guard.evaluate("builtin", request)
            estimates.append(result)
        findings = analyze_task(case.task, rules=case.deviation_rules, exclusions=case.exclusions)
        return {
            "schema": "human_reliability.assessment.v1",
            "input_digest": canonical_digest(case),
            "task_id": case.task.id,
            "context_id": case.context.id,
            "estimates": [value.model_dump(mode="json") for value in estimates],
            "findings": [value.model_dump(mode="json") for value in findings],
            "empirical_plant_validation_claim": False,
        }

    def _builtin(self, request, spec):
        p = spec.parameters
        if spec.method == "evidence_catalog":
            from .evidence_catalog import ApplicabilityReview, builtin_evidence_catalog
            import json

            if set(p) - {"record_id", "review", "prior", "selected_value"}:
                raise ValueError("unknown evidence-catalog parameter")
            prior = (
                BetaPrior.model_validate_json(json.dumps(p["prior"])) if p.get("prior") is not None else None
            )
            if self._evidence_catalog is None:
                self._evidence_catalog = builtin_evidence_catalog()
            binding = self._evidence_catalog.bind(
                p["record_id"],
                request.event,
                review=ApplicabilityReview.model_validate_json(json.dumps(p["review"])),
                prior=prior,
                selected_value=p.get("selected_value"),
            )
            if set(spec.evidence_ids) != set(binding.estimate.evidence_ids):
                raise ValueError("model specification must cite the exact catalog/prior evidence identities")
            return binding.estimate
        if spec.method == "declared":
            if set(p) - {"probability", "includes"}:
                raise ValueError("unknown declared method parameter")
            return declared_estimator(p["probability"], spec.evidence_ids[0], includes=p.get("includes", ()))(
                request
            )
        if spec.method == "empirical":
            if set(p) != {"alpha", "beta", "failures", "opportunities"} or len(spec.evidence_ids) != 2:
                raise ValueError(
                    "empirical model requires four named parameters and prior/observation evidence"
                )
            prior = BetaPrior(alpha=p["alpha"], beta=p["beta"], evidence_id=spec.evidence_ids[0])
            return prior.posterior(
                p["failures"],
                p["opportunities"],
                event_id=request.event.id,
                observation_id=spec.evidence_ids[1],
                conditioning=request.event.conditioning,
            )
        if spec.method == "cognitive_chain":
            if set(p) != {"conditional_failures"}:
                raise ValueError("cognitive chain requires conditional_failures")
            return cognitive_chain(
                request.event.id,
                p["conditional_failures"],
                conditioning=request.event.conditioning,
                evidence_ids=spec.evidence_ids,
            )
        if spec.method == "spar_h":
            if set(p) - {"stage", "factors", "insufficient_time", "nominal"}:
                raise ValueError("unknown SPAR-H parameter")
            value, trace = spar_h_probability(**p)
        elif spec.method == "heart":
            if set(p) != {"nominal", "effects"}:
                raise ValueError("HEART arithmetic requires nominal and effects")
            value, trace = heart_probability(p["nominal"], tuple(map(tuple, p["effects"])))
        else:
            raise ValueError(f"unsupported method: {spec.method}; register a plugin")
        return Estimate(
            event_id=request.event.id,
            method=spec.method,
            probability=value,
            conditioning=request.event.conditioning,
            evidence_ids=spec.evidence_ids,
            status="method_estimate",
            trace=trace,
        )
