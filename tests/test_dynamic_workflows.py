import json

import pytest

from human_reliability.actions import (
    Command,
    EquipmentCapability,
    ExecutableAction,
    ProcessState,
    StatePredicate,
    StateValue,
)
from human_reliability.dynamics import (
    CoupledCase,
    RuntimeJob,
    StateProcess,
    StateRate,
    run_coupled_case,
    run_coupled_episode,
)
from human_reliability.verification import (
    DiscreteTimedNet,
    TimedTransition,
    compile_task_net,
    verify_progress,
)
from human_reliability.workflow import Transition, WorkflowNet
from human_reliability import ApplicabilityReview, HumanFailureEvent, builtin_evidence_catalog
from human_reliability.evidence_catalog import HumanEvidenceCatalog, HumanErrorRecord
from human_reliability.method_workflows import MethodWorkflowCase, run_method_workflow
from human_reliability.methods import SPAR_H_FACTORS
from human_reliability.contracts import Context, Evidence, Task, TaskStep
from human_reliability.assessment import AssessmentCase, AssessmentEngine, ModelSpec
from human_reliability.probability import BetaPrior


def dynamics_setup():
    capabilities = tuple(
        EquipmentCapability(target=t, verb="position", state_key=t + ".position", minimum=0.0, maximum=1.0)
        for t in ("v1", "v2")
    )
    initial = ProcessState(
        revision="r",
        values={
            "v1.position": StateValue(value=1.0),
            "v2.position": StateValue(value=0.0),
            "pressure": StateValue(value=4.0, unit="bar"),
            "hidden": StateValue(value=True),
        },
    )
    close = ExecutableAction(
        id="close", command=Command(target="v1", verb="position", value=0.0), evidence="e"
    )
    open_action = ExecutableAction(
        id="open",
        command=Command(target="v2", verb="position", value=1.0),
        safety_conditions=(StatePredicate(key="pressure", operator="le", value=2.0, unit="bar"),),
        evidence="e",
    )
    return capabilities, initial, (close, open_action)


def test_closed_loop_updates_before_next_decision_without_hidden_truth():
    capabilities, initial, actions = dynamics_setup()

    def advance(state, dt, now):
        values = dict(state.values)
        if values["v1.position"].value == 0:
            values["pressure"] = StateValue(value=max(0.0, values["pressure"].value - 2 * dt), unit="bar")
        return ProcessState(revision="t:" + str(now), values=values)

    process = StateProcess(
        initial, advance=advance, visibility={"control": ("pressure",), "field": ("pressure",)}
    )
    seen = []

    def policy(job, observation, history, rng):
        assert "hidden" not in observation.values
        if job.id == "second":
            assert not history  # another role's command is not automatically visible
            seen.append(observation.values["pressure"].value)
            return actions[1].command if observation.values["pressure"].value <= 2 else None
        return actions[0].command

    jobs = (
        RuntimeJob(id="first", action_id="close", candidate_actors=("control",), duration_s=1.0),
        RuntimeJob(
            id="second",
            action_id="open",
            candidate_actors=("field",),
            duration_s=1.0,
            release_s=2.0,
            predecessors=("first",),
        ),
    )
    result = run_coupled_episode(jobs, actions, capabilities, process, horizon_s=4.0, seed=3, policy=policy)
    assert seen == [2.0]
    assert result["status"] == "completed" and result["records"][-1]["success"]
    assert result["final_state"]["values"]["v2.position"]["value"] == 1


def test_preemption_resumption_and_completion_at_horizon():
    capabilities, initial, actions = dynamics_setup()
    jobs = (
        RuntimeJob(id="normal", action_id="close", candidate_actors=("op",), duration_s=10.0, priority=5),
        RuntimeJob(
            id="urgent",
            action_id="close",
            candidate_actors=("op",),
            duration_s=1.0,
            release_s=2.0,
            priority=0,
        ),
    )
    result = run_coupled_episode(jobs, actions, capabilities, StateProcess(initial), horizon_s=11.0, seed=4)
    completions = {r["job_id"]: r["completion_s"] for r in result["records"]}
    assert completions == {"urgent": 3.0, "normal": 11.0}
    assert result["status"] == "completed"
    assert [r["remaining_s"] for r in result["audit"] if r["kind"] == "interrupted"] == [8.0]


def test_bounded_retries_horizon_and_json_linear_case():
    capabilities, initial, actions = dynamics_setup()
    job = RuntimeJob(
        id="retry",
        action_id="close",
        candidate_actors=("op",),
        duration_s=1.0,
        error_probability=1.0,
        error_evidence="Authored forced omission",
        maximum_attempts=2,
        retry_mode="repeat",
    )
    result = run_coupled_episode((job,), actions, capabilities, StateProcess(initial), horizon_s=3.0, seed=2)
    assert len(result["records"]) == 2 and not any(r["success"] for r in result["records"])
    long = job.model_copy(update={"duration_s": 10.0})
    assert run_coupled_episode((long,), actions, capabilities, StateProcess(initial), horizon_s=3.0, seed=2)[
        "unfinished_jobs"
    ] == ["retry"]
    case = CoupledCase(
        initial=initial,
        actions=actions,
        capabilities=capabilities,
        jobs=(job,),
        horizon_s=3.0,
        seed=2,
        visibility={"op": ("pressure",)},
        rates={"pressure": StateRate(rate=-0.5, unit="bar/s")},
    )
    report = run_coupled_case(CoupledCase.model_validate_json(case.model_dump_json()))
    assert report["final_state"]["values"]["pressure"]["value"] == pytest.approx(2.5)
    with pytest.raises(ValueError, match="budget"):
        run_coupled_episode(
            (job,), actions, capabilities, StateProcess(initial), horizon_s=3.0, seed=2, maximum_events=1
        )


def test_process_advance_partition_consistency():
    _, initial, _ = dynamics_setup()

    def linear(state, dt, now):
        return ProcessState(
            revision="t:" + str(now),
            values=state.values
            | {"pressure": StateValue(value=state.values["pressure"].value + 0.5 * dt, unit="bar")},
        )

    whole, split = StateProcess(initial, advance=linear), StateProcess(initial, advance=linear)
    whole.advance_to(4.0)
    for t in (1.0, 2.0, 3.0, 4.0):
        split.advance_to(t)
    assert whole.snapshot() == split.snapshot()


def test_retry_policy_cannot_read_injected_truth_or_another_roles_history():
    capabilities, initial, actions = dynamics_setup()
    assert not StateProcess(initial).observe("op", 0.0).values
    job = RuntimeJob(
        id="repeat",
        action_id="close",
        candidate_actors=("op",),
        duration_s=1.0,
        error_probability=1.0,
        error_evidence="Authored hidden wrong-target injection",
        error_command=Command(target="v2", verb="position", value=0.0),
        maximum_attempts=2,
        retry_mode="policy",
    )
    decisions = []

    def policy(task, observation, history, rng):
        assert not hasattr(task, "error_probability") and not hasattr(task, "error_command")
        assert set(observation.values) == {"pressure"}
        if history:
            assert history[-1]["command"]["target"] == "v1"
            assert "success" not in history[-1] and "execution" not in history[-1]
        decisions.append(observation.observed_at_s)
        return actions[0].command

    def retry(task, observation, history, attempt, rng):
        assert history[-1]["command"]["target"] == "v1"
        return attempt < 2

    result = run_coupled_episode(
        (job,),
        actions,
        capabilities,
        StateProcess(initial, visibility={"op": ("pressure",)}),
        horizon_s=3.0,
        seed=1,
        policy=policy,
        retry_decider=retry,
    )
    assert decisions == [0.0, 1.0]
    assert all(r["execution"]["realized"]["target"] == "v2" for r in result["records"])


def test_possible_completion_is_not_inevitable_progress():
    net = WorkflowNet(
        ("active", "done"),
        (
            Transition("repeat", {"active": 1}, {"active": 1}),
            Transition("finish", {"active": 1}, {"done": 1}),
        ),
        capacities={"active": 1, "done": 1},
    )

    def goal(s):
        return s["done"] == 1

    assert (
        net.verify({"active": 1}, unsafe=lambda s: False, terminal=goal)["status"] == "pass_modeled_property"
    )
    assert verify_progress(net, {"active": 1}, goal=goal)["status"] == "nontermination_reachable"
    assert (
        verify_progress(net, {"active": 1}, goal=goal, require_all_paths=False)["status"]
        == "pass_possible_completion"
    )
    assert (
        verify_progress(net, {"active": 1}, goal=goal, maximum_states=1)["status"] == "incomplete_state_limit"
    )


def test_timed_deadline_quantifier_and_exact_boundary():
    transition = Transition("complete", {"ready": 1}, {"done": 1})
    net = DiscreteTimedNet(
        ("ready", "done"),
        (TimedTransition(transition, 1, 3),),
        capacities={"ready": 1, "done": 1},
        tick_seconds=0.5,
    )

    def goal(s):
        return s["done"] == 1

    assert (
        net.verify_deadline({"ready": 1}, goal=goal, deadline_ticks=2)["status"]
        == "deadline_or_progress_violation"
    )
    assert (
        net.verify_deadline({"ready": 1}, goal=goal, deadline_ticks=2, require_all_paths=False)["status"]
        == "pass_bounded_deadline"
    )
    assert net.verify_deadline({"ready": 1}, goal=goal, deadline_ticks=3)["status"] == "pass_bounded_deadline"
    with pytest.raises(ValueError):
        net.verify_deadline({"ready": 1}, goal=goal, deadline_ticks=3, require_all_paths="yes")


def test_zero_time_cycle_is_not_a_deadline_proof():
    net = DiscreteTimedNet(
        ("active", "done"),
        (
            TimedTransition(Transition("repeat", {"active": 1}, {"active": 1}), 0, 0),
            TimedTransition(Transition("finish", {"active": 1}, {"done": 1}), 1, 1),
        ),
        capacities={"active": 1, "done": 1},
    )
    result = net.verify_deadline({"active": 1}, goal=lambda s: s["done"] == 1, deadline_ticks=2)
    assert result["zero_time_cycle"] and result["status"] == "deadline_or_progress_violation"


def test_compiler_preserves_dag_fanout_and_injects_errors():
    a = TaskStep(
        id="a",
        action="Prepare",
        kind="manipulate",
        target="valve",
        actor="op",
        cue="start",
        completion="done",
    )
    task = Task(
        id="t",
        title="Authored",
        procedure_version="1",
        steps=(
            a,
            a.model_copy(update={"id": "b", "predecessors": ("a",)}),
            a.model_copy(update={"id": "c", "predecessors": ("a",)}),
        ),
        evidence=(Evidence(id="e", reference="Authored", origin="assumed", applicability="test"),),
    )
    net, initial, goals = compile_task_net(task)
    assert (
        verify_progress(net, initial, goal=lambda s: all(s[g] for g in goals))["status"]
        == "pass_all_paths_complete"
    )
    net, initial, goals = compile_task_net(task, error_variants={"b": ("omission",)})
    result = verify_progress(
        net, initial, goal=lambda s: all(s[g] for g in goals), unsafe=lambda s: s["error:b:omission"] == 1
    )
    assert result["status"] == "unsafe_reachable"


def target_event():
    return HumanFailureEvent(
        id="failure",
        task_id="task",
        step_ids=("act",),
        role="response",
        failure_definition="Authored response failure",
        opportunity_definition="One authored demand",
        conditioning="Authored demand",
    )


def test_native_task_binding_rejects_unresolved_text_conditions():
    from human_reliability.dynamics import bind_task_execution
    from human_reliability.actions import execute_action

    step = TaskStep(
        id="act",
        action="Open",
        kind="manipulate",
        target="v2",
        actor="op",
        cue="start",
        completion="done",
        preconditions=("pressure_safe",),
    )
    task = Task(
        id="t",
        title="Native task",
        procedure_version="1",
        steps=(step,),
        evidence=(Evidence(id="e", reference="Authored", origin="assumed", applicability="test"),),
    )
    capabilities, initial, actions = dynamics_setup()
    with pytest.raises(ValueError, match="predicate binding"):
        bind_task_execution(task, {"act": actions[1]}, {"act": 1.0})
    plan = bind_task_execution(
        task,
        {"act": actions[1]},
        {"act": 1.0},
        safety_bindings={
            "pressure_safe": StatePredicate(key="pressure", operator="le", value=2.0, unit="bar")
        },
    )
    assert plan.jobs[0].id == step.id and plan.procedure_version == task.procedure_version
    assert execute_action(initial, plan.actions[0], capabilities).status == "unsafe_attempt"


def review(effects):
    return ApplicabilityReview(
        analyst="Authored test",
        target_domain="authored",
        rationale="Software test",
        scope_rationale="Explicit effect scope",
        included_effects=effects,
    )


def test_spar_workflow_stage_union_recovery_and_assessment_integration():
    levels = dict.fromkeys(SPAR_H_FACTORS, "reference")
    workflow = MethodWorkflowCase(
        method="spar_h_profile",
        event=target_event(),
        review=review(("timing", "recovery")),
        parameters={
            "stages": [
                {"stage": "diagnosis", "levels": levels, "conditioning": "Demand"},
                {"stage": "action", "levels": levels, "conditioning": "Correct diagnosis"},
            ]
        },
        recovery={"failure_to_recover_given_error": 0.5, "evidence": "recovery_assumption"},
    )
    workflow = MethodWorkflowCase.model_validate_json(json.dumps(workflow.model_dump(mode="json")))
    binding = run_method_workflow(workflow)
    assert binding.estimate.probability == pytest.approx((0.01 + 0.99 * 0.001) * 0.5)
    assert set(binding.estimate.includes) == {"timing", "recovery"}
    step = TaskStep(
        id="act",
        action="Respond",
        kind="manipulate",
        target="valve",
        actor="op",
        cue="alarm",
        completion="done",
    )
    task = Task(id="task", title="Authored", procedure_version="1", steps=(step,), evidence=binding.evidence)
    case = AssessmentCase(
        task=task,
        context=Context(id="ctx", operating_mode="authored"),
        events=(target_event(),),
        models={
            "failure": ModelSpec(
                method="method_workflow",
                parameters={"workflow": workflow.model_dump(mode="json")},
                evidence_ids=binding.estimate.evidence_ids,
            )
        },
    )
    assert AssessmentEngine().assess(case)["estimates"][0]["probability"] == binding.estimate.probability


def test_heart_workflow_and_dependency_is_conditional():
    workflow = MethodWorkflowCase.model_validate_json(
        json.dumps(
            dict(
                method="heart_profile",
                event=target_event().model_dump(mode="json"),
                review=review(("dependency",)).model_dump(mode="json"),
                parameters={"task_code": "G", "effects": [], "base_includes": []},
                dependency={
                    "level": "complete",
                    "preceding_failure_id": "earlier",
                    "conditioning": "Authored demand",
                    "evidence": "reviewed_dependency",
                },
            )
        )
    )
    result = run_method_workflow(workflow)
    assert result.estimate.probability == 1 and result.estimate.trace["preceding_failure_id"] == "earlier"


def test_idheas_source_selection_floor_and_placeholders():
    catalog = builtin_evidence_catalog()
    configuration = dict(
        method="idheas_function",
        event=target_event().model_dump(mode="json"),
        review=review(()).model_dump(mode="json"),
        parameters={
            "function": "action",
            "base_records": {"scenario_familiarity": None, "information": None, "task_complexity": None},
            "base_includes": [],
        },
    )
    result = run_method_workflow(
        MethodWorkflowCase.model_validate_json(json.dumps(configuration)), catalog=catalog
    )
    assert (
        result.estimate.probability == 0.0001 and "eca.minimum.action" in result.estimate.trace["record_ids"]
    )
    placeholder = next(
        r.id
        for r in catalog.records.values()
        if r.source_id == "idheas_eca_2022" and r.function == "action" and r.basis == "placeholder"
    )
    configuration["parameters"]["modifier_records"] = [placeholder]
    with pytest.raises(ValueError, match="placeholders"):
        run_method_workflow(
            MethodWorkflowCase.model_validate_json(json.dumps(configuration)), catalog=catalog
        )


def test_cream_interval_requires_explicit_selection():
    catalog = builtin_evidence_catalog()
    row = next(r for r in catalog.records.values() if r.method == "cream_control_mode")
    case = MethodWorkflowCase(
        method="cream_range",
        event=target_event(),
        review=review(()),
        parameters={"record_id": row.id, "selected_value": row.lower, "base_includes": ()},
    )
    assert run_method_workflow(case, catalog=catalog).estimate.probability == row.lower


def test_reported_observed_probability_preserves_missing_denominator():
    source = builtin_evidence_catalog().sources["sacada_2019"]
    row = HumanErrorRecord(
        id="authored_summary",
        source_id=source.id,
        kind="reported_observed_probability",
        method="published_observation_summary",
        function="action",
        label="Authored schema test",
        domain="authored",
        locator="Authored test",
        quantity="probability",
        opportunity_definition="Reported demand",
        failure_definition="Reported failure",
        value=0.02,
        basis="field_observation",
        limitations=("Exact denominator not supplied in this authored test.",),
    )
    catalog = HumanEvidenceCatalog((source,), (row,))
    binding = catalog.bind(row.id, target_event(), review=review(()))
    assert binding.evidence[0].origin == "observed" and binding.estimate.status == "research"
    assert not binding.estimate.trace["denominator_available"]
    with pytest.raises(ValueError, match="fabricated"):
        catalog.bind(
            row.id,
            target_event(),
            review=review(()),
            prior=BetaPrior(alpha=1.0, beta=1.0, evidence_id="prior"),
        )
