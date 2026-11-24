"""二次抽取结果构建，并保留现有规则语义。"""

from __future__ import annotations

import copy
import re

from typing import Any

from word_parser.secondary.table_values.context import NormalizedTable
from word_parser.extraction.selection import has_value as _has_present_value, select_secondary

from word_parser.secondary.table_values.primitives import _NIL_STATUS, clean_text, normalize_number, normalize_value, parse_number


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
    """从合并文本值中仅保留配置指定的片段。"""
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


def compact_table_value_result(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成面向展示的二次抽取结果，仅保留成功字段和表格。"""
    results: list[dict[str, Any]] = []
    for section in enhanced.get("sections") or []:
        fields = [_compact_table_field(field) for field in section.get("tableFields") or [] if field.get("status") == "OK"]
        fields = [field for field in fields if field]
        tables = [_compact_derived_table(table) for table in section.get("derivedTables") or [] if table.get("status") == "OK"]
        tables = [table for table in tables if table]
        if not fields and not tables:
            continue
        item: dict[str, Any] = {"name": section.get("name"), "fields": fields}
        if tables:
            item["tables"] = tables
        results.append(item)
    return {"filePath": enhanced.get("filePath"), "results": results}


def final_result_with_table_values(enhanced: dict[str, Any]) -> dict[str, Any]:
    """将二次抽取值合入对应章节，构建最终结果。"""
    final = copy.deepcopy(enhanced)
    final.pop("tableValueExtraction", None)
    for section in final.get("sections") or []:
        table_fields = section.pop("tableFields", []) or []
        derived_tables = section.pop("derivedTables", []) or []
        _merge_section_fields(section, table_fields)
        _merge_section_tables(section, derived_tables)
    return final


def table_value_details(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成包含抽取状态和来源信息的过程明细。"""
    sections: list[dict[str, Any]] = []
    for section in enhanced.get("sections") or []:
        table_fields = list(section.get("tableFields") or [])
        derived_tables = list(section.get("derivedTables") or [])
        if not table_fields and not derived_tables:
            continue
        sections.append({"name": section.get("name"), "tableFields": table_fields, "derivedTables": derived_tables})
    extraction = enhanced.get("tableValueExtraction") or {}
    return {
        "filePath": enhanced.get("filePath"),
        "summary": extraction.get("summary") or {},
        "configVersion": extraction.get("configVersion"),
        "sections": sections,
    }


# 保留当前合并策略，维持二次结果与现有输出格式一致。
# 会保留所有已有的主字段，不限于这个旧字段子集。
_SECONDARY_NO_OVERWRITE_WHEN_PRESENT = {
    "electricalPrimaryTransformerSpec",
    "electricalPrimarySvgSpec",
    "electricalPrimarySvgUnit",
    "electricalPrimarySvgQuantity",
    "electricalPrimaryGroundingTransformerSetSpec",
    "electricalPrimaryExternalPowerTransformerSpec",
}


def _merge_section_fields(section: dict[str, Any], table_fields: list[dict[str, Any]]) -> None:
    """把成功的二次抽取字段合入章节字段，并执行既有覆盖规则。"""
    fields = list(section.get("fields") or [])
    index = {
        field.get("fieldCode"): position
        for position, field in enumerate(fields)
        if isinstance(field, dict) and field.get("fieldCode")
    }
    for table_field in table_fields:
        if table_field.get("status") != "OK":
            continue
        field_code = table_field.get("fieldCode")
        if not field_code:
            continue
        if field_code in index:
            existing = fields[index[field_code]]
            # 第二次查找只填补空缺；未经逐行核对，
            # 不得丢弃已有值。
            if select_secondary(existing, table_field) is existing:
                continue
            fields[index[field_code]] = _compact_table_field(table_field, fallback_name=existing.get("name"))
        else:
            compact = _compact_table_field(table_field)
            index[field_code] = len(fields)
            fields.append(compact)
    section["fields"] = fields


def _merge_section_tables(section: dict[str, Any], derived_tables: list[dict[str, Any]]) -> None:
    """把成功的派生表按表编码合入章节。"""
    tables = list(section.get("tables") or [])
    index = {
        table.get("tableCode") or table.get("key"): position
        for position, table in enumerate(tables)
        if isinstance(table, dict) and (table.get("tableCode") or table.get("key"))
    }
    for derived_table in derived_tables:
        if derived_table.get("status") != "OK":
            continue
        table_code = derived_table.get("key")
        if not table_code:
            continue
        if table_code in index:
            if tables[index[table_code]].get("data"):
                continue
            tables[index[table_code]] = _compact_derived_table(
                derived_table,
                fallback_name=tables[index[table_code]].get("name"),
            )
        else:
            compact = _compact_derived_table(derived_table)
            index[table_code] = len(tables)
            tables.append(compact)
    section["tables"] = tables


def _compact_table_field(field: dict[str, Any], fallback_name: str | None = None) -> dict[str, Any]:
    """把二次抽取字段转换为统一的展示结构。"""
    field_code = field.get("fieldCode")
    if not field_code:
        return {}
    return {
        "fieldCode": field_code,
        "name": field.get("fieldName") or field.get("name") or fallback_name or field_code,
        "value": field.get("value"),
        "unit": field.get("unit"),
    }


def _compact_derived_table(table: dict[str, Any], fallback_name: str | None = None) -> dict[str, Any]:
    """把派生表转换为统一的轻量展示结构。"""
    table_code = table.get("key")
    if not table_code:
        return {}
    item: dict[str, Any] = {
        "key": table_code,
        "tableCode": table_code,
        "name": table.get("name") or fallback_name or table_code,
    }
    source = table.get("source") or {}
    if source:
        item["tableRef"] = {
            "section": source.get("section"),
            "tableKey": source.get("tableKey"),
            "tableName": source.get("tableName"),
        }
    item["columns"] = list(table.get("columns") or [])
    item["data"] = list(table.get("data") or [])
    return item
