"""ResultBuilder 使用的文档、证据、数值和表格公共能力。

这里仅声明稳定的组合入口；具体实现按数值表格、文档表格和文档查询拆分。
方法解析顺序保持与拆分前一致。
"""

from __future__ import annotations

from word_parser.output.builder_support.support_document import DocumentQuerySupportMixin
from word_parser.output.builder_support.support_tables import DocumentTableSupportMixin
from word_parser.output.builder_support.support_values import DocumentValueSupportMixin


class DocumentSupportMixin(
    DocumentQuerySupportMixin,
    DocumentTableSupportMixin,
    DocumentValueSupportMixin,
):
    """组合 ResultBuilder 所需的底层文档辅助方法。

    DocumentQuerySupportMixin 排在首位，用于保留原文件中后定义方法优先的
    Python 语义，避免兼容拆分改变既有业务行为。
    """
