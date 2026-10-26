"""Original synthetic end-to-end collection example. No field observations are present."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from human_reliability.collection import (
    CodedOutcome, CollectionBundle, CollectionProtocol, CoverageWindow, Prediction,
    RegisteredDemand, TABLES, write_collection_kit,
)
from human_reliability.contracts import canonical_digest
from human_reliability.fault_tree import Event, Gate, fault_probability
from human_reliability.opportunity_validation import ValidationPlan, validate_collection
from human_reliability.probability import BetaPrior


def synthetic_collection():
    protocol = CollectionProtocol(
        id="synthetic-collection", version="1", source_id="authored-fixture", domain="synthetic_demo",
        task_id="verify-isolation", event_id="missed-verification",
        failure_definition="Authored Boolean fixture for missed verification by the deadline",
        opportunity_definition="One prelisted synthetic verification demand; retries do not add trials",
        conditioning="Synthetic fixture only; no operating plant inference", setting="synthetic",
        sampling="window_census", clock_id="simulation-relative", clock_origin_and_unit="relative seconds",
        frozen_at_s=0, coverage_review="All fixture rows enumerated by the generator",
        registry_review="Generator count reconciled independently of assigned outcomes",
        adjudication_rule="Synthetic fixture assignments, not actual raters",
        collection_authorization="Original authored software fixture", data_license="MIT-original-synthetic",
        license_evidence="Repository LICENSE", public_release_authorization="Original synthetic example only",
    )
    windows = (
        CoverageWindow(id="train", start_s=1, end_s=50, coverage_complete=True,
                       expected_register_rows=12, reconciliation_evidence="fixture-generator"),
        CoverageWindow(id="evaluation", start_s=100, end_s=200, coverage_complete=True,
                       expected_register_rows=24, reconciliation_evidence="fixture-generator"),
    )
    demands, outcomes, predictions = [], [], []
    for window, count, start in (("train", 12, 2), ("evaluation", 24, 101)):
        for index in range(count):
            identity = f"{window}-{index}"
            demands.append(RegisteredDemand(
                id=identity, source_event_id=identity, window_id=window, start_s=start + index,
                end_s=start + index + 0.5, deadline_s=start + index + 0.4,
                group_id=f"{window}-crew-{index // 4}", disposition="eligible",
                disposition_evidence="fixture-register",
                context={"procedure_version": "demo-v1", "shift": "day" if index % 2 else "night"},
                context_evidence="synthetic fixture assignment",
            ))
            unknown = window == "evaluation" and index in {22, 23}
            initial = None if unknown else index % 8 == 0
            final = None if unknown else index % 12 == 0
            outcomes.append(CodedOutcome(
                demand_id=identity, initial_error=initial, final_failure=final,
                followup_complete=not unknown, endpoint_adjudicated=not unknown,
                coder_id="synthetic-coder", adjudicator_id="synthetic-reviewer", evidence="fixture-outcome",
            ))
            if window == "evaluation":
                predictions.append(Prediction(demand_id=identity, model_id="fixed-demo", probability=0.1,
                                              issued_s=90))
    bundle = CollectionBundle(protocol, windows, tuple(demands), tuple(outcomes), (), tuple(predictions))
    plan = ValidationPlan(
        id="synthetic-plan", model_id="fixed-demo", estimand="final", evaluation_window_ids=("evaluation",),
        training_demand_ids=tuple(d.id for d in demands if d.window_id == "train"),
        training_group_ids=tuple(sorted({d.group_id for d in demands if d.window_id == "train"})),
        frozen_at_s=50, training_manifest_digest=canonical_digest({"model": "fixed-demo", "p": 0.1}),
        external_training_review="Fixture deliberately separates training and evaluation crews",
    )
    return bundle, plan


def save_synthetic(path):
    bundle, plan = synthetic_collection()
    write_collection_kit(path)
    path = Path(path)
    (path / "protocol.json").write_text(bundle.protocol.model_dump_json(indent=2), encoding="utf-8")
    (path / "validation-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    for (name, _), rows in zip(TABLES.items(),
                              (bundle.windows, bundle.demands, bundle.outcomes, bundle.recoveries, bundle.predictions)):
        with (path / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(TABLES[name].model_fields))
            writer.writeheader()
            for row in rows:
                writer.writerow({key: "" if value is None else json.dumps(value) if isinstance(value, dict)
                                 else str(value).lower() if type(value) is bool else value
                                 for key, value in row.model_dump().items()})
    return bundle, plan


def main():
    # Repeat execution keeps existing artifacts intact and uses a fresh directory.
    import tempfile

    artifact = Path("artifacts/field_collection")
    artifact.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="synthetic-", dir=artifact)) / "forms"
    bundle, plan = save_synthetic(path)
    result = validate_collection(bundle, plan, bootstrap_replicates=500)
    estimate = bundle.hep(
        estimand="final", prior=BetaPrior(alpha=1, beta=1, evidence_id="authored-demo-prior"),
        independence_review="Synthetic Bernoulli example only; no empirical independence claim",
        missingness_review="Two intentionally unknown fixture outcomes; bounds retained",
        window_ids=("evaluation",),
    )
    result["synthetic_posterior"] = estimate.model_dump(mode="json")
    leaf = Event(estimate.event_id)
    result["synthetic_fta_probability"] = fault_probability(Gate("OR", (leaf, leaf)),
                                                           {estimate.event_id: estimate.probability})
    (path / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"setting": result["setting"], "eligible": result["eligible_evaluation_demands"],
                      "unknown": result["unknown_outcomes"], "brier": result["metrics_complete_cases"]["brier"],
                      "industrial_hep_validated": False}))


if __name__ == "__main__":
    main()
