"""Foundation, road, earthwork and land extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import ParsedField


class CivilRulesMixin:
    def _road_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        return self._road_original_table_from_document(ast)

    def _road_original_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        patterns = [
            r"进站道路.*(?:主要工程数量表|工程数量表|主要工程量表)",
            r"道路.*主要工程数量表",
            r"(?:\d+(?:\.\d+)*(?:-\s*\d+)?\.?)\s*进站道路.*(?:主要工程数量表|工程数量表|主要工程量表)",
        ]
        return self._original_captioned_table_by_regex_from_document(ast, "roadTechnical", patterns, include_table_text=False)

    def _road_combined_row_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        text = "\n".join(
            self._clean_text(block.text or "")
            for block in ast.blocks
            if block.text and ("道路" in block.text or "路基" in block.text or "路面" in block.text)
        )
        if not text:
            return None
        row = {
            "accessRoadLength": self._first_number_after_pattern(text, r"进站道路\D{0,8}([0-9]+(?:\.\d+)?)\s*km"),
            "accessRoadSubgradeWidth": self._first_number_after_pattern(text, r"进站道路[^\n。；;]{0,40}?路基宽\s*([0-9]+(?:\.\d+)?)\s*m"),
            "accessRoadPavementWidth": self._first_number_after_pattern(text, r"进站道路[^\n。；;]{0,50}?路面宽\s*([0-9]+(?:\.\d+)?)\s*m"),
            "siteRoadLength": self._first_number_after_pattern(text, r"场内道路\s*([0-9]+(?:\.\d+)?)\s*km"),
            "newRoadLength": self._first_number_after_pattern(text, r"新建道路\s*([0-9]+(?:\.\d+)?)\s*km"),
            "rebuiltRoadLength": self._first_number_after_pattern(text, r"改建道路\s*([0-9]+(?:\.\d+)?)\s*km"),
            "subgradeWidth": self._first_number_after_pattern(text, r"路基设计宽度为\s*([0-9]+(?:\.\d+)?)\s*m"),
            "pavementWidth": self._first_number_after_pattern(text, r"检修道路路基\D{0,12}路面宽\s*([0-9]+(?:\.\d+)?)\s*m") or self._last_number_after_pattern(text, r"路面宽\s*([0-9]+(?:\.\d+)?)\s*m"),
        }
        return row if any(value is not None for value in row.values()) else None

    def _supplement_road_lengths_from_matrix(self, matrix: list[list[str]], values: dict[str, Any]) -> None:
        if not matrix:
            return
        header = matrix[0]
        header_text = " | ".join(header)
        if "道路长度" in self._matrix_text(matrix) and ("场内新建" in header_text or "场区新建" in header_text):
            new_index = self._find_header_index(header, ["场内新建道路", "场区新建道路", "新建道路"])
            rebuilt_index = self._find_header_index(header, ["场内改建道路", "场内扩建道路", "场区改建道路", "改建道路", "扩建道路"])
            for row in matrix[1:]:
                label = self._row_label(row)
                if "道路长度" not in label or not any("km" in cell for cell in row):
                    continue
                if values.get("newRoadLength") is None and new_index is not None and new_index < len(row):
                    values["newRoadLength"] = self._normalize_table_cell(row[new_index])
                if values.get("rebuiltRoadLength") is None and rebuilt_index is not None and rebuilt_index < len(row):
                    values["rebuiltRoadLength"] = self._normalize_table_cell(row[rebuilt_index])
        if values.get("accessRoadLength") is not None:
            return
        for row in matrix[1:]:
            label = self._row_label(row)
            if "进站道路" not in label and "进升压站道路" not in label:
                continue
            if not re.search(r"（\s*m\s*）|\(\s*m\s*\)|\|\s*m\s*\|", " | ".join(row), flags=re.IGNORECASE):
                continue
            value = self._last_numeric_cell(row)
            if isinstance(value, (int, float)):
                values["accessRoadLength"] = value
                return

    def _wind_foundation_construction_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = {
            "foundationType": None,
            "pileDiameter": None,
            "pileRingCount": None,
            "pilesPerRing": None,
            "c20Concrete": None,
            "c40Concrete": None,
            "rebar": None,
            "steel": None,
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            caption = table.caption or self._caption_before_table(ast, table)
            section_text = " / ".join(table.section_path)
            if not any(keyword in text or keyword in caption or keyword in section_text for keyword in ("风机基础", "风电机组基础", "机组基础工程")):
                continue
            wind_rows = self._wind_foundation_rows(matrix) or matrix
            row["foundationType"] = row["foundationType"] or self._text_by_row_label(matrix, ["基础形式", "地基处理措施"])
            row["c20Concrete"] = row["c20Concrete"] or self._value_by_row_label(wind_rows, ["垫层混凝土 C20", "垫层混凝土C20", "垫层及散水混凝土C20"])
            row["c40Concrete"] = row["c40Concrete"] or self._value_by_row_label(wind_rows, ["基础混凝土 C40", "基础混凝土C40", "基础混凝土 C45", "基础混凝土C45", "基础承台C40混凝土"])
            row["rebar"] = row["rebar"] or self._value_by_row_label(wind_rows, ["钢筋制作", "钢筋工程量", "钢筋制作与安装"])
            row["steel"] = row["steel"] or self._value_by_row_label(wind_rows, ["钢结构制作", "钢结构制作与安装"])
        return self._schema_row_table("windFoundationConstruction", row) if any(value is not None for value in row.values()) else None

    def _wind_foundation_rows(self, matrix: list[list[str]]) -> list[list[str]]:
        rows: list[list[str]] = []
        active = False
        for row in matrix:
            code = row[0].strip() if row else ""
            text = " ".join(row)
            if any(keyword in text for keyword in ("风电机组基础工程", "风机基础工程", "机组基础工程")):
                active = True
                rows.append(row)
                continue
            if active and re.match(r"^(?:1\.2|2|二|三|四)\b", code):
                break
            if active:
                rows.append(row)
        return rows

    def _wind_foundation_technical_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        """从风机基础断面/尺寸表中提取标准化基础参数表。

        Args:
            ast: 已完成结构和章节识别的文档 AST。

        Returns:
            dict[str, Any] | None: 命中的风机基础参数表；未命中时返回 None。
        """
        row = {
            "capBottomRadius": None,
            "buriedDepth": None,
            "groundDiameter": None,
            "topRadius": None,
            "columnRadius": None,
            "outerEdgeHeight": None,
            "coneHeight": None,
            "columnHeight": None,
            "pileCount": None,
            "pileDiameter": None,
            "pileRingCount": None,
            "averagePileLength": None,
            "expandedBottomDiameter": None,
        }
        mapping = {
            "groundDiameter": ["圆形基础底面直径", "承台底板直径", "圆形基础地面直径"],
            "topRadius": ["基础圆台顶面半径", "顶面半径"],
            "columnRadius": ["承台台柱半径", "台柱半径"],
            "outerEdgeHeight": ["基础底板外缘高度", "承台基础边缘外缘高度"],
            "coneHeight": ["基础底板圆台高度", "承台基础底板棱台高度"],
            "columnHeight": ["台柱高度"],
            "buriedDepth": ["基础埋深"],
            "pileCount": ["桩数"],
            "pileDiameter": ["桩身直径", "桩截面外径", "桩径"],
            "pileRingCount": ["桩圈数"],
            "averagePileLength": ["平均桩长", "桩长"],
            "expandedBottomDiameter": ["底部扩底直径"],
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            caption = "\n".join(
                part
                for part in [
                    table.caption or "",
                    self._caption_before_table(ast, table),
                    str(table.meta.get("best_title") or "") if isinstance(table.meta, dict) else "",
                ]
                if part
            )
            context = f"{caption}\n{text}"
            if not any(keyword in context for keyword in ("基础断面表", "基础尺寸及参数表", "基础埋深", "承台底板直径", "圆形基础底面直径")):
                continue
            radius_value = self._foundation_radius_value(matrix)
            if radius_value is not None:
                row["capBottomRadius"] = row["capBottomRadius"] or radius_value
            for key, aliases in mapping.items():
                if row[key] is None:
                    row[key] = self._wind_foundation_profile_value(matrix, aliases)
                if row[key] is None:
                    row[key] = self._value_by_row_label(matrix, aliases)
            row["groundDiameter"] = self._meters_from_possible_mm(row["groundDiameter"])
            if row["groundDiameter"] is not None and radius_value is not None:
                row["groundDiameter"] = radius_value
            elif row["groundDiameter"] is not None and row["capBottomRadius"] is None:
                row["capBottomRadius"] = self._half_length(row["groundDiameter"])
            row["pileDiameter"] = self._meters_from_possible_mm(row["pileDiameter"])
            row["averagePileLength"] = self._meters_from_possible_mm(self._leading_number_value(row["averagePileLength"]))
        return self._schema_row_table("windFoundationTechnical", row) if any(value is not None for value in row.values()) else None

    def _wind_foundation_profile_value(self, matrix: list[list[str]], aliases: list[str]) -> Any:
        """从风机基础断面三列表中按“项目/单位/数值”读取主值。

        Args:
            matrix: 原始表格文本矩阵。
            aliases: 目标项目名别名。

        Returns:
            Any: 命中行的数值；未命中时返回 None。
        """
        for row in matrix:
            label = self._clean_text(row[0] if row else "")
            if not any(alias in label for alias in aliases):
                continue
            if len(row) >= 3:
                value = self._normalize_table_cell(row[2])
                return self._leading_number_value(value)
            if len(row) >= 2:
                value = self._normalize_table_cell(row[-1])
                return self._leading_number_value(value)
        return None

    def _leading_number_value(self, value: Any) -> Any:
        """从“22（含扩底部分 1.5m）”这类单元格中取开头主数值。

        Args:
            value: 表格单元格归一化后的值。

        Returns:
            Any: 开头是数字时返回该数字，否则返回原值。
        """
        if not isinstance(value, str):
            return value
        match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value.replace(",", ""))
        if not match:
            return value
        return self._clean_number(float(match.group(1)))

    def _foundation_radius_value(self, matrix: list[list[str]]) -> Any:
        for row in matrix:
            label = self._row_label(row)
            if not any(alias in label for alias in ("基础承台底面半径", "底面半径", "圆形基础地面直径")):
                continue
            if "半径" not in label and not re.search(r"\bR\b|R（|R\(", label):
                continue
            value = self._value_by_row_label([row], [label])
            if value is not None:
                return self._meters_from_possible_mm(value)
        return None

    def _meters_from_possible_mm(self, value: Any) -> Any:
        if isinstance(value, (int, float)) and value > 100:
            return self._clean_number(float(value) / 1000)
        return value

    def _box_foundation_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = {"concreteGrade": None, "c30Concrete": None, "c20Concrete": None, "rebarInstallation": None, "steelInstallation": None, "rebarQuantity": None}
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            caption = f"{table.caption or ''}\n{self._caption_before_table(ast, table)}"
            context = f"{caption}\n{text}"
            if not any(keyword in context for keyword in ("机组变压器基础", "箱变基础", "箱式变")):
                continue
            box_rows = self._box_foundation_rows(matrix)
            if not box_rows:
                continue
            source = box_rows
            is_direct_quantity_table = bool(matrix and any("工程量" in cell for cell in matrix[0]))
            row["concreteGrade"] = row["concreteGrade"] or self._box_foundation_concrete_grade(source)
            row["c30Concrete"] = row["c30Concrete"] or self._value_by_row_label(source, ["基础混凝土C30", "混凝土 C30", "混凝土C30", "混凝土 C25", "混凝土C25", "混凝土（C25）", "混凝土（C30）", "混凝土量（C30）", "混凝土量（C25）", "基层混凝土量"])
            row["c20Concrete"] = row["c20Concrete"] or self._value_by_row_label(source, ["垫层混凝土", "垫层混凝土C20", "垫层混凝土 C20"])
            row["rebarInstallation"] = row["rebarInstallation"] or self._value_by_row_label(source, ["钢筋制作与安装", "基础钢筋", "钢筋（", "钢筋"])
            row["steelInstallation"] = row["steelInstallation"] or self._value_by_row_label(source, ["铁件制作安装", "钢结构制作与安装"])
            if is_direct_quantity_table and row["c30Concrete"] is not None and row["rebarInstallation"] is not None:
                return self._box_foundation_result_table(row)
        return self._box_foundation_result_table(row) if any(value is not None for key, value in row.items() if key != "concreteGrade") else None

    def _box_foundation_concrete_grade(self, rows: list[list[str]]) -> str | None:
        text = self._matrix_text(rows)
        match = re.search(r"C\s*([0-9]{2})", text, flags=re.IGNORECASE)
        return f"C{match.group(1)}" if match else None

    def _box_foundation_result_table(self, row: dict[str, Any]) -> dict[str, Any]:
        grade = row.get("concreteGrade") or "C30"
        header_pairs: list[tuple[str, str]] = []
        output_row: dict[str, Any] = {}
        if row.get("c30Concrete") is not None:
            header_pairs.append(("c30Concrete", f"混凝土量（{grade}）【m³】"))
            output_row["c30Concrete"] = row.get("c30Concrete")
        if row.get("c20Concrete") is not None:
            header_pairs.append(("c20Concrete", "垫层混凝土量（C20）【m³】"))
            output_row["c20Concrete"] = row.get("c20Concrete")
        if row.get("rebarInstallation") is not None:
            rebar_name = "钢筋工程量【t】" if row.get("c20Concrete") is not None or grade == "C25" else "钢筋制作与安装【t】"
            header_pairs.append(("rebarInstallation", rebar_name))
            output_row["rebarInstallation"] = row.get("rebarInstallation")
        if row.get("steelInstallation") is not None and row.get("c20Concrete") is None:
            header_pairs.append(("steelInstallation", "钢结构制作与安装【t】"))
            output_row["steelInstallation"] = row.get("steelInstallation")
        if row.get("rebarQuantity") is not None:
            header_pairs.append(("rebarQuantity", "钢筋工程量【t】"))
            output_row["rebarQuantity"] = row.get("rebarQuantity")
        return {
            "key": "boxFoundationTechnical",
            "name": "箱变基础指标表",
            "columns": [name for _, name in header_pairs],
            "columnKeys": [key for key, _ in header_pairs],
            "index": [0] if header_pairs else [],
            "data": [[self._empty_to_none(output_row.get(key)) for key, _ in header_pairs]] if header_pairs else [],
        }

    def _box_foundation_rows(self, matrix: list[list[str]]) -> list[list[str]]:
        rows: list[list[str]] = []
        active = False
        if matrix and any("工程量" in cell for cell in matrix[0]):
            text = self._matrix_text(matrix)
            if "混凝土" in text and "钢筋" in text:
                return matrix
        for row in matrix:
            code = row[0].strip() if row else ""
            text = " ".join(row)
            if "机组变压器基础" in text or "箱变基础" in text:
                active = True
                continue
            if active and re.match(r"^(?:1\.3|2|二|三|四)\b", code):
                break
            if active:
                rows.append(row)
        return rows

    def _substation_civil_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            table_text = self._matrix_text(matrix)
            header_text = " | ".join(matrix[0])
            target_text = f"{caption}\n{section_caption}\n{header_text}\n{table_text[:300]}"
            is_target_caption = self._looks_like_substation_civil_caption(target_text)
            is_target_header = "总占地面积" in header_text and "围墙内占地面积" in header_text
            if not is_target_caption and not (is_target_header and ("升压站" in target_text or "土建" in target_text)):
                continue
            columns = matrix[0]
            data_rows = [row for row in matrix[1:] if any(cell.strip() for cell in row)]
            if not data_rows:
                continue
            data = [[self._normalize_scalar(cell) for cell in row] for row in data_rows]
            cell_sources = []
            for source_row_index, row in enumerate(matrix[1:], start=1):
                if not any(cell.strip() for cell in row):
                    continue
                cell_sources.append([
                    self._table_cell_source(
                        table,
                        source_row_index,
                        column_index,
                        "按土建升压站原表整表透传。",
                        resolver="substation_civil_table_passthrough",
                    ) if column_index < len(row) and row[column_index].strip() else None
                    for column_index in range(len(columns))
                ])
            result = {
                "key": "substationCivil",
                "name": caption or self._section_path_caption(table) or self.table_output_headers.get("substationCivil", {}).get("name", "substationCivil"),
                "columns": columns,
                "columnKeys": [f"col_{index}" for index in range(len(columns))],
                "index": list(range(len(data))),
                "data": data,
                "_sourceTable": {"tableId": table.id, "order": table.order, "caption": caption or self._section_path_caption(table), "sectionPath": table.section_path},
            }
            if any(any(source is not None for source in row) for row in cell_sources):
                result["_cellSources"] = cell_sources
            return result
        return None

    def _looks_like_substation_civil_caption(self, text: str) -> bool:
        patterns = [
            r"升压站\s*主要\s*土建\s*工程量表",
            r"土建\s*主要\s*工程量表",
            r"升压站\s*土建\s*清单",
            r"(?:8\.6-3|9\.7-1|7\.6\.6)\s*\.?.*(?:升压站.*土建|土建.*工程量|土建清单)",
        ]
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _substation_total_area_from_text(self, text: str) -> Any:
        patterns = [
            r"升压站总占地面积(?:为|约|：|:)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m2|㎡|平方米)",
            r"升压站(?:红线)?占地面积(?:为|约|：|:)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m2|㎡|平方米)",
        ]
        for pattern in patterns:
            value = self._first_matching_number(text, [pattern])
            if isinstance(value, (int, float)) and value > 1000:
                return value
        return None

    def _substation_total_area_from_matrix(self, matrix: list[list[str]]) -> Any:
        header = matrix[0] if matrix else []
        area_index = self._find_header_index(header, ["面积", "占地"])
        for row in matrix[1:]:
            label = " ".join(row[:2])
            if not any(alias in label for alias in ("升压站总占地", "总占地面积", "110kV升压站", "升压站占地")):
                continue
            value = self._normalize_table_cell(row[area_index]) if area_index is not None and area_index < len(row) else self._last_numeric_cell(row)
            if isinstance(value, (int, float)) and value > 1000:
                return value
        return None

    def _rows_after_group(self, matrix: list[list[str]], group_aliases: list[str], stop_prefixes: tuple[str, ...]) -> list[list[str]]:
        rows: list[list[str]] = []
        active = False
        for row in matrix:
            label = self._row_label(row)
            if any(alias in label for alias in group_aliases):
                active = True
                continue
            if active and label and any(label.startswith(prefix) for prefix in stop_prefixes):
                break
            if active:
                rows.append(row)
        return rows

    def _half_length(self, value: Any) -> Any:
        if value is None:
            return None
        match = re.search(r"[0-9]+(?:\.[0-9]+)?", str(value).replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
        if number > 100:
            number /= 1000
        return self._clean_number(number / 2)

    def _earthwork_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        explicit_rows = self._earthwork_rows_from_explicit_tables(ast)
        if explicit_rows:
            return self._schema_table("earthworkBalance", explicit_rows)
        major_quantity_rows = self._earthwork_rows_from_major_quantity_tables(ast)
        if major_quantity_rows:
            return self._schema_table("earthworkBalance", major_quantity_rows)
        narrative_rows = self._earthwork_rows_from_narrative(ast)
        if narrative_rows:
            return self._schema_table("earthworkBalance", narrative_rows)
        rows: list[dict[str, Any]] = []
        groups = [
            ("道路", ["道路设计", "交通工程"], ["道路"]),
            ("风机平台", ["吊装平台"], ["吊装平台"]),
            ("风机基础", ["风机基础", "风电机组基础"], ["风电机组基础工程", "风机基础"]),
            ("箱变基础", ["机组变压器基础", "箱变"], ["机组变压器基础", "箱变"]),
            ("升压站", ["升压站设计", "升压变电站"], ["升压站", "升压变电站"]),
        ]
        for item, section_aliases, text_aliases in groups:
            excavation = 0.0
            backfill = 0.0
            matched = False
            for table in ast.tables:
                section_text = " / ".join(table.section_path)
                matrix = self._table_matrix(table)
                text = self._matrix_text(matrix)
                if not any(alias in section_text or alias in text for alias in section_aliases + text_aliases):
                    continue
                table_excavation = self._sum_rows_by_label(matrix, ["土方开挖", "基础开挖", "开挖"])
                table_backfill = self._sum_rows_by_label(matrix, ["土方回填", "土石回填", "素土回填", "灰土回填", "回填方", "回填"])
                if table_excavation or table_backfill:
                    excavation += table_excavation
                    backfill += table_backfill
                    matched = True
            if matched:
                rows.append({"item": item, "excavation": self._clean_number(excavation), "backfill": self._clean_number(backfill)})
        if rows:
            rows.append(
                {
                    "item": "合计",
                    "excavation": self._clean_number(sum(float(row.get("excavation") or 0) for row in rows)),
                    "backfill": self._clean_number(sum(float(row.get("backfill") or 0) for row in rows)),
                }
            )
            return self._schema_table("earthworkBalance", rows)
        return None

    def _earthwork_rows_from_major_quantity_tables(self, ast: DocumentAST) -> list[dict[str, Any]]:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            table_text = self._matrix_text(matrix)
            if "土方开挖" not in table_text or "土方回填" not in table_text:
                continue
            if not any(keyword in table_text for keyword in ("主要工程量", "技术经济指标", "工程量")):
                continue
            excavation = self._value_after_row_label(matrix, "土方开挖")
            backfill = self._value_after_row_label(matrix, "土方回填")
            if excavation is None and backfill is None:
                continue
            row: dict[str, Any] = {
                "item": "合计",
                "excavation": excavation[0] if excavation else None,
                "backfill": backfill[0] if backfill else None,
            }
            cell_sources: dict[str, Any] = {}
            if excavation:
                cell_sources["excavation"] = self._table_cell_source(
                    table,
                    excavation[1],
                    excavation[2],
                    "由主要工程量表的土方开挖行抽取土石方平衡挖方。",
                    resolver="earthwork_major_quantity_table",
                )
            if backfill:
                cell_sources["backfill"] = self._table_cell_source(
                    table,
                    backfill[1],
                    backfill[2],
                    "由主要工程量表的土方回填行抽取土石方平衡填方。",
                    resolver="earthwork_major_quantity_table",
                )
            if cell_sources:
                row["_cellSources"] = cell_sources
            return [row]
        return []

    def _value_after_row_label(self, matrix: list[list[str]], label: str) -> tuple[Any, int, int] | None:
        for row_index, row in enumerate(matrix):
            for label_index, cell in enumerate(row):
                if label not in cell:
                    continue
                for value_index in range(label_index + 1, len(row)):
                    value = self._normalize_table_cell(row[value_index])
                    if isinstance(value, (int, float)):
                        if self._row_value_unit_is_ten_thousand_m3(row, label_index, value_index):
                            value = self._clean_number(float(value) * 10000)
                        return value, row_index, value_index
        return None

    def _row_value_unit_is_ten_thousand_m3(self, row: list[str], label_index: int, value_index: int) -> bool:
        unit_text = " ".join(str(cell) for cell in row[label_index + 1 : value_index])
        return bool(re.search(r"万\s*m\s*[³3]", unit_text, flags=re.IGNORECASE))

    def _earthwork_rows_from_explicit_tables(self, ast: DocumentAST) -> list[dict[str, Any]]:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            header = self._header_row(matrix, ["开挖", "回填"]) or matrix[0]
            header_index = matrix.index(header) if header in matrix else 0
            header_text = " | ".join(header)
            if not ("开挖" in header_text and "回填" in header_text):
                continue
            rows: list[dict[str, Any]] = []
            explicit_total: dict[str, Any] | None = None
            for source_row in matrix[header_index + 1 :]:
                label = self._row_label(source_row)
                if not label:
                    continue
                excavation = self._row_value_by_header(header, source_row, ["土方开挖", "开挖"])
                backfill = self._row_value_by_header(header, source_row, ["土方回填", "回填"])
                if excavation is None or backfill is None:
                    numbers = self._numeric_cells(source_row)
                    if len(numbers) >= 2:
                        excavation = numbers[-2][1]
                        backfill = numbers[-1][1]
                if "合计" in label and (excavation is not None or backfill is not None):
                    explicit_total = {"item": "合计", "excavation": excavation, "backfill": backfill}
                    continue
                if not any(keyword in label for keyword in ("道路", "平台", "风机基础", "箱变", "升压站", "电缆")):
                    continue
                item = self._earthwork_item_name(label)
                if item and (excavation is not None or backfill is not None):
                    rows.append({"item": item, "excavation": excavation, "backfill": backfill})
            if rows:
                rows.append(explicit_total or {"item": "合计", "excavation": self._clean_number(sum(float(row.get("excavation") or 0) for row in rows)), "backfill": self._clean_number(sum(float(row.get("backfill") or 0) for row in rows))})
                return rows
        return []

    def _earthwork_rows_from_narrative(self, ast: DocumentAST) -> list[dict[str, Any]]:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if "土石方" in block.text or "土方" in block.text)
        specs = [
            ("风机基础", r"风机基础工程(?:（单台）)?土石方开挖\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3].{0,20}?回填\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3]"),
            ("集电线路", r"电缆工程土石方开挖\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3].{0,20}?回填\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3]"),
            ("升压站", r"升压站场地平整土石方开挖\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3].{0,20}?回填\s*([0-9]+(?:\.[0-9]+)?)\s*m[³3]"),
        ]
        rows: list[dict[str, Any]] = []
        for item, pattern in specs:
            match = re.search(pattern, text)
            if match:
                rows.append({"item": item, "excavation": self._normalize_scalar(match.group(1)), "backfill": self._normalize_scalar(match.group(2))})
        if rows:
            rows.append({"item": "合计", "excavation": self._clean_number(sum(float(row.get("excavation") or 0) for row in rows)), "backfill": self._clean_number(sum(float(row.get("backfill") or 0) for row in rows))})
        return rows

    def _earthwork_item_name(self, label: str) -> str | None:
        if "道路" in label:
            return "道路"
        if "平台" in label:
            return "风机平台"
        if "风机基础" in label:
            return "风机基础"
        if "箱变" in label or "变压器基础" in label:
            return "箱变基础"
        if "升压站" in label:
            return "升压站"
        if "电缆" in label:
            return "集电线路"
        return None

    def _pile_diameter_from_radius(self, radius: Any) -> Any:
        if radius is None:
            return None
        try:
            value = float(str(radius).replace(",", "")) * 2
        except ValueError:
            return radius
        return int(value) if value.is_integer() else round(value, 3)

    def _normalize_piles_per_ring(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return re.sub(r"，分布半径为[^，]+", "", value)

    def _build_substation_civil_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        row = self._substation_civil_combined_row(ast)
        return {"substationCivilCombined": [row] if row else []}

    def _build_road_parameter_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        row = self._road_parameter_row_from_document(ast)
        return {"roadParameters": [row] if row else []}

    def _road_parameter_row_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        text_values = self._road_parameter_row_from_text(ast)
        table_values, explicit_table_keys = self._road_parameter_row_from_tables(ast)
        row = dict(table_values)
        for key, value in text_values.items():
            if key in explicit_table_keys:
                continue
            if row.get(key) is None and value is not None:
                row[key] = value
            elif key == "pavementWidth" and value is not None:
                row[key] = value
        self._clear_ambiguous_maintenance_road_length(row, ast)
        if any(value is not None for value in row.values()):
            source_text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text and any(keyword in block.text for keyword in ("道路", "路基", "路面", "进站", "进场")))
            if not source_text:
                source_text = "\n".join(self._table_text(table) for table in ast.tables if any(keyword in self._table_text(table) for keyword in ("道路", "路基", "路面", "进站", "进场")))
            row["_rowSource"] = self._combined_text_row_source(ast, source_text, "道路参数正文/表格组合字段来源。", "road_parameters_text_combined")
        return row if any(value is not None for value in row.values()) else None

    def _clear_ambiguous_maintenance_road_length(self, row: dict[str, Any], ast: DocumentAST) -> None:
        if self._should_clear_ambiguous_maintenance_road_length(row.get("maintenanceRoadLength"), row.get("siteRoadLength"), ast):
            row["maintenanceRoadLength"] = None

    def _should_clear_ambiguous_maintenance_road_length(self, maintenance: Any, site: Any, ast: DocumentAST) -> bool:
        if maintenance is None or site is None:
            return False
        try:
            maintenance_number = float(maintenance)
            if abs(maintenance_number - float(site)) > 0.0001:
                return False
        except (TypeError, ValueError):
            return False
        text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        return not self._has_explicit_maintenance_road_length(text, maintenance_number)

    def _has_explicit_maintenance_road_length(self, text: str, value: float) -> bool:
        value_text = self._number_regex_with_optional_trailing_zeros(value)
        explicit_pattern = rf"(?:场内[^。；;\n]{{0,24}}?)?检修道路\s*(?:长(?:度)?|长度|约)[^0-9。；;\n]{{0,16}}{value_text}\s*(?:km|公里|千米)"
        for match in re.finditer(explicit_pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 30): match.start()]
            if not re.search(r"施工道路\s*[（(]\s*$", prefix):
                return True
        return False

    def _road_parameter_row_from_tables(self, ast: DocumentAST) -> tuple[dict[str, Any], set[str]]:
        row: dict[str, Any] = self._empty_road_parameter_row()
        explicit_keys: set[str] = set()
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            table_text = self._matrix_text(matrix)
            if not any(keyword in f"{caption}\n{section_caption}\n{table_text}" for keyword in ("道路", "路基", "路面")):
                continue
            wide_values, wide_keys = self._road_parameter_values_from_wide_matrix(matrix)
            explicit_keys.update(wide_keys)
            self._merge_road_parameter_row(row, wide_values)
            self._merge_road_parameter_row(row, self._road_parameter_values_from_text(table_text), blocked_keys=explicit_keys)
            self._merge_road_parameter_row(row, self._road_parameter_values_from_matrix(matrix), blocked_keys=explicit_keys)
        return row, explicit_keys

    def _road_parameter_row_from_text(self, ast: DocumentAST) -> dict[str, Any]:
        blocks = [
            block
            for block in ast.blocks
            if block.text and block.type != "table" and any(keyword in block.text for keyword in ("道路", "路基", "路面", "进站", "进场"))
        ]
        preferred_blocks = [
            block
            for block in blocks
            if any(keyword in " / ".join(block.section_path or []) for keyword in ("施工组织", "施工总布置", "场内施工道路", "道路设计"))
        ]
        source_blocks = preferred_blocks or blocks
        text = "\n".join(
            self._clean_text(block.text or "")
            for block in source_blocks
        )
        table_text = "\n".join(
            self._table_text(table)
            for table in ast.tables
            if any(keyword in self._table_text(table) for keyword in ("道路", "路基", "路面", "进站", "进场"))
        )
        values = self._road_parameter_values_from_text(text)
        table_values = self._road_parameter_values_from_text(table_text)
        self._merge_road_parameter_row(values, table_values)
        return values

    def _empty_road_parameter_row(self) -> dict[str, Any]:
        return {
            "accessRoadLength": None,
            "siteEntryRoadLength": None,
            "accessRoadSubgradeWidth": None,
            "accessRoadPavementWidth": None,
            "newRoadLength": None,
            "rebuiltRoadLength": None,
            "subgradeWidth": None,
            "pavementWidth": None,
            "siteRoadLength": None,
            "maintenanceRoadLength": None,
            "maintenanceRoadSubgradeWidth": None,
            "maintenanceRoadPavementWidth": None,
        }

    def _merge_road_parameter_row(self, target: dict[str, Any], source: dict[str, Any], blocked_keys: set[str] | None = None) -> None:
        blocked_keys = blocked_keys or set()
        for key, value in source.items():
            if key in blocked_keys and target.get(key) is None:
                continue
            if (
                key in {"accessRoadSubgradeWidth", "accessRoadPavementWidth", "subgradeWidth", "pavementWidth", "maintenanceRoadSubgradeWidth", "maintenanceRoadPavementWidth"}
                and value is not None
                and not self._valid_road_width(value)
            ):
                continue
            if (
                key in {"accessRoadLength", "siteEntryRoadLength", "siteRoadLength", "newRoadLength", "rebuiltRoadLength", "maintenanceRoadLength"}
                and value is not None
                and not self._valid_road_length(value, key)
            ):
                continue
            if target.get(key) is None and value is not None:
                target[key] = value
            elif key in {"accessRoadSubgradeWidth", "accessRoadPavementWidth", "subgradeWidth", "pavementWidth", "maintenanceRoadSubgradeWidth", "maintenanceRoadPavementWidth"} and self._valid_road_width(value) and not self._valid_road_width(target.get(key)):
                target[key] = value
            elif key in {"accessRoadLength", "siteEntryRoadLength", "siteRoadLength", "newRoadLength", "rebuiltRoadLength", "maintenanceRoadLength"} and self._valid_road_length(value, key) and not self._valid_road_length(target.get(key), key):
                target[key] = value

    def _road_parameter_values_from_wide_matrix(self, matrix: list[list[str]]) -> tuple[dict[str, Any], set[str]]:
        values = self._empty_road_parameter_row()
        explicit_keys: set[str] = set()
        if len(matrix) < 2:
            return values, explicit_keys
        header_index, headers = self._road_parameter_wide_header(matrix)
        if header_index < 0:
            return values, explicit_keys
        data_row = next(
            (
                row
                for row in matrix[header_index + 1 :]
                if not self._road_parameter_unit_row(row) and any(isinstance(self._normalize_scalar(cell), (int, float)) for cell in row)
            ),
            [],
        )
        if not data_row:
            return values, explicit_keys
        for index, header in enumerate(headers):
            key = self._road_parameter_key_from_header(header)
            if key is None:
                continue
            explicit_keys.add(key)
            cell = data_row[index] if index < len(data_row) else ""
            value = self._road_parameter_value_from_cell(cell, key)
            if value is not None:
                values[key] = value
        return values, explicit_keys

    def _road_parameter_wide_header(self, matrix: list[list[str]]) -> tuple[int, list[str]]:
        search_limit = min(len(matrix), 4)
        for index in range(search_limit):
            row = matrix[index]
            if not any(self._road_parameter_key_from_header(cell) for cell in row):
                continue
            headers = list(row)
            if index + 1 < len(matrix) and self._road_parameter_unit_row(matrix[index + 1]):
                unit_row = matrix[index + 1]
                headers = [
                    f"{header}{unit_row[col_index]}" if col_index < len(unit_row) and unit_row[col_index] else header
                    for col_index, header in enumerate(headers)
                ]
            return index, headers
        return -1, []

    def _road_parameter_unit_row(self, row: list[str]) -> bool:
        cells = [self._compact_text(self._clean_text(cell or "")) for cell in row if self._clean_text(cell or "")]
        if not cells:
            return False
        return all(re.fullmatch(r"[（(]?(?:km|m|公里|千米|米)[）)]?", cell, flags=re.IGNORECASE) for cell in cells)

    def _road_parameter_key_from_header(self, header: str) -> str | None:
        text = self._compact_text(self._clean_text(header or ""))
        if not text:
            return None
        mappings = [
            ("accessRoadSubgradeWidth", ["进站道路路基宽度", "进场道路路基宽度"]),
            ("accessRoadPavementWidth", ["进站道路路面宽度", "进场道路路面宽度"]),
            ("siteEntryRoadLength", ["进场道路长度"]),
            ("accessRoadLength", ["进站道路长度", "进升压站道路长度"]),
            ("maintenanceRoadSubgradeWidth", ["检修道路路基宽度", "检修道路路基宽"]),
            ("maintenanceRoadPavementWidth", ["检修道路路面宽度", "检修道路路面宽"]),
            ("maintenanceRoadLength", ["检修道路长度"]),
            ("siteRoadLength", ["场内道路长度", "场内运输道路长度", "场内施工道路长度"]),
            ("newRoadLength", ["新建道路长度", "新修道路长度"]),
            ("rebuiltRoadLength", ["改建道路长度", "扩建道路长度", "改扩建道路长度"]),
            ("subgradeWidth", ["路基宽度", "路基宽"]),
            ("pavementWidth", ["路面宽度", "路面宽"]),
        ]
        for key, aliases in mappings:
            if any(alias in text for alias in aliases):
                return key
        return None

    def _road_parameter_value_from_cell(self, cell: Any, key: str) -> Any:
        text = self._clean_text(str(cell or ""))
        if not text or text in {"—", "——", "---", "--", "/", "无"}:
            return None
        value = self._normalize_scalar(text)
        target_unit = "km" if key.endswith("Length") else "m"
        return self._convert_road_length(value, text, target_unit) if key.endswith("Length") else value

    def _valid_road_width(self, value: Any) -> bool:
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return False
        return 2 <= number <= 12

    def _valid_road_length(self, value: Any, key: str) -> bool:
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return False
        if key == "accessRoadLength":
            return 0.05 <= number <= 50
        if key == "siteRoadLength":
            return 0.1 <= number <= 500
        if key in {"newRoadLength", "rebuiltRoadLength", "maintenanceRoadLength"}:
            return 0.001 <= number <= 500
        return True

    def _road_parameter_values_from_matrix(self, matrix: list[list[str]]) -> dict[str, Any]:
        values = self._empty_road_parameter_row()
        for row in matrix[1:]:
            label = self._row_label(row)
            if not label:
                continue
            if "表" in label and any(keyword in label for keyword in ("工程数量", "工程量", "汇总", "清单")):
                continue
            row_text = " ".join(row)
            value = self._last_measure_numeric_cell(row)
            if values["siteEntryRoadLength"] is None and "进场道路" in label and "路基" not in label and "路面" not in label:
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["siteEntryRoadLength"] = row_length
                else:
                    values["siteEntryRoadLength"] = self._convert_road_length(value, row_text, "km")
            if values["accessRoadLength"] is None and ("进站道路" in label or "进升压站道路" in label) and "路基" not in label and "路面" not in label:
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["accessRoadLength"] = row_length
                elif value is not None:
                    values["accessRoadLength"] = self._convert_road_length(value, row_text, "km")
            if values["siteRoadLength"] is None and any(keyword in label for keyword in ("场内道路", "场内运输道路", "场内施工道路")):
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["siteRoadLength"] = row_length
                elif value is not None:
                    values["siteRoadLength"] = self._convert_road_length(value, row_text, "km")
            if values["maintenanceRoadLength"] is None and "检修道路" in label and "施工道路" not in label and "路基" not in label and "路面" not in label:
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["maintenanceRoadLength"] = row_length
                elif value is not None:
                    values["maintenanceRoadLength"] = self._convert_road_length(value, row_text, "km")
            if values["maintenanceRoadSubgradeWidth"] is None and "检修道路" in label and "路基" in label and value is not None:
                values["maintenanceRoadSubgradeWidth"] = value
            if values["maintenanceRoadPavementWidth"] is None and "检修道路" in label and "路面" in label and value is not None:
                values["maintenanceRoadPavementWidth"] = value
            if values["newRoadLength"] is None and "新建" in label and "道路" in label:
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["newRoadLength"] = row_length
                elif value is not None and re.search(r"\bkm\b|公里|千米|(?<!k)m\b|米", row_text, flags=re.IGNORECASE) and not re.search(r"m2|m²|㎡|平方米", row_text, flags=re.IGNORECASE):
                    values["newRoadLength"] = self._convert_road_length(value, row_text, "km")
            if values["rebuiltRoadLength"] is None and any(keyword in label for keyword in ("改建道路", "扩建道路")):
                row_length = self._road_length_from_row_text(row_text, "km")
                if row_length is not None:
                    values["rebuiltRoadLength"] = row_length
                elif value is not None and re.search(r"\bkm\b|公里|千米|(?<!k)m\b|米", row_text, flags=re.IGNORECASE) and not re.search(r"m2|m²|㎡|平方米", row_text, flags=re.IGNORECASE):
                    values["rebuiltRoadLength"] = self._convert_road_length(value, row_text, "km")

            access_subgrade = self._first_width_match(row_text, [
                r"进(?:站|升压站|场)道路路基[（(]路面[）)]宽度[^0-9]{0,20}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*[（(]\s*[0-9]+(?:\.[0-9]+)?\s*[）)]",
                r"(?:进站道路|进升压站道路|场内运输道路及进站道路)[^。；;\n|]{0,100}?路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            ])
            if access_subgrade is not None and values["accessRoadSubgradeWidth"] is None:
                values["accessRoadSubgradeWidth"] = access_subgrade
            access_pavement = self._first_width_match(row_text, [
                r"进(?:站|升压站|场)道路路基[（(]路面[）)]宽度[^0-9]{0,20}[0-9]+(?:\.[0-9]+)?\s*[（(]\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*[）)]",
                r"(?:进站道路|进升压站道路|场内运输道路及进站道路)[^。；;\n|]{0,120}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
            ])
            if access_pavement is not None and values["accessRoadPavementWidth"] is None:
                values["accessRoadPavementWidth"] = access_pavement
            subgrade = self._first_width_match(row_text, [
                r"路基[（(]路面[）)]宽度[^0-9]{0,20}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*[（(]\s*[0-9]+(?:\.[0-9]+)?\s*[）)]",
                r"路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            ])
            if subgrade is not None and values["subgradeWidth"] is None:
                values["subgradeWidth"] = subgrade
            pavement = self._first_width_match(row_text, [
                r"路基[（(]路面[）)]宽度[^0-9]{0,20}[0-9]+(?:\.[0-9]+)?\s*[（(]\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*[）)]",
                r"路面(?:宽度|宽)\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
                r"路面\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            ])
            if pavement is not None and values["pavementWidth"] is None:
                values["pavementWidth"] = pavement
            maintenance_subgrade = self._first_width_match(row_text, [
                r"修复成\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m\s*宽作为检修道路路基",
                r"检修道路[^。；;\n|]{0,80}?路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
                r"检修道路[^。；;\n|]{0,80}?按路基宽\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            ])
            if maintenance_subgrade is not None and values["maintenanceRoadSubgradeWidth"] is None:
                values["maintenanceRoadSubgradeWidth"] = maintenance_subgrade
            maintenance_pavement = self._first_width_match(row_text, [
                r"检修道路[^。；;\n|]{0,120}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
                r"作为检修道路路基[^。；;\n|]{0,40}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
            ])
            if maintenance_pavement is not None and values["maintenanceRoadPavementWidth"] is None:
                values["maintenanceRoadPavementWidth"] = maintenance_pavement
        return values

    def _road_length_from_row_text(self, row_text: str, target_unit: str) -> Any:
        return self._first_road_length_match(row_text, [
            r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
        ], target_unit)

    def _road_parameter_values_from_text(self, text: str) -> dict[str, Any]:
        values = self._empty_road_parameter_row()
        if not text.strip():
            return values
        values["accessRoadLength"] = self._first_road_length_match(text, [
            r"(?:新建)?进(?:站|升压站)道路(?:长(?:度)?|为)?[^0-9\n。；;]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
        ], "km")
        values["siteEntryRoadLength"] = self._first_road_length_match(text, [
            r"(?:新建)?进场道路(?:长(?:度)?|为)?[^0-9\n。；;]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
            r"进场道路\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
        ], "km")
        values["siteRoadLength"] = self._first_road_length_match(text, [
            r"场内(?:运输|施工)?道路(?:长(?:度)?|长度|约)[^0-9\n。；;]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
            r"场内通往各风机点位的运输道路约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
            r"场内(?:运输|施工)?道路(?!及进站道路设计路基|路基|路面)[^0-9\n。；;]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
        ], "km")
        values["maintenanceRoadLength"] = self._maintenance_road_length_from_text(text)
        values["newRoadLength"] = self._first_road_length_match(text, [
            r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)\s*为新建道路",
            r"新建道路(?:长(?:度)?|约|为|共|合计)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)",
            r"(?:新建|修建)场内施工道路长?约?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)",
        ], "km")
        values["rebuiltRoadLength"] = self._first_road_length_match(text, [
            r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)\s*为改建道路",
            r"改建道路(?:长(?:度)?|约|为|共|合计)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)",
            r"扩建道路(?:长(?:度)?|约|为|共|合计)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米|m|米)",
        ], "km")
        values["accessRoadSubgradeWidth"] = self._first_width_match(text, [
            r"(?:进站道路|进升压站道路|进场道路|场内运输道路及进站道路)[^。；;\n]{0,100}?路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
        ])
        values["accessRoadPavementWidth"] = self._first_width_match(text, [
            r"(?:进站道路|进升压站道路|进场道路|场内运输道路及进站道路)[^。；;\n]{0,120}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
        ])
        values["subgradeWidth"] = self._first_width_match(text, [
            r"路基设计宽度为\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            r"施工期路基宽度为\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            r"路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
        ])
        preferred_pavement_width = self._first_width_match(text, [
            r"\u65bd\u5de5\u9053\u8def[^\n\u3002\uff1b;]{0,60}?\u8def\u9762\u5bbd\u5ea6\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            r"\u65bd\u5de5\u671f\u8def\u57fa\u5bbd\u5ea6[^\n\u3002\uff1b;]{0,40}?\u8def\u9762\u5bbd\u5ea6\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            r"\u573a\u5185\u9053\u8def\u8def\u9762\u5bbd\u5ea6\s*\|\s*m\s*\|\s*(?P<value>[0-9]+(?:\.[0-9]+)?)",
        ])
        values["pavementWidth"] = preferred_pavement_width or self._last_non_maintenance_width_match(text, [
            r"路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
        ])
        values["maintenanceRoadSubgradeWidth"] = self._first_width_match(text, [
            r"修复成\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m\s*宽作为检修道路路基",
            r"检修道路[^。；;\n]{0,100}?按路基宽\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
            r"检修道路[^。；;\n]{0,100}?路基(?:设计)?宽(?:度)?(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m",
        ])
        values["maintenanceRoadPavementWidth"] = self._first_width_match(text, [
            r"检修道路[^。；;\n]{0,140}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
            r"作为检修道路路基[^。；;\n]{0,60}?路面(?:宽(?:度)?|为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*m(?:宽)?",
        ])
        if (
            values["maintenanceRoadLength"] is not None
            and "检修道路" in text
            and re.search(r"施工完成后恢复为?原状", text)
        ):
            if values["maintenanceRoadSubgradeWidth"] is None:
                values["maintenanceRoadSubgradeWidth"] = values["subgradeWidth"]
            if values["maintenanceRoadPavementWidth"] is None:
                values["maintenanceRoadPavementWidth"] = values["pavementWidth"]
        return values

    def _maintenance_road_length_from_text(self, text: str) -> Any:
        patterns = [
            r"(?:场内[^。；;\n]{0,24}?)?检修道路\s*(?:长(?:度)?|长度|约)[^0-9\n。；;]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km|公里|千米)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                prefix = text[max(0, match.start() - 30): match.start()]
                if re.search(r"施工道路\s*[（(]\s*$", prefix):
                    continue
                value = self._normalize_scalar(match.group("value"))
                unit = match.groupdict().get("unit")
                return self._convert_road_length(value, unit or match.group(0), "km")
        return None

    def _last_non_maintenance_width_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
            for match in reversed(matches):
                start = match.start()
                prefix = text[max(0, start - 80): start]
                segment_start = max(prefix.rfind(mark) for mark in ("。", "；", ";", "\n")) + 1
                context = prefix[segment_start:] + text[start:match.end()]
                access_only = any(keyword in context for keyword in ("进站道路", "进升压站道路", "进场道路")) and "场内运输道路" not in context
                if "检修道路" in context or access_only:
                    continue
                return self._normalize_scalar(match.group("value") if "value" in match.groupdict() else match.group(1))
        return None

    def _first_road_length_match(self, text: str, patterns: list[str], target_unit: str) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = self._normalize_scalar(match.group("value"))
                unit = match.groupdict().get("unit")
                return self._convert_road_length(value, unit or match.group(0), target_unit)
        return None

    def _convert_road_length(self, value: Any, source_text: str | None, target_unit: str) -> Any:
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return value
        source = source_text or ""
        source_is_km = bool(re.search(r"km|公里|千米", source, flags=re.IGNORECASE))
        source_is_m = bool(re.search(r"(?<!k)m\b|米", source, flags=re.IGNORECASE))
        if target_unit == "m" and source_is_km:
            number *= 1000
        elif target_unit == "km" and source_is_m and not source_is_km:
            number /= 1000
        return self._clean_number(number)

    def _first_width_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group("value"))
        return None

    def _last_width_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
            if matches:
                return self._normalize_scalar(matches[-1].group("value"))
        return None

    def _substation_civil_combined_row(self, ast: DocumentAST) -> dict[str, Any] | None:
        text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        table_text = "\n".join(self._table_text(table) for table in ast.tables)
        combined = f"{text}\n{table_text}"
        total = self._first_length_area_number(combined, [
            r"\u5347\u538b\u7ad9\u603b\u5360\u5730\u9762\u79ef\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m\u00b2|\u33a1|\u5e73\u65b9\u7c73)",
            r"\u603b\u5360\u5730\u9762\u79ef\D{0,8}([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m\u00b2|\u33a1|\u5e73\u65b9\u7c73)?",
        ])
        inside = self._first_length_area_number(combined, [
            r"\u56f4\u5899\u5185\u5360\u5730\u9762\u79ef\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m\u00b2|\u33a1|\u5e73\u65b9\u7c73)",
            r"\u56f4\u5899\u5185\u5360\u5730\u9762\u79ef\D{0,8}([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m\u00b2|\u33a1|\u5e73\u65b9\u7c73)?",
        ])
        if total is None and inside is None:
            return None
        return {
            "totalLandArea": total,
            "insideWallLandArea": inside,
            "_rowSource": self._combined_text_row_source(ast, combined, "土建升压站正文/表格组合字段来源。", "substation_civil_text_combined"),
        }

    def _build_land_area_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "permanentLandArea": [],
            "longTermLeaseArea": [],
            "temporaryLandArea": [],
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            header = matrix[0]
            row = matrix[1]
            header_text = " | ".join(header)
            if "永久性占地项目" in header_text:
                details["permanentLandArea"] = [
                    {
                        "item": self._cell_at_alias(header, row, ["永久性占地项目"]),
                        "windFoundation": self._cell_at_alias(header, row, ["风机基础"]),
                        "boxTransformerFoundation": self._cell_at_alias(header, row, ["箱变基础"]),
                        "substation110kv": self._cell_at_alias(header, row, ["升压站", "110kV升压站"]),
                        "collectorTower": self._cell_at_alias(header, row, ["集电线路杆塔征地", "杆塔"]),
                        "accessRoad": self._cell_at_alias(header, row, ["进升压站道路"]),
                        "total": self._cell_at_alias(header, row, ["合计"]),
                    }
                ]
            elif "长期租地项目" in header_text:
                details["longTermLeaseArea"] = [
                    {
                        "category": row[0] if len(row) > 0 else None,
                        "item": self._header_value_pair(header, row, ["电缆直埋征地", "场内永久道路", "进站道路"])[0],
                        "area": self._header_value_pair(header, row, ["电缆直埋征地", "场内永久道路", "进站道路"])[1],
                        "compensationCategory": None,
                        "compensationItem": None,
                        "compensationArea": None,
                    }
                ]
            elif "临时性占地项目" in header_text:
                details["temporaryLandArea"] = [
                    {
                        "item": self._cell_at_alias(header, row, ["临时性占地项目"]),
                        "road": self._cell_at_alias(header, row, ["风场道路", "临时施工道路"]),
                        "platform": self._cell_at_alias(header, row, ["吊装平台", "安装平台", "场内平整"]),
                        "collectorLine": self._cell_at_alias(header, row, ["集电线路"]),
                        "directBuriedCable": self._cell_at_alias(header, row, ["电缆直埋"]),
                        "constructionSite": self._cell_at_alias(header, row, ["施工临建场地", "生活临建"]),
                        "total": self._cell_at_alias(header, row, ["合计"]),
                    }
                ]
            elif self._looks_like_mixed_land_header(header_text):
                land = self._land_area_rows_from_mixed_table(matrix)
                for key, value in land.items():
                    if value:
                        details[key] = value
            elif all(keyword in header_text for keyword in ("项目", "面积")) and any("风机基础" in " | ".join(row) for row in matrix):
                permanent = self._permanent_land_from_item_area_table(matrix)
                if permanent:
                    details["permanentLandArea"] = [permanent]
            elif "临时征地面积汇总表" in header_text or all(keyword in header_text for keyword in ("项目", "临时用地")):
                temporary, compensation = self._temporary_land_from_item_area_table(matrix)
                if temporary:
                    details["temporaryLandArea"] = [temporary]
                if compensation:
                    details["longTermLeaseArea"] = [compensation]
        block_land = self._land_area_from_text_blocks(ast)
        for key, rows in block_land.items():
            if rows and (not details.get(key) or not self._detail_rows_have_values(details[key])):
                details[key] = rows
        self._merge_land_continuation_tables(ast, details)
        return details

    def _detail_rows_have_values(self, rows: list[dict[str, Any]]) -> bool:
        return any(any(value is not None for value in row.values()) for row in rows)

    def _land_area_from_text_blocks(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "permanentLandArea": [],
            "longTermLeaseArea": [],
            "temporaryLandArea": [],
        }
        texts = [
            self._clean_text(block.text)
            for block in ast.blocks
            if block.text and ("永久性占地" in block.text or "长期租地" in block.text or "临时性占地" in block.text)
        ]
        for text in texts:
            if "永久性占地" in text:
                permanent = {
                    "item": "面积",
                    "windFoundation": self._area_value_after_label(text, ["风机基础"]),
                    "boxTransformerFoundation": self._area_value_after_label(text, ["箱变基础", "箱式变电站基础"]),
                    "substation110kv": self._area_value_after_label(text, ["110kV升压站", "升压站"]),
                    "collectorTower": self._area_value_after_label(text, ["集电线路杆塔征地", "杆塔基础"]),
                    "accessRoad": self._area_value_after_label(text, ["进升压站道路", "进站道路"]),
                    "total": self._area_value_after_label(text, ["永久性占地合计", "永久用地合计"]),
                }
                if permanent["total"] is None:
                    permanent["total"] = self._sum_present(value for key, value in permanent.items() if key != "item")
                if any(value is not None for key, value in permanent.items() if key != "item"):
                    details["permanentLandArea"] = [permanent]
            if "长期租地" in text:
                long_term = {
                    "category": "面积",
                    "item": "长期租地",
                    "directBuriedCable": self._area_value_after_label(text, ["电缆直埋征地", "电缆直埋"]),
                    "permanentRoad": self._area_value_after_label(text, ["场内永久道路", "永久道路"]),
                    "accessRoad": self._area_value_after_label(text, ["进站道路", "进升压站道路"]),
                    "area": None,
                    "compensationCategory": None,
                    "compensationItem": None,
                    "compensationArea": None,
                    "total": self._area_value_after_label(text, ["长期租地合计", "长期租地总计"]),
                }
                if long_term["total"] is None:
                    long_term["total"] = self._sum_present(long_term.get(key) for key in ("directBuriedCable", "permanentRoad", "accessRoad"))
                long_term["area"] = long_term["total"]
                if any(value is not None for key, value in long_term.items() if key not in {"category", "item"}):
                    details["longTermLeaseArea"] = [long_term]
            if "临时性占地" in text:
                road = self._area_value_after_label(text, ["临时施工道路", "风场道路"])
                construction_site = self._area_value_after_label(text, ["生活临建", "施工临建场地", "临时施工设施"])
                temporary = {
                    "item": "面积",
                    "road": road,
                    "platform": self._area_value_after_label(text, ["场地平整（安装平台）", "安装平台", "吊装平台", "场内平整"]),
                    "collectorLine": self._area_value_after_label(text, ["集电线路"]),
                    "directBuriedCable": self._area_value_after_label(text, ["电缆直埋"]),
                    "constructionSite": construction_site,
                    "temporaryRoad": road,
                    "livingFacility": construction_site,
                    "total": self._area_value_after_label(text, ["临时性占地合计", "临时用地合计", "临时性占地总计"]),
                }
                if temporary["total"] is None:
                    temporary["total"] = self._sum_present(temporary.get(key) for key in ("road", "platform", "collectorLine", "directBuriedCable", "constructionSite"))
                if any(value is not None for key, value in temporary.items() if key != "item"):
                    details["temporaryLandArea"] = [temporary]
        return details

    def _area_value_after_label(self, text: str, labels: list[str]) -> Any:
        for label in labels:
            pattern = rf"{re.escape(label)}\s*\|\s*(?:m2|m²|㎡|平方米)?\s*\|\s*([0-9]+(?:\.[0-9]+)?)"
            match = re.search(pattern, text)
            if match:
                return self._normalize_scalar(match.group(1))
        return None

    def _merge_land_continuation_tables(self, ast: DocumentAST, details: dict[str, list[dict[str, Any]]]) -> None:
        if not details.get("temporaryLandArea"):
            return
        target = details["temporaryLandArea"][0]
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            labels = {row[0].strip() for row in matrix if row}
            if not ({"电缆直埋", "施工临建场地"} & labels):
                continue
            for row in matrix:
                label = row[0].strip() if row else ""
                if label not in {"电缆直埋", "施工临建场地", "合计"}:
                    continue
                value = self._normalize_table_cell(row[3]) if len(row) > 3 else self._last_numeric_cell(row)
                if value is None:
                    continue
                if label == "电缆直埋":
                    target["directBuriedCable"] = value
                elif label == "施工临建场地":
                    target["constructionSite"] = value
                elif label == "合计":
                    target["total"] = value

    def _permanent_land_from_item_area_table(self, matrix: list[list[str]]) -> dict[str, Any] | None:
        header = matrix[0]
        item_index = self._find_header_index(header, ["项目"])
        area_index = self._find_header_index(header, ["面积（㎡）", "面积(m2)", "面积"])
        if item_index is None or area_index is None:
            return None
        values: dict[str, Any] = {}
        for row in matrix[1:]:
            if item_index >= len(row) or area_index >= len(row):
                continue
            label = row[item_index]
            value = self._normalize_table_cell(row[area_index])
            if value is not None:
                values[label] = value
        result = {
            "item": "面积",
            "windFoundation": values.get("风机基础"),
            "boxTransformerFoundation": values.get("箱变基础"),
            "substation110kv": self._first_present(values.get("升压站"), values.get("110kV升压站")),
            "collectorTower": self._first_present(values.get("集电线路杆塔征地"), values.get("杆塔基础")),
            "accessRoad": self._first_present(values.get("进升压站道路"), values.get("进站道路")),
            "total": values.get("合计"),
        }
        if result["total"] is None:
            result["total"] = self._sum_present(value for key, value in result.items() if key != "item")
        return result if any(value is not None for key, value in result.items() if key != "item") else None

    def _temporary_land_from_item_area_table(self, matrix: list[list[str]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        header = matrix[1] if matrix and len(matrix[0]) == 1 and len(matrix) > 1 else matrix[0]
        data_rows = matrix[2:] if matrix and len(matrix[0]) == 1 and len(matrix) > 1 else matrix[1:]
        item_index = self._find_header_index(header, ["项目"])
        temp_index = self._find_header_index(header, ["临时用地", "临时征地"])
        compensation_index = self._find_header_index(header, ["临征永补"])
        if item_index is None:
            return None, None
        values: dict[str, Any] = {}
        compensation_values: dict[str, Any] = {}
        for row in data_rows:
            if item_index >= len(row):
                continue
            label = row[item_index]
            if temp_index is not None and temp_index < len(row):
                value = self._normalize_table_cell(row[temp_index])
                if value is not None:
                    values[label] = value
            if compensation_index is not None and compensation_index < len(row):
                value = self._normalize_table_cell(row[compensation_index])
                if value is not None:
                    compensation_values[label] = value
        temporary = {
            "item": "面积",
            "road": self._first_present(values.get("检修道路"), values.get("风场道路"), values.get("施工道路"), values.get("临时施工道路")),
            "platform": self._first_present(values.get("吊装平台"), values.get("安装平台")),
            "collectorLine": self._first_present(values.get("杆塔基础"), values.get("集电线路")),
            "directBuriedCable": self._first_present(values.get("电缆"), values.get("直埋电缆"), values.get("电缆直埋")),
            "constructionSite": self._first_present(values.get("临时施工设施"), values.get("施工临建场地"), values.get("施工临建"), values.get("生活临建")),
            "total": values.get("合计"),
        }
        if temporary["total"] is None:
            temporary["total"] = self._sum_present(value for key, value in temporary.items() if key != "item")
        compensation = None
        compensation_total = self._first_present(compensation_values.get("合计"), self._sum_present(compensation_values.values()))
        if compensation_total is not None:
            compensation = {
                "category": "临征永补",
                "item": "临征永补",
                "area": compensation_total,
                "compensationCategory": "临征永补项目",
                "compensationItem": "杆塔基础/检修道路",
                "compensationArea": compensation_total,
            }
        return (temporary if any(value is not None for key, value in temporary.items() if key != "item") else None), compensation

    def _land_area_rows_from_mixed_table(self, matrix: list[list[str]]) -> dict[str, list[dict[str, Any]]]:
        header = matrix[0]
        permanent_index = self._find_header_index(header, ["永久征地", "永久占地", "征地", "永久"])
        long_index = self._find_header_index(header, ["长期租地"])
        temporary_index = self._find_header_index(header, ["短期租地", "临时性占地", "临时租地", "临时"])
        values: dict[str, Any] = {}
        for row in matrix[1:]:
            label = row[0] if row else ""
            if not label:
                continue
            for key, index in (("permanent", permanent_index), ("long", long_index), ("temporary", temporary_index)):
                if index is not None and index < len(row):
                    number = self._normalize_table_cell(row[index])
                    if number is not None:
                        values[f"{key}:{label}"] = number
        permanent = {
            "item": "面积",
            "windFoundation": values.get("permanent:风机基础"),
            "boxTransformerFoundation": self._first_present(values.get("permanent:箱变"), values.get("permanent:箱变基础")),
            "substation110kv": self._first_present(values.get("permanent:升压站"), values.get("permanent:110kV升压站")),
            "collectorTower": self._first_present(values.get("permanent:集电线路杆塔征地"), values.get("permanent:杆塔基础")),
            "accessRoad": self._first_present(values.get("permanent:升压站进站道路"), values.get("permanent:进升压站道路"), values.get("permanent:进站道路")),
        }
        permanent["total"] = self._first_present(values.get("permanent:合计"), self._sum_present(permanent.values()))
        long_term = {
            "category": "面积",
            "item": "长期租地",
            "directBuriedCable": self._first_present(values.get("long:电缆直埋"), values.get("long:电缆直埋征地")),
            "permanentRoad": values.get("long:场内永久道路"),
            "maintenanceRoad": self._first_present(values.get("long:检修道路"), values.get("long:场内永久道路")),
            "accessRoad": self._first_present(values.get("long:进站道路"), values.get("long:进升压站道路")),
            "towerFoundation": self._first_present(values.get("long:塔基础"), values.get("long:铁塔基础"), values.get("long:杆塔基础")),
            "area": None,
            "compensationCategory": None,
            "compensationItem": None,
            "compensationArea": None,
        }
        long_term["total"] = self._first_present(values.get("long:合计"), self._sum_present(long_term.get(key) for key in ("directBuriedCable", "permanentRoad", "maintenanceRoad", "accessRoad", "towerFoundation")))
        long_term["area"] = long_term["total"]
        temporary = {
            "item": "面积",
            "road": self._first_present(values.get("temporary:风场道路"), values.get("temporary:施工道路"), values.get("temporary:临时施工道路")),
            "temporaryRoad": self._first_present(values.get("temporary:施工道路"), values.get("temporary:临时施工道路"), values.get("temporary:风场道路")),
            "platform": self._first_present(values.get("temporary:吊装平台"), values.get("temporary:安装平台"), values.get("temporary:施工吊装平台")),
            "collectorLine": values.get("temporary:集电线路"),
            "directBuriedCable": self._first_present(values.get("temporary:电缆"), values.get("temporary:直埋电缆"), values.get("temporary:电缆直埋")),
            "constructionSite": self._first_present(values.get("temporary:施工临建场地"), values.get("temporary:施工临建"), values.get("temporary:生活临建")),
        }
        temporary["livingFacility"] = temporary["constructionSite"]
        temporary["total"] = self._first_present(values.get("temporary:合计"), self._sum_present(temporary.values()))
        return {
            "permanentLandArea": [permanent] if any(value is not None for value in permanent.values()) else [],
            "longTermLeaseArea": [long_term] if long_term["area"] is not None else [],
            "temporaryLandArea": [temporary] if any(value is not None for value in temporary.values()) else [],
        }

    def _looks_like_mixed_land_header(self, header_text: str) -> bool:
        return (
            "项目" in header_text
            and any(keyword in header_text for keyword in ("永久征地", "永久占地", "征地"))
            and any(keyword in header_text for keyword in ("长期租地", "短期租地", "临时性占地", "临时租地"))
        )

    def _apply_earthwork_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        rows = self._earthwork_rows_from_explicit_tables(ast) or self._earthwork_rows_from_major_quantity_tables(ast) or self._earthwork_rows_from_narrative(ast)
        if not rows:
            table = self._earthwork_table_from_document(ast)
            rows = self._table_rows_as_dicts(table) if table else []
        for row in rows:
            item = str(row.get("item") or "")
            field_codes = self.EARTHWORK_FIELD_ROWS.get(item)
            if not field_codes:
                continue
            for value_key, code in (("excavation", field_codes[0]), ("backfill", field_codes[1])):
                if code in skip_codes:
                    continue
                value = row.get(value_key)
                if value is None:
                    continue
                name, unit = self.required_field_meta.get(code, (code, "m3"))
                self._set_field(
                    fields,
                    code,
                    name,
                    value,
                    unit,
                    f"由土石方平衡表“{item}”行抽取。",
                    source_type="table",
                    meta={"resolver": "earthwork_balance_table", "sectionPath": ["土石方平衡"]},
                )
        for code, name, value, unit, evidence_text, section_path in self._earthwork_spoil_disposal_field_values(ast):
            if code in skip_codes or value is None:
                continue
            self._set_field(
                fields,
                code,
                name,
                value,
                unit,
                evidence_text,
                source_type="paragraph",
                meta={"resolver": "earthwork_spoil_disposal_text", "sectionPath": section_path or ["土石方平衡"]},
            )

    def _earthwork_spoil_disposal_field_values(
        self, ast: DocumentAST
    ) -> list[tuple[str, str, Any, str, str, list[str]]]:
        """Extract spoil-disposal site count and total footprint from local text."""
        body_blocks = self._body_blocks(ast)
        blocks = [
            block
            for block in body_blocks
            if self._section_path_matches(block.section_path, ["土石方平衡", "渣场规划", "弃渣场"])
        ]
        if not blocks:
            blocks = [block for block in body_blocks if "弃渣场" in self._clean_text(block.text or "")]

        results: dict[str, tuple[str, str, Any, str, str, list[str]]] = {}
        for block in blocks:
            text = self._clean_text(block.text or "")
            if "弃渣场" not in text:
                continue
            section_path = list(block.section_path or ["土石方平衡"])
            if "spoilDisposalSiteCount" not in results:
                count_match = re.search(
                    r"(?:设置|设有|布置|新建|拟设(?:置)?|考虑设置)[^0-9。；;]{0,16}([0-9]+(?:\.[0-9]+)?)\s*个\s*弃渣场",
                    text,
                ) or re.search(r"弃渣场[^0-9。；;]{0,16}([0-9]+(?:\.[0-9]+)?)\s*个", text)
                if count_match:
                    results["spoilDisposalSiteCount"] = (
                        "spoilDisposalSiteCount",
                        "弃渣场数量",
                        self._normalize_scalar(count_match.group(1)),
                        "个",
                        text,
                        section_path,
                    )
            if "spoilDisposalSiteArea" not in results:
                area_match = re.search(
                    r"(?:总占地面积|占地面积)\s*(?:约为|约|为)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m\s*[²2]|㎡|平方米)",
                    text,
                    flags=re.IGNORECASE,
                )
                if area_match:
                    results["spoilDisposalSiteArea"] = (
                        "spoilDisposalSiteArea",
                        "弃渣场面积",
                        self._normalize_scalar(area_match.group(1)),
                        "㎡",
                        text,
                        section_path,
                    )
        return list(results.values())

    def _apply_wind_foundation_table_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        """从基础断面/尺寸表补齐风机基础字段，不再输出派生参数表。"""
        skip_codes = skip_codes or set()
        for field_code, override in self._wind_foundation_quantity_field_values(ast).items():
            if field_code in skip_codes:
                continue
            existing = fields.get(field_code)
            if existing is not None and existing.value is not None:
                continue
            name, value, unit, evidence_text, meta = override
            self._set_field(fields, field_code, name, value, unit, evidence_text, source_type="table", meta=meta)
        table = self._wind_foundation_technical_table_from_document(ast)
        if table is None or not table.get("data"):
            return
        values = dict(zip(table.get("columnKeys") or [], table["data"][0]))
        mapping = {
            "capBottomRadius": "foundationCapBottomRadius",
            "topRadius": "foundationTopRadius",
            "columnRadius": "foundationColumnRadius",
            "outerEdgeHeight": "foundationOuterEdgeHeight",
            "coneHeight": "foundationConeHeight",
            "columnHeight": "foundationColumnHeight",
            "buriedDepth": "foundationBuriedDepth",
            "pileDiameter": "pileOuterDiameter",
            "pileCount": "pileCount",
            "averagePileLength": "pileLength",
            "pileRingCount": "pileRingCount",
        }
        source = table.get("_sourceTable") or {}
        evidence_text = source.get("caption") or table.get("name") or "基础断面表"
        for column_key, field_code in mapping.items():
            if field_code in skip_codes:
                continue
            value = values.get(column_key)
            if value in (None, "", [], {}):
                continue
            existing = fields.get(field_code)
            if existing is not None and existing.value is not None:
                continue
            name, unit = self.required_field_meta.get(field_code, (field_code, None))
            self._set_field(
                fields,
                field_code,
                name,
                value,
                unit,
                str(evidence_text),
                source_type="table",
                meta={"resolver": "wind_foundation_profile_table", "sectionPath": ["风机基础"], "tableId": source.get("tableId")},
            )

    def _wind_foundation_quantity_field_values(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str, dict[str, Any]]]:
        values: dict[str, tuple[str, Any, str | None, str, dict[str, Any]]] = {}
        for table in sorted(ast.tables, key=lambda item: item.order):
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_text = self._clean_text(" ".join(table.section_path or []))
            table_text = self._matrix_text(matrix)
            context = f"{caption}\n{section_text}\n{table_text[:800]}"
            if not any(keyword in context for keyword in ("风机基础工程量", "风电机组基础工程量", "风机基础工程量表")):
                continue
            for row in matrix:
                row_text = self._clean_text(" ".join(row))
                if not row_text:
                    continue
                if "开挖" in row_text and "windFoundationExcavationQuantity" not in values:
                    value = self._wind_foundation_min_numeric_value(row)
                    if value is not None:
                        values["windFoundationExcavationQuantity"] = self._wind_foundation_table_override(
                            "风机基础开挖量", value, "m³", row, table, caption, "wind_foundation_quantity_table"
                        )
                if "回填" in row_text and "windFoundationBackfillQuantity" not in values:
                    value = self._wind_foundation_min_numeric_value(row)
                    if value is not None:
                        values["windFoundationBackfillQuantity"] = self._wind_foundation_table_override(
                            "风机基础回填量", value, "m³", row, table, caption, "wind_foundation_quantity_table"
                        )
                if "风机基础" not in row_text and "基础" not in row_text:
                    continue
                for grade, code in (
                    ("C15", "windFoundationC15Concrete"),
                    ("C20", "windFoundationC20Concrete"),
                    ("C40", "windFoundationC40Concrete"),
                    ("C45", "windFoundationC45Concrete"),
                ):
                    if code in values or grade not in row_text:
                        continue
                    value = self._wind_foundation_concrete_value(row, grade)
                    if value is None:
                        continue
                    values[code] = self._wind_foundation_table_override(
                        f"风机基础-{grade}混凝土", f"{grade}混凝土：{value}m³", "m³", row, table, caption, "wind_foundation_quantity_table"
                    )
        return values

    def _wind_foundation_table_override(
        self,
        name: str,
        value: Any,
        unit: str | None,
        row: list[str],
        table: DocumentTable,
        caption: str,
        resolver: str,
    ) -> tuple[str, Any, str | None, str, dict[str, Any]]:
        return (
            name,
            value,
            unit,
            self._clean_text(" | ".join(row)),
            {
                "resolver": resolver,
                "sectionPath": list(table.section_path or ["风机基础"]),
                "tableId": table.id,
                "caption": caption or table.caption or self._caption_before_table_from_table(table),
                "matchMethod": "row_keyword_min_numeric",
            },
        )

    def _wind_foundation_min_numeric_value(self, row: list[str]) -> Any:
        numbers = [
            value
            for index, value in self._numeric_cells(row)
            if index > 0 and not (isinstance(value, (int, float)) and 0 < value < 100 and self._looks_like_unit_cell(row[index]))
        ]
        if not numbers:
            return None
        return min(numbers)

    def _wind_foundation_concrete_value(self, row: list[str], grade: str) -> Any:
        joined = " | ".join(row)
        match = re.search(rf"{grade}[^0-9]{{0,20}}([0-9]+(?:\.[0-9]+)?)\s*(?:m³|m3|立方米)?", joined, flags=re.IGNORECASE)
        if match:
            return self._normalize_scalar(match.group(1))
        numbers = [value for index, value in self._numeric_cells(row) if index > 0]
        return numbers[-1] if numbers else None

    def _clear_ambiguous_maintenance_road_length_field(self, fields: dict[str, ParsedField], ast: DocumentAST) -> None:
        maintenance_field = fields.get("maintenanceRoadLength")
        site_field = fields.get("siteRoadLength")
        if maintenance_field is not None and site_field is not None and self._should_clear_ambiguous_maintenance_road_length(maintenance_field.value, site_field.value, ast):
            fields.pop("maintenanceRoadLength", None)

    def _clear_invalid_site_road_length_field(self, fields: dict[str, ParsedField]) -> None:
        field = fields.get("siteRoadLength")
        if field is None or field.value is None:
            return
        if any(getattr(evidence, "meta", {}).get("resolver") == "road_parameters_text_combined" for evidence in field.evidence):
            return
        text = " ".join(evidence.text or "" for evidence in field.evidence)
        if "路基" in text or "路面" in text:
            value_text = self._number_regex_with_optional_trailing_zeros(float(field.value))
            explicit_pattern = rf"(?:场内(?:通往各风机点位的)?(?:运输|施工)?道路|场内道路)\s*(?:(?:长(?:度)?|长度|约)[^0-9。；;\n]{{0,16}})?{value_text}\s*(?:km|公里|千米)"
            if not re.search(explicit_pattern, text, flags=re.IGNORECASE):
                fields.pop("siteRoadLength", None)

    def _apply_road_parameter_field_overrides(self, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        rows = [row for row in details.get("roadParameters", []) if isinstance(row, dict)]
        if not rows:
            return
        row = rows[0]
        for field_code in self.ROAD_PARAMETER_FIELD_CODES:
            if field_code in skip_codes:
                continue
            value = self._empty_to_none(row.get(field_code))
            if value is None:
                continue
            name, unit = self.required_field_meta.get(field_code, (field_code, None))
            evidence = self._combined_field_evidence_from_row(row, field_code, "roadParameters")
            if evidence is not None:
                self._set_field_with_evidence(fields, field_code, name, value, unit, [evidence])
            else:
                self._set_field(fields, field_code, name, value, unit, "道路参数正文/表格组合字段来源。", source_type="paragraph", meta={"resolver": "road_parameters_text_combined"})

    def _road_text_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        if "offsiteTrafficConditionDescription" in skip_codes:
            return {}
        value = self._offsite_traffic_condition_description(ast)
        if value in (None, ""):
            return {}
        return {
            "offsiteTrafficConditionDescription": (
                "场外交通运输条件描述",
                value,
                None,
                value,
                "paragraph",
                {"resolver": "deterministic_road_text", "sectionPath": ["道路"]},
            )
        }

    def _offsite_traffic_condition_description(self, ast: DocumentAST) -> str | None:
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not text or not any(keyword in text for keyword in ("本工程对外交通", "本项目场外交通")):
                continue
            for sentence in self._sentences(text):
                if any(keyword in sentence for keyword in ("本工程对外交通", "本项目场外交通")):
                    return self._clean_text(sentence).rstrip("。；;")
            return text.rstrip("。；;")
        return None

    def _wind_foundation_text_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        blocks = self._configured_text_blocks(
            ast,
            "wind_foundation",
            ["风机基础"],
            ["风机基础", "风电机组基础", "补充逻辑", "承台直径", "承台底面半径", "台柱半径", "桩数", "桩径"],
        )
        text = "\n".join(self._clean_text(block.text or "") for block in blocks if block.text)
        if not text:
            return {}
        specs = self._configured_field_rules("wind_foundation", self._default_wind_foundation_text_field_rules())
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, rule in specs.items():
            if code in skip_codes:
                continue
            value = self._value_from_configured_patterns(text, rule)
            if value in (None, "", [], {}):
                continue
            overrides[code] = (
                str(rule.get("name") or self.required_field_meta.get(code, (code, None))[0]),
                value,
                rule.get("unit") or self.required_field_meta.get(code, (None, None))[1],
                self._field_evidence_text_for_value(ast, value, [str(item) for item in (rule.get("evidence_keywords") or [])]),
                "paragraph",
                {"resolver": "deterministic_wind_foundation_text", "sectionPath": ["风机基础"]},
            )
        self._add_wind_foundation_radius_derived_text_values(overrides, ast)
        return overrides

    def _default_wind_foundation_text_field_rules(self) -> dict[str, dict[str, Any]]:
        return {
            "windFoundationType": {
                "name": "风机基础类型",
                "unit": None,
                "value_type": "text",
                "evidence_keywords": ["风机基础", "采用", "基础"],
                "patterns": [
                    r"(?:本工程|本项目|风机基础)[^。；;\n]{0,30}?采用\s*([^。；;\n]{0,30}?基础)",
                    r"风机基础(?:型式|形式|类型)[为采用：:\s]*([^。；;\n]{0,30}?基础)",
                ],
            },
            "foundationCapBottomRadius": {"name": "基础承台底面半径", "unit": "m", "value_type": "number", "evidence_keywords": ["承台底面半径"], "patterns": [r"(?:基础)?承台(?:底面)?半径\s*R?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationTopRadius": {"name": "棱台顶面半径R1", "unit": "m", "value_type": "number", "evidence_keywords": ["顶面半径"], "patterns": [r"(?:基础圆台|棱台)?顶面半径\s*R1\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationColumnRadius": {"name": "承台台柱半径R2", "unit": "m", "value_type": "number", "evidence_keywords": ["台柱半径"], "patterns": [r"(?:承台)?台柱半径\s*R2\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationOuterEdgeHeight": {"name": "承台底板外缘高度H1", "unit": "m", "value_type": "number", "evidence_keywords": ["外缘高度"], "patterns": [r"(?:承台)?底板外缘高度\s*H1\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationConeHeight": {"name": "承台底板棱台高度H2", "unit": "m", "value_type": "number", "evidence_keywords": ["棱台高度"], "patterns": [r"(?:承台)?底板(?:棱台|台)高度\s*H2\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationColumnHeight": {"name": "台柱高度H3", "unit": "m", "value_type": "number", "evidence_keywords": ["台柱高度"], "patterns": [r"台柱高度\s*H3\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationBuriedDepth": {"name": "基础埋深Hd", "unit": "m", "value_type": "number", "evidence_keywords": ["埋深"], "patterns": [r"(?:基础)?埋深\s*Hd?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "pileOuterDiameter": {"name": "桩截面外径(直径)", "unit": "m", "value_type": "number", "evidence_keywords": ["桩截面外径"], "patterns": [r"桩截面外径(?:\s*[（(]直径[）)])?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?", r"桩径\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "pileCount": {"name": "桩数", "unit": "根", "value_type": "number", "evidence_keywords": ["桩数"], "patterns": [r"桩数\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:根)?"]},
            "pileLength": {"name": "桩长", "unit": "m", "value_type": "number", "evidence_keywords": ["桩长"], "patterns": [r"单桩长(?:为)?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?", r"桩长(?:为)?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "pileRingCount": {"name": "桩圈数", "unit": None, "value_type": "number", "evidence_keywords": ["桩圈数"], "patterns": [r"桩圈数\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:圈)?"]},
            "foundationCapDiameter": {"name": "承台直径", "unit": "m", "value_type": "number", "evidence_keywords": ["承台直径"], "patterns": [r"承台直径(?:为)?\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
            "foundationColumnDiameter": {"name": "台柱直径", "unit": "m", "value_type": "number", "evidence_keywords": ["台柱直径"], "patterns": [r"台柱直径\s*[:：=＝]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)?"]},
        }

    def _add_wind_foundation_radius_derived_text_values(
        self,
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]],
        ast: DocumentAST,
    ) -> None:
        derived_specs = [
            ("foundationCapDiameter", "承台直径", "foundationCapBottomRadius", "承台底面半径"),
            ("foundationColumnDiameter", "台柱直径", "foundationColumnRadius", "台柱半径"),
        ]
        for target_code, target_name, source_code, source_name in derived_specs:
            if target_code in overrides or source_code not in overrides:
                continue
            source_value = overrides[source_code][1]
            if not isinstance(source_value, (int, float)):
                continue
            value = self._clean_number(float(source_value) * 2)
            evidence_text = f"{source_name}={source_value}，{target_name}按半径乘2计算"
            overrides[target_code] = (
                target_name,
                value,
                "m",
                self._field_evidence_text_for_value(ast, source_value, [source_name]) or evidence_text,
                "paragraph",
                {"resolver": "deterministic_wind_foundation_text", "sectionPath": ["风机基础"], "calculation": evidence_text},
            )

    def _apply_land_field_overrides(self, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]]) -> None:
        mapping = {
            "permanentLandWindFoundationArea": ("风机基础征地面积", "permanentLandArea", "windFoundation"),
            "permanentLandBoxTransformerArea": ("箱变基础征地面积", "permanentLandArea", "boxTransformerFoundation"),
            "permanentLandSubstationArea": ("升压站征地面积", "permanentLandArea", "substation110kv"),
            "permanentLandCollectorTowerArea": ("\u6c38\u4e45\u5360\u5730-\u96c6\u7535\u7ebf\u8def\u6746\u5854\u5f81\u5730", "permanentLandArea", "collectorTower"),
            "permanentLandAccessRoadArea": ("进站道路征地面积", "permanentLandArea", "accessRoad"),
            "permanentLandTotalArea": ("永久征地总面积", "permanentLandArea", "total"),
            "longTermLeaseCableBuriedArea": ("\u957f\u671f\u79df\u5730-\u7535\u7f06\u76f4\u57cb\u5f81\u5730", "longTermLeaseArea", "directBuriedCable"),
            "longTermLeasePermanentRoadArea": ("\u957f\u671f\u79df\u5730-\u573a\u5185\u6c38\u4e45\u9053\u8def", "longTermLeaseArea", "permanentRoad"),
            "longTermLeaseMaintenanceRoadArea": ("检修道路征地总面积", "longTermLeaseArea", "maintenanceRoad"),
            "longTermLeaseAccessRoadArea": ("进站道路征地总面积", "longTermLeaseArea", "accessRoad"),
            "longTermLeaseTowerFoundationArea": ("铁塔基础征地总面积", "longTermLeaseArea", "towerFoundation"),
            "longTermLeaseTotalArea": ("长期征地总面积", "longTermLeaseArea", "total"),
            "temporaryLandPlatformArea": ("施工吊装平台征地总面积", "temporaryLandArea", "platform"),
            "temporaryLandConstructionRoadArea": ("施工道路征地总面积", "temporaryLandArea", "temporaryRoad"),
            "temporaryLandDirectBuriedCableArea": ("直埋电缆征地总面积", "temporaryLandArea", "directBuriedCable"),
            "temporaryLandConstructionSiteArea": ("临时施工区征地总面积", "temporaryLandArea", "constructionSite"),
            "temporaryLandLivingArea": ("\u4e34\u65f6\u5360\u5730-\u751f\u6d3b\u4e34\u5efa", "temporaryLandArea", "livingFacility"),
            "temporaryLandTotalArea": ("临时征地总面积", "temporaryLandArea", "total"),
        }
        for code, (name, detail_key, value_key) in mapping.items():
            rows = details.get(detail_key) or []
            if not rows:
                continue
            value = rows[0].get(value_key)
            if value is not None:
                self._set_field(fields, code, name, value, "m2", f"{detail_key}.{value_key}")
