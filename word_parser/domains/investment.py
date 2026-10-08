"""Investment estimate, equipment costs and pricing basis extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST

from parser_engine.document.ast.evidence import ParsedField


class InvestmentRulesMixin:
    def _investment_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = {
            "totalProjectCost": None,
            "equipmentPurchaseCost": None,
            "installationCost": None,
            "constructionCost": None,
            "mainEquipmentUnitPrice": None,
            "materialPriceLevel": None,
            "unitKwStaticInvestment": None,
            "dynamicInvestment": None,
        }
        header: list[str] | None = None
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if not any(keyword in text for keyword in ("工程总概算", "工程总投资合计", "动态总投资", "单位千瓦静态投资", "设备及安装工程概算")):
                continue
            header = self._header_row(matrix, ["设备购置费", "合计"]) or header
            for source_row in matrix:
                label = self._row_label(source_row)
                if "工程总投资合计" in label or "动态投资合计" in label or "动态总投资" in label:
                    row["totalProjectCost"] = self._row_value_by_header(header, source_row, ["合计"]) or self._amount_numeric_cell(source_row)
                elif "静态总投资" in label and row["totalProjectCost"] is None:
                    row["totalProjectCost"] = self._row_value_by_header(header, source_row, ["合计"]) or self._amount_numeric_cell(source_row)
                elif "单位千瓦静态投资" in label:
                    row["unitKwStaticInvestment"] = self._row_value_by_header(header, source_row, ["合计"]) or self._amount_numeric_cell(source_row)
                elif "单位千瓦动态" in label or "动态 投资" in label:
                    row["dynamicInvestment"] = self._row_value_by_header(header, source_row, ["合计"]) or self._amount_numeric_cell(source_row)
                elif "施工辅助工程" in label and row["constructionCost"] is None and header:
                    row["constructionCost"] = self._row_value_by_header(header, source_row, ["建筑及安装工程费", "建筑安装工程费"])
                elif "设备及安装工程" in label:
                    if header:
                        row["equipmentPurchaseCost"] = row["equipmentPurchaseCost"] or self._row_value_by_header(header, source_row, ["设备购置费", "设备费"])
                        row["installationCost"] = row["installationCost"] or self._installation_total_from_row(source_row)
        detailed_installation = self._equipment_installation_totals_from_document(ast)
        for key, value in detailed_installation.items():
            if value is not None:
                row[key] = value
        material_level = self._material_price_level_from_document(ast)
        if material_level is not None:
            row["materialPriceLevel"] = material_level
        return self._schema_row_table("investmentEstimate", row) if any(value is not None for value in row.values()) else None

    def _investment_estimate_original_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        """Return the detailed engineering estimate table instead of the compressed summary row."""
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if "工程总概算表" not in text:
                continue
            if "项目名称" not in text or "合计" not in text:
                continue
            if not any("工程静态投资" in self._row_label(row) for row in matrix):
                continue
            header_index = next((index for index, row in enumerate(matrix) if "项目名称" in self._row_label(row) and "合计" in " ".join(row)), None)
            if header_index is None:
                continue
            header = [self._clean_text(cell).replace("\x0b", "") for cell in matrix[header_index]]
            rows: list[list[Any]] = []
            for row in matrix[header_index + 1 :]:
                if not any(self._clean_text(cell) for cell in row):
                    continue
                padded = list(row[: len(header)])
                if len(padded) < len(header):
                    padded.extend([""] * (len(header) - len(padded)))
                rows.append([self._normalize_table_cell(cell) for cell in padded])
            if rows:
                return {
                    "key": "investmentEstimate",
                    "name": "15.2.1工程总概算表",
                    "columns": header,
                    "data": rows,
                }
        return None

    def _installation_total_from_row(self, row: list[str]) -> Any:
        numbers = self._numeric_cells(row)
        if len(row) >= 12:
            value = self._normalize_table_cell(row[10])
            if isinstance(value, (int, float)):
                return value
        return numbers[-2][1] if len(numbers) >= 2 else None

    def _equipment_installation_totals_from_document(self, ast: DocumentAST) -> dict[str, Any]:
        result: dict[str, Any] = {"equipmentPurchaseCost": None, "installationCost": None}
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if "设备及安装工程" not in text or "安装工程费" not in text:
                continue
            for row in matrix:
                label = self._row_label(row)
                if "设备及安装工程" not in label:
                    continue
                if len(row) >= 12:
                    equipment = self._normalize_table_cell(row[7])
                    installation = self._normalize_table_cell(row[8])
                else:
                    equipment = self._normalize_table_cell(row[6]) if len(row) > 6 else None
                    installation = self._normalize_table_cell(row[7]) if len(row) > 7 else None
                if isinstance(equipment, (int, float)):
                    result["equipmentPurchaseCost"] = equipment
                if isinstance(installation, (int, float)):
                    result["installationCost"] = installation
                if result["equipmentPurchaseCost"] is not None and result["installationCost"] is not None:
                    return result
        return result

    def _material_price_level_from_document(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        patterns = [
            r"(按[^。；;\n]{0,60}?(?:信息价|市场价格)[^。；;\n]{0,80}?确定)",
            r"([0-9]{4}\s*年\s*[0-9]{1,2}\s*月份材料价格水平)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_text_value(match.group(1).strip())
        return None

    def _apply_investment_summary_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        for code, name, value, unit, evidence_text in self._investment_summary_field_values(ast):
            if code in skip_codes or value is None:
                continue
            existing = fields.get(code)
            if existing is not None and existing.value is not None and any(evidence.source_type == "table" for evidence in existing.evidence):
                continue
            self._set_field(
                fields,
                code,
                name,
                value,
                unit,
                evidence_text,
                source_type="table",
                meta={"resolver": "investment_summary_table", "sectionPath": ["技经概算"]},
            )

    def _investment_basis_scalar_values(
        self, ast: DocumentAST, skip_codes: set[str] | None = None
    ) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        text = self._investment_basis_context_text(ast)
        specs = {
            "investmentCostStandard": ("费用标准", self._investment_cost_standard_from_text(text), ["陆上风电场工程设计概算编制规定及费用标准", "路上风电场工程设计概算编制规定及费用标准"]),
            "investmentQuotaSystem": ("定额体系", self._investment_quota_system_from_text(text), ["陆上风电场工程概算定额", "路上风电场工程概算定额"]),
            "investmentPriceLevel": ("价格水平", self._investment_price_level_from_text(text), ["价格水平编制"]),
        }
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, (name, value, keywords) in specs.items():
            if code in skip_codes or value in (None, "", [], {}):
                continue
            overrides[code] = (
                name,
                value,
                None,
                self._field_evidence_text_for_value(ast, value, keywords),
                "paragraph",
                {"resolver": "deterministic_investment_basis_text", "sectionPath": ["技经概算"]},
            )
        return overrides

    def _investment_basis_context_text(self, ast: DocumentAST) -> str:
        parts: list[str] = []
        keywords = ("概算编制规定", "费用标准", "概算定额", "价格水平编制", "价格水平")
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            section_text = " ".join(str(part) for part in (block.section_path or []))
            if any(keyword in f"{section_text} {text}" for keyword in (*keywords, "技经概算", "设计概算", "投资概算")):
                parts.append(text)
        parts.extend(
            self._clean_text(str(page.get("text", "")))
            for page in (ast.meta.get("pdf_page_texts") or [])
            if isinstance(page, dict) and any(keyword in str(page.get("text", "")) for keyword in keywords)
        )
        return "\n".join(parts)

    def _investment_cost_standard_from_text(self, text: str) -> str | None:
        match = re.search(r"《?\s*(?P<title>[陆路]上风电场工程设计概算编制规定及费用标准)\s*》?", text)
        if not match:
            return None
        title = match.group("title").replace("路上", "陆上")
        return f"《{title}》"

    def _investment_quota_system_from_text(self, text: str) -> str | None:
        pattern = r"《?\s*(?P<title>[陆路]上风电场工程概算定额)\s*》?\s*(?:[（(]?\s*(?P<code>NB\s*/\s*T\s*31010\s*[-－—]\s*2019)\s*[）)]?)?"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        title = match.group("title").replace("路上", "陆上")
        code = match.group("code")
        if code:
            normalized_code = re.sub(r"\s+", "", code).replace("－", "-").replace("—", "-")
            return f"《{title}》({normalized_code})"
        return f"《{title}》"

    def _investment_price_level_from_text(self, text: str) -> str | None:
        patterns = [
            r"按[^。；;\n]{0,30}?(?P<year>[0-9]{4})\s*年\s*(?:第\s*)?(?P<quarter>[一二三四1234])\s*季度[^。；;\n]{0,20}?价格水平编制",
            r"(?P<year>[0-9]{4})\s*年\s*(?:第\s*)?(?P<quarter>[一二三四1234])\s*季度[^。；;\n]{0,20}?价格水平",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return f"{match.group('year')}年第{self._quarter_number(match.group('quarter'))}季度"
        return None

    def _quarter_number(self, value: str) -> str:
        return {"一": "1", "二": "2", "三": "3", "四": "4"}.get(value, value)

    def _investment_summary_field_values(self, ast: DocumentAST) -> list[tuple[str, str, Any, str | None, str]]:
        values: list[tuple[str, str, Any, str | None, str]] = []
        found_codes: set[str] = set()
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            table_text = self._matrix_text(matrix)
            context = f"{table.caption or ''} {' / '.join(table.section_path)} {table_text}"
            if not any(keyword in context for keyword in ("工程总概算", "工程总投资", "静态总投资", "动态总投资", "单位千瓦静态投资")):
                continue
            header = self._header_row(matrix, ["合计"]) or self._header_row(matrix, ["项目名称"]) or matrix[0]
            for row in matrix:
                label = self._row_label(row)
                if not label:
                    continue
                for code, (name, unit, aliases) in self.INVESTMENT_SUMMARY_FIELD_ROWS.items():
                    if code in found_codes:
                        continue
                    if not any(alias in label for alias in aliases):
                        continue
                    value = self._row_value_by_header(header, row, ["合计（万元）", "合计", "总计"]) or self._amount_numeric_cell(row)
                    if value is None:
                        continue
                    values.append((code, name, value, unit, f"由工程总概算表“{label}”行抽取。"))
                    found_codes.add(code)
        return values
