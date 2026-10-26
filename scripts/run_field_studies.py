"""Run the frozen public-data protocol and retain unfavorable or withheld results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from human_reliability import canonical_digest
from human_reliability.field_studies import (
    evaluate_distillation,
    evaluate_gas_turbine,
    evaluate_rail_incidents,
    evaluate_sacada_contexts,
    evaluate_steel_energy,
    evaluate_water_properties,
)
from acquire_field_data import verified_assets
from field_verification_inputs import field_hashes

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=ROOT / "research/field_protocol.json")
    parser.add_argument("--out", type=Path, default=ROOT / "research/field_validation_results.json")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    assets = verified_assets()
    results = {
        "version": "0.4.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": canonical_digest(protocol),
        "protocol_file_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "asset_manifest_digest": canonical_digest(assets),
        "source_assets_verified": True,
        "human_field_hep_validated": False,
        "study_design": protocol["design"],
        "studies": {},
    }
    specifications, seed = protocol["studies"], protocol["seed"]
    studies = [
        (
            "gas_turbine",
            lambda: evaluate_gas_turbine(
                ROOT / "data/raw/gas_turbine/source.zip", specifications["gas_turbine"], seed=seed
            ),
        ),
        (
            "steel_energy",
            lambda: evaluate_steel_energy(
                ROOT / "data/raw/steel_energy/source.zip", specifications["steel_energy"], seed=seed
            ),
        ),
        (
            "continuous_distillation",
            lambda: evaluate_distillation(
                ROOT / "data/raw/continuous_distillation/source.zip",
                specifications["continuous_distillation"],
            ),
        ),
        (
            "water_thermodynamic_consistency",
            lambda: evaluate_water_properties(ROOT / "data/raw/continuous_distillation/source.zip"),
        ),
        (
            "rail_incidents",
            lambda: evaluate_rail_incidents(ROOT / "data/raw/rail_incidents/data_105cases_human_factors.csv"),
        ),
        ("sacada_context_validation", lambda: evaluate_sacada_contexts(seed=seed)),
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for name, run in studies:
        print("Evaluating " + name, flush=True)
        try:
            results["studies"][name] = run()
        except Exception as error:
            results["all_prespecified_studies_executed"] = False
            results["failed_study"] = name
            results["exception_type"] = type(error).__name__
            args.out.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            raise
        args.out.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    results["implementation_hashes"] = field_hashes(ROOT)
    results["implementation_hash_algorithm"] = "sha256_with_text_CRLF_normalized_to_LF"
    from importlib.metadata import version

    results["library_versions"] = {
        name: version(name) for name in ("numpy", "scipy", "pandas", "scikit-learn", "CoolProp")
    }
    results["all_prespecified_studies_executed"] = len(results["studies"]) == len(studies)
    results["statistical_accuracy_guarantee"] = False
    results["source_publications_or_raw_rows_included"] = False
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Recorded all six prespecified evaluations; field HEP qualification remains explicit.")


if __name__ == "__main__":
    main()
