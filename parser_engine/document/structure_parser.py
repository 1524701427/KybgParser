"""文档结构解析器。"""

from __future__ import annotations

import re

from parser_engine.document.ast.document import DocumentAST
from parser_engine.core.logger import logger


class StructureParser:
    """识别标题、表题、图题和普通正文。"""

    TABLE_TITLE_KEYWORDS = (
        "表",
        "附表",
        "清单",
        "工程量",
        "概算",
        "估算",
        "汇总",
        "统计",
        "成果",
        "计算",
        "参数",
        "材料",
        "设备",
        "箱变基础",
        "土石方平衡",
        "财务指标",
        "敏感性分析",
    )

    TABLE_TITLE_BODY_HINTS = (
        "本工程",
        "其中",
        "采用",
        "设置",
        "根据",
        "通过",
        "因此",
        "另外",
        "同时",
        "满足",
    )

    HEADING_PATTERNS = [
        re.compile(r"^第[一二三四五六七八九十百]+[章节篇]\s*"),
        re.compile(r"^[一二三四五六七八九十]+[、.]\s*"),
        re.compile(r"^\d+(?:\.\d+){0,3}\s+"),
    ]

    def parse(self, ast: DocumentAST) -> DocumentAST:
        """解析文档结构。

        Args:
            ast: 文档 AST。

        Returns:
            DocumentAST: 增加结构信息后的 AST。
        """
        for index, block in enumerate(ast.blocks):
            if block.type == "paragraph":
                block.meta["structure_type"] = self._detect_paragraph_type(block.text, block.style)
                block.meta["heading_level"] = self._detect_heading_level(block.text, block.style)
                # 表题通常紧邻表格，后续会挂到对应表格上。
                if self._is_table_caption(block.text):
                    block.meta["structure_type"] = "table_caption"
                if self._is_figure_caption(block.text):
                    block.meta["structure_type"] = "figure_caption"
            elif block.type == "table":
                block.meta["structure_type"] = "table"
                self._attach_caption(ast, block, index)
        logger.info("文档结构识别完成")
        return ast

    def _detect_paragraph_type(self, text: str, style) -> str:
        """识别段落类型。

        Args:
            text: 段落文本。
            style: 样式信息。

        Returns:
            str: `heading` 或 `paragraph`。
        """
        if self._detect_heading_level(text, style):
            return "heading"
        return "paragraph"

    def _detect_heading_level(self, text: str, style) -> int | None:
        """识别标题级别。

        Args:
            text: 段落文本。
            style: 样式信息。

        Returns:
            int | None: 标题级别，非标题返回 None。
        """
        style_name = (getattr(style, "style_name", None) or "").lower()
        if "heading" in style_name:
            match = re.search(r"(\d+)", style_name)
            return int(match.group(1)) if match else 1
        if len(text) <= 40 and any(pattern.match(text) for pattern in self.HEADING_PATTERNS):
            if self._looks_like_numbered_body_text(text):
                return None
            # 编号中点越多，标题层级越深。
            prefix = text.split()[0]
            if re.match(r"^\d+(?:\.\d+)+", prefix):
                return min(prefix.count(".") + 1, 4)
            return 1
        if len(text) <= 20 and getattr(style, "bold", False):
            return 2
        return None

    def _looks_like_numbered_body_text(self, text: str) -> bool:
        """排除被编号标题模式误命中的工程数量正文。"""
        stripped = text.strip()
        if stripped.endswith(("。", "；", ";", "，", ",")):
            return True
        if re.match(r"^\d+(?:\.\d+)?\s*(千米|公里|km|KM|基|台|面|根|支|套|回|m|M|kV|KV|kVA|KVA|MW|MVA)\b", stripped):
            return True
        if re.search(r"(?:约|其中|包括|采用|设置|布置|满足|形成|达到|根据|通过|因此|另外|同时)", stripped) and len(stripped) > 12:
            return True
        if len(re.findall(r"\d+(?:\.\d+)?", stripped)) >= 2:
            return True
        return False

    def _is_table_caption(self, text: str) -> bool:
        """判断是否表题。

        Args:
            text: 段落文本。

        Returns:
            bool: 是否表题。
        """
        cleaned = self._clean_text(text)
        if not cleaned:
            return False
        patterns = [
            r"^(?:附表|表)\s*[\d一二三四五六七八九十]+(?:[.．、\-－]\d+)*\s*[：:、.．]?\s*\S+",
            r"^\d+(?:\.\d+){1,4}(?:\s*[-－]\s*\d+)?\s+.*(?:表|清单|工程量|概算|估算|汇总|统计|成果|计算|参数|材料|设备)",
        ]
        return any(re.search(pattern, cleaned) for pattern in patterns)

    def _is_figure_caption(self, text: str) -> bool:
        """判断是否图题。

        Args:
            text: 段落文本。

        Returns:
            bool: 是否图题。
        """
        return bool(re.match(r"^图\s*[\d一二三四五六七八九十.-]+", text))

    def _attach_caption(self, ast: DocumentAST, table_block, block_index: int) -> None:
        """将表题挂到表格对象。

        Args:
            ast: 文档 AST。
            table_block: 表格占位块。
            block_index: 表格占位块位置。
        """
        table_id = table_block.meta.get("table_id")
        table = ast.get_table(table_id) if table_id else None
        if table is None:
            return
        candidates = self._table_title_candidates(ast, table, block_index)
        table.meta["title_candidates"] = candidates
        if candidates:
            table.meta["best_title"] = candidates[0]["text"]
            table.meta["caption_source"] = candidates[0]["source"]
            table.meta["caption_score"] = candidates[0]["score"]
        # 只有候选分数达到阈值时才写入 caption，避免普通正文误挂到表格上。
        for candidate in candidates:
            if candidate.get("crossedTable"):
                continue
            if float(candidate.get("score") or 0.0) < 2.5:
                continue
            table.caption = candidate["text"]
            if candidate.get("source") in {"table_caption", "nearby_title", "styled_title", "heading", "layout_linked_caption", "layout_nearby_title", "layout_caption"}:
                table.meta["caption_before"] = candidate["text"]
            return

    def _table_title_candidates(self, ast: DocumentAST, table, block_index: int) -> list[dict]:
        """收集表格的多来源表题候选。

        Args:
            ast: 文档 AST。
            table: 当前表格对象。
            block_index: 当前表格占位块在 blocks 中的位置。

        Returns:
            list[dict]: 按可信度从高到低排序后的表题候选。
        """
        candidates: list[dict] = []
        if table.caption:
            candidates.append({"source": "caption", "text": self._clean_text(table.caption), "score": 5.0})
        candidates.extend(self._layout_title_candidates(table))
        candidates.extend(self._previous_paragraph_title_candidates(ast, table, block_index))
        first_row_title = self._table_first_row_title_candidate(table)
        if first_row_title:
            candidates.append({"source": "table_first_row", "text": first_row_title, "score": 3.2})
        return self._deduplicate_title_candidates(candidates)

    def _layout_title_candidates(self, table) -> list[dict]:
        """读取 PDF layout sidecar 写入的标题候选。"""
        results: list[dict] = []
        for candidate in (table.meta.get("layout_title_candidates") or []) if isinstance(table.meta, dict) else []:
            if not isinstance(candidate, dict):
                continue
            text = self._clean_text(candidate.get("text") or "")
            if not text:
                continue
            results.append(
                {
                    **candidate,
                    "source": candidate.get("source") or "layout_title",
                    "text": text,
                    "score": float(candidate.get("score") or 0.0),
                }
            )
        return results

    def _previous_paragraph_title_candidates(self, ast: DocumentAST, table, block_index: int) -> list[dict]:
        """从表格前方段落中寻找题注、正文标题和样式标题候选。

        Args:
            ast: 文档 AST。
            table: 当前表格对象。
            block_index: 当前表格占位块位置。

        Returns:
            list[dict]: 表前段落候选列表。
        """
        candidates: list[dict] = []
        previous_blocks = ast.blocks[:block_index]
        for distance, block in enumerate(reversed(previous_blocks[-12:]), start=1):
            if block.type != "paragraph":
                continue
            text = self._clean_text(block.text or "")
            if not text:
                continue
            crossed_table = any(candidate.type == "table" for candidate in ast.blocks if block.order < candidate.order < table.order)
            score = self._score_paragraph_title_candidate(block, table, distance, crossed_table)
            if score <= 0:
                continue
            source = self._paragraph_title_source(block, text)
            candidates.append(
                {
                    "source": source,
                    "text": text,
                    "score": score,
                    "blockId": block.id,
                    "order": block.order,
                    "page": block.page,
                    "crossedTable": crossed_table,
                }
            )
        return candidates

    def _score_paragraph_title_candidate(self, block, table, distance: int, crossed_table: bool) -> float:
        """给表前段落表题候选打分。

        Args:
            block: 表前段落块。
            table: 当前表格对象。
            distance: 段落距离表格的倒序距离，1 表示紧邻表格。
            crossed_table: 候选和当前表格之间是否隔着其他表格。

        Returns:
            float: 候选可信度分数。
        """
        text = self._clean_text(block.text or "")
        if not text:
            return 0.0
        score = 0.0
        if self._is_table_caption(text):
            score += 4.0
        if self._looks_like_table_title_text(text):
            score += 1.8
        structure_type = block.meta.get("structure_type")
        if structure_type == "table_caption":
            score += 1.2
        elif structure_type == "heading":
            score += 0.8
        style = block.style
        if getattr(style, "bold", False):
            score += 0.5
        if str(getattr(style, "alignment", "") or "").lower() in {"center", "centre", "居中"}:
            score += 0.6
        font_size = getattr(style, "font_size", None)
        try:
            if font_size is not None and float(font_size) >= 11:
                score += 0.2
        except (TypeError, ValueError):
            pass
        score += self._page_proximity_score(block, table)
        score += self._bbox_proximity_score(block, table)
        if len(text) <= 80:
            score += 0.4
        if distance <= 2:
            score += 0.8
        elif distance <= 5:
            score += 0.3
        if crossed_table:
            score -= 2.5
        if self._looks_like_body_sentence(text):
            score -= 2.0
        if len(text) > 140:
            score -= 2.0
        return score

    def _page_proximity_score(self, block, table) -> float:
        """根据段落和表格页码给题注候选加权。"""
        table_page = table.page or (table.meta.get("layout_page") if isinstance(table.meta, dict) else None)
        if block.page is None or table_page is None:
            return 0.0
        try:
            delta = abs(int(table_page) - int(block.page))
        except (TypeError, ValueError):
            return 0.0
        if delta == 0:
            return 0.5
        if delta == 1:
            return 0.15
        return -1.0

    def _bbox_proximity_score(self, block, table) -> float:
        """根据段落和表格 bbox 垂直距离给题注候选加权。"""
        block_meta = block.meta if isinstance(block.meta, dict) else {}
        table_meta = table.meta if isinstance(table.meta, dict) else {}
        block_box = self._bbox_tuple(block_meta.get("bounding_box") or block_meta.get("bbox"))
        table_box = self._bbox_tuple(table_meta.get("bounding_box") or table_meta.get("layout_bbox") or table_meta.get("bbox"))
        if block_box is None or table_box is None:
            return 0.0
        _, _, _, block_bottom = block_box
        _, table_top, _, _ = table_box
        gap = table_top - block_bottom
        if 0 <= gap <= 40:
            return 0.6
        if 40 < gap <= 100:
            return 0.25
        if gap < -5:
            return -0.5
        return 0.0

    def _paragraph_title_source(self, block, text: str) -> str:
        """标记表题候选来自题注、标题还是样式段落。"""
        if block.meta.get("structure_type") == "table_caption" or self._is_table_caption(text):
            return "table_caption"
        style = block.style
        if getattr(style, "bold", False) or str(getattr(style, "alignment", "") or "").lower() in {"center", "centre", "居中"}:
            return "styled_title"
        if block.meta.get("structure_type") == "heading":
            return "heading"
        return "nearby_title"

    def _looks_like_table_title_text(self, text: str) -> bool:
        """判断短文本是否像业务表题或表格标题。"""
        cleaned = self._clean_text(text)
        if not cleaned or len(cleaned) > 120:
            return False
        if self._looks_like_body_sentence(cleaned):
            return False
        if cleaned.startswith(("表", "附表")):
            return True
        if re.match(r"^\d+(?:\.\d+){1,4}(?:[.．、\-－]\d+)*\s+", cleaned):
            return any(keyword in cleaned for keyword in self.TABLE_TITLE_KEYWORDS if keyword not in {"表", "附表"})
        return any(keyword in cleaned for keyword in self.TABLE_TITLE_KEYWORDS)

    def _looks_like_body_sentence(self, text: str) -> bool:
        """排除看起来像正文叙述句的候选。"""
        cleaned = self._clean_text(text)
        if cleaned.endswith(("。", "；", ";")):
            return True
        return bool(len(cleaned) > 30 and any(keyword in cleaned for keyword in self.TABLE_TITLE_BODY_HINTS))

    def _table_first_row_title_candidate(self, table) -> str:
        """从表格首行识别内嵌表题。"""
        if not table.rows:
            return ""
        first_row = [self._clean_text(cell.text) for cell in table.rows[0] if self._clean_text(cell.text)]
        if len(first_row) == 1 and self._looks_like_table_title_text(first_row[0]):
            return first_row[0]
        joined = self._clean_text(" ".join(first_row))
        if len(first_row) <= 3 and self._looks_like_table_title_text(joined):
            return joined
        return ""

    def _deduplicate_title_candidates(self, candidates: list[dict]) -> list[dict]:
        """按文本去重并按分数排序表题候选。"""
        deduped: dict[str, dict] = {}
        for candidate in candidates:
            text = self._clean_text(candidate.get("text") or "")
            if not text:
                continue
            normalized = re.sub(r"\s+", "", text)
            existing = deduped.get(normalized)
            item = {**candidate, "text": text, "score": round(float(candidate.get("score") or 0.0), 3)}
            source = str(item.get("source") or "")
            if existing is None:
                item["sources"] = [source] if source else []
                deduped[normalized] = item
                continue
            existing_sources = list(existing.get("sources") or [])
            if not existing_sources and existing.get("source"):
                existing_sources.append(str(existing.get("source")))
            if source and source not in existing_sources:
                existing_sources.append(source)
            if item["score"] > float(existing.get("score") or 0.0):
                item["sources"] = existing_sources
                deduped[normalized] = item
            else:
                existing["sources"] = existing_sources
        return sorted(deduped.values(), key=lambda item: (float(item.get("score") or 0.0), int(item.get("order") or 0)), reverse=True)

    def _clean_text(self, text: str) -> str:
        """清理段落文本中的控制字符和重复空白。"""
        text = re.sub(r"[\x00-\x1f]", " ", str(text or ""))
        return re.sub(r"\s+", " ", text).strip()

    def _bbox_tuple(self, bbox) -> tuple[float, float, float, float] | None:
        """把常见 bbox 格式归一为 `(x0, y0, x1, y1)`。"""
        if isinstance(bbox, dict):
            values = [bbox.get(name) for name in ("x0", "y0", "x1", "y1")]
            if any(value is not None for value in values):
                try:
                    return tuple(float(value) for value in values)  # type: ignore[return-value]
                except (TypeError, ValueError):
                    return None
            values = [bbox.get(name) for name in ("left", "top", "right", "bottom")]
            if any(value is not None for value in values):
                try:
                    return tuple(float(value) for value in values)  # type: ignore[return-value]
                except (TypeError, ValueError):
                    return None
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                return tuple(float(value) for value in bbox[:4])  # type: ignore[return-value]
            except (TypeError, ValueError):
                return None
        return None
