"""二次抽取选择器，并保留现有规则语义。"""

from __future__ import annotations

import re

from typing import Any

from word_parser.secondary.table_values.context import NormalizedTable

from word_parser.secondary.table_values.primitives import _NIL_STATUS, clean_text, column_match_score, normalize_label, row_match_score, value_at

def select_row(table: NormalizedTable, spec: dict[str, Any]) -> dict[str, Any]:
    """按配置选择表格行。"""
    selector_type = spec.get("type") or "label"
    if selector_type == "index":
        index = int(spec.get("index", 0))
        base = str(spec.get("index_base") or "data_rows")
        row_index = index - 1 if base == "data_rows" and index > 0 else index
        if 0 <= row_index < len(table.data):
            return {"rowIndex": row_index, "row": table.data[row_index], "selector": "index"}
        return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"行号越界：{index}"}
    patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
    search_columns = column_indices_for_selector(table, spec.get("column") or spec.get("column_aliases"))
    matches: list[dict[str, Any]] = []
    for row_index, row in enumerate(table.data):
        cells = [value_at(row, index) for index in search_columns] if search_columns else row
        text = clean_text(" ".join(str(cell or "") for cell in cells))
        if not text:
            continue
        score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
        if score > 0:
            matches.append({"rowIndex": row_index, "row": row, "score": score, "text": text})
    if not matches:
        return {"status": _NIL_STATUS, "reason": "row_not_found", "message": "未找到匹配行。"}
    matches.sort(key=lambda item: item["score"], reverse=True)
    if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
        return {"status": _NIL_STATUS, "reason": "ambiguous_row", "message": "行选择命中多个同分候选。", "candidates": matches[:5]}
    return {**matches[0], "selector": "label"}

def select_row_occurrence(table: NormalizedTable, spec: dict[str, Any], occurrence: int) -> dict[str, Any]:
    """按匹配行出现次序选择表格行。

    用于连续表被合并后多次出现同一行标签的情况，比如风切变表的多个“综合值”行。
    occurrence 从 0 开始，命中不足时返回 NIL，不回落到随机行。
    """
    patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
    exclude_patterns = [str(pattern) for pattern in spec.get("exclude_patterns") or spec.get("exclude_aliases") or []]
    search_columns = column_indices_for_selector(table, spec.get("column") or spec.get("column_aliases"))
    matches: list[dict[str, Any]] = []
    for row_index, row in enumerate(table.data):
        cells = [value_at(row, index) for index in search_columns] if search_columns else row
        text = clean_text(" ".join(str(cell or "") for cell in cells))
        if not text:
            continue
        if exclude_patterns and row_match_score(text, exclude_patterns) > 0:
            continue
        score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
        if score > 0:
            matches.append({"rowIndex": row_index, "row": row, "score": score, "text": text})
    matches.sort(key=lambda item: item["rowIndex"])
    min_occurrences = max(int(spec.get("min_occurrences") or 0), 0)
    if len(matches) < min_occurrences:
        return {
            "status": _NIL_STATUS,
            "reason": "row_not_found",
            "message": f"\u5339\u914d\u884c\u4e0d\u8db3 {min_occurrences} \u4e2a\uff0c\u5b9e\u9645\u627e\u5230 {len(matches)} \u4e2a\u3002",
            "candidates": matches[:10],
        }
    if occurrence < len(matches):
        return {**matches[occurrence], "selector": "label_occurrence", "occurrence": occurrence}
    if len(matches) == 1 and occurrence > 0:
        return {**matches[0], "selector": "label_occurrence_fallback", "occurrence": 0}
    return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"\u672a\u627e\u5230\u7b2c {occurrence + 1} \u4e2a\u5339\u914d\u884c\u3002", "candidates": matches[:10]}

def select_column(table: NormalizedTable, spec: dict[str, Any]) -> dict[str, Any]:
    """按配置选择表格列。"""
    if "index" in spec:
        index = int(spec.get("index"))
        if 0 <= index < len(table.columns):
            return {"columnIndex": index, "column": table.columns[index], "selector": "index"}
        return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"列号越界：{index}"}
    aliases = [str(alias) for alias in spec.get("aliases") or spec.get("patterns") or []]
    matches: list[dict[str, Any]] = []
    for index, column in enumerate(table.columns):
        score = column_match_score(column, aliases)
        if score > 0:
            matches.append({"columnIndex": index, "column": column, "score": score})
    if not matches:
        return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"未找到匹配列：{aliases}", "columns": table.columns}
    matches.sort(key=lambda item: item["score"], reverse=True)
    if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
        return {"status": _NIL_STATUS, "reason": "ambiguous_column", "message": "列选择命中多个同分候选。", "candidates": matches[:5]}
    return {**matches[0], "selector": "label"}

def column_indices_for_selector(table: NormalizedTable, selector: Any) -> list[int]:
    """把行选择中的列范围配置转换成列索引。"""
    if selector is None:
        return []
    specs = selector if isinstance(selector, list) else [selector]
    indices: list[int] = []
    for item in specs:
        if isinstance(item, int):
            indices.append(item)
            continue
        result = select_column(table, {"aliases": [item]})
        if result.get("status") != _NIL_STATUS:
            indices.append(result["columnIndex"])
    return indices
