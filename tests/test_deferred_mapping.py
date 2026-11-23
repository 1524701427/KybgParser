"""The full route can map after secondary extraction without changing output."""

from __future__ import annotations

import json
from pathlib import Path

from word_parser.application.api import enhance_parse_result
from word_parser.mapping.projector import mapping_from_details


def test_deferred_mapping_matches_existing_two_step_route(tmp_path: Path):
    config_root = Path(__file__).resolve().parents[1] / "configs"
    table_config = tmp_path / "empty_table_rules.yaml"
    table_config.write_text("version: 2\nrules: []\n", encoding="utf-8")
    primary = {
        "filePath": "report.docx",
        "sections": [{"name": "通用", "fields": [
            {"fieldCode": "projectName", "name": "项目名称", "value": "测试风电场", "unit": None},
        ], "tables": []}],
    }
    detail = {
        "filePath": "report.docx",
        "fieldIndex": {"projectName": {"value": "测试风电场"}},
        "tableIndex": {},
        "sections": [],
    }

    outputs = []
    for route in ("existing", "deferred"):
        result_path = tmp_path / f"{route}_result.json"
        detail_path = tmp_path / f"{route}_details.json"
        mapped_path = tmp_path / f"{route}_mapped.json"
        result_path.write_text(json.dumps(primary, ensure_ascii=False), encoding="utf-8")
        detail_path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        parsed = {
            "mapped": mapping_from_details(detail_path, config_root) if route == "existing" else {},
            "outputFiles": {"result": str(result_path), "detail": str(detail_path), "mapped": str(mapped_path)},
        }
        if route == "deferred":
            parsed["result"] = primary
        outputs.append(enhance_parse_result(parsed, config_path=table_config, config_root=config_root))

    assert outputs[0]["result"] == outputs[1]["result"]
    assert outputs[0]["mapped"] == outputs[1]["mapped"]
    assert outputs[1]["mapped"]["${project_name}"] == "测试风电场"
