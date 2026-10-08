"""字段匹配器。"""

from __future__ import annotations

from parser_engine.document.ast.evidence import Candidate, FieldMatch
from parser_engine.core.logger import logger


class FieldMatcher:
    """组合 alias、正则和向量匹配的字段匹配器。"""

    def __init__(self, bge_matcher=None, bge_top_k_per_field: int = 30, bge_min_score: float = 0.0):
        """初始化字段匹配器。

        Args:
            bge_matcher: 可选 BGE 匹配器。
            bge_top_k_per_field: 每个字段最多送入 BGE 的候选数量。
            bge_min_score: 送入 BGE 的候选最低匹配分。
        """
        self.bge_matcher = bge_matcher
        self.bge_top_k_per_field = bge_top_k_per_field
        self.bge_min_score = bge_min_score

    def match(self, candidates: list[Candidate]) -> list[FieldMatch]:
        """对候选内容进行字段匹配。

        Args:
            candidates: 候选内容。

        Returns:
            list[FieldMatch]: 字段匹配结果。
        """
        matches: list[FieldMatch] = []
        alias_scores: list[float] = []
        bge_candidates_by_field: dict[str, list[tuple[int, Candidate]]] = {}

        for index, candidate in enumerate(candidates):
            aliases = candidate.field_config.get("aliases") or []
            alias_score = 1.0 if any(alias in candidate.text for alias in aliases) else 0.0
            alias_scores.append(alias_score)
            # Short aliases are often ambiguous and still need BGE disambiguation.
            if self._bge_enabled() and candidate.score >= self.bge_min_score and self._should_score_with_bge(candidate, alias_score):
                bge_candidates_by_field.setdefault(candidate.field_code, []).append((index, candidate))

        bge_scores = [0.0] * len(candidates)
        bge_indexes: list[int] = []
        bge_candidates: list[Candidate] = []
        for field_code, items in bge_candidates_by_field.items():
            sorted_items = sorted(items, key=lambda item: item[1].score, reverse=True)
            filtered_items = self._prefer_chapter_candidates([candidate for _index, candidate in sorted_items])
            if filtered_items:
                index_by_id = {id(candidate): index for index, candidate in sorted_items}
                sorted_items = [(index_by_id[id(candidate)], candidate) for candidate in filtered_items if id(candidate) in index_by_id]
            selected_items = sorted_items if self.bge_top_k_per_field <= 0 else sorted_items[: self.bge_top_k_per_field]
            for index, candidate in selected_items:
                bge_indexes.append(index)
                bge_candidates.append(candidate)
        if bge_candidates:
            logger.info(f"字段匹配器开始 BGE 语义匹配：{len(bge_candidates)} / {len(candidates)} 条候选需要向量打分")
            scored = self.bge_matcher.score_many(bge_candidates)
            for index, score in zip(bge_indexes, scored, strict=True):
                bge_scores[index] = score
            if getattr(self.bge_matcher, "release_after_match", False):
                self.bge_matcher._release_model()

        for candidate, alias_score, bge_score in zip(candidates, alias_scores, bge_scores, strict=True):
            score = candidate.score + alias_score + bge_score
            method_parts = []
            if alias_score:
                method_parts.append("alias")
            if bge_score:
                method_parts.append("bge")
            if not method_parts:
                method_parts.append("section")
            if score <= 0:
                continue
            matches.append(
                FieldMatch(
                    candidate=candidate,
                    method="+".join(method_parts),
                    score=score,
                    debug={"alias_score": alias_score, "bge_score": bge_score, "candidate_score": candidate.score},
                )
            )
        logger.info(f"字段匹配器产出匹配：{len(matches)} 条")
        return matches

    def _bge_enabled(self) -> bool:
        return bool(self.bge_matcher and getattr(self.bge_matcher, "enabled", True))

    def _prefer_chapter_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        """优先保留目标章节候选；没有目标章节时退回摘要或全局候选。"""
        target = [candidate for candidate in candidates if candidate.meta.get("section_origin") == "target_section"]
        if target:
            return target
        summary = [candidate for candidate in candidates if candidate.meta.get("section_origin") == "summary_fallback"]
        if summary:
            return summary
        return candidates

    def _should_score_with_bge(self, candidate: Candidate, alias_score: float) -> bool:
        """Score alias hits when they are short or otherwise ambiguous."""
        if alias_score == 0.0:
            return True
        return self._has_short_alias_hit(candidate)

    def _has_short_alias_hit(self, candidate: Candidate) -> bool:
        aliases = candidate.field_config.get("aliases") or []
        matched_aliases = [alias for alias in aliases if alias and alias in candidate.text]
        if not matched_aliases:
            return False
        if candidate.field_config.get("bge_on_alias"):
            return True
        return min(len(alias.strip()) for alias in matched_aliases) <= 4

