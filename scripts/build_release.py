"""Build inspectable source and wheel artifacts after verification succeeds."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from verification_inputs import input_files

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / "research/verification_summary.json").read_text(encoding="utf-8"))
    if not report["all_passed"]:
        raise ValueError("recorded software verification has not passed")
    import hashlib

    current_names = {path.relative_to(ROOT).as_posix() for path in input_files(ROOT)}
    if current_names != set(report["source_hashes"]):
        raise ValueError("verification input file set changed since verification")
    for name, digest in report["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("source changed since verification: " + name)
    subprocess.run([sys.executable, "scripts/record_extension_validation.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "build"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/release_audit.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/smoke_install.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
