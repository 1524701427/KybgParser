"""候选、证据和字段解析结果对象。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class FieldEvidence:
    """字段证据，说明结果来自哪里。"""

    source_type: Literal["paragraph", "table", "image", "unknown"]
    text: str
    score: float = 0.0
    block_id: str | None = None
    table_id: str | None = None
    page: int | None = None
    section_path: list[str] = field(default_factory=list)
    match_method: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的证据。
        """
        return asdict(self)


@dataclass
class Candidate:
    """字段候选文本或候选表格区域。"""

    field_code: str
    field_name: str
    source_type: Literal["paragraph", "table"]
    text: str
    score: float
    block_id: str | None = None
    table_id: str | None = None
    page: int | None = None
    section_path: list[str] = field(default_factory=list)
    field_config: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldMatch:
    """字段匹配结果。"""

    candidate: Candidate
    method: str
    score: float
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class Extraction:
    """字段值抽取结果。"""

    field_code: str
    field_name: str
    raw_value: str
    value: str | float | int | None
    unit: str | None
    score: float
    method: str
    evidence: FieldEvidence
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedField:
    """最终字段结果。"""

    field_code: str
    field_name: str
    value: str | float | int | None
    unit: str | None = None
    normalized_value: str | float | int | None = None
    confidence: float = 0.0
    status: Literal["PASS", "WARNING", "FAIL", "MISSING"] = "MISSING"
    evidence: list[FieldEvidence] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。

        Returns:
            dict[str, Any]: 可 JSON 序列化的字段结果。
        """
        return asdict(self)
