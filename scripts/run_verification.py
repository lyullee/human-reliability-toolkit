"""Run necessary software checks and save compact, machine-readable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from verification_inputs import input_files

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrations", action="store_true")
    options = parser.parse_args()
    artifact = ROOT / "artifacts"
    artifact.mkdir(exist_ok=True)
    checks = []

    def run(name, command):
        started = time.monotonic()
        completed = subprocess.run(
            command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True
        )
        checks.append(
            {
                "name": name,
                "exit_code": completed.returncode,
                "elapsed_s": round(time.monotonic() - started, 3),
            }
        )
        print(name, "PASS" if completed.returncode == 0 else "FAIL", flush=True)
        (artifact / (name + ".log")).write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            print((completed.stdout + completed.stderr)[-16000:], flush=True)
        return completed.returncode == 0

    run("lint", [sys.executable, "-m", "ruff", "check", "src", "scripts", "tests", "examples"])
    run("tests", [sys.executable, "-m", "pytest", "-q", "-W", "error", "--junitxml=artifacts/tests.xml"])
    run("python_example", [sys.executable, "examples/python_api.py"])
    run("evidence_example", [sys.executable, "examples/evidence_to_risk.py"])
    run("operational_example", [sys.executable, "examples/operational_research.py"])
    run("field_example", [sys.executable, "examples/field_evidence.py"])
    run("collection_example", [sys.executable, "examples/field_collection.py"])
    run("opportunity_benchmarks_cli", [sys.executable, "-m", "human_reliability", "opportunity-benchmarks"])
    run("field_sources_cli", [sys.executable, "-m", "human_reliability", "field-sources"])
    run("field_empirical_record", [sys.executable, "scripts/check_field_record.py"])
    run("evidence_cli", [sys.executable, "-m", "human_reliability", "evidence", "summary"])
    run("documentation", [sys.executable, "scripts/check_documentation.py"])
    with tempfile.TemporaryDirectory(dir=artifact) as directory:
        destination = Path(directory)
        run("collection_template_cli", [sys.executable, "-m", "human_reliability", "collection-template",
                                        str(destination / "collection")])
        run(
            "cli_template",
            [sys.executable, "-m", "human_reliability", "template", str(destination / "case.json")],
        )
        run(
            "cli_run",
            [
                sys.executable,
                "-m",
                "human_reliability",
                "run",
                str(destination / "case.json"),
                "--out",
                str(destination / "result.json"),
            ],
        )
        for family in ("risk", "coupled", "workflow"):
            case_path, result_path = destination / (family + ".json"), destination / (family + "-result.json")
            run(
                family + "_template",
                [sys.executable, "-m", "human_reliability", family + "-template", str(case_path)],
            )
            run(
                family + "_cli",
                [
                    sys.executable,
                    "-m",
                    "human_reliability",
                    family + "-run",
                    str(case_path),
                    "--out",
                    str(result_path),
                ],
            )
        run(
            "risk_replay",
            [
                sys.executable,
                "-m",
                "human_reliability",
                "risk-run",
                "artifacts/operational_research/risk_case.json",
                "--out",
                str(destination / "risk-replay.json"),
            ],
        )
    if options.integrations:
        run("integration_objects", [sys.executable, "scripts/check_integrations.py"])
    hashes = {}
    for path in input_files(ROOT):
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    pytest_counts = {}
    xml_path = artifact / "tests.xml"
    if xml_path.exists():
        suite = ET.parse(xml_path).getroot().find("testsuite")
        if suite is not None:
            pytest_counts = {
                name: int(suite.attrib.get(name, "0")) for name in ("tests", "failures", "errors", "skipped")
            }
    report = {
        "schema_version": "2",
        "checks": checks,
        "pytest": pytest_counts,
        "source_hashes": hashes,
        "all_passed": all(check["exit_code"] == 0 for check in checks),
        "physical_or_human_field_validation_claim": False,
    }
    (ROOT / "research/verification_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
