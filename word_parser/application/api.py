"""对外提供稳定的报告解析函数。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from word_parser.application.factory import create_default_parser
from word_parser.application.service import ParserService
from word_parser.application.workflow import (
    DEFAULT_TABLE_VALUE_CONFIG,
    enhance_parse_result,
    run_full_parse,
)


def create_parser(config_root: str | Path = "configs") -> ParserService:
    """创建默认解析器。"""
    return create_default_parser(config_root=config_root)


def parse_document(file_path: str, config_root: str | Path = "configs") -> dict[str, Any]:
    """解析单个文档，只运行主解析链路。"""
    return create_parser(config_root=config_root).parse(file_path)


def parse_document_with_table_values(
    file_path: str,
    config_root: str | Path = "configs",
    table_value_config: str | Path | None = None,
) -> dict[str, Any]:
    """解析文档，并继续执行二次表内抽取。"""
    return run_full_parse(
        create_parser(config_root=config_root),
        file_path,
        config_root=config_root,
        table_value_config=table_value_config,
    )
