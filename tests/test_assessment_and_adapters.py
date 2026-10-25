from importlib.resources import files
import io
import json
from types import SimpleNamespace
import zipfile

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from human_reliability import Estimate, canonical_digest
from human_reliability.adapters import (
    dynasense_scenario,
    human_initiator,
    monitoring_context,
    observation_series,
    prism_branches,
    prism_demand,
    qsafety_frequency_mixture,
    saga_context,
    station_stop_requested,
    psa_trace,
)
from human_reliability.assessment import AssessmentCase, AssessmentEngine
from human_reliability.barriers import Barrier, lopa_screen
from human_reliability.datasets import cog_behavior
from human_reliability.methods import SPAR_H_FACTORS, spar_h_probability
from human_reliability.qualitative import DeviationRule
from human_reliability.registers import RiskMatrix, hazop_rows
from human_reliability.studies import cluster_bootstrap_rate, group_holdout
from human_reliability.timing import CensoredRegression
from test_core import estimate, task


def case():
    return AssessmentCase.model_validate_json(
        files("human_reliability.data").joinpath("example_case.json").read_text()
    )


def test_json_case_and_custom_rules_round_trip():
    original = case()
    reconstructed = AssessmentCase.model_validate_json(original.model_dump_json())
    assert canonical_digest(original) == canonical_digest(reconstructed)
    custom = DeviationRule(
        id="domain_rule",
        kinds=("*",),
        question="Is {target} qualified?",
        effect_to_check="application-specific",
        concern="design",
    )
    result = AssessmentEngine().assess(original.model_copy(update={"deviation_rules": (custom,)}))
    assert {row["rule_id"] for row in result["findings"]} == {"domain_rule", "latent_condition"}


def test_declared_and_empirical_case_methods():
    original = case()
    from human_reliability.assessment import ModelSpec

    key = original.events[0].id
    changed = original.model_copy(
        update={
            "models": {
                key: ModelSpec(method="declared", parameters={"probability": 0.3}, evidence_ids=("demo",))
            }
        }
    )
    assert AssessmentEngine().assess(changed)["estimates"][0]["probability"] == 0.3
    engine = AssessmentEngine()

    def plugin(request):
        return Estimate(
            event_id=request.event.id,
            method="custom",
            probability=0.2,
            conditioning=request.event.conditioning,
            evidence_ids=("demo",),
            status="assumed",
        )

    engine.register("context_plugin", plugin)
    changed = changed.model_copy(
        update={"models": {key: ModelSpec(method="context_plugin", parameters={}, evidence_ids=("demo",))}}
    )
    assert engine.assess(changed)["estimates"][0]["probability"] == 0.2


def test_prism_payloads_keep_new_initiator_separate():
    source = estimate()
    payload = prism_demand(source, 20.0)
    assert payload["failure_probability_per_demand"] == 0.1
    custom = human_initiator(source, 20.0, task_id="task", component_id="valve", release_binding="declared")
    assert custom["annual_frequency_per_year"] == 2
    assert custom["requires_prism_initiator_extension"]
    assert (
        sum(
            row["probability_given_initiation"]
            for row in prism_branches({"a": 0.2, "b": 0.8}, evidence="reviewed")
        )
        == 1
    )


def test_custom_method_parameters_and_conditioning_guard():
    from human_reliability.assessment import ModelSpec

    original = case()
    key = original.events[0].id
    configured = original.model_copy(
        update={
            "models": {
                key: ModelSpec(
                    method="plugin", parameters={"local_probability": 0.37}, evidence_ids=("demo",)
                )
            }
        }
    )
    engine = AssessmentEngine()

    def plugin(request):
        return Estimate(
            event_id=request.event.id,
            method="plugin",
            probability=request.parameters["local_probability"],
            conditioning=request.event.conditioning,
            evidence_ids=("demo",),
            status="assumed",
        )

    engine.register("plugin", plugin)
    assert engine.assess(configured)["estimates"][0]["probability"] == 0.37
    engine.register(
        "plugin",
        lambda request: plugin(request).model_copy(update={"conditioning": "a different demand definition"}),
        replace=True,
    )
    with pytest.raises(ValueError, match="conditioning"):
        engine.assess(configured)


def test_grouped_logistic_rejects_fractional_outcomes():
    from human_reliability.studies import grouped_logistic

    frame = pd.DataFrame({"participant": range(10), "context": ["a"] * 10, "outcome": [0.5] * 10})
    with pytest.raises(ValueError, match="binary"):
        grouped_logistic(frame, "outcome", "participant", features=("context",))


def test_dynasense_and_manual_stop_use_different_times():
    bound = dynasense_scenario({"horizon_s": 40.0, "isolation_time_s": 10.0}, None)
    assert bound["isolation_time_s"] > 40
    assert not station_stop_requested(4, {"status": "completed", "command_time_s": 5})
    assert station_stop_requested(5, {"status": "completed", "command_time_s": 5})
    assert not station_stop_requested(100, {"status": "wrong_action", "command_time_s": 5})


def test_signal_adapters_preserve_invalid_measurements():
    result = SimpleNamespace(
        time_s=[0.0], scores=[np.nan], alarms=[False], valid=[False], detector="test", threshold=1.0
    )
    assert monitoring_context(result, 0)["score"] is None
    table = SimpleNamespace(time_s=[0.0, 1.0], values={"p": [10.0, np.nan]}, valid_masks={"p": [True, False]})
    series = observation_series(table, "p", unit="Pa", clock_id="fixture", origin="authored_fixture")
    assert series.values == (10.0, None)
    assert not series.valid[1]
    mixture = qsafety_frequency_mixture([1.0, 3.0], [0.1, 0.3])
    assert mixture["weighted_event_rate_per_year"] == pytest.approx(1)
    payload = saga_context({"valid": False}, station_id="s", scenario_id="c")
    assert json.loads(payload["context_text"])["human_reliability"]["valid"] is False


def test_psa_cumulative_clock_rejects_cycle_clock_reset(tmp_path):
    path = tmp_path / "trace.csv"
    pd.DataFrame({"time_s": [0.0, 1.0, 0.0], "pressure_pa": [1e5, 2e5, 1e5]}).to_csv(path, index=False)
    with pytest.raises(ValueError):
        psa_trace(path, channel="pressure_pa", unit="Pa", clock_id="simulation")


def test_nested_subject_zip_paths_and_flag_order(tmp_path):
    stream = io.BytesIO()
    savemat(stream, {"PVT": {"reaction_times": np.array([0.2, 0.3]), "error_trial": np.array([0, 1])}})
    path = tmp_path / "sub-01_behavioral.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sub-01/sub-01/ses-S2/behavioral/PVT.mat", stream.getvalue())
    result = cog_behavior([path])["vigilance"]
    assert result.session.unique().tolist() == ["ses-S2"]
    assert result.source_error_flag.tolist() == [False, True]


def test_lopa_withholds_shared_dependencies():
    automatic = Barrier(
        "auto", "automatic", 0.1, "reliability evidence", "independence reviewed", ("shared_sensor",)
    )
    human = Barrier("human", "human", 0.2, "human study", "independence reviewed", ("shared_sensor",), True)
    assert lopa_screen(0.01, (automatic, human))["residual_frequency_per_year"] is None
    separate = Barrier("human2", "human", 0.2, "human study", "independence reviewed", ("separate",), True)
    assert lopa_screen(0.01, (automatic, separate))["residual_frequency_per_year"] == pytest.approx(0.0002)


def test_ordinal_register_does_not_supply_numeric_hep():
    matrix = RiskMatrix(
        ("minor", "major"),
        ("rare", "frequent"),
        {
            ("minor", "rare"): "low",
            ("minor", "frequent"): "medium",
            ("major", "rare"): "medium",
            ("major", "frequent"): "high",
        },
    )
    assert matrix.classify("major", "rare") == "medium"
    from human_reliability import analyze_task

    row = hazop_rows(analyze_task(task()))[0]
    assert "probability" not in row


def test_group_split_and_cluster_bootstrap():
    groups = np.repeat(np.arange(20), 3)
    train, test = group_holdout(groups)
    assert not set(groups[train]) & set(groups[test])
    result = cluster_bootstrap_rate(np.tile([0, 0, 1], 20), groups, repeats=200)
    assert result["rate"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("model", ["weibull_aft", "cox_ph"])
def test_survival_regression_retains_context_effect(model):
    rng = np.random.default_rng(10)
    x = rng.integers(0, 2, 1200)
    true = 5 * np.exp(0.7 * x) * rng.weibull(1.8, 1200)
    frame = pd.DataFrame({"duration": np.minimum(true, 8), "completed": true <= 8, "load": x.astype(float)})
    regression = CensoredRegression(model).fit(
        frame,
        duration_col="duration",
        completed_col="completed",
        covariates=("load",),
        time_unit="s",
        evidence_id="authored stochastic check",
    )
    p = regression.completion_probability(5, pd.DataFrame({"load": [0.0, 1.0]}))
    assert 0 < p[1] < p[0] < 1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 0.0, True])
def test_insufficient_time_does_not_hide_invalid_factors(bad):
    factors = dict.fromkeys(SPAR_H_FACTORS, 1.0)
    factors["complexity"] = bad
    with pytest.raises(ValueError):
        spar_h_probability("action", factors, insufficient_time=True)
