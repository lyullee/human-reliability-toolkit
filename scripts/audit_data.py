"""Audit acquired data at its actual observation grain and retain source limitations."""

from __future__ import annotations

import json
import argparse
from pathlib import Path
import time
import zipfile

import numpy as np

from human_reliability import canonical_digest
from human_reliability import datasets

ROOT = Path(__file__).resolve().parents[1]


def shape(frame):
    return {
        "rows": len(frame),
        "columns": len(frame.columns),
        "missing_cells": int(frame.isna().sum().sum()),
        "column_names": list(map(str, frame.columns)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*")
    options = parser.parse_args()
    raw = ROOT / "data/raw"
    output = ROOT / "research/data_audit.json"
    results = json.loads(output.read_text(encoding="utf-8"))["datasets"] if output.exists() else {}
    for key in (
        "ai4i",
        "hydraulic",
        "metropt3",
        "gas_turbine",
        "water_treatment",
        "secom",
        "hitl",
        "cog_bci",
        "tep",
    ):
        if options.only is not None and key not in options.only:
            continue
        started = time.monotonic()
        try:
            archive = raw / key / "source.zip"
            if archive.exists():
                with zipfile.ZipFile(archive) as source:
                    if source.testzip() is not None:
                        raise ValueError("archive CRC failure")
            if key == "ai4i":
                frame = datasets.uci_ai4i(archive)
                result = shape(frame) | {
                    "origin": "synthetic",
                    "machine_failure_count": int(frame["Machine failure"].sum()),
                    "human_failure_labels": False,
                }
            elif key == "hydraulic":
                frame = datasets.uci_hydraulic(archive)
                nominal = (
                    (frame.cooler_condition == 100)
                    & (frame.valve_condition == 100)
                    & (frame.pump_leakage == 0)
                    & (frame.accumulator_bar == 130)
                )
                result = shape(frame) | {
                    "grain": "independent 60-second cycles",
                    "nominal_four_component_cycles": int(nominal.sum()),
                    "human_failure_labels": False,
                }
            elif key == "metropt3":
                frame = datasets.uci_metropt(archive)
                timestamp = next(column for column in frame if "timestamp" in str(column).lower())
                import pandas as pd

                clock = pd.to_datetime(frame[timestamp])
                result = shape(frame) | {
                    "source_rows": frame.attrs["source_rows"],
                    "row_stride": frame.attrs["stride"],
                    "observed_stride_median_seconds": float(clock.diff().dt.total_seconds().median()),
                    "human_failure_labels": False,
                    "fault_labels": "maintenance intervals require a separate interpretation",
                }
            elif key == "gas_turbine":
                frame = datasets.uci_gas_turbine(archive)
                result = shape(frame) | {
                    "source_files": int(frame.source_file.nunique()),
                    "human_failure_labels": False,
                }
            elif key == "water_treatment":
                frame = datasets.uci_water(archive)
                result = shape(frame) | {
                    "human_failure_labels": False,
                    "first_column": "source item/date identifier, not a numeric sensor",
                }
            elif key == "secom":
                frame, labels = datasets.uci_secom(archive)
                result = shape(frame) | {
                    "failed_items": int(np.count_nonzero(labels == 1)),
                    "grain": "manufactured item",
                    "human_failure_labels": False,
                }
            elif key == "hitl":
                tables = datasets.hitl_tables(archive)
                logs = tables["simulator_logs"]
                result = {
                    "sheets": {name: shape(frame) for name, frame in tables.items()},
                    "participant_info_count": int(tables["participant_info"].Participant.nunique()),
                    "logged_participants": int(logs.Participant.nunique()),
                    "scenario_rows": len(logs),
                    "duplicate_participant_group_scenario_keys": int(
                        logs.duplicated(["Participant", "Group", "Scenario"]).sum()
                    ),
                    "outcome_counts": logs["Overall Performance"].value_counts().to_dict(),
                    "consequence_counts": logs.Consequence.value_counts().to_dict(),
                    "limitations": [
                        "record overview describes a broader study than the released logs",
                        "scenario summaries, not individual alarm-opportunity records",
                        "time-column units and censor semantics unresolved",
                        "Accuracy is not constrained to [0,1]; do not treat it as HEP",
                    ],
                }
            elif key == "cog_bci":
                values = datasets.cog_behavior((raw / key).glob("*_behavioral.zip"))
                monitoring, vigilance = values["monitoring"], values["vigilance"]
                patterns = [
                    tuple(np.flatnonzero(frame.source_error_flag.to_numpy()).tolist())
                    for _, frame in vigilance.groupby(["participant", "session"], sort=True)
                ]
                identical = bool(patterns) and len(set(patterns)) == 1
                result = {
                    "behavioral_archives": len(list((raw / key).glob("*_behavioral.zip"))),
                    "monitoring_rows": len(monitoring),
                    "vigilance_rows": len(vigilance),
                    "monitoring_participants": int(monitoring.participant.nunique()),
                    "vigilance_participants": int(vigilance.participant.nunique()),
                    "source_error_flags": int(vigilance.source_error_flag.sum()),
                    "hep_calibration_eligible": False,
                    "sessions": len(patterns),
                    "identical_error_flag_positions": identical,
                    "positive_positions_zero_based": list(patterns[0]) if identical else None,
                    "error_flag_pattern_issue": "Identical session flags require source clarification."
                    if identical
                    else None,
                    "invalid_monitoring_durations": int((~monitoring.duration_valid).sum()),
                    "unsupported_objects": len(values["unsupported"]),
                    "limitations": [
                        "opaque MATLAB tables are not decoded or silently converted",
                        "SYSMON first column retained as source alarm code, not timestamp",
                        "observed response times do not reveal all missed-alarm opportunities",
                        "native duration units require explicit mapping before physical deadline use",
                        "vigilance errors are experimental task outcomes, not chemical-plant HEP",
                    ],
                }
            else:
                frame = datasets.tep_rdata(raw / key / "TEP_FaultFree_Training.RData")
                result = shape(frame) | {
                    "audited_file": "TEP_FaultFree_Training.RData",
                    "all_four_files_acquired": True,
                    "human_failure_labels": False,
                    "other_large_tables_loaded": False,
                    "limitations": [
                        "fault labels and manipulated process variables are not human failure labels"
                    ],
                }
            results[key] = {"status": "audited", "elapsed_s": round(time.monotonic() - started, 3)} | result
            print(key, "audited", flush=True)
        except Exception as error:
            results[key] = {"status": "failed", "error": str(error)}
            print(key, "FAILED", error, flush=True)
        (ROOT / "research/data_audit.json").write_text(
            json.dumps(
                {"schema_version": "1", "datasets": results, "audit_digest": canonical_digest(results)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if any(result["status"] != "audited" for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
