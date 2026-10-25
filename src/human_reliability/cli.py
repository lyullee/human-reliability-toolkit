"""Local JSON workflow for reproducible assessments and extension-friendly APIs."""

from __future__ import annotations

import argparse
from importlib.resources import files
import json
from pathlib import Path

from .assessment import AssessmentCase, AssessmentEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    template = actions.add_parser("template", help="Write an original illustrative input case")
    template.add_argument("path", type=Path)
    run = actions.add_parser("run", help="Evaluate a JSON case")
    run.add_argument("case", type=Path)
    run.add_argument("--out", type=Path, required=True)
    actions.add_parser("schema", help="Print the versioned case JSON schema")
    actions.add_parser("doctor", help="Report installed optional calculation libraries")
    evidence = actions.add_parser(
        "evidence", help="Inspect or search the packaged human-performance evidence"
    )
    evidence.add_argument("view", choices=("sources", "summary", "search", "show"))
    evidence.add_argument("record_id", nargs="?")
    for name in ("kind", "function", "method", "domain", "source-id", "text"):
        evidence.add_argument("--" + name)
    evidence.add_argument("--condition", action="append", default=[], metavar="FIELD=JSON_VALUE")
    evidence.add_argument("--limit", type=int, default=10)
    evidence.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "evidence":
        from collections import Counter
        from .evidence_catalog import builtin_evidence_catalog, sacada_context_labels

        catalog = builtin_evidence_catalog()
        if args.view == "sources":
            result = [source.model_dump(mode="json") for source in catalog.sources.values()]
        elif args.view == "summary":
            result = {
                "sources": len(catalog.sources),
                "records": len(catalog.records),
                "by_kind": dict(Counter(row.kind for row in catalog.records.values())),
                "observed_annual_frequency_records": 0,
            }
        elif args.view == "show":
            if args.record_id is None:
                parser.error("show requires a record ID")
            row = catalog.get(args.record_id)
            result = {
                "record": row.model_dump(mode="json"),
                "source": catalog.sources[row.source_id].model_dump(mode="json"),
            }
            if row.source_id == "sacada_2019":
                result["context_labels"] = sacada_context_labels(row)
        else:
            if args.limit <= 0:
                parser.error("limit must be positive")
            conditions = {}
            for value in args.condition:
                if "=" not in value:
                    parser.error("condition must use FIELD=JSON_VALUE")
                key, literal = value.split("=", 1)
                if key in conditions:
                    parser.error("condition field repeated")
                conditions[key] = json.loads(literal)
            matches = catalog.search(
                kind=args.kind,
                function=args.function,
                method=args.method,
                domain=args.domain,
                source_id=args.source_id,
                conditions=conditions,
                text=args.text,
            )
            result = {
                "matched": len(matches),
                "returned": min(args.limit, len(matches)),
                "records": [row.model_dump(mode="json") for row in matches[: args.limit]],
                "selection_is_not_applicability_approval": True,
            }
        output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output, encoding="utf-8")
        else:
            print(output)
    elif args.action == "doctor":
        import importlib.util
        from . import __version__

        print(
            json.dumps(
                {
                    "version": __version__,
                    "optional_libraries": {
                        name: importlib.util.find_spec(name) is not None
                        for name in ("pandas", "sklearn", "lifelines", "CoolProp", "SALib", "dd", "rdata")
                    },
                },
                indent=2,
            )
        )
    elif args.action == "schema":
        print(json.dumps(AssessmentCase.model_json_schema(), indent=2))
    elif args.action == "template":
        if args.path.exists():
            parser.error("template destination already exists")
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(
            files("human_reliability.data").joinpath("example_case.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        case = AssessmentCase.model_validate_json(args.case.read_text(encoding="utf-8"))
        result = AssessmentEngine().assess(case)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        print(f"Evaluated {len(result['estimates'])} events; input {result['input_digest']}")


if __name__ == "__main__":
    main()
