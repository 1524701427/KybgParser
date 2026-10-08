"""Generation summary, turbine selection and energy extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import ParsedField


class GenerationRulesMixin:
    def _generation_summary_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        row = self._generation_summary_row_from_document(ast)
        return self._schema_row_table("generationSummary", row) if any(value is not None for value in row.values()) else None

    def _generation_summary_row_from_document(self, ast: DocumentAST) -> dict[str, Any]:
        row: dict[str, Any] = {
            "installedCapacity": None,
            "turbineCount": None,
            "turbineCapacity": None,
            "generationHubHeight": None,
            "nonWakeLossFactor": None,
            "gridAnnualEnergy": None,
            "equivalentFullLoadHours": None,
        }
        for block in reversed(self._body_blocks(ast)):
            text = self._clean_text(block.text)
            if not text:
                continue
            self._merge_generation_text_fields(row, text, block)
        if row.get("installedCapacity") is None and row.get("turbineCount") is not None and row.get("turbineCapacity") is not None:
            row["installedCapacity"] = round(float(row["turbineCount"]) * float(row["turbineCapacity"]) / 1000, 6)
            row["installedCapacityEvidence"] = row.get("turbineCapacityEvidence") or row.get("turbineCountEvidence")
        for table in ast.tables:
            matrix = self._table_matrix(table)
            text = self._matrix_text(matrix)
            self._merge_generation_summary_table_fields(row, table, matrix, text)
            factor = self._value_by_row_label(matrix, ["\u4e0d\u8003\u8651\u5c3e\u6d41\u6548\u5e94\u7684\u6298\u51cf\u7cfb\u6570", "\u7efc\u5408\u6298\u51cf\u7cfb\u6570"])
            if factor is not None:
                row["nonWakeLossFactor"] = self._ratio_to_percent(factor)
                row["nonWakeLossFactorEvidence"] = text
                break
            match = re.search(r"(?:\u4e0d\u8003\u8651\u5c3e\u6d41\u6548\u5e94\u7684\u6298\u51cf\u7cfb\u6570|\u7efc\u5408\u6298\u51cf\u7cfb\u6570).{0,20}?([0-9]+(?:\.[0-9]+)?)\s*%", text)
            if match:
                row["nonWakeLossFactor"] = self._normalize_scalar(match.group(1))
                row["nonWakeLossFactorEvidence"] = text
                break
        preferred_hours = self._preferred_equivalent_full_load_hours(ast)
        if preferred_hours is not None:
            value, evidence = preferred_hours
            row["equivalentFullLoadHours"] = value
            row["equivalentFullLoadHoursEvidence"] = evidence
        return row

    def _merge_generation_summary_table_fields(self, row: dict[str, Any], table: DocumentTable, matrix: list[list[str]], table_text: str) -> None:
        if not self._is_generation_summary_matrix(table, matrix, table_text):
            return
        field_specs = {
            "installedCapacity": (["装机容量", "总装机容量"], "MW"),
            "turbineCapacity": (["单机容量"], "KW"),
            "turbineCount": (["台数", "机组台数", "风机台数"], "台"),
            "nonWakeLossFactor": (["不考虑尾流效应的折减系数", "综合折减系数"], "%"),
            "gridAnnualEnergy": (["年上网电量", "年上网发电量"], "万kW·h"),
            "equivalentFullLoadHours": (["年等效满负荷小时数", "等效满负荷小时数", "等效小时数", "利用小时数"], "h"),
        }
        for code, (aliases, unit) in field_specs.items():
            existing_meta = row.get(f"{code}Meta") or {}
            if row.get(code) is not None and existing_meta.get("sourceType") == "table":
                continue
            value = self._generation_summary_table_value(matrix, aliases, code)
            if value is None:
                continue
            row[code] = value
            row[f"{code}Evidence"] = table_text
            row[f"{code}Meta"] = {
                "sourceType": "table",
                "resolver": "generation_summary_table",
                "sectionPath": list(table.section_path or ["发电量章节"]),
                "tableId": table.id,
                "caption": table.caption or self._caption_before_table_from_table(table),
                "unit": unit,
            }

    def _is_generation_summary_matrix(self, table: DocumentTable, matrix: list[list[str]], table_text: str) -> bool:
        caption = self._clean_text(table.caption or self._caption_before_table_from_table(table) or "")
        combined = f"{caption}\n{table_text}"
        if "单机发电量" in combined or "单台风机" in combined or "风机编号" in combined:
            return False
        if not any(keyword in combined for keyword in ("发电量计算表", "发电量计算成果表", "年上网电量估算表")):
            return False
        header_text = " ".join(matrix[0]) if matrix else ""
        has_project_row_layout = "项目" in header_text and (
            "单位" in header_text or "数值" in header_text or "指标" in header_text
        )
        has_horizontal_metric_layout = any(
            keyword in header_text
            for keyword in (
                "不考虑尾流效应的折减系数",
                "年上网电量",
                "年上网发电量",
                "年等效满负荷小时数",
                "等效满负荷小时数",
                "等效小时数",
            )
        )
        return has_project_row_layout or has_horizontal_metric_layout

    def _generation_summary_table_value(self, matrix: list[list[str]], aliases: list[str], code: str) -> Any:
        horizontal_value = self._generation_summary_horizontal_value(matrix, aliases)
        if horizontal_value is not None:
            return horizontal_value
        for row in matrix:
            label = self._row_label(row)
            if not any(alias in label for alias in aliases):
                continue
            if code == "turbineCount":
                expression_value = self._turbine_count_expression_value(row)
                if expression_value is not None:
                    return expression_value
            numbers = self._numeric_cells(row)
            for index, value in numbers:
                if index > 1:
                    return value
            if numbers:
                return numbers[-1][1]
        return None

    def _generation_summary_horizontal_value(self, matrix: list[list[str]], aliases: list[str]) -> Any:
        horizontal_metric_aliases = (
            "不考虑尾流效应的折减系数",
            "综合折减系数",
            "年上网电量",
            "年上网发电量",
            "年等效满负荷小时数",
            "等效满负荷小时数",
            "等效小时数",
        )
        for header_index, header in enumerate(matrix[:-1]):
            metric_hits = sum(
                1
                for text in header
                if any(alias in self._clean_text(text) for alias in horizontal_metric_aliases)
            )
            if metric_hits < 2:
                continue
            matching_columns = [
                column_index
                for column_index, text in enumerate(header)
                if any(alias in self._clean_text(text) for alias in aliases)
            ]
            if not matching_columns:
                continue
            for value_row in matrix[header_index + 1 :]:
                for column_index in matching_columns:
                    if column_index >= len(value_row):
                        continue
                    value = self._normalize_table_cell(str(value_row[column_index]).replace("%", ""))
                    if value is not None:
                        return value
        return None

    def _turbine_count_expression_value(self, row: list[str]) -> Any:
        for cell in row[1:]:
            text = self._clean_text(cell).replace(" ", "")
            if not re.fullmatch(r"\d+(?:[+＋]\d+)+台?", text):
                continue
            numbers = [int(value) for value in re.findall(r"\d+", text)]
            if numbers:
                return sum(numbers)
        return None

    def _preferred_equivalent_full_load_hours(self, ast: DocumentAST) -> tuple[Any, str] | None:
        text_candidate = self._equivalent_full_load_hours_from_generation_text(ast)
        if text_candidate is not None:
            return text_candidate
        candidates: list[tuple[int, Any, str]] = []
        for table in ast.tables:
            matrix = self._table_matrix(table)
            table_text = self._matrix_text(matrix)
            section_text = " ".join(table.section_path or [])
            source_text = f"{section_text}\n{table.caption or ''}\n{table_text}"
            if not any(keyword in source_text for keyword in ("\u53d1\u7535\u91cf", "\u5e74\u4e0a\u7f51\u7535\u91cf", "\u5e74\u4e0a\u7f51\u53d1\u7535\u91cf")):
                continue
            for row in matrix:
                label = self._row_label(row)
                if not any(alias in label for alias in ("\u5e74\u7b49\u6548\u6ee1\u8d1f\u8377\u5c0f\u65f6\u6570", "\u5e74\u5229\u7528\u5c0f\u65f6\u6570", "\u7b49\u6548\u5c0f\u65f6\u6570")):
                    continue
                if "h" not in " ".join(row):
                    continue
                value = self._first_numeric_after_unit_cell(row, "h") or self._last_numeric_cell(row)
                if value is not None:
                    score = 100
                    if "\u98ce\u7535\u573a\u5de5\u7a0b\u5e74\u4e0a\u7f51\u7535\u91cf\u8ba1\u7b97\u6210\u679c\u8868" in source_text:
                        score += 80
                    if "\u7b2c\u4e94\u7ae0" in section_text or "\u53d1\u7535\u91cf" in section_text:
                        score += 60
                    if "\u65b9\u6848 1" in table_text or "\u5907\u9009\u673a\u578b" in table_text:
                        score -= 80
                    candidates.append((score, value, table_text))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1], candidates[0][2]
        text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        for segment in re.split(r"[\n\u3002\uff1b;]", text):
            if "\u8003\u8651\u5f03\u7535\u540e" not in segment or "\u5e74\u7b49\u6548\u6ee1\u8d1f\u8377\u5c0f\u65f6\u6570" not in segment:
                continue
            match = re.search(r"\u5e74\u7b49\u6548\u6ee1\u8d1f\u8377\u5c0f\u65f6\u6570\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*h", segment, flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group(1)), segment
        return None

    def _equivalent_full_load_hours_from_generation_text(self, ast: DocumentAST) -> tuple[Any, str] | None:
        candidates: list[tuple[int, int, Any, str]] = []
        pattern = re.compile(r"\u5e74\u7b49\u6548\u6ee1\u8d1f\u8377\u5c0f\u65f6\u6570\s*\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*h", flags=re.IGNORECASE)
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not text or "\u5e74\u7b49\u6548\u6ee1\u8d1f\u8377\u5c0f\u65f6\u6570" not in text:
                continue
            section_text = " ".join(block.section_path or [])
            for match in pattern.finditer(text):
                value = self._normalize_scalar(match.group(1))
                window = text[max(0, match.start() - 140): match.end() + 40]
                score = 10
                if "\u7b2c\u4e94\u7ae0" in section_text or "\u53d1\u7535\u91cf" in section_text:
                    score += 100
                if "\u5e74\u4e0a\u7f51\u53d1\u7535\u91cf" in window or "\u5e74\u4e0a\u7f51\u7535\u91cf" in window:
                    score += 40
                if "\u8003\u8651\u5f03\u7535\u540e" in window:
                    score += 80
                if "\u6280\u7ecf" in section_text or "\u5de5\u7a0b\u8bbe\u8ba1\u6982\u7b97" in section_text:
                    score -= 20
                candidates.append((score, block.order, value, text))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2], candidates[0][3]

    def _first_numeric_after_unit_cell(self, row: list[str], unit: str) -> Any:
        unit_index = next((index for index, cell in enumerate(row) if unit in str(cell)), None)
        if unit_index is None:
            return None
        for cell in row[unit_index + 1:]:
            cleaned = str(cell).replace(",", "").strip()
            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
                return self._normalize_scalar(cleaned)
        return None

    def _merge_generation_text_fields(self, row: dict[str, Any], text: str, block: DocumentBlock | None = None) -> None:
        for code, spec in self.generation_text_field_specs.items():
            if row.get(code) is not None:
                continue
            for pattern in spec.get("patterns") or []:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                value = self._normalize_scalar(match.group(1))
                if code == "installedCapacity" and "万千瓦" in match.group(0):
                    value = self._normalize_scalar(str(float(value) * 10))
                row[code] = value
                row[f"{code}Evidence"] = text
                row[f"{code}Meta"] = {
                    "ruleSource": spec.get("ruleSource") or "parser_engine.output.result_builder._merge_generation_text_fields",
                    "configuredField": code,
                    "configuredRule": "generation_text_fields",
                    "matchedPattern": pattern,
                    "matchedText": match.group(0),
                    "matchStart": match.start(),
                    "matchEnd": match.end(),
                    "matchMethod": "deterministic_regex",
                    "resolver": "generation_text_regex",
                    "sectionPath": list(block.section_path or []) if block else ["发电量章节"],
                    "blockId": block.id if block else None,
                    "page": block.page if block else None,
                }
                break

    def _average_wake_loss_from_single_turbine_table(self, ast: DocumentAST) -> Any:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            header = matrix[0]
            header_text = " | ".join(header)
            if "尾流" not in header_text or not ("折减" in header_text or "系数" in header_text):
                continue
            indexes = [index for index, cell in enumerate(header) if "尾流" in cell and ("折减" in cell or "系数" in cell)]
            for index in indexes:
                values = []
                for source_row in matrix[1:]:
                    if index >= len(source_row):
                        continue
                    value = self._normalize_scalar(source_row[index].replace("%", ""))
                    if isinstance(value, (int, float)) and -100 <= value <= 100:
                        values.append(float(value))
                if values:
                    return round(sum(values) / len(values), 2)
        return None

    def _turbine_capacity_kw(self, fields: dict[str, ParsedField]) -> Any:
        field = fields.get("turbineCapacity")
        if field is None or field.value is None:
            return None
        if isinstance(field.value, (int, float)):
            return int(round(float(field.value) * 1000))
        try:
            return int(round(float(str(field.value).replace(",", "")) * 1000))
        except ValueError:
            return field.value

    def _single_turbine_annual_energy_table(self, ast: DocumentAST) -> dict[str, Any] | None:
        table = None
        best_score = 0
        for candidate in ast.tables:
            matrix = self._table_matrix(candidate)
            if not matrix:
                continue
            header_text = " | ".join(matrix[0])
            caption_text = candidate.caption or self._caption_before_table(ast, candidate)
            if "备选机型" in caption_text or re.search(r"5\.3-2[A-Za-z0-9]", caption_text):
                continue
            body_text = self._table_text(candidate)
            combined = "\n".join([header_text, caption_text, body_text])
            score = 0
            if any(keyword in caption_text for keyword in ["单台风机年上网电量", "单台机组上网电量"]):
                score += 4
            if any(keyword in header_text for keyword in ["标签", "风机编号"]):
                score += 2
            if "X" in header_text and "Y" in header_text:
                score += 1
            if "年发电量" in header_text or "年均发电量" in header_text:
                score += 2
            if "上网电量" in header_text:
                score += 2
            if "项目 | 单位 | 指标" in header_text:
                score -= 4
            if score > best_score and any(keyword in combined for keyword in ["单台风机年上网电量", "年上网电量计算成果表", "风机编号", "标签"]):
                table = candidate
                best_score = score
        if table is None:
            return None
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return None
        columns = matrix[0]
        data_rows = [row for row in matrix[1:] if any(cell.strip() for cell in row)]
        cell_sources: list[list[dict[str, Any] | None]] = []
        for source_row_index, row in enumerate(matrix[1:], start=1):
            if not any(cell.strip() for cell in row):
                continue
            cell_sources.append(
                [
                    self._table_cell_source(
                        table,
                        source_row_index,
                        column_index,
                        "单台风机年上网电量计算成果表按原文表格单元格导出。",
                        resolver="document_table_passthrough",
                    )
                    if column_index < len(row) and row[column_index].strip()
                    else None
                    for column_index in range(len(columns))
                ]
            )
        data_rows.extend(self._single_turbine_continuation_rows(ast, table, len(columns)))
        for _ in range(len(cell_sources), len(data_rows)):
            cell_sources.append([None for _ in columns])
        data = [[self._normalize_scalar(cell) for cell in row] for row in data_rows]
        if not data:
            return None
        result = {
            "key": "singleTurbineAnnualEnergy",
            "name": table.caption or self._caption_before_table(ast, table) or "\u5355\u53f0\u98ce\u673a\u5e74\u4e0a\u7f51\u7535\u91cf\u8ba1\u7b97\u6210\u679c\u8868",
            "columns": columns,
            "columnKeys": [f"col_{index}" for index in range(len(columns))],
            "index": list(range(len(data))),
            "data": data,
        }
        if any(any(source is not None for source in row) for row in cell_sources):
            result["_cellSources"] = cell_sources
        return result

    def _single_turbine_continuation_rows(self, ast: DocumentAST, table: DocumentTable, column_count: int) -> list[list[str]]:
        rows: list[list[str]] = []
        tables = sorted(ast.tables, key=lambda item: item.order)
        selected = False
        for candidate in tables:
            if candidate is table:
                selected = True
                continue
            if not selected:
                continue
            if candidate.order > table.order + 3:
                break
            matrix = self._table_matrix(candidate)
            if not matrix:
                break
            candidate_rows = [row for row in matrix if len(row) == column_count and row and re.match(r"^\d+", row[0].strip())]
            if not candidate_rows:
                break
            rows.extend(candidate_rows)
        return rows

    def _apply_generation_field_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        table_values = self._generation_values_from_tables(ast)
        for code, override in table_values.items():
            if code in skip_codes:
                continue
            name, value, unit, evidence_text, *rest = override
            meta = rest[0] if rest and isinstance(rest[0], dict) else None
            source_type = (meta or {}).get("sourceType") or (meta or {}).get("source_type") or "paragraph"
            self._set_field(fields, code, name, value, unit, evidence_text, source_type=source_type, meta=meta)

    def _generation_values_from_tables(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str, dict[str, Any]]]:
        values: dict[str, tuple[str, Any, str | None, str, dict[str, Any]]] = {}
        row = self._generation_summary_row_from_document(ast)
        field_meta = {
        "installedCapacity": ("装机容量", "MW"),
        "turbineCount": ("风机台数", "台"),
        "turbineCapacity": ("单机容量", "KW"),
        "generationHubHeight": ("轮毂高度", "m"),
        "nonWakeLossFactor": ("不考虑尾流效应的折减系数", "%"),
            "gridAnnualEnergy": ("年上网发电量", "万kW·h"),
            "equivalentFullLoadHours": ("年等效满负荷小时数", "h"),
        }
        for code, (name, unit) in field_meta.items():
            value = row.get(code)
            if value is None:
                continue
            meta = dict(row.get(f"{code}Meta") or {})
            meta.setdefault("sectionPath", ["发电量章节"])
            meta.setdefault("resolver", "generation_summary_override")
            values[code] = (
                name,
                value,
                unit,
                row.get(f"{code}Evidence") or "generation source text",
                meta,
            )
        return values

    def _selected_turbine_safety_class_from_ast(self, ast: DocumentAST) -> str | None:
        candidates: list[tuple[int, str, str]] = []
        patterns = [
            r"(IEC\s*61400[:：\-\s]*2019[^。；;\n]{0,40}(?:III|\u2162)[^。；;\n]{0,40}(?:风力发电机组|风电机组))",
            r"((?:IEC\s*)?(?:III|\u2162)\s*C?\s*(?:类|级)?(?:及以上|以上)?[^。；;\n]{0,30}(?:风力发电机组|风电机组))",
            r"((?:风电场|本工程)[^。；;\n]{0,50}采用[^。；;\n]{0,60}(?:IEC|III|\u2162)[^。；;\n]{0,60}(?:风力发电机组|风电机组))",
        ]
        for block in self._blocks_in_sections(ast, ["风能资源", "风资源", "资源", "风力发电机组", "发电量"]):
            text = self._clean_text(block.text)
            if not any(keyword in text for keyword in ("IEC", "风力发电机组", "风电机组")):
                continue
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    value = self._normalize_turbine_safety_class_value(match.group(1).strip())
                    if value and self._valid_turbine_safety_class(value):
                        score = self._turbine_safety_class_score(value, text)
                        candidates.append((score, value, text))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _normalize_turbine_safety_class_value(self, value: str) -> str:
        value = self._normalize_text_value(value)
        match = re.search(
            r"(IEC\s*(?:III|\u2162)\s*[A-Ca-c]\s*(?:\u7c7b|\u7ea7)?\s*(?:\u53ca(?:\u5176)?\u4ee5\u4e0a)?(?:\u5b89\u5168\u7b49\u7ea7|\u7b49\u7ea7)?(?:\u7684)?(?:\u98ce\u673a|\u98ce\u529b\u53d1\u7535\u673a\u7ec4|\u98ce\u7535\u673a\u7ec4)?)",
            value,
            flags=re.IGNORECASE,
        )
        if match:
            value = match.group(1)
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"IECIII", "IEC\u2162", value, flags=re.IGNORECASE)
        value = re.sub(r"IEC\u2162([a-c])", lambda item: f"IEC\u2162{item.group(1)}", value, flags=re.IGNORECASE)
        return value

    def _valid_turbine_safety_class(self, value: str) -> bool:
        compact = self._compact_text(value)
        if any(keyword in value for keyword in ("风力发电机组", "风电机组")) and re.search(r"IEC|III|\u2162", value, flags=re.IGNORECASE):
            return True
        return bool(re.search(r"(?:IEC)?(?:III|\u2162)\s*[A-Ca-c](?:类|级)?(?:及(?:其)?以上)?", compact, flags=re.IGNORECASE))

    def _turbine_safety_class_score(self, value: str, text: str) -> int:
        score = 0
        for keyword in ("综上", "初步建议", "采用", "最终", "宜选", "IEC61400", "IEC 61400"):
            if keyword in text or keyword in value:
                score += 2
        if "基坑" in text or "支护" in text or "建筑" in text:
            score -= 10
        return score

    def _sum_first_generation_column(self, ast: DocumentAST) -> float | None:
        result = self._sum_first_generation_column_with_unit(ast)
        return result[0] if result is not None else None

    def _sum_first_generation_column_with_unit(self, ast: DocumentAST) -> tuple[float, str | None] | None:
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            header = matrix[0]
            header_text = " | ".join(header)
            if not any(keyword in header_text for keyword in ("\u98ce\u673a\u7f16\u53f7", "\u6807\u7b7e")) or "\u5e74\u53d1\u7535\u91cf" not in header_text:
                continue
            indexes = [index for index, cell in enumerate(header) if "\u5e74\u53d1\u7535\u91cf" in cell]
            if not indexes:
                continue
            column_index = indexes[0]
            unit = header[column_index]
            values = []
            for row in matrix[1:]:
                if not row:
                    continue
                label = row[0].strip()
                if "合计" in label and len(row) > column_index:
                    try:
                        return round(float(row[column_index].replace(",", "")), 1), unit
                    except ValueError:
                        pass
                if "备选" in label:
                    continue
                if not re.fullmatch(r"(?:[A-Za-z]+)?\d+(?:\s*\u5907\u9009)?", label):
                    continue
                try:
                    values.append(float(row[column_index].replace(",", "")))
                except (IndexError, ValueError):
                    continue
            if len(values) >= 5:
                return round(sum(values), 1), unit
        return None
