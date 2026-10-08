"""按字段分组的漏斗剪枝器。"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import TypeVar

from parser_engine.document.ast.evidence import Extraction, FieldMatch
from parser_engine.core.logger import logger

T = TypeVar("T")


class FunnelPruner:
    """在昂贵阶段前按字段保留 Top-K 候选。"""

    STRONG_EXTRACTION_METHODS = {
        "table_lookup",
        "table_rule",
        "table_aggregate",
        "table_list",
        "regex",
        "regex_derived",
        "regex_multi",
    }

    def __init__(self, enabled: bool = True, stages: dict[str, int] | None = None, field_configs: dict[str, dict] | None = None):
        """初始化剪枝器。

        Args:
            enabled: 是否启用漏斗剪枝。
            stages: 阶段名到每字段保留数量的映射；小于等于 0 表示不剪枝。
            field_configs: 字段配置，用于对 rule_first 字段保留强规则候选。
        """
        self.enabled = enabled
        self.stages = stages or {}
        self.field_configs = field_configs or {}

    def prune_matches(self, matches: list[FieldMatch], stage: str) -> list[FieldMatch]:
        """按字段剪枝匹配候选。"""
        return self._prune(matches, stage, key_func=lambda item: item.candidate.field_code, score_func=lambda item: item.score)

    def prune_extractions(self, extractions: list[Extraction], stage: str) -> list[Extraction]:
        """按字段剪枝抽取候选。"""
        return self._prune(
            extractions,
            stage,
            key_func=lambda item: item.field_code,
            score_func=lambda item: item.score,
            keep_func=self._policy_keep_extractions,
        )

    def _prune(self, items: list[T], stage: str, key_func, score_func, keep_func=None) -> list[T]:
        """通用分组 Top-K 剪枝。"""
        top_k = int(self.stages.get(stage, 0))
        if not self.enabled or top_k <= 0 or not items:
            return items

        grouped: dict[str, list[T]] = defaultdict(list)
        for item in items:
            grouped[key_func(item)].append(item)

        kept: list[T] = []
        for group_items in grouped.values():
            sorted_items = sorted(group_items, key=score_func, reverse=True)
            keep_items = sorted_items[:top_k]
            if keep_func is not None:
                keep_items = keep_func(sorted_items, keep_items, top_k)
            keep_ids = {id(item) for item in keep_items}
            for rank, item in enumerate(sorted_items, start=1):
                self._mark_debug(item, stage, rank, top_k, id(item) in keep_ids)
            kept.extend(keep_items)

        logger.info(f"漏斗剪枝完成：stage={stage}，输入 {len(items)} 条，输出 {len(kept)} 条，每字段 Top {top_k}")
        return kept

    def _policy_keep_extractions(self, sorted_items: list[Extraction], keep_items: list[Extraction], top_k: int) -> list[Extraction]:
        """For rule-first fields, keep at least one valid strong-rule extraction through model stages."""
        if not sorted_items or top_k <= 0:
            return keep_items
        field_code = sorted_items[0].field_code
        config = self.field_configs.get(field_code, {})
        if config.get("extraction_policy") != "rule_first":
            return keep_items

        preferred_methods = set(config.get("preferred_methods") or [])
        strong_methods = preferred_methods or self.STRONG_EXTRACTION_METHODS
        if any(item.method in strong_methods and self._extraction_allowed(item, config) for item in keep_items):
            return keep_items

        replacement = next(
            (item for item in sorted_items if item.method in strong_methods and self._extraction_allowed(item, config)),
            None,
        )
        if replacement is None:
            return keep_items

        if len(keep_items) < top_k:
            return [*keep_items, replacement]

        replace_index = len(keep_items) - 1
        for index in range(len(keep_items) - 1, -1, -1):
            if keep_items[index].method not in strong_methods:
                replace_index = index
                break
        updated = keep_items.copy()
        updated[replace_index] = replacement
        return updated

    def _extraction_allowed(self, extraction: Extraction, config: dict) -> bool:
        """Small validator subset used before resolver so valid rules are not pruned out."""
        validators = config.get("validators") or {}
        value_text = " ".join(
            str(part) for part in (extraction.value, extraction.raw_value, extraction.unit) if part is not None
        )
        evidence_text = f"{' / '.join(extraction.evidence.section_path or [])}\n{extraction.evidence.text or ''}"

        allow_pattern = validators.get("allow_pattern")
        if allow_pattern and not re.search(allow_pattern, value_text):
            return False
        if any(re.search(pattern, value_text) for pattern in validators.get("reject_patterns") or []):
            return False
        if any(token in value_text for token in validators.get("reject_contains") or []):
            return False
        if any(token in evidence_text for token in validators.get("reject_evidence_contains") or []):
            return False
        require_any = validators.get("require_evidence_any") or []
        if require_any and not any(token in evidence_text for token in require_any):
            return False
        require_all = validators.get("require_evidence_all") or []
        if require_all and not all(token in evidence_text for token in require_all):
            return False
        return True

    def _mark_debug(self, item, stage: str, rank: int, top_k: int, kept: bool) -> None:
        """记录候选在剪枝阶段的排名。"""
        debug = getattr(item, "debug", None)
        if debug is None:
            return
        debug[f"{stage}_rank"] = rank
        debug[f"{stage}_top_k"] = top_k
        debug[f"{stage}_kept"] = kept
