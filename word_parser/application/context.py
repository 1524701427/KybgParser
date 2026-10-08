"""解析上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from parser_engine.document.ast.document import DocumentAST
from parser_engine.document.ast.evidence import Candidate, Extraction, FieldMatch, ParsedField


@dataclass
class ParseContext:
    """单次解析过程中的全部中间数据。"""

    file_path: str
    ast: DocumentAST | None = None
    candidates: list[Candidate] = field(default_factory=list)
    matches: list[FieldMatch] = field(default_factory=list)
    extractions: list[Extraction] = field(default_factory=list)
    normalized: list[Extraction] = field(default_factory=list)
    resolved: dict[str, ParsedField] = field(default_factory=dict)
    validated: dict[str, ParsedField] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)
