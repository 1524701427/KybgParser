"""把召回的候选证据匹配到配置字段。"""

from __future__ import annotations

from word_parser.logger import logger
from word_parser.document.ast.evidence import Candidate, FieldMatch


class FieldMatcher:
    """结合字段别名与召回分数计算匹配分数。"""

    def match(self, candidates: list[Candidate]) -> list[FieldMatch]:
        matches: list[FieldMatch] = []
        for candidate in candidates:
            aliases = candidate.field_config.get("aliases") or []
            alias_score = 1.0 if any(alias in candidate.text for alias in aliases) else 0.0
            score = candidate.score + alias_score
            if score <= 0:
                continue
            matches.append(
                FieldMatch(
                    candidate=candidate,
                    method="alias" if alias_score else "section",
                    score=score,
                    debug={"alias_score": alias_score, "candidate_score": candidate.score},
                )
            )
        logger.info(f"字段匹配器产出匹配：{len(matches)} 条")
        return matches
