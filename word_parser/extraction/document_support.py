"""Shared document, evidence, numeric and table helpers.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import FieldEvidence, ParsedField


class DocumentSupportMixin:
    def _first_number_after_pattern(self, text: str, pattern: str) -> Any:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        value = self._normalize_scalar(match.group(1))
        return value

    def _last_number_after_pattern(self, text: str, pattern: str) -> Any:
        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
        if not matches:
            return None
        return self._normalize_scalar(matches[-1].group(1))

    def _length_numeric_value(self, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).replace(" ", "")
        multiply = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)×([0-9]+(?:\.[0-9]+)?)", text)
        if multiply:
            return self._clean_number(float(multiply.group(1)) * float(multiply.group(2)))
        match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
        return self._clean_number(float(match.group(0))) if match else None

    def _length_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).replace(" ", "")
        return f"{text}km" if "×" in text else self._km_text(self._length_numeric_value(value))

    def _first_length_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._clean_number(float(match.group(1)))
        return None

    def _first_length_text_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = re.sub(r"\s+", "", match.group(1)).replace("x", "×").replace("X", "×")
                return value if "×" in value else self._clean_number(float(value))
        return None

    def _tower_count_from_document(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._table_text(table) for table in ast.tables if "铁塔" in self._table_text(table) or "杆塔" in self._table_text(table))
        counts = []
        for row_text in text.splitlines():
            if "铁塔组立" not in row_text and "杆塔" not in row_text:
                continue
            numbers = re.findall(r"(?<![A-Za-z])([0-9]+(?:\.[0-9]+)?)(?![A-Za-z])", row_text)
            if numbers:
                value = self._normalize_scalar(numbers[0])
                if isinstance(value, (int, float)):
                    counts.append(float(value))
        if not counts:
            return None
        return f"{self._clean_number(sum(counts))}基"

    def _direct_tower_count_from_document(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if "铁塔" in block.text or "杆塔" in block.text)
        match = re.search(r"(?:全线共用铁塔|铁塔基数|杆塔数量)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*基", text)
        return f"{self._clean_number(float(match.group(1)))}基" if match else None

    def _first_matching_text(self, text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_text_value(match.group(1).strip())
        return None

    def _first_matching_number(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            value = self._normalize_scalar(match.group(1))
            if isinstance(value, (int, float)):
                return value
        return None

    def _original_captioned_table_by_regex_from_document(
        self,
        ast: DocumentAST,
        key: str,
        patterns: list[str],
        exclude_patterns: list[str] | None = None,
        include_table_text: bool = True,
        table_candidates: list[DocumentTable] | None = None,
    ) -> dict[str, Any] | None:
        for table in (table_candidates if table_candidates is not None else ast.tables):
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            table_text = self._matrix_text(matrix)
            target_text = f"{caption}\n{section_caption}\n{table_text[:200]}" if include_table_text else f"{caption}\n{section_caption}"
            if exclude_patterns and any(re.search(pattern, target_text) for pattern in exclude_patterns):
                continue
            if not any(re.search(pattern, target_text) for pattern in patterns):
                continue
            columns = matrix[0]
            data_rows = [row for row in matrix[1:] if any(cell.strip() for cell in row)]
            if not data_rows:
                continue
            data = [[self._normalize_scalar(cell) for cell in row] for row in data_rows]
            return {
                "key": key,
                "name": caption or self._section_path_caption(table) or self.table_output_headers.get(key, {}).get("name", key),
                "columns": columns,
                "columnKeys": [f"col_{index}" for index in range(len(columns))],
                "index": list(range(len(data))),
                "data": data,
                "_sourceTable": {"tableId": table.id, "order": table.order, "caption": caption or self._section_path_caption(table), "sectionPath": table.section_path},
            }
        return None

    def _section_path_caption(self, table: DocumentTable) -> str:
        section_path = [self._clean_text(item) for item in (table.section_path or []) if self._clean_text(item)]
        return section_path[-1] if section_path else ""

    def _original_captioned_table_from_document(self, ast: DocumentAST, key: str, caption_keywords: list[str], table_candidates: list[DocumentTable] | None = None) -> dict[str, Any] | None:
        for table in (table_candidates if table_candidates is not None else ast.tables):
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._matrix_text(matrix)
            if not any(keyword in caption or keyword in table_text for keyword in caption_keywords):
                continue
            columns = matrix[0]
            data_rows = [row for row in matrix[1:] if any(cell.strip() for cell in row)]
            if not data_rows:
                continue
            data = [[self._normalize_scalar(cell) for cell in row] for row in data_rows]
            name = caption or self.table_output_headers.get(key, {}).get("name", key)
            return {
                "key": key,
                "name": name,
                "columns": columns,
                "columnKeys": [f"col_{index}" for index in range(len(columns))],
                "index": list(range(len(data))),
                "data": data,
                "_sourceTable": {"tableId": table.id, "order": table.order, "caption": caption, "sectionPath": table.section_path},
            }
        return None

    def _matrix_text(self, matrix: list[list[str]]) -> str:
        return "\n".join(" | ".join(row) for row in matrix)

    def _row_label(self, row: list[str]) -> str:
        return " ".join(cell for cell in row[:3] if cell).strip()

    def _numeric_cells(self, row: list[str]) -> list[tuple[int, Any]]:
        numbers: list[tuple[int, Any]] = []
        for index, cell in enumerate(row):
            cleaned = str(cell).replace(",", "").replace("%", "").strip()
            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
                numbers.append((index, self._normalize_scalar(cleaned)))
        return numbers

    def _last_numeric_cell(self, row: list[str]) -> Any:
        numbers = self._numeric_cells(row)
        return numbers[-1][1] if numbers else None

    def _last_measure_numeric_cell(self, row: list[str]) -> Any:
        numbers = [(index, value) for index, value in self._numeric_cells(row) if index > 0]
        return numbers[-1][1] if numbers else None

    def _value_by_row_label(
        self,
        matrix: list[list[str]],
        aliases: list[str],
        unit_hint: str | None = None,
        prefer_total: bool = False,
    ) -> Any:
        for row in matrix:
            label = self._row_label(row)
            if not any(alias in label for alias in aliases):
                continue
            if unit_hint and unit_hint not in " ".join(row):
                continue
            numbers = self._numeric_cells(row)
            if not numbers:
                if unit_hint == "km":
                    label_value = self._length_from_label(label)
                    if label_value is not None:
                        return label_value
                continue
            header = matrix[0] if len(matrix) > 1 else []
            if row is not header and len(header) == len(row):
                quantity_index = self._find_header_index(header, ["24台", "总量", "合计", "数量", "指标", "数值", "工程量"])
                if quantity_index is not None and quantity_index < len(row):
                    value = self._normalize_table_cell(row[quantity_index])
                    if value is not None:
                        return value
                if len(row) >= 3 and any(unit in row[1] for unit in ("m", "m³", "m3", "t", "个", "根", "/")):
                    value = self._normalize_table_cell(row[2])
                    if value is not None:
                        return value
            if prefer_total:
                return numbers[0][1] if len(numbers) == 1 else numbers[1][1] if numbers[0][0] <= 1 else numbers[0][1]
            for index, value in numbers:
                if index > 1:
                    return value
            return numbers[-1][1]
        return None

    def _length_from_label(self, label: str) -> Any:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(km|m)\b", label, flags=re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2).lower() == "m":
            value /= 1000
        return self._clean_number(value)

    def _header_row(self, matrix: list[list[str]], aliases: list[str]) -> list[str] | None:
        for row in matrix:
            text = " | ".join(row)
            if all(alias in text for alias in aliases):
                return row
        return None

    def _row_value_by_header(self, header: list[str] | None, row: list[str], aliases: list[str]) -> Any:
        if not header:
            return None
        index = self._find_header_index(header, aliases)
        if index is None or index >= len(row):
            return None
        return self._normalize_table_cell(row[index])

    def _amount_numeric_cell(self, row: list[str]) -> Any:
        numbers = self._numeric_cells(row)
        if not numbers:
            return None
        filtered = [(idx, value) for idx, value in numbers if not (idx == len(row) - 1 and isinstance(value, (int, float)) and 0 <= value <= 100 and len(numbers) > 1)]
        return (filtered or numbers)[-1][1]

    def _unit_by_row_label(self, matrix: list[list[str]], aliases: list[str]) -> str | None:
        for row in matrix:
            label = self._row_label(row)
            if any(alias in label for alias in aliases):
                for cell in row:
                    if any(unit in cell for unit in ("MW·h", "MWh", "万kW", "万kWh", "h", "km", "m3", "m³")):
                        return cell
        return None

    def _text_by_row_label(self, matrix: list[list[str]], aliases: list[str]) -> str | None:
        for row in matrix:
            label = self._row_label(row)
            if not any(alias in label for alias in aliases):
                continue
            for cell in row[1:]:
                cleaned = cell.strip()
                if cleaned and cleaned not in {"/", "——", "-", "--"} and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
                    return self._normalize_text_value(cleaned)
        return None

    def _energy_to_10kwh(self, value: Any, unit: str | None) -> Any:
        if value is None:
            return None
        if unit and re.search(r"MW[·.]?h|MWh|兆瓦时", unit, flags=re.IGNORECASE):
            return self._mwh_to_10kwh(value)
        return value

    def _mwh_to_10kwh(self, value: Any) -> Any:
        try:
            number = float(str(value).replace(",", "")) * 0.1
        except ValueError:
            return value
        return self._clean_number(round(number, 3))

    def _ratio_to_percent(self, value: Any) -> Any:
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            return value
        if 0 <= number <= 1:
            number *= 100
        return self._clean_number(round(number, 3))

    def _length_indexes_from_headers(self, headers: list[list[str]]) -> list[int]:
        indexes: list[int] = []
        max_columns = max((len(header) for header in headers), default=0)
        for index in range(max_columns):
            text = " ".join(header[index] for header in headers if index < len(header))
            if "长度" in text or "架空" in text or "电缆" in text:
                indexes.append(index)
        return indexes

    def _sum_numeric_cells(self, rows: list[list[str]], indexes: list[int]) -> float:
        total = 0.0
        for row in rows:
            for index in indexes:
                if index < len(row):
                    value = self._normalize_scalar(str(row[index]).replace(",", ""))
                    if isinstance(value, (int, float)):
                        total += float(value)
        return round(total, 3)

    def _sum_rows_by_label(self, matrix: list[list[str]], aliases: list[str]) -> float:
        total = 0.0
        for row in matrix:
            label = self._row_label(row)
            if any(alias in label for alias in aliases):
                value = self._value_by_row_label([row], aliases)
                if isinstance(value, (int, float)):
                    total += float(value)
        return total

    def _km_text(self, value: float | int | None) -> str | None:
        if not value:
            return None
        return f"{self._clean_number(value)}km"

    def _clean_number(self, value: float | int) -> Any:
        number = float(value)
        return int(number) if number.is_integer() else round(number, 3)

    def _normalize_table_cell(self, text: str) -> Any:
        cleaned = text.strip()
        if cleaned in {"", "——", "—", "--", "-"}:
            return None
        return self._normalize_scalar(cleaned)

    def _table_cell_source(
        self,
        table: DocumentTable,
        source_row_index: int,
        source_column_index: int,
        description: str,
        resolver: str = "document_table_cell",
    ) -> dict[str, Any]:
        matrix = self._table_matrix(table)
        source_row = matrix[source_row_index] if source_row_index < len(matrix) else []
        source_text = source_row[source_column_index] if source_column_index < len(source_row) else None
        return {
            "source": {
                "kind": "document_table_cell",
                "sourceType": "table",
                "tableId": table.id,
                "page": table.page,
                "sectionPath": table.section_path,
                "sourceRow": source_row_index,
                "sourceColumn": source_column_index,
                "sourceText": source_text,
                "rowText": " | ".join(source_row),
                "caption": self._clean_table_caption_title(table.caption or ""),
                "matchMethod": resolver,
                "description": description,
            },
            "process": {
                "resolver": resolver,
                "calculation": description,
            },
            "sourceDescription": description,
        }

    def _table_row_source(
        self,
        table: DocumentTable,
        source_row_index: int,
        description: str,
        resolver: str = "document_table_row",
    ) -> dict[str, Any]:
        matrix = self._table_matrix(table)
        source_row = matrix[source_row_index] if source_row_index < len(matrix) else []
        return {
            "source": {
                "kind": "document_table_row",
                "sourceType": "table",
                "tableId": table.id,
                "page": table.page,
                "sectionPath": table.section_path,
                "sourceRow": source_row_index,
                "sourceColumn": None,
                "sourceText": " | ".join(source_row),
                "rowText": " | ".join(source_row),
                "caption": table.caption,
                "matchMethod": resolver,
                "description": description,
            },
            "process": {
                "resolver": resolver,
                "calculation": description,
            },
            "sourceDescription": description,
        }

    def _chinese_number_to_int(self, text: str) -> int | None:
        text = text.strip()
        if text.isdigit():
            return int(text)
        mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        return mapping.get(text)

    def _document_table_passthrough(
        self,
        key: str,
        name: str,
        table: DocumentTable,
        description: str,
        resolver: str = "document_table_passthrough",
        header_columns: list[str] | None = None,
        header_source_table: DocumentTable | None = None,
        data_start_index: int | None = None,
        prefer_provided_name: bool = False,
    ) -> dict[str, Any] | None:
        """把文档原表按原单元格透传为结果表。

        Args:
            key: 输出表 key。
            name: 调用方已经确认的表名或兜底表名。
            table: AST 中的源表。
            description: 单元格来源说明。
            resolver: 来源 resolver 名称。
            header_columns: 外部继承的表头；用于跨页续表或拆分表。
            header_source_table: 表头来源表。
            data_start_index: 数据起始行。
            prefer_provided_name: 为 True 时优先使用规则实际命中的表名，避免结构层旧 caption 覆盖正确标题。

        Returns:
            dict[str, Any] | None: 可导出的原表；无有效表头或数据时返回 None。
        """
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return None
        columns = header_columns or matrix[0]
        if data_start_index is not None:
            data_source_rows = list(enumerate(matrix[data_start_index:], start=data_start_index))
        elif header_columns:
            data_source_rows = list(enumerate(matrix, start=0))
        else:
            data_source_rows = list(enumerate(matrix[1:], start=1))
        data_rows = [(source_row_index, row) for source_row_index, row in data_source_rows if any(cell.strip() for cell in row)]
        if not columns or not data_rows:
            return None
        column_count = max(len(row) for _, row in [(None, columns), *data_rows])
        columns = [columns[index] if index < len(columns) and columns[index] else f"col_{index}" for index in range(column_count)]
        data = [
            [self._normalize_scalar(row[index]) if index < len(row) else None for index in range(column_count)]
            for _, row in data_rows
        ]
        cell_sources: list[list[dict[str, Any] | None]] = []
        for source_row_index, row in data_rows:
            cell_sources.append(
                [
                    self._table_cell_source(table, source_row_index, column_index, description, resolver=resolver)
                    if column_index < len(row) and row[column_index].strip()
                    else None
                    for column_index in range(column_count)
                ]
            )
        table_name = self._clean_text(name or table.caption or self._caption_before_table_from_table(table)) if prefer_provided_name else self._clean_text(table.caption or self._caption_before_table_from_table(table) or name)
        result = {
            "key": key,
            "name": table_name,
            "columns": columns,
            "columnKeys": [f"col_{index}" for index in range(len(columns))],
            "index": list(range(len(data))),
            "data": data,
            "_sourceTable": {"tableId": table.id, "order": table.order, "page": table.page, "caption": table_name or table.caption or name, "sectionPath": table.section_path},
        }
        if header_source_table is not None:
            result["_sourceTable"]["headerSource"] = {
                "tableId": header_source_table.id,
                "order": header_source_table.order,
                "caption": header_source_table.caption or self._caption_before_table_from_table(header_source_table),
                "sectionPath": header_source_table.section_path,
            }
        if any(any(source is not None for source in row) for row in cell_sources):
            result["_cellSources"] = cell_sources
        return result

    def _caption_before_table_from_table(self, table: DocumentTable) -> str:
        return table.meta.get("caption_before", "") if isinstance(table.meta, dict) else ""

    def _strip_leading_about(self, value: Any) -> Any:
        return re.sub(r"^约\s*", "", value) if isinstance(value, str) else value

    def _strip_leading_taken(self, value: Any) -> Any:
        return re.sub(r"^采取", "", value) if isinstance(value, str) else value

    def _number_regex_with_optional_trailing_zeros(self, value: float) -> str:
        text = str(self._clean_number(value))
        if "." not in text:
            return rf"{re.escape(text)}(?:\.0+)?"
        integer, decimal = text.split(".", 1)
        return rf"{re.escape(integer)}\.{re.escape(decimal)}0*"

    def _first_length_area_number(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group(1))
        return None

    def _last_numeric_cell_value(self, row: list[str]) -> Any:
        for cell in reversed(row):
            value = self._normalize_table_cell(cell)
            if value is not None:
                return value
        return None

    def _configured_header_row_index(self, matrix: list[list[str]], spec: dict[str, Any]) -> int:
        aliases: list[str] = []
        aliases.extend(spec.get("direction_column_aliases") or [])
        aliases.extend(spec.get("tower_column_aliases") or [])
        for metric in spec.get("metrics") or []:
            if isinstance(metric, dict):
                aliases.extend(metric.get("column_aliases") or [])
        for index, row in enumerate(matrix[: min(len(matrix), 6)]):
            text = " | ".join(row)
            if any(alias in text for alias in aliases if alias):
                return index
        return 0

    def _text_block_source(self, block: DocumentBlock, text: str, description: str, resolver: str) -> dict[str, Any]:
        source_text = self._clean_text(text or block.text or "")
        return {
            "source": {
                "kind": "document_text",
                "sourceType": "paragraph",
                "blockId": block.id,
                "page": block.page,
                "sectionPath": list(block.section_path or []),
                "sourceText": source_text,
                "matchMethod": resolver,
                "description": description,
            },
            "process": {
                "resolver": resolver,
                "calculation": description,
            },
            "sourceDescription": description,
        }

    def _block_containing_text(self, ast: DocumentAST, text: str) -> DocumentBlock | None:
        cleaned = self._clean_text(text or "")
        if not cleaned:
            return None
        compact = self._compact_text(cleaned)
        for block in self._body_blocks(ast):
            block_text = self._clean_text(block.text or "")
            if cleaned in block_text or compact in self._compact_text(block_text):
                return block
        return None

    def _normalize_tower_code(self, code: str) -> str:
        if not code:
            return code
        return re.sub(r"\s+", "", str(code)).replace("＃", "#")

    def _table_key_spec_matches(self, spec: dict[str, Any], text: str) -> bool:
        if not text:
            return False
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in spec.get("exclude_patterns", [])):
            return False
        patterns = spec.get("patterns") or []
        if patterns and any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return True
        all_patterns = spec.get("all_patterns") or []
        return bool(all_patterns) and all(re.search(pattern, text, flags=re.IGNORECASE) for pattern in all_patterns)

    def _raw_rows_from_table(self, table: DocumentTable) -> list[dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return []
        headers = [self._normalize_scalar(cell) for cell in matrix[0]]
        rows: list[dict[str, Any]] = []
        for source_row_index, source_row in enumerate(matrix[1:], start=1):
            if not any(cell.strip() for cell in source_row):
                continue
            row: dict[str, Any] = {}
            for index, header in enumerate(headers):
                if header in {None, ""}:
                    continue
                if index < len(source_row):
                    value = self._normalize_table_cell(source_row[index])
                    if value is not None:
                        key = str(header)
                        row[key] = value
                        row.setdefault("_cellSources", {})[key] = self._table_cell_source(
                            table,
                            source_row_index,
                            index,
                            "resource table passthrough",
                            resolver="resource_table_passthrough",
                        )
            if row:
                rows.append(row)
        return rows

    def _detail_rows_more_complete(self, candidate: list[dict[str, Any]], current: list[dict[str, Any]]) -> bool:
        if not current:
            return True
        return self._detail_row_value_count(candidate[0]) > self._detail_row_value_count(current[0])

    def _detail_row_value_count(self, row: dict[str, Any]) -> int:
        return sum(1 for key, value in row.items() if not str(key).startswith("_") and value not in (None, "", [], {}))

    def _combined_text_match_row_source(
        self,
        ast: DocumentAST,
        blocks: list[DocumentBlock],
        text: str,
        match: re.Match[str] | None,
        description: str,
        resolver: str,
    ) -> dict[str, Any]:
        evidence_text = self._clean_text(text)
        if match is not None:
            start = max(0, match.start() - 180)
            end = min(len(text), match.end() + 180)
            evidence_text = self._clean_text(text[start:end])
        source_block = self._block_containing_text(ast, match.group(0)) if match is not None else None
        source_block = source_block or next((block for block in blocks if block.text), None)
        if source_block is not None:
            return self._text_block_source(source_block, evidence_text, description, resolver=resolver)
        return {
            "source": {
                "kind": "document_text",
                "sourceType": "paragraph",
                "sourceText": evidence_text,
                "sectionPath": ["电气一次"],
                "matchMethod": resolver,
                "description": description,
            },
            "process": {"resolver": resolver, "calculation": description},
            "sourceDescription": description,
        }

    def _combined_text_row_source(self, ast: DocumentAST, text: str, description: str, resolver: str) -> dict[str, Any]:
        block = self._block_containing_text(ast, text) or next((item for item in self._body_blocks(ast) if item.text), None)
        if block is not None:
            return self._text_block_source(block, self._clean_text(text), description, resolver=resolver)
        return {
            "source": {
                "kind": "document_text",
                "sourceType": "paragraph",
                "sourceText": self._clean_text(text),
                "matchMethod": resolver,
                "description": description,
            },
            "process": {"resolver": resolver, "calculation": description},
            "sourceDescription": description,
        }

    def _merged_table_matrix(self, tables: list[DocumentTable]) -> list[list[str]]:
        matrix: list[list[str]] = []
        for table in tables:
            matrix.extend(self._table_matrix(table))
        return matrix

    def _sum_present(self, values: Any) -> Any:
        total = 0.0
        found = False
        for value in values:
            if isinstance(value, (int, float)):
                total += float(value)
                found = True
        return self._clean_number(total) if found else None

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    def _header_value_pair(self, header: list[str], row: list[str], aliases: list[str]) -> tuple[Any, Any]:
        for alias in aliases:
            index = self._find_header_index(header, [alias])
            if index is not None and index < len(row):
                return header[index], self._normalize_table_cell(row[index])
        return None, None

    def _rows_by_label(self, matrix: list[list[str]]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for row in matrix[1:]:
            if len(row) < 3:
                continue
            label = row[0].strip()
            if not label or label.startswith(("一、", "二、", "三、")):
                continue
            number = self._normalize_scalar(row[2])
            values[label] = number
            if label.startswith("电缆直埋征地"):
                values["电缆直埋征地"] = number
            if label.startswith("场地平整"):
                values["场地平整"] = number
        return values

    def _values_equivalent(self, left: Any, right: Any) -> bool:
        """比较抽取值是否等价，兼容数值字符串和浮点尾差。"""
        try:
            return abs(float(str(left).replace(",", "")) - float(str(right).replace(",", ""))) < 1e-6
        except (TypeError, ValueError):
            return self._clean_text(str(left or "")) == self._clean_text(str(right or ""))

    def _sentences(self, text: str) -> list[str]:
        return [part.strip() for part in re.split(r"(?<=[。；;])", text) if part.strip()]

    def _looks_like_unit_cell(self, text: str) -> bool:
        cleaned = self._clean_text(str(text))
        return cleaned in {"m", "m2", "m3", "m²", "m³", "t", "吨", "kg", "个", "根"}

    def _combined_field_evidence_from_row(self, row: dict[str, Any], source_key: str, detail_key: str) -> FieldEvidence | None:
        sources = row.get("_cellSources") if isinstance(row, dict) else None
        source_trace = sources.get(source_key) if isinstance(sources, dict) else None
        if not isinstance(source_trace, dict):
            source_trace = row.get("_rowSource") if isinstance(row.get("_rowSource"), dict) else None
        if not isinstance(source_trace, dict):
            return None
        source = source_trace.get("source") if isinstance(source_trace.get("source"), dict) else {}
        process = source_trace.get("process") if isinstance(source_trace.get("process"), dict) else {}
        meta = {
            "resolver": process.get("resolver") or source.get("matchMethod") or "combined_field_source",
            "sourceDetailKey": detail_key,
            "sourceColumnKey": source_key,
            "sourceRow": source.get("sourceRow"),
            "sourceColumn": source.get("sourceColumn"),
            "caption": source.get("caption"),
            "rowText": source.get("rowText"),
            "sourceDescription": source_trace.get("sourceDescription") or source.get("description"),
        }
        return FieldEvidence(
            source_type=source.get("sourceType") or source.get("kind") or "combined_field_source",
            text=source.get("sourceText") or source.get("rowText") or f"{detail_key}.{source_key}",
            score=1.0,
            block_id=source.get("blockId"),
            table_id=source.get("tableId"),
            page=source.get("page"),
            section_path=source.get("sectionPath") or [],
            match_method=source.get("matchMethod") or process.get("resolver") or "combined_field_source",
            meta={key: value for key, value in meta.items() if value not in (None, [], {})},
        )

    def _set_field_with_evidence(
        self,
        fields: dict[str, ParsedField],
        code: str,
        name: str,
        value: Any,
        unit: str | None,
        evidences: list[FieldEvidence],
    ) -> None:
        value, unit = self._normalize_configured_value(code, value, unit)
        resolver = (evidences[0].meta or {}).get("resolver") if evidences else "combined_field_source"
        fields[code] = ParsedField(
            field_code=code,
            field_name=name,
            value=value,
            unit=unit,
            normalized_value=value,
            confidence=0.99 if value is not None else 0.0,
            status="PASS" if value is not None else "MISSING",
            evidence=evidences,
            debug={"resolver": resolver or "combined_field_source"},
        )

    def _body_blocks(self, ast: DocumentAST) -> list[DocumentBlock]:
        return [block for block in ast.blocks if block.text and not self._is_toc_block(block)]

    def _source_section_path(self, section_path: list[str], canonical_sections: Any = None) -> list[str]:
        canonical = list(dict.fromkeys(str(section) for section in (canonical_sections or []) if section))
        path = [str(section) for section in (section_path or []) if section]
        return [*canonical, *[section for section in path if section not in canonical]]

    def _inferred_source_sections(self, text: str) -> list[str]:
        compact = self._compact_text(text)
        result: list[str] = []
        rules = [
            ("集电线路", ["集电线路路径长", "单回集电线路", "双回集电线路", "双回架空路径长", "单回架空路径长"]),
            ("道路", ["进场道路", "进站道路", "场内道路", "改建长度", "改建道路", "道路改造"]),
            ("电气一次", ["风电场接入系统方式", "打捆送至", "汇集站", "主变"]),
            ("发电量章节", ["风电场年上网电量估算", "综合折减率", "年上网电量"]),
        ]
        for section, keywords in rules:
            if any(keyword in text or self._compact_text(keyword) in compact for keyword in keywords):
                result.append(section)
        return result

    def _is_toc_block(self, block: DocumentBlock) -> bool:
        meta = block.meta or {}
        if str(meta.get("structure_type") or meta.get("type") or "").lower() in {"toc", "table_of_contents"}:
            return True
        return self._is_toc_like_text(block.text or "")

    def _is_toc_like_text(self, text: str) -> bool:
        cleaned = self._clean_text(text or "")
        if not cleaned:
            return False
        compact = self._compact_text(cleaned)
        lowered = cleaned.lower()
        if any(marker.lower() in lowered for marker in ("HYPERLINK", "PAGEREF", "TOC ", "\\o ", "_Toc")):
            return True
        if compact in {"目录", "目錄", "contents"}:
            return True
        if compact.startswith("目录") and len(compact) < 120:
            return True
        toc_link_hits = len(re.findall(r"_Toc\d+|PAGEREF|HYPERLINK", cleaned, flags=re.IGNORECASE))
        if toc_link_hits >= 3:
            return True
        dotted_entries = len(re.findall(r"\d+(?:\.\d+)+[^\n]{0,50}(?:\.{3,}|…{2,}|\s{2,})\d+", cleaned))
        return "目录" in cleaned[:80] and dotted_entries >= 2

    def _page_section_path_map(self, ast: DocumentAST) -> dict[int, list[str]]:
        page_sections: dict[int, list[str]] = {}
        last_section: list[str] = []
        blocks = sorted((block for block in ast.blocks if block.page is not None), key=lambda item: item.order)
        for block in blocks:
            try:
                page = int(block.page) if block.page is not None else None
            except (TypeError, ValueError):
                page = None
            if page is None:
                continue
            if block.section_path:
                last_section = list(block.section_path)
                page_sections[page] = last_section
            elif last_section and page not in page_sections:
                page_sections[page] = last_section
        return page_sections

    def _field_evidence_text_for_value(self, ast: DocumentAST, value: Any, keywords: list[str]) -> str:
        value_text = str(value)
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if value_text in text and all(keyword in text for keyword in keywords if keyword):
                return text
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if value_text in text:
                return text
        return value_text

    def _table_index_value(self, row: list[str], index: int | None) -> Any:
        if index is None or index < 0 or index >= len(row):
            return None
        value = self._clean_text(row[index])
        return value or None

    def _extract_first_pattern_value(self, text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _keyword_window(self, text: str, keywords: list[str], radius: int) -> str:
        for keyword in keywords:
            index = text.find(keyword)
            if index >= 0:
                return text[max(0, index - radius) : min(len(text), index + radius)]
        return ""

    def _regex_from_blocks(self, ast: DocumentAST, pattern: str) -> str | None:
        for block in ast.blocks:
            found = re.search(pattern, block.text)
            if found:
                return found.group(1).strip()
        return None

    def _set_field(
        self,
        fields: dict[str, ParsedField],
        code: str,
        name: str,
        value: Any,
        unit: str | None,
        evidence_text: str,
        source_type: str = "table",
        meta: dict[str, Any] | None = None,
    ) -> None:
        meta = dict(meta or {})
        value, unit = self._normalize_configured_value(code, value, unit)
        section_path = meta.pop("sectionPath", [])
        block_id = meta.pop("blockId", None)
        table_id = meta.pop("tableId", None)
        page = meta.pop("page", None)
        fields[code] = ParsedField(
            field_code=code,
            field_name=name,
            value=value,
            unit=unit,
            normalized_value=value,
            confidence=0.99 if value is not None else 0.0,
            status="PASS" if value is not None else "MISSING",
            evidence=[FieldEvidence(source_type=source_type, text=evidence_text, score=1.0, block_id=block_id, table_id=table_id, page=page, section_path=section_path, match_method=meta.get("matchMethod") or "deterministic_override", meta=meta)],
            debug={"resolver": meta.get("resolver") or "deterministic_override"},
        )

    def _table_matrix(self, table: DocumentTable) -> list[list[str]]:
        return [[cell.text.strip() for cell in self._expanded_row(row)] for row in table.rows]

    def _normalize_tower_code(self, text: str) -> str | None:
        if not text:
            return None
        normalized_text = str(text).replace("＃", "#")
        found = re.search(r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*#", normalized_text)
        if not found:
            return None
        code = re.sub(r"\s+", "", found.group(0))
        if re.fullmatch(r"\d+(?:m|M)#", code):
            return None
        return code

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[\x00-\x1f]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _clean_table_caption_title(self, caption: str) -> str:
        cleaned = self._clean_text(caption or "")
        if not cleaned:
            return ""
        markers = list(re.finditer(r"(?:附表|表)\s*\d+(?:\.\d+)*(?:-\s*\d+)?", cleaned))
        if markers and ("图" in cleaned[: markers[-1].start()] or len(markers) > 1):
            return self._clean_text(cleaned[markers[-1].start() :])
        return cleaned

    def _normalize_text_value(self, text: str) -> str:
        cleaned = self._clean_text(str(text))
        return cleaned.strip(" ?,??;?:")

    def _blocks_in_sections(self, ast: DocumentAST, section_keywords: list[str]) -> list[Any]:
        matched = [
            block
            for block in ast.blocks
            if self._section_path_matches(block.section_path, section_keywords)
        ]
        return matched or list(ast.blocks)

    def _tables_in_sections(self, ast: DocumentAST, section_keywords: list[str]) -> list[DocumentTable]:
        matched = [
            table
            for table in ast.tables
            if self._section_path_matches(table.section_path, section_keywords)
        ]
        return matched or list(ast.tables)

    def _section_path_matches(self, section_path: list[str], section_keywords: list[str]) -> bool:
        section_text = " / ".join(section_path)
        return bool(section_text) and any(keyword in section_text for keyword in section_keywords)

    def _drop_none(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if value is not None}

    def _table_matches(self, table: DocumentTable, section_text: str, spec: dict[str, Any]) -> bool:
        """Match detail tables by header signature, using section only for weak signatures."""
        if not table.rows:
            return False
        header = [cell.text for cell in self._expanded_row(table.rows[0])]
        header_text = " | ".join(header)
        if not all(keyword in header_text for keyword in spec["required_headers"]):
            return False
        column_matches = sum(
            1 for aliases in spec["columns"].values() if self._find_header_index(header, aliases) is not None
        )
        min_column_matches = spec.get("min_column_matches", min(2, len(spec["columns"])))
        value_column_matches = sum(
            1
            for key, aliases in spec["columns"].items()
            if key != "item" and self._find_header_index(header, aliases) is not None
        )
        if column_matches < min_column_matches or value_column_matches < max(1, min_column_matches - 1):
            return False
        section_keywords = spec.get("section_keywords") or []
        if not section_keywords:
            return True
        return column_matches >= max(2, min_column_matches) or any(keyword in section_text for keyword in section_keywords)

    def _rows_for_table(self, table: DocumentTable, columns: dict[str, list[str]]) -> list[dict[str, Any]]:
        """按表头映射输出表格数据行。"""
        if len(table.rows) < 2:
            return []
        header = [cell.text for cell in self._expanded_row(table.rows[0])]
        column_indexes = {key: self._find_header_index(header, aliases) for key, aliases in columns.items()}
        rows: list[dict[str, Any]] = []
        for source_row_index, row in enumerate(table.rows[1:], start=1):
            expanded = self._expanded_row(row)
            item: dict[str, Any] = {}
            for key, index in column_indexes.items():
                if index is None or index >= len(expanded):
                    continue
                text = expanded[index].text.strip()
                if not text or text in {"——", "--", "-"}:
                    continue
                item[key] = self._normalize_scalar(text)
                item.setdefault("_cellSources", {})[key] = self._table_cell_source(
                    table,
                    source_row_index,
                    index,
                    f"按原文表头映射列 {header[index]} 抽取。",
                    resolver="table_header_mapping",
                )
            public_keys = [key for key in item if not str(key).startswith("_")]
            if public_keys and (len(public_keys) > 1 or "item" not in item):
                rows.append(item)
        return rows

    def _expanded_row(self, row):
        """Expand col_span so header indexes match data-cell indexes."""
        expanded = []
        for cell in row:
            span = max(1, int(getattr(cell, "col_span", 1) or 1))
            expanded.extend([cell] * span)
        return expanded

    def _find_header_index(self, header: list[str], aliases: list[str]) -> int | None:
        """按别名查找表头列。"""
        for index, text in enumerate(header):
            if any(alias in text for alias in aliases):
                return index
        return None

    def _normalize_scalar(self, text: str) -> Any:
        """把纯数值文本转成数字，保留复杂字符串。"""
        cleaned = text.replace(",", "").strip()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
            number = float(cleaned)
            return int(number) if number.is_integer() else number
        return text

    def _table_text(self, table: DocumentTable) -> str:
        """生成表格全文。"""
        return "\n".join(" | ".join(cell.text for cell in row) for row in table.rows)

    def _caption_before_table(self, ast: DocumentAST, table: DocumentTable) -> str:
        previous = [block for block in ast.blocks if block.order < table.order and block.type == "paragraph"]
        for block in reversed(previous[-5:]):
            if any(candidate.order > block.order and candidate.order < table.order for candidate in ast.tables):
                continue
            text = self._clean_text(block.text)
            if text.startswith(("表", "附表")) or "成果表" in text:
                return text
            collector_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:电气部分材料清册|杆塔部分材料清册|基础部分材料清册|光缆部分材料清册|电缆部分材料清册|铁塔接地装置材料|集电线路部分主要设备及材料清册))",
                text,
            )
            if collector_heading:
                return self._clean_text(collector_heading.group(1))
            if any(keyword in text for keyword in ("电气部分材料清册", "杆塔部分材料清册", "基础部分材料清册", "光缆部分材料清册", "电缆部分材料清册", "铁塔接地装置材料", "集电线路部分主要设备及材料清册")):
                return text
            substation_civil_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:土建主要工程量表|升压站主要土建工程量表|升压站土建清单))",
                text,
            )
            if substation_civil_heading:
                return self._clean_text(substation_civil_heading.group(1))
            foundation_or_road_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\s*\d+)?\.?\s*(?:基础尺寸及参数表|基础断面表|箱变基础工程量表|箱变基础单台工程量表(?:（配事故油池）)?|风电场主要工程量清单|进站道路主要工程数量表))",
                text,
            )
            if foundation_or_road_heading:
                return self._clean_text(foundation_or_road_heading.group(1))
            land_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:工程永久征地面积汇总表|工程临时征地面积汇总表|工程征用地计算合计表|工程总征地|工程面积汇总|工程征用地))",
                text,
            )
            if land_heading:
                return self._clean_text(land_heading.group(1))
            earthwork_heading = re.search(
                r"((?:表\s*)?\d+(?:\.\d+)*(?:-\d+)?\.?\s*(?:场内土石方平衡|土石方平衡表(?:（万m\(3\)）)?))",
                text,
            )
            if earthwork_heading:
                return self._clean_text(earthwork_heading.group(1))
            electrical_primary_heading = re.search(
                r"(6\.(?:2|3)\.\d+\.?\s*(?:主要\s*电气\s*一次\s*设备|升压站\s*电气\s*一次\s*主要设备材料工程量表))",
                text,
            )
            if electrical_primary_heading:
                return self._clean_text(electrical_primary_heading.group(1))
            electrical_secondary_heading = re.search(
                r"((?:表\s*)?(?:6\.4\.4-3|6\.3\.16-1|6\.5\.3|6\.5-1)\s*\.?\s*(?:升压站\s*)?(?:电气\s*二次\s*(?:主要设备表|设备材料清册表?)|主要\s*通信\s*设备表))",
                text,
            )
            if electrical_secondary_heading:
                return self._clean_text(electrical_secondary_heading.group(1))
            if re.match(r"6\.3-1", text) and re.search(r"110\s*kV\s*升压站本期规模", text, flags=re.IGNORECASE):
                return text
            if re.match(r"15\.2\.[1-5]", text) and "概算表" in text:
                return text
            if re.match(r"15\.3\.9\.\d+", text) and ("概算表" in text or "主要技术经济指标表" in text):
                return text
        return ""
