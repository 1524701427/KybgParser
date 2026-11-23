"""Regression tests for config-only verification; no PDF/Word or OCR runtime required."""
from pathlib import Path

from tools.scripts.audit_extraction_config import audit_fields, audit_runtime

ROOT = Path(__file__).resolve().parents[1]


def test_current_runtime_yaml_is_valid():
    assert not [issue for issue in audit_runtime(ROOT / "configs") if issue.severity == "error"]


def test_runtime_audit_rejects_broken_pattern(tmp_path):
    current = (ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8")
    assert "context_value_pattern:" in current
    invalid = current.replace(
        "context_value_pattern:",
        "bad_pattern_original: ignored\n  context_value_pattern: '[(' # malformed regex
    )
    (tmp_path / "extraction_runtime.yaml").write_text(invalid, encoding="utf-8")
    issues = audit_runtime(tmp_path)
    assert any("context_value_pattern" in item.location and item.severity == "error" for item in issues)


def test_cross_file_duplicate_fields_are_reported_without_changing_behavior(tmp_path):
    field_dir = tmp_path / "fields"
    field_dir.mkdir()
    (field_dir / "a.yaml").write_text("fields:\n  duplicateCode: {name: old}\n", encoding="utf-8")
    (field_dir / "b.yaml").write_text("fields:\n  duplicateCode: {name: new}\n", encoding="utf-8")
    warnings, count = audit_fields(tmp_path)
    assert count == 1
    assert any(item.severity == "warning" and "duplicateCode" in item.location for item in warnings)
    errors, count = audit_fields(tmp_path, strict_duplicates=True)
    assert count == 1
    assert any(item.severity == "error" and "duplicateCode" in item.location for item in errors)
