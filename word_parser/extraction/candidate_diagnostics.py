"""Read-only YAML-driven diagnostics for the existing lossless candidate fact view.

This is NOT a field resolver. Its findings are observations only:
real wind projects may have legitimately different design phases and schemes.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from typing import Any

from word_parser.extraction.candidate_facts import candidate_fact_report


DEFAULT_POLICY = {
    "version": 1,
    "enabled": True,
    "required_field_codes_for_statuses": ["candidate", "OK"],
    "evidence_checks": {
        "primary_any": ["blockId", "tableId", "evidence"],
        "secondary_field_any": ["tableKey", "tableName", "rowIndex", "columnIndex"],
        "secondary_table_any": ["tableKey", "tableName"],
        "nil_reason_key": "nilReason",
    },
    "cross_stage_variations": {
        "enabled": True,
        "accepted_primary_statuses": ["candidate"],
        "accepted_secondary_statuses": ["OK"],
        "include_only_same_unit": True,
    },
}


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(entry, str) and bool(entry.strip()) for entry in value
    ):
        raise ValueError(f"{label} must be a nonempty list of strings")
    return value


def validate_candidate_audit_policy(policy: dict[str, Any]) -> None:
    """Reject malformed audit-only configuration before examining any details."""
    if not isinstance(policy, dict):
        raise ValueError("candidate audit policy must be a YAML mapping")
    if policy.get("version") != 1:
        raise ValueError("candidate audit policy version must be 1")
    if not isinstance(policy.get("enabled"), bool):
        raise ValueError("candidate audit enabled must be a boolean")
    _string_list(policy.get("required_field_codes_for_statuses"), "required_field_codes_for_statuses")
    checks = policy.get("evidence_checks")
    if not isinstance(checks, dict):
        raise ValueError("evidence_checks must be a mapping")
    for name in ("primary_any", "secondary_field_any", "secondary_table_any"):
        _string_list(checks.get(name), f"evidence_checks.{name}")
    if not isinstance(checks.get("nil_reason_key"), str) or not checks["nil_reason_key"].strip():
        raise ValueError("evidence_checks.nil_reason_key must be a nonempty string")
    variations = policy.get("cross_stage_variations")
    if not isinstance(variations, dict):
        raise ValueError("cross_stage_variations must be a mapping")
    for name in ("enabled", "include_only_same_unit"):
        if not isinstance(variations.get(name), bool):
            raise ValueError(f"cross_stage_variations.{name} must be a boolean")
    for name in ("accepted_primary_statuses", "accepted_secondary_statuses"):
        _string_list(variations.get(name), f"cross_stage_variations.{name}")


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _token(value: Any) -> str:
    # Deterministic representation; never silently round engineering values.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _findings(facts: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    checks = policy["evidence_checks"]
    require_code = set(policy["required_field_codes_for_statuses"])
    issues: list[dict[str, Any]] = []
    names = {
        "primary": "primary_any",
        "secondary_field": "secondary_field_any",
        "secondary_table": "secondary_table_any",
    }
    for index, fact in enumerate(facts):
        stage = fact["stage"]
        status = fact.get("status")
        code = fact.get("code")
        base = {"factIndex": index, "stage": stage, "code": code}
        if status in require_code and not _present(code):
            issues.append({**base, "rule": "MISSING_FIELD_CODE", "message": "Active candidate has no field/table code"})
        if status == "NIL":
            reason = fact["original"].get(checks["nil_reason_key"])
            if not _present(reason):
                issues.append({**base, "rule": "MISSING_NIL_REASON", "message": "NIL result has no failure reason"})
            continue
        if status == "rejected":
            continue
        # Missing source is an audit observation, not an automatic value error.
        source = fact.get("source") or {}
        keys = checks[names[stage]]
        if not any(_present(source.get(key)) for key in keys):
            issues.append({
                **base, "rule": "MISSING_SOURCE_LOCATION",
                "message": "Candidate has none of the configured source-location signals",
                "expectedAny": list(keys),
            })
    return issues


def _cross_stage_variations(facts: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    settings = policy["cross_stage_variations"]
    if not settings["enabled"]:
        return []
    primary_statuses = set(settings["accepted_primary_statuses"])
    secondary_statuses = set(settings["accepted_secondary_statuses"])
    only_same_unit = settings["include_only_same_unit"]
    grouped: dict[tuple[str, str | None], dict[str, set[str]]] = defaultdict(
        lambda: {"primary": set(), "secondary_field": set()}
    )
    for fact in facts:
        stage = fact["stage"]
        if stage not in ("primary", "secondary_field") or fact["kind"] != "field" or not fact.get("code"):
            continue
        allowed = primary_statuses if stage == "primary" else secondary_statuses
        if fact.get("status") not in allowed or fact.get("value") is None:
            continue
        key = (str(fact["code"]), _token(fact.get("unit")) if only_same_unit else None)
        grouped[key][stage].add(_token(fact["value"]))
    observations = []
    for (code, unit), by_stage in sorted(grouped.items(), key=lambda pair: (pair[0][0], str(pair[0][1]))):
        if by_stage["primary"] and by_stage["secondary_field"]:
            union = by_stage["primary"] | by_stage["secondary_field"]
            if len(union) > 1:
                observations.append({
                    "code": code,
                    "unitToken": unit,
                    "primaryValues": sorted(by_stage["primary"]),
                    "secondaryValues": sorted(by_stage["secondary_field"]),
                    "distinctValueCount": len(union),
                    "classification": "REVIEW_ONLY",
                })
    return observations


def candidate_quality_report(
    primary_detail: dict[str, Any],
    secondary_detail: dict[str, Any] | None = None,
    *,
    policy: dict[str, Any] | None = None,
    include_nil: bool = True,
) -> dict[str, Any]:
    """Add opt-in observations to an audit copy; never mutate originals or mapped JSON."""
    settings = deepcopy(DEFAULT_POLICY if policy is None else policy)
    validate_candidate_audit_policy(settings)
    report = candidate_fact_report(primary_detail, secondary_detail, include_nil=include_nil)
    facts = report["facts"]
    issues = _findings(facts, settings) if settings["enabled"] else []
    variations = _cross_stage_variations(facts, settings) if settings["enabled"] else []
    rule_counts: dict[str, int] = {}
    for issue in issues:
        name = issue["rule"]
        rule_counts[name] = rule_counts.get(name, 0) + 1
    report["qualityChecks"] = {
        "mode": "read_only",
        "enabled": settings["enabled"],
        "issueCount": len(issues),
        "countsByRule": rule_counts,
        "issues": issues,
        "crossStageVariationCount": len(variations),
        "crossStageVariations": variations,
        "note": "Evidence observations only; never changes selected fields or verifies truth.",
    }
    return report
