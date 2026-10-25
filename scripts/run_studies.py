"""Execute the frozen data protocol and preserve unfavorable findings."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from human_reliability import canonical_digest
from human_reliability.datasets import cog_behavior, hitl_tables
from human_reliability.studies import (
    cluster_bootstrap_rate,
    group_holdout,
    grouped_logistic,
    probability_metrics,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    protocol = json.loads((ROOT / "research/protocol.json").read_text(encoding="utf-8"))
    seed = protocol["seed"]
    results = {"protocol_digest": canonical_digest(protocol), "studies": {}}
    logs = hitl_tables(ROOT / "data/raw/hitl/source.zip")["simulator_logs"].copy()
    logs["poor_outcome"] = (logs["Overall Performance"] == "Poor").astype(int)
    result = grouped_logistic(logs, "poor_outcome", "Participant", features=("Group", "Scenario"), seed=seed)
    result["held_out_groups_digest"] = canonical_digest(result.pop("held_out_groups_digest_input"))
    results["studies"]["hitl"] = result
    data = cog_behavior((ROOT / "data/raw/cog_bci").glob("*_behavioral.zip"))
    pvt = data["vigilance"]
    train, test = group_holdout(pvt.participant, seed=seed)
    p = (pvt.loc[train, "source_error_flag"].sum() + 1) / (np.count_nonzero(train) + 2)
    flag_diagnostic = cluster_bootstrap_rate(
        pvt.source_error_flag.to_numpy(), pvt.participant.to_numpy(), seed=seed
    ) | {
        "holdout_prevalence_model": probability_metrics(
            pvt.loc[test, "source_error_flag"], np.full(np.count_nonzero(test), p)
        ),
        "train_participants": int(pvt.loc[train, "participant"].nunique()),
        "test_participants": int(pvt.loc[test, "participant"].nunique()),
    }
    patterns = [
        tuple(group.loc[group.source_error_flag, "trial"].tolist())
        for _, group in pvt.groupby(["participant", "session"])
    ]
    results["studies"]["cog_pvt"] = {
        "status": "withheld_flag_semantics",
        "hep_calibration_eligible": False,
        "sessions": len(patterns),
        "observations": len(pvt),
        "identical_positive_flag_positions": len(set(patterns)) == 1,
        "positive_positions_zero_based": list(patterns[0]) if len(set(patterns)) == 1 else None,
        "reason": "All released sessions have an identical error-flag pattern; event semantics require source clarification.",
        "retained_descriptive_flag_diagnostic": flag_diagnostic,
    }
    monitoring = data["monitoring"].loc[lambda frame: frame.duration_valid].copy()
    train, test = group_holdout(monitoring.participant, seed=seed)
    thresholds = np.quantile(monitoring.loc[train, "duration_native"], [0.5, 0.9, 0.95])
    coverage = [float((monitoring.loc[test, "duration_native"] <= value).mean()) for value in thresholds]
    results["studies"]["cog_monitoring"] = {
        "train_rows": int(train.sum()),
        "test_rows": int(test.sum()),
        "native_unit_training_quantiles_p50_p90_p95": thresholds.tolist(),
        "held_out_coverage": coverage,
        "unit": "source_native",
        "missed_alarm_hep_inferred": False,
        "conditioning": "positive finite observed responses only",
    }
    (ROOT / "research/study_results.json").write_text(
        json.dumps(results, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
