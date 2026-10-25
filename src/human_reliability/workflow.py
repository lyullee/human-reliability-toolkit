"""Bounded Petri-net reachability tests check modeled procedure constraints."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Transition:
    id: str
    consume: dict[str, int]
    produce: dict[str, int]
    actor: str = "system"
    error_variant: bool = False


class WorkflowNet:
    def __init__(self, places: tuple[str, ...], transitions: tuple[Transition, ...], *, capacities=None):
        if not places or len(set(places)) != len(places) or any(not place.strip() for place in places):
            raise ValueError("unique nonempty place identities required")
        if len({transition.id for transition in transitions}) != len(transitions):
            raise ValueError("transition identities must be unique")
        self.places, self.transitions = places, transitions
        self.capacities = dict(capacities or {})
        if set(self.capacities) - set(places) or any(
            type(c) is not int or c < 1 for c in self.capacities.values()
        ):
            raise ValueError("positive capacities for known places required")
        for transition in transitions:
            if not transition.id.strip():
                raise ValueError("transition identity required")
            if (set(transition.consume) | set(transition.produce)) - set(places):
                raise ValueError("unknown transition place")
            if any(
                type(value) is not int or value < 0
                for value in (*transition.consume.values(), *transition.produce.values())
            ):
                raise ValueError("nonnegative integer arc weights required")

    def _marking(self, marking):
        if set(marking) - set(self.places) or any(
            type(value) is not int or value < 0 for value in marking.values()
        ):
            raise ValueError("nonnegative integer tokens at known places required")
        result = tuple(marking.get(place, 0) for place in self.places)
        if any(value > self.capacities.get(place, float("inf")) for place, value in zip(self.places, result)):
            raise ValueError("marking exceeds place capacity")
        return result

    def successors(self, marking):
        tokens = dict(zip(self.places, marking))
        result = []
        for transition in self.transitions:
            if any(tokens[place] < value for place, value in transition.consume.items()):
                continue
            after = {
                place: value - transition.consume.get(place, 0) + transition.produce.get(place, 0)
                for place, value in tokens.items()
            }
            if any(value > self.capacities.get(place, float("inf")) for place, value in after.items()):
                continue
            result.append((transition.id, tuple(after[place] for place in self.places)))
        return result

    def verify(self, initial, *, unsafe, terminal=None, maximum_states=10_000):
        """PASS requires exhaustive exploration within the declared finite bound."""
        if type(maximum_states) is not int or maximum_states < 1:
            raise ValueError("positive state exploration limit required")
        start = self._marking(initial)
        pending, seen, deadlocks = deque([(start, ())]), {start}, []
        while pending:
            state, path = pending.popleft()
            named = dict(zip(self.places, state))
            if unsafe(named):
                return {"status": "unsafe_reachable", "path": path, "state": named, "states": len(seen)}
            following = self.successors(state)
            if not following and not (terminal and terminal(named)):
                deadlocks.append({"state": named, "path": path})
            for action, after in following:
                if after not in seen:
                    if len(seen) >= maximum_states:
                        return {
                            "status": "incomplete_state_limit",
                            "states": len(seen),
                            "deadlocks": deadlocks,
                        }
                    seen.add(after)
                    pending.append((after, path + (action,)))
        return {
            "status": "deadlock_reachable" if deadlocks else "pass_modeled_property",
            "states": len(seen),
            "deadlocks": deadlocks,
            "scope": "specified transitions and predicate only",
        }
