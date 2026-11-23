"""表格字段来源、列来源与通用表格追踪。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.evidence import ParsedField


class DetailSourcesMixin:
    """表格字段来源、列来源与通用表格追踪，供 JsonExporter 组合使用。"""

    def _build_detail_fields(
        self,
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
        field_traces: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = dict(field_traces or {})
        for code, field in validated.items():
            display = final_fields.get(code, {})
            result[code] = self._build_field_trace(code, field, display)
        for code, display in final_fields.items():
            if code not in result:
                result[code] = self._build_final_field_trace(
                    code,
                    display,
                    display,
                    source={"kind": "missing", "fieldCode": code, "description": "schema required field not extracted"},
                    status="MISSING",
                )
        return result

    def _build_detail_sections(
        self,
        sections: list[dict[str, Any]],
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
        field_traces: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        code_by_name = self._field_codes_by_name(validated)
        for code, field in final_fields.items():
            name = field.get("name")
            if name:
                code_by_name.setdefault(name, code)
        detailed_sections: list[dict[str, Any]] = []
        for section in sections:
            detailed_section = {
                "name": section.get("name"),
                "fields": [],
                "tables": [],
            }
            for item in section.get("fields", []):
                field_name = item.get("name") or item.get("名字")
                field_code = item.get("fieldCode") or code_by_name.get(field_name)
                source_field = validated.get(field_code) if field_code else None
                final_field = final_fields.get(field_code, {}) if field_code else {}
                detailed_section["fields"].append(
                    self._build_section_field_trace(
                        item,
                        field_code,
                        source_field,
                        final_field,
                        (field_traces or {}).get(field_code or ""),
                    )
                )
            for table in section.get("tables", []):
                detailed_section["tables"].append(self._build_detail_table(table, validated, final_fields))
            detailed_sections.append(detailed_section)
        return detailed_sections

    def _field_codes_by_name(self, fields: dict[str, ParsedField]) -> dict[str, str]:
        return {field.field_name: code for code, field in fields.items() if field.field_name}

    def _build_detail_table(
        self,
        table: dict[str, Any],
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        detailed = {key: value for key, value in table.items() if not str(key).startswith("_")}
        key = table.get("key")
        source_fields = self._table_source_fields(key, table, validated, final_fields)
        if source_fields:
            detailed["sourceFields"] = source_fields
            detailed["source"] = {
                "kind": "field_derived",
                "tableKey": key,
                "fieldCodes": [item["fieldCode"] for item in source_fields],
            }
            detailed["columnSources"] = self._column_sources_from_source_fields(table, source_fields)
        elif key == "singleTurbineAnnualEnergy":
            detailed["source"] = {
                "kind": "document_table",
                "tableKey": key,
                "description": table.get("name"),
            }
            detailed["columnSources"] = self._document_table_column_sources(table)
        else:
            detailed["source"] = self._generic_table_source(table)
            detailed["columnSources"] = self._generic_table_column_sources(table, validated, final_fields)
        detailed["cellSources"] = self._table_cell_sources(table, detailed.get("columnSources", []))
        return detailed

    def _table_source_fields(
        self,
        table_key: str | None,
        table: dict[str, Any],
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        mapping = {
            "generationSummary": [
                {
                    "column": "不考虑尾流效应的折减系数",
                    "fieldCode": "nonWakeLossFactor",
                    "source": "发电量计算结果表。",
                },
            ],
        }
        items = mapping.get(table_key or "", [])
        if not items:
            return []
        data = table.get("data", []) or []
        row = data[0] if data else []
        sources: list[dict[str, Any]] = []
        for index, spec in enumerate(items):
            column_name = spec["column"]
            field_code = spec["fieldCode"]
            field = validated.get(field_code)
            table_value = row[index] if index < len(row) else None
            display = {
                "name": column_name,
                "value": table_value if table_value is not None else final_fields.get(field_code, {}).get("value"),
                "unit": final_fields.get(field_code, {}).get("unit"),
            }
            if field is not None:
                source_trace = self._build_field_trace(field_code, field, final_fields.get(field_code, {}), display)
            else:
                source_trace = self._build_final_field_trace(
                    field_code,
                    final_fields.get(field_code, {}),
                    display,
                    source={
                        "sourceType": "derived",
                        "text": spec["source"],
                        "tableKey": table_key,
                        "sectionPath": ["发电量章节"],
                    },
                    process={"resolver": "result_builder"},
                    status="PASS" if display["value"] is not None else "MISSING",
                )
            source_trace["sourceDescription"] = spec["source"]
            source_trace["column"] = column_name
            source_trace["tableValue"] = table_value
            sources.append(source_trace)
        return sources

    def _document_table_column_sources(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        columns = table.get("columns", []) or []
        if not columns:
            return [
                {
                    "column": None,
                    "columnIndex": None,
                    "source": {
                        "kind": "missing_document_table",
                        "tableKey": table.get("key"),
                        "description": "未在原文中命中整表，保留表级缺失来源说明。",
                    },
                }
            ]
        return [
            {
                "column": column,
                "columnIndex": index,
                "source": {
                    "kind": "document_table_column",
                    "tableKey": table.get("key"),
                    "description": "整表从原文表格抽取，表头作为字段名，数据行保持原表顺序。",
                },
            }
            for index, column in enumerate(columns)
        ]

    def _column_sources_from_source_fields(self, table: dict[str, Any], source_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_column = {item.get("column"): item for item in source_fields}
        column_sources: list[dict[str, Any]] = []
        for index, column in enumerate(table.get("columns", [])):
            trace = by_column.get(column)
            if trace is None:
                column_sources.append(self._generic_column_source(table, column, index))
                continue
            column_sources.append(
                {
                    "column": column,
                    "columnIndex": index,
                    "fieldCode": trace.get("fieldCode"),
                    "tableValue": trace.get("tableValue"),
                    "source": self._primary_evidence(trace),
                    "process": trace.get("process", {}),
                    "sourceDescription": trace.get("sourceDescription"),
                }
            )
        return column_sources

    def _generic_table_source(self, table: dict[str, Any]) -> dict[str, Any]:
        key = table.get("key")
        if self._looks_like_document_table(table):
            return {
                "kind": "document_table",
                "tableKey": key,
                "description": "由原文表格抽取或按需求表头重组，列级来源见 columnSources。",
            }
        return {
            "kind": "result_builder_table",
            "tableKey": key,
            "description": "由导出层按需求模块组装，值来自已抽取字段、确定性规则或原文表格重组，列级来源见 columnSources。",
        }

    def _looks_like_document_table(self, table: dict[str, Any]) -> bool:
        key = table.get("key")
        document_table_keys = {
            "earthworkBalance",
            "permanentLandArea",
            "longTermLeaseArea",
            "temporaryLandArea",
            "temporaryCompensatedLandArea",
            "singleTurbineAnnualEnergy",
            "investmentEstimate",
            "majorEquipmentPrice",
            "financialIndicatorSummary",
        }
        return key in document_table_keys or bool(table.get("columnKeys"))

    def _generic_table_column_sources(
        self,
        table: dict[str, Any],
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        columns = table.get("columns", []) or []
        column_keys = table.get("columnKeys", []) or []
        if not columns:
            return [
                {
                    "column": None,
                    "columnIndex": None,
                    "source": {
                        "kind": "missing_table_columns",
                        "tableKey": table.get("key"),
                        "description": "表格未抽到列，保留表级来源说明。",
                    },
                    "process": {"resolver": "result_builder", "calculation": "未命中原文表格列。"},
                }
            ]
        return [
            self._generic_column_source(
                table,
                column,
                index,
                column_key=column_keys[index] if index < len(column_keys) else None,
                matched_field_code=self._match_table_column_to_field(
                    column,
                    self._column_values(table, index),
                    validated,
                    final_fields,
                    column_key=column_keys[index] if index < len(column_keys) else None,
                ),
                validated=validated,
                final_fields=final_fields,
            )
            for index, column in enumerate(columns)
        ]

    def _generic_column_source(
        self,
        table: dict[str, Any],
        column: Any,
        index: int,
        column_key: str | None = None,
        matched_field_code: str | None = None,
        validated: dict[str, ParsedField] | None = None,
        final_fields: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        values = self._column_values(table, index)
        result: dict[str, Any] = {
            "column": column,
            "columnIndex": index,
            "columnKey": column_key,
            "valueCount": len(values),
            "tableValueSamples": values[:5],
        }
        if matched_field_code and validated is not None and final_fields is not None:
            field = validated.get(matched_field_code)
            final_field = final_fields.get(matched_field_code, {})
            if field is not None:
                trace = self._build_field_trace(matched_field_code, field, final_field, {"name": column})
            else:
                trace = self._build_final_field_trace(matched_field_code, final_field, {"name": column})
            result.update(
                {
                    "fieldCode": matched_field_code,
                    "source": self._primary_evidence(trace),
                    "process": trace.get("process", {}),
                }
            )
            return result
        result["source"] = {
            "kind": "document_table_column" if self._looks_like_document_table(table) else "result_builder_column",
            "tableKey": table.get("key"),
            "description": "该列来自原文表格表头/数据行或导出阶段按需求表头组装；未能唯一匹配到单个字段编码。",
        }
        result["process"] = {
            "resolver": "result_builder",
        }
        return result

    def _column_values(self, table: dict[str, Any], index: int) -> list[Any]:
        values: list[Any] = []
        for row in table.get("data", []) or []:
            if index < len(row):
                values.append(row[index])
        return values

    def _table_cell_sources(self, table: dict[str, Any], column_sources: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """构建与表格数据对齐的单元格级来源信息。"""
        column_keys = table.get("columnKeys", []) or []
        columns = table.get("columns", []) or []
        explicit_sources = table.get("_cellSources", []) or []
        cell_rows: list[list[dict[str, Any]]] = []
        for row_index, row in enumerate(table.get("data", []) or []):
            cell_row: list[dict[str, Any]] = []
            for column_index, value in enumerate(row):
                column_source = column_sources[column_index] if column_index < len(column_sources) else {}
                explicit = self._explicit_cell_source(explicit_sources, row_index, column_index)
                explicit_source = explicit.get("source") if explicit else None
                explicit_process = explicit.get("process") if explicit else None
                cell_row.append(
                    {
                        "rowIndex": row_index,
                        "columnIndex": column_index,
                        "column": columns[column_index] if column_index < len(columns) else None,
                        "columnKey": column_keys[column_index] if column_index < len(column_keys) else None,
                        "value": value,
                        "fieldCode": explicit.get("fieldCode") if explicit and explicit.get("fieldCode") else column_source.get("fieldCode"),
                        "source": explicit_source or column_source.get("source"),
                        "process": explicit_process or column_source.get("process", {}),
                        "sourceDescription": explicit.get("sourceDescription") if explicit and explicit.get("sourceDescription") else column_source.get("sourceDescription"),
                    }
                )
            cell_rows.append(cell_row)
        return cell_rows

    def _explicit_cell_source(self, source_rows: Any, row_index: int, column_index: int) -> dict[str, Any] | None:
        if not isinstance(source_rows, list) or row_index >= len(source_rows):
            return None
        row = source_rows[row_index]
        if not isinstance(row, list) or column_index >= len(row):
            return None
        source = row[column_index]
        return source if isinstance(source, dict) else None

    def _match_table_column_to_field(
        self,
        column: Any,
        values: list[Any],
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
        column_key: str | None = None,
    ) -> str | None:
        alias_code = self.COLUMN_KEY_FIELD_ALIASES.get(column_key or "")
        if alias_code and (alias_code in validated or alias_code in final_fields):
            return alias_code
        if column_key and column_key in validated:
            return column_key
        if column_key and column_key in final_fields:
            return column_key
        column_text = str(column)
        candidates: list[str] = []
        for code, final_field in final_fields.items():
            name = str(final_field.get("name") or "")
            if name and self._same_table_column_label(name, column_text):
                candidates.append(code)
                continue
            field = validated.get(code)
            if field is not None and self._field_value_in_column(field, values):
                candidates.append(code)
        unique = list(dict.fromkeys(candidates))
        return unique[0] if len(unique) == 1 else None

    def _same_table_column_label(self, field_name: str, column_text: str) -> bool:
        field_label = self._normalize_column_label(field_name)
        column_label = self._normalize_column_label(column_text)
        return bool(field_label and column_label and field_label == column_label)

    def _normalize_column_label(self, value: Any) -> str:
        text = str(value)
        text = re.sub(r"[\[【(（].*?[\]】)）]", "", text)
        text = re.sub(r"(?:m/s|W/m²|W/m2|万kW·h|万kWh|kWh|MWh|MW|kW|kV|kVA|m2|㎡|%|h)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "", text)
        return text.strip().lower()

    def _field_value_in_column(self, field: ParsedField, values: list[Any]) -> bool:
        if field.value is None:
            return False
        expected = {self._normalize_compare_value(field.value)}
        if field.unit:
            expected.add(self._normalize_compare_value(f"{field.value}{field.unit}"))
        return any(self._normalize_compare_value(value) in expected for value in values if value is not None)

    def _normalize_compare_value(self, value: Any) -> str:
        return str(value).replace(",", "").replace(" ", "").strip().lower()
