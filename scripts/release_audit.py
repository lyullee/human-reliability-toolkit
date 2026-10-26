"""Inspect built distributions for the declared source-only publication boundary."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tarfile
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {"source_cache", "raw", "processed", "field_records", ".venv", "artifacts", ".git", "__pycache__"}
FORBIDDEN_SUFFIXES = {".pdf", ".xls", ".xlsx", ".xlsb", ".rdata", ".mat", ".npz", ".pkl", ".pickle"}


def inspect_member(name, content):
    path = Path(name)
    errors = []
    if set(path.parts) & FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        errors.append("excluded file type or directory: " + name)
    if len(content) > 2_000_000:
        errors.append("unexpectedly large source member: " + name)
    prefixes = (
        b"C:" + bytes([92]) + b"Users" + bytes([92]),
        b"C:" + b"/Users" + b"/",
        b"file:///" + b"C:" + b"/",
    )
    if any(prefix in content for prefix in prefixes):
        errors.append("workstation path in source member: " + name)
    if re.search(rb"(?:sk-proj-|ghp_|gho_|ghu_|github_pat_)[A-Za-z0-9_]{20,}", content):
        errors.append("credential-like literal: " + name)
    return errors


def main():
    results = []
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for package in sorted((ROOT / "dist").glob("*")):
        if (
            not package.name.startswith("human_reliability_toolkit-" + version + "-")
            and package.name != "human_reliability_toolkit-" + version + ".tar.gz"
        ):
            continue
        errors, names = [], []
        if package.suffix == ".whl":
            with zipfile.ZipFile(package) as source:
                for name in source.namelist():
                    if not name.endswith("/"):
                        names.append(name)
                        errors += inspect_member(name, source.read(name))
        elif package.name.endswith(".tar.gz"):
            with tarfile.open(package) as source:
                for member in source.getmembers():
                    if member.isfile():
                        names.append(member.name)
                        errors += inspect_member(member.name, source.extractfile(member).read())
        else:
            continue
        results.append({"package": package.name, "members": len(names), "errors": errors, "file_list": names})
    if len(results) != 2:
        raise ValueError("one wheel and one source archive expected")
    report = {
        "packages": results,
        "source_boundary_passed": all(not row["errors"] for row in results),
        "legal_clearance_claim": False,
    }
    (ROOT / "research/release_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_boundary_passed": report["source_boundary_passed"],
                "packages": [
                    {"package": row["package"], "members": row["members"], "errors": row["errors"]}
                    for row in results
                ],
            },
            indent=2,
        )
    )
    if not report["source_boundary_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
