"""Trace a real observed context group into an explicitly illustrative risk model."""

from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path

from human_reliability import (
    ApplicabilityReview,
    BetaPrior,
    HumanFailureEvent,
    annual_frequency_from_evidence,
    builtin_evidence_catalog,
    sacada_context_labels,
)
from human_reliability.assessment import AssessmentCase, AssessmentEngine, ModelSpec
from human_reliability.event_tree import event_tree, protection_partition
from human_reliability.reference_methods import heart_profile_probability, spar_h_profile_probability


def main():
    catalog = builtin_evidence_catalog()
    # Select a pinned row, not a row chosen to obtain a favorable probability.
    record_id = "sacada.action.r0003"
    record = catalog.get(record_id)
    event = HumanFailureEvent(
        id="manual_action",
        task_id="demonstration",
        step_ids=("act",),
        role="response",
        failure_definition="An unsatisfactory manual action in the reviewed demonstration",
        opportunity_definition="One assessed manual-action demand in the demonstration",
        conditioning="Declared action context, conditional on an automatic failure",
        includes_recovery=True,
        includes_timing=True,
    )
    review = ApplicabilityReview(
        analyst="Example analyst",
        target_domain="illustrative_process_model",
        rationale="Demonstrate software handoff only. Transfer from nuclear simulator training is not field-qualified.",
        scope_rationale="The released UNSAT outcome does not separate lateness and recovery; lock both effects to avoid applying either twice.",
        included_effects=("timing", "recovery"),
    )
    binding = catalog.bind(
        record_id,
        event,
        review=review,
        prior=BetaPrior(alpha=0.5, beta=0.5, evidence_id="example_jeffreys_prior"),
    )
    initiating_frequency, automatic_success = 0.01, 0.9
    exposure = annual_frequency_from_evidence(
        binding.estimate,
        initiating_frequency * (1 - automatic_success),
        opportunity_definition=event.opportunity_definition,
        exposure_evidence="Example assumptions: 0.01 initiations/year and 0.9 automatic success; manual demands occur after automatic failure.",
    )
    ledger = event_tree(
        initiating_frequency,
        protection_partition(
            automatic_success,
            binding.estimate.probability,
            auto_evidence="Assumed automatic success probability",
            human_evidence=binding.evidence[0].id,
        ),
    )
    assert abs(ledger[-1]["annual_frequency_per_year"] - exposure["annual_frequency_per_year"]) < 1e-12
    levels = dict.fromkeys(
        (
            "available_time",
            "stress",
            "complexity",
            "experience_training",
            "procedures",
            "ergonomics",
            "fitness",
            "work_processes",
        ),
        "reference",
    )
    levels.update(complexity="moderate", experience_training="limited", procedures="weak")
    spar_value, spar_trace = spar_h_profile_probability("action", levels, catalog=catalog)
    heart_value, heart_trace = heart_profile_probability("G", (("heart.epc.2.v1", 0.25),), catalog=catalog)

    # Produce a JSON case runnable through the ordinary CLI without registering custom code.
    template = AssessmentCase.model_validate_json(
        files("human_reliability.data").joinpath("example_case.json").read_text()
    )
    bound_event = event.model_copy(
        update={
            "id": template.events[0].id,
            "task_id": template.task.id,
            "step_ids": template.events[0].step_ids,
        }
    )
    task = template.task.model_copy(update={"evidence": template.task.evidence + binding.evidence})
    specification = ModelSpec(
        method="evidence_catalog",
        evidence_ids=binding.estimate.evidence_ids,
        parameters={
            "record_id": record_id,
            "review": review.model_dump(mode="json"),
            "prior": {"alpha": 0.5, "beta": 0.5, "evidence_id": "example_jeffreys_prior"},
        },
    )
    case = template.model_copy(
        update={"task": task, "events": (bound_event,), "models": {bound_event.id: specification}}
    )
    result = AssessmentEngine().assess(case)
    assert result["estimates"][0]["probability"] == binding.estimate.probability
    destination = Path("artifacts/evidence_example")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "case.json").write_text(case.model_dump_json(indent=2), encoding="utf-8")
    output = {
        "observed_source_counts": {
            "unsatisfactory": record.failures,
            "opportunities": record.opportunities,
            "observed_fraction": record.observed_fraction,
        },
        "context": sacada_context_labels(record),
        "posterior": binding.estimate.model_dump(mode="json"),
        "illustrative_exposure_conversion": exposure,
        "illustrative_event_tree": ledger,
        "comparison_estimates": {
            "spar_h": {"probability": spar_value, "trace": spar_trace},
            "heart": {"probability": heart_value, "trace": heart_trace},
        },
        "comparison_methods_do_not_share_a_calibrated_context": True,
        "field_validation_claim": False,
    }
    (destination / "result.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_counts": output["observed_source_counts"],
                "posterior_probability": binding.estimate.probability,
                "derived_example_frequency_per_year": exposure["annual_frequency_per_year"],
                "json_case": "artifacts/evidence_example/case.json",
                "field_validation_claim": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
