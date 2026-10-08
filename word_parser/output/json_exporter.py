"""JSON exporter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from parser_engine.document.ast.evidence import FieldEvidence, ParsedField
from word_parser.application.context import ParseContext
from word_parser.output.result_builder import ResultBuilder


class JsonExporter:
    """Export detail JSON and a minimal result JSON."""

    COLUMN_KEY_FIELD_ALIASES = {
        "hubHeightAvgWindSpeed": "hubHeightAnnualAverageWindSpeed",
        "turbineCapacityKw": "turbineCapacity",
        "ratedVoltage": "collectorVoltageLevel",
        "totalLength": "collectorLineLength",
    }

    def __init__(self, result_builder: ResultBuilder | None = None, output_dir: str | Path = "data/predictions"):
        self.result_builder = result_builder or ResultBuilder()
        self.output_dir = Path(output_dir)

    def export(self, ctx: ParseContext) -> dict:
        built_result = self.result_builder.build(ctx.ast, ctx.validated, file_path=ctx.file_path)
        ctx.result = {
            "filePath": ctx.file_path,
            "sections": self._strip_private_keys(built_result.get("sections", [])),
        }
        detail_json = self._build_detail_json(ctx, built_result)
        result_json = self._build_result_json(ctx)
        self._write_output_files(ctx, detail_json, result_json)
        return {
            "filePath": ctx.file_path,
            "result": ctx.result,
            "fields": detail_json["fieldIndex"],
            "debug": detail_json.get("debug", {}),
            "outputFiles": {
                "detail": str(self._output_path(ctx, "details")),
                "result": str(self._output_path(ctx, "result")),
            },
        }

    def _build_detail_json(self, ctx: ParseContext, built_result: dict[str, Any]) -> dict:
        final_fields = built_result.get("fields", {}) or {}
        field_traces = built_result.get("fieldTraces", {}) or {}
        trace_fields = built_result.get("parsedFields", ctx.validated) or ctx.validated
        compact_fields = self._build_compact_field_traces(ctx, trace_fields, final_fields, field_traces)
        sections = built_result.get("sections", [])
        self._apply_detail_sections(compact_fields, sections)
        compact_tables = self._build_compact_tables(sections, compact_fields)
        return {
            "filePath": ctx.file_path,
            "summary": {
                "blockCount": len(ctx.ast.blocks) if ctx.ast else 0,
                "tableCount": len(ctx.ast.tables) if ctx.ast else 0,
                "resolvedFieldCount": len(trace_fields),
                "finalFieldCount": len(final_fields),
            },
            "sections": self._build_ordered_detail_sections(sections, compact_fields, compact_tables),
            "fieldIndex": compact_fields,
            "tableIndex": compact_tables,
        }

    def _apply_detail_sections(self, fields: dict[str, dict[str, Any]], sections: list[dict[str, Any]]) -> None:
        for section in sections:
            section_name = section.get("name")
            for field in section.get("fields", []) or []:
                code = field.get("fieldCode")
                if not code or code not in fields:
                    continue
                fields[code]["section"] = section_name
                location = fields[code].setdefault("location", {}) or {}
                if not location.get("sectionPath") and section_name:
                    location["sectionPath"] = [section_name]
                    location["sectionPathFallback"] = True
                source = fields[code].get("source") or {}
                if source is not None and not source.get("sectionPath") and section_name:
                    source["sectionPath"] = [section_name]
                    source["sectionPathFallback"] = True

    def _build_compact_field_traces(
        self,
        ctx: ParseContext,
        validated: dict[str, ParsedField],
        final_fields: dict[str, dict[str, Any]],
        field_traces: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        codes = list(dict.fromkeys([*final_fields.keys(), *validated.keys(), *(field_traces or {}).keys()]))
        return {
            code: self._build_compact_field_trace(
                ctx,
                code,
                validated.get(code),
                final_fields.get(code, {}),
                (field_traces or {}).get(code),
            )
            for code in codes
        }

    def _build_compact_field_trace(
        self,
        ctx: ParseContext,
        field_code: str,
        field: ParsedField | None,
        final_field: dict[str, Any],
        final_trace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace = final_trace or (self._build_field_trace(field_code, field, final_field) if field else {})
        name = final_field.get("name") or trace.get("name") or (field.field_name if field else None)
        value = final_field.get("value", trace.get("value") if trace else (field.value if field else None))
        unit = final_field.get("unit", trace.get("unit") if trace else (field.unit if field else None))
        evidence = trace.get("evidence", []) if trace else []
        source = self._compact_source(evidence)
        sources = self._compact_sources(evidence)
        result = {
            "fieldCode": field_code,
            "name": name,
            "value": value,
            "unit": unit,
            "status": final_field.get("status") or trace.get("status") or (field.status if field else "MISSING"),
            "source": source,
            "rule": self._field_rule_summary(field_code, trace, source),
            "articleLocation": self._article_location_summary(self._source_location(source)),
        }
        if len(sources) > 1:
            result["sources"] = sources
        return result

    def _build_pipeline_debug(self, ctx: ParseContext) -> dict[str, Any]:
        return {
            "counts": {
                "candidates": len(ctx.candidates),
                "matchesAfterPruning": len(ctx.matches),
                "extractions": len(ctx.extractions),
                "normalizedAfterPruning": len(ctx.normalized),
                "validatedFields": len(ctx.validated),
            },
            "components": {
                "retrieval": {"candidateCount": len(ctx.candidates)},
                "bge": {
                    "used": any(match.method == "bge" for match in ctx.matches),
                    "matchCount": sum(1 for match in ctx.matches if match.method == "bge"),
                },
                "uie": {
                    "produced": any(extraction.method == "uie" for extraction in ctx.extractions),
                    "extractionCount": sum(1 for extraction in ctx.extractions if extraction.method == "uie"),
                },
                "reranker": {
                    "scored": sum(1 for extraction in ctx.normalized if "reranker_score" in extraction.debug),
                },
                "nli": {
                    "scored": sum(1 for extraction in ctx.normalized if "nli_score" in extraction.debug),
                },
            },
        }

    def _field_candidates(self, ctx: ParseContext, field_code: str) -> list[Any]:
        return [candidate for candidate in ctx.candidates if candidate.field_code == field_code]

    def _field_matches(self, ctx: ParseContext, field_code: str) -> list[Any]:
        return [match for match in ctx.matches if match.candidate.field_code == field_code]

    def _field_extractions(self, ctx: ParseContext, field_code: str) -> list[Any]:
        return [extraction for extraction in ctx.extractions if extraction.field_code == field_code]

    def _field_normalized(self, ctx: ParseContext, field_code: str) -> list[Any]:
        return [extraction for extraction in ctx.normalized if extraction.field_code == field_code]

    def _field_pipeline_summary(self, candidates: list[Any], matches: list[Any], extractions: list[Any], normalized: list[Any]) -> dict[str, Any]:
        return {
            "retrieval": {"candidateCount": len(candidates)},
            "matching": {
                "matchCount": len(matches),
                "methods": self._counts(match.method for match in matches),
                "bgeUsed": any(match.method == "bge" for match in matches),
            },
            "extraction": {
                "extractionCount": len(extractions),
                "methods": self._counts(extraction.method for extraction in extractions),
                "uieProduced": any(extraction.method == "uie" for extraction in extractions),
            },
            "verification": {
                "normalizedCount": len(normalized),
                "rerankerScored": sum(1 for extraction in normalized if "reranker_score" in extraction.debug),
                "nliScored": sum(1 for extraction in normalized if "nli_score" in extraction.debug),
            },
        }

    def _field_decision_summary(self, field_code: str, process: dict[str, Any], debug: dict[str, Any], messages: list[Any]) -> dict[str, Any]:
        merged = dict(debug)
        merged.update(process)
        return {
            "resolver": merged.get("resolver"),
            "resolverScore": merged.get("resolver_score"),
            "baseScore": merged.get("base_score"),
            "semanticScore": merged.get("semantic_score"),
            "rerankerScore": merged.get("reranker_score"),
            "nliLabel": merged.get("nli_label"),
            "nliScore": merged.get("nli_score"),
            "calculation": merged.get("calculation") or self._default_field_calculation(field_code),
            "messages": [*messages, *merged.get("messages", [])] if isinstance(merged.get("messages", []), list) else messages,
        }

    def _default_field_calculation(self, field_code: str) -> str | None:
        return None

    def _compact_source(self, evidence: list[Any]) -> dict[str, Any] | None:
        if not evidence:
            return None
        source = evidence[0]
        if self._is_internal_combined_evidence(source):
            return None
        return self._compact_evidence_source(source)

    def _compact_sources(self, evidence: list[Any]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for source in evidence:
            if self._is_internal_combined_evidence(source):
                continue
            compact = self._compact_evidence_source(source)
            identity = (
                compact.get("sourceType"),
                compact.get("blockId"),
                compact.get("tableId"),
                compact.get("page"),
                compact.get("matchMethod"),
                compact.get("text"),
            )
            if identity in seen:
                continue
            seen.add(identity)
            sources.append(compact)
        return sources

    def _compact_evidence_source(self, source: Any) -> dict[str, Any]:
        return {
            "sourceType": source.get("sourceType", source.get("source_type")),
            "text": self._short_text(source.get("text"), limit=260),
            "score": source.get("score"),
            "matchMethod": source.get("matchMethod", source.get("match_method")),
            "blockId": source.get("blockId", source.get("block_id")),
            "tableId": source.get("tableId", source.get("table_id")),
            "page": source.get("page"),
            "sectionPath": source.get("sectionPath", source.get("section_path", [])),
            "meta": source.get("meta", {}),
        }

    def _is_internal_combined_evidence(self, source: Any) -> bool:
        if not isinstance(source, dict):
            return False
        meta = source.get("meta") or {}
        return (
            source.get("sourceType", source.get("source_type")) == "combined_field"
            or meta.get("resolver") == "combined_field_mapping"
        )

    def _compact_matches(self, matches: list[Any], limit: int = 3) -> list[dict[str, Any]]:
        sorted_matches = sorted(matches, key=lambda item: item.score, reverse=True)[:limit]
        return [
            {
                "method": match.method,
                "score": round(float(match.score), 6),
                "sourceType": match.candidate.source_type,
                "blockId": match.candidate.block_id,
                "tableId": match.candidate.table_id,
                "sectionPath": match.candidate.section_path,
                "text": self._short_text(match.candidate.text),
            }
            for match in sorted_matches
        ]

    def _compact_extractions(self, extractions: list[Any], limit: int = 3) -> list[dict[str, Any]]:
        sorted_extractions = sorted(extractions, key=lambda item: item.score, reverse=True)[:limit]
        return [
            {
                "method": extraction.method,
                "value": extraction.value,
                "unit": extraction.unit,
                "score": round(float(extraction.score), 6),
                "sourceType": extraction.evidence.source_type,
                "matchMethod": extraction.evidence.match_method,
                "text": self._short_text(extraction.evidence.text),
                "debug": self._compact_debug(extraction.debug),
            }
            for extraction in sorted_extractions
        ]

    def _compact_debug(self, debug: dict[str, Any]) -> dict[str, Any]:
        keep = (
            "semantic_score",
            "semantic_alias_hit",
            "semantic_value_near_alias",
            "semantic_section_score",
            "semantic_penalty",
            "reranker_score",
            "nli_label",
            "nli_score",
            "candidate_normalized",
            "semantic_candidates_rank",
            "semantic_candidates_top_k",
            "reranker_candidates_rank",
            "reranker_candidates_top_k",
            "nli_candidates_rank",
            "nli_candidates_top_k",
            "schema_name",
            "uie_probability",
        )
        return {key: debug[key] for key in keep if key in debug}

    def _counts(self, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    def _short_text(self, text: Any, limit: int = 180) -> Any:
        if not isinstance(text, str):
            return text
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned if len(cleaned) <= limit else f"{cleaned[:limit]}..."

    def _build_compact_sections(self, sections: list[dict[str, Any]], fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        compact_sections: list[dict[str, Any]] = []
        for section in sections:
            field_codes = []
            for item in section.get("fields", []) or []:
                code = item.get("fieldCode")
                name = item.get("name") or item.get("名字")
                if not code:
                    code = next((field_code for field_code, trace in fields.items() if trace.get("name") == name), None)
                if code:
                    field_codes.append(code)
            compact_sections.append(
                {
                    "name": section.get("name"),
                    "fieldCodes": field_codes,
                    "tableKeys": [table.get("key") for table in section.get("tables", []) or []],
                }
            )
        return compact_sections

    def _build_ordered_detail_sections(
        self,
        sections: list[dict[str, Any]],
        fields: dict[str, dict[str, Any]],
        tables: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ordered_sections: list[dict[str, Any]] = []
        for section in sections:
            section_fields = []
            for item in section.get("fields", []) or []:
                code = item.get("fieldCode") or self._field_code_for_display(item, fields)
                if code and code in fields:
                    section_fields.append(self._section_field_detail(fields[code]))
            section_tables = []
            for table in section.get("tables", []) or []:
                key = table.get("key")
                if key and key in tables:
                    section_tables.append(self._section_table_detail(tables[key]))
            ordered_sections.append(
                {
                    "name": section.get("name"),
                    "fields": section_fields,
                    "tables": section_tables,
                }
            )
        return ordered_sections

    def _section_field_detail(self, field: dict[str, Any]) -> dict[str, Any]:
        source = field.get("source") or {}
        source_text = self._short_text(source.get("text"), limit=220) if source else None
        article_location = field.get("articleLocation") or self._article_location_summary(field.get("location"))
        return {
            "fieldCode": field.get("fieldCode"),
            "name": field.get("name"),
            "value": field.get("value"),
            "unit": field.get("unit"),
            "status": field.get("status"),
            "rule": field.get("rule"),
            "articleLocation": article_location,
            "sourceText": source_text,
        }

    def _legacy_section_field_detail(self, field: dict[str, Any]) -> dict[str, Any]:
        return {
            "fieldCode": field.get("fieldCode"),
            "name": field.get("name"),
            "value": field.get("value"),
            "unit": field.get("unit"),
            "status": field.get("status"),
            "rule": field.get("rule"),
            "location": field.get("location"),
            "decision": field.get("decision"),
        }

    def _section_table_detail(self, table: dict[str, Any]) -> dict[str, Any]:
        if table.get("tableType") == "original_table":
            source = self._original_table_source_summary(table.get("source") or {})
            location = table.get("location") or self._source_location(source)
            return {
                "key": table.get("key"),
                "name": table.get("name"),
                "tableType": table.get("tableType"),
                "source": source,
                "articleLocation": self._article_location_summary(location),
                "section": table.get("section") or self._first_section(location),
            }
        detail = {
            "key": table.get("key"),
            "name": table.get("name"),
            "tableType": table.get("tableType"),
            "rowCount": table.get("rowCount"),
            "columns": table.get("columns"),
            "data": table.get("data"),
            "sampleRows": table.get("sampleRows"),
            "rule": table.get("rule"),
            "location": table.get("location"),
        }
        if table.get("tableType") == "combined_table":
            detail["valueTraces"] = table.get("cellValueTraces")
        else:
            detail["columnRules"] = table.get("valueTraces")
        return detail

    def _article_location_summary(self, location: dict[str, Any] | None) -> dict[str, Any] | None:
        if not location:
            return None
        compact = {
            "sectionPath": location.get("sectionPath") or [],
            "page": location.get("page"),
            "blockId": location.get("blockId"),
            "tableId": location.get("tableId"),
            "caption": location.get("caption"),
            "sourceRow": location.get("sourceRow"),
            "sourceColumn": location.get("sourceColumn"),
            "sectionPathFallback": location.get("sectionPathFallback"),
        }
        return {key: value for key, value in compact.items() if value not in (None, [], {})}

    def _original_table_source_summary(self, source: dict[str, Any]) -> dict[str, Any]:
        compact = {
            "tableId": source.get("tableId"),
            "tableOrder": source.get("tableOrder"),
            "page": source.get("page"),
            "sectionPath": source.get("documentSectionPath") or source.get("sectionPath") or [],
            "caption": source.get("caption"),
        }
        return {key: value for key, value in compact.items() if value not in (None, [], {})}

    def _first_section(self, location: dict[str, Any] | None) -> str | None:
        if not location:
            return None
        section_path = location.get("sectionPath") or []
        if isinstance(section_path, list) and section_path:
            return str(section_path[0])
        if isinstance(section_path, str) and section_path:
            return section_path
        return None

    def _field_code_for_display(self, item: dict[str, Any], fields: dict[str, dict[str, Any]]) -> str | None:
        name = item.get("name") or item.get("名字")
        value = item.get("value", item.get("结果"))
        for code, trace in fields.items():
            if trace.get("name") == name and (value is None or trace.get("value") == value):
                return code
        return next((code for code, trace in fields.items() if trace.get("name") == name), None)

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
        """Build cell-level provenance aligned with table data."""
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

    def _build_section_field_trace(
        self,
        display_field: dict[str, Any],
        field_code: str | None,
        source_field: ParsedField | None,
        final_field: dict[str, Any],
        final_trace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if source_field is None:
            if final_trace is not None:
                trace = dict(final_trace)
                trace["name"] = display_field.get("name", display_field.get("名字", trace.get("name")))
                trace["value"] = display_field.get("value", display_field.get("结果", trace.get("value")))
                trace["result"] = trace["value"]
                trace["unit"] = display_field.get("unit", display_field.get("单位", trace.get("unit")))
                return trace
            if final_field:
                return self._build_final_field_trace(field_code, final_field, display_field)
            return {
                "fieldCode": field_code,
                "name": display_field.get("名字"),
                "value": display_field.get("结果"),
                "unit": display_field.get("单位"),
                "evidence": [],
                "process": {},
                "messages": [],
                "debug": {},
            }
        return self._build_field_trace(field_code or source_field.field_code, source_field, final_field, display_field)

    def _build_final_field_trace(
        self,
        field_code: str | None,
        final_field: dict[str, Any],
        display_field: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        process: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        display_field = display_field or {}
        value = display_field.get("value", display_field.get("结果", final_field.get("value")))
        unit = display_field.get("unit", display_field.get("单位", final_field.get("unit")))
        return {
            "fieldCode": field_code,
            "name": display_field.get("name", display_field.get("名字", final_field.get("name"))),
            "value": value,
            "result": value,
            "unit": unit,
            "status": status,
            "confidence": None,
            "evidence": [source] if source else [],
            "process": process or {},
            "messages": [],
            "debug": {},
        }

    def _build_field_trace(
        self,
        field_code: str,
        field: ParsedField,
        final_field: dict[str, Any] | None = None,
        display_field: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        display_field = display_field or {}
        value = display_field.get("value", display_field.get("结果", field.value))
        unit = display_field.get("unit", display_field.get("单位", field.unit))
        evidence = [self._summarize_evidence(item) for item in field.evidence]
        return {
            "fieldCode": field_code,
            "name": display_field.get("name", display_field.get("名字", field.field_name)),
            "value": value,
            "result": value,
            "unit": unit,
            "status": field.status,
            "confidence": field.confidence,
            "evidence": evidence,
            "process": self._summarize_process(field),
            "messages": list(field.messages),
            "debug": dict(field.debug),
        }

    def _primary_evidence(self, trace: dict[str, Any]) -> dict[str, Any] | None:
        evidence = trace.get("evidence") or []
        return evidence[0] if evidence else None

    def _summarize_evidence(self, evidence: FieldEvidence) -> dict[str, Any]:
        return {
            "fieldCode": getattr(evidence, "field_code", None),
            "sourceType": evidence.source_type,
            "text": evidence.text,
            "score": evidence.score,
            "blockId": evidence.block_id,
            "tableId": evidence.table_id,
            "page": evidence.page,
            "sectionPath": evidence.section_path,
            "matchMethod": evidence.match_method,
            "meta": evidence.meta,
        }

    def _summarize_process(self, field: ParsedField) -> dict[str, Any]:
        debug = field.debug or {}
        process: dict[str, Any] = {}
        for key in (
            "resolver",
            "candidate_count",
            "resolver_score",
            "base_score",
            "aggregate_part_count",
            "semantic_score",
            "reranker_score",
            "nli_label",
            "nli_score",
            "extractor",
        ):
            if key in debug:
                process[key] = debug[key]
        if field.messages:
            process["messages"] = list(field.messages)
        return process

    def _build_result_json(self, ctx: ParseContext) -> dict:
        return {
            "filePath": ctx.result.get("filePath", ctx.file_path),
            "sections": self._strip_private_keys(ctx.result.get("sections", [])),
        }

    def _strip_private_keys(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._strip_private_keys(item) for key, item in value.items() if not str(key).startswith("_")}
        if isinstance(value, list):
            return [self._strip_private_keys(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return self._strip_private_keys(item())
            except (TypeError, ValueError):
                pass
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                return self._strip_private_keys(tolist())
            except (TypeError, ValueError):
                pass
        return value

    def _write_output_files(self, ctx: ParseContext, detail_json: dict, result_json: dict) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path(ctx, "details").write_text(
            json.dumps(self._strip_private_keys(detail_json), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._output_path(ctx, "result").write_text(
            json.dumps(self._strip_private_keys(result_json), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _output_path(self, ctx: ParseContext, suffix: str) -> Path:
        stem = Path(ctx.file_path).stem or "parse_result"
        safe_stem = "".join(char if char not in '<>:"/\\|?*' else "_" for char in stem)
        return self.output_dir / f"{safe_stem}_{suffix}.json"
