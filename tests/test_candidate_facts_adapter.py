"""Unified candidate facts: lossless evidence, no output/mapping mutation."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from word_parser.extraction.candidate_facts import candidate_fact_report, collect_candidate_facts
from word_parser.secondary.table_values.context import NormalizedTable
from word_parser.secondary.table_values.results import (
    derived_table_result, field_result, nil_field, table_value_details,
)
from tools.scripts.audit_candidate_facts import main as audit_main


def _fixture():
    source_table = NormalizedTable(
        section_name="资源章节",
        table={"key": "source-table", "name": "风机技术参数表"},
        columns=["指标", "数值"],
        data=[["轮毂高度", "121"]],
    )
    value_rule = {"field_code": "hubHeight", "field_name": "轮毂高度",
                  "unit": "m", "section": "资源章节", "value_type": "number", "operation": "cell"}
    secondary_field = field_result(
        value_rule, "121", source_table,
        row={"rowIndex": 0, "row": ["轮毂高度", "121"]},
        column={"columnIndex": 1, "column": "数值"},
    )
    nil_record = nil_field(
        {"field_code": "stationTransformer", "field_name": "站用变", "section": "电气一次",
         "operation": "cell"},
        "row_not_found", "未找到对应行", {"missing": ["站用变"]},
    )
    table_rule = {
        "table_code": "windSpeeds", "table_name": "各高度平均风速表",
        "section": "资源章节", "operation": "table_projection",
    }
    derived = derived_table_result(
        table_rule, source_table, ["高度", "风速"], [[80, 6.2], [100, 6.4]],
        {"sources": ["source-table"]},
    )
    enhanced = {
        "filePath": "wind_farm.docx",
        "sections": [
            {"name": "资源章节", "tableFields": [secondary_field], "derivedTables": [derived]},
            {"name": "电气一次", "tableFields": [nil_record], "derivedTables": []},
        ],
        "tableValueExtraction": {"summary": {"fieldCount": 2}, "configVersion": 1},
    }
    primary = {
        "filePath": "wind_farm.docx",
        "extractionCandidates": [
            {
                "fieldCode": "hubHeight", "rawValue": "120", "value": 120,
                "unit": "m", "method": "table_lookup", "score": 2.5,
                "status": "candidate", "sourceType": "table",
                "tableId": "original-t1", "blockId": None, "page": 9,
                "row": 2, "column": 1, "sectionPath": ["风机参数"],
                "evidence": "轮毂高度 | m | 120",
            },
            {
                "fieldCode": "hubHeight", "rawValue": "150", "value": 150,
                "unit": "m", "method": "regex", "score": 1.2,
                "status": "rejected", "reason": "wrong_phase",
                "sourceType": "paragraph", "blockId": "p10",
                "page": 10, "sectionPath": ["规划二期"],
                "evidence": "远期轮毂高度150m",
            },
        ],
        "tableValueExtraction": table_value_details(enhanced),
    }
    return primary, secondary_field, nil_record, derived


def test_lossless_candidates_including_nil_and_derived_table():
    primary, second, nil_record, derived = _fixture()
    original = deepcopy(primary)
    facts = collect_candidate_facts(primary)
    assert len(facts) == 5
    assert [fact.stage for fact in facts] == [
        "primary", "primary", "secondary_field", "secondary_table", "secondary_field",
    ]
    assert facts[0].score == 2.5 and facts[0].confidence is None
    assert facts[0].source["page"] == 9 and facts[0].source["tableId"] == "original-t1"
    assert facts[0].original == primary["extractionCandidates"][0]
    assert facts[2].original == second
    assert facts[2].raw_value == second["source"]["rawValue"]
    assert facts[2].source["rowIndex"] == 0 and facts[2].source["columnIndex"] == 1
    assert facts[2].score is None and facts[2].confidence == 1.0
    assert facts[3].kind == "table" and facts[3].value["data"] == derived["data"]
    assert facts[3].original == derived
    assert facts[4].status == "NIL" and facts[4].original == nil_record
    assert facts[4].value is None
    assert primary == original  # Audit never modifies parser detail or final mapped output.
    json.dumps([fact.to_dict() for fact in facts], ensure_ascii=False, allow_nan=False)


def test_read_only_report_preserves_candidate_variation_without_selecting_winner():
    primary, _, _, _ = _fixture()
    report = candidate_fact_report(primary)
    assert report["version"] == 1
    assert report["summary"]["countsByStage"] == {
        "primary": 2, "secondary_field": 2, "secondary_table": 1,
    }
    assert report["summary"]["nilCount"] == 1
    assert report["valueVariations"] == [
        {"kind": "field", "code": "hubHeight", "distinctValueCount": 2},
    ]
    assert "mapped" not in report
    assert "selected" not in report


def test_standalone_secondary_overrides_embedded_and_avoids_double_counting():
    primary, _, _, _ = _fixture()
    standalone = primary["tableValueExtraction"]
    with_override = collect_candidate_facts(primary, secondary_detail=standalone)
    assert len(with_override) == len(collect_candidate_facts(primary))
    trimmed = collect_candidate_facts(primary, include_nil=False)
    assert len(trimmed) == len(with_override) - 1
    assert all(item.status != "NIL" for item in trimmed)


def test_adapter_does_not_silently_ignore_bad_details():
    with pytest.raises(ValueError, match="extractionCandidates"):
        collect_candidate_facts({"extractionCandidates": {"bad": True}})
    with pytest.raises(ValueError, match="tableFields"):
        collect_candidate_facts({"tableValueExtraction": {"sections": [
            {"name": "资源章节", "tableFields": [42]}
        ]}})


def test_cli_reads_details_and_only_writes_explicit_separate_report(tmp_path, capsys):
    primary, _, _, _ = _fixture()
    detail = tmp_path / "wind_details.json"
    detail.write_text(json.dumps(primary, ensure_ascii=False), encoding="utf-8")
    unchanged = detail.read_bytes()
    assert audit_main([str(detail)]) == 0
    assert detail.read_bytes() == unchanged
    output = tmp_path / "wind_candidate_facts.json"
    assert audit_main([str(detail), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["totalFacts"] == 5
    assert audit_main([str(detail), "--output", str(detail)]) == 2
    assert audit_main([str(detail), "--output", str(tmp_path / "wind_mapped.json")]) == 2
    assert detail.read_bytes() == unchanged
