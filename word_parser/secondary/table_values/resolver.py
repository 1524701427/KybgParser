"""二次抽取解析器，并保留现有规则语义。"""

from __future__ import annotations

import copy
import json

from pathlib import Path

from typing import Any

from word_parser.config.loader import ConfigLoader

from word_parser.secondary.table_values.context import ResultContext

from word_parser.secondary.table_values.results import final_result_with_table_values, nil_field, table_value_details

from word_parser.secondary.table_values.primitives import json_safe

from word_parser.secondary.table_values.expansion import RuleExpansionMixin

from word_parser.secondary.table_values.cells import CellOperationsMixin

from word_parser.secondary.table_values.projection import ProjectionOperationsMixin

from word_parser.secondary.table_values.locator import TableLocatorMixin


class TableValueResolver(RuleExpansionMixin, CellOperationsMixin, ProjectionOperationsMixin, TableLocatorMixin):

    # Operators continue to be selected by table_field_extractors.yaml.
    # The dispatch registry replaces the growing Python if/elif chain without
    # modifying the existing operator implementations or their output types.
    _FIELD_OPERATIONS = {
        "cell": "_extract_cell",
        "max_row_label": "_extract_max_row_label",
        "sector_max": "_extract_sector_max",
        "column_values": "_extract_column_values",
        "cell_series": "_extract_cell_series",
        "cell_ratio": "_extract_cell_ratio",
        "sum_fields": "_extract_sum_fields",
    }
    _MULTI_FIELD_OPERATIONS = {
        "cell_items": "_extract_cell_items",
        "investment_group_fields": "_extract_investment_group_fields",
    }
    _TABLE_OPERATIONS = {
        "table_projection": "_extract_table_projection",
        "filter_table_projection": "_extract_filter_table_projection",
        "copy_table": "_extract_copy_table",
    }


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

        参数：
            result: 主解析链路导出的 result JSON 对象。

        返回：
            dict[str, Any]: 深拷贝后的增强结果，原对象不会被修改。
        """
        enhanced = copy.deepcopy(result)
        context = ResultContext(enhanced)
        for rule in self._expand_rules(self.rules, context):
            operation = str(rule.get("operation") or "cell")
            if operation in self._FIELD_OPERATIONS:
                handler = getattr(self, self._FIELD_OPERATIONS[operation])
                context.add_table_field(handler(context, rule))
            elif operation in self._MULTI_FIELD_OPERATIONS:
                handler = getattr(self, self._MULTI_FIELD_OPERATIONS[operation])
                for field in handler(context, rule):
                    context.add_table_field(field)
            elif operation in self._TABLE_OPERATIONS:
                handler = getattr(self, self._TABLE_OPERATIONS[operation])
                context.add_derived_table(handler(context, rule))
            else:
                context.add_table_field(nil_field(rule, "unsupported_operation", f"不支持的二次抽取操作：{operation}"))
        summary = context.summary()
        summary["skippedDynamicRuleCount"] = len(self._skipped_dynamic_rules)
        summary["skippedDynamicRules"] = self._skipped_dynamic_rules
        enhanced.setdefault("tableValueExtraction", {})["summary"] = summary
        enhanced.setdefault("tableValueExtraction", {})["configVersion"] = self.config.get("version")
        return enhanced


def enhance_result_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path = "configs/table_field_extractors.yaml",
    details_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取结果文件，写出合并后的最终结果和二次抽取明细。"""
    input_file = Path(input_path)
    result = json.loads(input_file.read_text(encoding="utf-8"))
    enhanced = TableValueResolver.from_config_file(config_path).enhance_result(result)
    if output_path is None:
        output_path = input_file
    if details_output_path is None:
        details_output_path = default_table_value_details_path(input_file)
    final_result = json_safe(final_result_with_table_values(enhanced))
    Path(output_path).write_text(json.dumps(final_result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_table_value_details(details_output_path, table_value_details(enhanced))
    return enhanced


def default_table_value_details_path(input_file: str | Path) -> Path:
    """根据主结果文件路径生成明细文件路径。"""
    path = Path(input_file)
    return path.with_name(f"{_base_result_stem(path)}_details.json")


def _base_result_stem(path: Path) -> str:
    """剥离结果文件后缀，避免重复生成 enhanced 标识。"""
    stem = path.stem
    if stem.endswith("_enhanced_result"):
        return stem[: -len("_enhanced_result")]
    if stem.endswith("_result"):
        return stem[: -len("_result")]
    return stem


def write_table_value_details(path: str | Path, details: dict[str, Any]) -> None:
    """写入二次抽取明细；已有明细文件时保留其中其他内容。"""
    details_path = Path(path)
    payload: dict[str, Any]
    if details_path.exists():
        try:
            payload = json.loads(details_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    if not payload.get("filePath") and details.get("filePath"):
        payload["filePath"] = details.get("filePath")
    payload["tableValueExtraction"] = details
    details_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
