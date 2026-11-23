"""字段值抽取器。"""

from __future__ import annotations

import re

from word_parser.document.ast.evidence import Extraction, FieldEvidence, FieldMatch
from word_parser.logger import logger


class ValueExtractor:
    """组合表格规则与正则的抽取器。"""

    NUMBER_PATTERN = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z%/·\u4e00-\u9fa5-]+)?")
    VALUE_HEADER_KEYWORDS = ("数值", "指标值", "推荐值", "取值", "金额", "投资", "容量", "规模", "长度", "数量", "台数")
    UNIT_HEADER_KEYWORDS = ("单位", "计量单位")
    NOISE_HEADER_KEYWORDS = ("序号", "编号", "备注", "说明", "类别", "阶段")
    RAW_UNIT_HEADER_KEYWORDS = ("单位", "unit", "Unit")
    SUMMARY_ROW_KEYWORDS = ("合计", "总计", "总长", "小计", "求和", "平均", "total", "Total")
    MATERIAL_GRADE_PATTERN = r"\b(?:C|AC|HRB|HPB)\s*[-]?\d+"
    HEADING_EXCLUSION_PATTERNS = (
        r"\d+(?:\.\d+){1,4}\s+[^|:]{1,40}",
        r"\s*\d+(?:[-.]\d+)+(?:\s+[^|:]{0,40})?",
    )
    HEADING_VALUE_MARKERS = (":", "：", "|")

    def __init__(
        self,
        table_rule_enabled: bool = True,
        regex_enabled: bool = True,
        table_header_config: dict | None = None,
        value_config: dict | None = None,
    ):
        """初始化抽取器。

        参数：
            table_rule_enabled: 是否启用表格规则抽取。
            regex_enabled: 是否启用字段正则和兜底数值抽取。
        """
        self.table_rule_enabled = table_rule_enabled
        self.regex_enabled = regex_enabled
        # Keep legacy defaults for direct callers, but read all active table labels
        # from configs/extraction_runtime.yaml in the application factory.
        headers = table_header_config or {}
        self.VALUE_HEADER_KEYWORDS = tuple(headers.get("value", self.VALUE_HEADER_KEYWORDS))
        self.UNIT_HEADER_KEYWORDS = tuple(headers.get("unit", self.UNIT_HEADER_KEYWORDS))
        self.NOISE_HEADER_KEYWORDS = tuple(headers.get("noise", self.NOISE_HEADER_KEYWORDS))
        self.RAW_UNIT_HEADER_KEYWORDS = tuple(headers.get("raw_unit", self.RAW_UNIT_HEADER_KEYWORDS))
        self.SUMMARY_ROW_KEYWORDS = tuple(headers.get("summary", self.SUMMARY_ROW_KEYWORDS))
        self.MATERIAL_GRADE_PATTERN = str(headers.get("material_grade_pattern", self.MATERIAL_GRADE_PATTERN))
        policy = value_config or {}
        self.number_near_alias_window = int(policy.get("number_near_alias_window", 80))
        self.table_group_header_max_cells = int(policy.get("table_group_header_max_cells", 2))
        self.heading_exclusion_patterns = tuple(
            policy.get("heading_exclusion_patterns", self.HEADING_EXCLUSION_PATTERNS)
        )
        self.heading_value_markers = tuple(
            policy.get("heading_value_markers", self.HEADING_VALUE_MARKERS)
        )

    def extract(self, matches: list[FieldMatch]) -> list[Extraction]:
        """从匹配候选中抽取字段值。

        参数：
            matches: 字段匹配结果。

        返回：
            list[Extraction]: 抽取结果。
        """
        extractions: list[Extraction] = []
        for match in matches:
            current: list[Extraction] = []
            if self.table_rule_enabled and match.candidate.source_type == "table":
                current.extend(self._extract_from_table(match))
            if self.regex_enabled:
                current.extend(self._extract_by_regex(match))
            if match.candidate.meta.get("appendix_fallback"):
                for extraction in current:
                    extraction.debug["appendix_fallback"] = True
            extractions.extend(current)
        deduped = self._deduplicate_extractions(extractions)
        logger.info(f"值抽取器产出结果：{len(deduped)} 条，去重前 {len(extractions)} 条")
        return deduped

    def _deduplicate_extractions(self, extractions: list[Extraction]) -> list[Extraction]:
        """去重同一字段、同一值、同一证据的重复抽取。"""
        best_by_key: dict[tuple[str, str, str | None, str], Extraction] = {}
        for extraction in extractions:
            key = (
                extraction.field_code,
                str(extraction.raw_value),
                extraction.unit,
                extraction.evidence.text,
            )
            current = best_by_key.get(key)
            if current is None or extraction.score > current.score:
                best_by_key[key] = extraction
        return sorted(best_by_key.values(), key=lambda item: item.score, reverse=True)

    def _extract_from_table(self, match: FieldMatch) -> list[Extraction]:
        """从表格候选中抽取值。

        参数：
            match: 字段匹配结果。

        返回：
            list[Extraction]: 表格抽取结果。
        """
        table = match.candidate.meta.get("table")
        if table is None:
            return []
        aliases = match.candidate.field_config.get("aliases") or []
        results: list[Extraction] = []
        results.extend(self._extract_by_table_aggregate(match, table))
        results.extend(self._extract_by_table_list(match, table))
        lookup_results = self._extract_by_table_lookup(match, table)
        if lookup_results:
            results.extend(lookup_results)
            return results
        if match.candidate.field_config.get("coarse_table_rule_enabled") is False:
            return results
        for row_index, row in enumerate(table.rows):
            expanded_row = self._expanded_row(row)
            row_text = " | ".join(cell.text for cell in expanded_row)
            if not self._row_context_allowed(match, table, row_index, row_text):
                continue
            header_items = [] if match.candidate.field_config.get("row_label_aliases") else self._extract_values_from_table_header_row(table, row_index, match.candidate.field_config)
            alias_hit = any(alias in row_text for alias in aliases)
            if not alias_hit and not header_items:
                continue
            extracted_items = header_items
            score_bonus = 0.95 if extracted_items else 0.6
            if not extracted_items:
                extracted_items = [
                    item
                    for item in [self._extract_value_from_table_row(table, row_index, match.candidate.field_config)]
                    if item[0] is not None
                ]
            for value_text, unit, evidence_text in extracted_items:
                if not self._value_allowed(value_text, match.candidate.field_config):
                    continue
                evidence = self._build_evidence(match, evidence_text or row_text, "table_rule")
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=value_text,
                        value=value_text,
                        unit=unit,
                        score=match.score + score_bonus,
                        method="table_rule",
                        evidence=evidence,
                        debug={"row_text": evidence_text or row_text, "row_index": row_index},
                    )
                )
        return results

    def _extract_by_table_aggregate(self, match: FieldMatch, table) -> list[Extraction]:
        """从指定数值表格列中抽取最大值、合计值等聚合结果。"""
        config = match.candidate.field_config
        aggregate = config.get("table_aggregate") or {}
        if not aggregate or not table.rows:
            return []
        op = aggregate.get("op")
        if op not in {"max", "sum"}:
            return []

        header_rows = self._header_rows(table, int(aggregate.get("header_rows", 1) or 1))
        header_texts = self._merged_header_texts(header_rows)
        target_headers = aggregate.get("value_headers") or config.get("value_headers") or []
        if not target_headers:
            return []
        column_indexes = [
            index for index, header in header_texts.items() if any(keyword in header for keyword in target_headers)
        ]
        occurrence = aggregate.get("column_occurrence")
        if isinstance(occurrence, int) and occurrence > 0:
            column_indexes = column_indexes[occurrence - 1 : occurrence]
        if not column_indexes:
            return []

        require_any = aggregate.get("require_any") or []
        reject_any = aggregate.get("reject_any") or []
        table_text = getattr(table, "meta", {}).get("table_text") or "\n".join(
            " | ".join(cell.text for cell in row) for row in table.rows
        )
        section_text = " / ".join(getattr(table, "section_path", []) or [])
        context_text = f"{section_text}\n{table_text}"
        if require_any and not any(keyword in context_text for keyword in require_any):
            return []
        if reject_any and any(keyword in context_text for keyword in reject_any):
            return []

        values: list[float] = []
        summary_values: list[float] = []
        evidence_rows: list[str] = []
        for row_index, row in enumerate(table.rows[len(header_rows) :], start=len(header_rows)):
            expanded = self._expanded_row(row)
            row_text = " | ".join(cell.text for cell in expanded)
            if self._looks_like_header_or_group_row(expanded):
                continue
            if not self._row_context_allowed(match, table, row_index, row_text):
                continue
            is_summary_row = self._row_has_summary_label(expanded)
            for column_index in column_indexes:
                if column_index >= len(expanded):
                    continue
                value_text, _unit = self._first_number_with_unit(expanded[column_index].text, config)
                if value_text is None or not self._value_allowed(value_text, config):
                    continue
                try:
                    numeric_value = float(str(value_text).replace(",", ""))
                    if is_summary_row:
                        summary_values.append(numeric_value)
                    else:
                        values.append(numeric_value)
                    evidence_rows.append(row_text)
                except ValueError:
                    continue

        if op == "sum" and aggregate.get("prefer_summary", True) and summary_values:
            values = [summary_values[-1]]
        min_values = int(aggregate.get("min_values", 1) or 1)
        if len(values) < min_values and not summary_values:
            return []
        aggregated = max(values) if op == "max" else sum(values)
        precision = aggregate.get("precision")
        if isinstance(precision, int):
            aggregated = round(aggregated, precision)
        value_text = str(int(aggregated)) if float(aggregated).is_integer() else str(aggregated)
        header_label = " / ".join(header_texts[index] for index in column_indexes if index in header_texts)
        evidence_text = f"{header_label} | {op}={value_text} | rows={len(values)}"
        if evidence_rows:
            evidence_text = f"{evidence_text}\n" + "\n".join(evidence_rows[:5])
        return [
            Extraction(
                field_code=match.candidate.field_code,
                field_name=match.candidate.field_name,
                raw_value=value_text,
                value=value_text,
                unit=aggregate.get("unit") or config.get("standard_unit"),
                score=match.score + 1.35,
                method="table_aggregate",
                evidence=self._build_evidence(match, evidence_text, "table_aggregate"),
                debug={
                    "aggregate_op": op,
                    "aggregate_values": len(values),
                    "aggregate_summary_values": len(summary_values),
                    "aggregate_columns": column_indexes,
                    "aggregate_signature": f"{match.candidate.field_code}:{op}:{header_label}",
                },
            )
        ]

    def _extract_by_table_lookup(self, match: FieldMatch, table) -> list[Extraction]:
        """按配置的行/列表头交叉定位表格值。"""
        lookup = match.candidate.field_config.get("table_lookup") or {}
        row_aliases = lookup.get("row_aliases") or []
        column_aliases = lookup.get("column_aliases") or []
        if not row_aliases or not column_aliases or not table.rows:
            return []

        header_rows = self._header_rows(table, int(lookup.get("header_rows", 1) or 1))
        header_texts = self._merged_header_texts(header_rows)
        column_indexes = [
            index for index, header in header_texts.items() if any(alias in header for alias in column_aliases)
        ]
        occurrence = lookup.get("column_occurrence")
        if isinstance(occurrence, int) and occurrence > 0:
            column_indexes = column_indexes[occurrence - 1 : occurrence]
        if not column_indexes:
            return []

        results: list[Extraction] = []
        for row_index, row in enumerate(table.rows[len(header_rows) :], start=len(header_rows)):
            expanded = self._expanded_row(row)
            row_text = " | ".join(cell.text for cell in expanded)
            if not self._row_label_matches(expanded, lookup, row_aliases):
                continue
            if not self._row_context_allowed(match, table, row_index, row_text):
                continue
            for column_index in column_indexes:
                if column_index >= len(expanded):
                    continue
                cell_text = expanded[column_index].text.strip()
                value_text, unit = self._value_from_cell_text(cell_text, match.candidate.field_config)
                if value_text is None or not self._value_allowed(value_text, match.candidate.field_config):
                    continue
                header_text = header_texts.get(column_index, "")
                evidence_text = f"{row_text} | {header_text}={cell_text}"
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=value_text,
                        value=value_text,
                        unit=unit or self._unit_from_text(header_text, match.candidate.field_config),
                        score=match.score + 0.75,
                        method="table_lookup",
                        evidence=self._build_evidence(match, evidence_text, "table_lookup"),
                        debug={"row_index": row_index, "column_index": column_index, "table_lookup": lookup},
                    )
                )
        return results

    def _extract_by_table_list(self, match: FieldMatch, table) -> list[Extraction]:
        """从配置的表格列中抽取紧凑列表或范围。"""
        config = match.candidate.field_config
        table_list = config.get("table_list") or {}
        if not table_list or not table.rows:
            return []

        header_rows = self._header_rows(table, int(table_list.get("header_rows", 1) or 1))
        header_texts = self._merged_header_texts(header_rows)
        column_aliases = table_list.get("column_aliases") or []
        column_indexes = [
            index for index, header in header_texts.items() if any(alias in header for alias in column_aliases)
        ]
        if not column_indexes:
            return []
        column_index = column_indexes[0]
        reject_any = table_list.get("reject_any") or []
        require_any = table_list.get("require_any") or []

        values: list[str] = []
        evidence_rows: list[str] = []
        for row_index, row in enumerate(table.rows[len(header_rows) :], start=len(header_rows)):
            expanded = self._expanded_row(row)
            row_text = " | ".join(cell.text for cell in expanded)
            if not self._row_context_allowed(match, table, row_index, row_text):
                continue
            if require_any and not any(keyword in row_text for keyword in require_any):
                continue
            if reject_any and any(keyword in row_text for keyword in reject_any):
                continue
            if column_index >= len(expanded):
                continue
            value = self._clean_string_value(expanded[column_index].text)
            if not value or value in {"--", "-", "——"}:
                continue
            values.append(value)
            evidence_rows.append(row_text)

        values = list(dict.fromkeys(values))
        if not values:
            return []
        value_text = self._format_list_value(values, table_list.get("format"))
        evidence_text = f"{header_texts.get(column_index, '')} | {value_text}"
        if evidence_rows:
            evidence_text = f"{evidence_text}\n" + "\n".join(evidence_rows[:8])
        return [
            Extraction(
                field_code=match.candidate.field_code,
                field_name=match.candidate.field_name,
                raw_value=value_text,
                value=value_text,
                unit=None,
                score=match.score + 1.1,
                method="table_list",
                evidence=self._build_evidence(match, evidence_text, "table_list"),
                debug={"table_list_count": len(values), "column_index": column_index},
            )
        ]

    def _extract_value_from_table_row(self, table, row_index: int, field_config: dict) -> tuple[str | None, str | None, str | None]:
        """按表头、单元格位置和单位列从指标表行中取值。"""
        row = self._expanded_row(table.rows[row_index])
        aliases = field_config.get("aliases") or []
        if field_config.get("row_label_aliases") and not self._row_label_matches(row, field_config, []):
            return None, None, None
        alias_indexes = [index for index, cell in enumerate(row) if any(alias in cell.text for alias in aliases)]
        unit_aliases = list(field_config.get("unit_aliases") or [])
        standard_unit = field_config.get("standard_unit")
        if standard_unit:
            unit_aliases.append(standard_unit)

        headers = self._column_headers(table, row_index)
        unit_from_row = self._unit_from_cells(row, unit_aliases)
        unit_from_column = self._unit_from_unit_column(row, headers, unit_aliases)
        raw_unit_from_column = self._raw_unit_from_unit_column(row, headers)
        if self._unit_rejected(raw_unit_from_column, unit_aliases):
            return None, None, None
        scored: list[tuple[float, int, str, str | None]] = []

        for index, cell in enumerate(row):
            if self._looks_like_non_value_cell(cell.text, headers.get(index, ""), field_config):
                continue
            value_text, unit = self._value_from_cell_text(cell.text, field_config)
            if value_text is None:
                continue
            score = self._table_value_cell_score(index, cell.text, headers.get(index, ""), alias_indexes, unit_aliases, field_config)
            if score <= -2.0:
                continue
            scored.append((score, index, value_text, unit or unit_from_column or unit_from_row))

        if not scored:
            return None, None, None

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return scored[0][2], scored[0][3], " | ".join(cell.text for cell in row)

    def _extract_values_from_table_header_row(self, table, row_index: int, field_config: dict) -> list[tuple[str, str | None, str]]:
        """从“表头在本行、数据在后续行”的横向指标表中按列抽值。"""
        if row_index >= len(table.rows) - 1:
            return []
        header_row = self._expanded_row(table.rows[row_index])
        aliases = field_config.get("aliases") or []
        matched_columns = [index for index, cell in enumerate(header_row) if any(alias in cell.text for alias in aliases)]
        if not matched_columns:
            return []

        results: list[tuple[str, str | None, str]] = []
        for column_index in matched_columns:
            header_text = header_row[column_index].text
            unit_from_header = self._unit_from_text(header_text, field_config)
            for data_row in table.rows[row_index + 1 :]:
                expanded = self._expanded_row(data_row)
                if len(table.rows) > 5 and not field_config.get("multi_value") and self._row_has_summary_label(expanded):
                    continue
                if column_index >= len(expanded):
                    continue
                cell_text = expanded[column_index].text.strip()
                if not cell_text or cell_text in {"——", "--", "-"}:
                    continue
                value_text, unit = self._value_from_cell_text(cell_text, field_config)
                if value_text is None or not self._value_allowed(value_text, field_config):
                    continue
                evidence_text = f"{header_text} | {cell_text}"
                results.append((value_text, unit or unit_from_header, evidence_text))
        return results

    def _expanded_row(self, row):
        """按 col_span 做基础展开，便于用逻辑列号匹配表头。"""
        expanded = []
        for cell in row:
            span = max(1, int(getattr(cell, "col_span", 1) or 1))
            expanded.extend([cell] * span)
        return expanded

    def _column_headers(self, table, row_index: int) -> dict[int, str]:
        """合并目标行之前的表头文本，生成列号到表头语义的映射。"""
        headers: dict[int, list[str]] = {}
        for header_row in table.rows[:row_index]:
            expanded = self._expanded_row(header_row)
            if not expanded:
                continue
            for index, cell in enumerate(expanded):
                text = cell.text.strip()
                if text:
                    headers.setdefault(index, []).append(text)
        return {index: " ".join(parts) for index, parts in headers.items()}

    def _raw_unit_from_unit_column(self, row, headers: dict[int, str]) -> str | None:
        """读取单位列原始文本，不受允许单位配置限制。"""
        unit_keywords = self.RAW_UNIT_HEADER_KEYWORDS
        for index, cell in enumerate(row):
            header = headers.get(index, "")
            if any(keyword in header for keyword in unit_keywords):
                text = cell.text.strip()
                return text or None
        return None

    def _unit_rejected(self, raw_unit: str | None, unit_aliases: list[str]) -> bool:
        """拒绝单位列与字段允许单位冲突的表格行。"""
        if not raw_unit or not unit_aliases:
            return False
        return not any(unit and unit in raw_unit for unit in unit_aliases)

    def _looks_like_non_value_cell(self, text: str, header_text: str, field_config: dict) -> bool:
        """跳过仅偶然包含数字的材料牌号和备注单元格。"""
        if field_config.get("value_type") != "number":
            return False
        stripped = text.strip()
        if not stripped:
            return True
        if re.search(self.MATERIAL_GRADE_PATTERN, stripped):
            return True
        if any(keyword in header_text for keyword in self.NOISE_HEADER_KEYWORDS):
            return True
        return False

    def _row_has_summary_label(self, row) -> bool:
        """识别长明细表中的合计或汇总行，词典由 YAML 配置。"""
        label = " ".join(cell.text for cell in row[:3])
        return any(keyword in label for keyword in self.SUMMARY_ROW_KEYWORDS)

    def _unit_from_unit_column(self, row, headers: dict[int, str], unit_aliases: list[str]) -> str | None:
        """优先从表头为“单位”的列读取单位。"""
        for index, cell in enumerate(row):
            header = headers.get(index, "")
            if not any(keyword in header for keyword in self.UNIT_HEADER_KEYWORDS):
                continue
            for unit in sorted(set(unit_aliases), key=len, reverse=True):
                if unit in cell.text:
                    return unit
        return None

    def _table_value_cell_score(
        self,
        index: int,
        cell_text: str,
        header_text: str,
        alias_indexes: list[int],
        unit_aliases: list[str],
        field_config: dict,
    ) -> float:
        """按表头语义、别名单元格距离和噪声列惩罚给候选值单元格打分。"""
        score = 0.0
        target_headers = field_config.get("value_headers") or []
        if target_headers:
            if any(keyword in header_text for keyword in target_headers):
                score += 4.0
            elif header_text:
                score -= 2.0
        if any(keyword in header_text for keyword in self.VALUE_HEADER_KEYWORDS):
            score += 3.0
        if (chr(0x63a8) + chr(0x8350) in header_text) and (chr(0x65b9) + chr(0x6848) in header_text):
            score += 3.0
        if any(keyword in header_text for keyword in self.UNIT_HEADER_KEYWORDS):
            score -= 3.0
        if any(keyword in header_text or keyword in cell_text for keyword in self.NOISE_HEADER_KEYWORDS):
            score -= 3.0
        if not header_text and any(keyword in cell_text for keyword in self.NOISE_HEADER_KEYWORDS):
            score -= 2.0
        if any(unit and unit in cell_text for unit in unit_aliases):
            score += 0.8
        if alias_indexes:
            nearest_alias = min(alias_indexes, key=lambda alias_index: abs(index - alias_index))
            if index <= nearest_alias:
                score -= 2.0
            else:
                score += max(0.0, 1.5 - 0.25 * (index - nearest_alias - 1))
        return score

    def _value_from_cell_text(self, text: str, field_config: dict) -> tuple[str | None, str | None]:
        """按字段类型从单元格文本中取值。"""
        if field_config.get("value_type") == "string":
            preferred = self._preferred_string_value(text, field_config)
            if preferred is not None:
                return preferred, None
            if field_config.get("preferred_values"):
                return None, None
            cleaned = self._clean_string_value(text)
            return (cleaned, None) if cleaned and cleaned not in {"\u2014\u2014", "--", "-"} else (None, None)
        return self._first_number_with_unit(text, field_config)

    def _unit_from_text(self, text: str, field_config: dict) -> str | None:
        """从表头或单元格文本中识别允许单位。"""
        unit_aliases = list(field_config.get("unit_aliases") or [])
        standard_unit = field_config.get("standard_unit")
        if standard_unit:
            unit_aliases.append(standard_unit)
        for unit in sorted(set(unit_aliases), key=len, reverse=True):
            if unit and (unit in text or self._compact_text(unit) in self._compact_text(text)):
                return unit
        return None

    def _unit_from_cells(self, row, unit_aliases: list[str]) -> str | None:
        """从同一行单元格中识别单位列。"""
        for cell in row:
            text = cell.text.strip()
            for unit in sorted(set(unit_aliases), key=len, reverse=True):
                if text == unit or unit in text or self._compact_text(unit) in self._compact_text(text):
                    return unit
        return None

    def _header_rows(self, table, header_count: int):
        """返回用作表头的前置表格行。"""
        return table.rows[: max(1, min(header_count, len(table.rows)))]

    def _merged_header_texts(self, header_rows) -> dict[int, str]:
        """按照逻辑列索引合并多行表头。"""
        headers: dict[int, list[str]] = {}
        for row in header_rows:
            for index, cell in enumerate(self._expanded_row(row)):
                text = cell.text.strip()
                if text:
                    headers.setdefault(index, []).append(text)
        return {index: " ".join(dict.fromkeys(parts)) for index, parts in headers.items()}

    def _looks_like_header_or_group_row(self, row) -> bool:
        """跳过作为分组标签而非数据记录的行。"""
        non_empty = [cell.text.strip() for cell in row if cell.text.strip()]
        if not non_empty:
            return True
        if len(non_empty) <= self.table_group_header_max_cells and not any(re.search(r"\d", text) for text in non_empty):
            return True
        return False

    def _row_label_matches(self, row, config: dict, aliases: list[str]) -> bool:
        """在语义行标签列中匹配别名，而不是匹配整行。"""
        label_aliases = config.get("row_label_aliases") or aliases
        if not label_aliases:
            return True
        column_count = int(config.get("row_label_columns", 2) or 2)
        label_cells = [cell.text.strip() for cell in row[: max(1, column_count)] if cell.text.strip()]
        label_text = " ".join(label_cells)
        if not label_text:
            return False
        reject_any = config.get("row_label_reject_any") or []
        if reject_any and any(keyword in label_text for keyword in reject_any):
            return False
        mode = config.get("row_label_match", "contains")
        normalized_cells = [text.replace(" ", "") for text in label_cells]
        normalized_label = label_text.replace(" ", "")
        normalized_aliases = [alias.replace(" ", "") for alias in label_aliases if alias]
        if mode == "exact":
            return any(alias == cell for alias in normalized_aliases for cell in normalized_cells)
        if mode == "prefix":
            return any(normalized_label.startswith(alias) for alias in normalized_aliases)
        return any(alias in normalized_label for alias in normalized_aliases)

    def _format_list_value(self, values: list[str], format_name: str | None) -> str:
        """格式化抽取的列表值，并可将 A线…H线 合并为 A-H。"""
        if format_name == "alpha_range":
            letters: list[str] = []
            for value in values:
                found = re.fullmatch(r"([A-Za-z])(?:线|回|路)?", value.strip())
                if not found:
                    continue
                letters.append(found.group(1).upper())
            if len(letters) == len(values) and letters:
                ordered = sorted(dict.fromkeys(letters))
                if len(ordered) >= 2:
                    return f"{ordered[0]}-{ordered[-1]}"
                return ordered[0]
        separator = "、" if any(re.search(r"[\u4e00-\u9fff]", value) for value in values) else ","
        return separator.join(values)

    def _row_context_allowed(self, match: FieldMatch, table, row_index: int, row_text: str) -> bool:
        """应用字段配置中声明的通用表格和行上下文约束。"""
        config = match.candidate.field_config
        context = config.get("row_context") or {}
        if not context:
            return True
        table_text = getattr(table, "meta", {}).get("table_text") or match.candidate.text or ""
        section_text = " / ".join(getattr(table, "section_path", []) or match.candidate.section_path or [])
        headers = self._column_headers(table, row_index)
        header_text = " | ".join(headers.values())
        before_rows = table.rows[: row_index + 1]
        previous_text = "\n".join(" | ".join(cell.text for cell in self._expanded_row(row)) for row in before_rows[-6:])
        full_context = f"{section_text}\n{table_text}\n{header_text}"
        local_context = f"{previous_text}\n{row_text}\n{header_text}"
        require_any = context.get("require_any") or []
        require_all = context.get("require_all") or []
        row_require_any = context.get("row_require_any") or []
        reject_any = context.get("reject_any") or []
        row_reject_any = context.get("row_reject_any") or []
        if require_any and not any(keyword in full_context for keyword in require_any):
            return False
        if require_all and not all(keyword in full_context for keyword in require_all):
            return False
        if row_require_any and not any(keyword in local_context for keyword in row_require_any):
            return False
        if reject_any and any(keyword in full_context for keyword in reject_any):
            return False
        if row_reject_any and any(keyword in local_context for keyword in row_reject_any):
            return False
        return True

    def _preferred_string_value(self, text: str, field_config: dict) -> str | None:
        """字符串字段存在优选值时，返回配置的短语。"""
        preferred_values = field_config.get("preferred_values") or []
        for value in sorted(set(preferred_values), key=len, reverse=True):
            if value and value in text:
                return value
        return None

    def _clean_string_value(self, text: str) -> str:
        """移除中文抽取短语开头常见的连接词。"""
        strip_chars = "\uff1a:,\uff0c\u3002\uff1b; "
        cleaned = text.strip().strip(strip_chars)
        prefixes = (
            "\u4e3a",
            "\u7ea6",
            "\u6309",
            "\u91c7\u7528",
            "\u62df\u91c7\u7528",
            "\u9009\u7528",
            "\u672c\u671f",
            "\u672c\u9636\u6bb5",
            "\u5bb9\u91cf\u4e3a",
        )
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip().strip(strip_chars)
                    changed = True
        return cleaned.strip(strip_chars)

    def _value_allowed(self, value_text: str | None, field_config: dict) -> bool:
        """排序前拒绝超出配置校验范围的数值。"""
        if value_text is None:
            return True
        validators = field_config.get("validators") or {}
        reject_contains = validators.get("reject_contains") or []
        if reject_contains and any(token in str(value_text) for token in reject_contains):
            return False
        allow_pattern = validators.get("allow_pattern")
        if allow_pattern and not re.search(allow_pattern, str(value_text)):
            return False
        if field_config.get("value_type") != "number":
            return True
        try:
            value = float(str(value_text).replace(",", ""))
        except ValueError:
            return False
        min_value = validators.get("min")
        max_value = validators.get("max")
        if min_value is not None and value < float(min_value):
            return False
        if max_value is not None and value > float(max_value):
            return False
        return True

    def _extract_by_regex(self, match: FieldMatch) -> list[Extraction]:
        """使用字段配置正则抽取值。

        参数：
            match: 字段匹配结果。

        返回：
            list[Extraction]: 正则抽取结果。
        """
        patterns = match.candidate.field_config.get("patterns") or []
        results: list[Extraction] = []
        multi_pattern = match.candidate.field_config.get("multi_number_pattern")
        if multi_pattern:
            results.extend(self._extract_by_multi_number_pattern(match, multi_pattern))
        for pattern in patterns:
            for found in self._iter_regex_matches(pattern, match.candidate.text):
                raw_value = self._value_from_regex_match(found)
                unit = self._unit_from_regex_match(found, match.candidate.field_config)
                if self._looks_like_heading_number(
                    match.candidate.text, raw_value, match.candidate.field_config,
                    allow_missing_alias=bool(match.candidate.meta.get("observation_hint")),
                ):
                    continue
                if not self._value_allowed(raw_value, match.candidate.field_config):
                    continue
                evidence = self._build_evidence(match, found.group(0), "regex")
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=raw_value,
                        value=raw_value,
                        unit=unit,
                        score=match.score + 0.4,
                        method="regex",
                        evidence=evidence,
                        debug={"pattern": pattern},
                    )
                )
        if results:
            return results

        for derived in match.candidate.field_config.get("derived_patterns") or []:
            pattern = derived.get("pattern")
            if not pattern:
                continue
            for found in re.finditer(pattern, match.candidate.text):
                op = derived.get("op")
                if op == "sum_groups":
                    raw_groups = [group for group in found.groups() if group is not None]
                    number_groups = [group for group in raw_groups if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", str(group).strip())]
                    if not number_groups:
                        continue
                    raw_value = str(sum(float(group) for group in number_groups))
                    unit = derived.get("unit")
                elif op == "subtract_from":
                    group_index = int(derived.get("group", 1) or 1)
                    raw_value = found.group(group_index) if len(found.groups()) >= group_index else found.group(0)
                    unit = found.group(group_index + 1) if len(found.groups()) >= group_index + 1 else None
                    try:
                        base_value = float(derived.get("base", 100.0))
                        numeric_value = float(str(raw_value).replace(",", ""))
                        value = base_value - numeric_value
                        raw_value = str(int(value)) if value.is_integer() else str(round(value, 6)).rstrip("0").rstrip(".")
                    except (TypeError, ValueError):
                        continue
                else:
                    group_index = int(derived.get("group", 1) or 1)
                    raw_value = found.group(group_index) if len(found.groups()) >= group_index else found.group(0)
                    unit = found.group(group_index + 1) if len(found.groups()) >= group_index + 1 else None
                try:
                    if op != "subtract_from":
                        numeric_value = float(str(raw_value).replace(",", ""))
                        multiplier = float(derived.get("multiplier", 1.0))
                        value = numeric_value * multiplier
                        raw_value = str(int(value)) if value.is_integer() else str(round(value, 6)).rstrip("0").rstrip(".")
                except (TypeError, ValueError):
                    continue
                if not self._value_allowed(raw_value, match.candidate.field_config):
                    continue
                evidence = self._build_evidence(match, found.group(0), "regex_derived")
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=raw_value,
                        value=raw_value,
                        unit=unit or derived.get("unit"),
                        score=match.score + 0.45,
                        method="regex_derived",
                        evidence=evidence,
                        debug={"pattern": pattern, "multiplier": derived.get("multiplier", 1.0)},
                    )
                )
        if results:
            return results

        # 字段已匹配但未配置正则时，优先取字段别名附近的数值，只作为低分候选。
        if match.candidate.meta.get("observation_hint"):
            # 名称相似度只用于定位原文；没有命中字段正则时不猜测数值。
            return []
        if match.candidate.field_config.get("regex_fallback_enabled") is False:
            return []
        if match.candidate.field_config.get("value_type") != "number":
            return []
        value_text, unit = self._number_near_alias(match.candidate.text, match.candidate.field_config)
        if value_text is None:
            return []
        if self._looks_like_heading_number(match.candidate.text, value_text, match.candidate.field_config):
            return []
        if not self._value_allowed(value_text, match.candidate.field_config):
            return []
        return [
            Extraction(
                field_code=match.candidate.field_code,
                field_name=match.candidate.field_name,
                raw_value=value_text,
                value=value_text,
                unit=unit,
                score=match.score + 0.1,
                method="regex_fallback",
                evidence=self._build_evidence(match, match.candidate.text, "regex_fallback"),
                debug={},
            )
        ]

    def _iter_regex_matches(self, pattern: str, text: str):
        yield from re.finditer(pattern, text)
        compact = self._compact_text(text)
        if compact != text:
            yield from re.finditer(pattern, compact)

    def _compact_text(self, text: str) -> str:
        return ''.join(str(text or '').split())

    def _unit_from_regex_match(self, found: re.Match, field_config: dict) -> str | None:
        groupdict = found.groupdict()
        if 'unit' in groupdict:
            return self._clean_unit(groupdict.get('unit'), field_config)
        if len(found.groups()) >= 2:
            return self._clean_unit(found.group(2), field_config)
        return self._clean_unit(None, field_config)

    def _value_from_regex_match(self, found: re.Match) -> str:
        groupdict = found.groupdict()
        if 'value' in groupdict and groupdict.get('value') is not None:
            return groupdict['value']
        return found.group(1) if found.groups() else found.group(0)

    def _extract_by_multi_number_pattern(self, match: FieldMatch, pattern: str) -> list[Extraction]:
        """先定位上下文片段，再抽取片段中的多个数字。"""
        results: list[Extraction] = []
        number_pattern = self._multi_number_value_pattern(match.candidate.field_config)
        for found in re.finditer(pattern, match.candidate.text):
            segment = found.group(1) if found.groups() else found.group(0)
            if not segment:
                continue
            for number in number_pattern.finditer(segment):
                raw_value = number.group('value')
                unit = self._clean_unit(number.group('unit'), match.candidate.field_config)
                if not self._value_allowed(raw_value, match.candidate.field_config):
                    continue
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=raw_value,
                        value=raw_value,
                        unit=unit or match.candidate.field_config.get('standard_unit'),
                        score=match.score + 0.35,
                        method='regex_multi',
                        evidence=self._build_evidence(match, found.group(0), 'regex_multi'),
                        debug={'pattern': pattern},
                    )
                )
        return results

    def _multi_number_value_pattern(self, field_config: dict) -> re.Pattern[str]:
        """构建保留配置单位的数值匹配器，并跳过嵌在单位中的数字。"""
        unit_aliases = list(field_config.get('unit_aliases') or [])
        standard_unit = field_config.get('standard_unit')
        if standard_unit:
            unit_aliases.append(standard_unit)
        expanded_aliases = []
        for unit in unit_aliases:
            if not unit:
                continue
            expanded_aliases.append(unit)
            expanded_aliases.append(unit.replace('2', '²').replace('3', '³'))
        escaped_units = [re.escape(unit) for unit in sorted(set(expanded_aliases), key=len, reverse=True) if unit]
        if escaped_units:
            unit_group = '|'.join(escaped_units)
            return re.compile(
                rf'(?<![0-9A-Za-z])(?P<value>[-+]?\d+(?:\.\d+)?)(?:(?:\s*(?P<unit>{unit_group}))|(?=[\s,，、;；。:：\)\]】]|$))'
            )
        return re.compile(r'(?<![0-9A-Za-z])(?P<value>[-+]?\d+(?:\.\d+)?)(?=[\s,，、;；。:：\)\]】]|$)')
    def _number_near_alias(self, text: str, field_config: dict) -> tuple[str | None, str | None]:
        """在字段名/别名附近找数值，降低章节号、序号被兜底命中的概率。"""
        aliases = [field_config.get("name", "")]
        aliases.extend(field_config.get("aliases") or [])
        alias_indexes = [text.find(alias) for alias in aliases if alias and text.find(alias) >= 0]
        if not alias_indexes:
            compact_text = self._compact_text(text)
            alias_indexes = [compact_text.find(self._compact_text(alias)) for alias in aliases if alias and compact_text.find(self._compact_text(alias)) >= 0]
            if alias_indexes:
                value_text, unit = self._first_number_with_unit(compact_text[min(alias_indexes): min(len(compact_text), max(alias_indexes) + self.number_near_alias_window)], field_config)
                if value_text is not None:
                    return value_text, unit
        if not alias_indexes:
            return None, None
        start = min(alias_indexes)
        end = min(len(text), max(alias_indexes) + self.number_near_alias_window)
        value_text, unit = self._first_number_with_unit(text[start:end], field_config)
        if value_text is not None:
            return value_text, unit
        return None, None

    def _looks_like_heading_number(self, text: str, value_text: str, field_config: dict,
                                   allow_missing_alias: bool = False) -> bool:
        """从低信息量兜底候选中排除章节号、表号和图号。"""
        stripped = text.strip()
        if not stripped:
            return True
        if field_config.get("value_type") != "number" and field_config.get("regex_requires_alias") is False:
            return False
        aliases = [field_config.get("name", ""), *(field_config.get("aliases") or [])]
        compact_stripped = self._compact_text(stripped)
        if not allow_missing_alias and not any(
            alias and (alias in stripped or self._compact_text(alias) in compact_stripped) for alias in aliases
        ):
            return True
        if any(re.fullmatch(pattern, stripped) for pattern in self.heading_exclusion_patterns):
            return True
        if value_text and stripped.startswith(value_text) and not any(mark in stripped for mark in self.heading_value_markers):
            return True
        return False

    def _first_number_with_unit(self, text: str, field_config: dict | None = None) -> tuple[str | None, str | None]:
        """提取第一个数值和单位。

        参数：
            text: 文本。

        返回：
            tuple[str | None, str | None]: 数值文本和单位。
        """
        found = self.NUMBER_PATTERN.search(text)
        if not found:
            return None, None
        return found.group(1), self._clean_unit(found.group(2), field_config or {})

    def _last_number_with_unit(self, text: str, field_config: dict | None = None) -> tuple[str | None, str | None]:
        """提取最后一个数值和单位。

        参数：
            text: 文本。

        返回：
            tuple[str | None, str | None]: 数值文本和单位。
        """
        matches = list(self.NUMBER_PATTERN.finditer(text))
        if not matches:
            return None, None
        found = matches[-1]
        return found.group(1), self._clean_unit(found.group(2), field_config or {})

    def _clean_unit(self, unit: str | None, field_config: dict) -> str | None:
        """只保留字段配置允许的单位，避免把普通中文误当单位。"""
        if not unit:
            return None
        unit_aliases = list(field_config.get("unit_aliases") or [])
        standard_unit = field_config.get("standard_unit")
        if standard_unit:
            unit_aliases.append(standard_unit)
        for allowed_unit in sorted(set(unit_aliases), key=len, reverse=True):
            if unit.startswith(allowed_unit) or self._compact_text(unit).startswith(self._compact_text(allowed_unit)):
                return allowed_unit
        return None

    def _build_evidence(self, match: FieldMatch, text: str, method: str) -> FieldEvidence:
        """构建证据对象。

        参数：
            match: 字段匹配结果。
            text: 证据文本。
            method: 抽取方法。

        返回：
            FieldEvidence: 字段证据。
        """
        candidate = match.candidate
        return FieldEvidence(
            source_type=candidate.source_type,
            text=text,
            score=match.score,
            block_id=candidate.block_id,
            table_id=candidate.table_id,
            page=candidate.page,
            section_path=candidate.section_path.copy(),
            match_method=f"{match.method}+{method}",
        )


