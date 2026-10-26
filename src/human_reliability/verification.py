"""Finite progress and deadline properties supplement the existing untimed safety checks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .workflow import Transition, WorkflowNet


def _cycle(edges):
    """Iterative DFS avoids a recursion limit on a valid large finite graph."""
    color = {}
    for start in edges:
        if color.get(start):
            continue
        color[start] = 1
        stack, active = [(start, iter(edges[start]))], [start]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                color[node] = 2
                stack.pop()
                active.pop()
            elif color.get(child) == 1:
                return tuple(active[active.index(child) :] + [child])
            elif not color.get(child):
                color[child] = 1
                stack.append((child, iter(edges[child])))
                active.append(child)
    return ()


def verify_progress(
    net: WorkflowNet, initial, *, goal, unsafe=None, require_all_paths=True, maximum_states=10_000
):
    """Goals stop an episode. All-path progress rejects reachable cycles without assuming fairness."""
    if type(maximum_states) is not int or maximum_states < 1 or type(require_all_paths) is not bool:
        raise ValueError("positive state budget and boolean path quantifier required")
    start = net._marking(initial)
    pending, paths, edges, goals, deadlocks = deque([start]), {start: ()}, {}, [], []
    while pending:
        state = pending.popleft()
        named = dict(zip(net.places, state))
        if unsafe and unsafe(named):
            return {"status": "unsafe_reachable", "path": paths[state], "state": named}
        if goal(named):
            goals.append(state)
            edges[state] = []
            continue
        following = net.successors(state)
        edges[state] = [after for _, after in following]
        if not following:
            deadlocks.append(state)
        for action, after in following:
            if after not in paths:
                if len(paths) >= maximum_states:
                    return {"status": "incomplete_state_limit", "states": len(paths)}
                paths[after] = paths[state] + (action,)
                pending.append(after)
    cycle = _cycle(edges)
    if not goals:
        status = "goal_unreachable"
    elif require_all_paths and (cycle or deadlocks):
        status = "nontermination_reachable" if cycle else "nonterminal_deadlock"
    else:
        status = "pass_all_paths_complete" if require_all_paths else "pass_possible_completion"
    witness = cycle[0] if cycle else deadlocks[0] if deadlocks else goals[0] if goals else start
    return {
        "status": status,
        "states": len(paths),
        "goal_reachable": bool(goals),
        "path": paths[witness],
        "cycle_markings": cycle,
        "nonterminal_deadlocks": deadlocks,
        "fairness_assumed": False,
        "scope": "finite supplied net; goals terminate the modeled episode",
    }


@dataclass(frozen=True)
class TimedTransition:
    transition: Transition
    minimum_ticks: int
    maximum_ticks: int
    earliest_start: int = 0
    latest_start: int | None = None

    def __post_init__(self):
        values = (self.minimum_ticks, self.maximum_ticks, self.earliest_start)
        if any(type(x) is not int or x < 0 for x in values) or self.minimum_ticks > self.maximum_ticks:
            raise ValueError("ordered nonnegative integer durations required")
        if self.latest_start is not None and (
            type(self.latest_start) is not int or self.latest_start < self.earliest_start
        ):
            raise ValueError("invalid latest-start tick")


class DiscreteTimedNet:
    """Serial atomic firings on an explicit time grid; not a concurrent timed-Petri solver."""

    def __init__(
        self, places, transitions, *, capacities=None, tick_seconds=1.0, maximum_duration_choices=1000
    ):
        if (
            isinstance(tick_seconds, bool)
            or not isinstance(tick_seconds, (float, int))
            or not 0 < tick_seconds < float("inf")
        ):
            raise ValueError("finite positive tick size required")
        if type(maximum_duration_choices) is not int or maximum_duration_choices < 1:
            raise ValueError("positive duration-choice budget required")
        if any(t.maximum_ticks - t.minimum_ticks + 1 > maximum_duration_choices for t in transitions):
            raise ValueError("duration choice expansion exceeds budget")
        self.net = WorkflowNet(tuple(places), tuple(t.transition for t in transitions), capacities=capacities)
        self.transitions = {t.transition.id: t for t in transitions}
        self.tick_seconds = float(tick_seconds)

    def verify_deadline(
        self, initial, *, goal, deadline_ticks, unsafe=None, require_all_paths=True, maximum_states=10_000
    ):
        if (
            type(deadline_ticks) is not int
            or deadline_ticks < 0
            or type(maximum_states) is not int
            or maximum_states < 1
            or type(require_all_paths) is not bool
        ):
            raise ValueError("nonnegative integer deadline and positive state budget required")
        start = (self.net._marking(initial), 0)
        pending, paths, edges, goals, failures = deque([start]), {start: ()}, {}, [], []
        while pending:
            key = pending.popleft()
            marking, clock = key
            named = dict(zip(self.net.places, marking))
            edges[key] = []
            if unsafe and unsafe(named, clock * self.tick_seconds):
                return {"status": "unsafe_reachable", "path": paths[key], "time_s": clock * self.tick_seconds}
            if goal(named):
                goals.append(key)
                continue
            following = []
            for action, after in self.net.successors(marking):
                timed = self.transitions[action]
                begin = max(clock, timed.earliest_start)
                if timed.latest_start is not None and begin > timed.latest_start:
                    continue
                for duration in range(timed.minimum_ticks, timed.maximum_ticks + 1):
                    end = begin + duration
                    if end > deadline_ticks:
                        failures.append(
                            {"path": paths[key] + ((action, duration),), "reason": "deadline_exceeded"}
                        )
                        continue
                    following.append((action, duration, (after, end)))
            if not following:
                failures.append({"path": paths[key], "reason": "no_completion_by_deadline"})
            for action, duration, after in following:
                edges[key].append(after)
                if after not in paths:
                    if len(paths) >= maximum_states:
                        return {"status": "incomplete_state_limit", "states": len(paths)}
                    paths[after] = paths[key] + ((action, duration),)
                    pending.append(after)
        cycle = _cycle(edges)
        passed = bool(goals) and (not require_all_paths or not failures and not cycle)
        return {
            "status": "pass_bounded_deadline" if passed else "deadline_or_progress_violation",
            "goal_reachable": bool(goals),
            "states": len(paths),
            "failures": failures,
            "zero_time_cycle": cycle,
            "deadline_s": deadline_ticks * self.tick_seconds,
            "scope": "serial atomic firings; enumerated integer duration choices; no fairness assumption",
        }


def compile_task_net(task, *, error_variants=None):
    """Compile attempt order and selected error alternatives; physical predicates stay in actions.

    Each predecessor edge gets its own token so fan-out does not consume another child's permission.
    Attempted and successful completion are deliberately distinct places.
    """
    error_variants = error_variants or {}
    ids = {s.id for s in task.steps}
    if set(error_variants) - ids:
        raise ValueError("error variant refers to an unknown task step")
    places, initial, transitions = set(), {}, []
    children = {key: [] for key in ids}
    for step in task.steps:
        for parent in step.predecessors:
            children[parent].append(step.id)
    for step in task.steps:
        inputs = {f"edge:{p}:{step.id}": 1 for p in step.predecessors}
        if not inputs:
            inputs = {"ready:" + step.id: 1}
            initial["ready:" + step.id] = 1
        outputs = {f"edge:{step.id}:{child}": 1 for child in children[step.id]}
        outputs["attempted:" + step.id] = 1
        success = outputs | {"success:" + step.id: 1}
        places.update(inputs)
        places.update(success)
        transitions.append(Transition(step.id + ":nominal", inputs, success, actor=step.actor))
        variants = error_variants.get(step.id, ())
        if len(variants) != len(set(variants)) or any(not v.strip() for v in variants):
            raise ValueError("unique nonempty error variant names required")
        for variant in variants:
            error = outputs | {f"error:{step.id}:{variant}": 1}
            places.update(error)
            transitions.append(
                Transition(step.id + ":" + variant, inputs, error, actor=step.actor, error_variant=True)
            )
    net = WorkflowNet(tuple(sorted(places)), tuple(transitions), capacities={p: 1 for p in places})
    return net, initial, tuple("attempted:" + key for key in sorted(ids))
