"""Boolean fault trees preserve shared event identity and support declared joint states."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Literal

from .probability import probability


@dataclass(frozen=True)
class Event:
    id: str

    def __post_init__(self):
        if not self.id.strip():
            raise ValueError("event ID required")


@dataclass(frozen=True)
class Gate:
    kind: Literal["AND", "OR", "NOT", "VOTE"]
    children: tuple[Event | Gate, ...]
    threshold: int | None = None

    def __post_init__(self):
        if not self.children or self.kind not in {"AND", "OR", "NOT", "VOTE"}:
            raise ValueError("recognized gate and nonempty children required")
        if self.kind == "NOT" and len(self.children) != 1:
            raise ValueError("NOT has exactly one child")
        if self.kind == "VOTE" and (
            type(self.threshold) is not int or not 1 <= self.threshold <= len(self.children)
        ):
            raise ValueError("VOTE requires an integer threshold in the child range")
        if self.kind != "VOTE" and self.threshold is not None:
            raise ValueError("threshold belongs only to a VOTE gate")


def event_ids(tree):
    if isinstance(tree, Event):
        return frozenset({tree.id})
    if not isinstance(tree, Gate):
        raise TypeError("fault tree nodes must be Event or Gate")
    return frozenset().union(*(event_ids(child) for child in tree.children))


def evaluate_state(tree, state):
    if isinstance(tree, Event):
        if tree.id not in state or type(state[tree.id]) is not bool:
            raise ValueError("state must supply boolean values for every event")
        return state[tree.id]
    results = [evaluate_state(child, state) for child in tree.children]
    if tree.kind == "NOT":
        return not results[0]
    if tree.kind == "AND":
        return all(results)
    if tree.kind == "OR":
        return any(results)
    return sum(results) >= tree.threshold


def _bdd_probability(tree, values):
    from dd.autoref import BDD

    manager = BDD()
    names = {key: f"e{index}" for index, key in enumerate(sorted(values))}
    inverse = {name: key for key, name in names.items()}
    manager.declare(*names.values())

    def compile_node(node):
        if isinstance(node, Event):
            return manager.var(names[node.id])
        children = [compile_node(child) for child in node.children]
        if node.kind == "NOT":
            return ~children[0]
        if node.kind in {"AND", "OR"}:
            result = manager.true if node.kind == "AND" else manager.false
            for child in children:
                result = result & child if node.kind == "AND" else result | child
            return result
        # Dynamic programming represents a cardinality gate without counting
        # a repeated event as independent trials.
        counts = [manager.true] + [manager.false] * node.threshold
        for child in children:
            counts = [counts[0]] + [counts[k] | (counts[k - 1] & child) for k in range(1, len(counts))]
        return counts[-1]

    root = compile_node(tree)
    memo = {}

    def weighted(node):
        if node == manager.true:
            return 1.0
        if node == manager.false:
            return 0.0
        if node in memo:
            return memo[node]
        variable = node.var
        p = values[inverse[variable]]
        low = manager.let({variable: False}, node)
        high = manager.let({variable: True}, node)
        result = (1 - p) * weighted(low) + p * weighted(high)
        memo[node] = result
        return result

    result = weighted(root)
    # Recursive closures otherwise keep Function nodes alive through a cycle
    # until after the BDD manager's shutdown assertion runs.
    memo.clear()
    root = None
    weighted = None
    compile_node = None
    manager.collect_garbage()
    return result


def fault_probability(tree, probabilities: dict[str, float], *, backend="enumerate"):
    ids = event_ids(tree)
    if set(probabilities) != ids:
        raise ValueError("probability keys must exactly match distinct tree events")
    values = {key: probability(value) for key, value in probabilities.items()}
    if backend == "bdd":
        return _bdd_probability(tree, values)
    if backend != "enumerate" or len(ids) > 20:
        raise ValueError("enumeration supports at most 20 events; select bdd for larger trees")
    ordered = sorted(ids)
    total = []
    for flags in product((False, True), repeat=len(ordered)):
        state = dict(zip(ordered, flags))
        if evaluate_state(tree, state):
            total.append(math.prod(values[key] if flag else 1 - values[key] for key, flag in state.items()))
    return math.fsum(total)


def fault_probability_joint(tree, joint_states):
    """Evaluate dependence using a complete distribution of distinct event states."""
    ids = event_ids(tree)
    seen, total, failure = set(), 0.0, 0.0
    for state, weight in joint_states:
        if set(state) != ids or any(type(v) is not bool for v in state.values()):
            raise ValueError("joint row must specify every event as a boolean")
        key = tuple(sorted(state.items()))
        if key in seen:
            raise ValueError("duplicate joint state")
        seen.add(key)
        p = probability(weight)
        total += p
        failure += p * evaluate_state(tree, state)
    if not math.isclose(total, 1.0, abs_tol=1e-12, rel_tol=0):
        raise ValueError("joint distribution must sum to one")
    return failure


def minimal_cut_sets(tree):
    """Exact small monotone-tree cut sets; NOT requires a different explanation model."""

    def monotone(node):
        return isinstance(node, Event) or (
            node.kind != "NOT" and all(monotone(child) for child in node.children)
        )

    if not monotone(tree):
        raise ValueError("cut sets require a monotone tree")
    ids = sorted(event_ids(tree))
    if len(ids) > 18:
        raise ValueError("cut-set enumeration limited to 18 distinct events")
    candidates = []
    states = sorted(product((False, True), repeat=len(ids)), key=sum)
    for flags in states:
        active = frozenset(key for key, flag in zip(ids, flags) if flag)
        if any(existing <= active for existing in candidates):
            continue
        if evaluate_state(tree, dict(zip(ids, flags))):
            candidates.append(active)
    return tuple(candidates)


def birnbaum_importance(tree, probabilities, *, backend="enumerate"):
    return {
        key: fault_probability(tree, probabilities | {key: 1.0}, backend=backend)
        - fault_probability(tree, probabilities | {key: 0.0}, backend=backend)
        for key in probabilities
    }
