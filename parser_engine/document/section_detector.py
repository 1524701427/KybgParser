"""章节识别器。"""

from __future__ import annotations

import re

from parser_engine.document.ast.document import DocumentAST
from parser_engine.core.logger import logger


class SectionDetector:
    """根据标题结构构建章节路径。"""

    def __init__(self, section_config: dict | None = None):
        self.section_aliases = self._build_section_aliases(section_config or {})

    def detect(self, ast: DocumentAST) -> DocumentAST:
        """识别章节并给块/表格挂载章节路径。

        Args:
            ast: 文档 AST。

        Returns:
            DocumentAST: 增加 section_path 后的 AST。
        """
        section_stack: list[str] = []
        for block in ast.blocks:
            if block.meta.get("structure_type") == "heading":
                level = block.meta.get("heading_level") or 1
                title = self._clean_heading_title(block.text)
                section_stack = section_stack[: max(level - 1, 0)]
                section_stack.append(title)
                block.section_path = section_stack.copy()
            else:
                if section_stack or not block.section_path:
                    block.section_path = section_stack.copy()
            self._attach_canonical_sections(block)
            if block.type == "table":
                table_id = block.meta.get("table_id")
                table = ast.get_table(table_id) if table_id else None
                if table:
                    anchored_sections = self._sections_from_table_title(table)
                    if anchored_sections:
                        block.section_path = anchored_sections.copy()
                    table.section_path = anchored_sections or block.section_path.copy()
                    block.meta["canonical_sections"] = self._canonical_sections_for_path(block.section_path)
                    table.meta["canonical_sections"] = self._canonical_sections_for_path(table.section_path)
        logger.info("章节识别完成")
        return ast

    def _clean_heading_title(self, text: str) -> str:
        """清洗标题文本。

        Args:
            text: 原始标题。

        Returns:
            str: 清洗后的标题。
        """
        return text.strip().replace("\t", " ")

    def _build_section_aliases(self, section_config: dict) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for config in (section_config.get("sections") or {}).values():
            name = config.get("name")
            if not name:
                continue
            aliases = [name, *(config.get("aliases") or [])]
            for alias in aliases:
                if alias:
                    items.append((name, alias))
        return sorted(set(items), key=lambda item: len(item[1]), reverse=True)

    def _attach_canonical_sections(self, block) -> None:
        section_text = " / ".join(block.section_path)
        matched: list[str] = []
        for name, alias in self.section_aliases:
            if alias in section_text and name not in matched:
                matched.append(name)
        if matched:
            block.meta["canonical_sections"] = matched
        else:
            block.meta["canonical_sections"] = []

    def _canonical_sections_for_path(self, section_path: list[str]) -> list[str]:
        """根据章节路径文本返回归一化章节名称。"""
        section_text = " / ".join(section_path)
        matched: list[str] = []
        for name, alias in self.section_aliases:
            if alias in section_text and name not in matched:
                matched.append(name)
        return matched

    def _sections_from_table_title(self, table) -> list[str]:
        """用表题候选反向修正表格章节。

        Args:
            table: 当前表格对象。

        Returns:
            list[str]: 通过表题识别出的章节路径；无法判断时返回空列表。
        """
        title_text = self._table_title_text(table)
        if not title_text:
            return []
        # 财务附表、概算表、土建工程量这几类最容易因 Word/PDF 结构丢失章节锚点，优先用表题补齐。
        mappings = [
            ("财务", [r"附表\s*(?:16\.)?\d+", r"财务指标", r"现金流量", r"资产负债", r"总成本费用", r"利润与利润分配", r"借款还本付息", r"敏感性分析"]),
            ("技经概算", [r"主要技术经济指标表", r"工程总概算表", r"(?:施工辅助工程|设备及安装工程|建筑工程|其他费用)概算表"]),
            ("箱变基础", [r"箱变基础", r"箱式变电站基础", r"机组变压器基础"]),
            ("土石方平衡", [r"土石方平衡"]),
            ("道路", [r"道路.*(?:工程数量表|主要工程量表)"]),
            ("用地", [r"征地", r"用地"]),
            ("风机基础", [r"基础尺寸及参数表", r"基础断面表"]),
        ]
        for section, patterns in mappings:
            if any(re.search(pattern, title_text) for pattern in patterns):
                return [section]
        return []

    def _table_title_text(self, table) -> str:
        """拼接表格已有 caption 和结构层标题候选。"""
        parts: list[str] = []
        if getattr(table, "caption", None):
            parts.append(str(table.caption))
        meta = getattr(table, "meta", {}) if isinstance(getattr(table, "meta", {}), dict) else {}
        for key in ("best_title", "caption_before"):
            if meta.get(key):
                parts.append(str(meta.get(key)))
        for candidate in meta.get("title_candidates") or []:
            if isinstance(candidate, dict) and candidate.get("text"):
                parts.append(str(candidate.get("text")))
        for candidate in meta.get("layout_title_candidates") or []:
            if isinstance(candidate, dict) and candidate.get("text"):
                parts.append(str(candidate.get("text")))
        return " / ".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))
