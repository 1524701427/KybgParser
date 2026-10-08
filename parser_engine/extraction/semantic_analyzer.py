"""候选值语义一致性分析。"""

from __future__ import annotations

from parser_engine.document.ast.evidence import Extraction
from parser_engine.core.logger import logger


class SemanticAnalyzer:
    """在最终消解前按字段语义给抽取候选二次打分。"""

    def __init__(self, field_configs: dict[str, dict], enabled: bool = True, near_window: int = 40):
        """初始化语义分析器。

        Args:
            field_configs: 字段配置。
            enabled: 是否启用语义分析。
            near_window: 字段词和抽取值之间的近邻字符窗口。
        """
        self.field_configs = field_configs
        self.enabled = enabled
        self.near_window = near_window

    def analyze(self, extractions: list[Extraction]) -> list[Extraction]:
        """为抽取候选追加语义一致性分。"""
        if not self.enabled:
            return extractions

        for extraction in extractions:
            delta, debug = self._semantic_score(extraction)
            extraction.score += delta
            extraction.debug["semantic_score"] = delta
            extraction.debug.update(debug)
        logger.info(f"语义一致性分析完成：{len(extractions)} 条候选")
        return extractions

    def _semantic_score(self, extraction: Extraction) -> tuple[float, dict]:
        """计算单条候选的语义一致性分。"""
        config = self.field_configs.get(extraction.field_code, {})
        evidence_text = extraction.evidence.text or ""
        aliases = self._aliases(config)

        score = 0.0
        debug: dict[str, object] = {}

        alias_hit = [alias for alias in aliases if alias and alias in evidence_text]
        if alias_hit:
            score += 0.35
            debug["semantic_alias_hit"] = alias_hit[:3]
        elif extraction.method == "regex_fallback":
            score -= 0.35
            debug["semantic_penalty"] = "fallback_without_alias"

        if self._value_near_alias(extraction, evidence_text, aliases):
            score += 0.35
            debug["semantic_value_near_alias"] = True

        section_score = self._section_score(extraction, config)
        if section_score:
            score += section_score
            debug["semantic_section_score"] = section_score

        if config.get("value_type") == "number" and not isinstance(extraction.value, (int, float)):
            score -= 0.8
            debug["semantic_penalty"] = "number_field_non_numeric_value"

        return score, debug

    def _aliases(self, config: dict) -> list[str]:
        """返回字段名和别名。"""
        aliases = [config.get("name", "")]
        aliases.extend(config.get("aliases") or [])
        return list(dict.fromkeys(alias for alias in aliases if alias))

    def _value_near_alias(self, extraction: Extraction, evidence_text: str, aliases: list[str]) -> bool:
        """判断抽取值是否靠近字段名或别名。"""
        raw_value = str(extraction.raw_value or extraction.value or "").strip()
        if not raw_value:
            return False
        value_index = evidence_text.find(raw_value)
        if value_index < 0:
            return False
        for alias in aliases:
            alias_index = evidence_text.find(alias)
            if alias_index >= 0 and abs(value_index - alias_index) <= self.near_window:
                return True
        return False

    def _section_score(self, extraction: Extraction, config: dict) -> float:
        """按证据章节路径给语义分。"""
        section_text = " / ".join(extraction.evidence.section_path)
        sections = config.get("sections") or {}
        if any(keyword in section_text for keyword in sections.get("exclude", [])):
            return -1.0
        if any(keyword in section_text for keyword in sections.get("include", [])):
            return 0.2
        return 0.0
