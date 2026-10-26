"""Recompute the public aggregate benchmark without reconstructing individual records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from human_reliability.contracts import canonical_digest
from human_reliability.field_validation import aggregate_binomial_metrics
from human_reliability.opportunity_validation import opportunity_benchmarks, zero_error_plan

ROOT = Path(__file__).resolve().parents[1]


def compute():
    protocol = json.loads((ROOT / "research/denominator_protocol.json").read_text(encoding="utf-8"))
    source = opportunity_benchmarks()["sources"][0]
    rows = source["rows"]
    for row in rows:
        if any(type(row[k]) is not int or row[k] < 0 for k in ("successes", "failures", "opportunities")):
            raise ValueError("nonnegative integer aggregate counts required")
        if row["successes"] + row["failures"] != row["opportunities"]:
            raise ValueError("aggregate denominator mismatch")
    if len({r["period"] for r in rows}) != len(rows):
        raise ValueError("duplicate aggregate period")
    train = [r for r in rows if r["period"] in protocol["train_periods"]]
    test = [r for r in rows if r["period"] in protocol["evaluation_periods"]]
    if (set(protocol["train_periods"]) & set(protocol["evaluation_periods"]) or
            len(train) != len(protocol["train_periods"]) or len(test) != len(protocol["evaluation_periods"])):
        raise ValueError("nonoverlapping complete declared periods required")
    k, n = sum(r["failures"] for r in train), sum(r["opportunities"] for r in train)
    p = (k + 1) / (n + 2)
    result = aggregate_binomial_metrics(
        [r["failures"] for r in test], [r["opportunities"] for r in test], [p] * len(test)
    )
    inputs = ["research/denominator_protocol.json", "scripts/run_denominator_study.py",
              "src/human_reliability/opportunity_validation.py", "src/human_reliability/field_validation.py",
              "src/human_reliability/data/opportunity_benchmarks.json"]
    return {
        "schema_version": "1", "source_id": source["id"], "protocol_digest": canonical_digest(protocol),
        "input_sha256_lf": {name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                            for name in inputs},
        "count_audit": {"successes": sum(r["successes"] for r in rows),
                        "failures": sum(r["failures"] for r in rows),
                        "opportunities": sum(r["opportunities"] for r in rows)},
        "training": {"failures": k, "opportunities": n, "prior_alpha": 1, "prior_beta": 1,
                     "posterior_mean_prediction": p},
        "evaluation": result,
        "monthly_calibration": [r | {"prediction": p, "observed_fraction": r["failures"] / r["opportunities"]}
                                for r in test],
        "zero_error_planning": [zero_error_plan(t, independence_review="Planning assumption only; effective independent trials must be justified.")
                                for t in (0.001, 0.0001)],
        "finding": "Training-period prediction overstates the later observed composite rate; temporal calibration is not established.",
        "industrial_hep_validated": False, "adjudicated_human_field_hep_validated": False,
        "simulated_data_used_in_this_benchmark": False,
    }


def main():
    report = compute()
    path = ROOT / "research/denominator_validation_results.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("count_audit", "training", "evaluation", "finding")}, indent=2))


if __name__ == "__main__":
    main()
