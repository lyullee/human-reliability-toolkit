"""Original end-to-end demonstrations of the twelve configurable research extensions."""

from datetime import date
from importlib.resources import files
import json
from pathlib import Path

from scipy.stats import beta

from human_reliability import (
    ApplicabilityReview,
    BetaPrior,
    Command,
    EquipmentCapability,
    ExecutableAction,
    HumanFailureEvent,
    ProcessState,
    StatePredicate,
    StateValue,
    builtin_evidence_catalog,
)
from human_reliability.actions import Permissive, error_variants
from human_reliability.assurance import (
    ArtifactFingerprint,
    Assumption,
    AssuranceLifecycle,
    TraceStep,
    procedure_conformance,
)
from human_reliability.calibration import (
    BetaHyperPoint,
    BinomialGroup,
    ExpertJudgment,
    expert_calibration_weights,
    fit_elicited_beta,
    fit_partial_pooling,
    heldout_binomial_scores,
    posterior_predictive_check,
)
from human_reliability.causal import CausalGate, CausalGraph, CausalLeaf
from human_reliability.cognition import BeliefState, Cue, CueStore, PollChannel, monitor_cues
from human_reliability.communication import Message, MessageLedger, WorkControl, WorkPermit
from human_reliability.contracts import Evidence, Task, TaskStep
from human_reliability.dynamics import RuntimeJob, StateProcess, run_coupled_episode
from human_reliability.interventions import CaseChange, Intervention, compare_intervention, risk_importance
from human_reliability.method_workflows import MethodWorkflowCase, run_method_workflow
from human_reliability.observations import (
    ObservationLedger,
    ObservationWindow,
    RecoveryAttempt,
    TaskOpportunity,
)
from human_reliability.risk import (
    ConsequenceSpec,
    InitiatingFrequency,
    RiskBranch,
    RiskCase,
    RiskEngine,
    RiskScenario,
)
from human_reliability.safety_case import Claim, SafetyCase
from human_reliability.verification import (
    DiscreteTimedNet,
    TimedTransition,
    compile_task_net,
    verify_progress,
)
from human_reliability.workflow import Transition


def evidence_risk(destination):
    event = HumanFailureEvent(
        id="action_error",
        task_id="illustration",
        step_ids=("operate",),
        role="initiating",
        failure_definition="Illustrative task error; simulator transfer remains unqualified",
        opportunity_definition="One illustrative work demand",
        conditioning="One illustrative work demand",
    )
    binding = builtin_evidence_catalog().bind(
        "sacada.action.r0003",
        event,
        prior=BetaPrior(alpha=0.5, beta=0.5, evidence_id="explicit_demo_prior"),
        review=ApplicabilityReview(
            analyst="Example analyst",
            target_domain="illustrative_process",
            rationale="Integration example; the simulator outcome is not a qualified plant failure definition",
            scope_rationale="UNSAT does not separate recovery/timing; do not apply either again",
            included_effects=("timing", "recovery"),
        ),
    )
    graph = CausalGraph(
        id="release",
        root="uncontrolled",
        conditioning=event.conditioning,
        leaves=(
            CausalLeaf(
                id="human",
                kind="action",
                estimate_id=event.id,
                conditioning=event.conditioning,
                evidence=binding.evidence[0].id,
                scope_group="task_failure",
            ),
            CausalLeaf(
                id="hidden_state",
                kind="latent",
                probability=0.02,
                conditioning=event.conditioning,
                evidence="Assumed hidden-state probability",
            ),
            CausalLeaf(
                id="automatic_failure",
                kind="barrier_failure",
                probability=0.1,
                conditioning=event.conditioning,
                evidence="Assumed independent automatic failure probability",
            ),
        ),
        gates=(
            CausalGate(id="initiating", kind="OR", children=("human", "hidden_state")),
            CausalGate(id="uncontrolled", kind="AND", children=("initiating", "automatic_failure")),
        ),
        independence_evidence="Illustrative independence only; actual shared causes need a joint model",
    )
    case = RiskCase(
        id="evidence_to_design",
        estimates=(binding.estimate,),
        evidence=binding.evidence,
        graphs=(graph,),
        opportunity_definitions={graph.id: event.opportunity_definition},
        partition_evidence="One authored demand population",
        scenarios=(
            RiskScenario(
                id="operation",
                evidence="Authored scenario",
                initiating=InitiatingFrequency(
                    mode="demands",
                    event_ref=graph.id,
                    opportunity_definition=event.opportunity_definition,
                    demands_per_year=50.0,
                    evidence="Assumed 50 demands/year",
                ),
                branches=(
                    RiskBranch(
                        id="release_path",
                        probability=1.0,
                        consequence_id="receptor",
                        evidence="One illustrative consequence path",
                    ),
                ),
            ),
        ),
        consequences=(
            ConsequenceSpec(
                id="receptor",
                parameters={
                    "harm_probability": 0.1,
                    "harm_scope": "conditional_on_presence",
                    "occupancy": 0.25,
                    "fatality_distribution": {0: 0.975, 1: 0.025},
                    "expected_loss": 100.0,
                    "currency": "USD",
                    "evidence": "Authored consequence assumptions",
                },
            ),
        ),
        fn_thresholds=(1,),
    )
    result = RiskEngine().assess(case)
    improvement = Intervention(
        id="automatic_design_change",
        version="1",
        rationale="Assumed improved automatic barrier",
        evidence="Unvalidated intervention parameter for demonstration",
        changes=(CaseChange(path=("graphs", "0", "leaves", "2", "probability"), value=0.02, unit="1"),),
    )
    comparison = compare_intervention(case, improvement)
    assert (
        abs(
            comparison["alternative"]["individual_risk_rate_per_year"] * 5
            - result["individual_risk_rate_per_year"]
        )
        < 1e-12
    )
    (destination / "risk_case.json").write_text(case.model_dump_json(indent=2), encoding="utf-8")
    (destination / "intervention.json").write_text(improvement.model_dump_json(indent=2), encoding="utf-8")
    return (
        case,
        result,
        comparison,
        risk_importance(graph.tree(), result["graphs"]["release"]["leaf_probabilities"]),
    )


def operations():
    capabilities = tuple(
        EquipmentCapability(target=t, verb="position", state_key=t + ".position", minimum=0.0, maximum=1.0)
        for t in ("feed", "vent")
    )
    initial = ProcessState(
        revision="initial",
        values={
            "feed.position": StateValue(value=1.0),
            "vent.position": StateValue(value=0.0),
            "pressure": StateValue(value=4e5, unit="Pa"),
            "hidden_test_label": StateValue(value=True),
        },
    )
    predicate = StatePredicate(key="pressure", operator="le", value=2e5, unit="Pa")
    close = ExecutableAction(
        id="isolate", command=Command(target="feed", verb="position", value=0.0), evidence="Authored action"
    )
    vent = ExecutableAction(
        id="vent",
        command=Command(target="vent", verb="position", value=1.0),
        safety_conditions=(predicate,),
        permissives=(Permissive(id="pressure", condition=predicate, evidence="Authored permissive"),),
        evidence="Authored action",
    )
    messages = MessageLedger()
    messages.send(
        Message(
            id="instruction",
            sender="control",
            receiver="field",
            command=vent.command,
            sent_s=0.0,
            expires_s=10.0,
            evidence="Authored message",
        )
    )
    assert messages.receive("instruction", "field", 0.1)
    assert messages.interpret("instruction", "field", vent.command, 0.2)
    assert messages.confirm("instruction", "control", vent.command, 0.3)

    def advance(state, dt, time_s):
        values = dict(state.values)
        if values["feed.position"].value == 0:
            values["pressure"] = StateValue(value=max(0.0, values["pressure"].value - 1e5 * dt), unit="Pa")
        return ProcessState(revision="physics:" + str(time_s), values=values)

    process = StateProcess(
        initial, advance=advance, visibility={"control": ("pressure",), "field": ("pressure",)}
    )
    jobs = (
        RuntimeJob(id="isolate", action_id="isolate", candidate_actors=("control",), duration_s=1.0),
        RuntimeJob(
            id="vent",
            action_id="vent",
            candidate_actors=("field",),
            duration_s=1.0,
            release_s=4.0,
            predecessors=("isolate",),
        ),
    )

    def policy(job, observation, history, rng):
        assert "hidden_test_label" not in observation.values
        if job.id == "vent":
            return (
                messages.authorized_command("instruction", "field", observation.observed_at_s)
                if observation.values["pressure"].value <= 2e5
                else None
            )
        return close.command

    episode = run_coupled_episode(
        jobs, (close, vent), capabilities, process, horizon_s=6.0, seed=42, policy=policy
    )
    assert episode["status"] == "completed" and all(r["success"] for r in episode["records"])
    control = WorkControl(incompatible_activities=(("maintenance", "energize"),))
    permit = WorkPermit(
        id="maintenance",
        revision="1",
        area="unit",
        activity="maintenance",
        valid_from_s=6.0,
        valid_until_s=30.0,
        conditions=(predicate,),
        lock_owners=("worker",),
        required_restorations=("trip_bypass",),
        evidence="Authored work-control example",
    )
    control.issue(permit, time_s=6.0)
    control.lock(permit.id, "worker", time_s=7.0, evidence="Authored personal lock")
    assert control.authorize(permit.id, process.snapshot(), time_s=8.0, evidence="Authored inspection")[
        "authorized"
    ]
    control.unlock(permit.id, "worker", actor="worker", time_s=9.0, evidence="Authored worker clear")
    control.confirm_restoration(
        permit.id, "trip_bypass", time_s=10.0, evidence="Authored restoration observation"
    )
    control.close(permit.id, time_s=11.0, evidence="Authored closeout")
    variants = error_variants(
        vent, capabilities, alternative_targets=("feed",), delays_s=(2.0,), repetitions=(2,)
    )
    task = Task(
        id="operation",
        title="Authored isolated operation",
        procedure_version="1",
        steps=(
            TaskStep(
                id="isolate",
                action="Close feed",
                kind="manipulate",
                target="feed",
                actor="control",
                cue="start",
                completion="closed",
            ),
            TaskStep(
                id="vent",
                action="Open vent",
                kind="manipulate",
                target="vent",
                actor="field",
                cue="instruction",
                completion="open",
                predecessors=("isolate",),
            ),
        ),
        evidence=(
            Evidence(
                id="authored",
                reference="Authored procedure",
                origin="assumed",
                applicability="Software example",
            ),
        ),
    )
    trace = tuple(
        TraceStep(
            id=str(i),
            step_id=r["job_id"],
            actor=r["actor"],
            target=r["execution"]["realized"]["target"],
            start_s=r["start_s"],
            completion_s=r["completion_s"],
            procedure_version="1",
            outcome="completed" if r["success"] else "failed",
            evidence="Authored episode",
        )
        for i, r in enumerate(episode["records"])
    )
    conformance = procedure_conformance(
        task, trace, complete_observation=True, require_success_before=("vent",)
    )
    assert conformance["status"] == "conforming_observed_trace"
    net, initial_marking, goals = compile_task_net(task, error_variants={"vent": ("omission",)})
    progress = verify_progress(net, initial_marking, goal=lambda s: all(s[g] for g in goals))
    assert (
        progress["status"] == "pass_all_paths_complete"
    )  # attempts terminate, including the erroneous attempt
    error_check = net.verify(initial_marking, unsafe=lambda s: s["error:vent:omission"] == 1)
    assert error_check["status"] == "unsafe_reachable"
    timed = DiscreteTimedNet(
        ("ready", "done"),
        (TimedTransition(Transition("complete", {"ready": 1}, {"done": 1}), 1, 3),),
        capacities={"ready": 1, "done": 1},
    )
    deadline = timed.verify_deadline({"ready": 1}, goal=lambda s: s["done"] == 1, deadline_ticks=2)
    assert deadline["status"] == "deadline_or_progress_violation"
    return {
        "episode": episode,
        "message_audit": messages.audit,
        "work_audit": control.audit,
        "variant_ids": [v.id for v in variants],
        "conformance": conformance,
        "progress": progress,
        "error_check": error_check,
        "deadline": deadline,
    }


def observation_and_calibration():
    window = ObservationWindow(
        id="w", source_id="authored", clock_id="c", start_s=0.0, end_s=10.0, evidence="Authored window"
    )
    opportunities = tuple(
        TaskOpportunity(
            id=str(i),
            source_event_id=str(i),
            window_id="w",
            task_id="task",
            event_id="error",
            domain="authored",
            failure_definition="Authored task error",
            opportunity_definition="One authored opportunity",
            start_s=1.0,
            end_s=9.0,
            initial_error=error,
            final_failure=None,
            followup_complete=error is not None,
            evidence="Authored count fixture",
        )
        for i, error in enumerate((True, False, True, None))
    )
    ledger = ObservationLedger(
        (window,),
        opportunities,
        recoveries=(
            RecoveryAttempt(
                id="r", opportunity_id="0", time_s=3.0, successful=True, evidence="Authored recovery"
            ),
        ),
    )
    initial, final = ledger.snapshot("error", estimand="initial"), ledger.snapshot("error", estimand="final")
    assert initial["failures"] == 2 and final["failures"] == 1 and final["opportunities"] == 3
    groups = tuple(
        BinomialGroup(
            id=key,
            group_id=key,
            failures=k,
            opportunities=n,
            opportunity_definition="One authored opportunity",
            domain="authored",
            evidence="Authored count fixture, not field evidence",
        )
        for key, k, n in (("small", 0, 2), ("larger", 3, 40))
    )
    posterior = fit_partial_pooling(
        groups,
        (
            BetaHyperPoint(alpha=0.5, beta=5.0, prior_weight=1.0),
            BetaHyperPoint(alpha=1.0, beta=20.0, prior_weight=1.0),
        ),
        exchangeability_review="Authored compatible groups only; no missing crew identities inferred",
    )
    heldout = BinomialGroup(
        id="test",
        group_id="test",
        failures=1,
        opportunities=10,
        opportunity_definition="One authored opportunity",
        domain="authored",
        evidence="Authored held-out fixture",
    )
    scoring = heldout_binomial_scores(
        groups, (heldout,), {"test": 0.1}, split_review="Disjoint authored groups; declared .1 baseline"
    )
    quantiles = tuple(float(x) for x in beta.ppf([0.1, 0.5, 0.9], 2, 18))
    fitted = fit_elicited_beta(
        ExpertJudgment(
            expert_id="example",
            quantile_probabilities=(0.1, 0.5, 0.9),
            quantile_values=quantiles,
            evidence="Authored distribution",
        )
    )
    experts = expert_calibration_weights(
        {"example": {"seed": 0.8}}, {"seed": True}, temperature=0.1, seed_evidence="Authored seed"
    )
    return {
        "initial_counts": initial,
        "final_counts": final,
        "partial_pooling": {g.id: posterior.summary(g.id) for g in groups},
        "predictive_check": posterior_predictive_check(posterior, "small", size=1000, seed=42),
        "heldout_declared_baseline": scoring,
        "elicited_beta": fitted,
        "expert_weights": experts,
    }


def information_and_assurance(case):
    cue = Cue(
        id="alarm",
        evidence_id="authored_alarm",
        key="alarm",
        observation=StateValue(value=True),
        measured_s=0.0,
        available_s=1.0,
        expires_s=10.0,
        visible_to=("operator",),
        likelihoods={"fault": 0.9, "normal": 0.1},
    )
    store, belief = (
        CueStore((cue,)),
        BeliefState({"fault": 0.5, "normal": 0.5}, evidence="Authored equal diagnostic prior"),
    )
    monitor = monitor_cues(
        store, "operator", (PollChannel(key="alarm", interval_s=2.0, dwell_s=0.5),), horizon_s=5.0
    )
    belief.update(cue, actor="operator", time_s=2.0, independence_evidence="One authored observation")
    decision = belief.choose({"fault": "isolate", "normal": "continue"}, minimum_posterior=0.8)
    assert decision["action_id"] == "isolate"
    assumption = Assumption(
        id="scope",
        statement="Authored operating scope",
        evidence="Reviewed fixture",
        review_status="approved",
        expires_on=date(2027, 1, 1),
    )
    artifact = ArtifactFingerprint.of("risk_case", case, dependencies=("scope",))
    safety = SafetyCase(
        (Claim("risk_claim", "Declared modeled risk", ("risk_case",)),), {"risk_case": artifact.digest}
    )
    lifecycle = AssuranceLifecycle((artifact,), (assumption,), safety_case=safety)
    review = lifecycle.review((artifact,), as_of=date(2028, 1, 1))
    assert review["affected_claims"] == ("risk_claim",)
    return {"monitoring": monitor, "diagnosis": decision, "assurance_expiry_review": review}


def main():
    destination = Path("artifacts/operational_research")
    destination.mkdir(parents=True, exist_ok=True)
    case, risk, comparison, importance = evidence_risk(destination)
    workflow = MethodWorkflowCase.model_validate_json(
        files("human_reliability.data").joinpath("method_workflow.json").read_text(encoding="utf-8")
    )
    binding = run_method_workflow(workflow)
    result = {
        "risk": risk,
        "intervention": comparison["metrics"],
        "importance": importance,
        "operations": operations(),
        "observations_and_calibration": observation_and_calibration(),
        "information_and_assurance": information_and_assurance(case),
        "reference_workflow": binding.estimate.model_dump(mode="json"),
        "authored_scenarios_are_not_field_calibration": True,
    }
    (destination / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "risk_case": "artifacts/operational_research/risk_case.json",
                "result": "artifacts/operational_research/result.json",
                "twelve_extension_demonstrations": "passed",
                "field_validation_claim": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
