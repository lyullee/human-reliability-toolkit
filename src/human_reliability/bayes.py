"""Exact small discrete Bayesian networks for shared conditions and dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math

from .probability import probability


@dataclass(frozen=True)
class DiscreteNode:
    name: str
    states: tuple[str, ...]
    parents: tuple[str, ...]
    cpt: dict[tuple[str, ...], tuple[float, ...]]


class BayesianNetwork:
    """Transparent exact inference, bounded to avoid accidental exponential work.

    CPTs describe conditional distributions, not causal proof. Larger learned
    models can be supplied through an application-specific inference adapter.
    """

    def __init__(self, nodes: tuple[DiscreteNode, ...], *, maximum_states=1_000_000):
        names = {node.name for node in nodes}
        if not nodes or len(names) != len(nodes) or any(not node.name.strip() for node in nodes):
            raise ValueError("nonempty unique node names required")
        pending, ordered, done = list(nodes), [], set()
        while pending:
            ready = next((node for node in pending if set(node.parents) <= done), None)
            if ready is None:
                raise ValueError("missing parent or network cycle")
            if (
                not ready.states
                or len(set(ready.states)) != len(ready.states)
                or len(set(ready.parents)) != len(ready.parents)
            ):
                raise ValueError("node states and parents must be unique")
            ordered.append(ready)
            done.add(ready.name)
            pending.remove(ready)
        self.nodes = tuple(ordered)
        self.by_name = {node.name: node for node in self.nodes}
        self.state_count = math.prod(len(node.states) for node in self.nodes)
        if self.state_count > maximum_states:
            raise ValueError("exact inference state budget exceeded")
        for node in self.nodes:
            keys = set(product(*(self.by_name[parent].states for parent in node.parents)))
            if set(node.cpt) != keys:
                raise ValueError("CPT must cover every parent combination exactly once")
            for row in node.cpt.values():
                if len(row) != len(node.states) or not math.isclose(
                    sum(probability(p) for p in row), 1, abs_tol=1e-12, rel_tol=0
                ):
                    raise ValueError("conditional state probabilities must sum to one")

    def joint_states(self, evidence: dict[str, str] | None = None):
        observed = evidence or {}
        if any(
            key not in self.by_name or value not in self.by_name[key].states
            for key, value in observed.items()
        ):
            raise ValueError("unknown observed node/state")
        rows = []
        for values in product(*(node.states for node in self.nodes)):
            state = dict(zip((node.name for node in self.nodes), values))
            if any(state[key] != value for key, value in observed.items()):
                continue
            p = 1.0
            for node in self.nodes:
                key = tuple(state[parent] for parent in node.parents)
                p *= node.cpt[key][node.states.index(state[node.name])]
            rows.append((state, p))
        total = math.fsum(p for _, p in rows)
        if total <= 0:
            raise ValueError("evidence has zero probability")
        return tuple((state, p / total) for state, p in rows)

    def query(self, node: str, evidence: dict[str, str] | None = None):
        if node not in self.by_name:
            raise ValueError("unknown query node")
        result = dict.fromkeys(self.by_name[node].states, 0.0)
        for state, p in self.joint_states(evidence):
            result[state[node]] += p
        return result
