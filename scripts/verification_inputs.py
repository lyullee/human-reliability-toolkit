"""Shared release gate covers executable source and the numeric data it loads."""

from pathlib import Path


def input_files(root: Path):
    paths = set()
    for folder in ("src", "tests", "scripts", "examples"):
        paths.update((root / folder).rglob("*.py"))
    paths.update((root / "src").rglob("*.json"))
    paths.add(root / "pyproject.toml")
    paths.add(root / "MANIFEST.in")
    paths.update(root.glob("*.md"))
    paths.update((root / "docs").glob("*.md"))
    paths.add(root / "CITATION.cff")
    paths.add(root / ".gitignore")
    paths.update((root / ".github").rglob("*.yml"))
    for name in (
        "human_evidence_assets.json",
        "human_method_profiles.json",
        "field_assets.json",
        "field_protocol.json",
        "field_protocol_deviations.json",
    ):
        paths.add(root / "research" / name)
    return sorted(paths)
