"""多候选冲突消解。"""

from __future__ import annotations

from collections import defaultdict
import re
from parser_engine.document.ast.evidence import Extraction, ParsedField
from parser_engine.core.logger import logger


class CandidateResolver:
    """从多个候选值中选择最终字段值。"""

    STRONG_RULE_METHODS = {
        "table_lookup",
        "table_aggregate",
        "table_list",
        "regex",
        "regex_derived",
        "regex_multi",
    }

    def __init__(self, field_configs: dict[str, dict] | None = None):
        """初始化候选消解器。

        Args:
            field_configs: 字段配置，用于在最终选择前做质量评分。
        """
        self.field_configs = field_configs or {}

    def resolve(self, extractions: list[Extraction]) -> dict[str, ParsedField]:
        """消解字段候选。

        Args:
            extractions: 抽取候选。

        Returns:
            dict[str, ParsedField]: 每个字段的最终结果。
        """
        grouped: dict[str, list[Extraction]] = defaultdict(list)
        for extraction in extractions:
            grouped[extraction.field_code].append(extraction)

        resolved: dict[str, ParsedField] = {}
        for field_code, items in grouped.items():
            config = self.field_configs.get(field_code, {})
            if config.get("multi_value"):
                resolved[field_code] = self._resolve_multi(field_code, items)
            else:
                resolved[field_code] = self._resolve_single(field_code, items)
        logger.info(f"候选冲突消解完成：{len(resolved)} 个字段")
        return resolved

    def _resolve_single(self, field_code: str, items: list[Extraction]) -> ParsedField:
        """消解单值字段。"""
        config = self.field_configs.get(field_code, {})
        aggregate_field = self._resolve_combined_table_aggregate(field_code, items, config)
        if aggregate_field is not None:
            return aggregate_field
        rank_items = self._rankable_items(items, config)
        best = max(rank_items, key=lambda item: self._resolver_score(item, rank_items))
        resolver_score = self._resolver_score(best, rank_items)
        output_unit = best.unit or config.get("standard_unit")
        return ParsedField(
            field_code=field_code,
            field_name=best.field_name,
            value=best.value,
            unit=output_unit,
            normalized_value=best.value,
            confidence=min(max(resolver_score, 0.0) / 4.0, 0.99),
            status="PASS",
            evidence=[best.evidence],
            debug={
                "resolver": "quality_score",
                "candidate_count": len(items),
                "extractor": best.method,
                "base_score": best.score,
                "resolver_score": resolver_score,
                **best.debug,
            },
        )

    def _resolve_combined_table_aggregate(self, field_code: str, items: list[Extraction], config: dict) -> ParsedField | None:
        """Combine aggregate fragments when Word split one logical detail table into adjacent tables."""
        combine_op = config.get("combine_table_aggregates")
        if combine_op not in {"sum"}:
            return None
        aggregate_items = [item for item in items if item.method == "table_aggregate" and item.debug.get("aggregate_op") == combine_op]
        min_parts = int(config.get("min_aggregate_parts", 2) or 2)
        if len(aggregate_items) < min_parts:
            return None

        sorted_items = sorted(aggregate_items, key=lambda item: self._resolver_score(item, aggregate_items), reverse=True)
        seen_tables = set()
        selected: list[Extraction] = []
        for item in sorted_items:
            key = item.evidence.table_id or item.evidence.text
            if key in seen_tables:
                continue
            seen_tables.add(key)
            selected.append(item)
        if len(selected) < min_parts:
            return None

        try:
            value = sum(float(str(item.value).replace(",", "")) for item in selected)
        except (TypeError, ValueError):
            return None
        precision = config.get("aggregate_precision")
        if isinstance(precision, int):
            value = round(value, precision)
        final_value = int(value) if float(value).is_integer() else value
        best_score = max(self._resolver_score(item, selected) for item in selected)
        first = selected[0]
        return ParsedField(
            field_code=field_code,
            field_name=first.field_name,
            value=final_value,
            unit=first.unit or config.get("standard_unit"),
            normalized_value=final_value,
            confidence=min(max(best_score, 0.0) / 4.0, 0.99),
            status="PASS",
            evidence=[item.evidence for item in selected],
            debug={
                "resolver": "combined_table_aggregate",
                "candidate_count": len(items),
                "aggregate_part_count": len(selected),
                "base_score": first.score,
                "resolver_score": best_score,
            },
        )

    def _resolve_multi(self, field_code: str, items: list[Extraction]) -> ParsedField:
        """消解多值字段，保留去重后的多个候选值。"""
        config = self.field_configs.get(field_code, {})
        rank_items = self._rankable_items(items, config)
        sorted_items = sorted(rank_items, key=lambda item: self._resolver_score(item, rank_items), reverse=True)
        values = []
        evidence = []
        seen = set()
        unit = None
        for item in sorted_items:
            key = (str(item.value), item.unit)
            if key in seen:
                continue
            seen.add(key)
            values.append(item.value)
            evidence.append(item.evidence)
            if unit is None and item.unit:
                unit = item.unit
        best_score = self._resolver_score(sorted_items[0], sorted_items) if sorted_items else 0.0
        first = sorted_items[0]
        output_unit = unit or config.get("standard_unit")
        return ParsedField(
            field_code=field_code,
            field_name=first.field_name,
            value=values,
            unit=output_unit,
            normalized_value=values,
            confidence=min(max(best_score, 0.0) / 4.0, 0.99),
            status="PASS",
            evidence=evidence,
            debug={
                "resolver": "multi_value_quality_score",
                "candidate_count": len(items),
                "value_count": len(values),
                "base_score": first.score,
                "resolver_score": best_score,
                **first.debug,
            },
        )

    def _rankable_items(self, items: list[Extraction], config: dict) -> list[Extraction]:
        """Prefer candidates that satisfy hard validators, but keep a fallback if all fail."""
        allowed = [item for item in items if self._candidate_allowed(item, config)]
        return allowed or items

    def _resolver_score(self, extraction: Extraction, candidates: list[Extraction] | None = None) -> float:
        """按抽取分、字段类型、单位和范围综合评分。"""
        config = self.field_configs.get(extraction.field_code, {})
        score = extraction.score
        value_type = config.get("value_type")

        if value_type == "number":
            if isinstance(extraction.value, (int, float)):
                score += 0.5
                score += self._range_bonus(extraction.value, config)
            else:
                score -= 2.0

        standard_unit = config.get("standard_unit")
        if standard_unit:
            if extraction.unit == standard_unit:
                score += 0.35
            elif extraction.unit is not None:
                score -= 0.8

        method_weight = {
            "table_lookup": 1.2,
            "table_rule": 0.55,
            "table_aggregate": 1.0,
            "table_list": 0.9,
            "regex": 0.15,
            "uie": 0.15,
            "regex_multi": 0.05,
            "regex_derived": 0.25,
            "regex_fallback": -1.2,
        }
        score += method_weight.get(extraction.method, 0.0)
        score += self._policy_bonus(extraction, config, candidates or [])
        score += self._validator_bonus(extraction, config)
        if extraction.debug.get("column_index") is not None or extraction.debug.get("row_index") is not None:
            score += 0.25
        score += self._section_bonus(extraction, config)
        score += self._source_priority_bonus(extraction, config)
        return score

    def _policy_bonus(self, extraction: Extraction, config: dict, candidates: list[Extraction]) -> float:
        """Apply field-level extraction strategy without disabling UIE or rule candidates."""
        policy = config.get("extraction_policy", "balanced")
        preferred_methods = set(config.get("preferred_methods") or [])
        valid_methods = {item.method for item in candidates if self._candidate_allowed(item, config)}
        has_preferred = bool(preferred_methods & valid_methods)
        has_strong_rule = bool(self.STRONG_RULE_METHODS & valid_methods)

        bonus = 0.0
        if extraction.method in preferred_methods:
            bonus += 2.0
        elif has_preferred:
            bonus -= 2.5

        if policy == "rule_first":
            if extraction.method in self.STRONG_RULE_METHODS:
                bonus += 1.25
            elif extraction.method == "table_rule":
                bonus += 0.35
            elif extraction.method == "uie" and has_strong_rule:
                bonus -= 4.0
            elif extraction.method == "uie":
                bonus -= 1.25
        elif policy == "uie_first":
            if extraction.method == "uie":
                bonus += 1.0
            elif extraction.method in self.STRONG_RULE_METHODS:
                bonus += 0.35
        elif policy == "hybrid_validate":
            if extraction.method in self.STRONG_RULE_METHODS:
                bonus += 0.7
            elif extraction.method == "uie":
                bonus += 0.25
        return bonus

    def _validator_bonus(self, extraction: Extraction, config: dict) -> float:
        """Score configured value/evidence validation signals."""
        if not self._candidate_allowed(extraction, config):
            return -8.0
        validators = config.get("validators") or {}
        bonus = 0.0
        value_text = self._candidate_value_text(extraction)
        evidence_text = self._candidate_evidence_text(extraction)
        if validators.get("allow_pattern") and re.search(validators["allow_pattern"], value_text):
            bonus += 0.45
        prefer_value_patterns = validators.get("prefer_patterns") or []
        for pattern in prefer_value_patterns:
            if re.search(pattern, value_text):
                bonus += 0.25
        prefer_evidence = validators.get("prefer_evidence_contains") or []
        if prefer_evidence and any(token in evidence_text for token in prefer_evidence):
            bonus += 0.55
        return bonus

    def _candidate_allowed(self, extraction: Extraction, config: dict) -> bool:
        """Apply hard validators to every extractor, including UIE."""
        validators = config.get("validators") or {}
        value_text = self._candidate_value_text(extraction)
        evidence_text = self._candidate_evidence_text(extraction)

        reject_contains = validators.get("reject_contains") or []
        if reject_contains and any(token in value_text for token in reject_contains):
            return False
        reject_patterns = validators.get("reject_patterns") or []
        if any(re.search(pattern, value_text) for pattern in reject_patterns):
            return False
        allow_pattern = validators.get("allow_pattern")
        if allow_pattern and not re.search(allow_pattern, value_text):
            return False

        reject_evidence = validators.get("reject_evidence_contains") or []
        if reject_evidence and any(token in evidence_text for token in reject_evidence):
            return False
        require_evidence_any = validators.get("require_evidence_any") or []
        if require_evidence_any and not any(token in evidence_text for token in require_evidence_any):
            return False
        require_evidence_all = validators.get("require_evidence_all") or []
        if require_evidence_all and not all(token in evidence_text for token in require_evidence_all):
            return False
        return True

    def _candidate_value_text(self, extraction: Extraction) -> str:
        """Build a normalized text surface for validator checks."""
        parts = [extraction.value, extraction.raw_value]
        if extraction.unit:
            parts.append(extraction.unit)
        return " ".join(str(part) for part in parts if part is not None)

    def _candidate_evidence_text(self, extraction: Extraction) -> str:
        """Build evidence text for context validators."""
        sections = " / ".join(extraction.evidence.section_path or [])
        return f"{sections}\n{extraction.evidence.text or ''}"

    def _section_bonus(self, extraction: Extraction, config: dict) -> float:
        """Prefer candidates from configured sections and penalize excluded sections."""
        sections = config.get("sections") or {}
        section_text = " / ".join(extraction.evidence.section_path)
        if any(keyword in section_text for keyword in sections.get("exclude", [])):
            return -4.0
        include = sections.get("include", [])
        if not include:
            return 0.0
        return 0.8 if any(keyword in section_text for keyword in include) else -0.8

    def _source_priority_bonus(self, extraction: Extraction, config: dict) -> float:
        """Use configured section priority weights during final conflict resolution."""
        source_priority = config.get("source_priority") or {}
        section_weights = source_priority.get("sections") or {}
        if not section_weights:
            return 0.0
        section_text = " / ".join(extraction.evidence.section_path)
        bonus = 0.0
        for keyword, weight in section_weights.items():
            if keyword in section_text:
                try:
                    bonus += float(weight)
                except (TypeError, ValueError):
                    continue
        return bonus

    def _range_bonus(self, value: int | float, config: dict) -> float:
        """根据配置范围给候选加减分。"""
        validators = config.get("validators") or {}
        min_value = validators.get("min")
        max_value = validators.get("max")
        if min_value is not None and value < min_value:
            return -4.0
        if max_value is not None and value > max_value:
            return -4.0
        if min_value is not None or max_value is not None:
            return 0.25
        return 0.0
