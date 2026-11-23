"""Run identical real reports in two KybgParser worktrees and compare outputs.

This performs actual PDF/Word/Aspose/OCR extraction with the same interpreter
and environment. It does NOT assume passing unit tests proves business parity.
It writes generated result files only to the specified regression output folder.

Example (Windows Git Bash):
    python tools/scripts/run_real_report_parity.py \
      --baseline-root ../KybgParser-main --candidate-root . \
      --report "samples/reports/5.陕西华电咸阳永寿常宁镇10万千瓦风电项目可行性研究报告.docx" \
      --out-dir ../KybgParser-parity-results

Any nonzero difference exits 1, extraction failure exits 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


# The child process sets the original parser's output directory explicitly;
# neither the baseline nor candidate repository's tracked prediction files are
# used as output destinations.
CHILD_CODE = r'''
import json
import sys
from pathlib import Path
from word_parser.application.factory import create_default_parser
from word_parser.application.workflow import run_full_parse
root, source, output = (Path(item).resolve() for item in sys.argv[1:4])
service = create_default_parser(config_root=root / "configs")
service.pipeline.exporter.output_dir = output
result = run_full_parse(
    service,
    str(source),
    config_root=root / "configs",
    table_value_config=root / "configs" / "table_field_extractors.yaml",
)
print("KYBG_PARITY_DONE=" + json.dumps(result.get("outputFiles") or {}, ensure_ascii=False))
'''


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _different(expected: Any, actual: Any, path: str = "$") -> list[dict[str, Any]]:
    """Do not coerce 0/False, integers/floats, null/empty, or table rows."""
    changes: list[dict[str, Any]] = []
    if type(expected) is not type(actual):
        return [{"path": path, "type": "TYPE_CHANGED",
                 "old": expected, "new": actual}]
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            next_path = f"{path}.{key}"
            if key not in expected:
                changes.append({"path": next_path, "type": "ADDED", "new": actual[key]})
            elif key not in actual:
                changes.append({"path": next_path, "type": "REMOVED", "old": expected[key]})
            else:
                changes.extend(_different(expected[key], actual[key], next_path))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            changes.append({"path": path, "type": "LIST_LENGTH",
                            "old": len(expected), "new": len(actual)})
        for index in range(min(len(expected), len(actual))):
            changes.extend(_different(expected[index], actual[index], f"{path}[{index}]"))
    elif expected != actual:
        changes.append({"path": path, "type": "VALUE_CHANGED",
                        "old": expected, "new": actual})
    return changes


def _output_path(folder: Path, report: Path, suffix: str) -> Path:
    safe_stem = "".join(c if c not in '<>:"/\\|?*' else "_" for c in report.stem) or "parse_result"
    return folder / f"{safe_stem}_{suffix}.json"


def compare_outputs(baseline: Path, candidate: Path, report: Path) -> dict[str, Any]:
    """Require both mapped *and* final result parity for a report."""
    result: dict[str, Any] = {"report": str(report), "differences": [], "error": None}
    for suffix in ("mapped", "result"):
        old_path = _output_path(baseline, report, suffix)
        new_path = _output_path(candidate, report, suffix)
        if not old_path.is_file() or not new_path.is_file():
            result["error"] = f"Missing {suffix} output: {old_path} or {new_path}"
            return result
        try:
            old = _read_json(old_path)
            new = _read_json(new_path)
        except (OSError, json.JSONDecodeError) as exc:
            result["error"] = f"Could not read {suffix} output: {exc}"
            return result
        changes = _different(old, new)
        result["differences"].extend({"output": suffix, **item} for item in changes)
    return result


def run_one(root: Path, report: Path, target_dir: Path, python_path: str, timeout: int) -> dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [python_path, "-c", CHILD_CODE, str(root), str(report), str(target_dir)],
            cwd=root,
            text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exitCode": -1, "error": str(exc)}
    # Do not put entire report text or parsed values in console logs.
    error_lines = completed.stderr.strip().splitlines()
    return {
        "exitCode": completed.returncode,
        "error": "\n".join(error_lines[-12:]) if completed.returncode else None,
        "completedMarker": "KYBG_PARITY_DONE=" in completed.stdout,
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Run real reports in baseline and candidate parsers, compare final JSON")
    cli.add_argument("--baseline-root", type=Path, required=True)
    cli.add_argument("--candidate-root", type=Path, required=True)
    cli.add_argument("--report", type=Path, action="append", required=True,
                     help="One report path; repeat flag for multiple reports")
    cli.add_argument("--out-dir", type=Path, required=True)
    cli.add_argument("--python", default=sys.executable,
                     help="Interpreter with the same OCR/Aspose dependencies for both versions")
    cli.add_argument("--timeout-seconds", type=int, default=1800)
    args = cli.parse_args(argv)

    baseline, candidate = args.baseline_root.resolve(), args.candidate_root.resolve()
    out_dir = args.out_dir.resolve()
    if not baseline.is_dir() or not candidate.is_dir() or baseline == candidate:
        cli.error("baseline-root and candidate-root must be distinct existing directories")
    if out_dir == baseline or baseline in out_dir.parents or out_dir == candidate or candidate in out_dir.parents:
        cli.error("out-dir must be outside both source worktrees to protect tracked outputs")
    if args.timeout_seconds <= 0:
        cli.error("timeout-seconds must be >0")
    if not (baseline / "word_parser" / "application" / "factory.py").is_file():
        cli.error("baseline-root does not appear to be a KybgParser checkout")
    if not (candidate / "word_parser" / "application" / "factory.py").is_file():
        cli.error("candidate-root does not appear to be a KybgParser checkout")

    cases = []
    failed = False
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(args.report, start=1):
        report = path.resolve()
        if not report.is_file():
            cli.error(f"Missing report: {path}")
        if report.suffix.lower() not in (".doc", ".docx", ".pdf"):
            cli.error(f"Unsupported report extension: {report.suffix}")
        token = hashlib.sha256(str(report).encode("utf-8")).hexdigest()[:10]
        case_dir = out_dir / f"{index:03d}_{token}"
        old_dir, new_dir = case_dir / "baseline", case_dir / "candidate"
        print(f"[{index}/{len(args.report)}] {report.name}", flush=True)
        old_run = run_one(baseline, report, old_dir, args.python, args.timeout_seconds)
        new_run = run_one(candidate, report, new_dir, args.python, args.timeout_seconds)
        entry: dict[str, Any] = {
            "report": str(report), "baselineRun": old_run, "candidateRun": new_run
        }
        if old_run["exitCode"] != 0 or new_run["exitCode"] != 0:
            entry["error"] = "Baseline or candidate extraction failed"
            entry["differences"] = []
            failed = True
        else:
            comparisons = compare_outputs(old_dir, new_dir, report)
            entry.update(comparisons)
            failed = failed or bool(entry.get("error") or entry["differences"])
        cases.append(entry)
        print(f"  differences={len(entry['differences'])} error={entry.get('error') or 'none'}", flush=True)

    summary = {
        "reportCount": len(cases),
        "passed": sum(not case.get("error") and not case["differences"] for case in cases),
        "failed": sum(bool(case.get("error") or case["differences"]) for case in cases),
        "differenceCount": sum(len(case["differences"]) for case in cases),
    }
    report_path = out_dir / "regression_summary.json"
    report_path.write_text(
        json.dumps({"summary": summary, "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Parity: {summary['passed']}/{summary['reportCount']} passed, "
          f"{summary['differenceCount']} differences; report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
