"""Typed causal-event specifications compile to the existing shared-event logic."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Estimate, Name, Probability
from .fault_tree import Event, Gate, fault_probability, fault_probability_joint
from .methods import multiplier_probability


class CausalLeaf(Contract):
    id: Name
    kind: Literal["cause", "latent", "action", "detection_failure", "recovery_failure", "barrier_failure"]
    evidence: Name
    conditioning: Name
    probability: Probability | None = None
    estimate_id: str | None = None
    dependency_groups: tuple[Name, ...] = ()
    scope_group: str | None = None
    includes: tuple[Literal["timing", "recovery", "dependency"], ...] = ()
    modifiers: dict[str, float] = {}
    modifier_evidence: str | None = None
    modifier_normalization: Literal["bounded_odds", "cap"] = "bounded_odds"

    @model_validator(mode="after")
    def source(self):
        if (self.probability is None) == (self.estimate_id is None):
            raise ValueError("a leaf needs exactly one probability or estimate reference")
        if self.modifiers and (self.kind != "cause" or not self.modifier_evidence):
            raise ValueError("within-mechanism modifiers need a cause and explicit evidence")
        return self


class CausalGate(Contract):
    id: Name
    kind: Literal["AND", "OR", "NOT", "VOTE"]
    children: tuple[Name, ...]
    threshold: int | None = None


class JointState(Contract):
    state: dict[str, bool]
    probability: Probability


class CausalGraph(Contract):
    id: Name
    root: Name
    conditioning: Name
    leaves: tuple[CausalLeaf, ...]
    gates: tuple[CausalGate, ...] = ()
    independence_evidence: str | None = None
    joint_states: tuple[JointState, ...] = ()
    maximum_depth: int = Field(default=100, ge=1, le=300)
    maximum_expanded_nodes: int = Field(default=10_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def structure(self):
        nodes = [n.id for n in (*self.leaves, *self.gates)]
        if not nodes or len(nodes) != len(set(nodes)) or self.root not in nodes:
            raise ValueError("unique graph nodes and an existing root required")
        if any(leaf.conditioning != self.conditioning for leaf in self.leaves):
            raise ValueError("graph leaves must describe the same conditioning population")
        by_id = {n.id: n for n in self.gates}
        visiting, visited = set(), set()

        def walk(key):
            if key not in nodes or key in visiting:
                raise ValueError("unknown reference or cycle in causal graph")
            if len(visiting) >= self.maximum_depth:
                raise ValueError("causal graph depth budget exceeded")
            if key in visited:
                return
            visiting.add(key)
            if key in by_id:
                for child in by_id[key].children:
                    walk(child)
                Gate(by_id[key].kind, tuple(Event(c) for c in by_id[key].children), by_id[key].threshold)
            visiting.remove(key)
            visited.add(key)

        walk(self.root)
        if visited != set(nodes):
            raise ValueError("unreachable graph nodes are not silently ignored")
        return self

    def tree(self):
        gates = {g.id: g for g in self.gates}
        expanded = 0

        def build(key):
            nonlocal expanded
            expanded += 1
            if expanded > self.maximum_expanded_nodes:
                raise ValueError("causal graph expansion budget exceeded")
            if key not in gates:
                return Event(key)
            gate = gates[key]
            return Gate(gate.kind, tuple(build(c) for c in gate.children), gate.threshold)

        return build(self.root)


def evaluate_causal_graph(
    graph: CausalGraph, estimates: dict[str, Estimate] | None = None, *, backend="enumerate"
):
    values, evidence, reasons, groups, scopes = {}, set(), [], {}, {}
    estimates = estimates or {}
    for leaf in graph.leaves:
        includes = set(leaf.includes)
        if leaf.estimate_id is not None:
            if leaf.estimate_id not in estimates:
                reasons.append("missing estimate: " + leaf.estimate_id)
                continue
            estimate = estimates[leaf.estimate_id]
            if estimate.event_id != leaf.estimate_id or estimate.conditioning != leaf.conditioning:
                raise ValueError("causal estimate identity or conditioning mismatch")
            value = estimate.probability
            includes |= set(estimate.includes)
            evidence.update(estimate.evidence_ids)
        else:
            value = leaf.probability
        if leaf.kind == "recovery_failure":
            includes.add("recovery")
        if leaf.scope_group:
            previous = scopes.setdefault(leaf.scope_group, set())
            if previous & includes:
                raise ValueError("effect counted twice in one failure scope")
            previous.update(includes)
        for group in leaf.dependency_groups:
            groups.setdefault(group, []).append(leaf.id)
        if leaf.modifiers:
            value, _ = multiplier_probability(
                value, leaf.modifiers, normalization=leaf.modifier_normalization
            )
            evidence.add(leaf.modifier_evidence)
        values[leaf.id] = value
        evidence.add(leaf.evidence)
    shared = {k: v for k, v in groups.items() if len(v) > 1}
    if not graph.joint_states:
        if shared:
            reasons.append("shared dependency groups require a joint distribution")
        if len(graph.leaves) > 1 and not (graph.independence_evidence or "").strip():
            reasons.append("independence evidence not supplied")
    if reasons:
        return {
            "graph_id": graph.id,
            "status": "withheld",
            "probability": None,
            "reasons": reasons,
            "shared_groups": shared,
        }
    if graph.joint_states:
        if any(leaf.modifiers for leaf in graph.leaves):
            raise ValueError("modifying marginals does not define a changed joint distribution")
        joint = tuple((row.state, row.probability) for row in graph.joint_states)
        value = fault_probability_joint(graph.tree(), joint)
        for key, marginal in values.items():
            actual = sum(w for state, w in joint if state[key])
            if abs(actual - marginal) > 1e-9:
                raise ValueError("joint distribution contradicts a declared leaf marginal")
    else:
        value = fault_probability(graph.tree(), values, backend=backend)
    return {
        "graph_id": graph.id,
        "status": "evaluated",
        "probability": value,
        "conditioning": graph.conditioning,
        "leaf_probabilities": values,
        "evidence_ids": sorted(evidence),
        "joint_model": bool(graph.joint_states),
        "shared_groups": shared,
        "field_validation_claim": False,
    }
