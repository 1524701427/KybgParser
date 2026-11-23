"""检查最终映射与业务结果的一致性。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from word_parser.config.loader import ConfigLoader
from word_parser.output.presentation import ResultPresentationMixin
from word_parser.secondary.table_values.results import final_result_with_table_values
from word_parser.mapping.projector import TRANSFORMS

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

def _validate_final_mapping(parse_result: dict[str, Any], config_root: str | Path) -> None:
    """导出的占位字段集合或可见值不一致时明确报错。"""
    result = parse_result.get("result") or {}
    mapped = parse_result.get("mapped") or {}
    schema = ConfigLoader(config_root).load_yaml("output_schema.yaml")
    output_codes = schema.get("output_field_codes") or {}
    fallbacks = schema.get("field_value_fallbacks") or {}
    transforms = schema.get("field_value_transforms") or {}
    placeholders = {
        code: value if str(value).startswith("${") else "${" + str(value) + "}"
        for code, value in output_codes.items()
    }
    missing = set(placeholders.values()) - set(mapped)
    mismatches: list[str] = []
    values_by_code = {code: field.get("value") for code, field in (parse_result.get("fields") or {}).items()}
    values_by_code.update({
        field.get("fieldCode"): field.get("value")
        for section in result.get("sections") or []
        for field in section.get("fields") or []
    })
    for section in result.get("sections") or []:
        for field in section.get("fields") or []:
            code = field.get("fieldCode")
            placeholder = placeholders.get(code)
            expected = field.get("value")
            if expected is None and code in fallbacks:
                expected = values_by_code.get(fallbacks[code])
            specification = transforms.get(code)
            if isinstance(specification, dict) and specification.get("validate_result_value", False):
                operator = specification.get("operator")
                if operator not in TRANSFORMS:
                    raise ValueError(f"Unknown mapping validation operator: {operator!r}")
                expected = TRANSFORMS[operator](expected)
            if placeholder in mapped and expected != mapped[placeholder]:
                mismatches.append(code)
        for table in section.get("tables") or []:
            code = table.get("key")
            placeholder = placeholders.get(code)
            if placeholder in mapped and (
                not isinstance(mapped[placeholder], dict)
                or table.get("data") != mapped[placeholder].get("data")
            ):
                mismatches.append(code)
    for _, table, code, _, aligned in _combined_columns(result):
        if table["key"] != "generationSingleTurbineAligned":
            continue
        placeholder = placeholders.get(code)
        if placeholder in mapped and mapped[placeholder] != aligned:
            mismatches.append(code)
    for section in result.get("sections") or []:
        for table in section.get("tables") or []:
            if table.get("key") != "windResourceCombined":
                continue
            columns = list(_COMBINED_TABLE_DISPLAY_FIELDS["windResourceCombined"].values())
            rows = table.get("data") or []
            if table.get("columns") != columns or any(
                not isinstance(row, list) or len(row) != len(columns) for row in rows
            ):
                mismatches.append("windResourceCombined")
                continue
            for code in _WIND_ROW_FIELDS:
                placeholder = placeholders.get(code)
                if placeholder not in mapped:
                    continue
                index = columns.index(_COMBINED_TABLE_DISPLAY_FIELDS["windResourceCombined"][code])
                if mapped[placeholder] != [row[index] for row in rows]:
                    mismatches.append(code)
            for code in _WIND_RECORD_FIELDS:
                placeholder = placeholders.get(code)
                if placeholder not in mapped:
                    continue
                index = columns.index(_COMBINED_TABLE_DISPLAY_FIELDS["windResourceCombined"][code])
                mapped_records = _flatten_values(mapped[placeholder])
                if any(not isinstance(record, dict) or not record.get("tower_code") for record in mapped_records):
                    mismatches.append(code)
                    continue
                table_records: list[dict[str, Any]] = []
                for row in rows:
                    if isinstance(row[index], str) or row[index] is None:
                        tower_records = [record for record in mapped_records if record["tower_code"] == row[0]]
                        expected = ResultPresentationMixin._wind_resource_record_display(tower_records)
                        if row[index] != expected:
                            mismatches.append(code)
                        continue
                    for record in _flatten_values(row[index]):
                        if not isinstance(record, dict) or record.get("tower_code") != row[0]:
                            mismatches.append(code)
                        else:
                            table_records.append(record)
                mapped_counts = Counter(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in mapped_records)
                table_counts = Counter(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in table_records)
                if any(mapped_counts[signature] < count for signature, count in table_counts.items()):
                    mismatches.append(code)
    has_tower_table = any(
        table.get("key") == "windResourceCombined"
        for section in result.get("sections") or []
        for table in section.get("tables") or []
    )
    if not has_tower_table:
        populated_tower_lists = [
            code for code in _WIND_ROW_FIELDS
            if (placeholder := placeholders.get(code)) in mapped
            and _flatten_values(mapped[placeholder])
        ]
        if len(populated_tower_lists) > 1:
            mismatches.append("windResourceCombined_missing_for_tower_alignment")
    if missing or mismatches:
        raise RuntimeError(
            f"Final mapping audit failed: missing placeholders={sorted(missing)}, "
            f"value mismatches={sorted(set(mismatches))}"
        )

