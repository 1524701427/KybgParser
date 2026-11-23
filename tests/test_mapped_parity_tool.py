"""Guarantee our old/new mapping comparator reports destructive business changes."""
import json

from tools.scripts.compare_mapped import compare_paths, compare_values


def test_value_loss_and_schema_changes_are_detected():
    old = {"${capacity}": 200.0, "${rows}": [{"model": "GW", "count": 40}], "${unit}": "MW"}
    new = {"${capacity}": None, "${rows}": [], "${unit}": ["MW"], "${extra}": 1}
    issues = compare_values(old, new)
    kinds = {item["kind"] for item in issues}
    assert {"LOST_VALUE", "CHANGED_LIST_LENGTH", "CHANGED_TYPE", "NEW_KEY"} <= kinds


def test_matching_results_have_no_diffs():
    value = {"${capacity}": 200, "${rows}": [{"model": "GW", "count": 40}]}
    assert compare_values(value, json.loads(json.dumps(value))) == []


def test_directory_comparison_fails_on_missing_file(tmp_path):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "first_mapped.json").write_text('{"a": 1}', encoding="utf-8")
    (new_dir / "second_mapped.json").write_text('{"b": 2}', encoding="utf-8")
    issues = compare_paths(old_dir, new_dir)
    assert len(issues) == 2
    assert all(item["kind"] == "MISSING_OUTPUT_FILE" for item in issues)


def test_same_filename_reports_value_change(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "a_mapped.json").write_text('{"a": 2}', encoding="utf-8")
    (new_dir / "a_mapped.json").write_text('{"a": 3}', encoding="utf-8")
    issues = compare_paths(old_dir, new_dir)
    assert len(issues) == 1
    assert issues[0]["kind"] == "CHANGED_VALUE"
