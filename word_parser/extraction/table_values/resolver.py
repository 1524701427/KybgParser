"""Secondary extraction: resolver. Existing rule semantics are preserved."""

from __future__ import annotations

import copy

from pathlib import Path

from typing import Any

from word_parser.config.loader import ConfigLoader

from word_parser.extraction.table_values.context import ResultContext

from word_parser.extraction.table_values.results import nil_field

from word_parser.extraction.table_values.expansion import RuleExpansionMixin

from word_parser.extraction.table_values.cells import CellOperationsMixin

from word_parser.extraction.table_values.projection import ProjectionOperationsMixin

from word_parser.extraction.table_values.locator import TableLocatorMixin


class TableValueResolver(RuleExpansionMixin, CellOperationsMixin, ProjectionOperationsMixin, TableLocatorMixin):
    """从 result.json 已有表格中执行配置化二次抽取。

    支持的操作包括：
    - ``cell``：按行标签和列名取单元格。
    - ``max_row_label``：指定数值列取最大值，并返回同一行的标签列。
    - ``table_projection``：按列名投影一个子表。
    - ``filter_table_projection``：按设备/项目别名筛选行，再投影固定列生成子表。
    - ``copy_table``：把已有表复制到二次抽取结果中，作为显式需求输出。
    - ``sum_fields``：从已有字段中按 fieldCode 求和，生成派生字段。
    - ``cell_items``：复用同一张表和目标列，按 items 批量生成多个字段。
    - ``cell_series``：同一目标行按多列批量抽取，返回列名到值的映射。
    - ``cell_ratio``：从两组表内单元格取数相除，生成比率字段。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """初始化二次抽取器。"""
        self.config = config or {}
        self.rules = list(self.config.get("rules") or [])
        self._table_frame_cache: dict[int, Any] = {}

    @classmethod
    def from_config_file(cls, config_path: str | Path = "configs/table_field_extractors.yaml") -> "TableValueResolver":
        """从独立 YAML 配置创建二次抽取器。"""
        path = Path(config_path)
        if path.is_absolute():
            config_root = path.parent
            relative_path = path.name
        else:
            config_root = path.parent if str(path.parent) not in {"", "."} else "configs"
            relative_path = path.name
        return cls(ConfigLoader(config_root).load_yaml(relative_path))

    def enhance_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """返回带二次抽取内部结果的增强版 result。

        Args:
            result: 主解析链路导出的 result JSON 对象。

        Returns:
            dict[str, Any]: 深拷贝后的增强结果，原对象不会被修改。
        """
        enhanced = copy.deepcopy(result)
        context = ResultContext(enhanced)
        for rule in self._expand_rules(self.rules, context):
            operation = str(rule.get("operation") or "cell")
            if operation == "cell":
                context.add_table_field(self._extract_cell(context, rule))
            elif operation == "cell_items":
                for field in self._extract_cell_items(context, rule):
                    context.add_table_field(field)
            elif operation == "max_row_label":
                context.add_table_field(self._extract_max_row_label(context, rule))
            elif operation == "sector_max":
                context.add_table_field(self._extract_sector_max(context, rule))
            elif operation == "column_values":
                context.add_table_field(self._extract_column_values(context, rule))
            elif operation == "cell_series":
                context.add_table_field(self._extract_cell_series(context, rule))
            elif operation == "cell_ratio":
                context.add_table_field(self._extract_cell_ratio(context, rule))
            elif operation == "sum_fields":
                context.add_table_field(self._extract_sum_fields(context, rule))
            elif operation == "table_projection":
                context.add_derived_table(self._extract_table_projection(context, rule))
            elif operation == "filter_table_projection":
                context.add_derived_table(self._extract_filter_table_projection(context, rule))
            elif operation == "copy_table":
                context.add_derived_table(self._extract_copy_table(context, rule))
            else:
                context.add_table_field(nil_field(rule, "unsupported_operation", f"不支持的二次抽取操作：{operation}"))
        enhanced.setdefault("tableValueExtraction", {})["summary"] = context.summary()
        enhanced.setdefault("tableValueExtraction", {})["configVersion"] = self.config.get("version")
        return enhanced
