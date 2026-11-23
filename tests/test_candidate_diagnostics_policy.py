"""Read-only YAML candidate diagnostics: provenance warnings, not field resolution."""
from copy import deepcopy
from pathlib import Path
import json

import pytest
import yaml

from word_parser.extraction.candidate_diagnostics import (
    candidate_quality_report,
    validate_candidate_audit_policy,
)
from tools.scripts.audit_candidate_facts import main as audit_main


ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "configs" / "candidate_audit.yaml").read_text(encoding="utf-8"))


def _primary(code="hubHeight", value=120, unit="m", status="candidate", **source):
    return {
        "fieldCode": code, "rawValue": str(value), "value": value,
        "unit": unit, "method": "table_lookup", "score": 2.2,
        "status": status, "sourceType": "table", "tableId": source.get("tableId"),
        "blockId": source.get("blockId"), "page": source.get("page"),
        "evidence": source.get("evidence"),
    }


def _secondary(code="hubHeight", value=121, unit="m", status="OK", **source):
    return {
        "fieldCode": code, "fieldName": "轮毂高度", "value": value, "unit": unit,
        "status": status, "operation": "cell", "confidence": 1.0,
        "source": source,
    }


def _details(primary=None, second=None):
    return {
        "filePath": "project.docx",
        "extractionCandidates": primary if primary is not None else [],
        "tableValueExtraction": {
            "sections": [
                {"name": "资源章节", "tableFields": second if second is not None else []}
            ]
        },
    }


def test_checked_in_yaml_policy_is_valid():
    validate_candidate_audit_policy(POLICY)


def test_cross_stage_variations_are_observations_not_selected_values():
    details = _details(
        primary=[_primary(value=120, tableId="t1"), _primary(value=150, status="rejected")],
        second=[_secondary(value=121, tableKey="t2", rowIndex=0, columnIndex=0)],
    )
    unchanged = deepcopy(details)
    report = candidate_quality_report(details, policy=POLICY)
    checks = report["qualityChecks"]
    assert checks["mode"] == "read_only"
    assert checks["issueCount"] == 0
    assert checks["crossStageVariationCount"] == 1
    assert checks["crossStageVariations"][0]["code"] == "hubHeight"
    assert checks["crossStageVariations"][0]["classification"] == "REVIEW_ONLY"
    assert checks["crossStageVariations"][0]["distinctValueCount"] == 2
    assert details == unchanged
    assert "mapped" not in report
    assert "winner" not in report
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_different_units_are_not_assumed_comparable_by_default():
    details = _details(
        primary=[_primary(value=120, unit="m", tableId="t1")],
        second=[_secondary(value=0.12, unit="km", tableKey="t2")],
    )
    report = candidate_quality_report(details, policy=POLICY)
    assert report["qualityChecks"]["crossStageVariationCount"] == 0
    modified = deepcopy(POLICY)
    modified["cross_stage_variations"]["include_only_same_unit"] = False
    observed = candidate_quality_report(details, policy=modified)
    assert observed["qualityChecks"]["crossStageVariationCount"] == 1


def test_missing_code_source_and_nil_reason_are_separate_findings():
    details = _details(
        primary=[_primary(code=None, value=120)],
        second=[
            _secondary(code="noTable", value=22),
            {"fieldCode": "station", "fieldName": "站用变", "status": "NIL", "value": None},
        ],
    )
    result = candidate_quality_report(details, policy=POLICY)["qualityChecks"]
    assert result["countsByRule"] == {
        "MISSING_FIELD_CODE": 1,
        "MISSING_SOURCE_LOCATION": 2,
        "MISSING_NIL_REASON": 1,
    }
    assert result["issueCount"] == 4


def test_nil_trace_and_falsey_row_index_zero_are_not_lost():
    details = _details(
        second=[
            _secondary(code="x", value=0, tableKey="", rowIndex=0),
            {"fieldCode": "y", "status": "NIL", "value": None,
             "nilReason": "row_not_found", "trace": {"missing": ["x"]}},
        ]
    )
    report = candidate_quality_report(details, policy=POLICY)
    assert report["qualityChecks"]["issueCount"] == 0
    assert report["facts"][1]["original"]["trace"]["missing"] == ["x"]


@pytest.mark.parametrize(
    "key,bad",
    [
        ("version", 2),
        ("enabled", "true"),
        ("required_field_codes_for_statuses", "OK"),
        ("evidence_checks", []),
        ("cross_stage_variations", None),
    ],
)
def test_invalid_policy_fails_loudly(key, bad):
    policy = deepcopy(POLICY)
    policy[key] = bad
    with pytest.raises(ValueError):
        validate_candidate_audit_policy(policy)


def test_disabled_policy_never_changes_candidate_fact_collection():
    details = _details(primary=[_primary(tableId="a")], second=[_secondary(tableKey="b")])
    policy = deepcopy(POLICY)
    policy["enabled"] = False
    report = candidate_quality_report(details, policy=policy)
    assert report["summary"]["totalFacts"] == 2
    assert report["qualityChecks"]["issueCount"] == 0
    assert report["qualityChecks"]["crossStageVariationCount"] == 0


def test_cli_uses_configured_policy_and_does_not_change_input(tmp_path):
    details = _details(primary=[_primary(value=120, tableId="t1")],
                       second=[_secondary(value=121, tableKey="t2")])
    detail_path = tmp_path / "project_details.json"
    detail_path.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
    before = detail_path.read_bytes()
    audit_path = tmp_path / "project_candidate_facts.json"
    assert audit_main([str(detail_path), "--output", str(audit_path)]) == 0
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    assert report["qualityChecks"]["crossStageVariationCount"] == 1
    assert report["qualityChecks"]["issueCount"] == 0
    assert detail_path.read_bytes() == before
    policy = deepcopy(POLICY)
    policy["enabled"] = False
    policy_path = tmp_path / "custom_audit.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True), encoding="utf-8")
    assert audit_main([str(detail_path), "--policy", str(policy_path),
                       "--output", str(audit_path)]) == 0
    assert json.loads(audit_path.read_text(encoding="utf-8"))["qualityChecks"]["enabled"] is False
    assert detail_path.read_bytes() == before


def test_empty_or_broken_yaml_does_not_silently_disable_diagnostics(tmp_path):
    detail_path = tmp_path / "project_details.json"
    detail_path.write_text(json.dumps(_details(), ensure_ascii=False), encoding="utf-8")
    original = detail_path.read_bytes()
    policy_file = tmp_path / "candidate_audit.yaml"
    output_file = tmp_path / "project_candidate_facts.json"
    for invalid_yaml in ("", "version: ["):
        policy_file.write_text(invalid_yaml, encoding="utf-8")
        assert audit_main([
            str(detail_path), "--policy", str(policy_file), "--output", str(output_file)
        ]) == 2
        assert not output_file.exists()
        assert detail_path.read_bytes() == original
