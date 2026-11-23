"""把召回的候选证据匹配到配置字段。"""

from __future__ import annotations

from word_parser.logger import logger
from word_parser.document.ast.evidence import Candidate, FieldMatch


class FieldMatcher:
    """结合字段别名与召回分数计算匹配分数。"""

    def __init__(self, settings: dict | None = None, lexicon=None):
        # Scoring and match() remain byte-for-byte behavior-compatible.
        self.alias_bonus = float((settings or {}).get("alias_bonus", 1.0))
        # Optional shared lexicon provides read-only diagnostics for future
        # operator migration. It does not modify current field matches.
        self.lexicon = lexicon

    def inspect_label(self, label: str) -> tuple[str | None, str | None, float]:
        """Return the discovery registry's suggestion without changing candidates."""
        if self.lexicon is None:
            return None, None, 0.0
        return self.lexicon.match(label)

    def match(self, candidates: list[Candidate]) -> list[FieldMatch]:
        matches: list[FieldMatch] = []
        for candidate in candidates:
            aliases = candidate.field_config.get("aliases") or []
            alias_score = self.alias_bonus if any(alias in candidate.text for alias in aliases) else 0.0
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
