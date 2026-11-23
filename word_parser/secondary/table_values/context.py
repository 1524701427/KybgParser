"""二次抽取上下文，并保留现有规则语义。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from word_parser.secondary.table_values.primitives import _NIL_STATUS, clean_text, normalize_label


@dataclass
class NormalizedTable:
    """二次抽取使用的标准化表对象。"""

    section_name: str
    table: dict[str, Any]
    columns: list[str]
    data: list[list[Any]]

    @property
    def key(self) -> str:
        """返回 result 中的表 key。"""
        return str(self.table.get("key") or "")

    @property
    def name(self) -> str:
        """返回 result 中的表名。"""
        return clean_text(self.table.get("name") or "")


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
    """判断首行是否包含横向年份表头，并保留既有项目、合计等列名。"""
    labels = [normalize_label(cell) for cell in row]
    return sum(1 for label in labels if re.fullmatch(r"第?\d+年", label)) >= 2


def row_looks_like_header(row: list[Any], columns: list[str]) -> bool:
    """判断第一行是否更像真实表头。"""
    if not row:
        return False
    normalized_columns = [normalize_label(column) for column in columns]
    if normalized_columns and not all(column.startswith("col") or column in {""} for column in normalized_columns):
        meaningful = sum(1 for column in normalized_columns if column and not column.startswith("col"))
        if meaningful >= max(2, len(normalized_columns) // 2):
            return False
    row_text = [normalize_label(cell) for cell in row]
    header_hits = sum(
        1
        for text in row_text
        if text in {"序号", "项目", "项目名称", "工程或费用名称", "名称", "单位", "数量", "单价", "合计", "备注", "型号规格及技术数据", "型号及规格"}
        or text.startswith("合计")
    )
    return header_hits >= 2


class ResultContext:
    """增强过程中的 result 索引和写入适配器。"""

    def __init__(self, result: dict[str, Any]):
        """构建章节、表和字段索引。"""
        self.result = result
        self.section_index = {section.get("name"): section for section in result.get("sections") or []}
        self.table_index: list[NormalizedTable] = []
        self.field_index: dict[str, dict[str, Any]] = {}
        for section in result.get("sections") or []:
            section_name = str(section.get("name") or "")
            for table in section.get("tables") or []:
                self.table_index.append(normalize_table(section_name, table))
            for field in section.get("fields") or []:
                field_code = field.get("fieldCode") or field.get("field_code")
                if field_code:
                    self.field_index[str(field_code)] = field

    def tables(self, section_name: str | None = None) -> list[NormalizedTable]:
        """返回指定章节或全部章节的表。"""
        if not section_name:
            return list(self.table_index)
        return [table for table in self.table_index if table.section_name == section_name]

    def add_table_field(self, field: dict[str, Any]) -> None:
        """把二次抽取字段追加到所属章节。"""
        section = self._section_for(field.get("section"))
        section.setdefault("tableFields", []).append(field)

    def add_derived_table(self, table: dict[str, Any]) -> None:
        """把二次抽取表追加到所属章节。"""
        section = self._section_for(table.get("section"))
        section.setdefault("derivedTables", []).append(table)

    def summary(self) -> dict[str, Any]:
        """生成二次抽取摘要。"""
        fields = [field for section in self.result.get("sections") or [] for field in section.get("tableFields") or []]
        tables = [table for section in self.result.get("sections") or [] for table in section.get("derivedTables") or []]
        return {
            "fieldCount": len(fields),
            "fieldOkCount": sum(1 for field in fields if field.get("status") == "OK"),
            "fieldNilCount": sum(1 for field in fields if field.get("status") == _NIL_STATUS),
            "derivedTableCount": len(tables),
            "derivedTableOkCount": sum(1 for table in tables if table.get("status") == "OK"),
            "derivedTableNilCount": sum(1 for table in tables if table.get("status") == _NIL_STATUS),
        }

    def _section_for(self, section_name: Any) -> dict[str, Any]:
        """获取或创建增强结果所属章节。"""
        name = str(section_name or "二次抽取")
        section = self.section_index.get(name)
        if section is None:
            section = {"name": name, "fields": [], "tables": [], "tableFields": [], "derivedTables": []}
            self.result.setdefault("sections", []).append(section)
            self.section_index[name] = section
        return section
