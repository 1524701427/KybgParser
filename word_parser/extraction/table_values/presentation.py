"""Secondary extraction: presentation. Existing rule semantics are preserved."""

from __future__ import annotations

import copy

from typing import Any


def compact_table_value_result(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成面向展示的二次抽取结果 JSON。

    输出只保留业务结果：字段使用和主解析 ``fields`` 一致的
    ``fieldCode/name/value/unit`` 结构；整表类结果只保留对原表的引用，
    完整行列命中、NIL、trace 和来源细节写入 details JSON。
    """
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
    return {
        "filePath": enhanced.get("filePath"),
        "results": results,
    }

def final_result_with_table_values(enhanced: dict[str, Any]) -> dict[str, Any]:
    """Build one final result JSON by merging secondary values into sections."""
    final = copy.deepcopy(enhanced)
    final.pop("tableValueExtraction", None)
    for section in final.get("sections") or []:
        table_fields = section.pop("tableFields", []) or []
        derived_tables = section.pop("derivedTables", []) or []
        _merge_section_fields(section, table_fields)
        _merge_section_tables(section, derived_tables)
    return final

def table_value_details(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取过程明细 JSON。"""
    sections: list[dict[str, Any]] = []
    for section in enhanced.get("sections") or []:
        table_fields = list(section.get("tableFields") or [])
        derived_tables = list(section.get("derivedTables") or [])
        if not table_fields and not derived_tables:
            continue
        sections.append(
            {
                "name": section.get("name"),
                "tableFields": table_fields,
                "derivedTables": derived_tables,
            }
        )
    extraction = enhanced.get("tableValueExtraction") or {}
    return {
        "filePath": enhanced.get("filePath"),
        "summary": extraction.get("summary") or {},
        "configVersion": extraction.get("configVersion"),
        "sections": sections,
    }

_SECONDARY_NO_OVERWRITE_WHEN_PRESENT = {
    "electricalPrimaryTransformerSpec",
    "electricalPrimarySvgSpec",
    "electricalPrimarySvgUnit",
    "electricalPrimarySvgQuantity",
    "electricalPrimaryGroundingTransformerSetSpec",
    "electricalPrimaryExternalPowerTransformerSpec",
}

def _merge_section_fields(section: dict[str, Any], table_fields: list[dict[str, Any]]) -> None:
    fields = list(section.get("fields") or [])
    index = {field.get("fieldCode"): position for position, field in enumerate(fields) if isinstance(field, dict) and field.get("fieldCode")}
    for table_field in table_fields:
        if table_field.get("status") != "OK":
            continue
        field_code = table_field.get("fieldCode")
        if not field_code:
            continue
        if field_code in index:
            existing = fields[index[field_code]]
            if field_code in _SECONDARY_NO_OVERWRITE_WHEN_PRESENT and _has_present_value(existing.get("value")) and not table_field.get("valueFiltered"):
                continue
            compact = _compact_table_field(table_field, fallback_name=fields[index[field_code]].get("name"))
            fields[index[field_code]] = compact
        else:
            compact = _compact_table_field(table_field)
            index[field_code] = len(fields)
            fields.append(compact)
    section["fields"] = fields

def _has_present_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True

def _merge_section_tables(section: dict[str, Any], derived_tables: list[dict[str, Any]]) -> None:
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
            compact = _compact_derived_table(derived_table, fallback_name=tables[index[table_code]].get("name"))
            tables[index[table_code]] = compact
        else:
            compact = _compact_derived_table(derived_table)
            index[table_code] = len(tables)
            tables.append(compact)
    section["tables"] = tables

def _compact_table_field(field: dict[str, Any], fallback_name: str | None = None) -> dict[str, Any]:
    """把二次字段转成和主解析 fields 一致的展示结构。"""
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
    """把二次表结果转成对原表的轻量引用。"""
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
