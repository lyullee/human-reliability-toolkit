from dataclasses import dataclass

import numpy as np
import pytest
from lifelines import KaplanMeierFitter

from human_reliability import SignalSeries, Task
from human_reliability.attention import allocate_attention
from human_reliability.monitoring import AlarmPolicy
from human_reliability.safety_case import Claim, SafetyCase
from human_reliability.simulation import simulate_response, simulate_task
from human_reliability.thermo import CoolPropState, energy_residual, inventory_mass_residual
from human_reliability.timing import (
    KaplanMeierTime,
    LognormalTime,
    apply_deadline,
    first_threshold_crossing,
    fit_weibull_censored,
    response_bins,
)
from human_reliability.uncertainty import Distribution, sample_inputs, sobol_sensitivity
from human_reliability.workflow import Transition, WorkflowNet
from test_core import estimate, task


def test_censored_ties_against_lifelines_and_unidentified_tail():
    durations = np.array([1, 2, 2, 3, 4, 4], float)
    completed = np.array([True, True, False, True, False, True])
    own = KaplanMeierTime(durations, completed)
    other = KaplanMeierFitter().fit(durations, event_observed=completed)
    for t in [0, 1, 1.5, 2, 3, 4]:
        assert own.cdf(t) == pytest.approx(1 - float(other.predict(t)))
    with pytest.raises(ValueError, match="unidentified"):
        own.cdf(5)


def test_deadline_and_bins_preserve_partition():
    time = LognormalTime(10.0, 0.3)
    assert time.cdf(10) == pytest.approx(0.5)
    result = apply_deadline(estimate(), time, 10.0, evidence_id="timing")
    assert result.probability == pytest.approx(0.55)
    assert sum(row["probability"] for row in response_bins(time, [5, 10, 20], 0.1)) == pytest.approx(1)
    with pytest.raises(ValueError):
        apply_deadline(result, time, 20, evidence_id="timing")
    assert first_threshold_crossing([0, 2, 4], [1, 3, 5], 4) == pytest.approx(3)


def test_censored_weibull_fit_uses_censoring():
    rng = np.random.default_rng(5)
    true = rng.weibull(2.0, 3000) * 10
    limit = np.full(len(true), 8.0)
    fit = fit_weibull_censored(np.minimum(true, limit), true <= limit)
    assert fit.scale_s == pytest.approx(10, rel=0.06)
    assert fit.shape == pytest.approx(2, rel=0.08)


def test_unknown_data_breaks_alarm_persistence():
    signal = SignalSeries(
        time_s=(0.0, 1.0, 2.0, 3.0, 4.0),
        values=(2.0, None, 2.0, 2.0, 2.0),
        valid=(True, False, True, True, True),
        clock_id="sim",
        unit="1",
        origin="authored",
    )
    result = AlarmPolicy(1.5, 1.0, persistence_s=2.0).evaluate(signal)
    assert result["activation_times_s"] == [4.0]
    assert result["valid"] == [True, False, True, True, True]


@dataclass
class FixedTime:
    value: float

    def sample(self, size, rng):
        return np.full(size, self.value)


def test_resource_schedule_and_physical_completion():
    value = task()
    history = simulate_task(
        value, {"detect": 0.0, "stop": 0.0}, {"detect": FixedTime(2), "stop": FixedTime(3)}, seed=1
    )
    assert history[1].start_s == 2
    assert history[1].completion_s == 5
    timeline = simulate_response(
        alarm_time_s=1, recognition_s=2, diagnosis_s=3, action_s=1, actuator_s=4, horizon_s=10
    )
    assert timeline["command_time_s"] == 7
    assert timeline["physical_completion_time_s"] == 11
    assert timeline["status"] == "not_completed_within_horizon"


def test_no_future_action_result_in_conditional_failure_model():
    first = task().steps[0]
    second = first.model_copy(update={"id": "parallel", "actor": "other"})
    value = Task(
        id="parallel",
        title="parallel",
        procedure_version="1",
        steps=(first, second),
        evidence=task().evidence,
    )
    seen = []

    def failure(history, rng):
        seen.append(dict(history))
        return 0.0

    replay = []
    simulate_task(
        value,
        {"detect": 0.0, "parallel": failure},
        {"detect": FixedTime(20), "parallel": FixedTime(1)},
        seed=1,
        consequence_callback=lambda step, outcome, history: replay.append(outcome.completion_s),
    )
    assert seen == [{}]
    assert replay == [1, 20]


def test_workflow_property_finds_unsafe_error_path_and_withholds_incomplete():
    network = WorkflowNet(
        ("pressurized", "isolated", "open"),
        (
            Transition("isolate", {"pressurized": 1}, {"isolated": 1}),
            Transition("normal_open", {"isolated": 1}, {"open": 1}),
            Transition(
                "premature_open", {"pressurized": 1}, {"pressurized": 1, "open": 1}, error_variant=True
            ),
        ),
    )
    result = network.verify({"pressurized": 1}, unsafe=lambda s: s["open"] > 0 and s["pressurized"] > 0)
    assert result["status"] == "unsafe_reachable"
    assert result["path"] == ("premature_open",)
    unbounded = WorkflowNet(("tokens",), (Transition("add", {}, {"tokens": 1}),))
    assert (
        unbounded.verify({}, unsafe=lambda s: False, maximum_states=4)["status"] == "incomplete_state_limit"
    )


def test_coolprop_and_balance_cross_checks():
    state = CoolPropState("Water").evaluate("P", 101325.0, "Q", 0.0)
    assert state["temperature_k"] == pytest.approx(373.1243, abs=0.01)
    assert max(abs(inventory_mass_residual([0, 1, 2], [10, 9, 8], [0, 0, 0], [1, 1, 1]))) == 0
    assert energy_residual(10, 12, heat_in_j=3, work_out_j=1, inflow_enthalpy_j=0, outflow_enthalpy_j=0) == 0


def test_dependency_sampling_and_attention_budget():
    draws = sample_inputs(
        {"a": Distribution("uniform", (0, 1)), "b": Distribution("uniform", (0, 1))},
        5000,
        seed=3,
        latent_correlation=[[1, 0.8], [0.8, 1]],
    )
    assert np.corrcoef(draws["a"], draws["b"])[0, 1] > 0.7
    result = allocate_attention(
        {"a": lambda x: (x - 0.8) ** 2, "b": lambda x: (x - 0.8) ** 2},
        {"a": (0, 1), "b": (0, 1)},
        budget=1,
        evidence_id="toy convex costs",
    )
    assert result["allocation"] == pytest.approx({"a": 0.5, "b": 0.5}, abs=1e-5)


def test_sobol_assumption_and_known_additive_ranking():
    with pytest.raises(ValueError):
        sobol_sensitivity(lambda a: a, {"a": (0, 1)})
    result = sobol_sensitivity(
        lambda a, b: a + 3 * b, {"a": (0, 1), "b": (0, 1)}, base_size=256, independent_inputs=True
    )
    assert result["evaluations"] == 1024
    assert result["ST"] == pytest.approx([0.1, 0.9], abs=0.03)


def test_safety_case_change_propagates():
    case = SafetyCase(
        (
            Claim("task", "procedure fits equipment", ("sop",)),
            Claim("risk", "risk estimate applies", ("task", "hep")),
        ),
        {"sop": "1", "hep": "1"},
    )
    assert case.affected_by(["sop"]) == ("risk", "task")
    assert case.changed_evidence({"sop": "2", "hep": "1"}) == ("sop",)
