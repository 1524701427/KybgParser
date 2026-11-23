"""Inspect existing first/second stage extraction details without rerunning the parser.

Usage:
    python tools/scripts/audit_candidate_facts.py data/predictions/PROJECT_details.json
    python tools/scripts/audit_candidate_facts.py data/predictions/PROJECT_details.json --output /tmp/PROJECT_candidate_facts.json
    python tools/scripts/audit_candidate_facts.py primary.json --secondary-detail secondary.json --output candidate_facts.json

The original *_details.json, *_result.json, *_mapped.json files are never changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from word_parser.extraction.candidate_facts import candidate_fact_report


def _read_json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unify primary/secondary candidate evidence for read-only audit")
    parser.add_argument("primary_detail", type=Path, help="Existing PROJECT_details.json (may embed secondary details)")
    parser.add_argument("--secondary-detail", type=Path, help="Optional standalone secondary detail JSON")
    parser.add_argument("--output", type=Path, help="Optional separate audit output file")
    parser.add_argument("--exclude-nil", action="store_true", help="Omit secondary NIL attempts from audit report")
    args = parser.parse_args(argv)

    try:
        primary = _read_json_object(args.primary_detail)
        secondary = _read_json_object(args.secondary_detail) if args.secondary_detail else None
        report = candidate_fact_report(primary, secondary, include_nil=not args.exclude_nil)
        if args.output is not None:
            destination = args.output.resolve()
            protected = {args.primary_detail.resolve()}
            if args.secondary_detail is not None:
                protected.add(args.secondary_detail.resolve())
            if destination in protected or destination.name.endswith(("_mapped.json", "_result.json", "_details.json")):
                raise ValueError("Audit output must not overwrite any parser result, mapped JSON or detail file")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Candidate audit error: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    counts = summary["countsByStage"]
    print(
        f"Candidate audit | total={summary['totalFacts']} "
        f"primary={counts['primary']} secondary_fields={counts['secondary_field']} "
        f"secondary_tables={counts['secondary_table']} "
        f"nil={summary['nilCount']} missing_codes={summary['missingCodeCount']} "
        f"value_variation_groups={summary['valueVariationGroupCount']}"
    )
    if args.output:
        print(f"Read-only audit report: {args.output}")
    if summary["valueVariationGroupCount"]:
        print("Value variations are observations only, not automatic error verdicts or selected final values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
