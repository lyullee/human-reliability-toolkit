"""Executable, unit-checked commands and explicitly bounded task mutations."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .contracts import Contract, Name, Nonnegative, Task

Scalar = float | str | bool


class StateValue(Contract):
    value: Scalar | None
    unit: Name = "1"


class ProcessState(Contract):
    revision: Name
    values: dict[str, StateValue]


class StatePredicate(Contract):
    key: Name
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"] = "eq"
    value: Scalar
    unit: Name = "1"

    def evaluate(self, state: ProcessState) -> bool | None:
        fact = state.values.get(self.key)
        if fact is None or fact.value is None:
            return None
        if fact.unit != self.unit:
            raise ValueError("predicate unit mismatch: " + self.key)
        if type(fact.value) is not type(self.value):
            raise ValueError("predicate scalar types differ: " + self.key)
        a, b = fact.value, self.value
        if self.operator in {"lt", "le", "gt", "ge"} and type(a) is not float:
            raise ValueError("ordered comparisons require numeric state")
        return {
            "eq": lambda: a == b,
            "ne": lambda: a != b,
            "lt": lambda: a < b,
            "le": lambda: a <= b,
            "gt": lambda: a > b,
            "ge": lambda: a >= b,
        }[self.operator]()


class Command(Contract):
    target: Name
    verb: Name
    value: Scalar
    unit: Name = "1"


class EquipmentCapability(Contract):
    target: Name
    verb: Name
    state_key: Name
    unit: Name = "1"
    operation: Literal["set", "add"] = "set"
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Scalar, ...] = ()

    @model_validator(mode="after")
    def bounds(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("capability bounds reversed")
        return self

    def validate_command(self, command: Command):
        if (command.target, command.verb, command.unit) != (self.target, self.verb, self.unit):
            raise ValueError("command is outside the selected equipment capability")
        if self.allowed_values and not any(
            type(command.value) is type(v) and command.value == v for v in self.allowed_values
        ):
            raise ValueError("command value is not supported by the equipment")
        if self.minimum is not None or self.maximum is not None or self.operation == "add":
            if type(command.value) is not float:
                raise ValueError("numeric capability requires a numeric command")
            if self.operation == "set" and (
                (self.minimum is not None and command.value < self.minimum)
                or (self.maximum is not None and command.value > self.maximum)
            ):
                raise ValueError("command exceeds physical capability")


class Permissive(Contract):
    id: Name
    condition: StatePredicate
    enabled: bool = True
    evidence: Name


class ExecutableAction(Contract):
    id: Name
    command: Command
    safety_conditions: tuple[StatePredicate, ...] = ()
    permissives: tuple[Permissive, ...] = ()
    unknown_policy: Literal["withhold", "attempt"] = "withhold"
    evidence: Name


class ActionExecution(Contract):
    action_id: Name
    intended: Command
    realized: Command | None
    status: Literal["executed", "unsafe_attempt", "blocked", "unknown_withheld", "omitted"]
    state_before: ProcessState
    state_after: ProcessState
    condition_results: tuple[bool | None, ...]
    interlock_results: dict[str, bool | None]
    evidence: Name


def execute_action(
    state: ProcessState,
    action: ExecutableAction,
    capabilities: tuple[EquipmentCapability, ...],
    *,
    realized: Command | None = None,
    omitted=False,
) -> ActionExecution:
    """Safety conditions describe risk; enabled permissives actually prevent execution.

    A command is an atomic state update, not a model of fluid/thermal dynamics.
    Unknown enabled permissives block even when an analyst permits an unknown-risk attempt.
    """
    if type(omitted) is not bool:
        raise ValueError("omitted must be boolean")
    keys = [(c.target, c.verb) for c in capabilities]
    if len(keys) != len(set(keys)):
        raise ValueError("equipment capabilities must be unique")
    if len({p.id for p in action.permissives}) != len(action.permissives):
        raise ValueError("permissive IDs must be unique")
    command = realized or action.command
    matches = [c for c in capabilities if (c.target, c.verb) == (command.target, command.verb)]
    if len(matches) != 1:
        raise ValueError("realized target and verb require a declared capability")
    capability = matches[0]
    capability.validate_command(command)
    conditions = tuple(p.evaluate(state) for p in action.safety_conditions)
    locks = {p.id: p.condition.evaluate(state) for p in action.permissives if p.enabled}
    status = (
        "omitted"
        if omitted
        else "blocked"
        if any(v is not True for v in locks.values())
        else "unknown_withheld"
        if None in conditions and action.unknown_policy == "withhold"
        else "unsafe_attempt"
        if any(v is not True for v in conditions)
        else "executed"
    )
    after = state.model_copy(deep=True)
    if status in {"executed", "unsafe_attempt"}:
        previous = state.values.get(capability.state_key)
        if previous is not None and previous.unit != command.unit:
            raise ValueError("state and command units differ")
        value = command.value
        if previous is not None and previous.value is not None and type(previous.value) is not type(value):
            raise ValueError("command and state scalar types differ")
        if capability.operation == "add":
            if previous is None or type(previous.value) is not float:
                raise ValueError("add requires a known numeric initial value")
            value = previous.value + command.value
            if (capability.minimum is not None and value < capability.minimum) or (
                capability.maximum is not None and value > capability.maximum
            ):
                raise ValueError("result exceeds physical capability")
        after = ProcessState(
            revision=state.revision + ":" + action.id,
            values=state.values | {capability.state_key: StateValue(value=value, unit=command.unit)},
        )
    return ActionExecution(
        action_id=action.id,
        intended=action.command,
        realized=None if status == "omitted" else command,
        status=status,
        state_before=state.model_copy(deep=True),
        state_after=after,
        condition_results=conditions,
        interlock_results=locks,
        evidence=action.evidence,
    )


class ActionVariant(Contract):
    id: Name
    action_id: Name
    kind: Literal["nominal", "omission", "substitution", "magnitude", "timing", "repetition"]
    commands: tuple[Command, ...]
    delay_s: Nonnegative = 0.0


def error_variants(
    action: ExecutableAction,
    capabilities: tuple[EquipmentCapability, ...],
    *,
    alternative_targets=(),
    magnitudes=(),
    delays_s=(),
    repetitions=(),
    maximum_variants=100,
):
    """Generate only requested, physically supported variants; attach no invented HEP."""
    if type(maximum_variants) is not int or maximum_variants < 2:
        raise ValueError("variant budget must be an integer >= 2")
    candidates = [("nominal", (action.command,), 0.0), ("omission", (), 0.0)]
    candidates += [
        ("substitution", (action.command.model_copy(update={"target": target}),), 0.0)
        for target in alternative_targets
    ]
    candidates += [
        ("magnitude", (action.command.model_copy(update={"value": value}),), 0.0) for value in magnitudes
    ]
    candidates += [("timing", (action.command,), delay) for delay in delays_s]
    for count in repetitions:
        if type(count) is not int or count < 2:
            raise ValueError("repetitions require an integer >= 2")
        if count > maximum_variants:
            raise ValueError("repetition expansion exceeds budget")
        candidates.append(("repetition", (action.command,) * count, 0.0))
    if len(candidates) > maximum_variants:
        raise ValueError("variant expansion exceeds budget")
    result = []
    for index, (kind, commands, delay) in enumerate(candidates):
        commands = tuple(Command.model_validate(c.model_dump()) for c in commands)
        for command in commands:
            matches = [c for c in capabilities if (c.target, c.verb) == (command.target, command.verb)]
            if len(matches) != 1:
                raise ValueError("variant requires an unambiguous equipment capability")
            matches[0].validate_command(command)
        result.append(
            ActionVariant(
                id=f"{action.id}:{index}", action_id=action.id, kind=kind, commands=commands, delay_s=delay
            )
        )
    return tuple(result)


def reordered_plan(task: Task, order: tuple[str, ...], *, review: str):
    """Keep a reviewed erroneous order separate from the nominal task DAG."""
    if not review.strip() or len(order) != len(task.steps) or set(order) != {s.id for s in task.steps}:
        raise ValueError("a reviewed permutation of all step IDs is required")
    positions = {key: i for i, key in enumerate(order)}
    violations = tuple(
        (parent, step.id)
        for step in task.steps
        for parent in step.predecessors
        if positions[parent] > positions[step.id]
    )
    return {"step_order": order, "precedence_violations": violations, "review": review}
