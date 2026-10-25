"""Original, configurable analysis prompts tied to observable task deviations."""

from __future__ import annotations

from importlib.resources import files
import json
from typing import Literal

from pydantic import Field

from .contracts import Contract, Name, Task


class DeviationRule(Contract):
    id: Name
    kinds: tuple[str, ...]
    question: Name
    effect_to_check: Name
    concern: Name


class Finding(Contract):
    id: Name
    task_id: Name
    step_id: Name
    rule_id: Name
    concern: Name
    question: Name
    effect_to_check: Name
    status: Literal["candidate", "excluded", "confirmed", "needs_information"] = "candidate"
    rationale: str = ""
    consequence: str = ""
    controls: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def default_rules() -> tuple[DeviationRule, ...]:
    text = files("human_reliability.data").joinpath("deviations.json").read_text(encoding="utf-8")
    return tuple(DeviationRule.model_validate_json(json.dumps(row)) for row in json.loads(text))


def analyze_task(
    task: Task, *, rules: tuple[DeviationRule, ...] | None = None, exclusions: dict[str, str] | None = None
) -> tuple[Finding, ...]:
    """Create review candidates, never invented causes, probabilities or conclusions."""
    chosen = default_rules() if rules is None else rules
    if len({rule.id for rule in chosen}) != len(chosen):
        raise ValueError("rule IDs must be unique")
    excluded, result = exclusions or {}, []
    for step in task.steps:
        for rule in chosen:
            if "*" not in rule.kinds and step.kind not in rule.kinds:
                continue
            if step.applicable_deviations is not None and rule.id not in step.applicable_deviations:
                continue
            key = f"{step.id}:{rule.id}"
            rationale = excluded.get(key, "")
            if key in excluded and not rationale.strip():
                raise ValueError("exclusion requires a rationale")
            result.append(
                Finding(
                    id=key,
                    task_id=task.id,
                    step_id=step.id,
                    rule_id=rule.id,
                    concern=rule.concern,
                    question=rule.question.format(target=step.target, cue=step.cue),
                    effect_to_check=rule.effect_to_check,
                    status="excluded" if key in excluded else "candidate",
                    rationale=rationale,
                )
            )
        for hazard in step.latent_hazards:
            result.append(
                Finding(
                    id=f"{step.id}:latent:{len(result)}",
                    task_id=task.id,
                    step_id=step.id,
                    rule_id="latent_condition",
                    concern="precondition",
                    question=(f"Before {step.action}, how is the absence of {hazard} established?"),
                    effect_to_check="Check the outcome of the intended action with this hidden condition present.",
                )
            )
    if set(excluded) - {finding.id for finding in result}:
        raise ValueError("exclusion references a finding outside the analysis")
    return tuple(result)


class ReviewItem(Contract):
    id: Name
    domain: Name
    requirement: Name
    answer: Literal["met", "not_met", "unknown", "not_applicable"]
    rationale: Name
    evidence_ids: tuple[Name, ...] = ()
    affected_steps: tuple[str, ...] = ()
    recommendation: str = ""

    @property
    def requires_action(self):
        return self.answer in {"not_met", "unknown"}


class Review(Contract):
    """Use for procedure quality, management, design, handover and collaboration."""

    id: Name
    items: tuple[ReviewItem, ...] = Field(min_length=1)

    def gaps(self):
        return tuple(item for item in self.items if item.requires_action)
