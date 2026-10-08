"""业务侧常用入口。

这个文件把内部流水线、导出和二次抽取包装成少量稳定函数。
日常调用和脚本优先 import 这里，内部 parser_engine 子包只在需要改解析细节时再看。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from parser_engine.core.factory import create_default_parser
from parser_engine.core.service import ParserService
from parser_engine.tables.table_values import default_table_value_details_path, enhance_result_file


DEFAULT_TABLE_VALUE_CONFIG = Path("configs") / "table_field_extractors.yaml"


def create_parser(config_root: str | Path = "configs") -> ParserService:
    """创建默认解析器。"""
    return create_default_parser(config_root=config_root)


def parse_document(file_path: str, config_root: str | Path = "configs") -> dict[str, Any]:
    """解析单个文档，只运行主解析链路。"""
    return create_parser(config_root=config_root).parse(file_path)


def enhance_parse_result(
    parse_result: dict[str, Any],
    config_path: str | Path = DEFAULT_TABLE_VALUE_CONFIG,
) -> dict[str, Any]:
    """对主解析结果执行二次表内抽取，并更新 outputFiles。"""
    output_files = parse_result.get("outputFiles", {}) or {}
    result_path = output_files.get("result")
    if not result_path:
        raise RuntimeError("主解析结果中没有 outputFiles.result，无法执行二次抽取。")

    enhanced = enhance_result_file(result_path, config_path=config_path)
    result_file = Path(result_path)
    output_files["detail"] = str(default_table_value_details_path(result_file))
    parse_result["outputFiles"] = output_files
    parse_result["tableValueSummary"] = enhanced.get("tableValueExtraction", {}).get("summary", {})
    return parse_result


def parse_document_with_table_values(
    file_path: str,
    config_root: str | Path = "configs",
    table_value_config: str | Path = DEFAULT_TABLE_VALUE_CONFIG,
) -> dict[str, Any]:
    """解析文档，并继续执行二次表内抽取。"""
    return enhance_parse_result(parse_document(file_path, config_root=config_root), config_path=table_value_config)
