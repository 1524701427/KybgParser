"""根据字段所属对象的上下文筛选抽取候选值。"""

from __future__ import annotations

import re

from word_parser.document.ast.evidence import Extraction


class CandidateContextFilter:
    """所有抽取器生成候选值后，应用独立的字段约束。"""

    def __init__(self, field_configs: dict[str, dict]):
        self.field_configs = field_configs

    def filter(self, extractions: list[Extraction]) -> tuple[list[Extraction], list[Extraction]]:
        accepted: list[Extraction] = []
        rejected: list[Extraction] = []
        for extraction in extractions:
            rules = self.field_configs.get(extraction.field_code, {}).get("context_constraints") or {}
            if not rules:
                accepted.append(extraction)
                continue
            evidence = extraction.evidence.text or ""
            section = " / ".join(extraction.evidence.section_path or [])
            local_evidence = self._value_clause(evidence, extraction.raw_value)
            context = f"{section}\n{local_evidence}"
            negative = [term for term in rules.get("negative_context") or [] if term in local_evidence]
            required = rules.get("required_context_any") or []
            if negative or (required and not any(term in context for term in required)):
                extraction.debug["context_rejection"] = (
                    "negative_context" if negative else "required_context_missing"
                )
                extraction.debug["context_terms"] = negative or required
                rejected.append(extraction)
                continue
            extraction.debug["context_accepted"] = True
            accepted.append(extraction)
        return accepted, rejected

    @staticmethod
    def _value_clause(evidence: str, raw_value: str) -> str:
        """避免相邻工程对象的语句为当前值提供错误上下文。"""
        clauses = re.split(r"[，,。；;\n]", evidence)
        value = str(raw_value or "").strip()
        if value:
            for clause in clauses:
                if value in clause:
                    return clause
        return evidence
