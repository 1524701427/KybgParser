"""OpenDataLoader PDF 版面旁路增强。

该模块只把 PDF 视觉版面的表题、页码和 bbox 信息挂回 Word AST，
不替代 Word 表格单元格，也不直接参与字段抽值。
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable
from parser_engine.core.logger import logger


@dataclass
class LayoutTable:
    """PDF 版面中的表格摘要。"""

    id: Any
    order: int
    page: int | None
    bbox: Any = None
    caption: str | None = None
    linked_caption: str | None = None
    nearby_titles: list[dict[str, Any]] = field(default_factory=list)
    matrix_preview: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为可写入 AST meta 的普通字典。"""
        return asdict(self)


class OpenDataLoaderLayoutSidecar:
    """用 OpenDataLoader PDF 结果增强 Word AST 的表格标题元信息。"""

    def __init__(self, table_method: str = "cluster", reading_order: str = "xycut"):
        """初始化版面旁路解析器。

        Args:
            table_method: OpenDataLoader 表格解析方法。
            reading_order: OpenDataLoader 阅读顺序方法。
        """
        self.table_method = table_method
        self.reading_order = reading_order

    def enrich_ast_from_pdf(self, ast: DocumentAST, pdf_path: str | Path) -> DocumentAST:
        """解析 PDF 版面并把候选标题挂回 Word AST。

        Args:
            ast: Word loader 已经生成的 AST。
            pdf_path: 由同一个 Word 文档转换出的 PDF 路径。

        Returns:
            DocumentAST: 写入 layout_sidecar 元信息后的 AST。
        """
        pdf_path = Path(pdf_path)
        try:
            layout_tables = self.parse_pdf_tables(pdf_path)
        except Exception as exc:
            logger.warning(f"OpenDataLoader layout sidecar skipped: {exc}")
            ast.meta.setdefault("layout_sidecar", {})["status"] = "failed"
            ast.meta.setdefault("layout_sidecar", {})["error"] = str(exc)
            return ast
        self.attach_layout_tables(ast, layout_tables)
        ast.meta["layout_sidecar"] = {
            "status": "ok",
            "source": "opendataloader-pdf",
            "pdf": str(pdf_path),
            "tableCount": len(layout_tables),
        }
        return ast

    def parse_pdf_tables(self, pdf_path: Path) -> list[LayoutTable]:
        """调用 OpenDataLoader 并解析出 PDF 表格版面摘要。"""
        try:
            from opendataloader_pdf import convert  # type: ignore
        except Exception as exc:
            raise RuntimeError("缺少 opendataloader-pdf，无法启用 PDF layout sidecar") from exc

        with tempfile.TemporaryDirectory(prefix="opendataloader_sidecar_") as output_dir:
            convert(
                input_path=str(pdf_path),
                output_dir=output_dir,
                format="json",
                quiet=True,
                table_method=self.table_method,
                reading_order=self.reading_order,
                image_output="off",
            )
            data = json.loads(self._find_output_json(Path(output_dir), pdf_path).read_text(encoding="utf-8"))
        return self._layout_tables_from_json(data)

    def attach_layout_tables(self, ast: DocumentAST, layout_tables: list[LayoutTable]) -> None:
        """把 PDF layout table 按顺序和表头相似度匹配回 Word 表。

        Args:
            ast: Word AST。
            layout_tables: PDF 版面表格摘要。
        """
        used_layout_indexes: set[int] = set()
        for word_index, table in enumerate(sorted(ast.tables, key=lambda item: item.order)):
            layout_index, score = self._best_layout_match(table, layout_tables, used_layout_indexes, word_index)
            if layout_index is None:
                continue
            used_layout_indexes.add(layout_index)
            layout_table = layout_tables[layout_index]
            self._attach_layout_table(table, layout_table, score)

    def _layout_tables_from_json(self, data: dict[str, Any]) -> list[LayoutTable]:
        """从 OpenDataLoader JSON 中提取表格、题注和表前标题。"""
        nodes = list(data.get("kids") or [])
        caption_by_target = self._caption_links(nodes)
        previous_text_items: list[dict[str, Any]] = []
        tables: list[LayoutTable] = []
        for order, node in enumerate(nodes):
            node_type = str(node.get("type") or "").lower()
            page = self._page_number(node)
            if node_type == "table":
                matrix = self._table_matrix(node)
                if not matrix:
                    continue
                linked_caption = caption_by_target.get(str(node.get("id")))
                nearby_titles = self._nearby_title_candidates(previous_text_items, page, node.get("bounding box"))
                caption = linked_caption or (nearby_titles[0]["text"] if nearby_titles else None)
                tables.append(
                    LayoutTable(
                        id=node.get("id"),
                        order=order,
                        page=page,
                        bbox=node.get("bounding box"),
                        caption=caption,
                        linked_caption=linked_caption,
                        nearby_titles=nearby_titles,
                        matrix_preview=matrix[:8],
                    )
                )
                continue
            if node_type in {"caption", "paragraph"}:
                text = self._clean_text(str(node.get("content") or ""))
                if text:
                    item = {
                        "id": node.get("id"),
                        "type": node_type,
                        "text": text,
                        "page": page,
                        "bbox": node.get("bounding box"),
                        "order": order,
                    }
                    # OpenDataLoader 的样式字段随版本会有差异，这里只做宽松保留，后续打分按有则使用。
                    item.update(self._node_style_summary(node))
                    previous_text_items.append(
                        item
                    )
        return tables

    def _attach_layout_table(self, table: DocumentTable, layout_table: LayoutTable, score: float) -> None:
        """把匹配到的 PDF 表格版面信息写入 Word 表 meta。"""
        table.meta["layout_table"] = layout_table.to_dict()
        table.meta["layout_match_score"] = round(score, 3)
        table.meta["layout_page"] = layout_table.page
        table.meta["layout_bbox"] = layout_table.bbox
        if table.page is None:
            table.page = layout_table.page
        candidates = self._layout_title_candidates(layout_table)
        if candidates:
            table.meta["layout_title_candidates"] = candidates
            # 不直接覆盖 Word caption，只给结构层一个更强候选源。
            table.meta.setdefault("caption_before", candidates[0]["text"])

    def _layout_title_candidates(self, layout_table: LayoutTable) -> list[dict[str, Any]]:
        """把 PDF 表题和表前标题转换为统一候选结构。"""
        candidates: list[dict[str, Any]] = []
        if layout_table.linked_caption:
            candidates.append(
                {
                    "source": "layout_linked_caption",
                    "text": layout_table.linked_caption,
                    "score": 6.0,
                    "page": layout_table.page,
                    "bbox": layout_table.bbox,
                }
            )
        for title in layout_table.nearby_titles:
            candidates.append(
                {
                    "source": "layout_nearby_title",
                    "text": title.get("text"),
                    "score": float(title.get("score") or 0.0) + 1.5,
                    "page": layout_table.page,
                    "bbox": title.get("bbox"),
                    "distance": title.get("distance"),
                }
            )
        if layout_table.caption and not any(candidate.get("text") == layout_table.caption for candidate in candidates):
            candidates.append(
                {
                    "source": "layout_caption",
                    "text": layout_table.caption,
                    "score": 4.5,
                    "page": layout_table.page,
                    "bbox": layout_table.bbox,
                }
            )
        return self._deduplicate_candidates(candidates)

    def _best_layout_match(
        self,
        word_table: DocumentTable,
        layout_tables: list[LayoutTable],
        used_layout_indexes: set[int],
        word_index: int,
    ) -> tuple[int | None, float]:
        """给一张 Word 表找到最可能对应的 PDF layout 表。"""
        best_index: int | None = None
        best_score = 0.0
        for layout_index, layout_table in enumerate(layout_tables):
            if layout_index in used_layout_indexes:
                continue
            score = self._layout_match_score(word_table, layout_table, word_index, layout_index, len(layout_tables))
            if score > best_score:
                best_index = layout_index
                best_score = score
        if best_score < 0.35:
            return None, best_score
        return best_index, best_score

    def _layout_match_score(self, word_table: DocumentTable, layout_table: LayoutTable, word_index: int, layout_index: int, total_layout_tables: int) -> float:
        """计算 Word 表和 PDF layout 表的粗匹配分数。"""
        word_text = self._matrix_signature(word_table.to_matrix())
        layout_text = self._matrix_signature(layout_table.matrix_preview)
        text_score = self._token_overlap_score(word_text, layout_text)
        order_score = max(0.0, 1.0 - abs(word_index - layout_index) / max(total_layout_tables, 8))
        shape_score = self._table_shape_score(word_table.to_matrix(), layout_table.matrix_preview)
        return text_score * 0.7 + order_score * 0.2 + shape_score * 0.1

    def _table_shape_score(self, left: list[list[str]], right: list[list[str]]) -> float:
        """按行列形态给 Word 表和 PDF 表增加一个弱匹配分。"""
        left_cols = max((len(row) for row in left), default=0)
        right_cols = max((len(row) for row in right), default=0)
        if not left or not right or left_cols <= 0 or right_cols <= 0:
            return 0.0
        row_score = min(len(left), len(right)) / max(len(left), len(right))
        col_score = min(left_cols, right_cols) / max(left_cols, right_cols)
        return (row_score + col_score) / 2

    def _matrix_signature(self, matrix: list[list[str]], max_rows: int = 4) -> str:
        """取表格前几行生成匹配签名。"""
        rows = matrix[:max_rows]
        text = " ".join(cell for row in rows for cell in row if cell)
        return self._clean_text(text)

    def _token_overlap_score(self, left: str, right: str) -> float:
        """用字符 n-gram 重叠度近似表头/表身相似度。"""
        left_tokens = self._char_tokens(left)
        right_tokens = self._char_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _char_tokens(self, text: str) -> set[str]:
        """生成用于粗匹配的字符 token 集。"""
        compact = re.sub(r"\s+", "", text)
        if len(compact) <= 1:
            return {compact} if compact else set()
        return {compact[index : index + 2] for index in range(len(compact) - 1)}

    def _caption_links(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        """提取 OpenDataLoader caption 到 table id 的链接。"""
        links: dict[str, str] = {}
        for node in nodes:
            if str(node.get("type") or "").lower() != "caption":
                continue
            target_id = node.get("linked content id")
            text = self._clean_text(str(node.get("content") or ""))
            if target_id is not None and text:
                links[str(target_id)] = text
        return links

    def _nearby_title_candidates(self, items: list[dict[str, Any]], table_page: int | None, table_bbox: Any, window: int = 12) -> list[dict[str, Any]]:
        """从 PDF 表前文本中筛选疑似标题。

        Args:
            items: 阅读顺序中已经出现在当前表之前的文本块。
            table_page: 当前表所在页。
            table_bbox: 当前表的版面框。
            window: 最多回看多少个文本块。

        Returns:
            list[dict[str, Any]]: 按综合分排序后的标题候选。
        """
        candidates: list[dict[str, Any]] = []
        for distance, item in enumerate(reversed(items[-window:]), start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue
            score = self._score_title_text(text, distance, item, table_page, table_bbox)
            if score <= 0:
                continue
            candidates.append(
                {
                    "text": text,
                    "score": score,
                    "sourceType": item.get("type"),
                    "id": item.get("id"),
                    "distance": distance,
                    "bbox": item.get("bbox"),
                    "page": item.get("page"),
                    "fontSize": item.get("fontSize"),
                    "bold": item.get("bold"),
                    "alignment": item.get("alignment"),
                    "indent": item.get("indent"),
                }
            )
        return sorted(candidates, key=lambda item: item["score"], reverse=True)

    def _score_title_text(self, text: str, distance: int, item: dict[str, Any], table_page: int | None, table_bbox: Any) -> float:
        """给 PDF 表前文本候选打分。"""
        score = 0.0
        if str(item.get("type") or "").lower() == "caption":
            score += 3.0
        if self._looks_like_table_title(text):
            score += 2.0
        if len(text) <= 80:
            score += 0.5
        if distance <= 2:
            score += 0.8
        elif distance <= 5:
            score += 0.3
        if table_page is not None and item.get("page") is not None:
            page_delta = abs(int(table_page) - int(item.get("page")))
            if page_delta == 0:
                score += 0.8
            elif page_delta == 1:
                score += 0.2
            else:
                score -= 1.5
        score += self._style_title_score(item)
        score += self._vertical_gap_score(item.get("bbox"), table_bbox)
        if text.endswith(("。", "；", ";")):
            score -= 2.0
        return round(score, 3)

    def _style_title_score(self, item: dict[str, Any]) -> float:
        """把 PDF 文本块样式信号转换为弱标题分。"""
        score = 0.0
        if item.get("bold") is True:
            score += 0.5
        alignment = str(item.get("alignment") or "").lower()
        if alignment in {"center", "centre", "middle", "居中"}:
            score += 0.6
        font_size = item.get("fontSize")
        try:
            if font_size is not None and float(font_size) >= 11:
                score += 0.2
        except (TypeError, ValueError):
            pass
        return score

    def _vertical_gap_score(self, item_bbox: Any, table_bbox: Any) -> float:
        """根据候选文本和表格的垂直距离给版面相邻性加分。"""
        item_box = self._bbox_tuple(item_bbox)
        table_box = self._bbox_tuple(table_bbox)
        if item_box is None or table_box is None:
            return 0.0
        _, _, _, item_bottom = item_box
        _, table_top, _, _ = table_box
        gap = table_top - item_bottom
        if 0 <= gap <= 40:
            return 0.8
        if 40 < gap <= 100:
            return 0.3
        if gap < -5:
            return -0.5
        return 0.0

    def _looks_like_table_title(self, text: str) -> bool:
        """判断 PDF 文本块是否像表题。"""
        cleaned = self._clean_text(text)
        if not cleaned or len(cleaned) > 120:
            return False
        if re.search(r"^(?:附表|表|Table)\s*[\d一二三四五六七八九十A-Za-z.\-－]+", cleaned, flags=re.IGNORECASE):
            return True
        return any(keyword in cleaned for keyword in ("表", "清单", "工程量", "概算", "估算", "汇总", "统计", "成果", "计算", "参数", "材料", "设备"))

    def _table_matrix(self, node: dict[str, Any]) -> list[list[str]]:
        """从 OpenDataLoader table 节点读取文本矩阵。"""
        matrix: list[list[str]] = []
        for row in node.get("rows") or []:
            parsed = [self._cell_text(cell) for cell in (row.get("cells") or [])]
            if any(parsed):
                matrix.append(parsed)
        max_cols = max((len(row) for row in matrix), default=0)
        return [row + [""] * (max_cols - len(row)) for row in matrix]

    def _cell_text(self, cell: dict[str, Any]) -> str:
        """读取 PDF 表格单元格文本。"""
        parts: list[str] = []
        for kid in cell.get("kids") or []:
            text = self._clean_text(str(kid.get("content") or ""))
            if text:
                parts.append(text)
        return self._clean_text(" ".join(parts))

    def _deduplicate_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按标题文本去重 layout 候选。"""
        deduped: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            text = self._clean_text(candidate.get("text") or "")
            if not text:
                continue
            key = re.sub(r"\s+", "", text)
            item = {**candidate, "text": text, "score": round(float(candidate.get("score") or 0.0), 3)}
            if key not in deduped or item["score"] > float(deduped[key].get("score") or 0.0):
                deduped[key] = item
        return sorted(deduped.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)

    def _page_number(self, node: dict[str, Any]) -> int | None:
        """读取节点页码。"""
        value = node.get("page number")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _node_style_summary(self, node: dict[str, Any]) -> dict[str, Any]:
        """宽松提取 OpenDataLoader 文本节点里的样式信号。"""
        style = node.get("style") if isinstance(node.get("style"), dict) else {}
        source = {**style, **node}
        summary: dict[str, Any] = {}
        font_size = self._first_existing(source, ["font size", "font_size", "font-size", "fontSize", "size"])
        if font_size is not None:
            summary["fontSize"] = font_size
        bold = self._first_existing(source, ["bold", "is bold", "is_bold", "font bold", "font_bold"])
        if bold is not None:
            summary["bold"] = self._to_bool(bold)
        alignment = self._first_existing(source, ["alignment", "align", "text alignment", "text_align"])
        if alignment is not None:
            summary["alignment"] = str(alignment)
        indent = self._first_existing(source, ["indent", "left indent", "left_indent", "x indent"])
        if indent is not None:
            summary["indent"] = indent
        return summary

    def _first_existing(self, data: dict[str, Any], names: list[str]) -> Any:
        """按多个可能的字段名读取第一个非空值。"""
        for name in names:
            if name in data and data.get(name) not in (None, ""):
                return data.get(name)
        return None

    def _to_bool(self, value: Any) -> bool:
        """把 OpenDataLoader 可能输出的布尔样式值归一成 bool。"""
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "bold", "加粗"}

    def _bbox_tuple(self, bbox: Any) -> tuple[float, float, float, float] | None:
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

    def _find_output_json(self, output_dir: Path, source_path: Path) -> Path:
        """查找 OpenDataLoader 输出 JSON。"""
        direct = output_dir / f"{source_path.stem}.json"
        if direct.exists():
            return direct
        matches = list(output_dir.glob("*.json"))
        if matches:
            return matches[0]
        raise RuntimeError("OpenDataLoader 未生成 JSON 输出")

    def _clean_text(self, text: str) -> str:
        """清理控制字符和重复空白。"""
        text = re.sub(r"[\x00-\x1f]", " ", str(text or ""))
        return re.sub(r"\s+", " ", text).strip()
