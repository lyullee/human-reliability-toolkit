"""Auditable task opportunities preserve missing outcomes, recovery and denominator meaning."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .contracts import Contract, Name, Nonnegative
from .evidence_catalog import HumanErrorRecord
from .probability import BetaPrior, nonnegative


class ObservationWindow(Contract):
    id: Name
    source_id: Name
    clock_id: Name
    start_s: Nonnegative
    end_s: Nonnegative
    evidence: Name
    context: dict[str, int | float | str | bool] = {}

    @model_validator(mode="after")
    def interval(self):
        if self.end_s <= self.start_s:
            raise ValueError("observation window must have positive duration")
        return self


class TaskOpportunity(Contract):
    id: Name
    source_event_id: Name
    window_id: Name
    task_id: Name
    event_id: Name
    domain: Name
    failure_definition: Name
    opportunity_definition: Name
    start_s: Nonnegative
    end_s: Nonnegative
    deadline_s: Nonnegative | None = None
    initial_error: bool | None
    final_failure: bool | None
    followup_complete: bool
    context: dict[str, int | float | str | bool] = {}
    group_id: str | None = None
    evidence: Name

    @model_validator(mode="after")
    def interval(self):
        if self.end_s < self.start_s or self.deadline_s is not None and self.deadline_s < self.start_s:
            raise ValueError("invalid task-opportunity interval")
        if self.final_failure is not None and not self.followup_complete:
            raise ValueError("a final outcome requires complete follow-up")
        return self


class ObservedAction(Contract):
    id: Name
    opportunity_id: Name
    step_id: Name
    actor_id: Name
    time_s: Nonnegative
    target: Name
    procedure_version: Name
    result: Literal["correct", "error", "unknown"]
    evidence: Name


class RecoveryAttempt(Contract):
    id: Name
    opportunity_id: Name
    time_s: Nonnegative
    successful: bool | None
    evidence: Name


class ObservationLedger:
    def __init__(self, windows, opportunities, *, actions=(), recoveries=()):
        for rows in (windows, opportunities, actions, recoveries):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("duplicate observation identity")
        self.windows = {r.id: r for r in windows}
        self.opportunities = {r.id: r for r in opportunities}
        self.actions, self.recoveries = tuple(actions), tuple(recoveries)
        natural_keys = set()
        for row in opportunities:
            if row.window_id not in self.windows:
                raise ValueError("opportunity references an unknown window")
            window = self.windows[row.window_id]
            if not window.start_s <= row.start_s <= row.end_s <= window.end_s:
                raise ValueError("opportunity is outside observation coverage")
            key = (window.source_id, row.source_event_id)
            if key in natural_keys:
                raise ValueError("same source event cannot create multiple opportunities")
            natural_keys.add(key)
        for row in (*self.actions, *self.recoveries):
            if row.opportunity_id not in self.opportunities:
                raise ValueError("observation references an unknown opportunity")
            opportunity = self.opportunities[row.opportunity_id]
            if not opportunity.start_s <= row.time_s <= opportunity.end_s:
                raise ValueError("action/recovery outside opportunity follow-up")
        for row in self.recoveries:
            opportunity = self.opportunities[row.opportunity_id]
            if opportunity.initial_error is not True:
                raise ValueError("a recovery attempt needs an observed initial error")
            if row.successful and opportunity.deadline_s is not None and row.time_s > opportunity.deadline_s:
                raise ValueError("recovery after the defined failure deadline cannot be successful")
            if row.successful and opportunity.final_failure is True:
                raise ValueError("successful recovery contradicts the declared final-failure estimand")

    def snapshot(self, event_id, *, estimand: Literal["initial", "final"], window_ids=None, conditions=None):
        if estimand not in {"initial", "final"}:
            raise ValueError("initial or final estimand required")
        selected_windows = set(self.windows) if window_ids is None else set(window_ids)
        if not selected_windows <= set(self.windows) or not selected_windows:
            raise ValueError("known nonempty window selection required")
        windows = [self.windows[key] for key in selected_windows]
        for i, left in enumerate(windows):
            for right in windows[i + 1 :]:
                if (left.source_id, left.clock_id) == (right.source_id, right.clock_id) and max(
                    left.start_s, right.start_s
                ) < min(left.end_s, right.end_s):
                    raise ValueError("overlapping windows require source reconciliation before counting")
        rows = [
            r
            for r in self.opportunities.values()
            if r.event_id == event_id and r.window_id in selected_windows
        ]
        if conditions:
            known = {key for row in rows for key in row.context}
            if set(conditions) - known:
                raise ValueError("unknown context field")
            rows = [
                r
                for r in rows
                if all(
                    k in r.context and type(r.context[k]) is type(v) and r.context[k] == v
                    for k, v in conditions.items()
                )
            ]
        meanings = {(r.domain, r.failure_definition, r.opportunity_definition) for r in rows}
        if not rows or len(meanings) != 1:
            raise ValueError("one nonempty compatible event/denominator population required")
        results, missing = {}, []
        for row in rows:
            value = row.initial_error if estimand == "initial" else row.final_failure
            if estimand == "final" and value is None and row.followup_complete:
                recovery = [r for r in self.recoveries if r.opportunity_id == row.id]
                if any(r.successful is True for r in recovery):
                    value = False
                elif row.initial_error is False:
                    value = False
                elif row.initial_error is True and not any(r.successful is None for r in recovery):
                    value = True
            if value is None:
                missing.append(row.id)
            else:
                results[row.id] = value
        failures, n = sum(results.values()), len(results)
        return {
            "event_id": event_id,
            "estimand": estimand,
            "failures": failures,
            "opportunities": n,
            "eligible_opportunities": len(rows),
            "missing_ids": missing,
            "observed_fraction": failures / n if n else None,
            "counted_ids": list(results),
            "window_ids": sorted(selected_windows),
            "population": next(iter(meanings)),
            "evidence_ids": sorted({r.evidence for r in rows} | {r.evidence for r in windows}),
            "independent_trials_verified": False,
            "missing_at_random_verified": False,
        }

    def annual_demand_exposure(
        self,
        event_id,
        *,
        coverage_review,
        stationarity_review,
        calendar_seconds_per_year=365.25 * 86400,
        **selection,
    ):
        """Annualize observed demands, including demands whose human outcome is missing."""
        year = nonnegative(calendar_seconds_per_year)
        if year <= 0 or not coverage_review.strip() or not stationarity_review.strip():
            raise ValueError("positive calendar scale, coverage and stationarity reviews required")
        snapshot = self.snapshot(event_id, estimand="initial", **selection)
        windows = [self.windows[key] for key in snapshot["window_ids"]]
        if len({(w.source_id, w.clock_id) for w in windows}) != 1:
            raise ValueError("annualization needs one source/clock exposure population")
        for key, value in (selection.get("conditions") or {}).items():
            if any(
                key not in w.context or type(w.context[key]) is not type(value) or w.context[key] != value
                for w in windows
            ):
                raise ValueError("conditional exposure needs windows dedicated to that context")
        duration = sum(w.end_s - w.start_s for w in windows)
        return {
            "demands_per_year": snapshot["eligible_opportunities"] * year / duration,
            "observed_demands": snapshot["eligible_opportunities"],
            "observed_duration_s": duration,
            "opportunity_definition": snapshot["population"][2],
            "calendar_seconds_per_year": year,
            "coverage_review": coverage_review,
            "stationarity_review": stationarity_review,
            "observed_annual_frequency_series": False,
            "origin": "annualized_observed_window_demands",
        }

    def posterior(
        self,
        event_id,
        *,
        estimand,
        prior: BetaPrior,
        observation_id,
        conditioning,
        independence_review,
        missingness_review=None,
        **selection,
    ):
        snapshot = self.snapshot(event_id, estimand=estimand, **selection)
        if not independence_review.strip() or not snapshot["opportunities"]:
            raise ValueError("nonempty observed outcomes and an independence review required")
        if snapshot["missing_ids"] and not (missingness_review or "").strip():
            raise ValueError("missing outcomes require a missingness/selection review")
        estimate = prior.posterior(
            snapshot["failures"],
            snapshot["opportunities"],
            event_id=event_id,
            observation_id=observation_id,
            conditioning=conditioning,
        )
        return estimate.model_copy(
            update={
                "trace": estimate.trace
                | {
                    "observation_snapshot": snapshot,
                    "independence_review": independence_review,
                    "missingness_review": missingness_review,
                }
            }
        )

    def catalog_record(self, event_id, *, record_id, source_id, function, estimand, locator, **selection):
        snapshot = self.snapshot(event_id, estimand=estimand, **selection)
        if not snapshot["opportunities"]:
            raise ValueError("no observed denominator to export")
        domain, failure, opportunity = snapshot["population"]
        return HumanErrorRecord(
            id=record_id,
            source_id=source_id,
            kind="observed_count",
            method="observed_counts",
            function=function,
            label=event_id + ":" + estimand,
            domain=domain,
            locator=locator,
            quantity="probability",
            opportunity_definition=opportunity,
            failure_definition=failure + ":" + estimand,
            conditions=selection.get("conditions") or {},
            failures=snapshot["failures"],
            opportunities=snapshot["opportunities"],
            basis="operational_record",
            limitations=("Complete-case count; inspect missingness and within-group dependence.",),
        )
