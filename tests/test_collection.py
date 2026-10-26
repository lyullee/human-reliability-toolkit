"""Meaningful denominator, missingness, adjudication and leakage acceptance checks."""

import csv
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from human_reliability.collection import load_collection, write_collection_kit
from human_reliability.opportunity_validation import (
    exact_binomial_interval, opportunity_benchmarks, validate_collection, zero_error_plan,
)
from human_reliability.probability import BetaPrior

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collection_example", ROOT / "examples/field_collection.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


@pytest.fixture
def fixture():
    return example.synthetic_collection()


def test_collection_csv_roundtrip_and_synthetic_scope(tmp_path):
    expected, plan = example.save_synthetic(tmp_path / "forms")
    actual = load_collection(tmp_path / "forms")
    assert actual == expected
    report = validate_collection(actual, plan, bootstrap_replicates=200)
    assert report["eligible_evaluation_demands"] == 24
    assert report["unknown_outcomes"] == 2
    assert report["failure_fraction_bounds"] == [2 / 24, 4 / 24]
    assert sum(b["n"] for b in report["calibration_bins"]) == 22
    assert report["cluster_bootstrap"]["groups"] == 6
    assert not report["industrial_hep_validated"]
    estimate = actual.hep(estimand="final", prior=BetaPrior(alpha=1, beta=1, evidence_id="synthetic"),
                          independence_review="synthetic only", missingness_review="deliberate missing fixture",
                          window_ids=("evaluation",))
    assert estimate.status == "research" and estimate.trace["setting"] == "synthetic"
    assert estimate.probability == 3 / 24


def test_unrecorded_eligible_outcome_is_missing_not_success(fixture):
    bundle, _ = fixture
    altered = replace(bundle, outcomes=tuple(r for r in bundle.outcomes if r.demand_id != "evaluation-0"))
    result = altered.audit()["counts"]["final"]
    assert result["eligible_opportunities"] == 36
    assert set(result["missing_ids"]) == {"evaluation-0", "evaluation-22", "evaluation-23"}
    with pytest.raises(ValueError, match="missing outcomes"):
        altered.hep(estimand="final", prior=BetaPrior(alpha=1, beta=1, evidence_id="prior"),
                    independence_review="fixture")


def test_typed_condition_filter_and_context_provenance(fixture):
    b, _ = fixture
    snapshot = b.ledger().snapshot(b.protocol.event_id, estimand="initial", conditions={"shift": "night"})
    assert snapshot["eligible_opportunities"] == 18
    row = b.demands[0]
    with pytest.raises(ValueError, match="provenance"):
        type(row).model_validate(row.model_dump() | {"context_evidence": ""})


def test_collection_fingerprint_changes_when_observations_change(fixture):
    b, _ = fixture
    changed = replace(b, outcomes=(b.outcomes[0].model_copy(update={"initial_error": False, "final_failure": False}),
                                   *b.outcomes[1:]))
    assert b.audit()["protocol_digest"] == changed.audit()["protocol_digest"]
    assert b.audit()["collection_digest"] != changed.audit()["collection_digest"]
    options = dict(estimand="final", prior=BetaPrior(alpha=1, beta=1, evidence_id="prior"),
                   independence_review="synthetic only", missingness_review="fixture missingness")
    assert b.hep(**options).evidence_ids != changed.hep(**options).evidence_ids


@pytest.mark.parametrize("change", ["missing_register", "incomplete_coverage"])
def test_unreconciled_denominator_withholds_hep_and_validation(fixture, change):
    bundle, plan = fixture
    w = bundle.windows[1]
    update = {"expected_register_rows": 25} if change == "missing_register" else {"coverage_complete": False}
    bundle = replace(bundle, windows=(bundle.windows[0], w.model_copy(update=update)))
    assert not bundle.audit()["denominator_reconciled"]
    with pytest.raises(ValueError, match="unqualified denominator"):
        validate_collection(bundle, plan)


@pytest.mark.parametrize("change", ["demand", "source", "outcome", "prediction"])
def test_duplicate_records_cannot_inflate_trials(fixture, change):
    b, _ = fixture
    if change == "demand":
        b = replace(b, demands=(*b.demands, b.demands[0]))
    elif change == "source":
        b = replace(b, demands=(*b.demands, b.demands[0].model_copy(update={"id": "another"})))
    elif change == "outcome":
        b = replace(b, outcomes=(*b.outcomes, b.outcomes[0]))
    else:
        b = replace(b, predictions=(*b.predictions, b.predictions[0]))
    with pytest.raises(ValueError, match="duplicate"):
        b.ledger()


def test_explicit_duplicate_and_pretrigger_withdrawal_are_audited(fixture):
    bundle, _ = fixture
    retained = bundle.demands[0]
    duplicate = retained.model_copy(update={"id": "duplicate", "disposition": "duplicate_record",
                                           "duplicate_of": retained.id})
    withdrawn = retained.model_copy(update={"id": "withdrawn", "source_event_id": "withdrawn",
                                           "disposition": "withdrawn_before_trigger", "withdrawn_at_s": 1.5})
    b = replace(bundle, demands=(*bundle.demands, duplicate, withdrawn),
                windows=(bundle.windows[0].model_copy(update={"expected_register_rows": 14}), bundle.windows[1]))
    assert b.audit()["excluded_rows"] == 2
    assert b.audit()["counts"]["initial"]["eligible_opportunities"] == 36
    bad = withdrawn.model_copy(update={"withdrawn_at_s": withdrawn.start_s})
    with pytest.raises(ValueError, match="before the demand trigger"):
        replace(b, demands=(*bundle.demands, duplicate, bad)).ledger()


@pytest.mark.parametrize("update", [
    {"initial_error": True, "endpoint_adjudicated": False},
    {"final_failure": None, "followup_complete": True},
    {"final_failure": True, "followup_complete": False},
    {"coder_id": "synthetic-reviewer"},
])
def test_ambiguous_attribution_followup_and_self_adjudication_rejected(fixture, update):
    row = fixture[0].outcomes[0]
    with pytest.raises(ValueError):
        type(row).model_validate(row.model_dump() | update)


@pytest.mark.parametrize("change", ["late_prediction", "missing_prediction", "trained_demand", "trained_group",
                                      "late_plan", "prediction_before_plan", "future_training"])
def test_prediction_cohort_and_training_leakage_guards(fixture, change):
    b, p = fixture
    if change == "late_prediction":
        b = replace(b, predictions=(b.predictions[0].model_copy(update={"issued_s": 101}), *b.predictions[1:]))
    elif change == "missing_prediction":
        b = replace(b, predictions=b.predictions[:-1])  # Even an UNKNOWN outcome needs a prediction.
    elif change == "trained_demand":
        p = p.model_copy(update={"training_demand_ids": ("evaluation-0",)})
    elif change == "trained_group":
        p = p.model_copy(update={"training_group_ids": ("evaluation-crew-0",)})
    elif change == "late_plan":
        p = p.model_copy(update={"frozen_at_s": 101})
    elif change == "prediction_before_plan":
        p = p.model_copy(update={"frozen_at_s": 95})
    else:
        p = p.model_copy(update={"frozen_at_s": 5})
    with pytest.raises(ValueError):
        validate_collection(b, p)


@pytest.mark.parametrize("token", ["False", "0", "NA", "yes"])
def test_csv_boolean_tokens_are_never_truthiness_coerced(tmp_path, token):
    example.save_synthetic(tmp_path / "forms")
    path = tmp_path / "forms/outcomes.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    rows[1][1] = token
    with path.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)
    with pytest.raises(ValueError, match="outcomes.csv:2"):
        load_collection(tmp_path / "forms")


def test_kit_is_blank_strict_and_never_overwrites(tmp_path):
    path = write_collection_kit(tmp_path / "kit")
    assert json.loads((path / "protocol.json").read_text())["data_license"] == "internal_only"
    assert len((path / "demands.csv").read_text().splitlines()) == 1
    with pytest.raises(FileExistsError):
        write_collection_kit(path)
    with pytest.raises(ValueError):
        load_collection(path)


def test_published_blank_forms_match_current_generator(tmp_path):
    generated = write_collection_kit(tmp_path / "kit")
    published = ROOT / "templates/field_collection"
    assert {p.name for p in generated.iterdir()} == {p.name for p in published.iterdir()}
    for file in generated.iterdir():
        assert file.read_bytes().replace(b"\r\n", b"\n") == (published / file.name).read_bytes().replace(b"\r\n", b"\n")


def test_cli_executes_local_audit_and_validation(tmp_path):
    path = tmp_path / "forms"
    example.save_synthetic(path)
    output = tmp_path / "result.json"
    for command in (
        ["collection-audit", str(path), "--out", str(output)],
        ["collection-validate", str(path), str(path / "validation-plan.json"), "--out", str(output)],
    ):
        completed = subprocess.run([sys.executable, "-m", "human_reliability", *command],
                                   capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text())
    assert result["unknown_outcomes"] == 2 and result["setting"] == "synthetic"


def test_exact_binomial_and_zero_error_planning_do_not_report_zero_risk():
    interval = exact_binomial_interval(0, 100, independence_review="hypothetical independent trials")
    assert interval["lower"] == 0 and 0.036 < interval["upper"] < 0.037
    assert zero_error_plan(0.001, independence_review="planning") ["independent_opportunities_required"] == 2995
    assert zero_error_plan(0.0001, independence_review="planning") ["independent_opportunities_required"] == 29956
    with pytest.raises(ValueError):
        exact_binomial_interval(True, 100, independence_review="")


def test_public_aggregate_counts_keep_endpoint_and_rights_boundary():
    source = opportunity_benchmarks()["sources"][0]
    assert sum(r["opportunities"] for r in source["rows"]) == 5617
    assert sum(r["successes"] for r in source["rows"]) == 4971
    assert sum(r["failures"] for r in source["rows"]) == 646
    assert all(r["successes"] + r["failures"] == r["opportunities"] for r in source["rows"])
    assert source["license"] == "CC-BY-4.0"
    assert not source["human_error_attribution_adjudicated"] and not source["industrial_transfer_qualified"]


def test_retained_denominator_study_matches_current_inputs():
    spec = importlib.util.spec_from_file_location("denominator_study", ROOT / "scripts/run_denominator_study.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = json.loads((ROOT / "research/denominator_validation_results.json").read_text())
    assert result == module.compute()
    assert result["evaluation"]["observed_rate"] < result["evaluation"]["predicted_rate"]
    assert not result["adjudicated_human_field_hep_validated"]
