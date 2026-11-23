"""升压站、电气一次设备、主变和接入系统抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex, domain_strings

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable
from word_parser.document.ast.evidence import ParsedField


class ElectricalPrimaryRulesMixin:
    """升压站、电气一次设备、主变和接入系统抽取，通过 ElectricalRulesMixin 组合到结果构建器。"""

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
        # 接入站容量、升压站规划规模和本期规模属于三个不同对象，不能共用装机或主变容量。
        capacity_matches = {
            "accessibleCapacity": re.search(domain_regex(self, "electrical_primary", "search_001", r"(?:接入站[^，。；;\n]{0,20}?)?可接入容量\s*[：:]?\s*(?:为|约)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:MVA|兆伏安)"), text, flags=re.IGNORECASE),
            "plannedCapacity": re.search(domain_regex(self, "electrical_primary", "search_002", r"(?:升压站|主接线)[^，。；;\n]{0,20}?(?:规划总规模|规划容量|规划规模|远期规划容量)\s*[：:]?\s*为?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:MW|兆瓦)"), text, flags=re.IGNORECASE),
            "currentCapacity": re.search(domain_regex(self, "electrical_primary", "search_003", r"(?:升压站|主接线)[^，。；;\n]{0,20}?(?:本期规模|本期容量|本期建设容量)\s*[：:]?\s*为?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:MW|兆瓦)"), text, flags=re.IGNORECASE),
        }
        capacity_values = {
            key: self._normalize_scalar(match.group(1)) if match else None
            for key, match in capacity_matches.items()
        }
        source_match = next((match for match in capacity_matches.values() if match), None)
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
        if station or voltage_values or capacity_values["accessibleCapacity"] is not None:
            details["electricalPrimaryAccessStationCombined"] = [{
                "accessStationName": station,
                "accessibleVoltage": self._normalize_table_cell("、".join(voltage_values)) if voltage_values else None,
                "accessibleCapacity": capacity_values["accessibleCapacity"],
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
        if any(capacity_values[key] is not None for key in ("plannedCapacity", "currentCapacity")) or connection_parts:
            details["electricalPrimaryMainConnectionCombined"] = [{
                "plannedCapacity": capacity_values["plannedCapacity"],
                "currentCapacity": capacity_values["currentCapacity"],
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
            r"风电场[^。；;\n]{0,40}?([0-9]{2,3})\s*kV\s*出线[^。；;\n]{0,40}?接入",
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
        compact = re.sub(domain_regex(self, "electrical_primary", "sub_004", r"\s+"), "", value)
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
        for segment in re.split(domain_regex(self, "electrical_primary", "split_005", r"[\n\u3002\uff1b;]"), text):
            if "\u72ec\u7acb\u907f\u96f7\u9488" not in segment or "\u6784\u67b6\u907f\u96f7\u9488" not in segment:
                continue
            independent = re.search(domain_regex(self, "electrical_primary", "search_006", r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*(?:[0-9]+\s*m)?\s*\u72ec\u7acb\u907f\u96f7\u9488"), segment)
            frame = re.search(domain_regex(self, "electrical_primary", "search_007", r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*(?:[0-9]+\s*m)?\s*\u6784\u67b6\u907f\u96f7\u9488"), segment)
            if independent is None:
                independent = re.search(domain_regex(self, "electrical_primary", "search_008", r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*[0-9]+\s*m\s*\u72ec\u7acb\u907f\u96f7\u9488"), segment)
            if frame is None:
                frame = re.search(domain_regex(self, "electrical_primary", "search_009", r"([0-9]+)\s*(?:\u6839|\u5ea7|\u4e2a)\s*[0-9]+\s*m\s*\u6784\u67b6\u907f\u96f7\u9488"), segment)
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
        return equipment_hits >= 2 and bool(re.search(domain_regex(self, "electrical_primary", "search_010", r"\b(?:台|套|组|面|根|只|个)\b"), clean_text))

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
                    "accessStationName": self._find_header_index(header, domain_strings(self, "electrical_primary", "list_001", ["接入站名称"])),
                    "accessibleVoltage": self._find_header_index(header, domain_strings(self, "electrical_primary", "list_002", ["可接入电压"])),
                    "accessibleCapacity": self._find_header_index(header, domain_strings(self, "electrical_primary", "list_003", ["可接入容量"])),
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

    def _apply_electrical_primary_table_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        values = self._electrical_primary_station_scale_values(ast)
        values.update(self._electrical_primary_values_from_equipment_tables(ast))
        if "electricalPrimaryCurrentOutgoingLineCount" not in values:
            current_outgoing = self._current_outgoing_line_from_primary_text(ast)
            if current_outgoing is not None:
                value, block = current_outgoing
                values["electricalPrimaryCurrentOutgoingLineCount"] = (
                    "升压站本期出线回数", value, "回", self._clean_text(block.text or ""),
                    {
                        "sectionPath": list(block.section_path or ["电气一次"]),
                        "resolver": "electrical_primary_current_outgoing_text",
                        "matchMethod": "station_side_planned_outgoing_built_current",
                    },
                )
        for code, override in values.items():
            if code in skip_codes:
                continue
            name, value, unit, evidence_text, meta = override
            existing = fields.get(code)
            if existing is not None and existing.value is not None and any(evidence.source_type == "table" for evidence in existing.evidence):
                if code != "svgReactiveCompensationCapacity" or not re.fullmatch(
                    domain_regex(self, "electrical_primary", "fullmatch_011", r"[±+\-]?\s*\d+(?:\.\d+)?\s*Mvar"), self._clean_text(str(value)), re.I
                ) or re.fullmatch(domain_regex(self, "electrical_primary", "fullmatch_012", r"[±+\-]?\s*\d+(?:\.\d+)?\s*Mvar"), self._clean_text(str(existing.value)), re.I):
                    continue
            source_type = "paragraph" if meta.get("resolver") == "electrical_primary_current_outgoing_text" else "table"
            self._set_field(fields, code, name, value, unit, evidence_text, source_type=source_type, meta=meta)
        if "futureMainTransformerCount" not in skip_codes:
            existing = fields.get("futureMainTransformerCount")
            if existing is None or existing.value is None:
                future = self._future_main_transformer_count_from_document(ast)
                if future is not None:
                    value, evidence_text, source_type, meta = future
                    self._set_field(
                        fields, "futureMainTransformerCount", "主变远期台数", value, "台",
                        evidence_text, source_type=source_type, meta=meta,
                    )
        self._apply_electrical_primary_equivalents(ast, fields)

    def _apply_electrical_primary_equivalents(self, ast: DocumentAST, fields: dict[str, ParsedField]) -> None:
        """从主变设备行和接地方案中补充语义明确的独立指标。"""
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if "接入系统方案" not in text or "不宜作为" in text:
                continue
            selected = re.search(
                domain_regex(self, "electrical_primary", "search_013", r"([0-9]{2,3})\s*kV\s*(?:出线|线路)[^。；;]{0,40}?"
                r"接入\s*([\u4e00-\u9fffA-Za-z0-9]+?)\s*(?<![0-9])([0-9]{2,3})\s*kV\s*变\s*电站"),
                text, re.I,
            )
            if selected and selected.group(1) == selected.group(3):
                evidence = self._clean_text(selected.group(0))
                meta = {"resolver": "selected_grid_connection_scheme", "page": block.page, "sectionPath": list(block.section_path)}
                self._set_field(fields, "accessStationName", "接入站名称", f"{selected.group(2)}{selected.group(3)}kV变电站", None, evidence, source_type="paragraph", meta=meta)
                self._set_field(fields, "accessibleVoltage", "可接入电压", int(selected.group(1)), "kV", evidence, source_type="paragraph", meta=meta)
                break
        independent_rod = any("独立避雷针" in (block.text or "") for block in ast.blocks)
        rod_rows: list[tuple[DocumentTable, list[str]]] = []
        for table in ast.tables:
            if "电气一次" not in self._clean_text(table.caption or ""):
                continue
            for row in self._table_matrix(table):
                if len(row) > 4 and self._clean_text(row[1]) == "避雷针":
                    rod_rows.append((table, row))
                row_text = self._clean_text(" | ".join(row))
                if "主变压器" not in row_text or "型号" in row_text:
                    continue
                match = re.search(domain_regex(self, "electrical_primary", "search_014", r"\b(YN\s*[,，]\s*d\s*11|YN\s*[,，]\s*yn\s*0|Dyn\s*11)\b"), row_text, re.I)
                if match and (fields.get("connectionGroupType") is None or fields["connectionGroupType"].value is None):
                    self._set_field(
                        fields, "connectionGroupType", "主变压器接线组别",
                        re.sub(domain_regex(self, "electrical_primary", "sub_015", r"\s+"), "", match.group(1)).replace("，", ","), None, row_text,
                        source_type="table", meta={"resolver": "main_transformer_connection_group", "tableId": table.id},
                    )
                    break

        if independent_rod and len(rod_rows) == 1:
            table, row = rod_rows[0]
            quantity = self._normalize_table_cell(row[4])
            if isinstance(quantity, (int, float)) and 0 < quantity <= 10 and "H=" in " ".join(row):
                self._set_field(
                    fields, "independentLightningRodCount", "独立避雷针个数", quantity, "座",
                    self._clean_text(" | ".join(row)), source_type="table",
                    meta={"resolver": "independent_lightning_rod_equipment_row", "tableId": table.id},
                )

        if fields.get("groundingTransformerResistance") is None or fields["groundingTransformerResistance"].value is None:
            for block in self._body_blocks(ast):
                text = self._clean_text(block.text or "")
                if "接地变" not in text and not ("中性点" in text and "小电阻" in text):
                    continue
                match = re.search(domain_regex(self, "electrical_primary", "search_016", r"(?:阻值为|接地电阻(?:值|装置)?\s*(?:为|取|Rn\s*=)?|Rn\s*=)\s*([0-9]+(?:\.[0-9]+)?)\s*[Ω欧]"), text, re.I)
                if match:
                    self._set_field(
                        fields, "groundingTransformerResistance", "接地变接地电阻",
                        self._clean_number(float(match.group(1))), "Ω", text,
                        source_type="paragraph", meta={"resolver": "grounding_resistance_synonym", "sectionPath": list(block.section_path or ["电气一次"])},
                    )
                    break

    def _current_outgoing_line_from_primary_text(self, ast: DocumentAST) -> tuple[int, Any] | None:
        candidates = []
        pattern = re.compile(
            domain_regex(self, "electrical_primary", "compile_017", r"升压站\s*(\d{2,3})\s*kV\s*侧[^。；;\n]{0,60}?(\d+)\s*回\s*出线[^。；;\n]{0,40}?本期(?:一次)?建成"),
            re.IGNORECASE,
        )
        for block in self._body_blocks(ast):
            if "电气一次" not in " ".join(block.section_path or []):
                continue
            text = self._clean_text(block.text or "")
            for match in pattern.finditer(text):
                if int(match.group(1)) >= 66:
                    candidates.append((int(match.group(2)), block))
        return candidates[0] if len({value for value, _ in candidates}) == 1 else None

    def _future_main_transformer_count_from_document(
        self, ast: DocumentAST
    ) -> tuple[int, str, str, dict[str, Any]] | None:
        """优先采用明确的远期规划；仅在容量证实时推断两者相等。"""
        main: tuple[int, float, DocumentTable, str] | None = None
        for table in self._electrical_primary_equipment_tables(ast):
            matrix = self._table_matrix(table)
            header = next((row for row in matrix[:5] if "名称" in " ".join(row) and "数量" in " ".join(row)), [])
            name_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_004", ["名称", "名  称"])) if header else None
            quantity_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_005", ["数量", "数  量"])) if header else None
            spec_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_006", ["型号、规格及技术数据", "型号规格"])) if header else None
            name_index = 1 if name_index is None else name_index
            quantity_index = 4 if quantity_index is None else quantity_index
            spec_index = 2 if spec_index is None else spec_index
            for row_index, row in enumerate(matrix):
                label = self._clean_text(row[name_index] if name_index < len(row) else "")
                if label != "主变压器":
                    continue
                count = self._normalize_table_cell(row[quantity_index] if quantity_index < len(row) else "")
                spec = self._electrical_primary_equipment_block_text(matrix, row_index, name_index, spec_index)
                model = re.search(domain_regex(self, "electrical_primary", "search_018", r"\bSZ[A-Z0-9]*[-－]\s*(\d+(?:\.\d+)?)\s*/\s*\d{2,3}\b"), spec, re.I)
                if isinstance(count, (int, float)) and not isinstance(count, bool) and model:
                    main = (int(count), float(model.group(1)), table, self._clean_text(" | ".join(row)))
                    break
            if main is not None:
                break

        blocks = self._electrical_primary_text_blocks(ast)
        if not blocks:
            return None
        current_count = main[0] if main else None
        for block in blocks:
            text = self._clean_text(block.text or "")
            if "远期" not in text or "主变" not in text or (re.search(domain_regex(self, "electrical_primary", "search_019", r"方案[一二三四\d]"), text) and not re.search(domain_regex(self, "electrical_primary", "search_020", r"选定|推荐|最终采用"), text)):
                continue
            for segment in re.split(domain_regex(self, "electrical_primary", "split_021", r"[。；;\n]"), text):
                if "远期" not in segment or "主变" not in segment:
                    continue
                increase = re.search(domain_regex(self, "electrical_primary", "search_022", r"远期[^。；;]{0,35}?(?:新增|增加|扩建)\s*([1-9]\d?)\s*台[^。；;]{0,20}?主变"), segment)
                if increase and current_count is not None:
                    count = current_count + int(increase.group(1))
                else:
                    match = re.search(domain_regex(self, "electrical_primary", "search_023", r"远期[^。；;]{0,40}?([1-9]\d?)\s*台[^。；;]{0,20}?主变"), segment) or re.search(
                        domain_regex(self, "electrical_primary", "search_024", r"主变[^。；;]{0,25}?远期[^。；;]{0,30}?([1-9]\d?)\s*台"), segment
                    ) or re.search(domain_regex(self, "electrical_primary", "search_025", r"远期[^。；;]{0,35}?([1-9]\d?)\s*[×xX]\s*\d+(?:\.\d+)?\s*MVA[^。；;]{0,15}?主变"), segment, re.I)
                    if match is None:
                        continue
                    count = int(match.group(1))
                return count, self._clean_text(segment), "paragraph", {
                    "resolver": "future_main_transformer_explicit_plan",
                    "sectionPath": list(block.section_path or ["电气一次"]),
                    "blockId": block.id,
                }

        if main is None:
            return None
        current_count, unit_capacity_kva, table, row_text = main
        capacities: list[tuple[float, str, list[str]]] = []
        for block in blocks:
            text = self._clean_text(block.text or "")
            for match in re.finditer(
                domain_regex(self, "electrical_primary", "finditer_026", r"(?:本项目|本工程|项目|工程)[^。；;]{0,35}?(?:规划)?(?:总装机容量|总容量|建设规模)\s*(?:为|约为|达)?\s*(\d+(?:\.\d+)?)\s*(MW|万千瓦)"),
                text, re.I,
            ):
                capacity_mw = float(match.group(1)) * (10 if match.group(2) == "万千瓦" else 1)
                capacities.append((capacity_mw, text, list(block.section_path or ["电气一次"])))
        if not capacities or len({round(value, 3) for value, _, _ in capacities}) != 1:
            return None
        capacity_mw, capacity_text, section_path = capacities[0]
        if abs(current_count * unit_capacity_kva / 1000 - capacity_mw) > max(1, capacity_mw * 0.01):
            return None
        return current_count, f"{row_text}；{capacity_text}", "table", {
            "resolver": "future_main_transformer_capacity_consistency",
            "sectionPath": section_path,
            "tableId": table.id,
            "calculation": f"{current_count}×{unit_capacity_kva:g}kVA={capacity_mw:g}MW",
        }

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
            if not re.search(domain_regex(self, "electrical_primary", "search_027", r"110\s*kV\s*升压站"), target_text, flags=re.IGNORECASE):
                continue
            header_index = self._station_scale_header_row_index(matrix)
            header = matrix[header_index]
            name_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_007", ["名称", "项目", "项目名称"]))
            current_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_008", ["本期规模", "本期"]))
            future_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_009", ["远期规模", "远期"]))
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
        compact = re.sub(domain_regex(self, "electrical_primary", "sub_028", r"\s+"), "", self._clean_text(text)).lower()
        return bool(re.search(domain_regex(self, "electrical_primary", "search_029", r"110kv(?:出线|回路数|出线回数)"), compact))

    def _station_outgoing_line_count_value(self, value: Any) -> Any:
        text = self._clean_text(str(value or ""))
        if not text:
            return None
        match = re.search(domain_regex(self, "electrical_primary", "search_030", r"([0-9]+(?:\.\d+)?)\s*回"), text)
        if match:
            return self._normalize_scalar(match.group(1))
        chinese_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        match = re.search(domain_regex(self, "electrical_primary", "search_031", r"([一二两三四五六七八九十])\s*回"), text)
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
                "value": "model",
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
            name_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_010", ["名称", "名 称", "设备名称"]))
            spec_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_011", ["型号、规格及技术数据", "型号规格及技术数据", "型号及规格", "型号与规格", "规格"]))
            if name_index is None:
                name_index = 1 if len(header) > 1 else 0
            if spec_index is None:
                spec_index = 2 if len(header) > 2 else None
            if spec_index is None:
                continue
            has_header = any(keyword in self._clean_text(" ".join(header)) for keyword in ("型号", "规格", "技术数据", "名称"))
            data_start_index = 1 if has_header else 0
            unit_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_012", ["单位"]))
            quantity_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_013", ["数量"]))
            if unit_index is None and not has_header and len(header) > 3:
                unit_index = 3
            if quantity_index is None and not has_header and len(header) > 4:
                quantity_index = 4
            remark_index = self._find_header_index(header, domain_strings(self, "electrical_primary", "list_014", ["备注"]))
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
                elif value_kind == "model":
                    raw_spec = self._table_index_value(row, spec_index)
                    value = self._gis_model_from_spec(raw_spec) or self._gis_model_from_spec(name_cell)
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

    @staticmethod
    def _gis_model_from_spec(value: Any) -> str | None:
        """仅提取显式型号；额定电压、电流和开断容量属于技术规格。"""
        text = str(value or "").strip()
        match = re.search(r"(?:^|型号\s*(?:为|是)?\s*[:：]?\s*)([A-Z][A-Z0-9]{1,12}[-－]\d{2,4}(?:/[A-Z0-9.]+)?)\b", text, re.IGNORECASE)
        return match.group(1).replace("－", "-") if match else None

    def _normalize_equipment_label(self, value: Any) -> str:
        text = self._clean_text(str(value or "")).lower()
        text = text.replace("（", "(").replace("）", ")").replace("×", "x")
        return re.sub(domain_regex(self, "electrical_primary", "sub_032", r"[^0-9a-zA-Z\u4e00-\u9fa5]+"), "", text)

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
        text = re.sub(domain_regex(self, "electrical_primary", "sub_033", r"\s+"), "", text)
        text = text.replace("＋", "+")
        if text.startswith("+") or text.startswith("-"):
            text = "±" + text[1:]
        if re.fullmatch(domain_regex(self, "electrical_primary", "fullmatch_034", r"\d+(?:\.\d+)?"), text):
            return text
        if re.fullmatch(domain_regex(self, "electrical_primary", "fullmatch_035", r"\d+(?:\.\d+)?(?:kVA|Mvar)"), text, flags=re.IGNORECASE):
            return re.sub(domain_regex(self, "electrical_primary", "sub_036", r"kva$"), "kVA", text, flags=re.IGNORECASE).replace("mvar", "Mvar")
        return text

    def _normalize_electrical_spec_text(self, value: str) -> str:
        text = self._normalize_text_value(value)
        text = re.sub(domain_regex(self, "electrical_primary", "sub_037", r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])"), "", text)
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
                    domain_strings(self, "electrical_primary", "list_015", [
                        r"备用电源引自站外\s*10\s*kV\s*线路[^。；;\n]{0,80}?容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                        r"选用\s*1\s*台容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)\s*的\s*外来变压器",
                    ]),
                ),
                None,
                ["站用变", "10kV"],
            ),
            "groundingTransformerCapacity35kv": (
                "35kV接地变容量",
                self._first_matching_text(
                    combined,
                    domain_strings(self, "electrical_primary", "list_016", [
                        r"配置\s*1\s*台容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)\s*接地变",
                        r"接地变(?:成套装置)?\s*DKSC-([0-9]+(?:\.[0-9]+)?\s*kVA?)[-/]35\s*kV",
                        r"DKSC-([0-9]+(?:\.[0-9]+)?)(?:\s*kVA)?[-/]35\s*kV",
                    ]),
                ),
                None,
                ["接地变"],
            ),
            "groundingStationTransformerCapacity35kv": (
                "35kV接地变兼站用变容量",
                self._first_matching_text(
                    combined,
                    domain_strings(self, "electrical_primary", "list_017", [
                        r"兼带站用变[^。；;\n]{0,30}?站用变容量为\s*([0-9]+(?:\.[0-9]+)?\s*kVA)",
                        r"DKSC-[0-9]+(?:\.[0-9]+)?\s*kVA-([0-9]+(?:\.[0-9]+)?\s*kVA)[-/]35\s*kV",
                        r"DKSC-[0-9]+(?:\.[0-9]+)?(?:\s*kVA)?-([0-9]+(?:\.[0-9]+)?\s*kVA)",
                    ]),
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
                    domain_strings(self, "electrical_primary", "list_018", [
                        r"选用\s*(一组\s*220\s*V[、,，/]\s*250\s*Ah\s*阀控式\s*密封铅酸蓄电池组)",
                        r"(一组\s*220\s*V[、,，/]\s*250\s*Ah\s*阀控式\s*密封铅酸蓄电池组)",
                    ]),
                ),
                None,
                ["220V", "蓄电池"],
            ),
            "upsPowerConfiguration": (
                "UPS电源配置",
                self._ups_configuration_from_blocks(ast) or self._first_matching_text(
                    combined,
                    domain_strings(self, "electrical_primary", "list_019", [
                        r"设置\s*([0-9]+\s*套\s*[0-9]+(?:\.[0-9]+)?\s*kVA\s*双冗余互为备用[^。；;\n]{0,30}?UPS)",
                        r"([0-9]+\s*套\s*[0-9]+(?:\.[0-9]+)?\s*kVA\s*双冗余互为备用)",
                    ]),
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
        labelled_box_specs = self._electrical_box_transformer_labelled_specs(combined)
        if labelled_box_specs:
            capacities = [item["capacity"] for item in labelled_box_specs]
            specs["boxTransformerCapacity"] = (
                "箱变容量", self._one_or_many(capacities), "kVA", ["箱式变电站", "额定容量"]
            )
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, (name, value, unit, evidence_keywords) in specs.items():
            if code in skip_codes or value in (None, "", [], {}):
                continue
            if code in {
                "electricalPrimaryBoxTransformerModel",
                "electricalPrimaryBoxTransformerVoltageLevel",
                "electricalPrimaryBoxTransformerCapacity",
                "boxTransformerCapacity",
            } and isinstance(value, list):
                value = [self._normalize_scalar(self._normalize_electrical_text_value(str(item))) for item in value]
                evidence_value = value[0]
            else:
                value = self._normalize_scalar(self._normalize_electrical_text_value(str(value)))
                evidence_value = value
            evidence_text = self._field_evidence_text_for_value(ast, evidence_value, evidence_keywords)
            if labelled_box_specs and code in {
                "electricalPrimaryBoxTransformerModel",
                "electricalPrimaryBoxTransformerVoltageLevel",
                "electricalPrimaryBoxTransformerCapacity",
                "boxTransformerCapacity",
            }:
                evidence_text = "\n".join(item["evidence"] for item in labelled_box_specs)
            overrides[code] = (
                name,
                value,
                unit,
                evidence_text,
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
        supplemental = self._electrical_box_transformer_labelled_specs(combined)
        if supplemental and (box_model is None or len(supplemental) > 1):
            box_model = self._one_or_many([item["model"] for item in supplemental])
            box_capacity = self._one_or_many([item["capacity"] for item in supplemental])
            box_voltage = self._one_or_many([item["voltage"] for item in supplemental])
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

    def _one_or_many(self, values: list[Any]) -> Any:
        return values[0] if len(values) == 1 else values

    def _electrical_box_transformer_labelled_specs(self, text: str) -> list[dict[str, Any]]:
        """补充抽取带标签且重复出现的箱变型号参数。"""
        model_pattern = re.compile(
            domain_regex(self, "electrical_primary", "compile_038", r"(?:变压器)?型号\s*(?:为|是|[:：])?\s*"
            r"(?P<model>[A-Z][A-Z0-9.-]{1,30}/[0-9]+(?:\.[0-9]+)?)"),
            re.I,
        )
        box_pattern = re.compile(domain_regex(self, "electrical_primary", "compile_039", r"箱式变电站|箱式变压器|箱变|机组变压器"))
        other_pattern = re.compile(domain_regex(self, "electrical_primary", "compile_040", r"主变压器|接地变(?:压器)?|站用变(?:压器)?"))
        matches = list(model_pattern.finditer(text))
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, match in enumerate(matches):
            prefix = text[max(0, match.start() - 650):match.start()]
            box_mentions = list(box_pattern.finditer(prefix))
            if not box_mentions:
                continue
            other_mentions = list(other_pattern.finditer(prefix))
            if other_mentions and other_mentions[-1].start() > box_mentions[-1].start():
                continue
            model = match.group("model")
            if model in seen:
                continue
            seen.add(model)
            end = min(match.end() + 220, matches[index + 1].start() if index + 1 < len(matches) else len(text))
            segment = text[match.end():end]
            segment = re.split(domain_regex(self, "electrical_primary", "split_041", r"[（(]\s*\d+\s*[）)]\s*(?=[\u4e00-\u9fa5])"), segment, maxsplit=1)[0]
            end = match.end() + len(segment)
            capacity_match = re.search(domain_regex(self, "electrical_primary", "search_042", r"额定容量\s*[:：为是]?\s*([0-9]+(?:\.[0-9]+)?)\s*(MVA|kVA|千伏安)"), segment, re.I)
            voltage_match = re.search(domain_regex(self, "electrical_primary", "search_043", r"额定电压\s*[:：为是]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:kV|千伏)"), segment, re.I)
            inferred_capacity, inferred_voltage = self._electrical_box_transformer_capacity_voltage(model)
            capacity = inferred_capacity
            if capacity_match:
                capacity = self._normalize_scalar(capacity_match.group(1))
                if capacity_match.group(2).upper() == "MVA":
                    capacity = self._normalize_scalar(float(capacity) * 1000)
            voltage = self._normalize_scalar(voltage_match.group(1)) if voltage_match else inferred_voltage
            result.append({
                "model": model, "capacity": capacity, "voltage": voltage,
                "evidence": self._clean_text(text[match.start():end]),
            })
        return result

    def _lightning_rod_height_from_ast(self, ast: DocumentAST, kind: str) -> Any:
        electrical_text = "\n".join(self._clean_text(block.text or "") for block in self._electrical_primary_text_blocks(ast))
        value = self._lightning_rod_height_from_text(electrical_text, kind)
        if value is not None:
            return value
        all_text = "\n".join(self._clean_text(block.text or "") for block in self._body_blocks(ast))
        value = self._lightning_rod_height_from_text(all_text, kind)
        if value is not None or kind != "independent" or "独立避雷针" not in all_text:
            return value
        # 清单只写“避雷针”时，正文明确设备类型且仅有一处规格才可归入独立避雷针。
        heights = {
            float(match.group(1))
            for table in ast.tables if "电气一次" in self._clean_text(table.caption or "")
            for row in self._table_matrix(table)
            if "避雷针" in self._clean_text(row[1] if len(row) > 1 else "")
            for match in re.finditer(domain_regex(self, "electrical_primary", "finditer_044", r"\bH\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*m\b"), " ".join(row), re.I)
        }
        return self._clean_number(next(iter(heights))) if len(heights) == 1 else None

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
        match = re.search(domain_regex(self, "electrical_primary", "search_045", r"-([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)"), model)
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
        match = re.search(domain_regex(self, "electrical_primary", "search_046", r"([0-9]+(?:\.[0-9]+)?)\s*km"), text, flags=re.IGNORECASE)
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
            match = re.search(domain_regex(self, "electrical_primary", "search_047", r"([0-9]{2,3}\s*kV[^，。；;\n]{0,20}?升压站|[\u4e00-\u9fa5A-Za-z0-9]+升压站)"), text)
            station = self._clean_text(match.group(1)).replace(" ", "") if match else ""
            return f"扩建-{station}" if station else "扩建"
        return None

    def _electrical_expanded_substation_name(self, ast: DocumentAST) -> str | None:
        """从同一局部语句中提取扩建或共用升压站名称。"""
        for block in self._electrical_primary_text_blocks(ast):
            text = self._clean_text(block.text or "")
            for clause in re.split(domain_regex(self, "electrical_primary", "split_048", r"[。；;\n]"), text):
                if "升压站" not in clause or not any(keyword in clause for keyword in ("扩建", "共用一座")):
                    continue
                station = self._expanded_substation_from_clause(clause)
                if station:
                    return f"扩建-{station}"
        return None

    def _expanded_substation_from_clause(self, clause: str) -> str | None:
        trigger_matches = list(re.finditer(domain_regex(self, "electrical_primary", "finditer_049", r"扩建|共用一座"), clause))
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

        # 优先采用带电压等级的站名，因为其文本边界更可靠。
        voltage_matches = list(
            re.finditer(domain_regex(self, "electrical_primary", "finditer_050", r"[0-9]{2,3}\s*kV[^，,。；;\n]{0,24}?升压站"), value, flags=re.IGNORECASE)
        )
        if voltage_matches:
            match = voltage_matches[-1] if prefer_tail else voltage_matches[0]
            return re.sub(domain_regex(self, "electrical_primary", "sub_051", r"\s+"), "", match.group(0))

        value = re.sub(
            domain_regex(self, "electrical_primary", "sub_052", r"^(?:本期|本工程|本项目|工程|项目|拟|计划|将|对|与|同|和|现有|既有|原有|已建成?的?|建设|进行|实施|一座|[0-9]+座)+"),
            "",
            value,
        )
        if prefer_tail:
            match = re.search(domain_regex(self, "electrical_primary", "search_053", r"([\u4e00-\u9fa5A-Za-z0-9·#（）()_-]{1,30}升压站)$"), value)
        else:
            match = re.match(domain_regex(self, "electrical_primary", "match_054", r"([\u4e00-\u9fa5A-Za-z0-9·#（）()_-]{1,30}?升压站)"), value)
        if not match:
            return None
        return re.sub(domain_regex(self, "electrical_primary", "sub_055", r"\s+"), "", match.group(1))

    def _substation_voltage_level_from_ast(self, ast: DocumentAST) -> Any:
        text = "\n".join(self._clean_text(block.text or "") for block in self._electrical_primary_text_blocks(ast))
        pattern = r"([0-9]{2,3})\s*kV\s*升压站|升压站[^。；;\n]{0,40}?([0-9]{2,3})\s*kV"
        # 过短的关键词窗口可能在真正的升压站电压之前截断。
        for candidate in (self._keyword_window(text, ["电气主接线", "升压站电气主接线", "升压站"], 180), text):
            if not candidate:
                continue
            match = re.search(pattern, candidate, flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group(1) or match.group(2))
        return None

    def _normalize_electrical_text_value(self, value: str) -> str:
        value = self._normalize_text_value(value)
        if "UPS" in value and "\u53cc\u5197\u4f59\u4e92\u4e3a\u5907\u7528" in value:
            value = re.split(domain_regex(self, "electrical_primary", "split_056", r"\u7684\u4ea4\u6d41|\uff08UPS|\(UPS"), value, maxsplit=1)[0]
        value = re.sub(domain_regex(self, "electrical_primary", "sub_057", r"\s+"), "", value)
        value = re.sub(domain_regex(self, "electrical_primary", "sub_058", r"^([0-9]+(?:\.[0-9]+)?)kVA?$"), r"\1kVA", value, flags=re.IGNORECASE)
        value = re.sub(domain_regex(self, "electrical_primary", "sub_059", r"^([±+\-]?[0-9]+(?:\.[0-9]+)?)Mvar$"), r"\1Mvar", value, flags=re.IGNORECASE)
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
                    score = 5 if re.search(domain_regex(self, "electrical_primary", "search_060", r"10\s*kV\s*站用变"), nearby, flags=re.IGNORECASE) else 1
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
            match = re.search(domain_regex(self, "electrical_primary", "search_061", r"((?:线变组|单母线(?:分段)?)接线(?:型式|方式)?)"), text)
            if match:
                return match.group(1)
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
