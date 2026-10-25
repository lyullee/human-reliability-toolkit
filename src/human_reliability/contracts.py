"""Strict, portable records shared by analysis methods and integration adapters."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0, le=1)]
Nonnegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
Name = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]


class Contract(BaseModel):
    """Reject unknown fields, nonfinite numbers and coercion of strings to numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


def canonical_digest(value: Any) -> str:
    """Hash JSON meaning rather than indentation or dictionary insertion order."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return sha256(data.encode("utf-8")).hexdigest()


class Evidence(Contract):
    id: Name
    reference: Name
    origin: Literal["observed", "simulation", "literature", "elicited", "assumed"]
    applicability: Name
    version: Name = "1"
    locator: str = ""
    limitations: tuple[str, ...] = ()


class ContextValue(Contract):
    value: float | str | bool | None
    evidence_id: Name
    unit: str = "1"


class Context(Contract):
    id: Name
    operating_mode: Name
    factors: dict[str, ContextValue] = Field(default_factory=dict)
    team_id: str | None = None
    scenario_id: str | None = None


class TaskStep(Contract):
    id: Name
    action: Name
    kind: Literal["observe", "identify", "decide", "communicate", "manipulate", "verify", "restore"]
    target: Name
    actor: Name
    cue: Name
    completion: Name
    predecessors: tuple[Name, ...] = ()
    preconditions: tuple[Name, ...] = ()
    latent_hazards: tuple[Name, ...] = ()
    deadline_s: Positive | None = None
    applicable_deviations: tuple[str, ...] | None = None
    context_tags: tuple[str, ...] = ()
    processing_mode: Literal["skill", "rule", "knowledge", "mixed"] = "mixed"


class Task(Contract):
    id: Name
    title: Name
    procedure_version: Name
    steps: tuple[TaskStep, ...]
    evidence: tuple[Evidence, ...]

    @model_validator(mode="after")
    def check_graph(self):
        ids = [step.id for step in self.steps]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("task requires nonempty unique step IDs")
        if not self.evidence or len({e.id for e in self.evidence}) != len(self.evidence):
            raise ValueError("task requires unique provenance records")
        pending = {step.id: set(step.predecessors) for step in self.steps}
        if any(parents - set(ids) for parents in pending.values()):
            raise ValueError("step predecessor is outside task")
        done = set()
        while pending:
            ready = {key for key, parents in pending.items() if parents <= done}
            if not ready:
                raise ValueError("task dependency graph contains a cycle")
            done.update(ready)
            pending = {key: parents for key, parents in pending.items() if key not in ready}
        return self

    def ordered_steps(self) -> tuple[TaskStep, ...]:
        pending, done, result = list(self.steps), set(), []
        while pending:
            step = next(step for step in pending if set(step.predecessors) <= done)
            result.append(step)
            done.add(step.id)
            pending.remove(step)
        return tuple(result)


class HumanFailureEvent(Contract):
    id: Name
    task_id: Name
    step_ids: tuple[Name, ...]
    role: Literal["initiating", "latent", "response"]
    failure_definition: Name
    opportunity_definition: Name
    conditioning: Name
    deadline_s: Positive | None = None
    includes_recovery: bool = False
    includes_timing: bool = False
    dependency_group: str | None = None


class Estimate(Contract):
    """A probability belongs to a defined event and conditioning, never a person."""

    event_id: Name
    method: Name
    probability: Probability
    conditioning: Name
    evidence_ids: tuple[Name, ...]
    uncertainty: dict[str, float | str] = Field(default_factory=dict)
    includes: tuple[Literal["recovery", "timing", "dependency"], ...] = ()
    status: Literal["assumed", "empirical", "method_estimate", "research"]
    trace: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def evidence_required(self):
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("nonempty unique evidence IDs required")
        return self


class MethodInput(Contract):
    event: HumanFailureEvent
    context: Context
    evidence: tuple[Evidence, ...]
    parameters: dict[str, Any] = Field(default_factory=dict)


class SignalSeries(Contract):
    time_s: tuple[float, ...]
    values: tuple[float | None, ...]
    valid: tuple[bool, ...]
    clock_id: Name
    unit: Name
    origin: Name

    @model_validator(mode="after")
    def consistent(self):
        if not self.time_s or not len(self.time_s) == len(self.values) == len(self.valid):
            raise ValueError("matched nonempty signal arrays required")
        if any(b <= a for a, b in zip(self.time_s, self.time_s[1:])):
            raise ValueError("signal clock must strictly increase")
        if any(t < 0 for t in self.time_s):
            raise ValueError("elapsed times must be nonnegative")
        if any(ok and value is None for ok, value in zip(self.valid, self.values)):
            raise ValueError("missing signal cannot be valid")
        return self
