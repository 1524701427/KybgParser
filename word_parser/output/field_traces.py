"""字段证据与最终追踪结构构建。"""

from __future__ import annotations

from typing import Any

from word_parser.document.ast.evidence import FieldEvidence, ParsedField


class FieldTracesMixin:
    """字段证据与最终追踪结构构建，供 JsonExporter 组合使用。"""

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
            "extractor",
        ):
            if key in debug:
                process[key] = debug[key]
        if field.messages:
            process["messages"] = list(field.messages)
        return process
