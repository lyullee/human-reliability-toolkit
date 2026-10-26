"""Reviewed case changes, paired model comparisons and static risk importance."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
from pydantic import model_validator

from .contracts import Contract, Evidence, Name, canonical_digest
from .fault_tree import Event, birnbaum_importance, fault_probability
from .risk import RiskCase, RiskEngine
from .uncertainty import propagate, sample_inputs


class CaseChange(Contract):
    path: tuple[Name, ...]
    value: Any
    unit: Name

    @model_validator(mode="after")
    def location(self):
        if not self.path or self.path[0] in {"schema_version", "id"}:
            raise ValueError("a non-identity case field path is required")
        expected = {
            "probability": "1",
            "context_weight": "1",
            "harm_probability": "1",
            "occupancy": "1",
            "annual_rate": "1/year",
            "demands_per_year": "demand/year",
        }
        if self.path[-1] in expected and self.unit != expected[self.path[-1]]:
            raise ValueError("intervention quantity unit mismatch")
        return self


class Intervention(Contract):
    id: Name
    version: Name
    rationale: Name
    evidence: Name
    changes: tuple[CaseChange, ...]
    exposure_change_review: str | None = None

    @model_validator(mode="after")
    def disjoint_changes(self):
        if not self.changes:
            raise ValueError("an intervention must contain a concrete change")
        paths = [c.path for c in self.changes]
        if any(a == b[: len(a)] or b == a[: len(b)] for i, a in enumerate(paths) for b in paths[i + 1 :]):
            raise ValueError("intervention paths cannot overlap")
        return self


def apply_intervention(case: RiskCase, intervention: Intervention) -> RiskCase:
    document = case.model_dump(mode="json")
    changed_estimates, changed_leaves = set(), set()
    for change in intervention.changes:
        if change.path[-1] in {"failures", "opportunities"}:
            raise ValueError("an intervention cannot rewrite observed count evidence")
        if change.path[0] == "estimates":
            if len(change.path) != 3 or change.path[2] != "probability" or not change.path[1].isdecimal():
                raise ValueError("estimate interventions override a probability, not its source metadata")
            changed_estimates.add(int(change.path[1]))
        if (
            len(change.path) == 5
            and change.path[0] == "graphs"
            and change.path[2] == "leaves"
            and change.path[-1] == "probability"
        ):
            changed_leaves.add((int(change.path[1]), int(change.path[3])))
        current = document
        for part in change.path[:-1]:
            if isinstance(current, list):
                if not part.isdecimal() or int(part) >= len(current):
                    raise ValueError("invalid intervention list index")
                current = current[int(part)]
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise ValueError("intervention path does not exist")
        final = change.path[-1]
        if isinstance(current, list):
            if not final.isdecimal() or int(final) >= len(current):
                raise ValueError("invalid intervention list index")
            current[int(final)] = change.value
        elif isinstance(current, dict) and final in current:
            current[final] = change.value
        else:
            raise ValueError("intervention path does not exist")
    evidence_id = "intervention:" + intervention.id + ":" + intervention.version
    if evidence_id in {e.id for e in case.evidence}:
        raise ValueError("intervention identity/version already applied")
    document["evidence"].append(
        Evidence(
            id=evidence_id,
            reference=intervention.evidence,
            origin="assumed",
            applicability=intervention.rationale,
            limitations=("Modeled intervention effect is not an observed outcome.",),
        ).model_dump(mode="json")
    )
    for index in changed_estimates:
        old = case.estimates[index]
        row = document["estimates"][index]
        row.update(
            method="intervention_override",
            status="assumed",
            uncertainty={},
            evidence_ids=list(old.evidence_ids)
            + ([evidence_id] if evidence_id not in old.evidence_ids else []),
            trace={"baseline_estimate": old.model_dump(mode="json"), "intervention_evidence": evidence_id},
        )
    for graph, leaf in changed_leaves:
        document["graphs"][graph]["leaves"][leaf]["evidence"] = evidence_id
    document["intervention_basis"] = {
        "intervention": intervention.model_dump(mode="json"),
        "baseline_input_digest": canonical_digest(case),
        "origin": "assumed_model_change",
    }
    document["id"] = case.id + ":" + intervention.id + ":" + intervention.version
    alternative = RiskCase.model_validate_json(json.dumps(document, allow_nan=False))
    before = [(s.id, s.context_weight, s.initiating.model_dump()) for s in case.scenarios]
    after = [(s.id, s.context_weight, s.initiating.model_dump()) for s in alternative.scenarios]
    if before != after and not (intervention.exposure_change_review or "").strip():
        raise ValueError("changed initiators or exposure require an explicit comparison review")
    return alternative


def compare_intervention(case: RiskCase, intervention: Intervention, *, engine=None):
    engine = engine or RiskEngine()
    alternative = apply_intervention(case, intervention)
    baseline, changed = engine.assess(case), engine.assess(alternative)
    differences = {}
    for key in ("annual_frequency_per_year", "individual_risk_rate_per_year", "expected_loss_per_year"):
        a, b = baseline[key], changed[key]
        differences[key] = {
            "baseline": a,
            "alternative": b,
            "reduction": None if a is None or b is None else a - b,
            "relative_reduction": None if a in (None, 0) or b is None else (a - b) / a,
        }
    return {
        "intervention": intervention.model_dump(mode="json"),
        "baseline": baseline,
        "alternative": changed,
        "metrics": differences,
        "causally_identified_field_effect": False,
    }


def paired_model_comparison(
    baseline_model, alternative_model, distributions, *, size, seed, latent_correlation=None, evidence
):
    if not evidence.strip():
        raise ValueError("intervention assumptions need evidence")
    samples = sample_inputs(distributions, size, seed=seed, latent_correlation=latent_correlation)
    a = propagate(baseline_model, samples)["outputs"]
    b = propagate(alternative_model, samples)["outputs"]
    difference = a - b
    return {
        "baseline_mean": float(a.mean()),
        "alternative_mean": float(b.mean()),
        "mean_reduction": float(difference.mean()),
        "reduction_p05_p50_p95": np.quantile(difference, [0.05, 0.5, 0.95]).tolist(),
        "monte_carlo_standard_error": float(difference.std(ddof=1) / math.sqrt(size)) if size > 1 else None,
        "paired_reductions": difference,
        "samples": size,
        "seed": seed,
        "evidence": evidence,
        "causally_identified_field_effect": False,
    }


def risk_importance(tree, probabilities, *, backend="enumerate"):
    def coherent(node):
        return isinstance(node, Event) or node.kind != "NOT" and all(coherent(c) for c in node.children)

    if not coherent(tree):
        raise ValueError("standard FV/RAW/RRW report requires monotone static logic")
    q = fault_probability(tree, probabilities, backend=backend)
    birnbaum = birnbaum_importance(tree, probabilities, backend=backend)
    rows = {}
    for key in probabilities:
        q0 = fault_probability(tree, probabilities | {key: 0.0}, backend=backend)
        q1 = fault_probability(tree, probabilities | {key: 1.0}, backend=backend)
        rows[key] = {
            "birnbaum": birnbaum[key],
            "fussell_vesely": (q - q0) / q if q else None,
            "risk_achievement_worth": q1 / q if q else None,
            "risk_reduction_worth": q / q0 if q0 else None,
            "zero_denominator": q == 0 or q0 == 0,
        }
    return {
        "top_probability": q,
        "events": rows,
        "assumptions": "independent primitive events; static monotone logic",
    }
