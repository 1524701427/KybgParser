"""正文块、章节、表格查询和标题识别辅助方法。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable
from word_parser.document.ast.evidence import FieldEvidence, ParsedField


class DocumentQuerySupportMixin:
    """正文块、章节、表格查询和标题识别辅助方法，由 DocumentSupportMixin 统一组合。"""

    def _body_blocks(self, ast: DocumentAST) -> list[DocumentBlock]:
        return [block for block in ast.blocks if block.text and not self._is_toc_block(block)]

    def _source_section_path(self, section_path: list[str], canonical_sections: Any = None) -> list[str]:
        canonical = list(dict.fromkeys(str(section) for section in (canonical_sections or []) if section))
        path = [str(section) for section in (section_path or []) if section]
        return [*canonical, *[section for section in path if section not in canonical]]

    def _inferred_source_sections(self, text: str) -> list[str]:
        compact = self._compact_text(text)
        result: list[str] = []
        rules = [
            ("集电线路", ["集电线路路径长", "单回集电线路", "双回集电线路", "双回架空路径长", "单回架空路径长"]),
            ("道路", ["进场道路", "进站道路", "场内道路", "改建长度", "改建道路", "道路改造"]),
            ("电气一次", ["风电场接入系统方式", "打捆送至", "汇集站", "主变"]),
            ("发电量章节", ["风电场年上网电量估算", "综合折减率", "年上网电量"]),
        ]
        for section, keywords in rules:
            if any(keyword in text or self._compact_text(keyword) in compact for keyword in keywords):
                result.append(section)
        return result

    def _is_toc_block(self, block: DocumentBlock) -> bool:
        meta = block.meta or {}
        if str(meta.get("structure_type") or meta.get("type") or "").lower() in {"toc", "table_of_contents"}:
            return True
        return self._is_toc_like_text(block.text or "")

    def _is_toc_like_text(self, text: str) -> bool:
        cleaned = self._clean_text(text or "")
        if not cleaned:
            return False
        compact = self._compact_text(cleaned)
        lowered = cleaned.lower()
        if any(marker.lower() in lowered for marker in ("HYPERLINK", "PAGEREF", "TOC ", "\\o ", "_Toc")):
            return True
        if compact in {"目录", "目錄", "contents"}:
            return True
        if compact.startswith("目录") and len(compact) < 120:
            return True
        toc_link_hits = len(re.findall(r"_Toc\d+|PAGEREF|HYPERLINK", cleaned, flags=re.IGNORECASE))
        if toc_link_hits >= 3:
            return True
        dotted_entries = len(re.findall(r"\d+(?:\.\d+)+[^\n]{0,50}(?:\.{3,}|…{2,}|\s{2,})\d+", cleaned))
        return "目录" in cleaned[:80] and dotted_entries >= 2

    def _page_section_path_map(self, ast: DocumentAST) -> dict[int, list[str]]:
        page_sections: dict[int, list[str]] = {}
        last_section: list[str] = []
        blocks = sorted((block for block in ast.blocks if block.page is not None), key=lambda item: item.order)
        for block in blocks:
            try:
                page = int(block.page) if block.page is not None else None
            except (TypeError, ValueError):
                page = None
            if page is None:
                continue
            if block.section_path:
                last_section = list(block.section_path)
                page_sections[page] = last_section
            elif last_section and page not in page_sections:
                page_sections[page] = last_section
        return page_sections

    def _field_evidence_text_for_value(self, ast: DocumentAST, value: Any, keywords: list[str]) -> str:
        value_text = str(value)
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if value_text in text and all(keyword in text for keyword in keywords if keyword):
                return text
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if value_text in text:
                return text
        return value_text

    def _table_index_value(self, row: list[str], index: int | None) -> Any:
        if index is None or index < 0 or index >= len(row):
            return None
        value = self._clean_text(row[index])
        return value or None

    def _extract_first_pattern_value(self, text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _keyword_window(self, text: str, keywords: list[str], radius: int) -> str:
        for keyword in keywords:
            index = text.find(keyword)
            if index >= 0:
                return text[max(0, index - radius) : min(len(text), index + radius)]
        return ""

    def _regex_from_blocks(self, ast: DocumentAST, pattern: str) -> str | None:
        for block in ast.blocks:
            found = re.search(pattern, block.text)
            if found:
                return found.group(1).strip()
        return None

    def _set_field(
        self,
        fields: dict[str, ParsedField],
        code: str,
        name: str,
        value: Any,
        unit: str | None,
        evidence_text: str,
        source_type: str = "table",
        meta: dict[str, Any] | None = None,
    ) -> None:
        meta = dict(meta or {})
        value, unit = self._normalize_configured_value(code, value, unit)
        section_path = meta.pop("sectionPath", [])
        block_id = meta.pop("blockId", None)
        table_id = meta.pop("tableId", None)
        page = meta.pop("page", None)
        evidence = FieldEvidence(source_type=source_type, text=evidence_text, score=1.0,
                                 block_id=block_id, table_id=table_id, page=page,
                                 section_path=section_path,
                                 match_method=meta.get("matchMethod") or "deterministic_override",
                                 meta=meta)
        if value is not None and hasattr(self, "context_filter"):
            from word_parser.document.ast.evidence import Extraction

            proposed = Extraction(field_code=code, field_name=name, raw_value=str(value),
                                  value=value, unit=unit, score=1.0,
                                  method="deterministic_override", evidence=evidence)
            accepted, _rejected = self.context_filter.filter([proposed])
            if not accepted:
                return
        fields[code] = ParsedField(
            field_code=code,
            field_name=name,
            value=value,
            unit=unit,
            normalized_value=value,
            confidence=0.99 if value is not None else 0.0,
            status="PASS" if value is not None else "MISSING",
            evidence=[evidence],
            debug={"resolver": meta.get("resolver") or "deterministic_override"},
        )

    def _table_matrix(self, table: DocumentTable) -> list[list[str]]:
        return [[cell.text.strip() for cell in self._expanded_row(row)] for row in table.rows]

    def _normalize_tower_code(self, text: str) -> str | None:
        if not text:
            return None
        normalized_text = str(text).replace("＃", "#")
        found = re.search(r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*#", normalized_text)
        if not found:
            return None
        code = re.sub(r"\s+", "", found.group(0))
        if re.fullmatch(r"\d+(?:m|M)#", code):
            return None
        return code

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[\x00-\x1f]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _clean_table_caption_title(self, caption: str) -> str:
        cleaned = self._clean_text(caption or "")
        if not cleaned:
            return ""
        markers = list(re.finditer(r"(?:附表|表)\s*\d+(?:\.\d+)*(?:-\s*\d+)?", cleaned))
        if markers and ("图" in cleaned[: markers[-1].start()] or len(markers) > 1):
            return self._clean_text(cleaned[markers[-1].start() :])
        return cleaned

    def _normalize_text_value(self, text: str) -> str:
        cleaned = self._clean_text(str(text))
        return cleaned.strip(" ?,??;?:")

    def _blocks_in_sections(self, ast: DocumentAST, section_keywords: list[str]) -> list[Any]:
        matched = [
            block
            for block in ast.blocks
            if self._section_path_matches(block.section_path, section_keywords)
        ]
        return matched or list(ast.blocks)

    def _tables_in_sections(self, ast: DocumentAST, section_keywords: list[str]) -> list[DocumentTable]:
        matched = [
            table
            for table in ast.tables
            if self._section_path_matches(table.section_path, section_keywords)
        ]
        return matched or list(ast.tables)

    def _section_path_matches(self, section_path: list[str], section_keywords: list[str]) -> bool:
        section_text = " / ".join(section_path)
        return bool(section_text) and any(keyword in section_text for keyword in section_keywords)

    def _drop_none(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if value is not None}

    def _table_matches(self, table: DocumentTable, section_text: str, spec: dict[str, Any]) -> bool:
        """按表头特征匹配明细表，仅对弱特征使用章节信息辅助判断。"""
        if not table.rows:
            return False
        header = [cell.text for cell in self._expanded_row(table.rows[0])]
        header_text = " | ".join(header)
        if not all(keyword in header_text for keyword in spec["required_headers"]):
            return False
        column_matches = sum(
            1 for aliases in spec["columns"].values() if self._find_header_index(header, aliases) is not None
        )
        min_column_matches = spec.get("min_column_matches", min(2, len(spec["columns"])))
        value_column_matches = sum(
            1
            for key, aliases in spec["columns"].items()
            if key != "item" and self._find_header_index(header, aliases) is not None
        )
        if column_matches < min_column_matches or value_column_matches < max(1, min_column_matches - 1):
            return False
        section_keywords = spec.get("section_keywords") or []
        if not section_keywords:
            return True
        return column_matches >= max(2, min_column_matches) or any(keyword in section_text for keyword in section_keywords)

    def _rows_for_table(self, table: DocumentTable, columns: dict[str, list[str]]) -> list[dict[str, Any]]:
        """按表头映射输出表格数据行。"""
        if len(table.rows) < 2:
            return []
        header = [cell.text for cell in self._expanded_row(table.rows[0])]
        column_indexes = {key: self._find_header_index(header, aliases) for key, aliases in columns.items()}
        rows: list[dict[str, Any]] = []
        for source_row_index, row in enumerate(table.rows[1:], start=1):
            expanded = self._expanded_row(row)
            item: dict[str, Any] = {}
            for key, index in column_indexes.items():
                if index is None or index >= len(expanded):
                    continue
                text = expanded[index].text.strip()
                if not text or text in {"——", "--", "-"}:
                    continue
                item[key] = self._normalize_scalar(text)
                item.setdefault("_cellSources", {})[key] = self._table_cell_source(
                    table,
                    source_row_index,
                    index,
                    f"按原文表头映射列 {header[index]} 抽取。",
                    resolver="table_header_mapping",
                )
            public_keys = [key for key in item if not str(key).startswith("_")]
            if public_keys and (len(public_keys) > 1 or "item" not in item):
                rows.append(item)
        return rows

    def _expanded_row(self, row):
        """展开跨列单元格，使表头索引与数据单元格索引一致。"""
        expanded = []
        for cell in row:
            span = max(1, int(getattr(cell, "col_span", 1) or 1))
            expanded.extend([cell] * span)
        return expanded

    def _find_header_index(self, header: list[str], aliases: list[str]) -> int | None:
        """按别名查找表头列。"""
        for index, text in enumerate(header):
            if any(alias in text for alias in aliases):
                return index
        return None

    def _normalize_scalar(self, text: str) -> Any:
        """把纯数值文本转成数字，保留复杂字符串。"""
        cleaned = text.replace(",", "").strip()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
            number = float(cleaned)
            return int(number) if number.is_integer() else number
        return text

    def _table_text(self, table: DocumentTable) -> str:
        """生成表格全文。"""
        return "\n".join(" | ".join(cell.text for cell in row) for row in table.rows)

    def _caption_before_table(self, ast: DocumentAST, table: DocumentTable) -> str:
        previous = [block for block in ast.blocks if block.order < table.order and block.type == "paragraph"]
        for block in reversed(previous[-5:]):
            if any(candidate.order > block.order and candidate.order < table.order for candidate in ast.tables):
                continue
            text = self._clean_text(block.text)
            if text.startswith(("表", "附表")) or "成果表" in text:
                return text
            collector_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:电气部分材料清册|杆塔部分材料清册|基础部分材料清册|光缆部分材料清册|电缆部分材料清册|铁塔接地装置材料|集电线路部分主要设备及材料清册))",
                text,
            )
            if collector_heading:
                return self._clean_text(collector_heading.group(1))
            if any(keyword in text for keyword in ("电气部分材料清册", "杆塔部分材料清册", "基础部分材料清册", "光缆部分材料清册", "电缆部分材料清册", "铁塔接地装置材料", "集电线路部分主要设备及材料清册")):
                return text
            substation_civil_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:土建主要工程量表|升压站主要土建工程量表|升压站土建清单))",
                text,
            )
            if substation_civil_heading:
                return self._clean_text(substation_civil_heading.group(1))
            foundation_or_road_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\s*\d+)?\.?\s*(?:基础尺寸及参数表|基础断面表|箱变基础工程量表|箱变基础单台工程量表(?:（配事故油池）)?|风电场主要工程量清单|进站道路主要工程数量表))",
                text,
            )
            if foundation_or_road_heading:
                return self._clean_text(foundation_or_road_heading.group(1))
            land_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:工程永久征地面积汇总表|工程临时征地面积汇总表|工程征用地计算合计表|工程总征地|工程面积汇总|工程征用地))",
                text,
            )
            if land_heading:
                return self._clean_text(land_heading.group(1))
            earthwork_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:场内土石方平衡|土石方平衡表(?:（万m\(3\)）)?))",
                text,
            )
            if earthwork_heading:
                return self._clean_text(earthwork_heading.group(1))
            electrical_primary_heading = re.search(
                r"(6\.(?:2|3)\.\d+\.?\s*(?:主要\s*电气\s*一次\s*设备|升压站\s*电气\s*一次\s*主要设备材料工程量表))",
                text,
            )
            if electrical_primary_heading:
                return self._clean_text(electrical_primary_heading.group(1))
            electrical_secondary_heading = re.search(
                r"((?:表\s*)?(?:6\.4\.4-3|6\.3\.16-1|6\.5\.3|6\.5-1)\s*\.?\s*(?:升压站\s*)?(?:电气\s*二次\s*(?:主要设备表|设备材料清册表?)|主要\s*通信\s*设备表))",
                text,
            )
            if electrical_secondary_heading:
                return self._clean_text(electrical_secondary_heading.group(1))
            if re.match(r"6\.3-1", text) and re.search(r"110\s*kV\s*升压站本期规模", text, flags=re.IGNORECASE):
                return text
            if re.match(r"15\.2\.[1-5]", text) and "概算表" in text:
                return text
            if re.match(r"15\.3\.9\.\d+", text) and ("概算表" in text or "主要技术经济指标表" in text):
                return text
        return ""
