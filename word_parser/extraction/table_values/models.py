"""Secondary extraction: models. Existing rule semantics are preserved."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from word_parser.extraction.table_values.primitives import clean_text


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
