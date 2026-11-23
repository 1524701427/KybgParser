"""风资源相关字段的最终映射规则。"""

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


def merge_turbulence_records(records: Any) -> Any:
    """按测风塔和高度合并湍流记录，优先采用不限定风速的平均值。"""
    if not isinstance(records, list):
        return records
    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    for source in records:
        if not isinstance(source, dict):
            continue
        key = (source.get("tower_code"), source.get("height"))
        if key not in merged:
            merged[key] = {
                "tower_code": source.get("tower_code"),
                "height": source.get("height"),
                "height_unit": source.get("height_unit") or "m",
                "average_value": None,
                "representative_value": None,
                "wind_speed_segment": None,
                "wind_speed_unit": None,
            }
        target = merged[key]
        average = source.get("average_value")
        speed = source.get("wind_speed_segment")
        if average is not None and (
            target["average_value"] is None
            or (target["wind_speed_segment"] is not None and speed is None)
        ):
            target["average_value"] = average
            target["wind_speed_segment"] = speed
            target["wind_speed_unit"] = source.get("wind_speed_unit") if speed is not None else None
        if target["representative_value"] is None and source.get("representative_value") is not None:
            target["representative_value"] = source["representative_value"]
    return list(merged.values())

def _align_combined_table_mappings(parse_result: dict[str, Any], config_root: str | Path) -> None:
    """仅填充可独立核实且行对齐的映射值。"""
    result = parse_result.get("result")
    mapped = parse_result.get("mapped")
    if not isinstance(result, dict) or not isinstance(mapped, dict):
        return
    schema = ConfigLoader(config_root).load_yaml("output_schema.yaml")
    output_codes = schema.get("output_field_codes") or {}
    changed: dict[str, tuple[Any, str, str]] = {}
    for section, table, code, column, aligned in _combined_columns(result):
        output_code = output_codes.get(code)
        if not output_code:
            continue
        placeholder = output_code if str(output_code).startswith("${") else "${" + str(output_code) + "}"
        if placeholder not in mapped:
            continue
        old = mapped[placeholder]
        invalid_old = _invalid_tower_metadata(code, old)
        tower_row = table["key"] == "windResourceCombined" and code in _WIND_ROW_FIELDS
        if tower_row or table["key"] == "generationSingleTurbineAligned":
            # 所有列都从相同的源行映射；各列独立处理时
            # 列表可能错位，也可能意外包含标签文本。
            replacement = aligned
        elif invalid_old:
            replacement = aligned if _flatten_values(aligned) else None
        elif _flatten_values(aligned) and _values_covered(old, aligned):
            replacement = aligned
        else:
            continue
        field_changed = False
        if tower_row or invalid_old or table["key"] == "generationSingleTurbineAligned":
            for field in (field for field in section.get("fields") or [] if field.get("fieldCode") == code):
                if field.get("value") != replacement:
                    field["value"] = replacement
                    field_changed = True
        if old == replacement and not field_changed:
            continue
        mapped[placeholder] = replacement
        changed[code] = (replacement, table["key"], column)
    if not changed:
        return
    output_files = parse_result.get("outputFiles") or {}
    mapped_path = output_files.get("mapped")
    if mapped_path:
        Path(mapped_path).write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_path = output_files.get("detail")
    if detail_path and Path(detail_path).exists():
        details = json.loads(Path(detail_path).read_text(encoding="utf-8"))
        index = details.get("fieldIndex") or {}
        for code, (value, table_key, column) in changed.items():
            output_code = output_codes[code]
            placeholder = output_code if str(output_code).startswith("${") else "${" + str(output_code) + "}"
            source = {
                "sourceType": "table", "tableId": table_key,
                "matchMethod": "aligned_combined_column", "meta": {"column": column},
            } if _flatten_values(value) else None
            for item in (index.get(code), index.get(placeholder), *(
                item for section in details.get("sections") or []
                for item in section.get("fields") or [] if item.get("fieldCode") in {code, placeholder}
            )):
                if isinstance(item, dict):
                    item.update(value=value, status="PASS" if _flatten_values(value) else "MISSING", source=source)
        Path(detail_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

def _hide_combined_table_duplicate_fields(parse_result: dict[str, Any], config_root: str | Path = "configs") -> None:
    """仅隐藏已被完整覆盖的旧字段，保留源表数据。"""
    result = parse_result.get("result")
    if not isinstance(result, dict):
        return
    mapped = parse_result.get("mapped") or {}
    output_codes = ConfigLoader(config_root).load_yaml("output_schema.yaml").get("output_field_codes") or {}
    for section in result.get("sections") or []:
        aligned_by_code = {
            code: values for owner, _, code, _, values in _combined_columns(result) if owner is section
        }
        fields = []
        for field in section.get("fields") or []:
            code = field.get("fieldCode") if isinstance(field, dict) else None
            aligned = aligned_by_code.get(code)
            if aligned is None or not _values_covered(field.get("value"), aligned):
                fields.append(field)
                continue
            output_code = output_codes.get(code)
            placeholder = output_code if str(output_code).startswith("${") else "${" + str(output_code) + "}"
            if output_code and placeholder in mapped and not _values_covered(mapped[placeholder], aligned):
                fields.append(field)
        section["fields"] = fields
    result_path = (parse_result.get("outputFiles") or {}).get("result")
    if result_path:
        Path(result_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

