"""集电线路电压、回路、敷设方式和线路长度抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex, domain_strings

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST


class CollectorLineRulesMixin:
    """集电线路电压、回路、敷设方式和线路长度抽取，通过 ElectricalRulesMixin 组合到结果构建器。"""

    def _collector_line_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if "线路名称" not in text or not any(keyword in text for keyword in ("路径长度", "线路路径长度", "单回", "双回")):
                continue
            headers = matrix[:2]
            data_rows = [row for row in matrix[2:] if row and re.search(domain_regex(self, "electrical_collector", "search_001", r"[A-Z]{1,2}[0-9]?\s*线"), row[0])]
            if not data_rows:
                continue
            length_indexes = self._length_indexes_from_headers(headers)
            double_indexes = [idx for idx in length_indexes if any("双回" in header[idx] for header in headers if idx < len(header))]
            single_indexes = [idx for idx in length_indexes if any("单回" in header[idx] for header in headers if idx < len(header))]
            total = self._sum_numeric_cells(data_rows, length_indexes)
            double_total = self._sum_numeric_cells(data_rows, double_indexes)
            single_total = self._sum_numeric_cells(data_rows, single_indexes)
            cable_indexes = [idx for idx in length_indexes if any("电缆" in header[idx] for header in headers if idx < len(header))]
            cable_total = self._sum_numeric_cells(data_rows, cable_indexes)
            row = {
                "layingMethod": "直埋+架空线路" if cable_total and (single_total or double_total) else self._collector_laying_method(ast),
                "circuitCount": None,
                "ratedVoltage": self._collector_voltage_from_document(ast),
                "circuit": self._collector_circuit_label(single_total, double_total),
                "totalLength": self._km_text(total),
                "doubleCircuitOverheadLength": self._km_text(double_total),
                "singleCircuitOverheadLength": self._km_text(single_total),
                "towerFoundationCount": None,
                "cableLength": self._km_text(cable_total),
            }
            summary = self._collector_line_row_from_summary(ast)
            if summary:
                for key, value in summary.items():
                    if row.get(key) is None and value is not None:
                        row[key] = value
            return self._schema_row_table("collectorLineTechnical", row)
        row = self._collector_line_row_from_summary(ast)
        if row is not None:
            return self._schema_row_table("collectorLineTechnical", row)
        return None

    def _collector_line_row_from_summary(self, ast: DocumentAST) -> dict[str, Any] | None:
        joined = "\n".join(
            self._clean_text(block.text)
            for block in ast.blocks
            if block.text and ("集电线路" in block.text or "架空线路长度" in block.text or "电缆线路长度" in block.text)
        )
        joined += "\n" + "\n".join(self._table_text(table) for table in ast.tables if "架空线路长度" in self._table_text(table) or "电缆线路长度" in self._table_text(table))
        if "集电线路" not in joined and "架空线路长度" not in joined:
            return None
        total = self._first_length_match(joined, domain_strings(self, "electrical_collector", "list_001", [r"(?:线路总计长度|新建线路路径长|线路路径长|架空线路长度)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*km"]))
        single = self._first_circuit_length(joined, "单回")
        double = self._first_circuit_length(joined, "双回")
        cable = self._first_length_match(joined, domain_strings(self, "electrical_collector", "list_002", [r"电缆线路长度约?\s*([0-9]+(?:\.[0-9]+)?)\s*km", r"([0-9]+(?:\.[0-9]+)?)\s*km[^。；;\n]{0,20}电缆线路"]))
        single_value = self._length_numeric_value(single)
        double_value = self._length_numeric_value(double)
        if total is None and (single_value is not None or double_value is not None):
            total = self._clean_number(float(single_value or 0) + float(double_value or 0))
        if total is None and cable is None:
            return None
        row = {
            "layingMethod": "直埋+架空线路" if cable is not None and total is not None else self._collector_laying_method(ast),
            "circuitCount": self._first_number_after_pattern(joined, r"(?:设|共计)\s*([0-9]+)\s*回(?:\s*35\s*kV\s*集电线路)?"),
            "ratedVoltage": self._collector_voltage_from_document(ast),
            "circuit": self._collector_circuit_label(float(single_value or 0), float(double_value or 0)),
            "totalLength": self._km_text(total),
            "doubleCircuitOverheadLength": self._length_text(double),
            "singleCircuitOverheadLength": self._length_text(single),
            "towerFoundationCount": self._direct_tower_count_from_document(ast),
            "cableLength": self._km_text(cable),
        }
        return row

    def _first_circuit_length(self, text: str, circuit_label: str) -> Any:
        patterns = [
            rf"{circuit_label}(?:路)?(?:架空)?线路(?:路径)?长(?:度)?约?\s*([0-9]+\s*[×xX]\s*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*km",
            rf"{circuit_label}[^。；;\n]{{0,12}}?([0-9]+\s*[×xX]\s*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*km",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = re.sub(domain_regex(self, "electrical_collector", "sub_002", r"\s+"), "", match.group(1)).replace("x", "×").replace("X", "×")
                return value if "×" in value else self._clean_number(float(value))
        return None

    def _first_circuit_overhead_length(self, text: str, circuit_label: str) -> Any:
        patterns = [
            rf"{circuit_label}(?:路)?架空(?:集电)?线路(?:路径)?长(?:度)?约?\s*([0-9]+\s*[×xX]\s*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*km",
            rf"{circuit_label}[^。；;\n]{{0,16}}?架空[^。；;\n]{{0,16}}?([0-9]+\s*[×xX]\s*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*km",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = re.sub(domain_regex(self, "electrical_collector", "sub_003", r"\s+"), "", match.group(1)).replace("x", "×").replace("X", "×")
                return value if "×" in value else self._clean_number(float(value))
        return None

    def _collector_voltage_from_document(self, ast: DocumentAST) -> Any:
        candidates: list[float] = []
        for table in ast.tables:
            text = self._table_text(table)
            if "集电线路" in text or "线路额定电压" in text:
                for match in re.finditer(domain_regex(self, "electrical_collector", "finditer_004", r"([0-9]+(?:\.\d+)?)\s*kV"), text, flags=re.IGNORECASE):
                    value = float(match.group(1))
                    if 10 <= value <= 35:
                        candidates.append(value)
        if not candidates:
            return None
        selected = max(candidates)
        return f"{self._clean_number(selected)}kV"

    def _collector_circuit_label(self, single_total: float, double_total: float) -> str | None:
        labels = []
        if single_total:
            labels.append("单回")
        if double_total:
            labels.append("双回")
        return "/".join(labels) if labels else None

    def _collector_laying_method(self, ast: DocumentAST | None) -> str | None:
        if ast is None:
            return None
        texts: list[str] = []
        for block in ast.blocks:
            section_text = " / ".join(block.section_path)
            if "集电线路" in section_text or "集电线路" in block.text:
                texts.append(block.text)
        for table in ast.tables:
            section_text = " / ".join(table.section_path)
            table_text = self._table_text(table)
            if "集电线路" in section_text or "线路额定电压" in table_text or "集电线路" in table_text:
                texts.append(table_text)
        joined = "\n".join(texts)
        if not joined:
            return None
        return "直埋+架空线路" if "架空线路" in joined or "架空" in joined else "直埋"

    def _collector_circuit_count(self, value: Any) -> Any:
        if value is None:
            return None
        text = str(value)
        match = re.search(domain_regex(self, "electrical_collector", "search_005", r"([0-9]+)\s*回"), text)
        if match:
            return int(match.group(1))
        if "单/双" in text or "单双" in text:
            return None
        if "双回" in text:
            return 2
        if "单回" in text:
            return 1
        return None

    def _build_collector_line_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        row = self._collector_line_combined_row(ast)
        return {"collectorLineCombined": [row] if row else []}

    def _collector_line_combined_row(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = self._collector_line_row_from_tables(ast)
        source_blocks = [
            block
            for block in ast.blocks
            if block.text and ("集电线路" in block.text or "架空线路" in block.text or "线路路径" in block.text)
        ]
        joined = "\n".join(self._clean_text(block.text or "") for block in source_blocks)
        joined += "\n" + "\n".join(self._table_text(table) for table in ast.tables if any(keyword in self._table_text(table) for keyword in ("集电线路电压", "新建线路", "全线集电线路", "双回架空", "单回架空", "电缆路径")))
        if not joined.strip():
            return row if any(value is not None for key, value in row.items() if not str(key).startswith("_")) else None
        self._set_collector_text_value(row, "collectorVoltage", ast, joined, source_blocks, self._first_number_after_pattern(joined, r"([0-9]+(?:\.\d+)?)\s*kV\s*集电线路"))
        self._set_collector_text_value(row, "circuitCount", ast, joined, source_blocks, self._first_number_after_pattern(joined, r"(?:设|建设|共建设?|回路数\D{0,8})([0-9]+)\s*回"))
        self._set_collector_text_value(row, "newRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_003", [r"(?:新建线路路径长度|新建线路径长度|新建线路路径长)\D{0,12}([0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "newOverheadLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_004", [r"新建架空线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "newSingleCircuitLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_005", [r"新建单回路线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "newDoubleCircuitLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_006", [r"新建双回路线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "newCableLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_007", [r"新建电缆线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        if row.get("newCableLineLength") is None:
            cable_total = self._collector_cable_total_from_equipment(ast)
            if cable_total is not None:
                row["newCableLineLength"] = cable_total
                row.setdefault("_cellSources", {})["newCableLineLength"] = self._collector_text_source(
                    ast, joined, source_blocks, "35kV集电电缆规格数量相加，作为电缆线路总长度。"
                )
        self._set_collector_text_value(row, "totalCollectorRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_008", [r"全线集电线路路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        if row.get("totalCollectorRouteLength") is None:
            scoped_total = self._collector_total_route_from_section(ast)
            if scoped_total is not None:
                length, block = scoped_total
                row["totalCollectorRouteLength"] = length
                row.setdefault("_cellSources", {})["totalCollectorRouteLength"] = self._text_block_source(
                    block, self._clean_text(block.text or ""),
                    "按集电线路章节中的全线总路径长度提取。", resolver="collector_section_total_route",
                )
        self._set_collector_text_value(row, "doubleCircuitOverheadRouteLength", ast, joined, source_blocks, self._first_circuit_overhead_length(joined, "双回"))
        self._set_collector_text_value(row, "singleCircuitOverheadRouteLength", ast, joined, source_blocks, self._first_circuit_overhead_length(joined, "单回"))
        self._set_collector_text_value(row, "boxToTerminalTowerCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_009", [r"箱变至终端塔电缆路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "singleCircuitCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_010", [r"单回(?:路)?电缆线路路径长(?:度)?约?\s*([0-9]+\s*[×xX]\s*[0-9]+(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*km"])))
        self._set_collector_text_value(row, "doubleCircuitCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, domain_strings(self, "electrical_collector", "list_011", [r"双回(?:路|进站)?电缆路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"])))
        preferred_circuit_count = self._preferred_collector_circuit_count(joined)
        if preferred_circuit_count is not None:
            row["circuitCount"] = preferred_circuit_count
            row.setdefault("_cellSources", {})["circuitCount"] = self._collector_text_source(ast, joined, source_blocks, "集电线路正文回路数优选。")
        preferred_single_overhead = self._preferred_single_circuit_overhead_route_length(joined)
        if preferred_single_overhead is not None:
            row["singleCircuitOverheadRouteLength"] = preferred_single_overhead
            row.setdefault("_cellSources", {})["singleCircuitOverheadRouteLength"] = self._collector_text_source(ast, joined, source_blocks, "集电线路正文单回架空路径长度优选。")
        self._fill_new_overhead_route_lengths(row, ast, joined, source_blocks)
        if not any(value is not None for key, value in row.items() if not str(key).startswith("_")):
            return None
        return row

    def _collector_cable_total_from_equipment(self, ast: DocumentAST) -> Any:
        """汇总设备清单中35kV集电电缆各规格的长度，排除低压和站内电缆。"""
        totals: list[float] = []
        for table in ast.tables:
            matrix = self._table_matrix(table)
            values: list[float] = []
            for row in matrix:
                label = " ".join(row[:2])
                specification = " ".join(row)
                if "电力电缆" not in label or not re.search(domain_regex(self, "electrical_collector", "search_006", r"26\s*/\s*35"), specification):
                    continue
                for index, cell in enumerate(row):
                    if self._clean_text(cell).lower() != "km" or index + 1 >= len(row):
                        continue
                    value = self._normalize_table_cell(row[index + 1])
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        values.append(float(value))
                    break
            if len(values) >= 2:
                totals.append(sum(values))
        unique = {round(value, 3) for value in totals}
        return self._clean_number(totals[0]) if len(unique) == 1 else None

    def _collector_total_route_from_section(self, ast: DocumentAST) -> tuple[Any, Any] | None:
        patterns = (
            r"全线(?:集电)?线路(?:路径)?总计?长度\s*[:：]?\s*(?:新建)?(?:集电)?线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*(?:km|公里|千米)",
            r"全线(?:集电)?线路(?:路径)?总计?长度\s*[:：]?\s*([0-9]+(?:\.\d+)?)\s*(?:km|公里|千米)",
        )
        matches = []
        for block in self._body_blocks(ast):
            if "集电线路" not in " ".join(block.section_path or []):
                continue
            text = self._clean_text(block.text or "")
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    matches.append((self._clean_number(float(match.group(1))), block))
                    break
        return matches[0] if len({value for value, _ in matches}) == 1 else None

    def _fill_new_overhead_route_lengths(
        self, row: dict[str, Any], ast: DocumentAST, text: str, blocks: list[DocumentBlock]
    ) -> None:
        """使用明确标注的单回路和双回路架空线路长度作为兜底值。"""
        component_fields = (
            ("newSingleCircuitLineLength", "singleCircuitOverheadRouteLength", "单回"),
            ("newDoubleCircuitLineLength", "doubleCircuitOverheadRouteLength", "双回"),
        )
        components: list[Any] = []
        for target, source_key, circuit in component_fields:
            route = self._overhead_route_km(row.get(source_key))
            if route is None:
                continue
            components.append(route)
            if row.get(target) is None:
                full_route = self._full_circuit_route_km(text, circuit)
                row[target] = full_route if full_route is not None else route
                source = (row.get("_cellSources") or {}).get(source_key)
                row.setdefault("_cellSources", {})[target] = self._collector_route_source(
                    ast, text, blocks, circuit, full_route if full_route is not None else route,
                    overhead=full_route is None,
                ) or source
        if row.get("newOverheadLineLength") is None and len(components) == len(component_fields):
            row["newOverheadLineLength"] = self._clean_number(sum(float(value) for value in components))
            source = self._collector_overhead_total_source(ast, text, blocks)
            if source:
                row.setdefault("_cellSources", {})["newOverheadLineLength"] = source

    def _collector_route_source(
        self, ast: DocumentAST, text: str, blocks: list[DocumentBlock], circuit: str,
        route: Any, *, overhead: bool,
    ) -> dict[str, Any] | None:
        prefix = rf"{circuit}(?:路)?架空(?:集电)?线路" if overhead else rf"{circuit}(?:路)?(?:集电)?线路"
        pattern = rf"{prefix}[^。；;]{{0,35}}?{re.escape(str(route))}\s*km"
        match = re.search(pattern, text, re.I)
        if not match:
            return None
        block = next((item for item in blocks if circuit in (item.text or "") and (not overhead or "架空" in item.text)), None)
        if block is None:
            return self._collector_text_source(ast, match.group(0), [], "按回路类型的线路路径长度补充新建长度。")
        return self._text_block_source(block, match.group(0), "按回路类型的线路路径长度补充新建长度。", resolver="collector_line_route_fallback")

    def _collector_overhead_total_source(
        self, ast: DocumentAST, text: str, blocks: list[DocumentBlock]
    ) -> dict[str, Any] | None:
        snippets = []
        for circuit in ("单回", "双回"):
            match = re.search(rf"{circuit}(?:路)?架空(?:集电)?线路[^。；;]{{0,45}}?km", text, re.I)
            if match:
                snippets.append(match.group(0))
        if len(snippets) != 2:
            block = next((item for item in blocks if "架空" in (item.text or "") and ("单回" in item.text or "双回" in item.text)), None)
            if block:
                return self._text_block_source(block, self._clean_text(block.text or ""), "单回与双回架空路径长度相加，不乘回路数。", resolver="collector_line_overhead_sum")
            return self._collector_text_source(ast, text, [], "单回与双回架空路径长度相加，不乘回路数。")
        block = next((item for item in blocks if "单回架空" in (item.text or "") or "双回架空" in (item.text or "")), None)
        evidence = "；".join(snippets)
        if block is None:
            return self._collector_text_source(ast, evidence, [], "单回与双回架空路径长度相加，不乘回路数。")
        return self._text_block_source(block, evidence, "单回与双回架空路径长度相加，不乘回路数。", resolver="collector_line_overhead_sum")

    def _overhead_route_km(self, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).replace(" ", "").replace("x", "×").replace("X", "×")
        match = re.fullmatch(domain_regex(self, "electrical_collector", "fullmatch_007", r"(?:[0-9]+(?:\.[0-9]+)?×)?([0-9]+(?:\.[0-9]+)?)(?:km)?"), text, re.I)
        return self._clean_number(float(match.group(1))) if match else None

    def _full_circuit_route_km(self, text: str, circuit: str) -> Any:
        pattern = rf"{circuit}(?:路)?(?:集电)?线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.[0-9]+)?)\s*km"
        match = re.search(pattern, text, re.I)
        return self._clean_number(float(match.group(1))) if match else None

    def _set_collector_text_value(self, row: dict[str, Any], key: str, ast: DocumentAST, text: str, blocks: list[DocumentBlock], value: Any) -> None:
        if row.get(key) is not None or value is None:
            return
        row[key] = value
        row.setdefault("_cellSources", {})[key] = self._collector_text_source(ast, text, blocks, "集电线路正文规则抽取。")

    def _collector_text_source(self, ast: DocumentAST, text: str, blocks: list[DocumentBlock], description: str) -> dict[str, Any]:
        block = blocks[0] if blocks else self._block_containing_text(ast, text)
        if block is not None:
            return self._text_block_source(block, text, description, resolver="collector_line_text")
        return {
            "source": {
                "kind": "document_text",
                "sourceType": "paragraph",
                "sourceText": self._clean_text(text),
                "matchMethod": "collector_line_text",
                "description": description,
            },
            "process": {"resolver": "collector_line_text", "calculation": description},
            "sourceDescription": description,
        }

    def _preferred_collector_circuit_count(self, text: str) -> Any:
        return self._first_number_after_pattern(text, r"(?:\u96c6\u7535\u7ebf\u8def)?[^\n\u3002\uff1b;]{0,40}?\u672c\u671f\u5171\u5efa\u8bbe\s*([0-9]+)\s*\u56de")

    def _preferred_single_circuit_overhead_route_length(self, text: str) -> Any:
        patterns = [
            r"\u5355\u56de\u96c6\u7535\u7ebf\u8def\u8def\u5f84\u957f\u7ea6\s*[0-9]+(?:\.[0-9]+)?\s*km[^\n\u3002\uff1b;]{0,40}?\u67b6\u7a7a\u8def\u5f84\u957f\s*([0-9]+(?:\.[0-9]+)?)\s*km",
            r"\u5408\u8ba1\s*\|\s*\|\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*[0-9]+(?:\.[0-9]+)?\s*\|\s*[0-9]+(?:\.[0-9]+)?\s*\|",
        ]
        return self._first_length_text_match(text, patterns)

    def _collector_line_row_from_tables(self, ast: DocumentAST) -> dict[str, Any]:
        row: dict[str, Any] = {
            "collectorVoltage": None,
            "circuitCount": None,
            "newRouteLength": None,
            "newOverheadLineLength": None,
            "newSingleCircuitLineLength": None,
            "newDoubleCircuitLineLength": None,
            "newCableLineLength": None,
            "totalCollectorRouteLength": None,
            "doubleCircuitOverheadRouteLength": None,
            "singleCircuitOverheadRouteLength": None,
            "boxToTerminalTowerCableRouteLength": None,
            "singleCircuitCableRouteLength": None,
            "doubleCircuitCableRouteLength": None,
        }
        aliases = {
            "collectorVoltage": ["集电线路电压", "电压"],
            "circuitCount": ["回路数"],
            "newRouteLength": ["新建线路路径长度", "新建线路径长度", "新建线路路径长"],
            "newOverheadLineLength": ["新建架空线路长度", "新建架空线路路径长度"],
            "newSingleCircuitLineLength": ["新建单回路线路长度", "新建单回路线路路径长度"],
            "newDoubleCircuitLineLength": ["新建双回路线路长度", "新建双回路线路路径长度"],
            "newCableLineLength": ["新建电缆线路长度", "新建电缆线路路径长度"],
            "totalCollectorRouteLength": ["全线集电线路路径长度", "全线集电线路路径长"],
            "doubleCircuitOverheadRouteLength": ["双回架空线路路径长度", "双回架空集电线路路径长度"],
            "singleCircuitOverheadRouteLength": ["单回架空线路路径长度", "单回架空集电线路路径长度"],
            "boxToTerminalTowerCableRouteLength": ["箱变至终端塔电缆路径长度", "箱变至终端塔电缆路径长"],
            "singleCircuitCableRouteLength": ["单回电缆线路路径长度", "单回电缆线路路径长"],
            "doubleCircuitCableRouteLength": ["双回路电缆路径长度", "双回路电缆路径长"],
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            header = matrix[0]
            header_text = " | ".join(header)
            if not any(keyword in header_text for keyword in ("集电线路电压", "回路数", "新建线路", "全线集电线路", "架空", "电缆路径")):
                continue
            value_row_index = next((index for index in range(1, len(matrix)) if any(cell.strip() for cell in matrix[index])), None)
            if value_row_index is None:
                continue
            value_row = matrix[value_row_index]
            for key, key_aliases in aliases.items():
                if row.get(key) is not None:
                    continue
                column_index = self._find_header_index(header, key_aliases)
                if column_index is None or column_index >= len(value_row):
                    continue
                value = self._normalize_table_cell(value_row[column_index])
                if value is None:
                    continue
                row[key] = value
                row.setdefault("_cellSources", {})[key] = self._table_cell_source(
                    table,
                    value_row_index,
                    column_index,
                    f"按集电线路组合表表头 {header[column_index]} 抽取。",
                    resolver="collector_line_header_mapping",
                )
        return row

    def _collector_line_text_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        context = self._collector_line_text_context(ast)
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        specs = {
            "collectorCableCoreMaterial": ("电缆电芯材质", self._collector_cable_core_material(context), None, ["本工程", "采用", "电力电缆"]),
            "collectorLayingMethod": ("敷设方式", self._collector_laying_method_from_text(context), None, ["集电线路", "架空", "电缆"]),
        }
        for code, (name, value, unit, evidence_keywords) in specs.items():
            if code in skip_codes or value in (None, "", [], {}):
                continue
            overrides[code] = (
                name,
                value,
                unit,
                self._field_evidence_text_for_value(ast, value, evidence_keywords),
                "paragraph",
                {"resolver": "deterministic_collector_line_text", "sectionPath": ["集电线路"]},
            )
        if "newSingleCircuitLineLength" not in skip_codes:
            pattern = re.compile(
                domain_regex(self, "electrical_collector", "compile_008", r"(?:新建|建设)[^。；;\n]{0,80}?单回\s*[0-9]{2,3}\s*kV\s*线路"
                r"[^。；;\n]{0,100}?线路长度\s*(?:约|为)?\s*([0-9]+(?:\.[0-9]+)?)\s*km"),
                re.I,
            )
            for block in ast.blocks:
                match = pattern.search(self._clean_text(block.text or ""))
                if match is None:
                    continue
                overrides["newSingleCircuitLineLength"] = (
                    "新建单回路线路长度", self._clean_number(float(match.group(1))), "km",
                    match.group(0), "paragraph",
                    {"resolver": "single_circuit_outgoing_line_text", "page": block.page, "sectionPath": list(block.section_path)},
                )
                break
        return overrides

    def _collector_line_text_context(self, ast: DocumentAST) -> str:
        parts: list[str] = []
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            section_text = " ".join(str(part) for part in (block.section_path or []))
            if "集电线路" in section_text or any(keyword in text for keyword in ("集电线路", "架空线路", "电力电缆", "电缆敷设")):
                parts.append(text)
        return "\n".join(parts)

    def _collector_cable_core_material(self, text: str) -> str | None:
        for sentence in self._sentences(text):
            if "本工程" in sentence and "采用" in sentence and "电力电缆" in sentence:
                return self._clean_text(sentence).rstrip("。；;")
        match = re.search(domain_regex(self, "electrical_collector", "search_009", r"(本工程[^。；;\n]{0,40}?采用[^。；;\n]{1,160}?电力电缆)"), text)
        if match:
            return self._clean_text(match.group(1))
        return None

    def _collector_laying_method_from_text(self, text: str) -> str | None:
        if not text:
            return None
        return "架空+电缆直埋" if "架空" in text else "电缆直埋"

    def _collector_line_names(self, ast: DocumentAST) -> str | None:
        names: list[str] = []
        seen: set[str] = set()
        for table in ast.tables:
            text = self._table_text(table)
            if "线路名称" not in text and "A线" not in text:
                continue
            for row in self._table_matrix(table):
                for cell in row:
                    for match in re.finditer(domain_regex(self, "electrical_collector", "finditer_010", r"(?<![A-Z0-9])([A-Z][0-9]?)\s*线"), cell):
                        name = f"{match.group(1)}线"
                        if name not in seen:
                            seen.add(name)
                            names.append(name)
            if names:
                break
        if not names:
            text = "\n".join(self._clean_text(block.text) for block in ast.blocks if "线" in block.text and ("集电线路" in block.text or "架空线路" in block.text))
            single_segments = re.findall(domain_regex(self, "electrical_collector", "findall_011", r"单回(?:路)?线路长度[^。；;\n]{0,220}"), text)
            search_text = "\n".join(single_segments) or text
            for match in re.finditer(domain_regex(self, "electrical_collector", "finditer_012", r"(?<![A-Z0-9])([A-Z][0-9]?)\s*线\s*[0-9]+(?:\.[0-9]+)?\s*km"), search_text):
                name = f"{match.group(1)}线"
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        if len(names) >= 2:
            return "、".join(names)
        return None
