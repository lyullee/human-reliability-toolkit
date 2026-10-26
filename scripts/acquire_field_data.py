"""Acquire only pinned, rights-reviewed field-study assets; never publish raw files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

from human_reliability.field_data import field_sources

ROOT = Path(__file__).resolve().parents[1]


def verified_assets(*, acquire=False, selected=None):
    manifest = json.loads((ROOT / "research/field_assets.json").read_text(encoding="utf-8"))
    sources = field_sources()
    names = {a["source_id"] for a in manifest["assets"]}
    if selected and set(selected) - names:
        raise ValueError("unknown selected asset source")
    report = []
    for asset in manifest["assets"]:
        if selected and asset["source_id"] not in selected:
            continue
        source = sources[asset["source_id"]]
        if source.license != "CC-BY-4.0":
            raise ValueError("asset is outside this study's reviewed reusable-data boundary")
        target = (ROOT / asset["path"]).resolve()
        if not target.is_relative_to((ROOT / "data/raw").resolve()):
            raise ValueError("asset destination leaves the ignored raw-data directory")
        if not target.exists():
            if not acquire:
                raise FileNotFoundError("pinned asset unavailable: " + asset["path"])
            with urllib.request.urlopen(asset["url"], timeout=45) as response:
                content = response.read(asset["bytes"] + 1)
            if len(content) != asset["bytes"] or hashlib.sha256(content).hexdigest() != asset["sha256"]:
                raise ValueError("download differs from pinned source version: " + asset["source_id"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".partial", delete=False) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            temporary.replace(target)
        content = target.read_bytes()
        if len(content) != asset["bytes"] or hashlib.sha256(content).hexdigest() != asset["sha256"]:
            raise ValueError("local source checksum mismatch: " + asset["path"])
        if asset["supplier_checksum"]:
            algorithm, digest = asset["supplier_checksum"].split(":", 1)
            if hashlib.new(algorithm, content).hexdigest() != digest:
                raise ValueError("supplier checksum mismatch: " + asset["path"])
        report.append(asset | {"license": source.license, "origin": source.origin, "verified": True})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", dest="selected")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    rows = verified_assets(acquire=not args.verify_only, selected=args.selected)
    result = {
        "version": "0.4.0",
        "assets": rows,
        "all_verified": True,
        "raw_assets_in_source_release": False,
        "license_terms": "DATA_LICENSES.md",
    }
    (ROOT / "research/field_acquisition.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verified_assets": len(rows), "bytes": sum(r["bytes"] for r in rows)}))


if __name__ == "__main__":
    main()
