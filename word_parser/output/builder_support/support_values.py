"""基础数值、单位、表格单元格和证据构造辅助方法。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable


class DocumentValueSupportMixin:
    """基础数值、单位、表格单元格和证据构造辅助方法，由 DocumentSupportMixin 统一组合。"""

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
