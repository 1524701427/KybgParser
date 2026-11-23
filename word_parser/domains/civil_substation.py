"""升压站土建表格和占地参数抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST


class SubstationCivilRulesMixin:
    """升压站土建表格和占地参数抽取，通过 CivilRulesMixin 组合到结果构建器。"""

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
        match = re.search(domain_regex(self, "civil_substation", "search_001", r"[0-9]+(?:\.[0-9]+)?"), str(value).replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
        if number > 100:
            number /= 1000
        return self._clean_number(number / 2)

    def _build_substation_civil_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        row = self._substation_civil_combined_row(ast)
        return {"substationCivilCombined": [row] if row else []}

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
