from importlib.resources import files
import json

import pytest

from human_reliability import (
    ApplicabilityReview,
    BetaPrior,
    HumanFailureEvent,
    annual_frequency_from_evidence,
    builtin_evidence_catalog,
    sacada_context_labels,
)
from human_reliability.assessment import AssessmentCase, AssessmentEngine, ModelSpec
from human_reliability.dependency import apply_recovery
from human_reliability.evidence_catalog import HumanEvidenceCatalog, HumanErrorRecord, load_evidence_catalog
from human_reliability.reference_methods import (
    heart_profile_probability,
    idheas_cfm_probability,
    spar_h_profile_probability,
)
from human_reliability.methods import SPAR_H_FACTORS


@pytest.fixture(scope="module")
def catalog():
    return builtin_evidence_catalog()


def event():
    return HumanFailureEvent(
        id="failure",
        task_id="task",
        step_ids=("act",),
        role="response",
        failure_definition="Reviewed unsatisfactory action",
        opportunity_definition="One reviewed task demand",
        conditioning="Declared response context",
    )


def review(domain="nuclear_simulator"):
    return ApplicabilityReview(
        analyst="Authored test analyst",
        target_domain=domain,
        rationale="Explicit analytical test scope; no plant effectiveness claim.",
        scope_rationale="Aggregate training outcome cannot separate timing and recovery.",
        included_effects=("timing", "recovery"),
    )


def test_catalog_counts_and_complete_source_provenance(catalog):
    assert len(catalog.sources) == 7
    assert len(catalog.records) == 1334
    expected = {
        "detect_alarm": (61, 13, 2099),
        "read_indicator": (95, 17, 2198),
        "understanding": (116, 28, 2613),
        "decision": (147, 32, 6019),
        "action": (159, 59, 5167),
    }
    for function, (contexts, failures, opportunities) in expected.items():
        rows = catalog.search(kind="observed_count", function=function)
        assert (len(rows), sum(row.failures for row in rows), sum(row.opportunities for row in rows)) == (
            contexts,
            failures,
            opportunities,
        )
    for row in catalog.records.values():
        source = catalog.sources[row.source_id]
        assert source.authors and source.rights.reference and row.locator and row.failure_definition
        if row.kind != "observed_count":
            assert row.failures is None and row.opportunities is None


def test_observed_counts_remain_distinct_from_posterior_and_field_transfer(catalog):
    row = catalog.get("sacada.action.r0003")
    assert (row.failures, row.opportunities) == (1, 103)
    prior = BetaPrior(alpha=0.5, beta=0.5, evidence_id="prior")
    bound = catalog.bind(row.id, event(), review=review(), prior=prior)
    assert bound.estimate.probability == pytest.approx(1.5 / 104)
    assert bound.estimate.trace["source_observed_fraction"] == pytest.approx(1 / 103)
    assert bound.estimate.status == "empirical"
    transferred = catalog.bind(row.id, event(), review=review("hydrogen_station"), prior=prior)
    assert transferred.estimate.status == "research"
    assert not transferred.estimate.trace["field_validation_claim"]
    with pytest.raises(ValueError, match="explicit prior"):
        catalog.bind(row.id, event(), review=review())
    with pytest.raises(ValueError, match="already"):
        apply_recovery(bound.estimate, 0.2, evidence_id="would_double_count")


def test_zero_observed_errors_do_not_become_certain_success(catalog):
    row = next(row for row in catalog.search(kind="observed_count") if row.failures == 0)
    bound = catalog.bind(
        row.id, event(), review=review(), prior=BetaPrior(alpha=0.5, beta=0.5, evidence_id="prior")
    )
    assert row.observed_fraction == 0
    assert bound.estimate.probability > 0
    assert bound.estimate.uncertainty["upper"] > bound.estimate.probability


def test_exact_context_filters_and_missing_codes(catalog):
    rows = catalog.search(
        kind="observed_count", function="action", conditions={"workload": 2, "time_criticality": 2}
    )
    assert rows and all(row.conditions["workload"] == 2 for row in rows)
    assert not catalog.search(kind="observed_count", function="action", conditions={"workload": True})
    assert not catalog.search(
        kind="observed_count", function="action", conditions={"workload": True, "time_criticality": 2}
    )
    with pytest.raises(ValueError, match="unavailable"):
        catalog.search(kind="observed_count", conditions={"worklaod": 2})
    row = next(
        row
        for row in catalog.search(function="detect_alarm", kind="observed_count")
        if row.conditions["expectation"] == 0
    )
    labels = sacada_context_labels(row)
    assert labels["expectation"]["missing"]
    assert labels["non_standard"]["code"] == 0 and not labels["non_standard"]["missing"]


def test_counts_cannot_be_pooled_across_functions_or_repeated(catalog):
    ids = ("sacada.action.r0003", "sacada.action.r0004")
    summary = catalog.count_summary(
        ids, disjoint_contexts_rationale="Distinct released context rows within one function."
    )
    assert (summary["failures"], summary["opportunities"]) == (1, 116)
    assert not summary["independent_trials_verified"]
    with pytest.raises(ValueError, match="different"):
        catalog.count_summary((ids[0], "sacada.decision.r0003"), disjoint_contexts_rationale="invalid")
    with pytest.raises(ValueError, match="unique"):
        catalog.count_summary((ids[0], ids[0]), disjoint_contexts_rationale="invalid")


def test_method_records_never_accept_fabricated_denominators(catalog):
    bound = catalog.bind("heart.gtt.G", event(), review=review())
    assert bound.estimate.status == "method_estimate" and bound.estimate.probability == 0.0004
    with pytest.raises(ValueError, match="fabricated"):
        catalog.bind(
            "heart.gtt.G", event(), review=review(), prior=BetaPrior(alpha=1, beta=1, evidence_id="prior")
        )
    row = catalog.get("heart.gtt.G").model_dump()
    row.update(failures=1, opportunities=2500)
    with pytest.raises(ValueError, match="invented"):
        HumanErrorRecord.model_validate(row)


def test_components_and_multipliers_are_not_standalone_heps(catalog):
    for identity in ("eca.C34.source_level.action", "heart.epc.2.v1", "spar_h.action.fitness.unfit"):
        with pytest.raises(ValueError, match="stand-alone"):
            catalog.bind(identity, event(), review=review())
    assert catalog.get("eca.C34.source_level.action").value == 0.0026
    assert catalog.get("eca.C41.extreme_complexity_exchange.coordination").value == 0.1


def test_method_interval_requires_a_reviewed_point(catalog):
    with pytest.raises(ValueError, match="explicit point"):
        catalog.bind("cream.control_mode.tactical", event(), review=review())
    bound = catalog.bind("cream.control_mode.tactical", event(), review=review(), selected_value=0.02)
    assert bound.estimate.probability == 0.02
    with pytest.raises(ValueError):
        catalog.bind("cream.control_mode.tactical", event(), review=review(), selected_value=0.5)


def test_annual_frequency_requires_compatible_exposure(catalog):
    bound = catalog.bind("heart.gtt.G", event(), review=review())
    value = annual_frequency_from_evidence(
        bound.estimate,
        100.0,
        opportunity_definition=event().opportunity_definition,
        exposure_evidence="Authored annual work schedule",
    )
    assert value["annual_frequency_per_year"] == 0.04 and not value["observed_annual_frequency"]
    with pytest.raises(ValueError, match="match"):
        annual_frequency_from_evidence(
            bound.estimate,
            100,
            opportunity_definition="equipment operating hour",
            exposure_evidence="wrong unit",
        )


def test_not_cleared_source_blocks_binding(catalog):
    row = catalog.get("heart.gtt.G")
    source = catalog.sources[row.source_id]
    source = source.model_copy(
        update={"rights": source.rights.model_copy(update={"numeric_reuse": "not_cleared"})}
    )
    blocked = HumanEvidenceCatalog((source,), (row,))
    with pytest.raises(ValueError, match="not cleared"):
        blocked.bind(row.id, event(), review=review())


def test_unknown_catalog_version_is_rejected():
    with pytest.raises(ValueError, match="schema"):
        load_evidence_catalog({"schema_version": "2", "sources": []}, {"schema_version": "1", "records": []})


def test_catalog_assessment_case_matches_direct_binding(catalog):
    original = AssessmentCase.model_validate_json(
        files("human_reliability.data").joinpath("example_case.json").read_text()
    )
    target = original.events[0]
    prior = BetaPrior(alpha=0.5, beta=0.5, evidence_id="catalog_prior")
    bound = catalog.bind("sacada.action.r0003", target, review=review(), prior=prior)
    changed = original.model_copy(
        update={
            "task": original.task.model_copy(update={"evidence": original.task.evidence + bound.evidence}),
            "models": {
                target.id: ModelSpec(
                    method="evidence_catalog",
                    evidence_ids=bound.estimate.evidence_ids,
                    parameters={
                        "record_id": "sacada.action.r0003",
                        "review": review().model_dump(mode="json"),
                        "prior": prior.model_dump(mode="json"),
                    },
                )
            },
        }
    )
    result = AssessmentEngine(evidence_catalog=catalog).assess(
        AssessmentCase.model_validate_json(changed.model_dump_json())
    )
    assert result["estimates"][0]["probability"] == bound.estimate.probability
    assert json.dumps(result, allow_nan=False)


def test_spar_h_profiles_keep_stage_differences_and_terminal_rules(catalog):
    levels = dict.fromkeys(SPAR_H_FACTORS, "reference")
    assert spar_h_profile_probability("action", levels, catalog=catalog)[0] == 0.001
    assert spar_h_profile_probability("diagnosis", levels, catalog=catalog)[0] == 0.01
    changed = levels | {"complexity": "moderate", "experience_training": "limited", "procedures": "weak"}
    # Independent hand calculation: .001*2*3*5 / (1 + .001*(2*3*5 - 1)).
    assert spar_h_profile_probability("action", changed, catalog=catalog)[0] == pytest.approx(0.03 / 1.029)
    assert spar_h_profile_probability("action", levels | {"fitness": "unfit"}, catalog=catalog)[0] == 1
    with pytest.raises(ValueError, match="allow_unknown"):
        spar_h_profile_probability("action", levels | {"stress": "unknown"}, catalog=catalog)
    assert (
        spar_h_profile_probability(
            "action", levels | {"stress": "unknown"}, catalog=catalog, allow_unknown=True
        )[0]
        == 0.001
    )


def test_heart_profile_arithmetic_and_alternative_epc_levels(catalog):
    value, _ = heart_profile_probability("G", (("heart.epc.2.v1", 0.25),), catalog=catalog)
    assert value == pytest.approx(0.0004 * 3.5)
    with pytest.raises(ValueError, match="alternative"):
        heart_profile_probability("G", (("heart.epc.34.v1", 0.5), ("heart.epc.34.v2", 0.5)), catalog=catalog)
    assert catalog.get("heart.gtt.E").lower is None  # Published reversed interval is withheld.


def test_idheas_arithmetic_uses_additive_weights_and_nonzero_floor():
    base = dict(scenario_familiarity=0.0, information=0.0, task_complexity=0.0)
    assert idheas_cfm_probability("action", base, {})[0] == 0.0001
    assert idheas_cfm_probability("understanding", base, {})[0] == 0.001
    value, trace = idheas_cfm_probability(
        "action", base | {"task_complexity": 0.01}, {"a": 2.0, "b": 3.0}, recovery_divisor=2.0
    )
    assert value == pytest.approx(0.02)  # .01*(1 + 1 + 2)/2, not .01*2*3/2.
    assert not trace["official_full_method_implementation"]


def test_placeholders_are_not_presented_as_observed_weights(catalog):
    placeholders = [row for row in catalog.search(method="idheas_eca") if row.basis == "placeholder"]
    assert placeholders and all(row.value in {1.1, 1.2} and row.failures is None for row in placeholders)


def test_user_catalog_can_preserve_a_field_observation(catalog):
    original = catalog.get("sacada.action.r0003")
    record = original.model_copy(update={"id": "authored_test_field", "basis": "field_observation"})
    reconstructed = HumanErrorRecord.model_validate_json(record.model_dump_json())
    assert reconstructed.basis == "field_observation"
