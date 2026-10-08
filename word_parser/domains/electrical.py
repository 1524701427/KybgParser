"""Primary and secondary electrical and collector line extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import ParsedField


class ElectricalRulesMixin:
    def _collector_line_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if "线路名称" not in text or not any(keyword in text for keyword in ("路径长度", "线路路径长度", "单回", "双回")):
                continue
            headers = matrix[:2]
            data_rows = [row for row in matrix[2:] if row and re.search(r"[A-Z]{1,2}[0-9]?\s*线", row[0])]
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
        total = self._first_length_match(joined, [r"(?:线路总计长度|新建线路路径长|线路路径长|架空线路长度)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*km"])
        single = self._first_circuit_length(joined, "单回")
        double = self._first_circuit_length(joined, "双回")
        cable = self._first_length_match(joined, [r"电缆线路长度约?\s*([0-9]+(?:\.[0-9]+)?)\s*km", r"([0-9]+(?:\.[0-9]+)?)\s*km[^。；;\n]{0,20}电缆线路"])
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
                value = re.sub(r"\s+", "", match.group(1)).replace("x", "×").replace("X", "×")
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
                value = re.sub(r"\s+", "", match.group(1)).replace("x", "×").replace("X", "×")
                return value if "×" in value else self._clean_number(float(value))
        return None

    def _collector_voltage_from_document(self, ast: DocumentAST) -> Any:
        candidates: list[float] = []
        for table in ast.tables:
            text = self._table_text(table)
            if "集电线路" in text or "线路额定电压" in text:
                for match in re.finditer(r"([0-9]+(?:\.\d+)?)\s*kV", text, flags=re.IGNORECASE):
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
        match = re.search(r"([0-9]+)\s*回", text)
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
        self._set_collector_text_value(row, "newRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"(?:新建线路路径长度|新建线路径长度|新建线路路径长)\D{0,12}([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "newOverheadLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"新建架空线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "newSingleCircuitLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"新建单回路线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "newDoubleCircuitLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"新建双回路线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "newCableLineLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"新建电缆线路(?:路径)?长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "totalCollectorRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"全线集电线路路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "doubleCircuitOverheadRouteLength", ast, joined, source_blocks, self._first_circuit_overhead_length(joined, "双回"))
        self._set_collector_text_value(row, "singleCircuitOverheadRouteLength", ast, joined, source_blocks, self._first_circuit_overhead_length(joined, "单回"))
        self._set_collector_text_value(row, "boxToTerminalTowerCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"箱变至终端塔电缆路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "singleCircuitCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"单回(?:路)?电缆线路路径长(?:度)?约?\s*([0-9]+\s*[×xX]\s*[0-9]+(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*km"]))
        self._set_collector_text_value(row, "doubleCircuitCableRouteLength", ast, joined, source_blocks, self._first_length_text_match(joined, [r"双回(?:路|进站)?电缆路径长(?:度)?约?\s*([0-9]+(?:\.\d+)?)\s*km"]))
        preferred_circuit_count = self._preferred_collector_circuit_count(joined)
        if preferred_circuit_count is not None:
            row["circuitCount"] = preferred_circuit_count
            row.setdefault("_cellSources", {})["circuitCount"] = self._collector_text_source(ast, joined, source_blocks, "集电线路正文回路数优选。")
        preferred_single_overhead = self._preferred_single_circuit_overhead_route_length(joined)
        if preferred_single_overhead is not None:
            row["singleCircuitOverheadRouteLength"] = preferred_single_overhead
            row.setdefault("_cellSources", {})["singleCircuitOverheadRouteLength"] = self._collector_text_source(ast, joined, source_blocks, "集电线路正文单回架空路径长度优选。")
        if not any(value is not None for key, value in row.items() if not str(key).startswith("_")):
            return None
        return row

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

    def _build_electrical_secondary_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "electricalSecondaryMainEquipment": [],
            "electricalSecondaryCommunicationEquipment": [],
        }
        for table in ast.tables:
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            target_text = f"{caption}\n{section_caption}\n{self._table_text(table)[:300]}"
            key = self._electrical_secondary_table_key(target_text)
            if key is None:
                continue
            rows = self._raw_rows_from_table(table)
            if rows:
                details[key] = rows
        return details

    def _electrical_secondary_table_key(self, text: str) -> str | None:
        for spec in self.electrical_secondary_table_key_specs:
            if self._table_key_spec_matches(spec, text):
                return str(spec.get("key"))
        return None

    def _build_electrical_primary_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "electricalPrimaryEquipmentMaterial": [],
            "electricalPrimaryAccessStationCombined": [],
            "electricalPrimaryMainConnectionCombined": [],
            "electricalPrimaryLightningRodCombined": [],
        }
        tables = self._electrical_primary_equipment_tables(ast)
        if not tables:
            fallback = self._electrical_primary_text_combined_details(ast)
            access = self._electrical_access_station_combined_row_from_tables(ast)
            if access:
                fallback["electricalPrimaryAccessStationCombined"] = [access]
            for key, rows in fallback.items():
                if rows:
                    details[key] = rows
            return details
        original_rows: list[dict[str, Any]] = []
        for table in tables:
            original_rows.extend(self._raw_rows_from_table(table))
        details["electricalPrimaryEquipmentMaterial"] = original_rows
        first = tables[0]
        matrix = self._merged_table_matrix(tables)
        access = self._electrical_access_station_combined_row(matrix, first)
        all_table_access = self._electrical_access_station_combined_row_from_tables(ast)
        if all_table_access:
            access = all_table_access
        if access:
            details["electricalPrimaryAccessStationCombined"] = [access]
        main = self._electrical_main_connection_combined_row(matrix, first)
        if main:
            details["electricalPrimaryMainConnectionCombined"] = [main]
        lightning = self._electrical_lightning_combined_row(matrix, first)
        if lightning:
            details["electricalPrimaryLightningRodCombined"] = [lightning]
        fallback = self._electrical_primary_text_combined_details(ast)
        for key, rows in fallback.items():
            if rows and self._detail_rows_more_complete(rows, details.get(key) or []):
                details[key] = rows
        return details

    def _electrical_primary_text_combined_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        electrical_blocks = self._electrical_primary_text_blocks(ast)
        block_text = "\n".join(self._clean_text(block.text or "") for block in electrical_blocks if block.text)
        electrical_tables = self._original_tables_for_spec(ast, {"key_prefix": "electricalPrimaryOriginalTable"})
        table_text = "\n".join(self._table_text(table) for table in electrical_tables)
        text = f"{block_text}\n{table_text}"
        details: dict[str, list[dict[str, Any]]] = {
            "electricalPrimaryAccessStationCombined": [],
            "electricalPrimaryMainConnectionCombined": [],
            "electricalPrimaryLightningRodCombined": [],
        }
        if not text:
            return details
        capacity = None
        cap_match = re.search(r"(?:\u603b\u5bb9\u91cf\u4e3a|\u89c4\u5212\u603b\u88c5\u673a\u5bb9\u91cf\u4e3a)\s*([0-9]+(?:\.[0-9]+)?)\s*MW", text, flags=re.IGNORECASE)
        source_match: re.Match[str] | None = None
        if cap_match:
            capacity = self._normalize_scalar(cap_match.group(1))
            source_match = cap_match
        else:
            capacity = self._electrical_primary_capacity_from_text(text)
        station = self._preferred_access_station_name(text)
        voltage_values = self._electrical_primary_accessible_voltage_values(text)
        row_source = self._combined_text_match_row_source(
            ast,
            electrical_blocks,
            text,
            source_match,
            "电气一次正文/表格组合字段来源。",
            "electrical_primary_text_combined",
        )
        if station or voltage_values or capacity is not None:
            details["electricalPrimaryAccessStationCombined"] = [{
                "accessStationName": station,
                "accessibleVoltage": self._normalize_table_cell("、".join(voltage_values)) if voltage_values else None,
                "accessibleCapacity": capacity,
                "_rowSource": row_source,
            }]
        connection_parts: list[str] = []
        for pattern in self._configured_patterns(
            self._deterministic_rule_section("electrical_primary"),
            "connection_patterns",
            [
                r"110\s*kV[^\n\u3002\uff1b;]{0,80}?\u7ebf\s*[-\uff0d\u2014]\s*\u53d8\u7ec4\u63a5\u7ebf(?:\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)?",
                r"110\s*kV[^\n\u3002\uff1b;]{0,60}?\u7ebf\u53d8\u7ec4\u63a5\u7ebf(?:\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)",
                r"110\s*kV[^\n\u3002\uff1b;]{0,80}?\u5355\u6bcd\u7ebf\u63a5\u7ebf(?:\u65b9\u6848|\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)?",
                r"35\s*kV[^\n\u3002\uff1b;]{0,80}?\u5355\u6bcd(?:\u7ebf)?\u5206\u6bb5\u63a5\u7ebf(?:\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)?",
                r"35\s*kV[^\n\u3002\uff1b;]{0,60}?\u5355\u6bcd\u7ebf\u63a5\u7ebf(?:\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)",
                r"35\s*kV[^\n\u3002\uff1b;]{0,80}?\u53cc\u6bb5\u6bcd\u7ebf\u63a5\u7ebf(?:\u65b9\u6848|\u65b9\u5f0f|\u5f62\u5f0f|\u578b\u5f0f)?",
            ],
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = self._normalize_text_value(match.group(0))
                if value not in connection_parts:
                    connection_parts.append(value)
        if capacity is not None or connection_parts:
            details["electricalPrimaryMainConnectionCombined"] = [{
                "plannedCapacity": capacity,
                "currentCapacity": capacity,
                "connectionType": "\n".join(connection_parts) if connection_parts else None,
                "_rowSource": row_source,
            }]
        lightning = self._lightning_rod_counts_from_text(text)
        if lightning:
            details["electricalPrimaryLightningRodCombined"] = [{
                "independentLightningRodCount": lightning[0],
                "frameLightningRodCount": lightning[1],
                "_rowSource": row_source,
            }]
        return details

    def _electrical_primary_accessible_voltage_values(self, text: str) -> list[str]:
        """抽取接入电压，排除接入站名称里的电压等级。"""
        values: list[str] = []
        patterns = [
            r"([0-9]{2,3})\s*kV\s*(?:线路|线)[^。；;\n]{0,40}?(?:接至|接入)",
            r"(?:接至|接入)[^。；;\n]{0,50}?([0-9]{2,3})\s*kV\s*(?:备用)?出线间隔",
            r"可接入电压[^0-9]{0,20}([0-9]{2,3})(?:\s*kV)?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = match.group(1)
                span_text = match.group(0)
                if re.search(rf"{re.escape(value)}\s*kV\s*[\u4e00-\u9fa5A-Za-z0-9]{{0,12}}变电站", span_text, flags=re.IGNORECASE):
                    continue
                if value not in values:
                    values.append(value)
        return values

    def _electrical_primary_capacity_from_text(self, text: str) -> Any:
        patterns = self._configured_patterns(
            self._deterministic_rule_section("electrical_primary"),
            "capacity_patterns",
            [
                r"新建\s*(?P<count>[0-9]+)\s*台\s*(?P<capacity>[0-9]+(?:\.[0-9]+)?)\s*MVA\s*主变",
                r"选用\s*(?P<count>[0-9]+)\s*台容量为\s*(?P<capacity>[0-9]+(?:\.[0-9]+)?)\s*MVA\s*的主变压器",
                r"主变压器\s*\|\s*(?P<count>[0-9]+)\s*[×xX]\s*(?P<capacity>[0-9]+(?:\.[0-9]+)?)\s*MVA",
            ],
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            try:
                count = match.group("count")
                capacity = match.group("capacity")
            except IndexError:
                count = match.group(1)
                capacity = match.group(2)
            return self._clean_number(float(count) * float(capacity))
        return None

    def _electrical_primary_text_blocks(self, ast: DocumentAST) -> list[DocumentBlock]:
        body_blocks = self._body_blocks(ast)
        matched = [block for block in body_blocks if self._section_path_matches(block.section_path, ["电气", "升压站", "主接线", "接入系统"])]
        if matched:
            return matched
        if any(block.section_path for block in body_blocks):
            return []
        keywords = ("电气", "升压站", "主接线", "接入", "110kV", "35kV", "主变", "避雷针", "防雷")
        return [block for block in body_blocks if block.text and any(keyword in block.text for keyword in keywords)]

    def _preferred_access_station_name(self, text: str) -> str | None:
        candidates: list[tuple[int, int, str]] = []
        rule_section = self._deterministic_rule_section("electrical_primary")
        configured_patterns = rule_section.get("access_station_patterns") if isinstance(rule_section.get("access_station_patterns"), list) else []
        patterns: list[tuple[int, str]] = []
        for item in configured_patterns:
            if isinstance(item, dict) and item.get("pattern"):
                patterns.append((int(item.get("score") or 0), str(item["pattern"])))
        if not patterns:
            patterns = [
                (20, r"\u63a5\u5165\u5230\s*(?P<value>[^\n\uff0c\u3002\uff1b;]{1,50}?\u5347\u538b\u7ad9)"),
                (15, r"\u63a5\u5165\u81f3\s*(?P<value>[^\n\uff0c\u3002\uff1b;]{1,50}?\u5347\u538b\u7ad9)"),
                (10, r"\u63a5\u5165\s*(?P<value>[^\n\uff0c\u3002\uff1b;]{1,60}?\u5347\u538b\u7ad9)"),
                (5, r"(?:\u63a5\u81f3|\u9001\u81f3|\u81f3)\s*(?P<value>(?:330\s*kV)?[^\n\uff0c\u3002;\uff1b]{0,30}?\u53d8\u7535\u7ad9)"),
            ]
        for base_score, pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = self._normalize_text_value(str(self._deterministic_match_value(match)))
                if not value or self._looks_like_invalid_access_station_name(value):
                    continue
                score = base_score
                if "\u5347\u538b\u7ad9" in value:
                    score += 5
                if "\u9879\u76ee" in value:
                    score -= 5
                candidates.append((score, -len(value), value))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][2]

    def _looks_like_invalid_access_station_name(self, value: str) -> bool:
        compact = re.sub(r"\s+", "", value)
        patterns = self._configured_patterns(
            self._deterministic_rule_section("electrical_primary"),
            "invalid_access_station_patterns",
            ["到升压站", "至升压站", "接入升压站", r"[到至接入]{1,4}升压站"],
        )
        for pattern in patterns:
            if compact == pattern or re.fullmatch(pattern, compact):
                return True
        return False

    def _lightning_rod_counts_from_text(self, text: str) -> tuple[Any, Any] | None:
        for segment in re.split(r"[\n\u3002\uff1b;]", text):
            if "\u72ec\u7acb\u907f\u96f7\u9488" not in segment or "\u6784\u67b6\u907f\u96f7\u9488" not in segment:
                continue
            independent = re.search(r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*(?:[0-9]+\s*m)?\s*\u72ec\u7acb\u907f\u96f7\u9488", segment)
            frame = re.search(r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*(?:[0-9]+\s*m)?\s*\u6784\u67b6\u907f\u96f7\u9488", segment)
            if independent is None:
                independent = re.search(r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*[0-9]+\s*m\s*\u72ec\u7acb\u907f\u96f7\u9488", segment)
            if frame is None:
                frame = re.search(r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*[0-9]+\s*m\s*\u6784\u67b6\u907f\u96f7\u9488", segment)
            if independent and frame:
                return self._normalize_scalar(independent.group(1)), self._normalize_scalar(frame.group(1))
        return None

    def _electrical_primary_equipment_tables(self, ast: DocumentAST) -> list[DocumentTable]:
        tables: list[DocumentTable] = []
        for table in sorted(ast.tables, key=lambda item: item.order):
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            text = self._table_text(table)
            target_text = f"{caption}\n{section_caption}\n{text[:300]}"
            if self._looks_like_electrical_primary_source_table(target_text):
                tables.append(table)
                continue
            if tables and table.order <= tables[-1].order + 3 and self._looks_like_electrical_primary_continuation(text):
                tables.append(table)
        return tables

    def _looks_like_electrical_primary_source_table(self, text: str) -> bool:
        patterns = [
            r"110\s*kV\s*升压站本期规模",
            r"(?:6\.3-1|6\.3\.1|6\.2\.\d+).*升压站.*本期规模",
            r"升压站电气一次主要设备材料工程量表",
            r"主要电气一次设备",
            r"(?:6\.3\.3-10|6\.2\.9|6\.3\.11).*电气一次.*(?:主要设备|设备材料|材料工程量)",
        ]
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return True
        return (
            "电气一次" in text
            and "型号、规格及技术数据" in text
            and "单位" in text
            and "数量" in text
            and any(keyword in text for keyword in ("主变压器", "35kV SVG", "接地变成套装置", "GIS"))
        )

    def _looks_like_electrical_primary_continuation(self, text: str) -> bool:
        clean_text = self._clean_text(text)
        if not clean_text:
            return False
        header_hits = sum(1 for keyword in ("序号", "名称", "型号", "规范", "单位", "数量", "备注") if keyword in clean_text)
        if header_hits >= 3:
            return True
        equipment_hits = sum(
            1
            for keyword in (
                "主变",
                "断路器",
                "隔离开关",
                "互感器",
                "避雷器",
                "开关柜",
                "接地变",
                "无功补偿",
                "电缆",
                "母线",
                "站外电源",
                "站外电源变压器",
            )
            if keyword in clean_text
        )
        return equipment_hits >= 2 and bool(re.search(r"\b(?:台|套|组|面|根|只|个)\b", clean_text))

    def _electrical_access_station_combined_row(self, matrix: list[list[str]], table: DocumentTable) -> dict[str, Any]:
        row = {"accessStationName": None, "accessibleVoltage": None, "accessibleCapacity": None}
        for source_row_index, source_row in enumerate(matrix):
            if any("接入站名称" in cell for cell in source_row):
                value_row = self._next_non_empty_row(matrix, source_row_index + 1)
                if value_row:
                    row["accessStationName"] = self._normalize_table_cell(value_row[0]) if len(value_row) > 0 else None
                    row["accessibleVoltage"] = self._normalize_table_cell(value_row[1]) if len(value_row) > 1 else None
                    row["accessibleCapacity"] = self._normalize_table_cell(value_row[2]) if len(value_row) > 2 else None
                    row["_cellSources"] = {
                        key: self._table_cell_source(table, source_row_index + 1, column_index, "按电气一次原表表头抽取。", resolver="electrical_primary_header_mapping")
                        for key, column_index in (("accessStationName", 0), ("accessibleVoltage", 1), ("accessibleCapacity", 2))
                        if column_index < len(value_row) and value_row[column_index].strip()
                    }
                break
        return row if any(value is not None for value in row.values()) else {}

    def _electrical_access_station_combined_row_from_tables(self, ast: DocumentAST) -> dict[str, Any]:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            for header_index, header in enumerate(matrix):
                header_text = " ".join(header)
                if not all(keyword in header_text for keyword in ("接入站名称", "可接入电压", "可接入容量")):
                    continue
                value_row_index = next(
                    (
                        index
                        for index in range(header_index + 1, len(matrix))
                        if any(self._clean_text(cell) for cell in matrix[index])
                    ),
                    None,
                )
                if value_row_index is None:
                    continue
                value_row = matrix[value_row_index]
                column_by_key = {
                    "accessStationName": self._find_header_index(header, ["接入站名称"]),
                    "accessibleVoltage": self._find_header_index(header, ["可接入电压"]),
                    "accessibleCapacity": self._find_header_index(header, ["可接入容量"]),
                }
                row = {
                    key: self._normalize_table_cell(value_row[column_index]) if column_index is not None and column_index < len(value_row) else None
                    for key, column_index in column_by_key.items()
                }
                row["_cellSources"] = {
                    key: self._table_cell_source(table, value_row_index, column_index, "按接入站表明确表头抽取。", resolver="electrical_primary_access_station_table")
                    for key, column_index in column_by_key.items()
                    if column_index is not None and column_index < len(value_row) and self._clean_text(value_row[column_index])
                }
                return row if any(value is not None for key, value in row.items() if not str(key).startswith("_")) else {}
        return {}

    def _electrical_main_connection_combined_row(self, matrix: list[list[str]], table: DocumentTable) -> dict[str, Any]:
        row = {"plannedCapacity": None, "currentCapacity": None, "connectionType": None}
        for source_row_index, source_row in enumerate(matrix):
            if any("主接线规划总规模" in cell for cell in source_row):
                value_row = self._next_non_empty_row(matrix, source_row_index + 1)
                if value_row:
                    row["plannedCapacity"] = self._normalize_table_cell(value_row[0]) if len(value_row) > 0 else None
                    row["currentCapacity"] = self._normalize_table_cell(value_row[1]) if len(value_row) > 1 else None
                    row["connectionType"] = "\n".join(cell for cell in value_row[2:] if cell.strip()) if len(value_row) > 2 else None
                    row["_cellSources"] = {
                        key: self._table_cell_source(table, source_row_index + 1, column_index, "按电气一次原表表头抽取。", resolver="electrical_primary_header_mapping")
                        for key, column_index in (("plannedCapacity", 0), ("currentCapacity", 1), ("connectionType", 2))
                        if column_index < len(value_row) and value_row[column_index].strip()
                    }
                break
        return row if any(value is not None for value in row.values()) else {}

    def _electrical_lightning_combined_row(self, matrix: list[list[str]], table: DocumentTable) -> dict[str, Any]:
        row = {"independentLightningRodCount": None, "frameLightningRodCount": None}
        for source_row_index, source_row in enumerate(matrix):
            if any("独立避雷针座数" in cell for cell in source_row):
                value_row = self._next_non_empty_row(matrix, source_row_index + 1)
                if value_row:
                    row["independentLightningRodCount"] = self._normalize_table_cell(value_row[0]) if len(value_row) > 0 else None
                    row["frameLightningRodCount"] = self._normalize_table_cell(value_row[1]) if len(value_row) > 1 else None
                    row["_cellSources"] = {
                        key: self._table_cell_source(table, source_row_index + 1, column_index, "按电气一次原表表头抽取。", resolver="electrical_primary_header_mapping")
                        for key, column_index in (("independentLightningRodCount", 0), ("frameLightningRodCount", 1))
                        if column_index < len(value_row) and value_row[column_index].strip()
                    }
                break
        return row if any(value is not None for value in row.values()) else {}

    def _next_non_empty_row(self, matrix: list[list[str]], start: int) -> list[str] | None:
        for row in matrix[start:]:
            if any(cell.strip() for cell in row):
                return row
        return None

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
        match = re.search(r"(本工程[^。；;\n]{0,40}?采用[^。；;\n]{1,160}?电力电缆)", text)
        if match:
            return self._clean_text(match.group(1))
        return None

    def _collector_laying_method_from_text(self, text: str) -> str | None:
        if not text:
            return None
        return "架空+电缆直埋" if "架空" in text else "电缆直埋"

    def _communication_power_design_from_ast(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._clean_text(block.text or "") for block in self._body_blocks(ast) if block.text)
        table_text = "\n".join(self._table_text(table) for table in ast.tables)
        page_text = "\n".join(self._clean_text(str(page.get("text", ""))) for page in (ast.meta.get("pdf_page_texts") or []) if isinstance(page, dict))
        combined = f"{text}\n{table_text}\n{page_text}"
        patterns = [
            r"(\-?\s*48\s*V\s*/\s*200\s*Ah\s*\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60\s*[:\uff1a]\s*1\s*\u7ec4)",
            r"(200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60\s*1\s*\u7ec4\u53ca\s*1\s*\u5957\s*DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e)",
            r"(1\s*\u7ec4\s*200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,30}?DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e\s*1\s*\u5957)",
            r"(48\s*V\s*/\s*200\s*Ah[^\n\u3002\uff1b;]{0,30}?\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,20}?(?:1\s*\u7ec4))",
            r"(48\s*V\s*/\s*200\s*Ah[^\n\u3002\uff1b;]{0,50})",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined, flags=re.IGNORECASE)
            if match:
                return self._normalize_communication_power_design(match.group(1))
        return None

    def _communication_power_design_description_from_ast(self, ast: DocumentAST) -> str | None:
        patterns = self._communication_power_design_description_patterns()
        texts = [self._clean_text(block.text or "") for block in self._body_blocks(ast) if block.text]
        texts.extend(
            self._clean_text(str(page.get("text", "")))
            for page in (ast.meta.get("pdf_page_texts") or [])
            if isinstance(page, dict) and page.get("text")
        )
        for text in texts:
            for sentence in self._sentences(text):
                if self._communication_power_design_description_matches(sentence, patterns):
                    return self._clean_text(sentence).rstrip("。；;")
            if self._communication_power_design_description_matches(text, patterns):
                return self._clean_text(text).rstrip("。；;")
        return None

    def _communication_power_unit_quantity_from_ast(
        self, ast: DocumentAST
    ) -> tuple[str | None, Any, str, list[str]] | None:
        table_candidates: list[tuple[int, str | None, Any, str, list[str]]] = []
        for table in ast.tables:
            matrix = self._table_matrix(table)
            header = self._header_row(matrix, ["单位", "数量"])
            if not header:
                continue
            unit_index = self._find_header_index(header, ["单位", "单 位"])
            quantity_index = self._find_header_index(header, ["数量", "数 量"])
            if unit_index is None or quantity_index is None:
                continue
            for row in matrix[matrix.index(header) + 1 :]:
                row_text = self._clean_text(" | ".join(row))
                compact = re.sub(r"\s+", "", row_text)
                score = 0
                if "通讯电池" in compact or "通信电池" in compact:
                    score = 300
                elif re.search(r"48V/200Ah", compact, flags=re.IGNORECASE) and "蓄电池" in compact:
                    score = 200
                if not score:
                    continue
                unit_value = self._clean_text(row[unit_index]) if unit_index < len(row) else None
                quantity_value = self._normalize_scalar(row[quantity_index]) if quantity_index < len(row) else None
                if unit_value or quantity_value is not None:
                    table_candidates.append((score, unit_value or None, quantity_value, row_text, list(table.section_path or ["电气二次"])))
        if table_candidates:
            _, unit_value, quantity_value, evidence_text, section_path = max(table_candidates, key=lambda item: item[0])
            return unit_value, quantity_value, evidence_text, section_path

        blocks = self._configured_text_blocks(
            ast,
            "electrical_secondary",
            ["电气二次", "通信", "通讯"],
            ["通信电源", "通讯电源", "200Ah", "蓄电池"],
        )
        patterns = [
            r"(?:48\s*V\s*/\s*200\s*Ah|200\s*Ah)[^\n。；;]{0,50}?蓄电池[^\n。；;]{0,20}?([0-9]+(?:\.\d+)?)\s*(组|套|台)",
            r"([0-9]+(?:\.\d+)?)\s*(组|套|台)[^\n。；;]{0,20}?(?:48\s*V\s*/\s*200\s*Ah|200\s*Ah)[^\n。；;]{0,40}?蓄电池",
        ]
        text_sources = [
            (self._clean_text(block.text or ""), list(block.section_path or ["电气二次"]))
            for block in blocks
        ]
        text_sources.extend(
            (self._clean_text(str(page.get("text", ""))), ["电气二次"])
            for page in (ast.meta.get("pdf_page_texts") or [])
            if isinstance(page, dict) and page.get("text")
        )
        for text, section_path in text_sources:
            for pattern_index, pattern in enumerate(patterns):
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                if pattern_index == 0:
                    quantity, unit_value = match.group(1), match.group(2)
                else:
                    quantity, unit_value = match.group(1), match.group(2)
                return unit_value, self._normalize_scalar(quantity), text, section_path
        return None

    def _communication_power_design_description_patterns(self) -> list[str]:
        return [
            r"200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60\s*1\s*\u7ec4\u53ca\s*1\s*\u5957\s*DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e",
            r"1\s*\u7ec4\s*200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,30}?DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e\s*1\s*\u5957",
        ]

    def _communication_power_design_description_matches(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _normalize_communication_power_design(self, text: str) -> str:
        value = self._normalize_text_value(text)
        value = re.sub(r"\s+", "", value)
        value = value.lstrip("-")
        if "48V/200Ah" in value and "\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60" in value:
            return re.sub(r"(\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60)[:\uff1a,\uff0c]?(1\u7ec4)", r"\1：\2", value)
        value = re.sub(r"^1\u7ec4(200Ah\u514d\u7ef4\u62a4\u84c4\u7535\u6c60)[\uff0c,]?", r"\g<1>" + "1\u7ec4\u53ca", value)
        value = value.replace("：", "，").replace(":", "，")
        value = re.sub(r"，+", "，", value).strip("，")
        value = re.sub(r"(?<!，)(1组)$", r"，\1", value)
        return value

    def _apply_electrical_primary_table_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        values = self._electrical_primary_station_scale_values(ast)
        values.update(self._electrical_primary_values_from_equipment_tables(ast))
        for code, override in values.items():
            if code in skip_codes:
                continue
            if fields.get(code) is not None and fields[code].value is not None and any(evidence.source_type == "table" for evidence in fields[code].evidence):
                continue
            name, value, unit, evidence_text, meta = override
            self._set_field(fields, code, name, value, unit, evidence_text, source_type="table", meta=meta)

    def _electrical_primary_station_scale_values(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str, dict[str, Any]]]:
        values: dict[str, tuple[str, Any, str | None, str, dict[str, Any]]] = {}
        targets = [
            ("electricalPrimaryCurrentOutgoingLineCount", "升压站本期出线回数", "本期规模"),
            ("electricalPrimaryFutureOutgoingLineCount", "升压站远期出线回数", "远期规模"),
        ]
        for table in sorted(ast.tables, key=lambda item: item.order):
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            table_text = self._table_text(table)
            target_text = f"{caption}\n{section_caption}\n{table_text[:600]}"
            if not re.search(r"110\s*kV\s*升压站", target_text, flags=re.IGNORECASE):
                continue
            header_index = self._station_scale_header_row_index(matrix)
            header = matrix[header_index]
            name_index = self._find_header_index(header, ["名称", "项目", "项目名称"])
            current_index = self._find_header_index(header, ["本期规模", "本期"])
            future_index = self._find_header_index(header, ["远期规模", "远期"])
            if name_index is None:
                name_index = 0
            if current_index is None and future_index is None:
                continue
            for row_index, row in enumerate(matrix[header_index + 1 :], start=header_index + 1):
                name_text = self._clean_text(row[name_index] if name_index < len(row) else "")
                row_text = self._clean_text(" ".join(row))
                if not self._looks_like_station_outgoing_line_row(name_text or row_text):
                    continue
                for code, field_name, scale_name in targets:
                    if code in values:
                        continue
                    value_index = current_index if scale_name == "本期规模" else future_index
                    raw_value = self._table_index_value(row, value_index)
                    value = self._station_outgoing_line_count_value(raw_value)
                    if value is None:
                        continue
                    evidence_text = self._clean_text(" | ".join(row))
                    values[code] = (
                        field_name,
                        value,
                        "回",
                        evidence_text,
                        {
                            "sectionPath": list(table.section_path or ["电气一次"]),
                            "tableId": table.id,
                            "caption": caption or table.caption or self._caption_before_table_from_table(table),
                            "resolver": "electrical_primary_station_scale_table",
                            "matchMethod": "row_label_scale_column",
                        },
                    )
        return values

    def _station_scale_header_row_index(self, matrix: list[list[str]]) -> int:
        for index, row in enumerate(matrix[:4]):
            text = self._clean_text(" ".join(row))
            if any(keyword in text for keyword in ("本期规模", "远期规模")) and any(keyword in text for keyword in ("名称", "项目")):
                return index
        return 0

    def _looks_like_station_outgoing_line_row(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", self._clean_text(text)).lower()
        return bool(re.search(r"110kv(?:出线|回路数|出线回数)", compact))

    def _station_outgoing_line_count_value(self, value: Any) -> Any:
        text = self._clean_text(str(value or ""))
        if not text:
            return None
        match = re.search(r"([0-9]+(?:\.\d+)?)\s*回", text)
        if match:
            return self._normalize_scalar(match.group(1))
        chinese_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        match = re.search(r"([一二两三四五六七八九十])\s*回", text)
        if match:
            return chinese_map.get(match.group(1))
        return None

    def _electrical_primary_values_from_equipment_tables(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str, dict[str, Any]]]:
        values: dict[str, tuple[str, Any, str | None, str, dict[str, Any]]] = {}
        field_specs = {
            "electricalPrimaryTransformerSpec": {
                "name": "主变压器型号、规格及技术数据",
                "row_aliases": ["主变压器"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"三相双绕组油浸自冷式有\s*载调压变压器",
                    r"型号\s*[:：]\s*SZ20-100000/110",
                    r"115\s*±\s*8\s*×\s*1\.25%\s*/\s*37kV",
                    r"接线组别\s*[:：]\s*YN\s*[，,]\s*d11",
                ],
            },
            "electricalPrimarySvgSpec": {
                "name": "35kV SVG型号、规格及技术数据",
                "row_aliases": ["35kV SVG", "35kv SVG", "SVG"],
                "value": "spec",
                "merge": False,
            },
            "electricalPrimarySvgUnit": {
                "name": "35kV SVG单位",
                "row_aliases": ["35kV SVG", "35kv SVG", "SVG"],
                "value": "unit",
                "merge": False,
            },
            "electricalPrimarySvgQuantity": {
                "name": "35kV SVG数量",
                "row_aliases": ["35kV SVG", "35kv SVG", "SVG"],
                "value": "quantity",
                "merge": False,
            },
            "electricalPrimaryGisModelInfo": {
                "name": "GIS型号信息",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "spec",
                "merge": False,
            },
            "electricalPrimaryGisQuantity": {
                "name": "110kV架空出线间隔数量",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "quantity",
                "merge": False,
            },
            "electricalPrimaryGisUnit": {
                "name": "110kV架空出线间隔单位",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "unit",
                "merge": False,
            },
            "electricalPrimaryGisRemark": {
                "name": "110kV架空出线间隔备注",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "remark",
                "merge": False,
            },
            "electricalPrimaryCircuitBreakerModel": {
                "name": "断路器型号",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"SF6断路器[:：][^，。；;]*(?:[，,](?!\s*(?:三工位|快速接地|隔离|电流互感器|电压互感器))[^，。；;]*)*",
                ],
            },
            "electricalPrimaryDisconnectorModel": {
                "name": "隔离开关型号",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"(?:三工位)?隔离接地开关[:：][^，。；;]*(?:[，,](?!\s*(?:快速接地|电流互感器|电压互感器|SF6断路器))[^，。；;]*)*",
                    r"(?:三工位)?隔离开关[:：][^，。；;]*(?:[，,](?!\s*(?:快速接地|电流互感器|电压互感器|SF6断路器))[^，。；;]*)*",
                ],
            },
            "electricalPrimaryCurrentTransformerModel": {
                "name": "电流互感器型号",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"电流互感器[:：].*?(?=(?:[，,]\s*电压互感器)|$)",
                ],
            },
            "electricalPrimaryVoltageTransformerModel": {
                "name": "电压互感器型号",
                "row_aliases": ["GIS", "AIS", "GIS组合电器", "AIS组合电器", "GIS成套设备", "AIS成套设备"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"电压互感器[:：].*?(?=(?:[，,]\s*(?:避雷器|母线|汇控柜|电流互感器))|$)",
                ],
            },
            "electricalPrimaryGroundingTransformerSetSpec": {
                "name": "35kV接地变成套装置型号、规格及技术数据",
                "row_aliases": ["35kV接地变成套装置", "35kv接地变成套装置", "接地变成套装置"],
                "value": "spec",
                "merge": True,
                "include_patterns": [
                    r"DKSC-800/37-315/0\.4",
                    r"接地变容量\s*[:：]\s*500kVA",
                    r"小电阻型号\s*[:：]\s*NGR-37/200A\s*[—-]\s*10s\s*,\s*106\.8Ω",
                ],
            },
            "electricalPrimaryExternalPowerTransformerSpec": {
                "name": "站外电源变压器型号、规格及技术数据",
                "row_aliases": ["站外电源变压器", "站外备用电源变压器", "外来电源变压器"],
                "value": "spec",
                "merge": True,
            },
        }
        specs = {
            "svgReactiveCompensationCapacity": {
                "name": "SVG无功补偿装置容量",
                "unit": "Mvar",
                "row_aliases": ["SVG无功补偿装置", "SVG 无功补偿装置", "无功补偿装置", "SVG"],
                "patterns": [r"([±＋+-]?\s*\d+(?:\.\d+)?\s*Mvar)", r"([±＋+-]?\s*\d+(?:\.\d+)?)\s*Mvar"],
            },
            "stationTransformerCapacity10kv": {
                "name": "10kV站用变容量",
                "unit": None,
                "row_aliases": ["10kV站用变", "10kv站用变", "站用变"],
                "patterns": [r"([0-9]+(?:\.[0-9]+)?\s*kVA)", r"([0-9]+(?:\.[0-9]+)?)\s*kVA"],
            },
            "groundingTransformerCapacity35kv": {
                "name": "35kV接地变容量",
                "unit": None,
                "row_aliases": ["35kV接地变成套装置", "35kv接地变成套装置", "接地变成套装置"],
                "patterns": [
                    r"接地变容量\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                    r"DKSC[-－]\s*([0-9]+(?:\.[0-9]+)?)(?:\s*kVA)?\s*[/－-]\s*35",
                    r"([0-9]+(?:\.[0-9]+)?\s*kVA)",
                ],
            },
            "groundingStationTransformerCapacity35kv": {
                "name": "35kV接地变兼站用变容量",
                "unit": None,
                "row_aliases": ["35kV接地兼站用变", "35kv接地兼站用变", "接地变兼站用变成套装置"],
                "patterns": [
                    r"接地变容量\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?\s*/\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                    r"DKSC[-－]\s*[0-9]+(?:\.[0-9]+)?(?:\s*kVA)?\s*[/－-]\s*35\s*[/－-]\s*([0-9]+(?:\.[0-9]+)?)(?:\s*kVA)?",
                    r"([0-9]+(?:\.[0-9]+)?\s*kVA)",
                ],
            },
        }
        for table in self._electrical_primary_equipment_tables(ast):
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            header = matrix[0]
            name_index = self._find_header_index(header, ["名称", "名 称", "设备名称"])
            spec_index = self._find_header_index(header, ["型号、规格及技术数据", "型号规格及技术数据", "型号及规格", "型号与规格", "规格"])
            if name_index is None:
                name_index = 1 if len(header) > 1 else 0
            if spec_index is None:
                spec_index = 2 if len(header) > 2 else None
            if spec_index is None:
                continue
            has_header = any(keyword in self._clean_text(" ".join(header)) for keyword in ("型号", "规格", "技术数据", "名称"))
            data_start_index = 1 if has_header else 0
            unit_index = self._find_header_index(header, ["单位"])
            quantity_index = self._find_header_index(header, ["数量"])
            if unit_index is None and not has_header and len(header) > 3:
                unit_index = 3
            if quantity_index is None and not has_header and len(header) > 4:
                quantity_index = 4
            remark_index = self._find_header_index(header, ["备注"])
            self._merge_electrical_primary_equipment_table_fields(
                values,
                table,
                matrix,
                name_index,
                spec_index,
                unit_index,
                quantity_index,
                remark_index,
                field_specs,
                data_start_index,
            )
            for code, spec in specs.items():
                if code in values:
                    continue
                found = self._electrical_primary_value_from_equipment_matrix(table, matrix, name_index, spec_index, spec, data_start_index=data_start_index)
                if found is not None:
                    values[code] = found
        return values

    def _merge_electrical_primary_equipment_table_fields(
        self,
        values: dict[str, tuple[str, Any, str | None, str, dict[str, Any]]],
        table: DocumentTable,
        matrix: list[list[str]],
        name_index: int,
        spec_index: int,
        unit_index: int | None,
        quantity_index: int | None,
        remark_index: int | None,
        specs: dict[str, dict[str, Any]],
        data_start_index: int = 1,
    ) -> None:
        for row_index, row in enumerate(matrix[data_start_index:], start=data_start_index):
            name_cell = row[name_index] if name_index < len(row) else ""
            normalized_name = self._normalize_equipment_label(name_cell)
            if not normalized_name:
                continue
            for code, spec in specs.items():
                if code in values:
                    continue
                if not any(self._normalize_equipment_label(alias) in normalized_name for alias in spec["row_aliases"]):
                    continue
                value_kind = spec.get("value")
                if value_kind == "unit":
                    value = self._table_index_value(row, unit_index)
                elif value_kind == "quantity":
                    raw_value = self._table_index_value(row, quantity_index)
                    value = self._normalize_table_cell(raw_value) if raw_value is not None else None
                elif value_kind == "remark":
                    value = self._table_index_value(row, remark_index)
                elif spec.get("merge"):
                    value = self._electrical_primary_equipment_block_text(matrix, row_index, name_index, spec_index)
                    value = self._filter_electrical_primary_spec_text(value, spec.get("include_patterns") or [])
                else:
                    value = self._table_index_value(row, spec_index)
                if value in (None, "", [], {}):
                    continue
                source_text = self._electrical_primary_equipment_block_text(matrix, row_index, name_index, spec_index)
                values[code] = (
                    str(spec["name"]),
                    self._normalize_electrical_spec_text(str(value)) if value_kind == "spec" else value,
                    None,
                    source_text,
                    {
                        "sectionPath": list(table.section_path or ["电气一次"]),
                        "tableId": table.id,
                        "caption": table.caption or self._caption_before_table_from_table(table),
                        "resolver": "electrical_primary_equipment_table",
                        "matchMethod": "row_label_column_mapping",
                    },
                )

    def _normalize_equipment_label(self, value: Any) -> str:
        text = self._clean_text(str(value or "")).lower()
        text = text.replace("（", "(").replace("）", ")").replace("×", "x")
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5]+", "", text)

    def _electrical_primary_value_from_equipment_matrix(
        self,
        table: DocumentTable,
        matrix: list[list[str]],
        name_index: int,
        spec_index: int,
        spec: dict[str, Any],
        data_start_index: int = 1,
    ) -> tuple[str, Any, str | None, str, dict[str, Any]] | None:
        for row_index, row in enumerate(matrix[data_start_index:], start=data_start_index):
            name_cell = row[name_index] if name_index < len(row) else ""
            if not any(alias in self._clean_text(name_cell) for alias in spec["row_aliases"]):
                continue
            source_text = self._electrical_primary_equipment_block_text(matrix, row_index, name_index, spec_index)
            value = self._extract_first_pattern_value(source_text, spec["patterns"])
            if value is None:
                continue
            meta = {
                "sectionPath": list(table.section_path or ["电气一次"]),
                "tableId": table.id,
                "caption": table.caption or self._caption_before_table_from_table(table),
                "resolver": "electrical_primary_equipment_table",
                "matchMethod": "row_label_spec_column",
            }
            return str(spec["name"]), self._normalize_electrical_capacity_text(value), spec.get("unit"), source_text, meta
        return None

    def _filter_electrical_primary_spec_text(self, text: str, include_patterns: list[str]) -> str:
        if not include_patterns:
            return text
        parts: list[str] = []
        for pattern in include_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                parts.append(self._clean_text(match.group(0)))
        return self._normalize_text_value("，".join(parts)) if parts else text

    def _electrical_primary_equipment_block_text(self, matrix: list[list[str]], row_index: int, name_index: int, spec_index: int) -> str:
        parts: list[str] = []
        row = matrix[row_index]
        if spec_index < len(row):
            parts.append(row[spec_index])
        for next_row in matrix[row_index + 1 : row_index + 8]:
            next_name = self._clean_text(next_row[name_index] if name_index < len(next_row) else "")
            if next_name and next_name not in {"内容", "内含", "每间隔包含", "每间隔包含："}:
                break
            if spec_index < len(next_row) and self._clean_text(next_row[spec_index]):
                parts.append(next_row[spec_index])
        return self._normalize_text_value("，".join(part for part in parts if self._clean_text(part)))

    def _normalize_electrical_capacity_text(self, value: str) -> str:
        text = self._normalize_text_value(value)
        text = re.sub(r"\s+", "", text)
        text = text.replace("＋", "+")
        if text.startswith("+") or text.startswith("-"):
            text = "±" + text[1:]
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return text
        if re.fullmatch(r"\d+(?:\.\d+)?(?:kVA|Mvar)", text, flags=re.IGNORECASE):
            return re.sub(r"kva$", "kVA", text, flags=re.IGNORECASE).replace("mvar", "Mvar")
        return text

    def _normalize_electrical_spec_text(self, value: str) -> str:
        text = self._normalize_text_value(value)
        text = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", text)
        return text.replace("＋", "+")

    def _electrical_text_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        blocks = self._body_blocks(ast)
        text = "\n".join(self._clean_text(block.text or "") for block in blocks if block.text)
        table_text = "\n".join(self._table_text(table) for table in ast.tables)
        combined = f"{text}\n{table_text}"
        specs: dict[str, tuple[str, Any, str | None, list[str]]] = {
            "stationTransformerCapacity10kv": (
                "10kV站用变容量",
                self._station_transformer_capacity_10kv_from_ast(ast) or self._first_matching_text(
                    combined,
                    [
                        r"备用电源引自站外\s*10\s*kV\s*线路[^。；;\n]{0,80}?容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                        r"选用\s*1\s*台容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)\s*的\s*外来变压器",
                    ],
                ),
                None,
                ["站用变", "10kV"],
            ),
            "groundingTransformerCapacity35kv": (
                "35kV接地变容量",
                self._first_matching_text(
                    combined,
                    [
                        r"配置\s*1\s*台容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)\s*接地变",
                        r"接地变(?:成套装置)?\s*DKSC-([0-9]+(?:\.[0-9]+)?\s*kVA?)[-/]35\s*kV",
                        r"DKSC-([0-9]+(?:\.[0-9]+)?)(?:\s*kVA)?[-/]35\s*kV",
                    ],
                ),
                None,
                ["接地变"],
            ),
            "groundingStationTransformerCapacity35kv": (
                "35kV接地变兼站用变容量",
                self._first_matching_text(
                    combined,
                    [
                        r"兼带站用变[^。；;\n]{0,30}?站用变容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                        r"DKSC-[0-9]+(?:\.[0-9]+)?\s*kVA-([0-9]+(?:\.[0-9]+)?\s*kVA)[-/]35\s*kV",
                        r"DKSC-[0-9]+(?:\.[0-9]+)?(?:\s*kVA)?-([0-9]+(?:\.[0-9]+)?\s*kVA)",
                    ],
                ),
                None,
                ["接地变", "站用变"],
            ),
            "svgReactiveCompensationCapacity": (
                "SVG无功补偿装置容量",
                self._configured_electrical_text_field_value(combined, "svgReactiveCompensationCapacity") or self._svg_reactive_capacity_from_text(combined),
                None,
                ["SVG", "无功补偿"],
            ),
            "dcBatteryConfiguration": (
                "直流蓄电池配置",
                self._first_matching_text(
                    combined,
                    [
                        r"选用\s*(一组\s*220\s*V[、,，/]\s*250\s*Ah\s*阀控式\s*密封铅酸蓄电池组)",
                        r"(一组\s*220\s*V[、,，/]\s*250\s*Ah\s*阀控式\s*密封铅酸蓄电池组)",
                    ],
                ),
                None,
                ["220V", "蓄电池"],
            ),
            "upsPowerConfiguration": (
                "UPS电源配置",
                self._ups_configuration_from_blocks(ast) or self._first_matching_text(
                    combined,
                    [
                        r"设置\s*([0-9]+\s*套\s*[0-9]+(?:\.[0-9]+)?\s*kVA\s*双冗余互为备用[^。；;\n]{0,30}?UPS)",
                        r"([0-9]+\s*套\s*[0-9]+(?:\.[0-9]+)?\s*kVA\s*双冗余互为备用)",
                    ],
                ),
                None,
                ["UPS"],
            ),
            "independentLightningRodCount": (
                "独立避雷针座数",
                (self._lightning_rod_counts_from_text(combined) or (None, None))[0],
                "座",
                ["独立避雷针"],
            ),
            "frameLightningRodCount": (
                "构架避雷针座数",
                (self._lightning_rod_counts_from_text(combined) or (None, None))[1],
                "座",
                ["构架避雷针"],
            ),
        }
        specs.update(self._electrical_primary_additional_text_specs(ast, combined))
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, (name, value, unit, evidence_keywords) in specs.items():
            if code in skip_codes or value in (None, "", [], {}):
                continue
            value = self._normalize_scalar(self._normalize_electrical_text_value(str(value)))
            overrides[code] = (
                name,
                value,
                unit,
                self._field_evidence_text_for_value(ast, value, evidence_keywords),
                "paragraph",
                {"resolver": "deterministic_electrical_text", "sectionPath": ["电气一次" if code not in {"dcBatteryConfiguration", "upsPowerConfiguration"} else "电气二次"]},
            )
        return overrides

    def _configured_electrical_text_field_value(self, text: str, field_code: str) -> Any:
        section = self._deterministic_rule_section("electrical_primary")
        fields = section.get("text_fields") if isinstance(section.get("text_fields"), dict) else {}
        rule = fields.get(field_code) if isinstance(fields.get(field_code), dict) else None
        if not rule:
            return None
        value = self._value_from_configured_patterns(text, rule)
        if value is None:
            return None
        if rule.get("normalize") == "electrical_text":
            return self._normalize_electrical_text_value(str(value))
        return value

    def _svg_reactive_capacity_from_text(self, text: str) -> str | None:
        patterns = [
            r"([0-9]+\s*套\s*容性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar\s*[~～\-－—]\s*感性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar\s*SVG\s*动态无功补偿装置)",
            r"([0-9]+\s*套\s*感性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar\s*[~～\-－—]\s*容性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar\s*SVG\s*动态无功补偿装置)",
            r"(SVG\s*动态无功补偿装置[^\n。；;]{0,60}?容性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar[^\n。；;]{0,30}?感性\s*[0-9]+(?:\.[0-9]+)?\s*Mvar)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._normalize_text_value(match.group(1))
        return None

    def _electrical_primary_additional_text_specs(
        self, ast: DocumentAST, combined: str
    ) -> dict[str, tuple[str, Any, str | None, list[str]]]:
        box_model = self._electrical_box_transformer_model(combined)
        box_capacity, box_voltage = self._electrical_box_transformer_capacity_voltage(box_model)
        grid_connection_text = self._electrical_connection_context_text(ast)
        return {
            "electricalPrimaryFrameLightningRodHeight": ("构架避雷针高度", self._lightning_rod_height_from_ast(ast, "frame"), "m", ["构架避雷针", "避雷针高度"]),
            "electricalPrimaryIndependentLightningRodHeight": ("独立避雷针高度", self._lightning_rod_height_from_ast(ast, "independent"), "m", ["独立避雷针", "避雷针高度"]),
            "electricalPrimaryBoxTransformerType": ("箱变类型", self._electrical_box_transformer_type(combined), None, ["机组变压器选用", "箱式变电站选用", "箱式变电站"]),
            "electricalPrimaryBoxTransformerModel": ("箱变型号", box_model, None, ["箱式变电站", "变压器型号", "箱变选用"]),
            "electricalPrimaryBoxTransformerVoltageLevel": ("箱变电压等级", box_voltage, "kV", ["箱式变电站", "型号"]),
            "electricalPrimaryBoxTransformerCapacity": ("箱变容量", box_capacity, "kVA", ["箱式变电站", "型号"]),
            "electricalPrimaryBoxTransformerHighVoltageSideConfig": ("高压侧配置信息", self._electrical_box_side_sentence(combined, "高压侧"), None, ["箱式变电站", "高压侧"]),
            "electricalPrimaryBoxTransformerLowVoltageSideConfig": ("低压侧配置信息", self._electrical_box_side_sentence(combined, "低压侧"), None, ["箱式变电站", "低压侧"]),
            "electricalPrimaryGridConnectionDistance": ("接入距离", self._connection_distance_from_text(grid_connection_text), "km", ["接入系统方案", "接入系统方式", "安全稳定控制系统"]),
            "electricalPrimaryGridConnectionLineType": ("接入站送出线路方式", self._connection_line_type_from_text(grid_connection_text), None, ["接入系统方案", "接入系统方式", "安全稳定控制系统"]),
            "electricalPrimarySubstationConstructionType": ("升压站建设类型", self._electrical_substation_construction_type(ast), None, ["新建", "扩建", "共用一座", "升压站"]),
            "electricalPrimaryExpandedSubstationName": ("扩建升压站", self._electrical_expanded_substation_name(ast), None, ["扩建", "共用一座", "升压站"]),
            "electricalPrimarySubstationVoltageLevel": ("升压站电压等级", self._substation_voltage_level_from_ast(ast), "kV", ["电气主接线", "升压站电气主接线", "升压站"]),
        }

    def _lightning_rod_height_from_ast(self, ast: DocumentAST, kind: str) -> Any:
        electrical_text = "\n".join(self._clean_text(block.text or "") for block in self._electrical_primary_text_blocks(ast))
        value = self._lightning_rod_height_from_text(electrical_text, kind)
        if value is not None:
            return value
        all_text = "\n".join(self._clean_text(block.text or "") for block in self._body_blocks(ast))
        return self._lightning_rod_height_from_text(all_text, kind)

    def _lightning_rod_height_from_text(self, text: str, kind: str) -> Any:
        keyword_pattern = r"(?:构架|架构)\s*避雷针" if kind == "frame" else r"独立\s*避雷针"
        patterns = [
            rf"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m\s*{keyword_pattern}",
            rf"{keyword_pattern}[^。；;\n]{{0,20}}?(?:高度)?[^0-9]{{0,8}}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group("value"))
        return None

    def _electrical_box_transformer_type(self, text: str) -> str | None:
        context = self._keyword_window(text, ["机组变压器选用", "箱式变电站选用", "箱式变电站", "箱变"], 220)
        if not context:
            return None
        patterns = [
            r"((?:预装式|华变|华式|欧式|美式)[^，。；;\n]{0,20}?(?:箱式变电站|变电站|箱变))",
            r"((?:箱式变电站|箱变)[^，。；;\n]{0,20}?(?:预装式|华变|华式|欧式|美式)[^，。；;\n]{0,10})",
        ]
        return self._first_matching_text(context, patterns)

    def _electrical_box_transformer_model(self, text: str) -> str | None:
        context = self._keyword_window(text, ["箱式变电站", "箱变", "机组变压器"], 260)
        if not context:
            return None
        patterns = [
            r"(?:变压器型号|型号|箱变选用|箱式变电站选用)[^A-Za-z0-9]{0,20}([A-Z]{1,5}[0-9A-Z-]*-[0-9]+(?:\.[0-9]+)?/[0-9]+(?:\.[0-9]+)?)",
            r"([A-Z]{1,5}[0-9A-Z-]*-[0-9]+(?:\.[0-9]+)?/[0-9]+(?:\.[0-9]+)?)",
        ]
        return self._first_matching_text(context, patterns)

    def _electrical_box_transformer_capacity_voltage(self, model: str | None) -> tuple[Any, Any]:
        if not model:
            return None, None
        match = re.search(r"-([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)", model)
        if not match:
            return None, None
        return self._normalize_scalar(match.group(1)), self._normalize_scalar(match.group(2))

    def _electrical_box_side_sentence(self, text: str, keyword: str) -> str | None:
        for sentence in self._sentences(text):
            if keyword in sentence and any(marker in sentence for marker in ("箱式变电站", "箱式变", "箱变", "变压器")):
                return self._clean_text(sentence.strip("。；;"))
        return None

    def _electrical_connection_context_text(self, ast: DocumentAST) -> str:
        blocks = self._body_blocks(ast)
        parts: list[str] = []
        keywords = ("接入系统方案", "安全稳定控制系统", "接入系统方式")
        for index, block in enumerate(blocks):
            text = self._clean_text(block.text or "")
            if not any(keyword in text for keyword in keywords):
                continue
            window = [text]
            for next_block in blocks[index + 1 : index + 4]:
                next_text = self._clean_text(next_block.text or "")
                if next_text:
                    window.append(next_text)
            parts.append(" ".join(window))
        return "\n".join(parts)

    def _connection_distance_from_text(self, text: str) -> Any:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*km", text, flags=re.IGNORECASE)
        return self._normalize_scalar(match.group(1)) if match else None

    def _connection_line_type_from_text(self, text: str) -> str | None:
        if not text:
            return None
        return "电缆" if "电缆" in text else "架空"

    def _electrical_substation_construction_type(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._clean_text(block.text or "") for block in self._electrical_primary_text_blocks(ast))
        if "新建" in text and "升压站" in text:
            return "新建"
        if ("扩建" in text or "共用一座" in text) and "升压站" in text:
            match = re.search(r"([0-9]{2,3}\s*kV[^，。；;\n]{0,20}?升压站|[\u4e00-\u9fa5A-Za-z0-9]+升压站)", text)
            station = self._clean_text(match.group(1)).replace(" ", "") if match else ""
            return f"扩建-{station}" if station else "扩建"
        return None

    def _electrical_expanded_substation_name(self, ast: DocumentAST) -> str | None:
        """Extract the expanded/shared substation named in the same local clause."""
        for block in self._electrical_primary_text_blocks(ast):
            text = self._clean_text(block.text or "")
            for clause in re.split(r"[。；;\n]", text):
                if "升压站" not in clause or not any(keyword in clause for keyword in ("扩建", "共用一座")):
                    continue
                station = self._expanded_substation_from_clause(clause)
                if station:
                    return f"扩建-{station}"
        return None

    def _expanded_substation_from_clause(self, clause: str) -> str | None:
        trigger_matches = list(re.finditer(r"扩建|共用一座", clause))
        for trigger in trigger_matches:
            after = clause[trigger.end() :]
            station_end = after.find("升压站")
            if station_end >= 0:
                fragment = after[: station_end + len("升压站")]
                station = self._normalize_expanded_substation_fragment(fragment)
                if station:
                    return station

            before = clause[: trigger.start()]
            station_end = before.rfind("升压站")
            if station_end >= 0:
                fragment = before[: station_end + len("升压站")]
                station = self._normalize_expanded_substation_fragment(fragment, prefer_tail=True)
                if station:
                    return station
        return None

    def _normalize_expanded_substation_fragment(self, fragment: str, prefer_tail: bool = False) -> str | None:
        value = self._clean_text(fragment).strip(" ，,：:")
        if not value:
            return None

        # Prefer a voltage-qualified station name because it has a reliable boundary.
        voltage_matches = list(
            re.finditer(r"[0-9]{2,3}\s*kV[^，,。；;\n]{0,24}?升压站", value, flags=re.IGNORECASE)
        )
        if voltage_matches:
            match = voltage_matches[-1] if prefer_tail else voltage_matches[0]
            return re.sub(r"\s+", "", match.group(0))

        value = re.sub(
            r"^(?:本期|本工程|本项目|工程|项目|拟|计划|将|对|与|同|和|现有|既有|原有|已建成?的?|建设|进行|实施|一座|[0-9]+座)+",
            "",
            value,
        )
        if prefer_tail:
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·#（）()_-]{1,30}升压站)$", value)
        else:
            match = re.match(r"([\u4e00-\u9fa5A-Za-z0-9·#（）()_-]{1,30}?升压站)", value)
        if not match:
            return None
        return re.sub(r"\s+", "", match.group(1))

    def _substation_voltage_level_from_ast(self, ast: DocumentAST) -> Any:
        text = "\n".join(self._clean_text(block.text or "") for block in self._electrical_primary_text_blocks(ast))
        target = self._keyword_window(text, ["电气主接线", "升压站电气主接线", "升压站"], 180) or text
        match = re.search(r"([0-9]{2,3})\s*kV\s*升压站|升压站[^。；;\n]{0,40}?([0-9]{2,3})\s*kV", target, flags=re.IGNORECASE)
        if not match:
            return None
        return self._normalize_scalar(match.group(1) or match.group(2))

    def _normalize_electrical_text_value(self, value: str) -> str:
        value = self._normalize_text_value(value)
        if "UPS" in value and "\u53cc\u5197\u4f59\u4e92\u4e3a\u5907\u7528" in value:
            value = re.split(r"\u7684\u4ea4\u6d41|\uff08UPS|\(UPS", value, maxsplit=1)[0]
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"^([0-9]+(?:\.[0-9]+)?)kVA?$", r"\1kVA", value, flags=re.IGNORECASE)
        value = re.sub(r"^([±+\-]?[0-9]+(?:\.[0-9]+)?)Mvar$", r"\1Mvar", value, flags=re.IGNORECASE)
        return value

    def _station_transformer_capacity_10kv_from_ast(self, ast: DocumentAST) -> str | None:
        candidates: list[tuple[int, str]] = []
        patterns = [
            r"10\s*kV\s*站用变[^。；;\n]{0,80}?SC\w*-([0-9]+(?:\.[0-9]+)?)(?:/|\s*kVA)",
            r"10\s*kV\s*站用变[^。；;\n]{0,60}?([0-9]+(?:\.[0-9]+)?\s*kVA)",
            r"备用电源引自站外\s*10\s*kV\s*线路[^。；;\n]{0,60}?容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
            r"([0-9]+(?:\.[0-9]+)?\s*kVA)[^。；;\n]{0,40}?10\s*kV\s*站用变",
            r"站用变容量(?:选择为|为|[:：])\s*(?:S=)?([0-9]+(?:\.[0-9]+)?\s*kVA)",
        ]
        for block in self._blocks_in_sections(ast, ["电气", "升压站", "站用电"]):
            text = self._clean_text(block.text)
            if "站用变" not in text:
                continue
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    value = match.group(1).strip()
                    nearby = text[max(0, match.start() - 80): match.end() + 80]
                    score = 5 if re.search(r"10\s*kV\s*站用变", nearby, flags=re.IGNORECASE) else 1
                    if "备用电源引自站外" in nearby:
                        score += 5
                    if "SC" in nearby and not value.lower().endswith("kva"):
                        value = f"{value}kVA"
                    if "35kV接地兼站用变" in nearby or "接地兼站用变" in nearby:
                        score -= 4
                    candidates.append((score, value))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _main_connection_from_blocks(self, ast: DocumentAST) -> str | None:
        for block in ast.blocks:
            text = self._clean_text(block.text)
            if "主接线" not in text and "线变组接线" not in text and "单母线接线" not in text:
                continue
            if "线变组接线" in text and "单母线接线" in text:
                return "110kV变电站采用线变组接线方式；35kV侧采用单母线接线方式"
            match = re.search(r"((?:线变组|单母线(?:分段)?)接线(?:型式|方式)?)", text)
            if match:
                return match.group(1)
        return None

    def _collector_line_names(self, ast: DocumentAST) -> str | None:
        names: list[str] = []
        seen: set[str] = set()
        for table in ast.tables:
            text = self._table_text(table)
            if "线路名称" not in text and "A线" not in text:
                continue
            for row in self._table_matrix(table):
                for cell in row:
                    for match in re.finditer(r"(?<![A-Z0-9])([A-Z][0-9]?)\s*线", cell):
                        name = f"{match.group(1)}线"
                        if name not in seen:
                            seen.add(name)
                            names.append(name)
            if names:
                break
        if not names:
            text = "\n".join(self._clean_text(block.text) for block in ast.blocks if "线" in block.text and ("集电线路" in block.text or "架空线路" in block.text))
            single_segments = re.findall(r"单回(?:路)?线路长度[^。；;\n]{0,220}", text)
            search_text = "\n".join(single_segments) or text
            for match in re.finditer(r"(?<![A-Z0-9])([A-Z][0-9]?)\s*线\s*[0-9]+(?:\.[0-9]+)?\s*km", search_text):
                name = f"{match.group(1)}线"
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        if len(names) >= 2:
            return "、".join(names)
        return None

    def _extract_equipment_specs(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str]]:
        found: dict[str, tuple[str, Any, str | None, str]] = {}
        table_specs = self._distribution_equipment_specs_from_document(ast)
        if table_specs:
            names = {
                "circuitBreakerSpec": "断路器",
                "disconnectorSpec": "隔离开关",
                "currentTransformerSpec": "电流互感器",
                "voltageTransformerSpec": "电压互感器",
            }
            for code, value in table_specs.items():
                found[code] = (names.get(code, code), value, None, value)
            return found
        patterns = {
            "circuitBreakerSpec": ("断路器", r"SF6断路器[:：，]\s*([^|\n]+)"),
            "disconnectorSpec": ("隔离开关", r"(?:三工位)?隔离(?:接地)?开关[:：]\s*([^|\n]+)"),
            "currentTransformerSpec": ("电流互感器", r"电流互感器[:：，]\s*([^|\n]+)"),
            "voltageTransformerSpec": ("电压互感器", r"电压互感器[:：，]\s*([^|\n]+)"),
        }
        best: dict[str, tuple[int, str]] = {}
        for table in ast.tables:
            text = self._table_text(table)
            if "断路器" not in text and "互感器" not in text and "隔离" not in text:
                continue
            for code, (name, pattern) in patterns.items():
                matches = list(re.finditer(pattern, text))
                if not matches:
                    continue
                for selected in matches:
                    value = selected.group(0).strip()
                    if code == "disconnectorSpec" and not value.startswith("隔离开关"):
                        value = "隔离开关：" + selected.group(1).strip()
                    score = self._equipment_spec_score(code, value)
                    if score > best.get(code, (-1, ""))[0]:
                        best[code] = (score, value)
        for code, (_score, value) in best.items():
            name = patterns[code][0]
            found[code] = (name, value, None, value)
        return found

    def _equipment_spec_score(self, code: str, value: str) -> int:
        score = 1
        if code == "currentTransformerSpec" and "600-1200/1A" in value:
            score += 5
        if code == "currentTransformerSpec" and "0.5/0.5" in value:
            score += 2
        if code == "voltageTransformerSpec" and "35/√3" in value:
            score += 5
        if code == "voltageTransformerSpec" and "30/30/30/100VA" in value:
            score += 3
        if code == "voltageTransformerSpec" and "3P/3P" in value:
            score += 2
        if code in {"circuitBreakerSpec", "disconnectorSpec"} and "126kV" in value:
            score += 2
        return score

    def _ups_configuration_from_blocks(self, ast: DocumentAST) -> str | None:
        for block in ast.blocks:
            found = re.search(r"本工程取UPS容量为([^。；;\n]+)。([^。；;\n]*双冗余方式)", block.text)
            if found:
                return f"容量为{found.group(1).strip()}，{found.group(2).strip()}"
        return self._regex_from_blocks(ast, r"本工程取UPS容量为([^。；;\n]+)")
