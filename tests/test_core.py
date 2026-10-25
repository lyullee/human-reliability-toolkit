import math

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from human_reliability import (
    BetaPrior,
    Context,
    Estimate,
    Evidence,
    HumanFailureEvent,
    MethodInput,
    MethodRegistry,
    Task,
    TaskStep,
    analyze_task,
    declared_estimator,
)
from human_reliability.dependency import apply_recovery, conditional_dependency
from human_reliability.methods import (
    cognitive_chain,
    heart_probability,
    multiplier_probability,
    spar_h_probability,
    SPAR_H_FACTORS,
)
from human_reliability.probability import (
    demand_frequency,
    intersection_independent,
    interval_probability,
    union_independent,
)


def estimate(p=0.1):
    return Estimate(
        event_id="miss",
        method="declared",
        probability=p,
        conditioning="given task demand",
        evidence_ids=("assumption",),
        status="assumed",
    )


def task():
    return Task(
        id="shutdown",
        title="Manual response",
        procedure_version="demo1",
        evidence=(
            Evidence(
                id="demo", reference="authored example", origin="assumed", applicability="software example"
            ),
        ),
        steps=(
            TaskStep(
                id="detect",
                action="recognize alarm",
                kind="observe",
                target="alarm",
                actor="operator",
                cue="annunciator",
                completion="alarm identified",
            ),
            TaskStep(
                id="stop",
                action="request stop",
                kind="manipulate",
                target="ESD",
                actor="operator",
                cue="identified alarm",
                completion="button operated",
                predecessors=("detect",),
                latent_hazards=("actuator power unavailable",),
            ),
        ),
    )


def test_contract_graph_and_strictness():
    value = task()
    assert [step.id for step in value.ordered_steps()] == ["detect", "stop"]
    raw = value.model_dump()
    raw["steps"] = (value.steps[0].model_copy(update={"predecessors": ("stop",)}), value.steps[1])
    with pytest.raises(ValidationError, match="cycle"):
        Task.model_validate(raw)
    with pytest.raises(ValidationError):
        estimate(float("nan"))
    with pytest.raises(ValidationError):
        Estimate.model_validate(estimate().model_dump() | {"probability": "0.1"})


def test_rule_exclusion_requires_actual_candidate():
    findings = analyze_task(task())
    assert any(f.rule_id == "latent_condition" for f in findings)
    key = findings[0].id
    assert analyze_task(task(), exclusions={key: "independent physical interlock"})[0].status == "excluded"
    with pytest.raises(ValueError):
        analyze_task(task(), exclusions={"unrelated": "not applicable"})


def test_beta_snapshot_does_not_reingest_and_zero_failures_not_zero_risk():
    prior = BetaPrior(alpha=1.0, beta=1.0, evidence_id="prior")
    a = prior.posterior(0, 100, event_id="e", observation_id="snapshot", conditioning="sample")
    b = prior.posterior(0, 100, event_id="e", observation_id="snapshot", conditioning="sample")
    assert a == b
    assert a.probability == pytest.approx(1 / 102)
    assert a.uncertainty["lower"] < a.probability < a.uncertainty["upper"]
    with pytest.raises(ValueError):
        prior.posterior(2, 1, event_id="e", observation_id="x", conditioning="sample")


@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=10))
def test_probability_partition_bounds(values):
    union, intersection = union_independent(values), intersection_independent(values)
    assert 0 <= intersection <= min(values) + 1e-12
    assert max(values) - 1e-12 <= union <= 1


def test_probability_and_rate_units():
    assert demand_frequency(200, 0.01, 0.5) == pytest.approx(1)
    assert interval_probability(1, 365.25 * 86400) == pytest.approx(1 - math.exp(-1))
    for bad in [True, float("inf"), float("nan"), -1, 1.01]:
        with pytest.raises(ValueError):
            union_independent([bad])


def test_recovery_dependency_and_scope():
    before = estimate()
    after = apply_recovery(before, 0.2, evidence_id="recovery")
    assert after.probability == pytest.approx(0.02)
    with pytest.raises(ValueError, match="already"):
        apply_recovery(after, 0.2, evidence_id="recovery")
    values = [conditional_dependency(0.1, level) for level in ["zero", "low", "moderate", "high", "complete"]]
    assert values == sorted(values)
    assert values[2] == pytest.approx(1.6 / 7)


def test_method_arithmetic_without_hidden_tables():
    p, trace = multiplier_probability(0.1, {"a": 10.0, "b": 20.0})
    assert p < 1
    assert trace["unbounded_product"] > 1
    factors = dict.fromkeys(SPAR_H_FACTORS, 1.0)
    assert spar_h_probability("diagnosis", factors)[0] == pytest.approx(0.01)
    assert spar_h_probability("action", factors)[0] == pytest.approx(0.001)
    assert heart_probability(0.01, ((4.0, 0.5),))[0] == pytest.approx(0.025)
    result = cognitive_chain(
        "e", {"detect": 0.1, "understand": 0.2}, conditioning="given demand", evidence_ids=("a",)
    )
    assert result.probability == pytest.approx(0.28)
    assert sum(result.trace["first_failure_probabilities"].values()) == pytest.approx(result.probability)


def test_registry_evidence_boundary():
    event = HumanFailureEvent(
        id="miss",
        task_id="shutdown",
        step_ids=("stop",),
        role="response",
        failure_definition="no stop",
        opportunity_definition="one alarm",
        conditioning="given alarm",
    )
    request = MethodInput(
        event=event, context=Context(id="c", operating_mode="operation"), evidence=task().evidence
    )
    registry = MethodRegistry()
    registry.register("declared", declared_estimator(0.1, "demo"))
    assert registry.evaluate("declared", request).probability == 0.1
    registry.register("bad", declared_estimator(0.1, "unavailable"))
    with pytest.raises(ValueError, match="absent"):
        registry.evaluate("bad", request)
