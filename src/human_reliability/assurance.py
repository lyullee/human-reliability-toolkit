"""Procedure conformance and explicit assumption/configuration lifecycle review."""

from __future__ import annotations

import csv
from datetime import date
import json
from typing import Literal

from pydantic import model_validator

from .contracts import Contract, Evidence, Name, Nonnegative, Task, TaskStep, canonical_digest


class TraceStep(Contract):
    id: Name
    step_id: Name
    actor: Name
    target: Name
    start_s: Nonnegative
    completion_s: Nonnegative
    procedure_version: Name
    outcome: Literal["completed", "failed", "unknown"]
    evidence: Name

    @model_validator(mode="after")
    def interval(self):
        if self.completion_s < self.start_s:
            raise ValueError("trace completion precedes start")
        return self


def procedure_conformance(
    task: Task,
    trace: tuple[TraceStep, ...],
    *,
    complete_observation,
    allowed_retries=None,
    require_success_before=(),
):
    if type(complete_observation) is not bool or len({r.id for r in trace}) != len(trace):
        raise ValueError("unique trace identities and explicit observation-completeness flag required")
    by_id = {s.id: s for s in task.steps}
    retries = dict(allowed_retries or {})
    if (
        set(retries) - set(by_id)
        or set(require_success_before) - set(by_id)
        or any(type(v) is not int or v < 0 for v in retries.values())
    ):
        raise ValueError("known steps and nonnegative retry allowances required")
    findings, counts = [], {}
    for row in sorted(trace, key=lambda r: (r.start_s, r.completion_s, r.id)):
        if row.step_id not in by_id:
            findings.append({"trace_id": row.id, "kind": "unknown_step"})
            continue
        step = by_id[row.step_id]
        counts[row.step_id] = counts.get(row.step_id, 0) + 1
        if row.procedure_version != task.procedure_version:
            findings.append({"trace_id": row.id, "kind": "stale_procedure"})
        if row.actor != step.actor:
            findings.append({"trace_id": row.id, "kind": "unexpected_actor"})
        if row.target != step.target:
            findings.append({"trace_id": row.id, "kind": "wrong_target"})
        if counts[row.step_id] > 1 + retries.get(row.step_id, 0):
            findings.append({"trace_id": row.id, "kind": "unauthorized_repeat"})
        for predecessor in step.predecessors:
            prior = [r for r in trace if r.step_id == predecessor and r.completion_s <= row.start_s]
            if not prior:
                findings.append(
                    {"trace_id": row.id, "kind": "precedence_not_demonstrated", "predecessor": predecessor}
                )
            elif row.step_id in require_success_before and not any(r.outcome == "completed" for r in prior):
                findings.append(
                    {
                        "trace_id": row.id,
                        "kind": "successful_precondition_not_demonstrated",
                        "predecessor": predecessor,
                    }
                )
    for step in task.steps:
        observed = [r for r in trace if r.step_id == step.id]
        if not observed:
            findings.append(
                {
                    "step_id": step.id,
                    "kind": "omission" if complete_observation else "not_observed",
                    "restoration_step": step.kind == "restore",
                }
            )
        elif not any(r.outcome == "completed" for r in observed):
            findings.append(
                {
                    "step_id": step.id,
                    "kind": "completion_not_demonstrated",
                    "restoration_step": step.kind == "restore",
                }
            )
    return {
        "task_id": task.id,
        "procedure_version": task.procedure_version,
        "status": "conforming_observed_trace" if not findings and complete_observation else "review_required",
        "findings": findings,
        "observation_complete": complete_observation,
        "physical_safety_proven": False,
    }


def import_task_csv(
    path,
    *,
    task_id,
    title,
    procedure_version,
    evidence: tuple[Evidence, ...],
    columns=None,
    predecessor_separator=";",
    aliases=None,
):
    """Import reviewed structured rows; no automatic interpretation of natural-language SOPs."""
    fields = ("id", "action", "kind", "target", "actor", "cue", "completion", "predecessors")
    mapping = columns or {name: name for name in fields}
    if set(mapping) != set(fields) or not predecessor_separator:
        raise ValueError("explicit columns for all task fields and a separator required")
    aliases = aliases or {}
    steps = []
    with open(path, encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        if not set(mapping.values()) <= set(rows.fieldnames or ()):
            raise ValueError("CSV is missing configured task columns")
        for row in rows:
            if any(row[column] is None for column in mapping.values()):
                raise ValueError("CSV row has fewer cells than the configured schema")
            data = {key: row[column].strip() for key, column in mapping.items()}
            data["target"] = aliases.get(data["target"], data["target"])
            data["predecessors"] = tuple(
                p.strip() for p in data["predecessors"].split(predecessor_separator) if p.strip()
            )
            steps.append(TaskStep.model_validate(data))
    return Task(
        id=task_id, title=title, procedure_version=procedure_version, steps=tuple(steps), evidence=evidence
    )


class Assumption(Contract):
    id: Name
    statement: Name
    evidence: Name
    review_status: Literal["approved", "needs_review", "refuted"]
    expires_on: date | None = None


class ArtifactFingerprint(Contract):
    id: Name
    digest: Name
    dependencies: tuple[Name, ...] = ()

    @classmethod
    def of(cls, identity, value, *, dependencies=()):
        return cls(id=identity, digest=canonical_digest(value), dependencies=tuple(dependencies))


class IncidentLesson(Contract):
    id: Name
    statement: Name
    affected_ids: tuple[Name, ...]
    evidence: Name
    recommendation: str | None = None


class AssuranceLifecycle:
    def __init__(self, artifacts, assumptions, *, safety_case=None):
        if len({a.id for a in artifacts}) != len(artifacts) or len({a.id for a in assumptions}) != len(
            assumptions
        ):
            raise ValueError("artifact and assumption identities must be unique")
        self.artifacts, self.assumptions = {a.id: a for a in artifacts}, {a.id: a for a in assumptions}
        self.safety_case = safety_case
        if set(self.artifacts) & set(self.assumptions):
            raise ValueError("artifact and assumption identities overlap")
        known = set(self.artifacts) | set(self.assumptions)
        pending, done = dict(self.artifacts), set(self.assumptions)
        while pending:
            ready = {key for key, item in pending.items() if set(item.dependencies) <= done}
            if not ready:
                raise ValueError("artifact dependency graph has unknown references or cycles")
            done |= ready
            pending = {key: item for key, item in pending.items() if key not in ready}
        self.known = known

    def review(self, current_artifacts, *, as_of: date, current_assumptions=None, lessons=()):
        if type(as_of) is not date:
            raise ValueError("an explicit review date is required")
        if len({a.id for a in current_artifacts}) != len(current_artifacts):
            raise ValueError("duplicate current artifact")
        current = {a.id: a for a in current_artifacts}
        assumptions = (
            self.assumptions if current_assumptions is None else {a.id: a for a in current_assumptions}
        )
        if current_assumptions is not None and len(assumptions) != len(current_assumptions):
            raise ValueError("duplicate current assumption")
        changed, reasons = set(), {}
        for identity, artifact in self.artifacts.items():
            if identity not in current or current[identity] != artifact:
                changed.add(identity)
                reasons[identity] = "artifact changed or removed"
        new = (set(current) - set(self.artifacts)) | (set(assumptions) - set(self.assumptions))
        for identity, original in self.assumptions.items():
            assumption = assumptions.get(identity)
            if (
                assumption is None
                or assumption != original
                or assumption.review_status != "approved"
                or assumption.expires_on is not None
                and assumption.expires_on < as_of
            ):
                changed.add(identity)
                reasons[identity] = "assumption changed, unapproved, refuted or expired"
        for lesson in lessons:
            if not lesson.affected_ids or set(lesson.affected_ids) - self.known:
                raise ValueError("incident lesson needs known affected identities")
            for identity in lesson.affected_ids:
                changed.add(identity)
                reasons[identity] = "incident lesson: " + lesson.id
        affected = set(changed)
        while True:
            following = {key for key, item in self.artifacts.items() if set(item.dependencies) & affected}
            if following <= affected:
                break
            affected |= following
        claims = ()
        if self.safety_case:
            identities = set(self.safety_case.claims) | set(self.safety_case.evidence_versions)
            claims = self.safety_case.affected_by(affected & identities)
        refuted = any(a.review_status == "refuted" for a in assumptions.values())
        return {
            "status": "invalidated"
            if refuted
            else "review_required"
            if affected or new
            else "unchanged_qualified_scope",
            "as_of": as_of.isoformat(),
            "changed_ids": sorted(changed),
            "affected_artifacts": sorted(affected),
            "affected_claims": claims,
            "new_ids_require_scope_review": sorted(new),
            "reasons": reasons,
            "automatic_reapproval": False,
        }

    def baseline_json(self):
        return json.dumps(
            {
                "artifacts": [a.model_dump(mode="json") for a in self.artifacts.values()],
                "assumptions": [a.model_dump(mode="json") for a in self.assumptions.values()],
                "safety_case": None
                if self.safety_case is None
                else {
                    "claims": [
                        {"id": c.id, "statement": c.statement, "support_ids": c.support_ids}
                        for c in self.safety_case.claims.values()
                    ],
                    "evidence_versions": self.safety_case.evidence_versions,
                },
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text):
        from .safety_case import Claim, SafetyCase

        data = json.loads(text)
        if set(data) != {"artifacts", "assumptions", "safety_case"}:
            raise ValueError("unsupported assurance snapshot")
        artifacts = tuple(ArtifactFingerprint.model_validate_json(json.dumps(a)) for a in data["artifacts"])
        assumptions = tuple(Assumption.model_validate_json(json.dumps(a)) for a in data["assumptions"])
        case = data["safety_case"]
        safety = (
            None
            if case is None
            else SafetyCase(
                tuple(Claim(c["id"], c["statement"], tuple(c["support_ids"])) for c in case["claims"]),
                case["evidence_versions"],
            )
        )
        return cls(artifacts, assumptions, safety_case=safety)
