"""基于内存中的一次结果运行二次表格抽取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from word_parser.secondary.table_values.primitives import json_safe
from word_parser.secondary.table_values.resolver import (
    TableValueResolver,
    default_table_value_details_path,
    enhance_result_file,
    write_table_value_details,
)
from word_parser.secondary.table_values.results import final_result_with_table_values, table_value_details


def enhance_primary_result(
    parse_result: dict[str, Any], config_path: str | Path, *, write_outputs: bool = True,
) -> dict[str, Any]:
    """优先使用内存中的一次结果，兼容从文件读取的旧调用方。"""
    output_files = parse_result.get("outputFiles") or {}
    result_path = output_files.get("result")
    if not result_path:
        raise RuntimeError("主解析结果中没有 outputFiles.result，无法执行二次抽取。")
    primary = parse_result.get("result")
    if not isinstance(primary, dict):
        if not write_outputs:
            raise RuntimeError("无内存一次抽取结果，无法执行纯内存二次抽取")
        return enhance_result_file(result_path, config_path=config_path)

    enhanced = TableValueResolver.from_config_file(config_path).enhance_result(primary)
    final = json_safe(final_result_with_table_values(enhanced))
    if write_outputs:
        Path(result_path).write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        write_table_value_details(default_table_value_details_path(result_path), table_value_details(enhanced))
    return enhanced
