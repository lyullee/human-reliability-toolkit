"""Record versions and declared dependency licenses without workstation paths."""

from __future__ import annotations

import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    distributions = []
    requirements = []
    for distribution in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        info = distribution.metadata
        name = info["Name"]
        if name.lower() == "human-reliability-toolkit":
            continue
        declared = info.get("License-Expression") or info.get("License", "")
        # Long embedded license texts remain in the installed distributions.
        if len(declared) > 160:
            declared = declared.splitlines()[0][:160]
        classifiers = [value for value in info.get_all("Classifier", []) if value.startswith("License ::")]
        distributions.append(
            {
                "name": name,
                "version": distribution.version,
                "declared_license": declared,
                "license_classifiers": classifiers,
            }
        )
        requirements.append(f"{name}=={distribution.version}")
    report = {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "packages": distributions,
        "universal_platform_lock_claim": False,
    }
    (ROOT / "research/environment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "requirements-validated.txt").write_text(
        "# Recorded Windows Python 3.12 development/test environment, not a universal lock.\n"
        + "\n".join(requirements)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Recorded {len(distributions)} installed distributions; Python {sys.version_info.major}.{sys.version_info.minor}"
    )


if __name__ == "__main__":
    main()
