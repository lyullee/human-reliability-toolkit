"""Resource-constrained task episodes with declared failure and duration models."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math

import numpy as np

from .contracts import Task
from .probability import nonnegative, probability
from .timing import TimeModel


@dataclass(frozen=True)
class ActionOutcome:
    step_id: str
    actor: str
    target: str
    start_s: float
    completion_s: float
    failed_action: bool
    completed_before_deadline: bool


def simulate_task(
    task: Task,
    failure_models: Mapping[str, float | Callable],
    duration_models: Mapping[str, TimeModel],
    *,
    seed: int,
    resource_capacity: Mapping[str, int] | None = None,
    consequence_callback: Callable | None = None,
):
    """Simulate one episode; failed prerequisites remain in the conditional history.

    A callable receives the realized history and RNG, enabling shared context or
    preceding-failure dependencies. The caller owns action-to-physics semantics.
    Deadlines are measured from episode origin, not from each delayed task start.
    """
    ids = {step.id for step in task.steps}
    if set(failure_models) != ids or set(duration_models) != ids:
        raise ValueError("every task step requires a failure and duration model")
    capacities = dict(resource_capacity or {})
    actors = {step.actor for step in task.steps}
    if set(capacities) - actors or any(type(value) is not int or value < 1 for value in capacities.values()):
        raise ValueError("positive integer capacities for known actors required")
    availability = {actor: [0.0] * capacities.get(actor, 1) for actor in actors}
    history, pending, rng = {}, list(task.steps), np.random.default_rng(seed)
    while pending:
        candidates = []
        for index, step in enumerate(pending):
            if set(step.predecessors) <= set(history):
                dependency_time = max(
                    (history[parent].completion_s for parent in step.predecessors), default=0.0
                )
                resource_time = min(availability[step.actor])
                candidates.append((max(dependency_time, resource_time), index, step))
        if not candidates:
            raise ValueError("no executable task step")
        start, _, step = min(candidates, key=lambda item: item[:2])
        failure = failure_models[step.id]
        observed_history = {key: value for key, value in history.items() if value.completion_s <= start}
        q = probability(failure(observed_history, rng) if callable(failure) else failure)
        duration = float(duration_models[step.id].sample(1, rng)[0])
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("duration model returned an invalid completion time")
        finish = start + duration
        failed = bool(rng.random() < q)
        result = ActionOutcome(
            step.id,
            step.actor,
            step.target,
            start,
            finish,
            failed,
            not failed and (step.deadline_s is None or finish <= step.deadline_s),
        )
        history[step.id] = result
        slots = availability[step.actor]
        slot = slots.index(min(slots))
        slots[slot] = finish
        pending.remove(step)
    if consequence_callback is not None:
        by_id = {step.id: step for step in task.steps}
        replay = {}
        for outcome in sorted(history.values(), key=lambda value: value.completion_s):
            replay[outcome.step_id] = outcome
            consequence_callback(by_id[outcome.step_id], outcome, dict(replay))
    return tuple(history.values())


def simulate_response(
    *,
    alarm_time_s: float,
    recognition_s: float,
    diagnosis_s: float,
    action_s: float,
    actuator_s: float,
    horizon_s: float,
    wrong_action=False,
):
    """Construct an explicit alarm-to-physical-completion timeline for adapters."""
    fields = [alarm_time_s, recognition_s, diagnosis_s, action_s, actuator_s, horizon_s]
    for value in fields:
        nonnegative(value)
    if horizon_s <= 0:
        raise ValueError("positive observation horizon required")
    recognized = alarm_time_s + recognition_s
    diagnosed = recognized + diagnosis_s
    command = diagnosed + action_s
    complete = command + actuator_s
    return {
        "alarm_time_s": alarm_time_s,
        "recognition_time_s": recognized,
        "diagnosis_time_s": diagnosed,
        "command_time_s": command,
        "physical_completion_time_s": None if wrong_action else complete,
        "status": "wrong_action"
        if wrong_action
        else "completed"
        if complete <= horizon_s
        else "not_completed_within_horizon",
        "horizon_s": horizon_s,
    }
