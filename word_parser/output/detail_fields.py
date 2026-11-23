"""字段详情索引、流程摘要与章节展示构建。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.evidence import ParsedField
from word_parser.application.context import ParseContext


class DetailFieldsMixin:
    """字段详情索引、流程摘要与章节展示构建，供 JsonExporter 组合使用。"""

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
                "contextRejectedCount": len(ctx.debug.get("context_rejections", [])),
                "conflictFieldCount": len(ctx.debug.get("candidate_conflicts", {})),
            },
            "sections": self._build_ordered_detail_sections(sections, compact_fields, compact_tables),
            "fieldIndex": compact_fields,
            "tableIndex": compact_tables,
            "discoveredIndicators": ctx.debug.get("indicators", []),
            "extractionCandidates": [
                {
                    "fieldCode": item.field_code,
                    "rawValue": item.raw_value,
                    "value": item.value,
                    "unit": item.unit,
                    "method": item.method,
                    "score": item.debug.get("rule_score", item.score),
                    "status": "rejected" if item.debug.get("context_rejection") else "candidate",
                    "reason": item.debug.get("context_rejection"),
                    "sourceType": item.evidence.source_type,
                    "blockId": item.evidence.block_id,
                    "tableId": item.evidence.table_id,
                    "page": item.evidence.page,
                    "row": item.debug.get("row_index"),
                    "column": item.debug.get("column_index"),
                    "sectionPath": item.evidence.section_path,
                    "evidence": self._short_text(item.evidence.text, limit=260),
                }
                for item in ctx.extractions
            ],
            "contextRejections": ctx.debug.get("context_rejections", [])[:200],
            "candidateConflicts": ctx.debug.get("candidate_conflicts", {}),
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
            },
            "extraction": {
                "extractionCount": len(extractions),
                "methods": self._counts(extraction.method for extraction in extractions),
            },
            "verification": {
                "normalizedCount": len(normalized),
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
            "candidate_normalized",
            "context_accepted",
            "rule_score",
            "semantic_candidates_rank",
            "semantic_candidates_top_k",
            "schema_name",
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
