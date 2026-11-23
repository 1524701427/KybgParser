"""风机基础与箱变基础参数和工程量抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex, domain_strings

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable
from word_parser.document.ast.evidence import ParsedField


class WindFoundationRulesMixin:
    """风机基础与箱变基础参数和工程量抽取，通过 CivilRulesMixin 组合到结果构建器。"""

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
            row["foundationType"] = row["foundationType"] or self._text_by_row_label(matrix, domain_strings(self, "civil_foundation", "list_001", ["基础形式", "地基处理措施"]))
            row["c20Concrete"] = row["c20Concrete"] or self._value_by_row_label(wind_rows, domain_strings(self, "civil_foundation", "list_002", ["垫层混凝土 C20", "垫层混凝土C20", "垫层及散水混凝土C20"]))
            row["c40Concrete"] = row["c40Concrete"] or self._value_by_row_label(wind_rows, domain_strings(self, "civil_foundation", "list_003", ["基础混凝土 C40", "基础混凝土C40", "基础混凝土 C45", "基础混凝土C45", "基础承台C40混凝土"]))
            row["rebar"] = row["rebar"] or self._value_by_row_label(wind_rows, domain_strings(self, "civil_foundation", "list_004", ["钢筋制作", "钢筋工程量", "钢筋制作与安装"]))
            row["steel"] = row["steel"] or self._value_by_row_label(wind_rows, domain_strings(self, "civil_foundation", "list_005", ["钢结构制作", "钢结构制作与安装"]))
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
            if active and re.match(domain_regex(self, "civil_foundation", "match_001", r"^(?:1\.2|2|二|三|四)\b"), code):
                break
            if active:
                rows.append(row)
        return rows

    def _wind_foundation_technical_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        """从风机基础断面/尺寸表中提取标准化基础参数表。

        参数：
            ast: 已完成结构和章节识别的文档 AST。

        返回：
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

        参数：
            matrix: 原始表格文本矩阵。
            aliases: 目标项目名别名。

        返回：
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

        参数：
            value: 表格单元格归一化后的值。

        返回：
            Any: 开头是数字时返回该数字，否则返回原值。
        """
        if not isinstance(value, str):
            return value
        match = re.match(domain_regex(self, "civil_foundation", "match_002", r"\s*([0-9]+(?:\.[0-9]+)?)"), value.replace(",", ""))
        if not match:
            return value
        return self._clean_number(float(match.group(1)))

    def _foundation_radius_value(self, matrix: list[list[str]]) -> Any:
        for row in matrix:
            label = self._row_label(row)
            if not any(alias in label for alias in ("基础承台底面半径", "底面半径", "圆形基础地面直径")):
                continue
            if "半径" not in label and not re.search(domain_regex(self, "civil_foundation", "search_003", r"\bR\b|R（|R\("), label):
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
            row["c30Concrete"] = row["c30Concrete"] or self._value_by_row_label(source, domain_strings(self, "civil_foundation", "list_006", ["基础混凝土C30", "混凝土 C30", "混凝土C30", "混凝土 C25", "混凝土C25", "混凝土（C25）", "混凝土（C30）", "混凝土量（C30）", "混凝土量（C25）", "基层混凝土量"]))
            row["c20Concrete"] = row["c20Concrete"] or self._value_by_row_label(source, domain_strings(self, "civil_foundation", "list_007", ["垫层混凝土", "垫层混凝土C20", "垫层混凝土 C20"]))
            row["rebarInstallation"] = row["rebarInstallation"] or self._value_by_row_label(source, domain_strings(self, "civil_foundation", "list_008", ["钢筋制作与安装", "基础钢筋", "钢筋（", "钢筋"]))
            row["steelInstallation"] = row["steelInstallation"] or self._value_by_row_label(source, domain_strings(self, "civil_foundation", "list_009", ["铁件制作安装", "钢结构制作与安装"]))
            if is_direct_quantity_table and row["c30Concrete"] is not None and row["rebarInstallation"] is not None:
                return self._box_foundation_result_table(row)
        return self._box_foundation_result_table(row) if any(value is not None for key, value in row.items() if key != "concreteGrade") else None

    def _box_foundation_concrete_grade(self, rows: list[list[str]]) -> str | None:
        text = self._matrix_text(rows)
        match = re.search(domain_regex(self, "civil_foundation", "search_004", r"C\s*([0-9]{2})"), text, flags=re.IGNORECASE)
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
            if active and re.match(domain_regex(self, "civil_foundation", "match_005", r"^(?:1\.3|2|二|三|四)\b"), code):
                break
            if active:
                rows.append(row)
        return rows

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
        return re.sub(domain_regex(self, "civil_foundation", "sub_006", r"，分布半径为[^，]+"), "", value)

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
            is_civil_quantity_table = "土建工程量表" in caption
            if not is_civil_quantity_table and not any(keyword in context for keyword in ("风机基础工程量", "风电机组基础工程量", "风机基础工程量表")):
                continue
            for row in matrix:
                row_text = self._clean_text(" ".join(row))
                if not row_text:
                    continue
                if "开挖" in row_text and (not is_civil_quantity_table or "风机基础" in row_text) and "windFoundationExcavationQuantity" not in values:
                    value = self._wind_foundation_min_numeric_value(row)
                    if value is not None:
                        values["windFoundationExcavationQuantity"] = self._wind_foundation_table_override(
                            "风机基础开挖量", value, "m³", row, table, caption, "wind_foundation_quantity_table"
                        )
                if "回填" in row_text and (not is_civil_quantity_table or "风机基础" in row_text) and "windFoundationBackfillQuantity" not in values:
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
        estimate_candidates: dict[str, list[tuple[Any, list[str], DocumentTable, str]]] = {}
        for table in sorted(ast.tables, key=lambda item: item.order):
            matrix = self._table_matrix(table)
            header = next((
                row for row in matrix
                if any("项目" in cell for cell in row)
                and any("数量" in cell or "工程量" in cell for cell in row)
                and any("单价" in cell for cell in row)
                and any("合计" in cell or "合价" in cell for cell in row)
            ), None)
            if header is None:
                continue
            name_index = next((index for index, cell in enumerate(header) if "项目" in cell), None)
            quantity_index = next((index for index, cell in enumerate(header) if "数量" in cell or "工程量" in cell), None)
            unit_index = next((index for index, cell in enumerate(header) if "单位" in cell), None)
            if name_index is None or quantity_index is None:
                continue
            scoped_rows = self._wind_foundation_rows(matrix)
            if not scoped_rows:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            for row in scoped_rows:
                if name_index >= len(row) or quantity_index >= len(row):
                    continue
                label = self._clean_text(row[name_index])
                if "混凝土" not in label or "桩" in label:
                    continue
                if unit_index is not None and unit_index < len(row) and self._clean_text(row[unit_index]) not in ("m3", "m³", "立方米", "方"):
                    continue
                quantity = self._normalize_table_cell(row[quantity_index])
                if not isinstance(quantity, (int, float)) or quantity <= 0:
                    continue
                for grade, code in (("C15", "windFoundationC15Concrete"), ("C20", "windFoundationC20Concrete"), ("C40", "windFoundationC40Concrete"), ("C45", "windFoundationC45Concrete")):
                    if code in values or not re.search(rf"(?<![A-Za-z0-9]){grade}(?!\d)", label, re.I):
                        continue
                    if grade in {"C15", "C20"} and "垫层" not in label:
                        continue
                    estimate_candidates.setdefault(code, []).append((quantity, row, table, caption))
        for grade, code in (("C15", "windFoundationC15Concrete"), ("C20", "windFoundationC20Concrete"), ("C40", "windFoundationC40Concrete"), ("C45", "windFoundationC45Concrete")):
            candidates = estimate_candidates.get(code) or []
            if code in values or len({candidate[0] for candidate in candidates}) != 1:
                continue
            quantity, row, table, caption = candidates[0]
            values[code] = self._wind_foundation_table_override(
                f"风机基础-{grade}混凝土", f"{grade}混凝土：{quantity}m³", "m³", row, table, caption,
                "wind_foundation_building_estimate", match_method="scoped_quantity_column",
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
        match_method: str = "row_keyword_min_numeric",
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
                "matchMethod": match_method,
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
        # 单位单独成格时，取紧随单位的工程量，避免把 m3 中的 3 误作数值。
        for index, cell in enumerate(row):
            if self._clean_text(cell) not in {"m3", "m³", "立方米"}:
                continue
            numbers_after_unit = [value for position, value in self._numeric_cells(row) if position > index]
            if numbers_after_unit:
                return numbers_after_unit[0]
        joined = " | ".join(row)
        match = re.search(rf"{grade}[^0-9]{{0,20}}([0-9]+(?:\.[0-9]+)?)\s*(?:m³|m3|立方米)?", joined, flags=re.IGNORECASE)
        if match:
            return self._normalize_scalar(match.group(1))
        numbers = [value for index, value in self._numeric_cells(row) if index > 0]
        return numbers[-1] if numbers else None

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

