"""将二次抽取结果同步到最终映射。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from word_parser.config.loader import ConfigLoader
from word_parser.output.presentation import ResultPresentationMixin
from word_parser.secondary.table_values.results import final_result_with_table_values

from word_parser.mapping.common import (
    _COMBINED_TABLE_DISPLAY_FIELDS,
    _TOWER_ROW_FIELDS,
    _WIND_ROW_FIELDS,
    _WIND_RECORD_FIELDS,
    _is_present,
    _flatten_values,
    _comparable,
    _values_covered,
    _combined_columns,
    _invalid_tower_metadata,
)

def _sync_secondary_outputs(
    parse_result: dict[str, Any],
    enhanced: dict[str, Any],
    config_root: str | Path,
) -> None:
    """只同步最终业务结果实际采用的二次抽取值。"""
    output_files = parse_result.get("outputFiles") or {}
    mapped = parse_result.get("mapped")
    if not isinstance(mapped, dict):
        return

    schema = ConfigLoader(config_root).load_yaml("output_schema.yaml")
    output_codes = {
        str(code): value if str(value).startswith("${") else "${" + str(value) + "}"
        for code, value in (schema.get("output_field_codes") or {}).items()
        if code and value
    }
    successful_fields = {
        (section.get("name"), field.get("fieldCode")): field
        for section in enhanced.get("sections") or []
        for field in section.get("tableFields") or []
        if field.get("status") == "OK" and field.get("fieldCode")
    }
    primary_present = {
        (section.get("name"), field.get("fieldCode"))
        for section in enhanced.get("sections") or []
        for field in section.get("fields") or []
        if field.get("fieldCode") and _flatten_values(field.get("value"))
    }
    successful_tables = {
        table.get("key")
        for section in enhanced.get("sections") or []
        for table in section.get("derivedTables") or []
        if table.get("status") == "OK" and table.get("key")
    }
    final = final_result_with_table_values(enhanced)
    parse_result["result"] = final
    # 兼容旧版已保存结果：新增的输出占位符可能不在旧 mapped 文件中。
    for section in final.get("sections") or []:
        for field in section.get("fields") or []:
            placeholder = output_codes.get(field.get("fieldCode"))
            if placeholder:
                mapped.setdefault(placeholder, field.get("value"))
        for table in section.get("tables") or []:
            placeholder = output_codes.get(table.get("key"))
            if placeholder:
                mapped.setdefault(placeholder, {
                    "name": table.get("name"),
                    "columns": table.get("columns", []),
                    "columnKeys": table.get("columnKeys", []),
                    "data": table.get("data", []),
                })
    for placeholder in output_codes.values():
        mapped.setdefault(placeholder, None)
    accepted_fields: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for section in final.get("sections") or []:
        for field in section.get("fields") or []:
            code = field.get("fieldCode")
            section_code = (section.get("name"), code)
            extracted = successful_fields.get(section_code)
            placeholder = output_codes.get(code)
            # 一次抽取已有值但映射仍为空时，允许同值的二次表格证据补齐占位符。
            if (section_code in primary_present and _is_present(mapped.get(placeholder))) or not extracted:
                continue
            if field.get("value") != extracted.get("value"):
                continue  # 主解析值按既有规则优先，二次结果未被采用。
            if placeholder and placeholder in mapped:
                mapped[placeholder] = field.get("value")
            accepted_fields[code] = (field, extracted)
        for table in section.get("tables") or []:
            code = table.get("key")
            placeholder = output_codes.get(code)
            if code not in successful_tables or not placeholder or placeholder not in mapped:
                continue
            mapped[placeholder] = {
                "name": table.get("name"),
                "columns": table.get("columns", []),
                "columnKeys": table.get("columnKeys", []),
                "data": table.get("data", []),
            }

    for prefix, output_code in (
        ("investmentOutgoingLine", "investmentOutgoingLineGroups"),
        ("investmentAccessStationShare", "investmentAccessStationShareGroups"),
    ):
        placeholder = output_codes.get(output_code)
        if not placeholder or placeholder not in mapped:
            continue
        groups: dict[tuple[str, int], dict[str, Any]] = {}
        for (section_name, code), extracted in successful_fields.items():
            if section_name != "技经概算" or not str(code).startswith(prefix):
                continue
            source = extracted.get("source") or {}
            heading = source.get("groupHeading")
            row_index = source.get("groupRowIndex")
            if heading is None or row_index is None:
                continue
            group = groups.setdefault(
                (str(heading), int(row_index)),
                {"name": heading, "sourceTable": source.get("tableName"), "amounts": {}},
            )
            suffix = next((part for part in ("StaticInvestment", "ConstructionInterest", "ProjectTotal", "DeductibleVat") if str(code).endswith(part)), None)
            if suffix:
                group["amounts"][suffix] = extracted.get("value")
        mapped[placeholder] = list(groups.values()) if groups else None

    mapped_path = output_files.get("mapped")
    if mapped_path:
        Path(mapped_path).write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")

    detail_path = output_files.get("detail")
    if detail_path and Path(detail_path).exists():
        details = json.loads(Path(detail_path).read_text(encoding="utf-8"))
        detail_index = details.get("fieldIndex") or {}
        for code, (field, extracted) in accepted_fields.items():
            placeholder = output_codes.get(code)
            source = extracted.get("source") or {}
            source_detail = {
                "sourceType": "table",
                "text": source.get("rowText"),
                "score": extracted.get("confidence", 1.0),
                "matchMethod": "secondary_table_lookup",
                "tableId": source.get("tableKey"),
                "sectionPath": [source.get("section")] if source.get("section") else [],
                "meta": {"tableName": source.get("tableName"), "column": source.get("column")},
            }
            if code not in detail_index:
                detail_index[code] = {
                    "fieldCode": code,
                    "name": field.get("name"),
                    "section": next((s.get("name") for s in final.get("sections") or [] if any(f.get("fieldCode") == code for f in s.get("fields") or [])), None),
                }
            for entry in [detail_index.get(code), detail_index.get(placeholder) if placeholder else None, *(
                item for section in details.get("sections") or []
                for item in section.get("fields") or [] if item.get("fieldCode") in {code, placeholder}
            )]:
                if isinstance(entry, dict):
                    entry.update(value=field.get("value"), unit=field.get("unit"), status="PASS", source=source_detail)
        Path(detail_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

