"""Secondary extraction: context. Existing rule semantics are preserved."""

from __future__ import annotations

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.models import NormalizedTable

from word_parser.extraction.table_values.selectors import normalize_table


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
