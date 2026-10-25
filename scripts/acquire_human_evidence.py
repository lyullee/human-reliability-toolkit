"""Acquire checksum-pinned evidence assets, optionally importing ordinary browser downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-directory", type=Path)
    parser.add_argument("--only", nargs="*")
    options = parser.parse_args()
    manifest = json.loads((ROOT / "research/human_evidence_assets.json").read_text(encoding="utf-8"))
    known = {asset["source_id"] for asset in manifest["assets"]}
    if options.only is not None and set(options.only) - known:
        parser.error("unknown source ID")
    rows = []
    for asset in manifest["assets"]:
        if options.only is not None and asset["source_id"] not in options.only:
            continue
        destination = ROOT / asset["path"]
        if not destination.resolve().is_relative_to((ROOT / "data/raw/hra_evidence").resolve()):
            raise ValueError("asset destination escapes the raw evidence directory")
        result = dict(path=asset["path"], url=asset["url"], source_id=asset["source_id"])
        try:
            if (
                destination.exists()
                and hashlib.sha256(destination.read_bytes()).hexdigest() == asset["sha256"]
            ):
                payload, transport = destination.read_bytes(), "verified_cache"
            elif options.import_directory is not None:
                payload = (options.import_directory / destination.name).read_bytes()
                transport = "imported_source_download"
            else:
                request = urllib.request.Request(
                    asset["url"], headers={"User-Agent": "HumanReliabilityToolkit/0.2 evidence acquisition"}
                )
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = response.read()
                transport = "https"
            digest = hashlib.sha256(payload).hexdigest()
            if digest != asset["sha256"] or len(payload) != asset["bytes"]:
                raise ValueError("source bytes differ from the pinned version")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                pending = destination.with_suffix(destination.suffix + ".part")
                pending.write_bytes(payload)
                pending.replace(destination)
            result.update(status="acquired", sha256=digest, bytes=len(payload), transport=transport)
        except Exception as error:
            result.update(status="failed", error_type=type(error).__name__)
            if isinstance(error, urllib.error.HTTPError):
                result["http_status"] = error.code
            result["next_step"] = (
                "Use the linked official page in an ordinary browser, save the named asset, then rerun with --import-directory. Changed content requires a provenance review."
            )
        rows.append(result)
        print(destination.name, result["status"], flush=True)
    report = dict(
        schema_version="1",
        assets=rows,
        all_selected_acquired=all(row["status"] == "acquired" for row in rows),
    )
    (ROOT / "research/human_evidence_acquisition.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if not report["all_selected_acquired"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
