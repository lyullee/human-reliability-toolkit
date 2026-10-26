"""Independent numerical checks and counterexamples for public-data qualification."""

import json
import zipfile

import numpy as np
import pytest

from human_reliability.field_data import (
    audit_clock,
    continuous_distillation,
    field_sources,
    incident_code_summary,
    incident_lessons,
    rail_incident_cases,
    steel_energy,
)
from human_reliability.field_studies import regression_holdout
from human_reliability.field_validation import (
    aggregate_binomial_metrics,
    calibration_width,
    detection_metrics,
    fit_robust_reference,
    interval_metrics,
    paired_block_rmse,
    regression_metrics,
    SampleAlarmPolicy,
)


def test_field_sources_keep_process_and_incident_evidence_out_of_hep():
    sources = field_sources()
    assert len(sources) == 4 and all(s.license == "CC-BY-4.0" for s in sources.values())
    for source in sources.values():
        with pytest.raises(ValueError, match="opportunity"):
            source.require_human_opportunities()
    assert sources["korea_rail_incidents"].origin == "observed_incident_codes"
    assert all(s.evidence().origin == "observed" for s in sources.values())


def test_clock_midnight_keeps_elapsed_seconds_without_inventing_a_date():
    result = audit_clock(["23:59:30", "00:00:00", "00:00:30"])
    assert result.qualified and result.elapsed_s == (0.0, 30.0, 60.0)
    assert result.midnight_rollovers == 1 and not result.has_calendar_date


def test_clock_duplicate_minutes_and_small_reversal_withhold_physical_delays():
    result = audit_clock(["1/5/2023 13:00", "01/05/2023 13:00", "01/05/2023 13:01:00"])
    assert not result.qualified and result.duplicate_intervals == 1
    backwards = audit_clock(["12:00:30", "12:00:00"])
    assert not backwards.qualified and backwards.backwards_intervals == 1
    assert not audit_clock(["12:00:00", "12:05:00"]).qualified
    assert not audit_clock(["12:60:00", "12:61:00"]).qualified


def original_distillation_zip(
    path,
    *,
    clocks=("12:00:00", "12:00:30", "12:01:00"),
    labels=(0, 0, 0),
    advanced=None,
    temperatures=(100.0, 101.0, np.nan),
):
    import pandas as pd

    name = "ContinuousDistillationData/ScenarioA_Authored/operating_point_001/train_normal_experiment_001"
    frame = pd.DataFrame(
        {
            "Time": clocks,
            "Label (common/all)": labels,
            "T102": temperatures,
            "PIC101": [1000.0, 1000.0, 1000.0],
        }
    )
    if advanced is not None:
        frame["Label (advanced/hard fault)"] = advanced
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(name + ".csv", frame.to_csv(index=False))
        z.writestr(name + ".yaml", "authored: true\n")
    return path


def test_distillation_signal_state_and_native_context_preserve_missingness(tmp_path):
    (run,) = continuous_distillation(original_distillation_zip(tmp_path / "test.zip"))
    signal = run.signal("T102", "degC")
    assert signal.valid == (True, True, False) and signal.values[-1] is None
    with pytest.raises(ValueError, match="labels"):
        run.process_state(0, {"Label (common/all)": "1"})
    state = run.process_state(0, {"T102": "degC", "PIC101": "mbar"})
    context = field_sources()["tum_continuous_distillation"].context(
        "observed", state, operating_mode="authored_test"
    )
    assert context.factors["PIC101"].value == 1000.0 and context.factors["PIC101"].unit == "mbar"
    assert context.factors["PIC101"].evidence_id == "field:tum_continuous_distillation"


def test_distillation_clock_cannot_silently_become_an_assumed_grid(tmp_path):
    (run,) = continuous_distillation(
        original_distillation_zip(tmp_path / "test.zip", clocks=("12:00", "12:00", "12:01"))
    )
    with pytest.raises(ValueError, match="clock"):
        run.signal("T102", "degC")
    series = run.signal("T102", "degC", declared_nominal_period_s=30.0)
    assert series.origin == "measured_values_on_assumed_clock" and series.clock_id.startswith("assumed_grid")
    assert series.time_s == (0.0, 30.0, 60.0)


def test_distillation_rejects_unrecognized_source_label_values(tmp_path):
    with pytest.raises(ValueError, match="binary"):
        continuous_distillation(original_distillation_zip(tmp_path / "bad.zip", labels=(0, 2, 0)))


def test_fractional_advanced_annotation_is_preserved_and_withheld_not_rounded(tmp_path):
    path = original_distillation_zip(tmp_path / "fractional.zip", advanced=(0.0, 0.5, 1.0))
    (run,) = continuous_distillation(path)
    assert run.frame["Label (advanced/hard fault)"].iloc[1] == 0.5
    assert run.annotation_audit["Label (advanced/hard fault)"]["unrecognized_phase_samples"] == 1
    with pytest.raises(ValueError, match="phase"):
        continuous_distillation(path, strict_advanced_labels=True)


def test_boolean_text_in_a_physical_measurement_is_unknown_not_zero(tmp_path):
    path = original_distillation_zip(tmp_path / "bad_measurement.zip", temperatures=(100.0, "FALSE", np.nan))
    (run,) = continuous_distillation(path)
    matrix, audit = run.numeric_matrix(["T102"])
    assert run.frame.T102.iloc[1] == "FALSE" and np.isnan(matrix[1, 0])
    assert audit["T102"]["non_numeric_boolean_or_nonfinite_cells"] == 1
    assert audit["T102"]["source_missing_cells"] == 1
    assert run.signal("T102", "degC").valid == (True, False, False)


def test_steel_loader_does_not_sort_away_duplicate_measurements(tmp_path):
    with zipfile.ZipFile(tmp_path / "steel.zip", "w") as z:
        z.writestr("Steel_industry_data.csv", "date,Usage_kWh\n01/01/2018 00:15,3\n01/01/2018 00:15,4\n")
    with pytest.raises(ValueError, match="strictly increasing"):
        steel_energy(tmp_path / "steel.zip")


def test_steel_midnight_interpretation_requires_opt_in_and_preserves_raw_date(tmp_path):
    with zipfile.ZipFile(tmp_path / "steel.zip", "w") as z:
        z.writestr(
            "Steel_industry_data.csv",
            "date,Usage_kWh\n01/01/2018 23:45,3\n01/01/2018 00:00,4\n02/01/2018 00:15,5\n",
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        steel_energy(tmp_path / "steel.zip")
    frame = steel_energy(tmp_path / "steel.zip", midnight_policy="end_of_recorded_day")
    assert frame.attrs["clock_interpretation"]["changed_rows"] == 1
    assert frame.source_time_raw.iloc[1].day == 1 and frame.source_time.iloc[1].day == 2
    assert frame.source_time.diff().dt.total_seconds().iloc[1:].tolist() == [900.0, 900.0]


def test_investigated_case_composition_is_not_probability_on_demand(tmp_path):
    columns = ["ID", *["C" + str(i) for i in range(1, 9)]]
    text = ",".join(columns) + "\n1,1,1,0,0,0,0,0,0\n2,0,1,0,0,0,0,0,0\n"
    path = tmp_path / "incidents.csv"
    path.write_text(text)
    result = incident_code_summary(rail_incident_cases(path))
    assert result["recorded_cases"] == 2 and result["code_case_composition"]["C2"] == 1.0
    assert result["human_failure_probability"] is None and result["annual_human_error_frequency"] is None
    assert result["overlapping_code_cases"] == 1
    path.write_text(text.replace("\n2,", "\n1,"))
    with pytest.raises(ValueError, match="unique"):
        rail_incident_cases(path)


def test_regression_metrics_match_independent_expression():
    result = regression_metrics([1.0, 3.0], [2.0, 4.0])
    assert result["mae"] == 1.0 and result["rmse"] == 1.0 and result["bias"] == 1.0
    assert result["r2"] == 0.0
    assert regression_metrics([1.0, 1.0], [2.0, 2.0])["r2"] is None
    with pytest.raises(ValueError, match="finite"):
        regression_metrics([1.0, np.nan], [2.0, 3.0])


def test_incident_findings_bind_to_assurance_only_with_explicit_transfer_review(tmp_path):
    text = "ID,C1,C2,C3,C4,C5,C6,C7,C8\n1,1,0,0,0,0,0,0,0\n"
    path = tmp_path / "authored.csv"
    path.write_text(text)
    frame = rail_incident_cases(path)
    with pytest.raises(ValueError, match="review"):
        incident_lessons(frame, {"C1": ("procedure",)}, analyst_review="")
    lessons = incident_lessons(
        frame,
        {"C1": ("procedure",)},
        analyst_review="Authored test transfer review",
        recommendations={"C1": "Review the procedure mapping"},
    )
    assert lessons[0].affected_ids == ("procedure",) and lessons[0].evidence == "field:korea_rail_incidents"
    assert (
        "not failure-on-demand" in lessons[0].statement
        and lessons[0].recommendation == "Review the procedure mapping"
    )


def test_calibration_order_statistic_and_unidentified_small_sample():
    assert calibration_width(np.arange(1.0, 10.0), np.zeros(9), nominal_coverage=0.9) == 9.0
    assert calibration_width([1.0], [0.0], nominal_coverage=0.9) is None
    assert interval_metrics([1.0], [0.0], half_width=None)["coverage"] is None
    assert interval_metrics([1.0, 2.0], [0.0, 0.0], half_width=1.0)["coverage"] == 0.5


def test_block_comparison_preserves_paired_constant_difference():
    result = paired_block_rmse(np.zeros(20), np.ones(20), np.full(20, 2.0), block_rows=4, repeats=100)
    assert result["model_minus_baseline_rmse"] == -1.0
    assert result["descriptive_block_95_interval"] == [-1.0, -1.0]


def test_regression_runner_never_fits_the_calibration_or_test_outcomes():
    import pandas as pd

    class Spy:
        def __init__(self, **parameters):
            self.parameters = parameters

        def fit(self, x, y):
            assert y.tolist() == [1.0, 3.0]
            self.mean = float(y.mean())

        def predict(self, x):
            return np.full(len(x), self.mean)

    frame = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "y": [1.0, 3.0, 99.0, 101.0, 200.0, 300.0]})
    train, calibration, test = [np.asarray([i // 2 == group for i in range(6)]) for group in range(3)]
    result, _ = regression_holdout(
        frame,
        target="y",
        features=["x"],
        train=train,
        calibration=calibration,
        test=test,
        baseline_test=[2.0, 2.0],
        baseline_calibration=[2.0, 2.0],
        unit="authored",
        model_parameters={},
        model_factory=Spy,
        bootstrap_repeats=100,
        block_rows=1,
    )
    assert result["rows"] == {"train": 2, "calibration": 2, "test": 2, "excluded": 0}
    assert result["model_interval"]["coverage"] is None
    with pytest.raises(ValueError, match="disjoint"):
        regression_holdout(
            frame,
            target="y",
            features=["x"],
            train=train,
            calibration=train,
            test=test,
            baseline_test=[2.0, 2.0],
            baseline_calibration=[2.0, 2.0],
            unit="authored",
            model_parameters={},
            model_factory=Spy,
            bootstrap_repeats=100,
        )


def test_robust_reference_and_missing_channels_are_explicit():
    ref = fit_robust_reference([[1.0, 10.0], [1.0, 10.0], [1.0, 10.0]], scale_floors=[0.5, 1.0])
    scores = ref.score([[1.0, 10.0], [2.0, 10.0], [np.nan, 10.0]])
    assert scores[0] == 0.0 and scores[1] == 2.0 and np.isnan(scores[2])
    with pytest.raises(ValueError, match="complete"):
        fit_robust_reference([[np.nan], [1.0]], scale_floors=[1.0])


def test_sample_alarm_persistence_uses_only_current_and_previous_samples():
    policy = SampleAlarmPolicy(2.0, 1.0, 3, 2)
    result = policy.evaluate([3.0, 3.0, np.nan, 3.0, 3.0, 3.0, 0.0, 0.0])
    assert result["activation_indices"] == [5]
    assert result["alarms"].tolist() == [False, False, False, False, False, True, True, False]
    assert result["valid"].tolist()[2] is False


def test_always_on_alarm_does_not_earn_event_detection_credit():
    alarms = {"alarms": np.ones(8, dtype=bool), "valid": np.ones(8, dtype=bool), "activation_indices": [0]}
    result = detection_metrics([0, 0, 1, 1, 1, 0, 0, 0], alarms)
    assert result["point_recall"] == 1.0 and result["event_recall"] == 0.0
    assert result["false_alarm_activations"] == 1 and not result["point_adjustment_applied"]


def test_event_delay_seconds_require_qualified_clock_and_one_activation_per_event():
    alarms = {
        "alarms": np.asarray([False, False, False, True, True, False]),
        "valid": np.ones(6, dtype=bool),
        "activation_indices": [3],
    }
    y = [0, 0, 1, 1, 1, 0]
    unknown_clock = detection_metrics(y, alarms)
    assert unknown_clock["events"][0]["delay_samples"] == 1 and unknown_clock["events"][0]["delay_s"] is None
    known_clock = detection_metrics(y, alarms, elapsed_s=np.arange(6) * 30, clock_qualified=True)
    assert known_clock["events"][0]["delay_s"] == 30.0
    alarms["activation_indices"] = [3, 4]
    with pytest.raises(ValueError, match="continuing"):
        detection_metrics(y, alarms)


def test_aggregate_binomial_scores_equal_expanded_observations():
    result = aggregate_binomial_metrics([1, 2], [4, 3], [0.25, 0.6])
    truth = np.asarray([1, 0, 0, 0, 1, 1, 0])
    p = np.asarray([0.25] * 4 + [0.6] * 3)
    assert result["brier"] == pytest.approx(np.mean((truth - p) ** 2))
    assert result["log_loss"] == pytest.approx(-np.mean(truth * np.log(p) + (1 - truth) * np.log1p(-p)))
    impossible = aggregate_binomial_metrics([1], [2], [0.0])
    assert impossible["log_loss"] is None and impossible["impossible_prediction"]
    json.dumps(impossible, allow_nan=False)


def test_aggregate_counts_cannot_be_reconstructed_from_rounded_proportions():
    with pytest.raises(ValueError, match="integer"):
        aggregate_binomial_metrics([0.1], [100.0], [0.2])
