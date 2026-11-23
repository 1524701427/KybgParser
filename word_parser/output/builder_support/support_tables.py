"""原表透传、表格合并和确定性字段写入辅助方法。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable
from word_parser.document.ast.evidence import FieldEvidence, ParsedField


class DocumentTableSupportMixin:

    def _cell_at_alias(self, header: list[str], row: list[str], aliases: list[str]):
        """按既有表头别名定位单元格，并使用原有数值归一化语义。

        历史 ResultBuilder 领域规则已调用该辅助方法，但重构拆分类时
        方法定义遗失。不存在匹配列或列越界时返回 None，而非抛出异常。
        """
        index = self._find_header_index(header, aliases)
        if index is None or index >= len(row):
            return None
        value = row[index]
        if value is None:
            return None
        return self._normalize_table_cell(str(value))


    """原表透传、表格合并和确定性字段写入辅助方法，由 DocumentSupportMixin 统一组合。"""

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

        参数：
            key: 输出表 key。
            name: 调用方已经确认的表名或兜底表名。
            table: AST 中的源表。
            description: 单元格来源说明。
            resolver: 来源 resolver 名称。
            header_columns: 外部继承的表头；用于跨页续表或拆分表。
            header_source_table: 表头来源表。
            data_start_index: 数据起始行。
            prefer_provided_name: 为 True 时优先使用规则实际命中的表名，避免结构层旧 caption 覆盖正确标题。

        返回：
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

