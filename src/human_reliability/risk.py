"""One serializable risk case joins estimates, causal logic, exposure and consequences."""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import Field, model_validator

from .assessment import AssessmentCase, AssessmentEngine
from .causal import CausalGraph, evaluate_causal_graph
from .contracts import Contract, Estimate, Evidence, Name, Nonnegative, Probability, canonical_digest
from .event_tree import Branch, event_tree


class InitiatingFrequency(Contract):
    mode: Literal["annual_rate", "demands"]
    evidence: Name
    annual_rate: Nonnegative | None = None
    demands_per_year: Nonnegative | None = None
    event_ref: str | None = None
    opportunity_definition: str | None = None

    @model_validator(mode="after")
    def meanings(self):
        if self.mode == "annual_rate" and any(
            v is not None for v in (self.demands_per_year, self.event_ref, self.opportunity_definition)
        ):
            raise ValueError("annual-rate initiator cannot also carry a demand model")
        if self.mode == "demands" and (
            self.annual_rate is not None or not self.event_ref or not self.opportunity_definition
        ):
            raise ValueError("demand initiator requires event and denominator meaning, without annual_rate")
        return self


class RiskBranch(Contract):
    id: Name
    evidence: Name
    probability: Probability | None = None
    event_ref: str | None = None
    conditioning: str | None = None
    complement: bool = False
    children: tuple[RiskBranch, ...] = ()
    consequence_id: str | None = None

    @model_validator(mode="after")
    def meanings(self):
        if (self.probability is None) == (self.event_ref is None):
            raise ValueError("branch requires exactly one probability or event reference")
        if self.event_ref and not self.conditioning:
            raise ValueError("referenced branch requires explicit conditional-path meaning")
        if self.children and self.consequence_id is not None or not self.children and not self.consequence_id:
            raise ValueError("only a terminal branch owns a consequence")
        return self


class RiskScenario(Contract):
    id: Name
    context_weight: Probability = 1.0
    evidence: Name
    initiating: InitiatingFrequency
    branches: tuple[RiskBranch, ...] = Field(min_length=1)


class ConsequenceMetrics(Contract):
    harm_probability: Probability | None = None
    harm_scope: Literal["includes_occupancy", "conditional_on_presence"] | None = None
    occupancy: Probability | None = None
    fatality_distribution: dict[int, Probability] | None = None
    expected_loss: Nonnegative | None = None
    currency: str | None = None
    evidence: Name

    @model_validator(mode="after")
    def quantities(self):
        if self.harm_probability is not None:
            if self.harm_scope is None or (
                self.harm_scope == "conditional_on_presence" and self.occupancy is None
            ):
                raise ValueError("harm needs its occupancy scope and, where applicable, occupancy")
            if self.harm_scope == "includes_occupancy" and self.occupancy is not None:
                raise ValueError("occupancy cannot be applied twice")
        elif self.harm_scope is not None or self.occupancy is not None:
            raise ValueError("occupancy requires a harm-probability model")
        if self.fatality_distribution is not None:
            if not self.fatality_distribution or any(k < 0 for k in self.fatality_distribution):
                raise ValueError("nonnegative discrete fatality outcomes required")
            if not math.isclose(sum(self.fatality_distribution.values()), 1, abs_tol=1e-12, rel_tol=0):
                raise ValueError("conditional fatality distribution must sum to one")
        if (self.expected_loss is None) != (self.currency is None) or self.currency == "":
            raise ValueError("loss needs an explicit currency")
        return self

    @property
    def receptor_harm(self):
        if self.harm_probability is None:
            return None
        return self.harm_probability * (self.occupancy if self.harm_scope == "conditional_on_presence" else 1)


class ConsequenceSpec(Contract):
    id: Name
    provider: Name = "fixed"
    parameters: dict[str, Any]


class RiskCase(Contract):
    schema_version: Literal["1"] = "1"
    id: Name
    assessment: AssessmentCase | None = None
    estimates: tuple[Estimate, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    intervention_basis: dict[str, Any] | None = None
    graphs: tuple[CausalGraph, ...] = ()
    opportunity_definitions: dict[str, Name] = {}
    scenario_mode: Literal["exclusive_contexts", "distinct_initiators"] = "exclusive_contexts"
    partition_evidence: Name
    scenarios: tuple[RiskScenario, ...] = Field(min_length=1)
    consequences: tuple[ConsequenceSpec, ...] = Field(min_length=1)
    fn_thresholds: tuple[int, ...] = ()

    @model_validator(mode="after")
    def identities(self):
        available = {e.id for e in self.evidence}
        if len(available) != len(self.evidence):
            raise ValueError("duplicate risk evidence identity")
        if self.assessment:
            supplied = {e.id: e for e in self.evidence}
            for record in self.assessment.task.evidence:
                if record.id in supplied and supplied[record.id] != record:
                    raise ValueError("conflicting evidence definitions")
                available.add(record.id)
        if any(set(estimate.evidence_ids) - available for estimate in self.estimates):
            raise ValueError("supplied estimates must cite available risk-case evidence")
        for rows in (self.estimates, self.graphs, self.scenarios, self.consequences):
            ids = [getattr(row, "event_id", None) or getattr(row, "id", None) for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate risk-case identity")
        if self.scenario_mode == "exclusive_contexts":
            if not math.isclose(sum(s.context_weight for s in self.scenarios), 1, abs_tol=1e-12, rel_tol=0):
                raise ValueError("exclusive contextual weights must sum to one")
        elif any(s.context_weight != 1 for s in self.scenarios):
            raise ValueError("distinct initiators have unit contextual weights")
        if any(type(n) is not int or n < 1 for n in self.fn_thresholds):
            raise ValueError("positive integer F-N thresholds required")
        return self


class ConsequenceRegistry:
    """Pure local providers; registration does not authorize remote or actuator calls."""

    def __init__(self):
        self._provenance = {
            "fixed": {"version": "ConsequenceMetrics.v1", "evidence": "Declared fixed consequence inputs"}
        }
        self._providers = {
            "fixed": lambda parameters, context: ConsequenceMetrics.model_validate_json(
                json.dumps(parameters)
            )
        }

    def register(self, name, provider, *, version, evidence):
        if not isinstance(name, str) or not name.strip() or name in self._providers or not callable(provider):
            raise ValueError("new named callable consequence provider required")
        if not version.strip() or not evidence.strip():
            raise ValueError("provider code/version pin and evidence required")
        self._providers[name] = provider
        self._provenance[name] = {"version": version, "evidence": evidence}

    def provenance(self, name):
        return dict(self._provenance[name])

    def evaluate(self, spec, context):
        if spec.provider not in self._providers:
            raise KeyError("consequence provider not registered: " + spec.provider)
        value = self._providers[spec.provider](dict(spec.parameters), context)
        if not isinstance(value, ConsequenceMetrics):
            raise ValueError("provider must return ConsequenceMetrics")
        return value


class RiskEngine:
    def __init__(self, *, assessment_engine=None, consequence_registry=None):
        self.assessment_engine = assessment_engine or AssessmentEngine()
        self.consequences = consequence_registry or ConsequenceRegistry()

    def assess(self, case: RiskCase):
        estimates = {e.event_id: e for e in case.estimates}
        definitions = dict(case.opportunity_definitions)
        assessment = None
        if case.assessment:
            assessment = self.assessment_engine.assess(case.assessment)
            for raw in assessment["estimates"]:
                estimate = Estimate.model_validate_json(json.dumps(raw))
                if estimate.event_id in estimates:
                    raise ValueError("an assessed event cannot also have a supplied estimate")
                estimates[estimate.event_id] = estimate
            for event in case.assessment.events:
                if event.id in definitions and definitions[event.id] != event.opportunity_definition:
                    raise ValueError("conflicting opportunity definitions")
                definitions[event.id] = event.opportunity_definition
        if set(estimates) & {g.id for g in case.graphs}:
            raise ValueError("graph and estimate reference identities overlap")
        graph_results = {g.id: evaluate_causal_graph(g, estimates) for g in case.graphs}
        unresolved, rows = [], []
        incomplete_partitions = False
        specs = {c.id: c for c in case.consequences}

        def reference(key, conditioning=None):
            if key in estimates:
                value, context = estimates[key].probability, estimates[key].conditioning
            elif key in graph_results:
                row = graph_results[key]
                if row["status"] != "evaluated":
                    raise KeyError("causal graph withheld: " + key)
                value, context = row["probability"], row["conditioning"]
            else:
                raise KeyError("unknown event reference: " + key)
            if conditioning is not None and conditioning != context:
                raise ValueError("branch conditioning disagrees with its event estimate")
            return value

        def branches(nodes, seen):
            result = []
            for node in nodes:
                if node.id in seen:
                    raise ValueError("branch IDs must be unique within a scenario")
                seen.add(node.id)
                p = (
                    node.probability
                    if node.event_ref is None
                    else reference(node.event_ref, node.conditioning)
                )
                result.append(
                    Branch(
                        node.id,
                        1 - p if node.complement else p,
                        branches(node.children, seen) if node.children else (),
                        node.consequence_id,
                        node.evidence,
                    )
                )
            return tuple(result)

        for scenario in case.scenarios:
            frequency = scenario.initiating
            rate = frequency.annual_rate
            if frequency.mode == "demands":
                expected = definitions.get(frequency.event_ref)
                if expected != frequency.opportunity_definition:
                    raise ValueError("demand exposure must match a declared target opportunity definition")
                if frequency.demands_per_year is None:
                    unresolved.append(scenario.id + ": demand exposure unavailable")
                    rate = None
                else:
                    try:
                        rate = frequency.demands_per_year * reference(frequency.event_ref)
                    except KeyError as error:
                        unresolved.append(scenario.id + ": " + str(error))
                        rate = None
            elif rate is None:
                unresolved.append(scenario.id + ": annual frequency unavailable")
            try:
                partition = branches(scenario.branches, set())
            except KeyError as error:
                unresolved.append(scenario.id + ": " + str(error))
                incomplete_partitions = True
                continue
            ledger = event_tree(1.0 if rate is None else rate * scenario.context_weight, partition)
            for row in ledger:
                row = dict(row)
                row["scenario_id"] = scenario.id
                row["context_weight"] = scenario.context_weight
                if rate is None:
                    row["annual_frequency_per_year"] = None
                key = row["consequence_id"]
                if key not in specs:
                    raise ValueError("missing consequence specification: " + key)
                try:
                    metrics = self.consequences.evaluate(
                        specs[key],
                        {
                            "scenario_id": scenario.id,
                            "path": row["path"],
                            "estimates": estimates,
                            "graph_results": graph_results,
                        },
                    )
                except KeyError as error:
                    unresolved.append(scenario.id + ": " + str(error))
                    metrics = None
                row["consequences"] = None if metrics is None else metrics.model_dump(mode="json")
                row["conditional_receptor_harm"] = None if metrics is None else metrics.receptor_harm
                row["provider_provenance"] = (
                    None if metrics is None else self.consequences.provenance(specs[key].provider)
                )
                rows.append(row)
        complete_frequency = (
            bool(rows)
            and not incomplete_partitions
            and all(r["annual_frequency_per_year"] is not None for r in rows)
        )
        risk_complete = complete_frequency and all(r["conditional_receptor_harm"] is not None for r in rows)
        individual_risk = (
            sum(r["annual_frequency_per_year"] * r["conditional_receptor_harm"] for r in rows)
            if risk_complete
            else None
        )
        fn = {}
        for n in case.fn_thresholds:
            if complete_frequency and all(
                r["consequences"] is not None and r["consequences"]["fatality_distribution"] is not None
                for r in rows
            ):
                fn[str(n)] = sum(
                    r["annual_frequency_per_year"]
                    * sum(p for k, p in r["consequences"]["fatality_distribution"].items() if int(k) >= n)
                    for r in rows
                )
            else:
                fn[str(n)] = None
        loss_rows = [
            r
            for r in rows
            if r["consequences"] is not None and r["consequences"]["expected_loss"] is not None
        ]
        currencies = {r["consequences"]["currency"] for r in loss_rows}
        if len(currencies) > 1:
            raise ValueError("expected losses in different currencies cannot be added")
        loss = (
            sum(r["annual_frequency_per_year"] * r["consequences"]["expected_loss"] for r in rows)
            if complete_frequency and len(loss_rows) == len(rows)
            else None
        )
        return {
            "schema": "human_reliability.risk.v1",
            "case_id": case.id,
            "input_digest": canonical_digest(case),
            "status": "evaluated" if complete_frequency and not unresolved else "withheld_or_partial",
            "unresolved": unresolved,
            "input_estimates": [e.model_dump(mode="json") for e in estimates.values()],
            "evidence": [e.model_dump(mode="json") for e in case.evidence],
            "assessment": assessment,
            "graphs": graph_results,
            "ledger": rows,
            "annual_frequency_per_year": sum(r["annual_frequency_per_year"] for r in rows)
            if complete_frequency
            else None,
            "individual_risk_rate_per_year": individual_risk,
            "fn_frequency_per_year": fn,
            "expected_loss_per_year": loss,
            "currency": next(iter(currencies), None),
            "field_validation_claim": False,
        }
