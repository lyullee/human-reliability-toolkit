"""Event-driven human/process feedback with observable policy inputs and bounded preemption."""

from __future__ import annotations

from copy import deepcopy
from typing import Literal, Protocol

import numpy as np
from pydantic import Field, model_validator

from .actions import (
    Command,
    EquipmentCapability,
    ExecutableAction,
    ProcessState,
    StatePredicate,
    StateValue,
    execute_action,
)
from .contracts import Contract, Evidence, Name, Nonnegative, Probability, Task, canonical_digest
from .probability import nonnegative


class ProcessBackend(Protocol):
    def advance_to(self, time_s: float) -> None: ...
    def observe(self, actor: str, time_s: float) -> ProcessState: ...
    def snapshot(self) -> ProcessState: ...
    def apply(self, execution, time_s: float) -> None: ...


class ProcessObservation(ProcessState):
    observed_at_s: Nonnegative


class StateProcess:
    """Adapters can supply continuous physics; the default only applies atomic commands."""

    def __init__(self, initial: ProcessState, *, advance=None, visibility=None):
        self._state = initial.model_copy(deep=True)
        self.time_s, self._advance = 0.0, advance
        self.visibility = {key: set(value) for key, value in (visibility or {}).items()}

    def advance_to(self, time_s):
        t = nonnegative(time_s)
        if t < self.time_s:
            raise ValueError("process clock cannot move backwards")
        if t > self.time_s and self._advance:
            after = self._advance(self._state.model_copy(deep=True), t - self.time_s, t)
            if not isinstance(after, ProcessState):
                raise ValueError("process advance must return ProcessState")
            self._state = after.model_copy(deep=True)
        self.time_s = t

    def snapshot(self):
        return self._state.model_copy(deep=True)

    def observe(self, actor, time_s):
        if time_s != self.time_s:
            raise ValueError("observations require a synchronized process clock")
        state = self.snapshot()
        allowed = self.visibility.get(actor, set())
        state = ProcessState(
            revision="observation:" + str(time_s),
            values={k: v for k, v in state.values.items() if k in allowed},
        )
        return ProcessObservation(revision=state.revision, values=state.values, observed_at_s=time_s)

    def apply(self, execution, time_s):
        if time_s != self.time_s or canonical_digest(execution.state_before) != canonical_digest(self._state):
            raise ValueError("command was evaluated against a stale physical snapshot")
        self._state = execution.state_after.model_copy(deep=True)


class RuntimeJob(Contract):
    id: Name
    action_id: Name
    candidate_actors: tuple[Name, ...] = Field(min_length=1)
    predecessors: tuple[Name, ...] = ()
    requires_success: bool = False
    release_s: Nonnegative = 0.0
    duration_s: Nonnegative
    priority: int = 0
    preempt: bool = True
    reconsider_on_resume: bool = False
    deadline_s: Nonnegative | None = None
    maximum_attempts: int = Field(default=1, ge=1, le=100)
    retry_mode: Literal["none", "repeat", "policy"] = "none"
    retry_delay_s: Nonnegative = 0.0
    error_probability: Probability = 0.0
    error_evidence: Name | None = None
    error_command: Command | None = None

    @model_validator(mode="after")
    def identities(self):
        if len(set(self.candidate_actors)) != len(self.candidate_actors) or len(
            set(self.predecessors)
        ) != len(self.predecessors):
            raise ValueError("actors and predecessors must not repeat")
        if self.maximum_attempts > 1 and self.retry_mode == "none":
            raise ValueError("multiple attempts require an explicit repeat or observed-policy rule")
        if self.error_probability > 0 and self.error_evidence is None:
            raise ValueError("nonzero injected error probability needs evidence")
        return self


class PolicyTask(Contract):
    id: Name
    action_id: Name
    candidate_actors: tuple[Name, ...]
    predecessors: tuple[Name, ...]
    release_s: Nonnegative
    duration_s: Nonnegative
    priority: int
    deadline_s: Nonnegative | None

    @classmethod
    def of(cls, job):
        return cls(**{name: getattr(job, name) for name in cls.model_fields})


class TaskExecutionPlan(Contract):
    task_id: Name
    procedure_version: Name
    actions: tuple[ExecutableAction, ...]
    jobs: tuple[RuntimeJob, ...]
    evidence: tuple[Evidence, ...]


def bind_task_execution(
    task: Task, actions_by_step, durations_s, *, safety_bindings=None, job_parameters=None
):
    """Bind native task IDs/order and resolve every textual precondition/latent-safety requirement.

    A binding predicate is true when the required safe condition holds. Named latent
    hazards therefore need an explicit safe-state predicate, not a guessed inversion.
    """
    ids = {step.id for step in task.steps}
    if set(actions_by_step) != ids or set(durations_s) != ids or set(job_parameters or {}) - ids:
        raise ValueError("one action and duration per native step required")
    bindings, parameters = safety_bindings or {}, job_parameters or {}
    actions, jobs = [], []
    for step in task.steps:
        action = actions_by_step[step.id]
        if not isinstance(action, ExecutableAction) or action.command.target != step.target:
            raise ValueError("nominal action must match the native task target")
        names = (*step.preconditions, *step.latent_hazards)
        if set(names) - set(bindings) or any(not isinstance(bindings[key], StatePredicate) for key in names):
            raise ValueError("every named task condition needs an explicit safe-state predicate binding")
        bound = action.model_copy(
            update={"safety_conditions": action.safety_conditions + tuple(bindings[key] for key in names)}
        )
        options = parameters.get(step.id, {})
        if set(options) & {"id", "action_id", "predecessors", "duration_s"}:
            raise ValueError("job options cannot replace native identity/order or the duration mapping")
        job = RuntimeJob(
            **(
                {
                    "id": step.id,
                    "action_id": action.id,
                    "candidate_actors": (step.actor,),
                    "predecessors": step.predecessors,
                    "deadline_s": step.deadline_s,
                    "duration_s": durations_s[step.id],
                }
                | options
            )
        )
        actions.append(bound)
        jobs.append(job)
    if len({action.id for action in actions}) != len(actions):
        raise ValueError("bound native steps require distinct executable action identities")
    return TaskExecutionPlan(
        task_id=task.id,
        procedure_version=task.procedure_version,
        actions=tuple(actions),
        jobs=tuple(jobs),
        evidence=task.evidence,
    )


class StateRate(Contract):
    rate: float
    unit: Name


class CoupledCase(Contract):
    """Portable authored linear/held-state model; real physics uses ProcessBackend."""

    schema_version: str = "1"
    initial: ProcessState
    actions: tuple[ExecutableAction, ...]
    capabilities: tuple[EquipmentCapability, ...]
    jobs: tuple[RuntimeJob, ...]
    horizon_s: Nonnegative
    seed: int
    visibility: dict[str, tuple[Name, ...]]
    resource_capacity: dict[str, int] = {}
    rates: dict[str, StateRate] = {}
    maximum_events: int = Field(default=100_000, ge=1)

    @model_validator(mode="after")
    def model(self):
        if self.schema_version != "1":
            raise ValueError("unsupported coupled-case schema")
        if any(job.retry_mode == "policy" for job in self.jobs):
            raise ValueError("observed retry callbacks use the Python API, not the fixed JSON runner")
        for key, rate in self.rates.items():
            fact = self.initial.values.get(key)
            if fact is None or type(fact.value) is not float or rate.unit != fact.unit + "/s":
                raise ValueError("linear rate needs known numeric state and matching unit/second")
        return self


def run_coupled_case(case: CoupledCase):
    def advance(state, duration, time_s):
        values = dict(state.values)
        for key, rate in case.rates.items():
            fact = values[key]
            if type(fact.value) is not float:
                raise ValueError("a linear-state channel became nonnumeric")
            values[key] = StateValue(value=fact.value + rate.rate * duration, unit=fact.unit)
        return ProcessState(revision="physics:" + str(time_s), values=values)

    process = StateProcess(case.initial, advance=advance, visibility=case.visibility)
    result = run_coupled_episode(
        case.jobs,
        case.actions,
        case.capabilities,
        process,
        horizon_s=case.horizon_s,
        seed=case.seed,
        resource_capacity=case.resource_capacity,
        maximum_events=case.maximum_events,
    )
    result["input_digest"] = canonical_digest(case)
    result["physical_model"] = "declared linear rates and atomic commands; no plant qualification"
    return result


def run_coupled_episode(
    jobs: tuple[RuntimeJob, ...],
    actions: tuple[ExecutableAction, ...],
    capabilities,
    process: ProcessBackend,
    *,
    horizon_s,
    seed,
    resource_capacity=None,
    policy=None,
    actor_selector=None,
    duration_provider=None,
    retry_decider=None,
    maximum_events=100_000,
):
    """Commands apply at physical completion; interruption preserves remaining work.

    Policies receive role-filtered observations and that role's command history,
    never the analyst's hidden states or failure labels. Retrying is explicitly bounded.
    """
    import simpy

    horizon = nonnegative(horizon_s)
    if horizon <= 0 or type(maximum_events) is not int or maximum_events < 1:
        raise ValueError("positive horizon and event budget required")
    ids, action_map = {j.id for j in jobs}, {a.id: a for a in actions}
    if not jobs or len(ids) != len(jobs) or len(action_map) != len(actions):
        raise ValueError("nonempty unique jobs and action identities required")
    remaining = {j.id: set(j.predecessors) for j in jobs}
    seen = set()
    while remaining:
        ready = {key for key, parents in remaining.items() if parents <= seen}
        if not ready:
            raise ValueError("runtime predecessors contain a cycle or unknown job")
        seen |= ready
        remaining = {key: parents for key, parents in remaining.items() if key not in ready}
    if any(j.action_id not in action_map for j in jobs):
        raise ValueError("job references an unknown executable action")
    if any(j.retry_mode == "policy" for j in jobs) and retry_decider is None:
        raise ValueError("observed-policy retry mode requires a callback")
    actors = {actor for job in jobs for actor in job.candidate_actors}
    capacities = dict(resource_capacity or {})
    if set(capacities) - actors or any(type(v) is not int or v < 1 for v in capacities.values()):
        raise ValueError("positive capacities for known actors required")
    env, rng = simpy.Environment(), np.random.default_rng(seed)
    resources = {
        actor: simpy.PreemptiveResource(env, capacity=capacities.get(actor, 1)) for actor in sorted(actors)
    }
    finished = {key: env.event() for key in sorted(ids)}
    audit, records, command_history, outcome_by_job = [], [], [], {}

    def log(kind, job, **details):
        if len(audit) >= maximum_events:
            raise ValueError("coupled simulation event budget exhausted")
        audit.append({"time_s": float(env.now), "kind": kind, "job_id": job.id, **details})

    def synchronize():
        process.advance_to(float(env.now))

    def perform(job):
        public_job = PolicyTask.of(job)
        if job.release_s:
            yield env.timeout(job.release_s)
        if job.predecessors:
            yield env.all_of([finished[key] for key in job.predecessors])
        if job.requires_success and any(not outcome_by_job[key]["success"] for key in job.predecessors):
            outcome_by_job[job.id] = {"job_id": job.id, "status": "prerequisite_not_met", "success": False}
            log("prerequisite_not_met", job)
            finished[job.id].succeed()
            return
        for attempt in range(1, job.maximum_attempts + 1):
            synchronize()
            if actor_selector:
                visible = {}
                for candidate in job.candidate_actors:
                    observed = process.observe(candidate, float(env.now))
                    visible[candidate] = ProcessObservation(
                        revision=observed.revision,
                        values=deepcopy(observed.values),
                        observed_at_s=float(env.now),
                    )
                actor = actor_selector(
                    public_job,
                    visible,
                    {a: resources[a].count + len(resources[a].queue) for a in job.candidate_actors},
                )
                if actor not in job.candidate_actors:
                    raise ValueError("selector returned an ineligible actor")
            else:
                actor = min(
                    job.candidate_actors,
                    key=lambda a: (
                        resources[a].count + len(resources[a].queue),
                        job.candidate_actors.index(a),
                    ),
                )
            resource = resources[actor]
            duration, command, perceived_command, decided, first_start = None, None, None, False, None
            while duration is None or duration > 1e-12:
                request, begin = resource.request(priority=job.priority, preempt=job.preempt), None
                try:
                    yield request
                    synchronize()
                    begin = float(env.now)
                    first_start = begin if first_start is None else first_start
                    observed = process.observe(actor, begin)
                    observation = ProcessObservation(
                        revision=observed.revision, values=deepcopy(observed.values), observed_at_s=begin
                    )
                    visible_history = tuple(deepcopy(r) for r in command_history if r["actor"] == actor)
                    if duration is None:
                        duration = nonnegative(
                            duration_provider(public_job, observation, rng)
                            if duration_provider
                            else job.duration_s
                        )
                    if not decided or job.reconsider_on_resume:
                        command = (
                            policy(public_job, observation, visible_history, rng)
                            if policy
                            else action_map[job.action_id].command
                        )
                        if command is not None and not isinstance(command, Command):
                            raise ValueError("policy must return Command or None for omission")
                        perceived_command = command
                        if rng.random() < job.error_probability:
                            command = job.error_command
                        decided = True
                        log(
                            "decision",
                            job,
                            actor=actor,
                            attempt=attempt,
                            observed_keys=sorted(observation.values),
                            omitted=command is None,
                        )
                    log("started_or_resumed", job, actor=actor, attempt=attempt, remaining_s=duration)
                    yield env.timeout(duration)
                    synchronize()
                    duration = 0.0
                except simpy.Interrupt:
                    if begin is None:
                        raise ValueError("unexpected interruption before resource acquisition")
                    duration = max(0.0, duration - (float(env.now) - begin))
                    synchronize()
                    log("interrupted", job, actor=actor, attempt=attempt, remaining_s=duration)
                finally:
                    if request in resource.users:
                        resource.release(request)
                    elif not request.triggered:
                        request.cancel()
            action = action_map[job.action_id]
            execution = execute_action(
                process.snapshot(), action, tuple(capabilities), realized=command, omitted=command is None
            )
            process.apply(execution, float(env.now))
            erroneous = command is None or canonical_digest(command) != canonical_digest(action.command)
            late = job.deadline_s is not None and env.now > job.deadline_s
            success = execution.status == "executed" and not erroneous and not late
            record = {
                "job_id": job.id,
                "actor": actor,
                "attempt": attempt,
                "start_s": first_start,
                "completion_s": float(env.now),
                "success": success,
                "late": late,
                "execution": execution.model_dump(mode="json"),
            }
            records.append(record)
            command_history.append(
                {
                    "job_id": job.id,
                    "actor": actor,
                    "completion_s": float(env.now),
                    "command": None
                    if perceived_command is None
                    else perceived_command.model_dump(mode="json"),
                }
            )
            log("completed_attempt", job, actor=actor, attempt=attempt, success=success)
            outcome_by_job[job.id] = record
            if attempt == job.maximum_attempts or job.retry_mode == "none":
                break
            if job.retry_mode == "policy":
                observed = process.observe(actor, float(env.now))
                view = ProcessObservation(
                    revision=observed.revision, values=deepcopy(observed.values), observed_at_s=float(env.now)
                )
                own_history = tuple(deepcopy(r) for r in command_history if r["actor"] == actor)
                again = retry_decider(public_job, view, own_history, attempt, rng)
                if type(again) is not bool:
                    raise ValueError("retry policy must return an explicit boolean")
                if not again:
                    break
            yield env.timeout(job.retry_delay_s)
        finished[job.id].succeed()

    for job in jobs:
        env.process(perform(job))
    steps = 0
    while env.peek() <= horizon:
        steps += 1
        if steps > maximum_events:
            raise ValueError("coupled scheduler event budget exhausted")
        env.step()
    process.advance_to(horizon)
    unfinished = sorted(key for key, event in finished.items() if not event.triggered)
    return {
        "status": "completed" if not unfinished else "incomplete_horizon",
        "records": records,
        "unfinished_jobs": unfinished,
        "audit": audit,
        "seed": seed,
        "horizon_s": horizon,
        "final_state": process.snapshot().model_dump(mode="json"),
        "atomic_commands_at_completion": True,
        "field_validation_claim": False,
    }
