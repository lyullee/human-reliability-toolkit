"""Check retained empirical evidence against its protocol, implementation and asset manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from human_reliability import canonical_digest
from field_verification_inputs import field_hashes

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-assets", action="store_true")
    args = parser.parse_args()
    report = json.loads((ROOT / "research/field_validation_results.json").read_text(encoding="utf-8"))
    protocol = json.loads((ROOT / "research/field_protocol.json").read_text(encoding="utf-8"))
    if report["protocol_digest"] != canonical_digest(protocol) or report[
        "implementation_hashes"
    ] != field_hashes(ROOT):
        raise ValueError("retained empirical evaluation is stale for its protocol or implementation")
    expected = {
        "gas_turbine",
        "steel_energy",
        "continuous_distillation",
        "water_thermodynamic_consistency",
        "rail_incidents",
        "sacada_context_validation",
    }
    if not report["all_prespecified_studies_executed"] or set(report["studies"]) != expected:
        raise ValueError("not all prespecified empirical evaluations completed")
    if report["human_field_hep_validated"] or any(
        s["human_field_validation"] for s in report["studies"].values()
    ):
        raise ValueError("these public datasets do not establish chemical-process field HEP validity")
    if args.require_assets:
        from acquire_field_data import verified_assets

        if report["asset_manifest_digest"] != canonical_digest(verified_assets()):
            raise ValueError("asset manifest or verified source bytes differ from empirical evaluation")
    print(
        json.dumps(
            {
                "prespecified_studies": len(expected),
                "retained_record_current": True,
                "raw_source_bytes_reverified": args.require_assets,
                "human_field_hep_validated": False,
            }
        )
    )


if __name__ == "__main__":
    main()
