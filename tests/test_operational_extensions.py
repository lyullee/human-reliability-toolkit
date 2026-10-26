from datetime import date
import json

import pytest
from scipy.stats import beta

from human_reliability.actions import Command, ProcessState, StatePredicate, StateValue
from human_reliability.communication import Handover, Message, MessageLedger, WorkControl, WorkPermit
from human_reliability.contracts import Evidence, Task, TaskStep, canonical_digest
from human_reliability.observations import (
    ObservationLedger,
    ObservationWindow,
    RecoveryAttempt,
    TaskOpportunity,
)
from human_reliability.probability import BetaPrior
from human_reliability.calibration import (
    BetaHyperPoint,
    BinomialGroup,
    ExpertJudgment,
    expert_calibration_weights,
    fit_elicited_beta,
    fit_partial_pooling,
    heldout_binomial_scores,
    posterior_predictive_check,
    sample_expert_mixture,
    transfer_sensitivity,
)
from human_reliability.cognition import BeliefState, Cue, CueStore, PollChannel, monitor_cues
from human_reliability.assurance import (
    ArtifactFingerprint,
    Assumption,
    AssuranceLifecycle,
    IncidentLesson,
    TraceStep,
    import_task_csv,
    procedure_conformance,
)
from human_reliability.safety_case import Claim, SafetyCase


def test_message_receipt_understanding_confirmation_and_expiry():
    ledger = MessageLedger()
    command = Command(target="v1", verb="position", value=0.0)
    ledger.send(
        Message(
            id="m",
            sender="control",
            receiver="field",
            command=command,
            sent_s=0.0,
            expires_s=10.0,
            evidence="e",
        )
    )
    assert not ledger.receive("m", "other", 1.0)
    assert ledger.receive("m", "field", 2.0)
    assert ledger.authorized_command("m", "field", 2.0) is None
    assert not ledger.interpret("m", "field", command.model_copy(update={"target": "v2"}), 3.0)
    assert not ledger.confirm("m", "control", command, 4.0)
    assert ledger.interpret("m", "field", command, 5.0)
    assert ledger.confirm("m", "control", command, 6.0)
    assert ledger.authorized_command("m", "field", 7.0) == command
    assert ledger.authorized_command("m", "field", 11.0) is None
    with pytest.raises(ValueError, match="chronological"):
        ledger.confirm("m", "control", command, 1.0)


def test_handover_uses_content_version_and_freshness():
    state = ProcessState(revision="r1", values={"isolated": StateValue(value=True)})
    digest = canonical_digest(state.model_dump(mode="json")["values"])
    handover = Handover(
        id="h",
        sender="day",
        receiver="night",
        procedure_version="1",
        state_revision="r1",
        facts_digest=digest,
        created_s=1.0,
        expires_s=10.0,
        evidence="e",
    )
    assert handover.accept(
        receiver="night", time_s=5.0, state=state, procedure_version="1", acknowledged_digest=digest
    )["accepted"]
    assert not handover.accept(
        receiver="night",
        time_s=5.0,
        state=state.model_copy(update={"revision": "r2"}),
        procedure_version="1",
        acknowledged_digest=digest,
    )["accepted"]
    assert not handover.accept(
        receiver="night", time_s=11.0, state=state, procedure_version="1", acknowledged_digest=digest
    )["accepted"]


def permit(identity="p", activity="entry", **changes):
    return WorkPermit(
        **(
            dict(
                id=identity,
                revision="1",
                area="a",
                activity=activity,
                valid_from_s=0.0,
                valid_until_s=20.0,
                conditions=(StatePredicate(key="isolated", value=True),),
                lock_owners=("alice", "bob"),
                required_restorations=("trip",),
                evidence="Authored test",
            )
            | changes
        )
    )


def test_personal_locks_restoration_and_permit_lifecycle():
    control = WorkControl()
    control.issue(permit(), time_s=0.0)
    safe = ProcessState(revision="r", values={"isolated": StateValue(value=True)})
    assert not control.authorize("p", safe, time_s=1.0, evidence="review")["authorized"]
    control.lock("p", "alice", time_s=2.0, evidence="e")
    control.lock("p", "bob", time_s=3.0, evidence="e")
    assert control.authorize("p", safe, time_s=4.0, evidence="review")["authorized"]
    with pytest.raises(ValueError, match="own"):
        control.unlock("p", "alice", actor="bob", time_s=5.0, evidence="e")
    with pytest.raises(ValueError, match="closeout"):
        control.close("p", time_s=5.0, evidence="e")
    control.unlock("p", "alice", actor="alice", time_s=6.0, evidence="e")
    assert control.status["p"] == "suspended"
    control.unlock("p", "bob", actor="bob", time_s=7.0, evidence="e")
    control.confirm_restoration("p", "trip", time_s=8.0, evidence="Observed restoration")
    control.close("p", time_s=9.0, evidence="Closeout review")
    assert control.status["p"] == "closed"


def test_conflicting_work_unknown_state_and_renewal():
    control = WorkControl(incompatible_activities=(("entry", "energize"),))
    safe = ProcessState(revision="r", values={"isolated": StateValue(value=True)})
    first, second = permit(lock_owners=()), permit("q", "energize", lock_owners=())
    control.issue(first, time_s=0.0)
    control.issue(second, time_s=0.0)
    assert control.authorize("p", safe, time_s=1.0, evidence="review")["authorized"]
    assert not control.authorize("q", safe, time_s=2.0, evidence="review")["authorized"]
    control.suspend("p", time_s=3.0, evidence="Stop work")
    assert not control.authorize("q", ProcessState(revision="r", values={}), time_s=4.0, evidence="review")[
        "authorized"
    ]
    renewed = first.model_copy(update={"revision": "2", "valid_until_s": 30.0})
    control.renew(renewed, time_s=5.0)
    assert control.status["p"] == "issued"


def window(identity="w", **changes):
    return ObservationWindow(
        **(
            dict(id=identity, source_id="authored", clock_id="clock", start_s=0.0, end_s=10.0, evidence="e")
            | changes
        )
    )


def opportunity(identity, error, final=None, **changes):
    return TaskOpportunity(
        **(
            dict(
                id=identity,
                source_event_id=identity,
                window_id="w",
                task_id="t",
                event_id="failure",
                domain="authored",
                failure_definition="Initial action error",
                opportunity_definition="One assessed demand",
                start_s=1.0,
                end_s=9.0,
                deadline_s=8.0,
                initial_error=error,
                final_failure=final,
                followup_complete=True,
                evidence="e",
            )
            | changes
        )
    )


def test_initial_recovered_final_and_missing_counts_are_distinct():
    rows = (
        opportunity("a", True),
        opportunity("b", True),
        opportunity("c", False),
        opportunity("d", None, followup_complete=False),
    )
    ledger = ObservationLedger(
        (window(),),
        rows,
        recoveries=(RecoveryAttempt(id="r", opportunity_id="a", time_s=5.0, successful=True, evidence="e"),),
    )
    initial, final = (
        ledger.snapshot("failure", estimand="initial"),
        ledger.snapshot("failure", estimand="final"),
    )
    assert (initial["failures"], initial["opportunities"]) == (2, 3)
    assert (final["failures"], final["opportunities"]) == (1, 3)
    assert final["missing_ids"] == ["d"]
    with pytest.raises(ValueError, match="missingness"):
        ledger.posterior(
            "failure",
            estimand="final",
            prior=BetaPrior(alpha=1.0, beta=1.0, evidence_id="prior"),
            observation_id="obs",
            conditioning="demand",
            independence_review="Authored independent episodes",
        )
    estimate = ledger.posterior(
        "failure",
        estimand="final",
        prior=BetaPrior(alpha=1.0, beta=1.0, evidence_id="prior"),
        observation_id="obs",
        conditioning="demand",
        independence_review="Authored independent episodes",
        missingness_review="Known incomplete episode excluded",
    )
    assert estimate.probability == pytest.approx(2 / 5)
    assert (
        ledger.catalog_record(
            "failure",
            record_id="r",
            source_id="s",
            function="action",
            estimand="final",
            locator="Authored ledger",
        ).failures
        == 1
    )


def test_duplicate_exposure_overlap_and_late_recovery_rejected():
    with pytest.raises(ValueError, match="same source"):
        ObservationLedger((window(),), (opportunity("a", True), opportunity("b", True, source_event_id="a")))
    ledger = ObservationLedger((window(), window("w2", start_s=5.0, end_s=15.0)), (opportunity("a", False),))
    with pytest.raises(ValueError, match="overlapping"):
        ledger.snapshot("failure", estimand="initial")
    with pytest.raises(ValueError, match="deadline"):
        ObservationLedger(
            (window(),),
            (opportunity("a", True),),
            recoveries=(
                RecoveryAttempt(id="r", opportunity_id="a", time_s=9.0, successful=True, evidence="e"),
            ),
        )


def group(identity, k, n, **changes):
    return BinomialGroup(
        **(
            dict(
                id=identity,
                group_id=identity,
                failures=k,
                opportunities=n,
                opportunity_definition="One assessed demand",
                domain="authored",
                evidence="e",
            )
            | changes
        )
    )


def test_finite_hyperprior_matches_conjugate_limit():
    posterior = fit_partial_pooling(
        (group("a", 1, 10),),
        (BetaHyperPoint(alpha=2.0, beta=3.0, prior_weight=1.0),),
        exchangeability_review="One authored group",
    )
    summary = posterior.summary("a")
    assert summary["posterior_mean"] == pytest.approx(3 / 15)
    assert [summary["lower"], summary["upper"]] == pytest.approx(beta.ppf([0.025, 0.975], 3, 12))
    assert (
        posterior.sample("a", size=100, seed=4).tolist() == posterior.sample("a", size=100, seed=4).tolist()
    )
    assert posterior_predictive_check(posterior, "a", size=100, seed=5)["independent_validation"] is False


def test_partial_pooling_grid_and_group_boundaries():
    groups = (group("a", 0, 2), group("b", 8, 100))
    grid = (
        BetaHyperPoint(alpha=0.2, beta=2.0, prior_weight=1.0),
        BetaHyperPoint(alpha=1.0, beta=9.0, prior_weight=1.0),
    )
    model = fit_partial_pooling(groups, grid, exchangeability_review="Authored shared population")
    assert 0 < model.summary("a")["posterior_mean"] < 1
    sensitivity = transfer_sensitivity(groups, {"assumed": grid}, exchangeability_review="Assumed transfer")
    assert sensitivity["assumed"]["a"]["posterior_mean"] == model.summary("a")["posterior_mean"]
    assert sensitivity["assumed"]["a"]["exchangeability_review"] == "Assumed transfer"
    with pytest.raises(ValueError, match="compatible"):
        fit_partial_pooling(
            (groups[0], group("other", 1, 10, domain="other")), grid, exchangeability_review="test"
        )
    with pytest.raises(ValueError, match="unique"):
        fit_partial_pooling(
            (groups[0], group("other", 1, 10, group_id="a")), grid, exchangeability_review="test"
        )


def test_heldout_aggregate_brier_and_leakage():
    train, test = (group("train", 1, 10),), (group("test", 1, 4),)
    result = heldout_binomial_scores(train, test, {"test": 0.25}, split_review="Disjoint authored episodes")
    assert result["brier"] == pytest.approx(0.1875)
    assert heldout_binomial_scores(train, test, {"test": 0.0}, split_review="test")["impossible_observation"]
    with pytest.raises(ValueError, match="overlap"):
        heldout_binomial_scores(
            train, (group("test", 1, 4, group_id="train"),), {"test": 0.25}, split_review="bad split"
        )


def test_elicitation_fitting_calibration_and_mixture():
    quantiles = tuple(float(x) for x in beta.ppf([0.1, 0.5, 0.9], 2, 18))
    judgment = ExpertJudgment(
        expert_id="a",
        quantile_probabilities=(0.1, 0.5, 0.9),
        quantile_values=quantiles,
        evidence="Authored expert distribution",
    )
    fit = fit_elicited_beta(judgment, maximum_quantile_error=0.001)
    assert fit["alpha"] == pytest.approx(2, rel=0.001)
    assert fit["beta"] == pytest.approx(18, rel=0.001)
    result = expert_calibration_weights(
        {"a": {"seed": 0.9}, "b": {"seed": 0.1}},
        {"seed": True},
        temperature=0.1,
        seed_evidence="Authored known seed",
    )
    assert result["weights"]["a"] > result["weights"]["b"]
    draws = sample_expert_mixture((fit,), {"a": 1.0}, size=20, seed=1)
    assert all(0 < v < 1 for v in draws)


def cue(identity="c", **changes):
    return Cue(
        **(
            dict(
                id=identity,
                evidence_id=identity,
                key="alarm",
                observation=StateValue(value=True),
                measured_s=0.0,
                available_s=2.0,
                expires_s=10.0,
                visible_to=("operator",),
                likelihoods={"fault": 0.9, "healthy": 0.1},
            )
            | changes
        )
    )


def test_role_visible_delayed_cues_and_bayesian_diagnosis():
    store = CueStore((cue(),))
    assert store.latest("alarm", "operator", 1.0) is None
    assert store.latest("alarm", "other", 3.0) is None
    belief = BeliefState({"fault": 0.5, "healthy": 0.5}, evidence="Authored equal prior")
    assert belief.choose({"fault": "stop", "healthy": "continue"}, minimum_posterior=0.8)["action_id"] is None
    after = belief.update(cue(), actor="operator", time_s=3.0, independence_evidence="One authored cue")
    assert after["fault"] == pytest.approx(0.9)
    assert (
        belief.choose({"fault": "stop", "healthy": "continue"}, minimum_posterior=0.8)["action_id"] == "stop"
    )
    with pytest.raises(ValueError, match="new observation"):
        belief.update(cue(), actor="operator", time_s=4.0, independence_evidence="test")


def test_monitoring_dwell_capacity_and_budget():
    store = CueStore((cue(available_s=0.0),))
    report = monitor_cues(
        store,
        "operator",
        (
            PollChannel(key="alarm", interval_s=1.0, dwell_s=1.0),
            PollChannel(key="other", interval_s=1.0, dwell_s=1.0),
        ),
        horizon_s=4.0,
    )
    assert [p["observation_s"] for p in report["polls"]] == [1.0, 2.0, 3.0, 4.0]
    assert report["polls"][1]["cue_id"] is None
    with pytest.raises(ValueError, match="budget"):
        monitor_cues(
            store,
            "operator",
            (PollChannel(key="alarm", interval_s=1.0, dwell_s=0.0),),
            horizon_s=10.0,
            maximum_polls=1,
        )


def task():
    a = TaskStep(
        id="a", action="Prepare", kind="manipulate", target="v1", actor="op", cue="start", completion="done"
    )
    b = a.model_copy(update={"id": "b", "kind": "restore", "predecessors": ("a",)})
    return Task(
        id="t",
        title="Authored",
        procedure_version="2",
        steps=(a, b),
        evidence=(Evidence(id="e", reference="Authored", origin="assumed", applicability="test"),),
    )


def test_conformance_missingness_order_versions_and_restoration(tmp_path):
    trace = (
        TraceStep(
            id="x",
            step_id="b",
            actor="op",
            target="v2",
            start_s=0.0,
            completion_s=1.0,
            procedure_version="1",
            outcome="completed",
            evidence="e",
        ),
    )
    result = procedure_conformance(task(), trace, complete_observation=True)
    assert {r["kind"] for r in result["findings"]} >= {
        "wrong_target",
        "stale_procedure",
        "precedence_not_demonstrated",
        "omission",
    }
    missing = procedure_conformance(task(), (), complete_observation=False)
    assert all(r["kind"] == "not_observed" for r in missing["findings"])
    path = tmp_path / "task.csv"
    path.write_text(
        "id,action,kind,target,actor,cue,completion,predecessors\na,Prepare,manipulate,valve,op,start,done,\nb,Restore,restore,valve,op,ready,done,a\n",
        encoding="utf-8",
    )
    imported = import_task_csv(
        path,
        task_id="t",
        title="Authored",
        procedure_version="2",
        evidence=task().evidence,
        aliases={"valve": "v1"},
    )
    assert imported.steps[1].predecessors == ("a",) and imported.steps[0].target == "v1"


def test_lifecycle_assumptions_hashes_claims_and_incident_lessons():
    assumption = Assumption(
        id="condition",
        statement="Authored assumption",
        evidence="e",
        review_status="approved",
        expires_on=date(2027, 1, 1),
    )
    artifact = ArtifactFingerprint.of("procedure", {"version": 2}, dependencies=("condition",))
    case = SafetyCase((Claim("safe", "Authored claim", ("procedure",)),), {"procedure": artifact.digest})
    lifecycle = AssuranceLifecycle((artifact,), (assumption,), safety_case=case)
    assert lifecycle.review((artifact,), as_of=date(2026, 10, 26))["status"] == "unchanged_qualified_scope"
    expired = lifecycle.review((artifact,), as_of=date(2028, 1, 1))
    assert "safe" in expired["affected_claims"] and "procedure" in expired["affected_artifacts"]
    lesson = IncidentLesson(
        id="lesson",
        statement="Observed counterexample",
        affected_ids=("condition",),
        evidence="e",
        recommendation="Review the procedure",
    )
    assert (
        lifecycle.review((artifact,), as_of=date(2026, 10, 26), lessons=(lesson,))["status"]
        == "review_required"
    )
    assert json.loads(lifecycle.baseline_json())["artifacts"][0]["id"] == "procedure"
    restored = AssuranceLifecycle.from_json(lifecycle.baseline_json())
    assert restored.review((artifact,), as_of=date(2028, 1, 1)) == expired


def test_annualized_demands_include_missing_outcomes_and_require_context_time():
    ledger = ObservationLedger(
        (window(),), (opportunity("a", True), opportunity("b", None, followup_complete=False))
    )
    rate = ledger.annual_demand_exposure(
        "failure",
        coverage_review="All demands logged",
        stationarity_review="Authored stationary window",
        calendar_seconds_per_year=100.0,
    )
    assert rate["demands_per_year"] == 20.0
    assert not rate["observed_annual_frequency_series"]
    contextual = ObservationLedger((window(),), (opportunity("a", False, context={"mode": "test"}),))
    with pytest.raises(ValueError, match="dedicated"):
        contextual.annual_demand_exposure(
            "failure", coverage_review="test", stationarity_review="test", conditions={"mode": "test"}
        )
