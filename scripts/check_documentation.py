"""Check local Markdown links and execute the self-contained README Python example."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    documents = [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]
    missing = []
    for path in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"^(?:https?:|mailto:|#)", target):
                continue
            destination = path.parent / target.split("#", 1)[0]
            if not destination.exists():
                missing.append({"document": path.relative_to(ROOT).as_posix(), "target": target})
    if missing:
        raise ValueError("missing documentation targets: " + json.dumps(missing))
    examples = re.findall(r"```python\n(.*?)```", (ROOT / "README.md").read_text(encoding="utf-8"), re.S)
    if not examples:
        raise ValueError("expected a self-contained Python README example")
    namespace = {}
    with redirect_stdout(io.StringIO()):
        for index, code in enumerate(examples):
            exec(compile(code, f"README example {index + 1}", "exec"), namespace)
        guide = ROOT / "docs/OPERATIONAL_EXTENSIONS.md"
        standalone = [
            code
            for code in re.findall(r"```python\n(.*?)```", guide.read_text(encoding="utf-8"), re.S)
            if code.startswith("# executable\n")
        ]
        for index, code in enumerate(standalone):
            exec(compile(code, f"Operational guide example {index + 1}", "exec"), {})
    print(
        f"Checked {len(documents)} Markdown documents, {len(examples)} README and {len(standalone)} operational-guide Python example(s)."
    )


if __name__ == "__main__":
    main()
