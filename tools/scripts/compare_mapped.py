"""Strict comparator for old/new mapped KybgParser JSON results.

Usage:
    python tools/scripts/compare_mapped.py old_mapped.json new_mapped.json
    python tools/scripts/compare_mapped.py old_output_dir new_output_dir

Exit 0 only when every compared mapped value, type, list item and key matches.
This does not replace manually reviewed ground truth for correctness.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def compare_values(expected: Any, actual: Any, path: str = "$") -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if type(expected) is not type(actual):
        kind = "LOST_VALUE" if expected is not None and actual is None else "CHANGED_TYPE"
        return [{"path": path, "kind": kind, "expected": expected, "actual": actual}]
    if isinstance(expected, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child = f"{path}.{key}"
            if key not in expected:
                issues.append({"path": child, "kind": "NEW_KEY", "actual": actual[key]})
            elif key not in actual:
                issues.append({"path": child, "kind": "MISSING_KEY", "expected": expected[key]})
            else:
                issues.extend(compare_values(expected[key], actual[key], child))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            issues.append({"path": path, "kind": "CHANGED_LIST_LENGTH", "expected": len(expected), "actual": len(actual)})
        for index in range(min(len(expected), len(actual))):
            issues.extend(compare_values(expected[index], actual[index], f"{path}[{index}]"))
    elif expected != actual:
        issues.append({"path": path, "kind": "CHANGED_VALUE", "expected": expected, "actual": actual})
    return issues


def matched_files(baseline: Path, candidate: Path) -> list[tuple[Path, Path]]:
    if baseline.is_file() and candidate.is_file():
        return [(baseline, candidate)]
    if not baseline.is_dir() or not candidate.is_dir():
        raise ValueError("Both inputs must be JSON files or directories")
    originals = {
        path.relative_to(baseline): path
        for path in baseline.rglob("*_mapped.json")
    }
    current = {
        path.relative_to(candidate): path
        for path in candidate.rglob("*_mapped.json")
    }
    all_names = sorted(originals.keys() | current.keys())
    if not all_names:
        raise ValueError("No *_mapped.json files found")
    # Missing files are explicitly reported by main(), never silently ignored.
    return [(originals.get(name), current.get(name)) for name in all_names]


def compare_paths(baseline: Path, candidate: Path) -> list[dict[str, Any]]:
    issues = []
    for old, new in matched_files(baseline, candidate):
        if old is None or new is None:
            issues.append({"path": str(old or new), "kind": "MISSING_OUTPUT_FILE"})
            continue
        try:
            expected = json.loads(old.read_text(encoding="utf-8-sig"))
            actual = json.loads(new.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append({"path": str(new), "kind": "INVALID_JSON", "detail": str(exc)})
            continue
        for issue in compare_values(expected, actual):
            issue["file"] = str(new)
            issues.append(issue)
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare existing vs refactored mapped JSON exactly")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    args = parser.parse_args(argv)
    try:
        issues = compare_paths(args.baseline, args.candidate)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for issue in issues[:50]:
        print(f"{issue['kind']}: {issue['path']}")
    print(f"Mapped JSON parity: {'PASS' if not issues else 'FAIL'} ({len(issues)} differences)")
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
