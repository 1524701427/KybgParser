"""Lossless read-only adapters for existing primary and secondary candidate details.

This module is not a resolver. It never normalizes, selects, overwrites or
writes mapped JSON. Original input payloads are deep-copied for traceability.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from typing import Any, Literal


Stage = Literal["primary", "secondary_field", "secondary_table"]
FactKind = Literal["field", "table"]


@dataclass(frozen=True)
class CandidateFact:
    stage: Stage
    kind: FactKind
    code: str | None
    name: str | None
    value: Any
    raw_value: Any
    unit: str | None
    method: str | None
    status: str | None
    score: int | float | None
    confidence: int | float | None
    section: str | None
    source: dict[str, Any]
    original: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rows(payload: dict[str, Any], key: str, context: str) -> list[dict[str, Any]]:
    rows = payload.get(key) or []
    if not isinstance(rows, list):
        raise ValueError(f"{context}.{key} must be a list")
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{context}.{key}[{position}] must be an object")
    return rows


def _primary_fact(record: dict[str, Any]) -> CandidateFact:
    source = {
        "sourceType": record.get("sourceType"),
        "blockId": record.get("blockId"),
        "tableId": record.get("tableId"),
        "page": record.get("page"),
        "row": record.get("row"),
        "column": record.get("column"),
        "sectionPath": deepcopy(record.get("sectionPath")),
        "evidence": record.get("evidence"),
    }
    section_path = record.get("sectionPath") or []
    section = " / ".join(str(item) for item in section_path) if section_path else None
    return CandidateFact(
        stage="primary", kind="field", code=record.get("fieldCode"),
        name=record.get("fieldName"), value=deepcopy(record.get("value")),
        raw_value=deepcopy(record.get("rawValue")), unit=record.get("unit"),
        method=record.get("method"), status=record.get("status"),
        score=record.get("score"), confidence=None,
        section=section, source=source, original=deepcopy(record),
    )


def _secondary_field_fact(record: dict[str, Any], section_name: str | None) -> CandidateFact:
    source = deepcopy(record.get("source") or {})
    if not isinstance(source, dict):
        raise ValueError("secondary table field source must be an object")
    return CandidateFact(
        stage="secondary_field", kind="field", code=record.get("fieldCode"),
        name=record.get("fieldName") or record.get("name"),
        value=deepcopy(record.get("value")),
        raw_value=deepcopy(source.get("rawValue")), unit=record.get("unit"),
        method=record.get("operation"), status=record.get("status"),
        score=None, confidence=record.get("confidence"),
        section=record.get("section") or section_name,
        source=source, original=deepcopy(record),
    )


def _secondary_table_fact(record: dict[str, Any], section_name: str | None) -> CandidateFact:
    source = deepcopy(record.get("source") or {})
    if not isinstance(source, dict):
        raise ValueError("secondary derived table source must be an object")
    value = (
        {"columns": deepcopy(record.get("columns")), "data": deepcopy(record.get("data"))}
        if record.get("status") == "OK" else None
    )
    return CandidateFact(
        stage="secondary_table", kind="table",
        code=record.get("key") or record.get("tableCode"),
        name=record.get("name"), value=value, raw_value=None, unit=None,
        method=record.get("operation"), status=record.get("status"),
        score=None, confidence=record.get("confidence"),
        section=record.get("section") or section_name,
        source=source, original=deepcopy(record),
    )


def collect_candidate_facts(
    primary_detail: dict[str, Any],
    secondary_detail: dict[str, Any] | None = None,
    *,
    include_nil: bool = True,
) -> list[CandidateFact]:
    """Collect every original observation without selecting a winning value.

    The secondary detail is ordinarily embedded inside the primary detail under
    tableValueExtraction. A separately supplied secondary detail takes
    precedence, avoiding duplicate records when both representations exist.
    """
    if not isinstance(primary_detail, dict):
        raise TypeError("primary_detail must be an object")
    if secondary_detail is not None and not isinstance(secondary_detail, dict):
        raise TypeError("secondary_detail must be an object")
    facts: list[CandidateFact] = []
    for row in _rows(primary_detail, "extractionCandidates", "primary"):
        facts.append(_primary_fact(row))
    secondary = secondary_detail if secondary_detail is not None else primary_detail.get("tableValueExtraction") or {}
    if not isinstance(secondary, dict):
        raise ValueError("tableValueExtraction must be an object")
    for section in _rows(secondary, "sections", "secondary"):
        section_name = section.get("name")
        for row in _rows(section, "tableFields", "secondary section"):
            if include_nil or row.get("status") != "NIL":
                facts.append(_secondary_field_fact(row, section_name))
        for row in _rows(section, "derivedTables", "secondary section"):
            if include_nil or row.get("status") != "NIL":
                facts.append(_secondary_table_fact(row, section_name))
    return facts


def _value_token(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def candidate_fact_report(
    primary_detail: dict[str, Any],
    secondary_detail: dict[str, Any] | None = None,
    *,
    include_nil: bool = True,
) -> dict[str, Any]:
    """Return a separate, JSON-serializable audit, not mapped output.

    valueVariations are observations, not error verdicts: phased projects and
    alternative schemes may legitimately have different candidate values.
    """
    facts = collect_candidate_facts(
        primary_detail, secondary_detail, include_nil=include_nil,
    )
    counts = {stage: sum(item.stage == stage for item in facts)
              for stage in ("primary", "secondary_field", "secondary_table")}
    observed: dict[tuple[str, str], set[str]] = {}
    for item in facts:
        if not item.code or item.value is None or item.status in ("NIL", "rejected"):
            continue
        observed.setdefault((item.kind, item.code), set()).add(_value_token(item.value))
    variations = [
        {"kind": kind, "code": code, "distinctValueCount": len(values)}
        for (kind, code), values in sorted(observed.items())
        if len(values) > 1
    ]
    return {
        "version": 1,
        "filePath": primary_detail.get("filePath"),
        "summary": {
            "totalFacts": len(facts),
            "countsByStage": counts,
            "missingCodeCount": sum(not item.code for item in facts),
            "nilCount": sum(item.status == "NIL" for item in facts),
            "valueVariationGroupCount": len(variations),
        },
        "valueVariations": variations,
        "facts": [item.to_dict() for item in facts],
    }
