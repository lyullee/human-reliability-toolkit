"""Searchable human-performance evidence with explicit provenance and transfer reviews."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Estimate, Evidence, HumanFailureEvent, Name, Nonnegative, canonical_digest
from .probability import BetaPrior, nonnegative, probability


class SourceRights(Contract):
    license_id: Name
    reference: Name
    numeric_reuse: Literal[
        "permitted_with_attribution", "government_public_use", "numeric_facts_only", "not_cleared"
    ]
    notice: Name


class HumanEvidenceSource(Contract):
    id: Name
    title: Name
    authors: tuple[Name, ...]
    url: Name
    version: Name
    reviewed_on: Name
    setting: Name
    rights: SourceRights
    limitations: tuple[Name, ...]


EvidenceKind = Literal[
    "observed_count",
    "reported_observed_probability",
    "method_probability",
    "method_interval",
    "method_multiplier",
    "method_component",
    "method_rule",
]


class HumanErrorRecord(Contract):
    id: Name
    source_id: Name
    kind: EvidenceKind
    method: Name
    function: Name
    label: Name
    domain: Name
    locator: Name
    quantity: Literal["probability", "multiplier", "base_component", "terminal_rule"]
    opportunity_definition: Name
    failure_definition: Name
    conditions: dict[str, int | float | str | bool] = Field(default_factory=dict)
    failures: int | None = Field(default=None, ge=0, strict=True)
    opportunities: int | None = Field(default=None, gt=0, strict=True)
    value: Nonnegative | None = None
    lower: Nonnegative | None = None
    upper: Nonnegative | None = None
    basis: Literal[
        "simulator_observation",
        "field_observation",
        "laboratory_observation",
        "operational_record",
        "method_reference",
        "expert_case_study",
        "placeholder",
    ]
    limitations: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def check_measure(self):
        if self.kind == "observed_count":
            if (
                self.failures is None
                or self.opportunities is None
                or self.failures > self.opportunities
                or self.value is not None
                or self.quantity != "probability"
                or self.lower is not None
                or self.upper is not None
                or self.basis
                not in {
                    "simulator_observation",
                    "field_observation",
                    "laboratory_observation",
                    "operational_record",
                }
            ):
                raise ValueError(
                    "observations need valid counts and cannot masquerade as supplied probabilities"
                )
        elif self.failures is not None or self.opportunities is not None:
            raise ValueError("method estimates do not carry invented empirical denominators")
        if (self.lower is None) != (self.upper is None):
            raise ValueError("both range endpoints required")
        if self.lower is not None and self.lower > self.upper:
            raise ValueError("range endpoints out of order")
        if self.quantity in {"probability", "base_component"}:
            for value in (self.value, self.lower, self.upper):
                if value is not None:
                    probability(value)
        required_quantity = {
            "reported_observed_probability": "probability",
            "method_probability": "probability",
            "method_interval": "probability",
            "method_multiplier": "multiplier",
            "method_component": "base_component",
            "method_rule": "terminal_rule",
        }
        if self.kind in required_quantity and self.quantity != required_quantity[self.kind]:
            raise ValueError("record kind and mathematical quantity disagree")
        if self.kind == "method_interval" and (self.lower is None or self.value is not None):
            raise ValueError("an interval has bounds without an automatic point selection")
        if self.kind not in {"observed_count", "method_interval"} and self.value is None:
            raise ValueError("numerical method records require a value")
        if self.kind == "method_multiplier" and self.value <= 0:
            raise ValueError("a multiplier must be positive")
        if self.kind == "reported_observed_probability":
            if self.basis not in {
                "simulator_observation",
                "field_observation",
                "laboratory_observation",
                "operational_record",
            }:
                raise ValueError("reported observed probabilities need an observational origin")
            if self.lower is not None and not self.lower <= self.value <= self.upper:
                raise ValueError("reported observational bounds must contain the reported value")
            if not self.limitations:
                raise ValueError("reported observations without counts need explicit limitations")
        return self

    @property
    def observed_fraction(self):
        return None if self.failures is None else self.failures / self.opportunities


class ApplicabilityReview(Contract):
    analyst: Name
    target_domain: Name
    rationale: Name
    scope_rationale: Name
    # Explicitly chosen by the analyst, including when the choice is empty.
    included_effects: tuple[Literal["timing", "recovery", "dependency"], ...]

    @model_validator(mode="after")
    def unique_scope(self):
        if len(set(self.included_effects)) != len(self.included_effects):
            raise ValueError("effects must not repeat")
        return self


@dataclass(frozen=True)
class EvidenceBinding:
    estimate: Estimate
    evidence: tuple[Evidence, ...]


class HumanEvidenceCatalog:
    """Exact filters return candidates; they never authorize domain transfer."""

    def __init__(self, sources, records):
        self.sources = {source.id: source for source in sources}
        self.records = {record.id: record for record in records}
        if len(self.sources) != len(sources) or len(self.records) != len(records):
            raise ValueError("unique source and record identities required")
        if any(record.source_id not in self.sources for record in records):
            raise ValueError("record references an unknown source")

    def get(self, record_id: str) -> HumanErrorRecord:
        try:
            return self.records[record_id]
        except KeyError as error:
            raise ValueError("unknown evidence record: " + record_id) from error

    def search(
        self,
        *,
        kind=None,
        function=None,
        method=None,
        domain=None,
        source_id=None,
        conditions=None,
        text=None,
    ):
        candidates = tuple(self.records.values())
        for field, value in (
            ("kind", kind),
            ("function", function),
            ("method", method),
            ("domain", domain),
            ("source_id", source_id),
        ):
            if value is not None:
                # Catch misspelled filters instead of quietly returning a different population.
                allowed = (
                    set(EvidenceKind.__args__)
                    if field == "kind"
                    else {getattr(row, field) for row in self.records.values()}
                )
                if value not in allowed:
                    raise ValueError("unknown " + field + ": " + str(value))
                candidates = tuple(row for row in candidates if getattr(row, field) == value)
        available = {name for row in candidates for name in row.conditions}
        if not candidates:
            available = {name for row in self.records.values() for name in row.conditions}
        for key in conditions or {}:
            if key not in available:
                raise ValueError("condition is unavailable in the filtered population: " + key)
        candidates = tuple(
            row
            for row in candidates
            if all(
                key in row.conditions
                and type(row.conditions[key]) is type(value)
                and row.conditions[key] == value
                for key, value in (conditions or {}).items()
            )
        )
        if text is not None:
            candidates = tuple(
                row for row in candidates if text.casefold() in (row.label + " " + row.id).casefold()
            )
        return candidates

    def evidence_for(self, record_id):
        row = self.get(record_id)
        source = self.sources[row.source_id]
        return Evidence(
            id="human_data:" + row.id,
            reference=source.url,
            origin="observed"
            if row.kind in {"observed_count", "reported_observed_probability"}
            else "literature",
            applicability=f"{row.domain}; {source.setting}; conditions={json.dumps(row.conditions, sort_keys=True)}",
            version=source.version,
            locator=row.locator,
            limitations=source.limitations + row.limitations,
        )

    def bind(
        self,
        record_id: str,
        event: HumanFailureEvent,
        *,
        review: ApplicabilityReview,
        prior: BetaPrior | None = None,
        selected_value: float | None = None,
    ) -> EvidenceBinding:
        row = self.get(record_id)
        source = self.sources[row.source_id]
        if source.rights.numeric_reuse == "not_cleared":
            raise ValueError("numerical reuse is not cleared")
        if row.kind not in {
            "observed_count",
            "reported_observed_probability",
            "method_probability",
            "method_interval",
        }:
            raise ValueError("a component, multiplier or terminal rule is not a stand-alone HEP")
        if event.includes_timing and "timing" not in review.included_effects:
            raise ValueError("event timing scope is not covered by the review")
        if event.includes_recovery and "recovery" not in review.included_effects:
            raise ValueError("event recovery scope is not covered by the review")
        evidence = self.evidence_for(record_id)
        records = (evidence,)
        if row.kind == "observed_count":
            if prior is None or selected_value is not None:
                raise ValueError(
                    "observed counts require an explicit prior, without a supplied point probability"
                )
            if prior.evidence_id == evidence.id:
                raise ValueError("prior and observations require distinct evidence identities")
            estimate = prior.posterior(
                row.failures,
                row.opportunities,
                event_id=event.id,
                observation_id=evidence.id,
                conditioning=event.conditioning,
            )
            records += (
                Evidence(
                    id=prior.evidence_id,
                    reference="Explicit analyst prior",
                    origin="assumed",
                    applicability=review.rationale,
                    limitations=("Not an independently observed sample.",),
                ),
            )
        else:
            if prior is not None:
                raise ValueError("a method point/range cannot be updated as fabricated Bernoulli counts")
            if row.kind == "method_interval":
                if selected_value is None or not row.lower <= probability(selected_value) <= row.upper:
                    raise ValueError("an interval requires an explicit point within its bounds")
                value = selected_value
            else:
                if selected_value is not None:
                    raise ValueError("supplied point records cannot be silently overridden")
                value = row.value
            estimate = Estimate(
                event_id=event.id,
                method=row.method,
                probability=value,
                conditioning=event.conditioning,
                evidence_ids=(evidence.id,),
                status="method_estimate",
            )
            if row.kind == "reported_observed_probability":
                estimate = estimate.model_copy(
                    update={
                        "status": "research",
                        "trace": {
                            "denominator_available": False,
                            "reported_bounds": [row.lower, row.upper],
                            "reported_bounds_are_not_a_fitted_distribution": True,
                        },
                    }
                )
        trace = estimate.trace | {
            "catalog_record": row.id,
            "catalog_kind": row.kind,
            "source_setting": source.setting,
            "source_domain": row.domain,
            "source_conditions": row.conditions,
            "source_failure_definition": row.failure_definition,
            "source_opportunity_definition": row.opportunity_definition,
            "source_observed_fraction": row.observed_fraction,
            "target_opportunity_definition": event.opportunity_definition,
            "applicability_review": review.model_dump(mode="json"),
            "field_validation_claim": False,
            "license_id": source.rights.license_id,
        }
        status = (
            "research"
            if row.kind == "observed_count" and review.target_domain != row.domain
            else estimate.status
        )
        return EvidenceBinding(
            estimate=estimate.model_copy(
                update={"trace": trace, "status": status, "includes": review.included_effects}
            ),
            evidence=records,
        )

    def estimator(self, record_id: str, *, review: ApplicabilityReview, prior=None, selected_value=None):
        """Register the returned callable after adding its binding's evidence to the task."""

        def evaluate(request):
            return self.bind(
                record_id, request.event, review=review, prior=prior, selected_value=selected_value
            ).estimate

        return evaluate

    def count_summary(self, record_ids, *, disjoint_contexts_rationale: str):
        """Aggregate one released function partition, never unrelated functions or methods."""
        if (
            not disjoint_contexts_rationale.strip()
            or not record_ids
            or len(set(record_ids)) != len(record_ids)
        ):
            raise ValueError("unique selected records and a disjoint-context justification required")
        rows = tuple(self.get(key) for key in record_ids)
        if any(row.kind != "observed_count" for row in rows):
            raise ValueError("only observed count records can be pooled")
        if len({(row.source_id, row.function, row.domain, row.opportunity_definition) for row in rows}) != 1:
            raise ValueError("different source/functions/denominators cannot be pooled")
        if len({canonical_digest(row.conditions) for row in rows}) != len(rows):
            raise ValueError("duplicate context vectors require an explicit source reconciliation")
        failures, opportunities = sum(row.failures for row in rows), sum(row.opportunities for row in rows)
        return {
            "failures": failures,
            "opportunities": opportunities,
            "observed_fraction": failures / opportunities,
            "record_ids": list(record_ids),
            "justification": disjoint_contexts_rationale,
            "independent_trials_verified": False,
            "field_validation_claim": False,
        }


def builtin_evidence_catalog() -> HumanEvidenceCatalog:
    root = files("human_reliability.data")
    return load_evidence_catalog(
        json.loads(root.joinpath("human_evidence_sources.json").read_text(encoding="utf-8")),
        json.loads(root.joinpath("human_error_records.json").read_text(encoding="utf-8")),
    )


def load_evidence_catalog(sources, records):
    """Accept decoded documents or JSON paths to support user-owned evidence catalogs."""

    def document(value):
        return (
            json.loads(Path(value).read_text(encoding="utf-8")) if isinstance(value, (str, Path)) else value
        )

    source_doc, record_doc = document(sources), document(records)
    if source_doc["schema_version"] != "1" or record_doc["schema_version"] != "1":
        raise ValueError("unsupported evidence catalog schema")
    return HumanEvidenceCatalog(
        tuple(HumanEvidenceSource.model_validate_json(json.dumps(row)) for row in source_doc["sources"]),
        tuple(HumanErrorRecord.model_validate_json(json.dumps(row)) for row in record_doc["records"]),
    )


def annual_frequency_from_evidence(
    estimate: Estimate, opportunities_per_year: float, *, opportunity_definition: str, exposure_evidence: str
):
    """A user-supplied exposure converts a probability into a derived expected annual count."""
    rate = nonnegative(opportunities_per_year, "opportunities per year")
    if (
        not exposure_evidence.strip()
        or not opportunity_definition.strip()
        or estimate.trace.get("target_opportunity_definition") != opportunity_definition
    ):
        raise ValueError("documented exposure must match the reviewed target opportunity definition")
    return {
        "annual_frequency_per_year": rate * estimate.probability,
        "probability_per_opportunity": estimate.probability,
        "opportunities_per_year": rate,
        "opportunity_definition": opportunity_definition,
        "exposure_evidence": exposure_evidence,
        "origin": "derived_probability_times_user_exposure",
        "observed_annual_frequency": False,
        "field_validation_claim": False,
    }


def sacada_context_labels(record: HumanErrorRecord):
    """Translate source categories without confusing missing codes and absent binary conditions."""
    if record.source_id != "sacada_2019":
        raise ValueError("SACADA codebook applies only to the pinned SACADA release")
    book = json.loads(
        files("human_reliability.data").joinpath("sacada_codebook.json").read_text(encoding="utf-8")
    )
    fields = book["functions"][record.function]
    return {
        key: {
            "code": value,
            "label": fields[key]["codes"].get(str(value), "Unmapped source category"),
            "missing": value in fields[key]["missing_codes"],
            "source_column": fields[key]["source_column"],
        }
        for key, value in record.conditions.items()
    }
