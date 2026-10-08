"""Secondary extraction: selectors. Existing rule semantics are preserved."""

from __future__ import annotations

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.models import NormalizedTable

from word_parser.extraction.table_values.primitives import clean_text, column_match_score, normalize_label, row_match_score, value_at


def normalize_table(section_name: str, table: dict[str, Any]) -> NormalizedTable:
    """把 result 表格归一为二次抽取内部结构。"""
    columns = [clean_text(column) for column in table.get("columns") or []]
    data = [list(row) if isinstance(row, list) else [row] for row in table.get("data") or []]
    if data and row_has_year_headers(data[0]):
        width = max(len(columns), len(data[0]))
        columns = [
            clean_text(data[0][index]) or (columns[index] if index < len(columns) else f"col_{index}")
            for index in range(width)
        ]
        data = data[1:]
    # 很多原表把真正表头放在第一行，columns 只是表名/col_x；这里仅在明显情况下提升表头。
    elif data and row_looks_like_header(data[0], columns):
        columns = [clean_text(cell) or f"col_{index}" for index, cell in enumerate(data[0])]
        data = data[1:]
    columns = infer_merged_year_columns(columns)
    return NormalizedTable(section_name=section_name, table=table, columns=columns, data=data)

def infer_merged_year_columns(columns: list[str]) -> list[str]:
    """把多级财务表里被合并表头占位的“运行期”推断为第1年。"""
    normalized = [normalize_label(column) for column in columns]
    if "第1年" in normalized:
        return columns
    for index, label in enumerate(normalized):
        if label != "运行期":
            continue
        later_labels = normalized[index + 1 :]
        if any(re.fullmatch(r"第?2年", item) for item in later_labels):
            result = list(columns)
            result[index] = "第1年"
            return result
    return columns

def row_has_year_headers(row: list[Any]) -> bool:
    """判断首行是否包含横向年份表头，并保留既有项目/合计等列名。"""
    labels = [normalize_label(cell) for cell in row]
    return sum(1 for label in labels if re.fullmatch(r"第?\d+年", label)) >= 2

def row_looks_like_header(row: list[Any], columns: list[str]) -> bool:
    """判断第一行是否更像真实表头。"""
    if not row:
        return False
    normalized_columns = [normalize_label(column) for column in columns]
    if normalized_columns and not all(column.startswith("col") or column in {""} for column in normalized_columns):
        # 当前 columns 已经有较明确的表头时，不轻易替换。
        meaningful = sum(1 for column in normalized_columns if column and not column.startswith("col"))
        if meaningful >= max(2, len(normalized_columns) // 2):
            return False
    row_text = [normalize_label(cell) for cell in row]
    header_hits = sum(1 for text in row_text if text in {"序号", "项目", "项目名称", "名称", "单位", "数量", "单价", "合计", "备注", "型号规格及技术数据", "型号及规格"})
    return header_hits >= 2

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
