"""Financing, price, tax and financial indicator extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import ParsedField


class FinanceRulesMixin:
    def _financing_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = {
            "constructionPeriodYears": None,
            "projectTotalInvestment": None,
            "totalCost": None,
            "workingCapital": None,
            "workingCapitalUnitKwIndicator": None,
            "workingCapitalLoanRatio": None,
            "workingCapitalCapitalRatio": None,
            "workingCapitalLoanInterestRate": None,
            "constructionCapitalRatio": None,
            "constructionFundLoanRatio": None,
            "repaymentMethod": None,
            "repaymentPeriod": None,
            "annualLoanInterestRate": None,
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            header = matrix[0] if matrix else []
            data_row = matrix[1] if len(matrix) > 1 else []
            if "项目总投资" in " | ".join(header) and data_row:
                row["projectTotalInvestment"] = row["projectTotalInvestment"] or self._cell_at_alias(header, data_row, ["项目总投资"])
                row["totalCost"] = row["totalCost"] or self._cell_at_alias(header, data_row, ["总成本费用"])
                row["workingCapitalLoanRatio"] = row["workingCapitalLoanRatio"] or self._cell_at_alias(header, data_row, ["流动资金贷款比例", "贷款比例"])
                row["workingCapitalCapitalRatio"] = row["workingCapitalCapitalRatio"] or self._cell_at_alias(header, data_row, ["流动资本金比例", "流动资金自有资金比例"])
                row["workingCapitalLoanInterestRate"] = row["workingCapitalLoanInterestRate"] or self._cell_at_alias(header, data_row, ["流动资金贷款利率", "贷款利率"])
                row["constructionCapitalRatio"] = row["constructionCapitalRatio"] or self._cell_at_alias(header, data_row, ["建设资本金比例", "资本金比例"])
                row["constructionFundLoanRatio"] = row["constructionFundLoanRatio"] or self._cell_at_alias(header, data_row, ["建设资金贷款比例"])
                row["repaymentMethod"] = row["repaymentMethod"] or self._cell_at_alias(header, data_row, ["还款方式"])
                row["repaymentPeriod"] = row["repaymentPeriod"] or self._cell_at_alias(header, data_row, ["偿还年限"])
                row["annualLoanInterestRate"] = row["annualLoanInterestRate"] or self._cell_at_alias(header, data_row, ["年贷款利率"])
            if "项目总投资" in text and row["projectTotalInvestment"] is None:
                row["projectTotalInvestment"] = self._value_by_row_label(matrix, ["项目总投资"], prefer_total=True)
            if "总成本费用" in text and row["totalCost"] is None:
                row["totalCost"] = self._value_by_row_label(matrix, ["总成本费用"], prefer_total=True)
            if "流动资金" in text and row["workingCapital"] is None:
                row["workingCapital"] = self._value_by_row_label(matrix, ["流动资金"], prefer_total=True)
            if "流动资金" in text and row["workingCapitalUnitKwIndicator"] is None:
                row["workingCapitalUnitKwIndicator"] = self._value_by_row_label(matrix, ["流动资金单位千瓦指标", "估算指标"])
            if "建设期" in text and row["constructionPeriodYears"] is None:
                period = self._value_by_row_label(matrix, ["建设期"], unit_hint="年")
                if isinstance(period, (int, float)) and period <= 20:
                    row["constructionPeriodYears"] = period
        self._supplement_financing_row_from_text(ast, row)
        return self._schema_row_table("financingAssumptions", row) if any(value is not None for value in row.values()) else None

    def _supplement_financing_row_from_text(self, ast: DocumentAST, row: dict[str, Any]) -> None:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        if row.get("constructionPeriodYears") is None:
            value = self._first_matching_text(
                text,
                [r"建设期\s*([0-9]+(?:\.[0-9]+)?\s*(?:年|个月|月))", r"其中建设期\s*([0-9]+(?:\.[0-9]+)?\s*(?:年|个月|月))"],
            )
            row["constructionPeriodYears"] = value
        if row.get("constructionCapitalRatio") is None:
            row["constructionCapitalRatio"] = self._first_matching_number(
                text,
                [r"资本金占(?:静态投资|动态投资|总投资)?的?\s*([0-9]+(?:\.[0-9]+)?)%"],
            )
        if row.get("constructionFundLoanRatio") is None:
            value = self._first_matching_number(
                text,
                [
                    r"总投资的\s*([0-9]+(?:\.[0-9]+)?)%\s*利用[^。；;\n]{0,20}?贷款",
                    r"资本金占(?:动态投资|总投资)?的?\s*([0-9]+(?:\.[0-9]+)?)%[^。；;\n]{0,40}?贷款",
                ],
            )
            if isinstance(value, (int, float)) and value < 50:
                value = self._clean_number(100 - float(value))
            row["constructionFundLoanRatio"] = value
        if row.get("workingCapitalLoanRatio") is None:
            row["workingCapitalLoanRatio"] = self._first_matching_number(
                text,
                [r"流动资金[^。；;\n]{0,120}?([0-9]+(?:\.[0-9]+)?)%\s*采用[^。；;\n]{0,20}?贷款"],
            )
        if row.get("workingCapitalUnitKwIndicator") is None:
            row["workingCapitalUnitKwIndicator"] = self._first_matching_number(
                text,
                [r"流动资金[^。；;\n]{0,80}?估算指标为\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW"],
            )
        if row.get("workingCapitalCapitalRatio") is None:
            row["workingCapitalCapitalRatio"] = self._first_matching_number(
                text,
                [r"流动资金[^。；;\n]{0,120}?其中\s*([0-9]+(?:\.[0-9]+)?)%\s*为(?:自有资金|资本金)"],
            )
        if row.get("workingCapitalLoanInterestRate") is None:
            row["workingCapitalLoanInterestRate"] = self._first_matching_number(
                text,
                [r"流动资金[^。；;\n]{0,120}?贷款年利率为\s*([0-9]+(?:\.[0-9]+)?)%"],
            )
        if row.get("repaymentPeriod") is None:
            row["repaymentPeriod"] = self._first_matching_number(
                text,
                [r"贷款偿还期为\s*([0-9]+(?:\.[0-9]+)?)\s*年", r"银行\s*\d*\s*贷款偿还期为\s*([0-9]+(?:\.[0-9]+)?)\s*年"],
            )
        if row.get("repaymentMethod") is None and re.search(r"等额(?:还本|本)利息照付", text):
            row["repaymentMethod"] = "每年按贷款等额还本利息照付"
        if row.get("annualLoanInterestRate") is None:
            row["annualLoanInterestRate"] = self._first_matching_number(
                text,
                [r"年贷款利率为\s*([0-9]+(?:\.[0-9]+)?)%", r"五年期及以上年贷款利率按\s*([0-9]+(?:\.[0-9]+)?)%"],
            )

    def _financial_evaluation_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = {
            "insuranceRate": None,
            "materialCost": None,
            "otherCost": None,
            "landUseTax": None,
            "windFarmGridPrice": None,
            "incomeTax": None,
        }
        grid_price = self._grid_price_from_document(ast)
        if grid_price is not None:
            row["windFarmGridPrice"] = grid_price
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        if row["insuranceRate"] is None:
            marker = "保险费取固定资产原值的"
            index = text.find(marker)
            if index >= 0:
                tail = text[index : index + 80]
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[%%％]", tail)
                if match:
                    row["insuranceRate"] = self._clean_number(float(match.group(1)))
        if row["materialCost"] is None:
            row["materialCost"] = self._first_matching_number(
                text,
                [r"材料费[^。；;\n]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*万元"],
            )
        if row["otherCost"] is None:
            row["otherCost"] = self._first_matching_number(
                text,
                [r"其他费用[^。；;\n]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*(?:元/kW|万元)", r"其他费用取\s*([0-9]+(?:\.[0-9]+)?)\s*(?:元/kW|万元)"],
            )
        if row["landUseTax"] is None:
            row["landUseTax"] = self._first_matching_number(
                text,
                [r"土地使用税[^。；;\n]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*万元", r"土地使用税每年取\s*([0-9]+(?:\.[0-9]+)?)\s*万元"],
            )
        for table in ast.tables:
            section_text = " / ".join(table.section_path)
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            if "财务评价" not in section_text and "财务评价" not in text:
                continue
            if "材料费" in text:
                row["materialCost"] = row["materialCost"] or self._value_by_row_label(matrix, ["材料费"], prefer_total=True)
            if "其他费用" in text:
                row["otherCost"] = row["otherCost"] or self._value_by_row_label(matrix, ["其他费用"], prefer_total=True)
            if "土地使用税" in text:
                row["landUseTax"] = row["landUseTax"] or self._value_by_row_label(matrix, ["土地使用税"], prefer_total=True)
            if ("上网电价" in text or "风电场上网电价" in text) and row["windFarmGridPrice"] is None:
                price = self._value_by_row_label(matrix, ["风电场上网电价", "上网电价"])
                if isinstance(price, (int, float)) and 0 < price < 2:
                    row["windFarmGridPrice"] = price
        return self._schema_row_table("financialEvaluation", row) if any(value is not None for value in row.values()) else None

    def _financial_indicator_summary_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        best: tuple[int, DocumentTable, str] | None = None
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            table_text = self._matrix_text(matrix)
            header_text = " | ".join(matrix[0])
            caption_text = table.caption or self._caption_before_table(ast, table)
            section_text = " / ".join(table.section_path)
            if not self._looks_like_financial_indicator_summary_table(caption_text, header_text, table_text):
                continue
            context = "\n".join([section_text, caption_text, header_text, table_text])
            score = self._financial_indicator_summary_score(context, header_text)
            if score <= 0:
                continue
            if self._looks_like_finance_parameter_table(context, header_text):
                score -= 4
            if score > 0 and (best is None or score > best[0]):
                best = (score, table, caption_text)
        if best is None:
            return None
        _score, table, caption_text = best
        return self._document_table_passthrough(
            "financialIndicatorSummary",
            caption_text or "财务指标汇总表",
            table,
            "财务指标汇总表按原文表格单元格导出。",
            resolver="financial_indicator_summary_passthrough",
        )

    def _looks_like_financial_indicator_summary_table(self, caption_text: str, header_text: str, table_text: str) -> bool:
        if re.search(r"(?:附表|表)\s*16(?:\.1)?\s*财务指标汇总表", caption_text):
            return True
        if "财务指标汇总表" in caption_text:
            return True
        if "财务指标汇总表" in table_text[:120]:
            return True
        header_ok = (
            any(keyword in header_text for keyword in ("项目", "指标", "名称"))
            and "单位" in header_text
            and any(keyword in header_text for keyword in ("数值", "取值", "金额"))
        )
        if not header_ok:
            return False
        required_items = (
            "风电系统容量",
            "年售电量",
            "项目总投资",
            "经营期平均电价",
            "项目投资财务内部收益率",
            "资本金财务内部收益率",
            "度电成本",
        )
        return sum(1 for keyword in required_items if keyword in table_text) >= 4

    def _financial_indicator_summary_score(self, context: str, header_text: str) -> int:
        score = 0
        if re.search(r"(?:附表|表)\s*16(?:\.1)?\s*财务指标汇总表", context):
            score += 20
        if any(keyword in context for keyword in ("财务指标汇总", "财务指标表", "主要财务指标", "财务评价指标", "财务分析指标", "经济评价指标")):
            score += 8
        if "财务" in context or "经济评价" in context:
            score += 2
        indicator_keywords = (
            "项目投资财务内部收益率",
            "资本金财务内部收益率",
            "财务净现值",
            "投资回收期",
            "总投资收益率",
            "资本金净利润率",
            "借款偿还期",
            "资产负债率",
            "盈亏平衡点",
        )
        score += min(sum(1 for keyword in indicator_keywords if keyword in context), 6)
        if any(keyword in header_text for keyword in ("指标", "项目", "单位", "数值", "税前", "税后")):
            score += 1
        return score

    def _looks_like_finance_parameter_table(self, context: str, header_text: str) -> bool:
        if "财务指标" in context or "评价指标" in context:
            return False
        parameter_signatures = (
            ("建设期", "流动资金"),
            ("定员人数", "人员工资"),
            ("保险费率", "所得税"),
            ("材料费", "其他费用", "土地使用税"),
        )
        combined = f"{header_text}\n{context}"
        return any(all(keyword in combined for keyword in signature) for signature in parameter_signatures)

    def _grid_price_from_document(self, ast: DocumentAST) -> Any:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        patterns = [
            r"(?:平均)?上网电价(?:为|按照|按)?\s*([0-9]+(?:\.[0-9]+)?)\s*元/kW\s*[·.]?\s*h[^。；;\n]{0,20}?含",
            r"经营期平均电价（含增值税）[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
            r"上网电价（含税）[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)",
            r"上网电价[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        ]
        for pattern in patterns:
            value = self._first_matching_number(text, [pattern])
            if isinstance(value, (int, float)) and 0 < value < 2:
                return value
        for table in ast.tables:
            matrix = self._table_matrix(table)
            for row in matrix:
                row_text = " | ".join(row)
                if "不含" in row_text:
                    continue
                if "含增值税" not in row_text and "含税" not in row_text and "上网电价" not in row_text:
                    continue
                if "上网电价" not in row_text and "经营期平均电价" not in row_text:
                    continue
                value = self._first_number_after_label(row)
                if isinstance(value, (int, float)) and 0 < value < 2:
                    return value
        return None

    def _normalize_staff_salary(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        found = re.search(r"(\d+(?:\.\d+)?)\s*万元", value)
        return f"人均年工资{found.group(1)}万元" if found else value

    def _irr_pair(self, fields: dict[str, ParsedField]) -> str | None:
        before = self._field_value(fields, "projectInvestmentIrrBeforeTax")
        after = self._field_value(fields, "projectInvestmentIrrAfterTax")
        if before is None and after is None:
            return None
        return f"所得税前：{before} | 所得税后：{after}"

    def _apply_finance_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        if "insuranceRate" not in skip_codes and "保险费" in text:
            marker = "保险费取固定资产原值的"
            index = text.find(marker)
            if index >= 0:
                tail = text[index : index + 80]
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[%%％]", tail)
                if match:
                    self._set_field(fields, "insuranceRate", "保险费率", self._clean_number(float(match.group(1))), "%", marker, source_type="regex")
        specs: dict[str, tuple[str, Any, str | None]] = {
            "depreciationYears": ("折旧年限", self._first_matching_number(text, [r"折旧年限按\s*([0-9]+(?:\.[0-9]+)?)\s*年", r"折旧年限[^。；;\n]{0,20}?([0-9]+(?:\.[0-9]+)?)\s*年"]), "年"),
            "salvageRate": ("残值率", self._first_matching_number(text, [r"残值率\s*([0-9]+(?:\.[0-9]+)?)%", r"残值率[^0-9]{0,10}([0-9]+(?:\.[0-9]+)?)%"]), "%"),
            "repairCost": ("修理费", self._first_matching_text(text, [r"(修理费采用分段取费计算[\s\S]{0,220}?其余年份取\s*[0-9]+(?:\.[0-9]+)?\s*元/kW)", r"(修理费率[\s\S]{0,220}?其余年份取\s*[0-9]+(?:\.[0-9]+)?\s*元/kW)"]), None),
            "materialCostPerKw": ("材料费（元/KW）", self._first_matching_number(text, [r"材料费(?:定额)?取\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW"]) or self._first_matching_text(text, [r"(材料费采用分段取费计算[\s\S]{0,220}?其余年份取\s*[0-9]+(?:\.[0-9]+)?\s*元/kW)", r"(材料费[^。；;\n]{0,180}?(?:元/kW|元/KW)[^。；;\n]{0,120})"]), None),
            "constructionPeriodYears": ("建设期（月/年)", self._first_matching_text(text, [r"建设期\s*([0-9]+(?:\.[0-9]+)?\s*(?:年|个月|月))", r"其中建设期\s*([0-9]+(?:\.[0-9]+)?\s*(?:年|个月|月))"]), None),
            "workingCapitalUnitKwIndicator": ("流动资金单位千瓦指标", self._first_matching_number(text, [r"流动资金按\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW\s*估算", r"流动资金[^。；;\n]{0,80}?估算指标为\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW"]), "元/KW"),
            "workingCapitalLoanRatio": ("流动资金贷款比例", self._first_matching_number(text, [r"流动资金[^。；;\n]{0,120}?([0-9]+(?:\.[0-9]+)?)%\s*采用[^。；;\n]{0,20}?贷款"]), "%"),
            "workingCapitalCapitalRatio": ("流动资本金比例", self._first_matching_number(text, [r"流动资金[^。；;\n]{0,120}?其中\s*([0-9]+(?:\.[0-9]+)?)%\s*为(?:自有资金|资本金)"]), "%"),
            "workingCapitalLoanInterestRate": ("流动资金贷款利率", self._first_matching_number(text, [r"流动资金[^。；;\n]{0,120}?贷款年利率为\s*([0-9]+(?:\.[0-9]+)?)%"]), "%"),
            "constructionCapitalRatio": ("建设资本金比例", self._first_matching_number(text, [r"资本金占(?:静态投资|动态投资|总投资)?的?\s*([0-9]+(?:\.[0-9]+)?)%"]), "%"),
            "constructionFundLoanRatio": ("建设资金贷款比例", None, "%"),
            "repaymentMethod": ("还款方式", self._first_matching_text(text, [r"((?:每年)?按贷款等额(?:还本|本)利息照付)"]), None),
            "repaymentPeriod": ("偿还年限", self._first_matching_number(text, [r"银行\s*\d*\s*贷款偿还期为\s*([0-9]+(?:\.[0-9]+)?)\s*年", r"贷款偿还期为\s*([0-9]+(?:\.[0-9]+)?)\s*年"]), "年"),
            "annualLoanInterestRate": ("年贷款利率", self._first_matching_number(text, [r"年贷款利率为\s*([0-9]+(?:\.[0-9]+)?)%", r"五年期及以上年贷款利率按\s*([0-9]+(?:\.[0-9]+)?)%"]), "%"),
            "staffingCount": ("定员人数", self._first_matching_number(text, [r"风电场定员\s*为?\s*([0-9]+(?:\.[0-9]+)?)\s*人", r"定员\s*为?\s*([0-9]+(?:\.[0-9]+)?)\s*人"]), "人"),
            "staffSalary": ("人员工资", self._first_matching_number(text, [r"(?:人年均工资|人均年工资|年工资)按\s*([0-9]+(?:\.[0-9]+)?)\s*万元", r"人员工资[^。；;\n]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*万元"]), "万元"),
            "welfareOtherRatio": ("职工福利费及其他占比", self._first_matching_number(text, [r"职工福利费及其他[\s\S]{0,80}?工资总(?:额)?的\s*([0-9]+(?:\.[0-9]+)?)%", r"职工福利费[\s\S]{0,80}?工资总(?:额)?的\s*([0-9]+(?:\.[0-9]+)?)%", r"职工福利费[^\d]{0,80}?([0-9]+(?:\.[0-9]+)?)%"]), "%"),
        }
        capital_ratio = specs["constructionCapitalRatio"][1]
        if specs["constructionFundLoanRatio"][1] is None and isinstance(capital_ratio, (int, float)):
            specs["constructionFundLoanRatio"] = ("建设资金贷款比例", self._clean_number(100 - float(capital_ratio)), "%")
        repayment_value = specs["repaymentMethod"][1]
        if isinstance(repayment_value, str):
            specs["repaymentMethod"] = ("还款方式", repayment_value.replace("等额本利息照付", "等额还本利息照付"), None)
        for code, (name, value, unit) in specs.items():
            if code in skip_codes or value is None:
                continue
            self._set_field(fields, code, name, value, unit, "finance text deterministic override", source_type="regex")

    def _finance_text_scalar_override_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        blocks = self._configured_text_blocks(ast, "finance", ["财务"], ["材料费", "流动资金", "工资"])
        text = "\n".join(self._clean_text(block.text or "") for block in blocks if block.text)
        specs = self._configured_field_rules("finance", self._default_finance_text_field_rules())
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, rule in specs.items():
            if code in skip_codes:
                continue
            value = self._value_from_configured_patterns(text, rule)
            if value is None:
                continue
            overrides[code] = (
                str(rule.get("name") or self.required_field_meta.get(code, (code, None))[0]),
                value,
                rule.get("unit") or self.required_field_meta.get(code, (None, None))[1],
                self._field_evidence_text_for_value(ast, value, [str(item) for item in (rule.get("evidence_keywords") or [])]),
                "paragraph",
                {"resolver": "deterministic_finance_text", "sectionPath": ["财务"]},
            )
        return overrides

    def _finance_curtailment_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        text = self._finance_curtailment_context_text(ast)
        if not text:
            return {}
        segments = self._finance_curtailment_rate_segments(text)
        single_rate = self._finance_curtailment_single_rate(text, segments)
        energy_mwh = self._finance_curtailment_on_grid_energy_mwh(text)
        hours = self._finance_curtailment_full_load_hours(text)
        specs = {
            "financeCurtailmentRateSingle": ("限电率（单一值）", single_rate, "%", ["限电率"]),
            "financeCurtailmentRateSegments": ("限电率（分段值）", segments, "%", ["限电率"]),
            "financeCurtailmentAnnualOnGridEnergyMwh": ("限电后年上网电量", energy_mwh, "MWh", ["限电率", "年上网电量"]),
            "financeCurtailmentEquivalentFullLoadHours": ("限电等效满负荷小时数", hours, "h", ["限电率", "等效满负荷小时数"]),
        }
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, (name, value, unit, evidence_keywords) in specs.items():
            if code in skip_codes or value in (None, "", [], {}):
                continue
            overrides[code] = (
                name,
                value,
                unit,
                self._field_evidence_text_for_value(ast, "限电率", evidence_keywords),
                "paragraph",
                {"resolver": "deterministic_finance_curtailment_text", "sectionPath": ["财务"]},
            )
        return overrides

    def _finance_curtailment_context_text(self, ast: DocumentAST) -> str:
        parts: list[str] = []
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_text = " ".join(str(part) for part in (block.section_path or []))
            if "限电率" in text or ("限电" in text and "财务" in section_text):
                parts.append(text)
        return "\n".join(parts)

    def _finance_curtailment_rate_segments(self, text: str) -> Any:
        pattern = r"(?P<label>(?:第?[一二三四五六七八九十0-9]+年\s*(?:至|~|～|-)\s*第?[一二三四五六七八九十0-9]+年|第?[一二三四五六七八九十0-9]+(?:阶段|年)|[0-9]+(?:\s*[~～至-]\s*[0-9]+)?\s*年|运营期|全阶段))[^。；;\n%]{0,30}?限电率[^0-9%]{0,10}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%"
        values: dict[str, Any] = {}
        for match in re.finditer(pattern, text):
            label = self._clean_text(match.group("label"))
            values[label] = self._normalize_scalar(match.group("value"))
        if values:
            return values
        inline = re.findall(r"限电率[^。；;\n]{0,120}", text)
        found = [self._normalize_scalar(value) for part in inline for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", part)]
        unique = []
        for value in found:
            if value not in unique:
                unique.append(value)
        return unique if len(unique) > 1 else None

    def _finance_curtailment_single_rate(self, text: str, segments: Any) -> Any:
        if isinstance(segments, dict) and len(set(segments.values())) == 1:
            return next(iter(segments.values()))
        if segments:
            return None
        match = re.search(r"限电率[^0-9%]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%", text)
        return self._normalize_scalar(match.group(1)) if match else None

    def _finance_curtailment_on_grid_energy_mwh(self, text: str) -> Any:
        context = self._keyword_window(text, ["限电率"], 260) or text
        patterns = [
            r"(?:限电后)?年上网(?:发)?电量[^0-9。；;\n]{0,20}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>MWh|MW[·.]?h|兆瓦时|万\s*kW[·.]?h|万\s*kWh)",
            r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>MWh|MW[·.]?h|兆瓦时|万\s*kW[·.]?h|万\s*kWh)[^。；;\n]{0,20}年上网(?:发)?电量",
        ]
        for pattern in patterns:
            match = re.search(pattern, context, flags=re.IGNORECASE)
            if match:
                return self._energy_value_to_mwh(match.group("value"), match.group("unit"))
        return None

    def _finance_curtailment_full_load_hours(self, text: str) -> Any:
        context = self._keyword_window(text, ["限电率"], 260) or text
        match = re.search(r"(?:限电后)?(?:等效满负荷小时数|年等效满负荷小时数)[^0-9。；;\n]{0,20}([0-9]+(?:\.[0-9]+)?)\s*h", context, flags=re.IGNORECASE)
        return self._normalize_scalar(match.group(1)) if match else None

    def _energy_value_to_mwh(self, value_text: str, unit: str) -> Any:
        value = self._normalize_scalar(value_text)
        if not isinstance(value, (int, float)):
            return None
        normalized_unit = re.sub(r"\s+", "", unit)
        if "万" in normalized_unit:
            return self._clean_number(float(value) * 10)
        return value

    def _finance_grid_price_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        if "windFarmGridPrice" in skip_codes:
            return {}
        patterns = [
            r"(?:风电站上网电价|风电场上网电价|本项目上网电价)[^0-9。；;\n]{0,30}([0-9]+(?:\.[0-9]+)?)\s*(?:元\s*/\s*(?:kWh|kW[·.]?h|千瓦时))",
            r"(?:风电站上网电价|风电场上网电价|本项目上网电价)[^0-9。；;\n]{0,30}([0-9]+(?:\.[0-9]+)?)",
        ]
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not any(keyword in text for keyword in ("风电站上网电价", "风电场上网电价", "本项目上网电价")):
                continue
            value = self._first_matching_number(text, patterns)
            if value is None:
                continue
            return {
                "windFarmGridPrice": (
                    "上网电价",
                    value,
                    "元/kWh",
                    text,
                    "paragraph",
                    {"resolver": "deterministic_finance_grid_price_text", "sectionPath": ["财务"]},
                )
            }
        return {}

    def _finance_capital_irr_scalar_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        if {"financeCapitalIrrWithoutOutgoing", "financeCapitalIrr"}.issubset(skip_codes):
            return {}
        values: list[tuple[Any, str, DocumentTable]] = []
        for table in sorted(ast.tables, key=lambda item: item.order):
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            table_text = self._matrix_text(matrix)
            header_text = " | ".join(matrix[0])
            caption_text = table.caption or self._caption_before_table(ast, table)
            if not self._looks_like_financial_indicator_summary_table(caption_text, header_text, table_text):
                continue
            values.extend(self._capital_irr_values_from_financial_indicator_matrix(matrix, table))
        unique: list[tuple[Any, str, DocumentTable]] = []
        seen: set[float] = set()
        for value, evidence_text, table in values:
            if not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if numeric in seen:
                continue
            seen.add(numeric)
            unique.append((value, evidence_text, table))
        if not unique:
            return {}
        selected = sorted(unique, key=lambda item: float(item[0]))
        assignments: dict[str, tuple[Any, str, DocumentTable]] = {}
        if len(selected) == 1:
            assignments["financeCapitalIrr"] = selected[0]
        else:
            assignments["financeCapitalIrr"] = selected[0]
            assignments["financeCapitalIrrWithoutOutgoing"] = selected[-1]
        result: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, (value, evidence_text, table) in assignments.items():
            if code in skip_codes:
                continue
            name, unit = self.required_field_meta.get(code, (code, "%"))
            result[code] = (
                name,
                value,
                unit,
                evidence_text,
                "table",
                {
                    "resolver": "deterministic_finance_capital_irr_table",
                    "sectionPath": list(table.section_path or ["财务"]),
                    "tableId": table.id,
                    "caption": table.caption or self._caption_before_table(ast, table),
                },
            )
        return result

    def _capital_irr_values_from_financial_indicator_matrix(self, matrix: list[list[str]], table: DocumentTable) -> list[tuple[Any, str, DocumentTable]]:
        header_index = self._financial_indicator_header_index(matrix)
        header = matrix[header_index] if header_index is not None else matrix[0]
        label_index = self._find_header_index(header, ["项目", "指标", "名称"])
        unit_indices = {index for index, value in enumerate(header) if any(keyword in value for keyword in ("单位", "序号", "编号"))}
        data_rows = matrix[(header_index + 1 if header_index is not None else 1) :]
        values: list[tuple[Any, str, DocumentTable]] = []
        for row in data_rows:
            row_text = self._clean_text(" | ".join(row))
            if "资本金财务内部收益率" not in row_text:
                continue
            label_text = row[label_index] if label_index is not None and label_index < len(row) else row_text
            if "资本金财务内部收益率" not in label_text and label_index is not None:
                continue
            start_index = label_index + 1 if label_index is not None else 0
            for index, cell in enumerate(row[start_index:], start=start_index):
                if index in unit_indices:
                    continue
                value = self._normalize_table_cell(cell)
                if isinstance(value, (int, float)):
                    values.append((value, row_text, table))
        return values

    def _financial_indicator_header_index(self, matrix: list[list[str]]) -> int | None:
        for index, row in enumerate(matrix[:5]):
            row_text = self._clean_text(" | ".join(row))
            if any(keyword in row_text for keyword in ("项目", "指标")) and any(keyword in row_text for keyword in ("数值", "单位", "金额")):
                return index
        return None

    def _finance_table_scalar_override_values(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        skip_codes = skip_codes or set()
        if "financeInsuranceRate" in skip_codes:
            return {}
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            table_text = self._matrix_text(matrix)
            context = f"{table.caption or ''} {' / '.join(table.section_path)} {table_text}"
            if "保险费率" not in context:
                continue
            if not any(keyword in context for keyword in ("财务", "还款", "折旧", "残值率", "其他费用", "保险费率")):
                continue
            header = self._header_row(matrix, ["字段", "数据"]) or self._header_row(matrix, ["项目", "数据"]) or matrix[0]
            for row in matrix[1:]:
                label = self._row_label(row)
                if "保险费率" not in label:
                    continue
                value = self._row_value_by_header(header, row, ["数据", "数值", "取值", "合计"]) or self._last_numeric_cell(row)
                if value is None:
                    continue
                return {
                    "financeInsuranceRate": (
                        "保险费率",
                        value,
                        "%",
                        "由财务参数表“保险费率”行抽取。",
                        "table",
                        {"resolver": "deterministic_finance_table", "sectionPath": ["财务"]},
                    )
                }
        return {}

    def _default_finance_text_field_rules(self) -> dict[str, dict[str, Any]]:
        return {
            "materialCostPerKw": {
                "name": "材料费（元/KW）",
                "unit": "元/KW",
                "value_type": "number",
                "evidence_keywords": ["材料费"],
                "patterns": [r"材料费(?:定额)?取\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW"],
            },
            "workingCapitalUnitKwIndicator": {
                "name": "流动资金单位千瓦指标",
                "unit": "元/KW",
                "value_type": "number",
                "evidence_keywords": ["流动资金"],
                "patterns": [
                    r"流动资金按\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW\s*估算",
                    r"流动资金[^。；;\n]{0,80}?估算指标为\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW",
                ],
            },
            "staffSalary": {
                "name": "人员工资",
                "unit": "万元",
                "value_type": "number",
                "evidence_keywords": ["工资"],
                "patterns": [
                    r"(?:人年均工资|人均年工资|年工资)按\s*([0-9]+(?:\.[0-9]+)?)\s*万元",
                    r"人员工资[^。；;\n]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*万元",
                ],
            },
        }
