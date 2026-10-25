"""Install the built core wheel into a separate environment and exercise public APIs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    wheels = list((ROOT / "dist").glob("human_reliability_toolkit-" + version + "-*.whl"))
    if len(wheels) != 1:
        raise ValueError("exactly one built wheel required")
    wheel = wheels[0]
    (ROOT / "artifacts").mkdir(exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="core_wheel_env_", dir=ROOT / "artifacts"))
    venv.EnvBuilder(with_pip=True).create(target)
    executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    checks = []

    def run(name, arguments):
        completed = subprocess.run(
            [str(executable), "-I", *arguments],
            cwd=target,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (ROOT / "artifacts" / ("install_" + name + ".log")).write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        checks.append({"name": name, "exit_code": completed.returncode})
        if completed.returncode:
            raise RuntimeError("clean installation check failed: " + name)
        return completed.stdout

    run("wheel", ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(wheel)])
    probe = """
import json, pathlib, sys
import human_reliability
from human_reliability.fault_tree import Event, Gate, fault_probability
from human_reliability.probability import BetaPrior
from human_reliability import builtin_evidence_catalog
module_path = pathlib.Path(human_reliability.__file__).resolve()
assert module_path.is_relative_to(pathlib.Path(sys.prefix).resolve())
a = Event("a")
assert abs(fault_probability(Gate("OR", (a, a)), {"a": 0.2}) - 0.2) < 1e-12
assert BetaPrior(alpha=1, beta=1, evidence_id="authored").alpha == 1
catalog = builtin_evidence_catalog()
assert len(catalog.sources) == 7 and len(catalog.records) == 1334
assert catalog.get("sacada.action.r0003").failures == 1
print(json.dumps({"version": human_reliability.__version__, "installed_under_environment": True}))
"""
    installed = json.loads(run("api", ["-c", probe]))
    optional = json.loads(run("doctor", ["-m", "human_reliability", "doctor"]))
    run("schema", ["-m", "human_reliability", "schema"])
    run("evidence", ["-m", "human_reliability", "evidence", "summary"])
    run("template", ["-m", "human_reliability", "template", "case.json"])
    run("case", ["-m", "human_reliability", "run", "case.json", "--out", "result.json"])
    result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    assert result["estimates"] and not result["empirical_plant_validation_claim"]
    report = {
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "installed": installed,
        "optional_libraries": optional["optional_libraries"],
        "checks": checks,
        "all_passed": True,
        "environment_kind": "isolated_core_only",
    }
    (ROOT / "research/install_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
