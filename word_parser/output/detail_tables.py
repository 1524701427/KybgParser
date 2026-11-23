"""表格详情压缩、规则摘要与来源定位。"""

from __future__ import annotations

from typing import Any


class DetailTablesMixin:
    """表格详情压缩、规则摘要与来源定位，供 JsonExporter 组合使用。"""

    def _build_compact_tables(self, sections: list[dict[str, Any]], fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        tables: dict[str, dict[str, Any]] = {}
        for section in sections:
            for table in section.get("tables", []) or []:
                key = table.get("key")
                if not key:
                    continue
                data = table.get("data", []) or []
                table_type = self._table_type(table)
                source = self._compact_table_source(table)
                compact = {
                    "key": key,
                    "name": table.get("name"),
                    "section": section.get("name"),
                    "tableType": table_type,
                    "columns": table.get("columns", []),
                    "columnKeys": table.get("columnKeys", []),
                    "rowCount": len(data),
                    "data": data,
                    "sampleRows": data[:1],
                    "valueTraces": self._table_value_traces(table, fields),
                    "source": source,
                    "location": self._source_location(source),
                    "articleLocation": self._article_location_summary(self._source_location(source)),
                    "rule": self._table_rule_summary(table),
                    "extractionTrace": self._compact_extraction_trace(table.get("_trace") or {}),
                }
                if table_type == "combined_table":
                    compact["cellValueTraces"] = self._compact_table_cell_value_traces(table, fields)
                else:
                    compact["dataLocation"] = "完整原表数据见 result.json 的同名 table key；details 仅保留命中规则、来源位置和样例行。"
                tables[key] = compact
        return tables

    def _table_type(self, table: dict[str, Any]) -> str:
        trace = table.get("_trace") or {}
        extraction_type = trace.get("extractionType")
        if extraction_type in {"original_table", "repeatable_original_table", "original_table_group"}:
            return "original_table"
        if extraction_type == "combined_or_project_detail":
            return "combined_table"
        return "original_table" if self._looks_like_document_table(table) else "combined_table"

    def _compact_extraction_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        if not trace:
            return {}
        title_candidates = trace.get("titleCandidates") or []
        compact = {
            "extractionType": trace.get("extractionType"),
            "ruleSource": trace.get("ruleSource"),
            "configuredKey": trace.get("configuredKey"),
            "matchedPattern": trace.get("matchedRule"),
            "matchedRule": trace.get("matchedRule"),
            "matchedTitle": trace.get("matchedTitle"),
            "titleSource": trace.get("titleSource"),
            "tablePosition": self._compact_table_position(trace.get("tablePosition") or {}),
            "merged": trace.get("merged"),
            "continuationCount": len(trace.get("continuations") or []),
            "titleCandidateCount": len(title_candidates),
            "titleCandidatesPreview": title_candidates[:5],
        }
        return {key: value for key, value in compact.items() if value not in (None, [], {}, 0)}

    def _compact_table_position(self, position: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(position, dict):
            return {}
        compact = {
            "tableId": position.get("tableId"),
            "order": position.get("order"),
            "page": position.get("page"),
            "caption": position.get("caption"),
            "sectionPath": position.get("sectionPath"),
            "isMerged": position.get("isMerged"),
            "continuationCount": len(position.get("continuations") or []),
        }
        return {key: value for key, value in compact.items() if value not in (None, [], {}, 0)}

    def _table_rule_summary(self, table: dict[str, Any]) -> dict[str, Any]:
        trace = table.get("_trace") or {}
        if trace:
            extraction_type = trace.get("extractionType")
            normalized_type = "original_table" if extraction_type in {"original_table", "repeatable_original_table", "original_table_group"} else extraction_type
            summary = {
                "extractionType": normalized_type,
                "rawExtractionType": extraction_type if extraction_type != normalized_type else None,
                "ruleSource": trace.get("ruleSource"),
                "configuredKey": trace.get("configuredKey"),
                "matchedPattern": self._display_matched_pattern(trace.get("matchedRule")),
                "matchedRule": trace.get("matchedRule"),
                "matchedTitle": trace.get("matchedTitle"),
                "titleSource": trace.get("titleSource"),
                "excludePatterns": trace.get("excludePatterns"),
                "tablePosition": self._compact_table_position(trace.get("tablePosition") or {}),
                "merged": trace.get("merged"),
                "continuationCount": len(trace.get("continuations") or []),
            }
            return {key: value for key, value in summary.items() if value not in (None, [], {}, 0)}
        if self._looks_like_document_table(table):
            return {
                "extractionType": "original_table",
                "resolver": "original_table_passthrough",
            }
        return {
            "extractionType": "combined_table",
            "resolver": "result_builder",
        }

    def _display_matched_pattern(self, pattern: Any) -> Any:
        if pattern in {"测风塔基本情况表", r"测风塔\s*基本情况表?"}:
            return "测风塔.*基本情况"
        return pattern

    def _compact_table_cell_value_traces(self, table: dict[str, Any], fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        columns = table.get("columns", []) or []
        column_keys = table.get("columnKeys", []) or []
        column_sources = self._generic_table_column_sources(table, {}, fields)
        cell_sources = self._table_cell_sources(table, column_sources)
        rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(table.get("data", []) or []):
            values = []
            for column_index, value in enumerate(row):
                cell = cell_sources[row_index][column_index] if row_index < len(cell_sources) and column_index < len(cell_sources[row_index]) else {}
                source = cell.get("source")
                values.append(
                    {
                        "column": columns[column_index] if column_index < len(columns) else None,
                        "columnKey": column_keys[column_index] if column_index < len(column_keys) else None,
                        "value": value,
                        "rule": self._cell_rule_summary(table, column_index, cell),
                        "location": self._source_location(source),
                    }
                )
            rows.append({"rowIndex": row_index, "values": values})
        return rows

    def _cell_rule_summary(self, table: dict[str, Any], column_index: int, cell: dict[str, Any]) -> dict[str, Any]:
        columns = table.get("columns", []) or []
        column = columns[column_index] if column_index < len(columns) else None
        explicit_process = cell.get("process") or {}
        if explicit_process:
            result = dict(explicit_process)
            return result
        if table.get("key") == "windResourceCombined":
            return {"resolver": "resource_combined_rules", "column": column}
        if self._looks_like_document_table(table):
            return {"resolver": "original_table_passthrough", "column": column}
        return {"resolver": "result_builder", "column": column}

    def _field_rule_summary(self, field_code: str, trace: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
        meta = (source or {}).get("meta") or {}
        if meta.get("ruleSource") or meta.get("matchedPattern") or meta.get("configuredRule"):
            return {
                key: meta.get(key)
                for key in (
                    "ruleSource",
                    "configuredField",
                    "configuredRule",
                    "matchedPattern",
                    "matchedText",
                    "score",
                )
                if meta.get(key) is not None
            }
        if meta.get("rule") or meta.get("patterns"):
            return {key: meta.get(key) for key in ("rule", "patterns", "builder", "matchedRule") if meta.get(key)}
        resolver = meta.get("resolver") or (trace.get("debug") or {}).get("resolver") or (trace.get("process") or {}).get("resolver")
        return {"resolver": resolver or "pipeline_resolver"}

    def _source_location(self, source: dict[str, Any] | None) -> dict[str, Any] | None:
        if not source:
            return None
        meta = source.get("meta") or {}
        return {
            "sourceType": source.get("sourceType") or source.get("kind"),
            "sectionPath": source.get("sectionPath") or source.get("documentSectionPath") or [],
            "blockId": source.get("blockId"),
            "tableId": source.get("tableId"),
            "tableOrder": source.get("tableOrder"),
            "caption": source.get("caption") or meta.get("caption"),
            "sectionPathFallback": source.get("sectionPathFallback"),
            "sourceRow": source.get("sourceRow") if source.get("sourceRow") is not None else meta.get("sourceRow"),
            "sourceColumn": source.get("sourceColumn") if source.get("sourceColumn") is not None else meta.get("sourceColumn"),
        }

    def _table_value_traces(self, table: dict[str, Any], fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        columns = table.get("columns", []) or []
        column_keys = table.get("columnKeys", []) or []
        first_row = (table.get("data", []) or [[]])[0] if table.get("data") else []
        traces: list[dict[str, Any]] = []
        for index, column in enumerate(columns):
            column_key = column_keys[index] if index < len(column_keys) else None
            value = first_row[index] if index < len(first_row) else None
            field_code = self.COLUMN_KEY_FIELD_ALIASES.get(column_key or "") or column_key
            field_trace = fields.get(field_code or "")
            traces.append(
                {
                    "column": column,
                    "columnKey": column_key,
                    "value": value,
                    "fieldCode": field_trace.get("fieldCode") if field_trace else None,
                    "source": field_trace.get("source") if field_trace else None,
                    "pipeline": field_trace.get("pipeline") if field_trace else None,
                    "decision": field_trace.get("decision") if field_trace else None,
                }
            )
        return traces

    def _compact_table_source(self, table: dict[str, Any]) -> dict[str, Any]:
        explicit = table.get("_cellSources") or []
        source_table = table.get("_sourceTable") or {}
        first_source = None
        for row in explicit:
            if not isinstance(row, list):
                continue
            first_source = next(
                (
                    cell.get("source")
                    for cell in row
                    if isinstance(cell, dict)
                    and isinstance(cell.get("source"), dict)
                    and cell["source"].get("sourceColumn") not in {None, 0}
                ),
                None,
            ) or next((cell.get("source") for cell in row if isinstance(cell, dict) and isinstance(cell.get("source"), dict)), None)
            if first_source:
                break
        is_document_table = self._looks_like_document_table(table)
        source = {
            "kind": "document_table" if is_document_table else (first_source.get("kind") if first_source else "result_builder_table"),
            "tableId": source_table.get("tableId") or (first_source.get("tableId") if first_source else None),
            "tableOrder": source_table.get("order"),
            "page": source_table.get("page") if is_document_table else (first_source.get("page") if first_source else source_table.get("page")),
            "documentSectionPath": source_table.get("sectionPath"),
            "sourceRow": None if is_document_table else (first_source.get("sourceRow") if first_source else None),
            "sourceColumn": None if is_document_table else (first_source.get("sourceColumn") if first_source else None),
            "sourceText": None if is_document_table else (first_source.get("sourceText") if first_source else None),
            "caption": source_table.get("caption") or (first_source.get("caption") if first_source else None) or table.get("name"),
            "isMerged": bool(source_table.get("isMerged")),
            "continuations": source_table.get("continuations"),
            "headerSource": source_table.get("headerSource"),
            "description": "查看 result.json 获取完整表格数据；details 只保留表级来源摘要。" if is_document_table else (first_source.get("description") if first_source else "查看 result.json 获取完整表格数据；details 只保留表级来源摘要。"),
        }
        rule = self._table_rule_summary(table)
        if rule:
            source["rule"] = rule
        return source
