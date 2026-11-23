"""Strict real-document regression tool tests (without invoking Aspose/OCR in CI)."""
import json

from tools.scripts.run_real_report_parity import (
    _different, _output_path, compare_outputs, main,
)


def test_equal_nested_fields_and_tables_have_no_diffs():
    fields = {"{capacity}": 200, "{table}": {"columns": ["风机", "容量"], "data": [["A", 5.0], ["B", 5.0]]}}
    assert _different(fields, json.loads(json.dumps(fields))) == []


def test_nonempty_to_null_and_lost_table_row_are_failures():
    old = {"{capacity}": 200, "{table}": [[1, 2], [3, 4]], "{zero}": 0}
    new = {"{capacity}": None, "{table}": [[1, 2]], "{zero}": False}
    diffs = _different(old, new)
    assert [(row["path"], row["type"]) for row in diffs] == [
        ("$.{capacity}", "TYPE_CHANGED"),
        ("$.{table}", "LIST_LENGTH"),
        ("$.{zero}", "TYPE_CHANGED"),
    ]


def test_full_result_and_mapped_json_are_both_checked(tmp_path):
    baseline, candidate = tmp_path / "base", tmp_path / "new"
    baseline.mkdir()
    candidate.mkdir()
    report = tmp_path / "sample.docx"
    report.touch()
    for suffix in ("result", "mapped"):
        _output_path(baseline, report, suffix).write_text('{"sections":[{"fields":[{"value":1}]}]}', encoding="utf-8")
        _output_path(candidate, report, suffix).write_text('{"sections":[{"fields":[{"value":1}]}]}', encoding="utf-8")
    assert compare_outputs(baseline, candidate, report)["differences"] == []
    _output_path(candidate, report, "result").write_text('{"sections":[{"fields":[{"value":2}]}]}', encoding="utf-8")
    diffs = compare_outputs(baseline, candidate, report)["differences"]
    assert len(diffs) == 1
    assert diffs[0]["output"] == "result"
    assert diffs[0]["type"] == "VALUE_CHANGED"


def test_missing_outputs_fails_closed(tmp_path):
    baseline, candidate = tmp_path / "a", tmp_path / "b"
    baseline.mkdir()
    candidate.mkdir()
    report = tmp_path / "sample.docx"
    result = compare_outputs(baseline, candidate, report)
    assert result["error"] and not result["differences"]


def test_cli_requires_distinct_repos_and_external_output(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    dummy = tmp_path / "x.docx"
    dummy.touch()
    try:
        main(["--baseline-root", str(root), "--candidate-root", str(root),
              "--report", str(dummy), "--out-dir", str(tmp_path / "output")])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected unsafe same-repository execution to be rejected")
