"""轻量 docx 解析器。

这个解析器只用于开发和兜底：它直接读取 docx 中的 XML，能解析段落和基础表格，
但不负责复杂 Shape、文本框、页码和精确合并单元格。生产建议安装并使用 Aspose。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from parser_engine.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
from parser_engine.core.logger import logger
from parser_engine.document.loaders.word_loader import WordLoader


NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class SimpleDocxLoader(WordLoader):
    """基于标准库的 docx 兜底解析器。"""

    def load(self, file_path: str) -> DocumentAST:
        """加载 docx 文件。

        Args:
            file_path: docx 文件路径。

        Returns:
            DocumentAST: 统一文档对象。
        """
        path = Path(file_path)
        if path.suffix.lower() != ".docx":
            raise ValueError("SimpleDocxLoader 只支持 docx；doc 文件请安装 Aspose.Words")

        logger.info("使用 SimpleDocxLoader 进行轻量 docx 解析")
        with zipfile.ZipFile(path) as package:
            xml = package.read("word/document.xml")

        root = ET.fromstring(xml)
        body = root.find("w:body", NAMESPACE)
        ast = DocumentAST(file_name=path.name, meta={"loader": "SimpleDocxLoader"})
        if body is None:
            return ast

        order = 0
        paragraph_index = 0
        table_index = 0
        for child in list(body):
            tag = self._strip_namespace(child.tag)
            if tag == "p":
                text = self._paragraph_text(child)
                if not text:
                    continue
                paragraph_index += 1
                style = self._paragraph_style(child)
                meta = {}
                layout = self._paragraph_layout(child)
                if layout:
                    meta["paragraph_layout"] = layout
                ast.blocks.append(
                    DocumentBlock(
                        id=f"p_{paragraph_index:04d}",
                        type="paragraph",
                        text=text,
                        order=order,
                        style=style,
                        meta=meta,
                    )
                )
                order += 1
            elif tag == "tbl":
                table_index += 1
                table = self._parse_table(child, table_index, order)
                ast.tables.append(table)
                ast.blocks.append(
                    DocumentBlock(
                        id=f"tb_{table_index:04d}",
                        type="table",
                        text=self._table_text(table),
                        order=order,
                        meta={"table_id": table.id},
                    )
                )
                order += 1

        logger.info(f"轻量 docx 解析完成：块 {len(ast.blocks)} 个，表格 {len(ast.tables)} 个")
        return ast

    def _paragraph_text(self, paragraph: ET.Element) -> str:
        """提取段落文本。

        Args:
            paragraph: XML 段落节点。

        Returns:
            str: 清洗后的段落文本。
        """
        texts = [node.text or "" for node in paragraph.findall(".//w:t", NAMESPACE)]
        return re.sub(r"\s+", " ", "".join(texts)).strip()

    def _paragraph_style(self, paragraph: ET.Element) -> TextStyle:
        """提取段落样式。

        Args:
            paragraph: XML 段落节点。

        Returns:
            TextStyle: 样式信息。
        """
        p_style = paragraph.find("w:pPr/w:pStyle", NAMESPACE)
        style_name = None
        if p_style is not None:
            style_name = p_style.attrib.get(f"{{{NAMESPACE['w']}}}val")
        # 简化版只从 XML 直出属性提取样式，复杂继承样式交给 Aspose 处理。
        bold = paragraph.find(".//w:b", NAMESPACE) is not None
        alignment_node = paragraph.find("w:pPr/w:jc", NAMESPACE)
        alignment = self._attr_value(alignment_node)
        font_size_node = paragraph.find(".//w:sz", NAMESPACE)
        font_size = self._half_point_to_point(self._attr_value(font_size_node))
        return TextStyle(style_name=style_name, font_size=font_size, bold=bold, alignment=alignment)

    def _paragraph_layout(self, paragraph: ET.Element) -> dict[str, float]:
        """提取段落缩进元信息。

        Args:
            paragraph: XML 段落节点。

        Returns:
            dict[str, float]: 缩进信息，单位为 pt。
        """
        indent = paragraph.find("w:pPr/w:ind", NAMESPACE)
        if indent is None:
            return {}
        values = {
            "leftIndent": self._twip_to_point(indent.attrib.get(f"{{{NAMESPACE['w']}}}left")),
            "rightIndent": self._twip_to_point(indent.attrib.get(f"{{{NAMESPACE['w']}}}right")),
            "firstLineIndent": self._twip_to_point(indent.attrib.get(f"{{{NAMESPACE['w']}}}firstLine")),
        }
        return {key: value for key, value in values.items() if value is not None}

    def _attr_value(self, node: ET.Element | None) -> str | None:
        """读取 Word XML 节点的 w:val 属性。"""
        if node is None:
            return None
        return node.attrib.get(f"{{{NAMESPACE['w']}}}val")

    def _half_point_to_point(self, value: str | None) -> float | None:
        """把 Word 半磅字号转成磅值。"""
        try:
            return float(value) / 2 if value is not None else None
        except (TypeError, ValueError):
            return None

    def _twip_to_point(self, value: str | None) -> float | None:
        """把 Word twip 缩进值转成磅值。"""
        try:
            return float(value) / 20 if value is not None else None
        except (TypeError, ValueError):
            return None

    def _parse_table(self, table_node: ET.Element, index: int, order: int) -> DocumentTable:
        """解析表格。

        Args:
            table_node: XML 表格节点。
            index: 表格序号。
            order: 文档顺序。

        Returns:
            DocumentTable: 统一表格对象。
        """
        rows: list[list[TableCell]] = []
        for row_index, row_node in enumerate(table_node.findall("w:tr", NAMESPACE)):
            row: list[TableCell] = []
            for col_index, cell_node in enumerate(row_node.findall("w:tc", NAMESPACE)):
                text_parts = [self._paragraph_text(p) for p in cell_node.findall("w:p", NAMESPACE)]
                text = " ".join(part for part in text_parts if part).strip()
                row.append(TableCell(text=text, row=row_index, col=col_index, is_header=row_index == 0))
            rows.append(row)
        return DocumentTable(id=f"t_{index:04d}", order=order, rows=rows)

    def _table_text(self, table: DocumentTable) -> str:
        """生成表格全文。

        Args:
            table: 表格对象。

        Returns:
            str: 用于候选召回的表格文本。
        """
        return "\n".join(" | ".join(cell.text for cell in row) for row in table.rows)

    def _strip_namespace(self, tag: str) -> str:
        """去掉 XML 命名空间。

        Args:
            tag: XML 标签。

        Returns:
            str: 不含命名空间的标签名。
        """
        return tag.rsplit("}", 1)[-1]
