"""Read-only configuration audit for KybgParser.

Checks the new YAML runtime policy and field-code collisions without modifying
the original business configuration or extraction pipeline.

Usage:
    python tools/scripts/audit_extraction_config.py --config-root configs
    python tools/scripts/audit_extraction_config.py --config-root configs --strict-duplicates
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Issue:
    severity: str
    location: str
    message: str


def _read_yaml(path: Path, issues: list[Issue]) -> dict[str, Any]:
    if not path.is_file():
        issues.append(Issue("error", str(path), "missing YAML configuration"))
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        issues.append(Issue("error", str(path), f"invalid YAML: {exc}"))
        return {}
    if not isinstance(data, dict):
        issues.append(Issue("error", str(path), "top level must be a YAML mapping"))
        return {}
    return data


def _mapping(value: Any, path: str, issues: list[Issue]) -> dict:
    if not isinstance(value, dict):
        issues.append(Issue("error", path, "expected YAML mapping"))
        return {}
    return value


def _strings(value: Any, path: str, issues: list[Issue], *, required: bool = True) -> None:
    if not isinstance(value, list) or (required and not value):
        issues.append(Issue("error", path, "expected a nonempty list of strings"))
        return
    if not all(isinstance(item, str) and bool(item.strip()) for item in value):
        issues.append(Issue("error", path, "list contains a non-string or empty token"))


def _number(value: Any, path: str, issues: list[Issue], low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        issues.append(Issue("error", path, f"expected number between {low} and {high}"))


def _pattern(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, str) or not value:
        issues.append(Issue("error", path, "expected nonempty regular expression"))
        return
    try:
        re.compile(value)
    except re.error as exc:
        issues.append(Issue("error", path, f"invalid regex: {exc}"))


def audit_runtime(config_root: Path) -> list[Issue]:
    issues: list[Issue] = []
    path = config_root / "extraction_runtime.yaml"
    cfg = _read_yaml(path, issues)
    if not cfg:
        return issues

    if cfg.get("version") != 1:
        issues.append(Issue("error", str(path) + ":version", "expected version: 1"))

    field_match = _mapping(cfg.get("field_matching"), "field_matching", issues)
    _number(field_match.get("alias_bonus"), "field_matching.alias_bonus", issues, 0, 10)

    retrieval = _mapping(cfg.get("retrieval"), "retrieval", issues)
    for key in (
        "paragraph_alias_bonus", "paragraph_hint_bonus",
        "table_alias_bonus", "table_caption_bonus",
        "table_aggregate_bonus", "table_hint_bonus",
        "summary_fallback_score",
    ):
        _number(retrieval.get(key), f"retrieval.{key}", issues, -100, 100)
    for key in ("summary_section_keywords", "toc_markers", "toc_headings"):
        _strings(retrieval.get(key), f"retrieval.{key}", issues)
    prefix = retrieval.get("toc_heading_prefix")
    if not isinstance(prefix, str) or not prefix:
        issues.append(Issue("error", "retrieval.toc_heading_prefix", "expected nonempty text"))
    for key in ("toc_heading_max_chars", "toc_prefix_window_chars"):
        _number(retrieval.get(key), f"retrieval.{key}", issues, 1, 100000)

    discovery = _mapping(cfg.get("discovery"), "discovery", issues)
    rapidfuzz = _mapping(discovery.get("rapidfuzz"), "discovery.rapidfuzz", issues)
    _number(rapidfuzz.get("acceptance_score"), "discovery.rapidfuzz.acceptance_score", issues, 0, 100)
    _number(rapidfuzz.get("minimum_competing_gap"), "discovery.rapidfuzz.minimum_competing_gap", issues, 0, 100)
    _number(rapidfuzz.get("safe_fallback_min_label_length"), "discovery.rapidfuzz.safe_fallback_min_label_length", issues, 1, 100)
    for name in ("non_indicator_labels", "column_header_exclusions", "paragraph_separators"):
        _strings(discovery.get(name), f"discovery.{name}", issues)
    scope = discovery.get("scope_terms")
    if not isinstance(scope, list) or not scope:
        issues.append(Issue("error", "discovery.scope_terms", "expected nonempty list of token lists"))
    else:
        for index, group in enumerate(scope):
            _strings(group, f"discovery.scope_terms[{index}]", issues)
    _pattern(discovery.get("context_value_pattern"), "discovery.context_value_pattern", issues)
    for key in ("label_min_length", "label_max_length", "paragraph_clause_max_length", "string_value_max_length"):
        _number(discovery.get(key), f"discovery.{key}", issues, 1, 10000)
    if (isinstance(discovery.get("label_min_length"), int)
            and isinstance(discovery.get("label_max_length"), int)
            and discovery["label_min_length"] > discovery["label_max_length"]):
        issues.append(Issue("error", "discovery.label_max_length", "must be >= label_min_length"))

    value_extraction = _mapping(cfg.get("value_extraction"), "value_extraction", issues)
    headers = _mapping(value_extraction.get("table_headers"), "value_extraction.table_headers", issues)
    for key in ("value", "unit", "noise", "raw_unit", "summary"):
        _strings(headers.get(key), f"value_extraction.table_headers.{key}", issues)
    _pattern(headers.get("material_grade_pattern"), "value_extraction.table_headers.material_grade_pattern", issues)

    resolver = _mapping(cfg.get("candidate_resolution"), "candidate_resolution", issues)
    weights = _mapping(resolver.get("method_weights"), "candidate_resolution.method_weights", issues)
    for name, weight in weights.items():
        if not isinstance(name, str) or not name.strip():
            issues.append(Issue("error", "candidate_resolution.method_weights", "empty method key"))
        _number(weight, f"candidate_resolution.method_weights.{name}", issues, -100, 100)
    _strings(resolver.get("strong_rule_methods"), "candidate_resolution.strong_rule_methods", issues)

    normalization = _mapping(cfg.get("normalization"), "normalization", issues)
    unit_aliases = _mapping(normalization.get("unit_aliases"), "normalization.unit_aliases", issues)
    if not unit_aliases:
        issues.append(Issue("error", "normalization.unit_aliases", "no unit aliases configured"))
    for source, target in unit_aliases.items():
        if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
            issues.append(Issue("error", "normalization.unit_aliases", f"invalid unit mapping {source!r}: {target!r}"))
    return issues


def audit_fields(config_root: Path, *, strict_duplicates: bool = False) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    field_dir = config_root / "fields"
    if not field_dir.is_dir():
        return [Issue("error", str(field_dir), "missing field config directory")], 0
    origins: dict[str, Path] = {}
    for path in sorted(field_dir.glob("*.yaml")):
        data = _read_yaml(path, issues)
        if not data:
            continue
        fields = _mapping(data.get("fields"), f"{path}:fields", issues)
        for code in fields:
            if not isinstance(code, str) or not code.strip():
                issues.append(Issue("error", str(path), f"invalid field code: {code!r}"))
                continue
            previous = origins.get(code)
            if previous is not None:
                severity = "error" if strict_duplicates else "warning"
                issues.append(Issue(severity, f"{path}:fields.{code}", f"also defined in {previous}; legacy last-file-wins remains in effect"))
            origins[code] = path
    return issues, len(origins)


def run(config_root: Path, strict_duplicates: bool = False) -> dict[str, Any]:
    runtime_issues = audit_runtime(config_root)
    field_issues, field_count = audit_fields(config_root, strict_duplicates=strict_duplicates)
    issues = runtime_issues + field_issues
    return {
        "config_root": str(config_root),
        "field_count": field_count,
        "error_count": sum(item.severity == "error" for item in issues),
        "warning_count": sum(item.severity == "warning" for item in issues),
        "issues": [asdict(item) for item in issues],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit KybgParser YAML configuration without running extraction")
    parser.add_argument("--config-root", type=Path, default=Path("configs"))
    parser.add_argument("--strict-duplicates", action="store_true")
    parser.add_argument("--report", type=Path, help="Optional JSON diagnostic report")
    args = parser.parse_args(argv)
    result = run(args.config_root, strict_duplicates=args.strict_duplicates)
    print(f"Fields: {result['field_count']} | Errors: {result['error_count']} | Warnings: {result['warning_count']}")
    for item in result["issues"][:25]:
        print(f"{item['severity'].upper()}: {item['location']}: {item['message']}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
