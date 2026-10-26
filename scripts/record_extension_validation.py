"""Link the twelve implemented scopes to passing tests from the current verified source set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import tomllib

from verification_inputs import input_files

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = {
    "G01": (
        "actions",
        "Atomic unit-checked commands and bounded reviewed variants",
        (
            "test_actual_wrong_target_and_unsafe_command",
            "test_three_valued_preconditions",
            "test_variant_bounds_and_reviewed_reordering",
            "test_native_task_binding_rejects_unresolved_text_conditions",
        ),
    ),
    "G02": (
        "causal",
        "Explicit same-population causal logic, shared events and declared joint models",
        (
            "test_shared_event_graph_exact_boolean_identity",
            "test_independence_and_joint_marginal_qualification",
            "test_graph_scope_and_cycles",
            "test_causal_conditioning_and_expansion_budget",
        ),
    ),
    "G03": (
        "risk",
        "Serializable conditional risk with explicit exposure and registered consequences",
        (
            "test_configurable_risk_frequency_harm_loss_and_fn",
            "test_unknown_exposure_never_becomes_zero_frequency",
            "test_unknown_provider_preserves_known_frequency_and_withholds_harm",
        ),
    ),
    "G04": (
        "dynamics",
        "Supplied process feedback, role-visible policies, bounded attempts and preemption",
        (
            "test_closed_loop_updates_before_next_decision_without_hidden_truth",
            "test_preemption_resumption_and_completion_at_horizon",
            "test_retry_policy_cannot_read_injected_truth_or_another_roles_history",
            "test_process_advance_partition_consistency",
        ),
    ),
    "G05": (
        "communication",
        "Modeled message/readback, handover and personal work-control records",
        (
            "test_message_receipt_understanding_confirmation_and_expiry",
            "test_handover_uses_content_version_and_freshness",
            "test_personal_locks_restoration_and_permit_lifecycle",
            "test_conflicting_work_unknown_state_and_renewal",
        ),
    ),
    "G06": (
        "observations",
        "Observation-qualified counts, recovery, reported summaries and reviewed annualization",
        (
            "test_initial_recovered_final_and_missing_counts_are_distinct",
            "test_duplicate_exposure_overlap_and_late_recovery_rejected",
            "test_annualized_demands_include_missing_outcomes_and_require_context_time",
            "test_reported_observed_probability_preserves_missing_denominator",
        ),
    ),
    "G07": (
        "interventions",
        "Assumed model contrasts and static independent-event importance",
        (
            "test_intervention_changes_parameters_not_baseline",
            "test_intervention_never_retains_an_empirical_label_or_stale_posterior",
            "test_paired_inputs_and_analytical_importance",
        ),
    ),
    "G08": (
        "verification",
        "Finite net progress and serial atomic integer-grid deadline checks",
        (
            "test_possible_completion_is_not_inevitable_progress",
            "test_timed_deadline_quantifier_and_exact_boundary",
            "test_zero_time_cycle_is_not_a_deadline_proof",
            "test_compiler_preserves_dag_fanout_and_injects_errors",
        ),
    ),
    "G09": (
        "cognition",
        "Declared cue visibility, finite diagnostic beliefs and bounded polling",
        (
            "test_role_visible_delayed_cues_and_bayesian_diagnosis",
            "test_monitoring_dwell_capacity_and_budget",
        ),
    ),
    "G10": (
        "calibration",
        "Finite hyperprior mixtures, held-out scores and explicitly elicited distributions",
        (
            "test_finite_hyperprior_matches_conjugate_limit",
            "test_partial_pooling_grid_and_group_boundaries",
            "test_heldout_aggregate_brier_and_leakage",
            "test_elicitation_fitting_calibration_and_mixture",
        ),
    ),
    "G11": (
        "assurance",
        "Observed procedure conformance and explicit artifact/assumption lifecycle review",
        (
            "test_conformance_missingness_order_versions_and_restoration",
            "test_lifecycle_assumptions_hashes_claims_and_incident_lessons",
        ),
    ),
    "G12": (
        "method_workflows",
        "Selected SPAR-H/HEART calculations plus limited source-linked function/range workflows",
        (
            "test_spar_workflow_stage_union_recovery_and_assessment_integration",
            "test_heart_workflow_and_dependency_is_conditional",
            "test_idheas_source_selection_floor_and_placeholders",
            "test_cream_interval_requires_explicit_selection",
        ),
    ),
}


def main():
    report_path = ROOT / "research/verification_summary.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["all_passed"]:
        raise ValueError("software verification did not pass")
    actual = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_files(ROOT)
    }
    if actual != report["source_hashes"]:
        raise ValueError("verification is stale for extension acceptance")
    for name in (
        "operational_example",
        "documentation",
        "risk_cli",
        "coupled_cli",
        "workflow_cli",
        "risk_replay",
    ):
        if not any(c["name"] == name and c["exit_code"] == 0 for c in report["checks"]):
            raise ValueError("required extension execution not verified: " + name)
    cases = ET.parse(ROOT / "artifacts/tests.xml").getroot().findall(".//testcase")
    passed = {
        case.attrib["name"].split("[", 1)[0]
        for case in cases
        if not any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
    }
    requirements = {}
    for key, (module, scope, names) in REQUIREMENTS.items():
        if set(names) - passed:
            raise ValueError("missing passing acceptance cases: " + repr(set(names) - passed))
        requirements[key] = {
            "status": "passed_implemented_scope",
            "module": "src/human_reliability/" + module + ".py",
            "scope": scope,
            "passing_acceptance_tests": list(names),
        }
    example = json.loads((ROOT / "artifacts/operational_research/result.json").read_text(encoding="utf-8"))
    if (
        not example["authored_scenarios_are_not_field_calibration"]
        or example["risk"]["status"] != "evaluated"
    ):
        raise ValueError("operational example scope or execution incomplete")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    result = {
        "schema_version": "1",
        "version": version,
        "all_passed": True,
        "verification_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "pytest": report["pytest"],
        "requirements": requirements,
        "operational_example_risk_digest": example["risk"]["input_digest"],
        "field_calibration_claim": False,
        "full_official_method_system_claim": False,
        "source_publications_or_private_records_included": False,
    }
    (ROOT / "research/extension_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    matrix_path = ROOT / "research/extension_implementation.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["version"] = version
    matrix["status"] = "complete_at_documented_implemented_scopes"
    for item in matrix["items"]:
        item.update(requirements[item["id"]])
    matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    print("Recorded passing acceptance evidence for all 12 operational extensions.")


if __name__ == "__main__":
    main()
