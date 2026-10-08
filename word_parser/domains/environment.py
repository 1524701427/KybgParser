"""Environmental and water conservation investment extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST


class EnvironmentRulesMixin:
    def _environmental_water_conservation_scalar_values(
        self, ast: DocumentAST, skip_codes: set[str] | None = None
    ) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        specs = [
            ("environmentalInvestment", "环保总投资", "环境保护投资", "环境保护"),
            ("waterSoilConservationInvestment", "水保总投资", "水土保持投资", "水土保持"),
        ]
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, name, text_keyword, table_keyword in specs:
            if code in skip_codes:
                continue
            text_match = self._environmental_investment_from_text(ast, text_keyword)
            if text_match is not None:
                value, evidence_text = text_match
                source_type = "paragraph"
                meta = {"resolver": "deterministic_environment_text", "sectionPath": ["环保水保"]}
            else:
                table_match = self._environmental_investment_from_other_cost_table(ast, table_keyword)
                if table_match is None:
                    continue
                value, evidence_text = table_match
                source_type = "table"
                meta = {"resolver": "deterministic_environment_other_cost_table", "sectionPath": ["环保水保"]}
            overrides[code] = (name, value, "万元", evidence_text, source_type, meta)
        return overrides

    def _environmental_investment_from_text(self, ast: DocumentAST, keyword: str) -> tuple[Any, str] | None:
        pattern = rf"{keyword}[^0-9。；;\n]{{0,20}}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>万元|元)?"
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if keyword not in text:
                continue
            match = re.search(pattern, text)
            if not match:
                continue
            value = self._environmental_investment_value(match.group("value"), match.group("unit") or "万元")
            if value is not None:
                return value, text
        return None

    def _environmental_investment_from_other_cost_table(self, ast: DocumentAST, keyword: str) -> tuple[Any, str] | None:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._matrix_text(matrix)
            if "其他费用概算表" not in f"{caption}\n{table_text}":
                continue
            header_index, total_index = self._environmental_other_cost_total_column(matrix)
            if total_index is None:
                continue
            for row in matrix[header_index + 1 :]:
                row_text = self._clean_text(" ".join(row))
                if keyword not in row_text or total_index >= len(row):
                    continue
                value = self._normalize_table_cell(row[total_index])
                if isinstance(value, (int, float)):
                    return value, "\n".join(part for part in (caption, row_text) if part)
        return None

    def _environmental_other_cost_total_column(self, matrix: list[list[str]]) -> tuple[int, int | None]:
        for index, row in enumerate(matrix[:5]):
            for column_index, cell in enumerate(row):
                if "合计" in self._clean_text(cell):
                    return index, column_index
        return 0, None

    def _environmental_investment_value(self, value_text: str, unit: str) -> Any:
        value = self._normalize_scalar(value_text)
        if not isinstance(value, (int, float)):
            return None
        if unit == "元":
            return self._clean_number(float(value) / 10000)
        return value
