"""Portable implementation fingerprint for the retained empirical evaluation."""

import hashlib


def field_inputs(root):
    names = [
        "scripts/field_verification_inputs.py",
        "scripts/run_field_studies.py",
        "scripts/acquire_field_data.py",
        "src/human_reliability/datasets.py",
        "src/human_reliability/evidence_catalog.py",
        "src/human_reliability/contracts.py",
        "research/field_assets.json",
        "research/field_protocol_deviations.json",
        "src/human_reliability/data/field_sources.json",
        "src/human_reliability/data/human_error_records.json",
    ]
    return sorted({*(root / name for name in names), *(root / "src/human_reliability").glob("field_*.py")})


def field_hashes(root):
    # Git normalizes text line endings. Fingerprint source text consistently on
    # Windows/Linux while raw acquired archives retain their exact byte hashes.
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for p in field_inputs(root)
    }
