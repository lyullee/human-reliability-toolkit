"""Original, offline collection forms reconcile eligible demands before outcome counting."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, get_args, get_origin

from pydantic import model_validator

from .contracts import Contract, Name, Nonnegative, Probability, canonical_digest
from .observations import ObservationLedger, ObservationWindow, RecoveryAttempt, TaskOpportunity


class CollectionProtocol(Contract):
    id: Name
    version: Name
    source_id: Name
    domain: Name
    task_id: Name
    event_id: Name
    failure_definition: Name
    opportunity_definition: Name
    conditioning: Name
    setting: Literal["natural_field", "simulator", "induced", "synthetic"]
    sampling: Literal["window_census"]
    clock_id: Name
    clock_origin_and_unit: Name
    frozen_at_s: Nonnegative
    coverage_review: Name
    registry_review: Name
    adjudication_rule: Name
    collection_authorization: Name
    data_license: Name
    license_evidence: Name
    public_release_authorization: str = ""


class CoverageWindow(Contract):
    id: Name
    start_s: Nonnegative
    end_s: Nonnegative
    coverage_complete: bool
    expected_register_rows: int
    reconciliation_evidence: Name

    @model_validator(mode="after")
    def valid(self):
        if self.end_s <= self.start_s or self.expected_register_rows < 0:
            raise ValueError("positive window duration and nonnegative register count required")
        return self


class RegisteredDemand(Contract):
    id: Name
    source_event_id: Name
    window_id: Name
    start_s: Nonnegative
    end_s: Nonnegative
    deadline_s: Nonnegative | None
    group_id: Name
    disposition: Literal["eligible", "withdrawn_before_trigger", "duplicate_record"]
    disposition_evidence: Name
    duplicate_of: str = ""
    withdrawn_at_s: Nonnegative | None = None
    context: dict[str, int | float | str | bool] = {}
    context_evidence: str = ""

    @model_validator(mode="after")
    def context_provenance(self):
        if self.context and not self.context_evidence.strip():
            raise ValueError("demand context requires a provenance reference")
        return self


class CodedOutcome(Contract):
    demand_id: Name
    initial_error: bool | None
    final_failure: bool | None
    followup_complete: bool
    endpoint_adjudicated: bool
    coder_id: Name
    adjudicator_id: Name
    evidence: Name

    @model_validator(mode="after")
    def valid(self):
        if not self.endpoint_adjudicated and (self.initial_error is not None or self.final_failure is not None):
            raise ValueError("unresolved human attribution must retain unknown human outcomes")
        if self.final_failure is None and self.followup_complete:
            raise ValueError("unknown final outcome requires incomplete follow-up; inference is disabled")
        if self.final_failure is not None and not self.followup_complete:
            raise ValueError("known final outcome needs complete follow-up")
        if self.coder_id == self.adjudicator_id:
            raise ValueError("distinct coding and adjudication identities required")
        return self


class Prediction(Contract):
    demand_id: Name
    model_id: Name
    probability: Probability
    issued_s: Nonnegative


TABLES = {
    "windows.csv": CoverageWindow,
    "demands.csv": RegisteredDemand,
    "outcomes.csv": CodedOutcome,
    "recoveries.csv": RecoveryAttempt,
    "predictions.csv": Prediction,
}


def _read_table(path, model):
    """CSV has explicit lexical rules; empty nullable cells alone mean unknown."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(model.model_fields):
            raise ValueError(f"exact ordered columns required for {Path(path).name}")
        rows = []
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("ragged row")
                parsed = {}
                for key, value in row.items():
                    field = model.model_fields[key]
                    annotation = str(field.annotation)
                    if value == "" and type(None) in get_args(field.annotation):
                        parsed[key] = None
                    elif get_origin(field.annotation) is dict:
                        parsed[key] = json.loads(value)
                    elif "bool" in annotation:
                        if value not in {"true", "false"}:
                            raise ValueError("boolean cells must be true, false, or nullable blank")
                        parsed[key] = value == "true"
                    elif "float" in annotation:
                        parsed[key] = float(value)
                    elif field.annotation is int:
                        if not value.isdecimal():
                            raise ValueError("integer cell required")
                        parsed[key] = int(value)
                    else:
                        parsed[key] = value
                rows.append(model.model_validate(parsed))
            except (ValueError, TypeError) as error:
                raise ValueError(f"{Path(path).name}:{line}: {error}") from error
    return tuple(rows)


def _unique(rows, key, label):
    values = [key(row) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError("duplicate " + label)


@dataclass(frozen=True)
class CollectionBundle:
    protocol: CollectionProtocol
    windows: tuple[CoverageWindow, ...]
    demands: tuple[RegisteredDemand, ...]
    outcomes: tuple[CodedOutcome, ...]
    recoveries: tuple[RecoveryAttempt, ...] = ()
    predictions: tuple[Prediction, ...] = ()

    def ledger(self):
        """Preserve unobserved eligible demands, including wholly unrecorded outcomes."""
        CollectionProtocol.model_validate(self.protocol.model_dump())
        for model, rows in zip(TABLES.values(),
                               (self.windows, self.demands, self.outcomes, self.recoveries, self.predictions)):
            for row in rows:
                model.model_validate(row.model_dump())
        _unique(self.windows, lambda r: r.id, "window")
        _unique(self.demands, lambda r: r.id, "demand")
        _unique(self.outcomes, lambda r: r.demand_id, "outcome")
        _unique(self.predictions, lambda r: (r.demand_id, r.model_id), "prediction")
        windows = {w.id: w for w in self.windows}
        demands = {d.id: d for d in self.demands}
        eligible = {d.id: d for d in self.demands if d.disposition == "eligible"}
        outcomes = {r.demand_id: r for r in self.outcomes}
        if not windows or not eligible:
            raise ValueError("nonempty windows and eligible demands required")
        if set(outcomes) - set(eligible) or any(p.demand_id not in eligible for p in self.predictions):
            raise ValueError("outcomes/predictions require eligible registered demands")
        natural_keys = set()
        for demand in self.demands:
            if demand.window_id not in windows:
                raise ValueError("unknown demand window")
            w = windows[demand.window_id]
            if not w.start_s <= demand.start_s <= demand.end_s <= w.end_s:
                raise ValueError("demand outside window")
            if demand.deadline_s is not None and not demand.start_s <= demand.deadline_s <= demand.end_s:
                raise ValueError("deadline must lie inside documented follow-up")
            if self.protocol.frozen_at_s >= demand.start_s:
                raise ValueError("protocol must precede every registered demand")
            if demand.disposition == "withdrawn_before_trigger":
                if demand.withdrawn_at_s is None or demand.withdrawn_at_s >= demand.start_s:
                    raise ValueError("withdrawal must be evidenced before the demand trigger")
            elif demand.withdrawn_at_s is not None:
                raise ValueError("only pretrigger withdrawals may declare withdrawn_at_s")
            if demand.disposition == "duplicate_record":
                original = demands.get(demand.duplicate_of)
                if original is None or original.disposition != "eligible" or (
                    original.source_event_id, original.window_id, original.start_s, original.end_s,
                    original.deadline_s, original.group_id
                ) != (demand.source_event_id, demand.window_id, demand.start_s, demand.end_s,
                      demand.deadline_s, demand.group_id):
                    raise ValueError("duplicate must point to the same retained eligible demand")
                if (original.context, original.context_evidence) != (demand.context, demand.context_evidence):
                    raise ValueError("duplicate cannot change the retained demand context")
            else:
                key = demand.source_event_id
                if key in natural_keys:
                    raise ValueError("unreconciled duplicate source event")
                natural_keys.add(key)
                if demand.duplicate_of:
                    raise ValueError("only duplicate records may declare duplicate_of")
        p = self.protocol
        ledger_windows = [ObservationWindow(
            id=w.id, source_id=p.source_id, clock_id=p.clock_id, start_s=w.start_s,
            end_s=w.end_s, evidence=w.reconciliation_evidence,
        ) for w in self.windows]
        opportunities = []
        for d in eligible.values():
            outcome = outcomes.get(d.id)
            opportunities.append(TaskOpportunity(
                id=d.id, source_event_id=d.source_event_id, window_id=d.window_id, task_id=p.task_id,
                event_id=p.event_id, domain=p.domain, failure_definition=p.failure_definition,
                opportunity_definition=p.opportunity_definition, start_s=d.start_s, end_s=d.end_s,
                deadline_s=d.deadline_s, initial_error=outcome.initial_error if outcome else None,
                final_failure=outcome.final_failure if outcome else None,
                followup_complete=outcome.followup_complete if outcome else False,
                group_id=d.group_id, evidence=outcome.evidence if outcome else d.disposition_evidence,
                context=d.context,
            ))
        ledger = ObservationLedger(ledger_windows, opportunities, recoveries=self.recoveries)
        # Also reject overlapping census windows before any HEP or metric is exposed.
        ledger.snapshot(p.event_id, estimand="initial")
        return ledger

    def audit(self):
        ledger = self.ledger()
        reasons = []
        for window in self.windows:
            actual = sum(d.window_id == window.id for d in self.demands)
            if actual != window.expected_register_rows:
                reasons.append(f"register count mismatch: {window.id}")
            if not window.coverage_complete:
                reasons.append(f"incomplete census coverage: {window.id}")
        counts = {}
        for estimand in ("initial", "final"):
            snapshot = ledger.snapshot(self.protocol.event_id, estimand=estimand)
            k, n = snapshot["failures"], snapshot["eligible_opportunities"]
            missing = len(snapshot["missing_ids"])
            counts[estimand] = snapshot | {"missingness_bounds": [k / n, (k + missing) / n]}
        return {
            "protocol_digest": canonical_digest(self.protocol), "setting": self.protocol.setting,
            "collection_digest": canonical_digest({
                "protocol": self.protocol.model_dump(mode="json"),
                "tables": {name: [r.model_dump(mode="json") for r in rows]
                           for name, rows in zip(TABLES, (self.windows, self.demands, self.outcomes,
                                                         self.recoveries, self.predictions))},
            }),
            "registered_rows": len(self.demands),
            "excluded_rows": len(self.demands) - len(ledger.opportunities),
            "denominator_reconciled": not reasons, "blocking_reasons": reasons, "counts": counts,
            "data_license": self.protocol.data_license,
            "public_release_authorized": bool(self.protocol.public_release_authorization.strip()),
            "industrial_hep_validated": False,
        }

    def require_reconciled(self):
        audit = self.audit()
        if not audit["denominator_reconciled"]:
            raise ValueError("unqualified denominator: " + "; ".join(audit["blocking_reasons"]))
        return audit

    def hep(self, *, estimand, prior, independence_review, missingness_review=None, **selection):
        """Reviewed complete-case posterior; unknown outcomes never become successes."""
        audit = self.require_reconciled()
        estimate = self.ledger().posterior(
            self.protocol.event_id, estimand=estimand, prior=prior,
            observation_id=self.protocol.id + ":" + audit["collection_digest"],
            conditioning=self.protocol.conditioning, independence_review=independence_review,
            missingness_review=missingness_review, **selection,
        )
        return estimate.model_copy(update={
            "status": "empirical" if self.protocol.setting == "natural_field" else "research",
            "trace": estimate.trace | {"collection_audit": audit, "source_id": self.protocol.source_id,
                                       "setting": self.protocol.setting},
        })


def load_collection(path) -> CollectionBundle:
    path = Path(path)
    protocol = CollectionProtocol.model_validate_json((path / "protocol.json").read_text(encoding="utf-8"))
    tables = [_read_table(path / name, model) for name, model in TABLES.items()]
    bundle = CollectionBundle(protocol, *tables)
    bundle.ledger()
    return bundle


def write_collection_kit(path):
    """Create blank original forms; refuse to overwrite any existing directory."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    protocol = {key: "" for key in CollectionProtocol.model_fields}
    protocol.update(version="1", setting="natural_field", sampling="window_census",
                    frozen_at_s=0, data_license="internal_only")
    (path / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    (path / "protocol.schema.json").write_text(
        json.dumps(CollectionProtocol.model_json_schema(), indent=2), encoding="utf-8"
    )
    schemas = {}
    for name, model in TABLES.items():
        with (path / name).open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(model.model_fields)
        schemas[name] = model.model_json_schema()
    (path / "tables.schema.json").write_text(json.dumps(schemas, indent=2), encoding="utf-8")
    from .opportunity_validation import ValidationPlan

    plan = {key: "" for key in ValidationPlan.model_fields}
    plan.update(estimand="final", evaluation_window_ids=[], training_demand_ids=[], training_group_ids=[],
                frozen_at_s=0)
    (path / "validation-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (path / "validation-plan.schema.json").write_text(
        json.dumps(ValidationPlan.model_json_schema(), indent=2), encoding="utf-8"
    )
    (path / "README.txt").write_text(
        "Original blank field collection kit. No observations are supplied.\n"
        "Complete and freeze protocol.json before observation. Use UTF-8 CSV; booleans are true/false, "
        "nullable blanks are unknown. Record ALL eligible demands independently of outcomes.\n"
        "Keep private records outside Git. Internal collection authorization is not a redistribution license.\n"
        "Full manual: https://github.com/lyullee/human-reliability-toolkit/blob/main/docs/FIELD_COLLECTION.md\n",
        encoding="utf-8",
    )
    return path
