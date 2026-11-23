"""Smoke-test real reports against one KybgParser worktree when old main itself crashes.

This is intentionally *not* a parity test. It guards previously crashing input
coverage and requires genuine mapped output rather than treating two failures
as equivalent. Actual business parity still requires a working baseline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_real_report_parity import _output_path, run_one


def _present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_present(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_present(v) for v in value)
    return True


def main(argv=None):
    cli = argparse.ArgumentParser(description="Run previously crashing real DOCX inputs through refactored parser")
    cli.add_argument("--candidate-root", required=True, type=Path)
    cli.add_argument("--report", type=Path, action="append", required=True)
    cli.add_argument("--out-dir", type=Path, required=True)
    cli.add_argument("--python", default=sys.executable)
    cli.add_argument("--timeout-seconds", type=int, default=900)
    args = cli.parse_args(argv)

    root, out = args.candidate_root.resolve(), args.out_dir.resolve()
    if root == out or root in out.parents:
        cli.error("out-dir must be outside candidate source repository")
    out.mkdir(parents=True, exist_ok=True)
    failures = []
    summaries = []
    for index, report in enumerate(args.report, 1):
        source = report.resolve()
        if not source.is_file():
            cli.error(f"missing report: {source}")
        target = out / f"report-{index:03d}"
        run = run_one(root, source, target, args.python, args.timeout_seconds)
        reason = run["error"] if run["exitCode"] != 0 else None
        present_count = 0
        if reason is None:
            try:
                mapped = json.loads(_output_path(target, source, "mapped").read_text(encoding="utf-8"))
                result = json.loads(_output_path(target, source, "result").read_text(encoding="utf-8"))
                if not isinstance(mapped, dict) or not isinstance(result, dict):
                    raise ValueError("mapped/result must be JSON objects")
                present_count = sum(_present(value) for value in mapped.values())
                if not present_count or not result.get("sections"):
                    raise ValueError("successful process produced no meaningful mapped fields/sections")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                reason = str(exc)
        summaries.append({"report": str(source), "nonemptyMappedFields": present_count, "error": reason})
        print(f"[{index}/{len(args.report)}] {source.name}: populated={present_count} error={reason or 'none'}", flush=True)
        if reason:
            failures.append({"report": str(source), "error": reason})
    (out / "smoke_summary.json").write_text(json.dumps({"cases": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
