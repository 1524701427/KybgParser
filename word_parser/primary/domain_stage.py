"""领域抽取阶段：位于预抽取和一次抽取之后、结果组装之前。

YAML 规则由 ResultBuilder 的领域方法消费；这里只负责阶段顺序和
状态交付。兼容期间复用原有全部 Python 方法，避免重写导致字段漏提。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from word_parser.document.ast.document import DocumentAST
from word_parser.document.ast.evidence import ParsedField

if TYPE_CHECKING:
    from word_parser.output.result_builder import ResultBuilder


@dataclass
class DomainExtractionState:
    """中间结果：字段、领域明细和源 AST；尚未生成最终映射。"""

    ast: DocumentAST | None
    fields: dict[str, ParsedField]
    details: dict[str, Any]


def extract_domain_fields(
    builder: "ResultBuilder",
    ast: DocumentAST | None,
    fields: dict[str, ParsedField],
    *,
    file_path: str | None = None,
) -> DomainExtractionState:
    """执行原有领域方法，调用顺序与旧 ResultBuilder.build 完全相同。

    Python 提供抽取、过滤、计算方法；字段词典和正则从 YAML 读取。
    本阶段不创建最终 result/mapped JSON，也不写输出文件。
    """
    details = builder._build_details(ast)
    builder._apply_detail_context_constraints(details)
    selected = dict(fields)
    if file_path and ast is not None:
        ast.meta.setdefault("file_path", file_path)
    if ast is not None:
        builder._apply_deterministic_overrides(ast, selected, details)
        builder._apply_quality_filters(selected, ast)
    builder._fill_foundation_equivalent_fields(selected)
    builder._fill_finance_insurance_equivalent_field(selected)
    return DomainExtractionState(ast=ast, fields=selected, details=details)
