"""道路表格、道路参数和场外交通条件抽取。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST
from word_parser.document.ast.evidence import ParsedField


class CivilRoadRulesMixin:
    """道路表格、道路参数和场外交通条件抽取，通过 CivilRulesMixin 组合到结果构建器。"""

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
        maintenance = self._maintenance_road_from_operational_roads(ast)
        for key, value in maintenance.items():
            if row.get(key) is None and value is not None:
                row[key] = value
        if any(value is not None for value in row.values()):
            source_text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text and any(keyword in block.text for keyword in ("道路", "路基", "路面", "进站", "进场")))
            if not source_text:
                source_text = "\n".join(self._table_text(table) for table in ast.tables if any(keyword in self._table_text(table) for keyword in ("道路", "路基", "路面", "进站", "进场")))
            row["_rowSource"] = self._combined_text_row_source(ast, source_text, "道路参数正文/表格组合字段来源。", "road_parameters_text_combined")
        return row if any(value is not None for value in row.values()) else None

    def _maintenance_road_from_operational_roads(self, ast: DocumentAST) -> dict[str, Any]:
        """将明确在投运后作为检修道路的场内新建、扩建道路合并。"""
        blocks = [self._clean_text(block.text or "") for block in ast.blocks if block.text]
        for index, text in enumerate(blocks):
            if "作为永久检修道路" not in text and "作为检修道路" not in text:
                continue
            context = " ".join(blocks[max(0, index - 2): index + 1])
            new = re.search(r"(?:场内新建道路|新建场内道路)(?:长(?:度)?)?\s*(?:约|为)?\s*([0-9]+(?:\.[0-9]+)?)\s*km", context, re.I)
            rebuilt = re.search(r"(?:场内扩建道路|扩建场内道路|场内改建道路|改建场内道路)(?:长(?:度)?)?\s*(?:约|为)?\s*([0-9]+(?:\.[0-9]+)?)\s*km", context, re.I)
            if not new or not rebuilt:
                continue
            width = re.search(r"路面宽(?:度)?\s*(?:为)?\s*([0-9]+(?:\.[0-9]+)?)\s*m", context, re.I)
            return {
                "maintenanceRoadLength": self._clean_number(float(new.group(1)) + float(rebuilt.group(1))),
                "maintenanceRoadPavementWidth": self._clean_number(float(width.group(1))) if width else None,
            }
        return {}

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
            # 单行仅有一个道路指标时是纵向数据行，不能当作宽表表头阻断后续取值。
            if sum(self._road_parameter_key_from_header(cell) is not None for cell in row) < 2:
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

    def _clear_unsupported_road_lengths(self, fields: dict[str, ParsedField], ast: DocumentAST) -> None:
        """排除从宽度、线路编号或材料等级误推断的道路长度。"""
        number = r"(?P<value>[0-9]+(?:\.[0-9]+)?)"
        unit = r"(?P<unit>km|公里|千米|m|米)"
        patterns_by_code = {
            "siteEntryRoadLength": [
                *self.field_configs.get("siteEntryRoadLength", {}).get("patterns", []),
                *(pattern for rule in self.field_configs.get("siteEntryRoadLength", {}).get("scalar_rules", [])
                  for pattern in rule.get("patterns", [])),
            ],
            "accessRoadLength": [
                rf"(?:新建)?进(?:站|升压站)道路(?:长(?:度)?|全长|总长)?\s*(?:约|为)?\s*{number}\s*{unit}",
                rf"进(?:站|升压站)道路\s*\|\s*{unit}\s*\|\s*{number}",
            ],
            "maintenanceRoadLength": [
                rf"(?:场内[^。；;\n]{{0,24}}?)?检修道路(?:长(?:度)?|全长|总长)?\s*(?:约|为)?\s*{number}\s*{unit}",
                rf"检修道路\s*\|\s*{unit}\s*\|\s*{number}",
            ],
        }
        document_texts = [block.text for block in ast.blocks if block.text and "道路" in block.text]
        for code, patterns in patterns_by_code.items():
            field = fields.get(code)
            if field is None or field.value is None:
                continue
            try:
                expected_km = float(field.value)
            except (TypeError, ValueError):
                fields.pop(code, None)
                continue
            supported = False
            evidence_texts = [evidence.text or "" for evidence in field.evidence]
            for source_text in [*evidence_texts, *document_texts]:
                for pattern in patterns:
                    for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
                        try:
                            measured = float(match.group("value"))
                        except (IndexError, ValueError):
                            continue
                        source_unit = match.groupdict().get("unit") or "km"
                        actual_km = measured / 1000 if source_unit.lower() in {"m", "米"} else measured
                        if abs(actual_km - expected_km) <= max(1e-6, abs(expected_km) * 1e-6):
                            supported = True
                            break
                    if supported:
                        break
                if supported:
                    break
            if not supported:
                if code == "maintenanceRoadLength":
                    composite = self._maintenance_road_from_operational_roads(ast).get(code)
                    supported = composite is not None and abs(float(composite) - expected_km) <= 1e-6
            if not supported:
                fields.pop(code, None)

    def _apply_road_parameter_field_overrides(self, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        rows = [row for row in details.get("roadParameters", []) if isinstance(row, dict)]
        if not rows:
            return
        row = rows[0]
        for field_code in self.ROAD_PARAMETER_FIELD_CODES:
            existing = fields.get(field_code)
            if field_code in skip_codes and (
                field_code not in {"maintenanceRoadLength", "maintenanceRoadPavementWidth"}
                or (existing is not None and existing.value is not None)
            ):
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
            section = " / ".join(block.section_path or [])
            has_context = any(keyword in text for keyword in ("本工程对外交通", "本项目场外交通")) or (
                "对外交通" in section and any(keyword in text for keyword in ("场区附近", "交通运输", "运输路线"))
            ) or ("对外交通" in text and any(keyword in text for keyword in ("场区附近", "交通运输", "运输路线")))
            if not text or not has_context:
                continue
            for sentence in self._sentences(text):
                if any(keyword in sentence for keyword in ("本工程对外交通", "本项目场外交通")):
                    return self._clean_text(sentence).rstrip("。；;")
            return text.rstrip("。；;")
        return None
