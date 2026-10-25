"""Acquire pinned public assets; external data stays outside source releases."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import time
import urllib.request
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
AGENT = {"User-Agent": "HumanReliabilityToolkit/0.1 public research"}


def open_source(request, *, timeout=60):
    for attempt in range(5):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise
            delay = int(error.headers.get("Retry-After", 30 * (attempt + 1)))
            print(f"Source requested backoff ({error.code}), waiting {delay}s", flush=True)
            while delay > 0:
                part = min(delay, 30)
                time.sleep(part)
                delay -= part


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=45) as response:
        return json.load(response)


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".partial")
        with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=90) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
        temporary.replace(target)
    if expected:
        algorithm, value = expected.split(":", 1)
        if digest(target, algorithm) != value:
            raise ValueError(f"source checksum mismatch: {target.name}")
    return {
        "file": target.relative_to(ROOT).as_posix(),
        "bytes": target.stat().st_size,
        "sha256": digest(target),
        "url": url,
        "supplier_checksum": expected,
    }


class RangeReader(io.RawIOBase):
    """Bounded, validated HTTP ranges with a small block cache for ZIP members."""

    block_size = 65536

    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.blocks = {}
        self.transferred = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = (
            offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        )
        if self.position < 0:
            raise ValueError("negative range position")
        return self.position

    def read(self, length=-1):
        length = min(length if length >= 0 else self.size - self.position, self.size - self.position)
        if length <= 0:
            return b""
        if length > 8_000_000:
            raise ValueError("requested archive range exceeds bound")
        start, stop = self.position, self.position + length
        pieces = []
        for number in range(start // self.block_size, (stop - 1) // self.block_size + 1):
            block_start = number * self.block_size
            block_stop = min(block_start + self.block_size, self.size)
            if number not in self.blocks:
                headers = AGENT | {"Range": f"bytes={block_start}-{block_stop - 1}"}
                with open_source(urllib.request.Request(self.url, headers=headers), timeout=60) as response:
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range")
                        != f"bytes {block_start}-{block_stop - 1}/{self.size}"
                    ):
                        raise ValueError("server did not honor exact byte range")
                    data = response.read(block_stop - block_start + 1)
                if len(data) != block_stop - block_start:
                    raise ValueError("range length mismatch")
                self.blocks[number] = data
                self.transferred += len(data)
            pieces.append(
                self.blocks[number][max(0, start - block_start) : min(self.block_size, stop - block_start)]
            )
        self.position = stop
        return b"".join(pieces)


def cog_subject(asset):
    target = ROOT / "data/raw/cog_bci" / asset["key"].replace(".zip", "_behavioral.zip")
    manifest_path = target.with_suffix(".json")
    if target.exists() and manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old["sha256"] == digest(target):
            return old
        raise ValueError("existing COG subset checksum mismatch")
    reader = RangeReader(asset["links"]["self"], asset["size"])
    members = []
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    with (
        zipfile.ZipFile(reader) as remote,
        zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output,
    ):
        selected = [
            item
            for item in remote.infolist()
            if "/behavioral/" in item.filename and item.filename.endswith(".mat")
        ]
        if not selected:
            raise ValueError("no behavioral members in subject archive")
        for item in selected:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or item.file_size > 2_000_000:
                raise ValueError("invalid or oversized behavioral member")
            content = remote.read(item)  # zipfile verifies the original member CRC.
            output.writestr(item.filename, content)
            members.append(
                {
                    "path": item.filename,
                    "bytes": len(content),
                    "crc32": f"{item.CRC:08x}",
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    temporary.replace(target)
    result = {
        "file": target.relative_to(ROOT).as_posix(),
        "bytes": target.stat().st_size,
        "sha256": digest(target),
        "url": asset["links"]["self"],
        "archive_bytes": asset["size"],
        "archive_supplier_checksum": asset["checksum"],
        "full_archive_checksum_verified": False,
        "member_integrity": "source CRC32 plus retained SHA256; full EEG archive not downloaded",
        "range_bytes_transferred": reader.transferred,
        "members": members,
    }
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def acquire_one(entry, cache_root=None):
    key = entry["id"]
    results = []
    if key == "cog_bci":
        with ThreadPoolExecutor(max_workers=2) as executor:
            jobs = {executor.submit(cog_subject, asset): asset["key"] for asset in entry["remote_archives"]}
            for future in as_completed(jobs):
                results.append(future.result())
                print(f"COG behavioral subset {jobs[future]} verified", flush=True)
    else:
        for asset in entry["assets"]:
            target = ROOT / "data/raw" / key / asset["filename"]
            if cache_root and key not in {"hitl", "tep"} and not target.exists():
                cached = Path(cache_root) / key / "source.zip"
                if cached.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(cached, target)
            results.append(download(asset["url"], target, asset.get("checksum")))
    return {
        "id": key,
        "status": "acquired",
        "files": sorted(results, key=lambda x: x["file"]),
        "human_response_data": entry["human_response_data"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="Dataset IDs; default is every selected dataset")
    parser.add_argument(
        "--cache-root", type=Path, help="Optional previously downloaded UCI archive directory"
    )
    options = parser.parse_args()
    catalog = json.loads((ROOT / "research/datasets.json").read_text(encoding="utf-8"))
    chosen = [
        entry
        for entry in catalog["datasets"]
        if entry["status"] == "selected" and (options.only is None or entry["id"] in options.only)
    ]
    known = {entry["id"] for entry in chosen}
    if options.only and set(options.only) != known:
        parser.error("unknown or unselected dataset ID")
    report_path = ROOT / "research/acquisition.json"
    old = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"datasets": []}
    results = {row["id"]: row for row in old["datasets"]}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = {executor.submit(acquire_one, entry, options.cache_root): entry["id"] for entry in chosen}
        for future in as_completed(jobs):
            key = jobs[future]
            try:
                results[key] = future.result()
                print(f"{key}: acquired and checked", flush=True)
            except Exception as error:
                results[key] = {"id": key, "status": "failed", "error": str(error)}
                print(f"{key}: FAILED {error}", flush=True)
            report_path.write_text(
                json.dumps({"schema_version": "1", "datasets": list(results.values())}, indent=2),
                encoding="utf-8",
            )
    print(f"Finished in {time.monotonic() - started:.1f} seconds", flush=True)
    if any(results[key]["status"] != "acquired" for key in known):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
