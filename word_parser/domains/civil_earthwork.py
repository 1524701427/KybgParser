"""土石方平衡、开挖回填和弃渣数据抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import math
import re
from typing import Any

from word_parser.document.ast.document import DocumentAST
from word_parser.document.ast.evidence import ParsedField


class EarthworkRulesMixin:
    """土石方平衡、开挖回填和弃渣数据抽取，通过 CivilRulesMixin 组合到结果构建器。"""

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
                    "excavation": self._earthwork_total(rows, "excavation"),
                    "backfill": self._earthwork_total(rows, "backfill"),
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
        return bool(re.search(domain_regex(self, "civil_earthwork", "search_001", r"万\s*m\s*[³3]"), unit_text, flags=re.IGNORECASE))

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
                excavation = self._earthwork_numeric_value(self._row_value_by_header(header, source_row, ["土方开挖", "开挖"]))
                backfill = self._earthwork_numeric_value(self._row_value_by_header(header, source_row, ["土方回填", "回填"]))
                if excavation is None and backfill is None:
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
                rows.append(explicit_total or {"item": "合计", "excavation": self._earthwork_total(rows, "excavation"), "backfill": self._earthwork_total(rows, "backfill")})
                return rows
        return []

    def _earthwork_numeric_value(self, value: Any) -> int | float | None:
        """只接受可用于土石方体积计算的有限数值。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value if math.isfinite(value) else None

    def _earthwork_total(self, rows: list[dict[str, Any]], key: str) -> int | float:
        """汇总已校验的土石方数值，忽略表格中的文字。"""
        values = (self._earthwork_numeric_value(row.get(key)) for row in rows)
        return self._clean_number(sum(value for value in values if value is not None))

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
            rows.append({"item": "合计", "excavation": self._earthwork_total(rows, "excavation"), "backfill": self._earthwork_total(rows, "backfill")})
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
                if self._earthwork_numeric_value(value) is None:
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
        estimate_values = self._collector_earthwork_from_estimate_tables(ast)
        for code, (value, sources) in estimate_values.items():
            existing = fields.get(code)
            if code in skip_codes or (existing is not None and existing.status == "PASS" and existing.value is not None):
                continue
            name, unit = self.required_field_meta.get(code, (code, "m3"))
            evidences = [
                evidence for source in sources
                if (evidence := self._combined_field_evidence_from_row(
                    {"_cellSources": {code: source}}, code,
                    "investmentConstructionAuxiliary" if "施工辅助" in source["source"].get("caption", "") else "investmentBuilding"
                )) is not None
            ]
            if evidences:
                self._set_field_with_evidence(fields, code, name, value, unit, evidences)
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

    def _collector_earthwork_from_estimate_tables(
        self, ast: DocumentAST
    ) -> dict[str, tuple[Any, list[dict[str, Any]]]]:
        """仅从集电工程下的土石方行读取工程量。"""
        totals = {
            "collectorLineEarthworkExcavation": 0.0,
            "collectorLineEarthworkBackfill": 0.0,
        }
        sources: dict[str, list[dict[str, Any]]] = {code: [] for code in totals}
        tables = self._original_tables_for_spec(ast, {"key_prefix": "investmentOriginalTable"})
        seen_tables: set[str] = set()
        for table in tables:
            if table.id in seen_tables:
                continue
            seen_tables.add(table.id)
            previous_paragraphs = [
                block for block in ast.blocks
                if block.type == "paragraph" and block.order < table.order
            ][-5:]
            nearby_titles = (
                self._clean_text(block.text or "")
                for block in reversed(previous_paragraphs)
                if not any(block.order < other.order < table.order for other in ast.tables)
            )
            caption = next((title for title in (
                self._clean_text(table.caption or ""),
                self._clean_text(self._caption_before_table_from_table(table) or ""),
                self._clean_text(self._caption_before_table(ast, table) or ""),
                *nearby_titles,
            ) if re.search(domain_regex(self, "civil_earthwork", "search_002", r"(?:建筑|施工辅助)工程概算表"), title)), "")
            if not caption:
                continue
            matrix = self._table_matrix(table)
            header_index = next((index for index, row in enumerate(matrix[:6]) if any("项目名称" in cell for cell in row) and any("数量" in cell for cell in row)), None)
            if header_index is None:
                continue
            header = matrix[header_index]
            label_column = next(index for index, cell in enumerate(header) if "项目名称" in cell)
            quantity_column = next(index for index, cell in enumerate(header) if "数量" in cell)
            unit_column = next((index for index, cell in enumerate(header) if "单位" in cell), None)
            serial_column = next((index for index, cell in enumerate(header) if "序号" in cell), None)
            in_collector = "集电线路" in caption
            for row_index, row in enumerate(matrix[header_index + 1:], start=header_index + 1):
                label = self._clean_text(row[label_column] if label_column < len(row) else "")
                serial = self._clean_text(row[serial_column] if serial_column is not None and serial_column < len(row) else "")
                if not label:
                    continue
                is_major_heading = bool(re.fullmatch(domain_regex(self, "civil_earthwork", "fullmatch_003", r"[一二三四五六七八九十]+"), serial) or re.match(domain_regex(self, "civil_earthwork", "match_004", r"第[一二三四五六七八九十\d]+部分"), label))
                if re.search(domain_regex(self, "civil_earthwork", "search_005", r"集电线路|集电工程|集电系统"), label) and (is_major_heading or "工程" in label):
                    in_collector = True
                    continue
                if is_major_heading or ("工程" in label and re.search(domain_regex(self, "civil_earthwork", "search_006", r"风电机组|升压站|道路|其他工程"), label)):
                    in_collector = False
                if not in_collector:
                    continue
                code = None
                if re.search(domain_regex(self, "civil_earthwork", "search_007", r"土(?:石)?方?开挖"), label):
                    code = "collectorLineEarthworkExcavation"
                elif re.search(domain_regex(self, "civil_earthwork", "search_008", r"土(?:石)?方?回填|回填土"), label):
                    code = "collectorLineEarthworkBackfill"
                if code is None:
                    continue
                unit = self._clean_text(row[unit_column] if unit_column is not None and unit_column < len(row) else "")
                if unit and not re.search(domain_regex(self, "civil_earthwork", "search_009", r"m\s*[³3]|立方米"), unit, re.I):
                    continue
                value = self._normalize_table_cell(row[quantity_column] if quantity_column < len(row) else "")
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                totals[code] += float(value)
                source = self._table_cell_source(
                    table, row_index, quantity_column,
                    "建筑/施工辅助工程概算表中集电线路工程分项的土方工程量。",
                    resolver="collector_earthwork_estimate_table",
                )
                source["source"]["caption"] = caption
                sources[code].append(source)
        return {
            code: (self._clean_number(total), sources[code])
            for code, total in totals.items() if sources[code]
        }

    def _earthwork_spoil_disposal_field_values(
        self, ast: DocumentAST
    ) -> list[tuple[str, str, Any, str, str, list[str]]]:
        """从局部文本中提取弃渣场数量和总占地面积。"""
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
                    domain_regex(self, "civil_earthwork", "search_010", r"(?:设置|设有|布置|新建|拟设(?:置)?|考虑设置)[^0-9。；;]{0,16}([0-9]+(?:\.[0-9]+)?)\s*个\s*弃渣场"),
                    text,
                ) or re.search(domain_regex(self, "civil_earthwork", "search_011", r"弃渣场[^0-9。；;]{0,16}([0-9]+(?:\.[0-9]+)?)\s*个"), text)
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
                    domain_regex(self, "civil_earthwork", "search_012", r"(?:总占地面积|占地面积)\s*(?:约为|约|为)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m\s*[²2]|㎡|平方米)"),
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
