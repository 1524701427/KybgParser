"""Secondary extraction: results. Existing rule semantics are preserved."""

from __future__ import annotations

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.models import NormalizedTable

from word_parser.extraction.table_values.primitives import clean_text, normalize_number, normalize_value, parse_number


def field_result(rule: dict[str, Any], value: Any, table: NormalizedTable, row: dict[str, Any], column: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取字段结果。"""
    include_patterns = rule.get("include_patterns") or []
    value = filter_included_value(value, include_patterns)
    parsed_value = normalize_value(value, str(rule.get("value_type") or "auto"))
    conversion = (rule.get("column") or {}).get("conversion", rule.get("conversion"))
    if conversion == "yuan_to_wan_yuan_by_header":
        column_name = clean_text(column.get("column"))
        if "万元" not in column_name and re.search(r"(?:^|[（(])元(?:[）)]|$)", column_name):
            number = parse_number(parsed_value)
            if number is not None:
                parsed_value = normalize_number(number / 10000)
    return {
        "fieldCode": rule.get("field_code"),
        "fieldName": rule.get("field_name") or rule.get("field_code"),
        "value": parsed_value,
        "unit": rule.get("unit"),
        "status": "OK",
        "section": rule.get("section"),
        "sourceKind": "table_cell",
        "operation": rule.get("operation") or "cell",
        "valueFiltered": bool(include_patterns),
        "confidence": 1.0,
        "source": {
            "section": table.section_name,
            "tableKey": table.key,
            "tableName": table.name,
            "rowIndex": row.get("rowIndex"),
            "rowText": clean_text(" ".join(str(cell or "") for cell in row.get("row") or [])),
            "columnIndex": column.get("columnIndex"),
            "column": column.get("column"),
            "rawValue": value,
        },
    }

def filter_included_value(value: Any, include_patterns: list[Any]) -> Any:
    """Keep only configured fragments from a merged text value."""
    if not include_patterns or not isinstance(value, str):
        return value
    parts: list[str] = []
    for pattern in include_patterns:
        match = re.search(str(pattern), value, flags=re.IGNORECASE)
        if match:
            parts.append(clean_text(match.group(0)))
    return "，".join(dict.fromkeys(parts)) if parts else value

def nil_field(rule: dict[str, Any], reason: str, message: str | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 NIL 字段结果，防止低置信乱取。"""
    return {
        "fieldCode": rule.get("field_code"),
        "fieldName": rule.get("field_name") or rule.get("field_code"),
        "value": None,
        "unit": rule.get("unit"),
        "status": _NIL_STATUS,
        "section": rule.get("section"),
        "sourceKind": "table_cell",
        "operation": rule.get("operation") or "cell",
        "nilReason": reason,
        "message": message,
        "trace": simplify_trace(trace or {}),
    }

def derived_table_result(rule: dict[str, Any], table: NormalizedTable, columns: list[str], rows: list[list[Any]], trace: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取表结果。"""
    return {
        "key": rule.get("table_code") or rule.get("field_code"),
        "name": rule.get("table_name") or rule.get("field_name") or rule.get("table_code"),
        "section": rule.get("section"),
        "status": "OK",
        "operation": rule.get("operation"),
        "sourceKind": "table_projection",
        "columns": columns,
        "data": rows,
        "source": {
            "section": table.section_name,
            "tableKey": table.key,
            "tableName": table.name,
        },
        "trace": trace,
    }

def nil_table(rule: dict[str, Any], reason: str, message: str | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 NIL 表结果。"""
    return {
        "key": rule.get("table_code") or rule.get("field_code"),
        "name": rule.get("table_name") or rule.get("field_name") or rule.get("table_code"),
        "section": rule.get("section"),
        "status": _NIL_STATUS,
        "operation": rule.get("operation"),
        "nilReason": reason,
        "message": message,
        "trace": simplify_trace(trace or {}),
    }

def table_summaries(tables: list[NormalizedTable]) -> list[dict[str, Any]]:
    """生成候选表摘要，便于 NIL 审计。"""
    return [{"section": table.section_name, "key": table.key, "name": table.name, "columns": table.columns[:8]} for table in tables[:20]]

def simplify_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """裁剪 NIL trace，避免把整张表写进错误信息。"""
    simplified: dict[str, Any] = {}
    for key, value in trace.items():
        if key == "table" and isinstance(value, NormalizedTable):
            simplified[key] = {"section": value.section_name, "key": value.key, "name": value.name, "columns": value.columns[:12]}
        elif key in {"candidates", "columns", "missing", "sources", "matchMethod", "confidence", "keyTable", "expectedPatterns", "requiredColumns"}:
            simplified[key] = value
    return simplified
