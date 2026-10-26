import json

import numpy as np
import pytest

from human_reliability.actions import (
    Command,
    EquipmentCapability,
    ExecutableAction,
    Permissive,
    ProcessState,
    StatePredicate,
    StateValue,
    error_variants,
    execute_action,
    reordered_plan,
)
from human_reliability.causal import CausalGate, CausalGraph, CausalLeaf, JointState, evaluate_causal_graph
from human_reliability.contracts import Estimate, Evidence, Task, TaskStep
from human_reliability.risk import (
    ConsequenceMetrics,
    ConsequenceSpec,
    InitiatingFrequency,
    RiskBranch,
    RiskCase,
    RiskEngine,
    RiskScenario,
)
from human_reliability.interventions import (
    CaseChange,
    Intervention,
    compare_intervention,
    paired_model_comparison,
    risk_importance,
)
from human_reliability.fault_tree import Event, Gate
from human_reliability.uncertainty import Distribution


@pytest.fixture
def equipment():
    return tuple(
        EquipmentCapability(target=t, verb="position", state_key=t + ".position", minimum=0.0, maximum=1.0)
        for t in ("v1", "v2")
    )


def state(pressure=4.0):
    return ProcessState(
        revision="initial",
        values={
            "v1.position": StateValue(value=0.0),
            "v2.position": StateValue(value=0.0),
            "pressure": StateValue(value=pressure, unit="bar"),
        },
    )


def action(**changes):
    data = dict(
        id="open",
        command=Command(target="v1", verb="position", value=1.0),
        safety_conditions=(StatePredicate(key="pressure", operator="le", value=1.0, unit="bar"),),
        evidence="authored",
    )
    return ExecutableAction(**(data | changes))


def test_actual_wrong_target_and_unsafe_command(equipment):
    before = state()
    result = execute_action(
        before, action(), equipment, realized=Command(target="v2", verb="position", value=1.0)
    )
    assert result.status == "unsafe_attempt"
    assert result.state_after.values["v2.position"].value == 1
    assert result.state_after.values["v1.position"].value == before.values["v1.position"].value == 0
    assert result.intended.target == "v1" and result.realized.target == "v2"


@pytest.mark.parametrize(
    "pressure,expected", [(None, "unknown_withheld"), (4.0, "unsafe_attempt"), (0.5, "executed")]
)
def test_three_valued_preconditions(equipment, pressure, expected):
    result = execute_action(state(pressure), action(), equipment)
    assert result.status == expected
    if pressure is None:
        assert result.state_after.values["v1.position"].value == 0


def test_unknown_interlock_cannot_be_bypassed_by_unknown_attempt_policy(equipment):
    lock = Permissive(
        id="pressure_lock",
        condition=StatePredicate(key="pressure", operator="le", value=1.0, unit="bar"),
        evidence="authored",
    )
    result = execute_action(state(None), action(permissives=(lock,), unknown_policy="attempt"), equipment)
    assert result.status == "blocked" and result.realized is not None
    omitted = execute_action(state(), action(), equipment, omitted=True)
    assert omitted.status == "omitted" and omitted.realized is None


def test_units_and_capability_fail_closed(equipment):
    bad = action(safety_conditions=(StatePredicate(key="pressure", value=4.0, unit="Pa"),))
    with pytest.raises(ValueError, match="unit"):
        execute_action(state(), bad, equipment)
    with pytest.raises(ValueError, match="physical"):
        execute_action(
            state(), action(), equipment, realized=Command(target="v1", verb="position", value=2.0)
        )
    boolean = ProcessState(revision="r", values={"enabled": StateValue(value=False)})
    capability = EquipmentCapability(target="switch", verb="set", state_key="enabled")
    numeric = ExecutableAction(id="wrong_scalar", command=Command(target="switch", verb="set", value=1.), evidence="test")
    with pytest.raises(ValueError, match="scalar"):
        execute_action(boolean, numeric, (capability,))


def test_variant_bounds_and_reviewed_reordering(equipment):
    variants = error_variants(
        action(), equipment, alternative_targets=("v2",), magnitudes=(0.5,), delays_s=(2.0,), repetitions=(2,)
    )
    assert {v.kind for v in variants} == {
        "nominal",
        "omission",
        "substitution",
        "magnitude",
        "timing",
        "repetition",
    }
    with pytest.raises(ValueError, match="budget"):
        error_variants(action(), equipment, alternative_targets=("v2",), maximum_variants=2)
    first = TaskStep(
        id="a", action="first", kind="manipulate", target="v1", actor="op", cue="start", completion="done"
    )
    second = first.model_copy(update={"id": "b", "predecessors": ("a",)})
    task = Task(
        id="task",
        title="Authored",
        procedure_version="1",
        steps=(first, second),
        evidence=(Evidence(id="e", reference="Authored", origin="assumed", applicability="test"),),
    )
    assert reordered_plan(task, ("b", "a"), review="Reviewed erroneous sequence")[
        "precedence_violations"
    ] == (("a", "b"),)


def leaf(identity, p, **extra):
    return CausalLeaf(
        id=identity, kind="latent", evidence="e", conditioning="specified demand", probability=p, **extra
    )


def test_shared_event_graph_exact_boolean_identity():
    graph = CausalGraph(
        id="g",
        root="top",
        conditioning="specified demand",
        leaves=(leaf("a", 0.2),),
        gates=(CausalGate(id="top", kind="OR", children=("a", "a")),),
    )
    assert evaluate_causal_graph(graph)["probability"] == pytest.approx(0.2)


def test_independence_and_joint_marginal_qualification():
    leaves = (leaf("a", 0.2, dependency_groups=("supply",)), leaf("b", 0.2, dependency_groups=("supply",)))
    graph = CausalGraph(
        id="g",
        root="top",
        conditioning="specified demand",
        leaves=leaves,
        gates=(CausalGate(id="top", kind="AND", children=("a", "b")),),
        independence_evidence="Claimed",
    )
    assert evaluate_causal_graph(graph)["status"] == "withheld"
    dependent = graph.model_copy(
        update={
            "joint_states": (
                JointState(state={"a": False, "b": False}, probability=0.8),
                JointState(state={"a": True, "b": True}, probability=0.2),
            )
        }
    )
    assert evaluate_causal_graph(dependent)["probability"] == pytest.approx(0.2)
    inconsistent = dependent.model_copy(update={"leaves": (leaf("a", 0.3), leaf("b", 0.2))})
    with pytest.raises(ValueError, match="marginal"):
        evaluate_causal_graph(inconsistent)


def test_graph_scope_and_cycles():
    with pytest.raises(ValueError, match="cycle"):
        CausalGraph(
            id="g",
            root="top",
            conditioning="demand",
            leaves=(),
            gates=(CausalGate(id="top", kind="OR", children=("top",)),),
        )
    source = Estimate(
        event_id="a",
        method="declared",
        probability=0.1,
        conditioning="demand",
        evidence_ids=("e",),
        status="assumed",
        includes=("recovery",),
    )
    graph = CausalGraph(
        id="g",
        root="top",
        conditioning="demand",
        leaves=(
            CausalLeaf(
                id="human",
                kind="action",
                estimate_id="a",
                evidence="e",
                conditioning="demand",
                scope_group="action",
            ),
            CausalLeaf(
                id="recovery",
                kind="recovery_failure",
                probability=0.5,
                evidence="e2",
                conditioning="demand",
                scope_group="action",
            ),
        ),
        gates=(CausalGate(id="top", kind="AND", children=("human", "recovery")),),
        independence_evidence="test",
    )
    with pytest.raises(ValueError, match="twice"):
        evaluate_causal_graph(graph, {"a": source})


def risk_case(*, exposure=100.0, harm=0.2):
    event = Estimate(
        event_id="error",
        method="declared",
        probability=0.01,
        conditioning="one demand",
        evidence_ids=("authored",),
        status="assumed",
    )
    return RiskCase(
        evidence=(
            Evidence(
                id="authored", reference="Authored parameter", origin="assumed", applicability="Software test"
            ),
        ),
        id="authored",
        estimates=(event,),
        opportunity_definitions={"error": "one demand"},
        partition_evidence="One authored exposure population",
        scenarios=(
            RiskScenario(
                id="s",
                evidence="authored",
                initiating=InitiatingFrequency(
                    mode="demands",
                    event_ref="error",
                    opportunity_definition="one demand",
                    demands_per_year=exposure,
                    evidence="Assumed exposure",
                ),
                branches=(
                    RiskBranch(id="release", probability=1.0, evidence="authored", consequence_id="harm"),
                ),
            ),
        ),
        consequences=(
            ConsequenceSpec(
                id="harm",
                parameters={
                    "harm_probability": harm,
                    "harm_scope": "conditional_on_presence",
                    "occupancy": 0.5,
                    "fatality_distribution": {0: 0.8, 2: 0.2},
                    "expected_loss": 100.0,
                    "currency": "USD",
                    "evidence": "authored",
                },
            ),
        ),
        fn_thresholds=(1, 2, 3),
    )


def test_configurable_risk_frequency_harm_loss_and_fn():
    case = risk_case()
    result = RiskEngine().assess(case)
    assert result["annual_frequency_per_year"] == 1.0
    assert result["individual_risk_rate_per_year"] == pytest.approx(0.1)
    assert result["expected_loss_per_year"] == 100.0
    assert result["fn_frequency_per_year"] == {"1": 0.2, "2": 0.2, "3": 0.0}
    restored = RiskCase.model_validate_json(case.model_dump_json())
    assert RiskEngine().assess(restored) == result


def test_unknown_exposure_never_becomes_zero_frequency():
    result = RiskEngine().assess(risk_case(exposure=None))
    assert result["status"] == "withheld_or_partial"
    assert result["annual_frequency_per_year"] is None and result["individual_risk_rate_per_year"] is None
    assert result["ledger"][0]["probability_given_initiation"] == 1


def test_occupancy_and_branch_conditioning_guard():
    with pytest.raises(ValueError, match="twice"):
        ConsequenceMetrics(harm_probability=0.2, harm_scope="includes_occupancy", occupancy=0.5, evidence="e")
    case = risk_case()
    data = case.model_dump(mode="json")
    data["scenarios"][0]["branches"] = [
        dict(id="b", evidence="e", event_ref="error", conditioning="other demand", consequence_id="harm")
    ]
    with pytest.raises(ValueError, match="conditioning"):
        RiskEngine().assess(RiskCase.model_validate_json(json.dumps(data)))


def test_intervention_changes_parameters_not_baseline():
    case = risk_case()
    change = Intervention(
        id="improve",
        version="1",
        rationale="Assumed engineering change",
        evidence="Assumption",
        changes=(CaseChange(path=("estimates", "0", "probability"), value=0.005, unit="1"),),
    )
    report = compare_intervention(case, change)
    assert case.estimates[0].probability == 0.01
    assert report["metrics"]["individual_risk_rate_per_year"]["reduction"] == pytest.approx(0.05)
    exposure = change.model_copy(
        update={
            "changes": (
                CaseChange(
                    path=("scenarios", "0", "initiating", "demands_per_year"), value=50.0, unit="demand/year"
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="exposure"):
        compare_intervention(case, exposure)


def test_paired_inputs_and_analytical_importance():
    result = paired_model_comparison(
        lambda x: x + 2,
        lambda x: x,
        {"x": Distribution("uniform", (0.0, 1.0))},
        size=40,
        seed=3,
        evidence="Authored paired model",
    )
    assert np.allclose(result["paired_reductions"], 2.0)
    assert result["monte_carlo_standard_error"] < 1e-15
    report = risk_importance(Gate("OR", (Event("a"), Event("b"))), {"a": 0.1, "b": 0.2})
    assert report["top_probability"] == pytest.approx(0.28)
    assert report["events"]["a"]["birnbaum"] == pytest.approx(0.8)
    assert report["events"]["a"]["fussell_vesely"] == pytest.approx(0.08 / 0.28)


def test_unknown_provider_preserves_known_frequency_and_withholds_harm():
    case = risk_case()
    spec = case.consequences[0].model_copy(update={"provider": "unregistered"})
    result = RiskEngine().assess(case.model_copy(update={"consequences": (spec,)}))
    assert result["annual_frequency_per_year"] == 1.0
    assert result["individual_risk_rate_per_year"] is None
    assert result["status"] == "withheld_or_partial"


def test_intervention_never_retains_an_empirical_label_or_stale_posterior():
    case = risk_case()
    empirical = case.estimates[0].model_copy(
        update={"status": "empirical", "uncertainty": {"distribution": "beta", "alpha": 1.0, "beta": 99.0}}
    )
    case = case.model_copy(update={"estimates": (empirical,)})
    intervention = Intervention(
        id="assumption",
        version="1",
        rationale="Assumed effect",
        evidence="Not observed",
        changes=(CaseChange(path=("estimates", "0", "probability"), value=0.005, unit="1"),),
    )
    from human_reliability.interventions import apply_intervention

    alternative = apply_intervention(case, intervention)
    assert alternative.estimates[0].status == "assumed" and not alternative.estimates[0].uncertainty
    assert alternative.estimates[0].trace["baseline_estimate"]["uncertainty"] == empirical.uncertainty
    assert case.estimates[0].status == "empirical"


def test_causal_conditioning_and_expansion_budget():
    with pytest.raises(ValueError, match="conditioning"):
        CausalGraph(id="g", root="a", conditioning="Other demand", leaves=(leaf("a", 0.2),))
    graph = CausalGraph(
        id="g",
        root="top",
        conditioning="specified demand",
        leaves=(leaf("a", 0.2),),
        gates=(CausalGate(id="top", kind="OR", children=("a", "a")),),
        maximum_expanded_nodes=1,
    )
    with pytest.raises(ValueError, match="expansion"):
        evaluate_causal_graph(graph)
