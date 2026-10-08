"""统一文档 AST 数据结构。

这一层隔离 Word 解析库，后续逻辑不直接依赖 Aspose、python-docx 或其他解析器。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class TextStyle:
    """文本样式信息。"""

    style_name: str | None = None
    font_size: float | None = None
    bold: bool = False
    italic: bool = False
    alignment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的样式字典。
        """
        return asdict(self)


@dataclass
class DocumentBlock:
    """文档块，表示段落、表格占位或图片占位。"""

    id: str
    type: Literal["paragraph", "table", "image"]
    text: str
    order: int
    page: int | None = None
    style: TextStyle | None = None
    section_path: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的文档块。
        """
        return asdict(self)


@dataclass
class TableCell:
    """表格单元格。"""

    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的单元格。
        """
        return asdict(self)


@dataclass
class DocumentTable:
    """统一表格对象。"""

    id: str
    order: int
    page: int | None = None
    caption: str | None = None
    section_path: list[str] = field(default_factory=list)
    rows: list[list[TableCell]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def iter_cells(self):
        """遍历全部单元格。

        Yields:
            TableCell: 表格中的单元格。
        """
        for row in self.rows:
            for cell in row:
                yield cell

    def to_matrix(self) -> list[list[str]]:
        """转换为文本矩阵。

        Returns:
            list[list[str]]: 仅包含文本的二维表格。
        """
        return [[cell.text for cell in row] for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的表格。
        """
        return asdict(self)


@dataclass
class DocumentImage:
    """图片对象。"""

    id: str
    order: int
    page: int | None = None
    caption: str | None = None
    section_path: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的图片信息。
        """
        return asdict(self)


@dataclass
class DocumentAST:
    """统一文档对象。"""

    file_name: str
    blocks: list[DocumentBlock] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)
    images: list[DocumentImage] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def get_table(self, table_id: str) -> DocumentTable | None:
        """按 ID 获取表格。

        Args:
            table_id: 表格 ID。

        Returns:
            DocumentTable | None: 匹配的表格，不存在时返回 None。
        """
        for table in self.tables:
            if table.id == table_id:
                return table
        return None

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的 AST。
        """
        return asdict(self)
