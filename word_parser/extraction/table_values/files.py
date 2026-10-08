"""Secondary extraction: files. Existing rule semantics are preserved."""

from __future__ import annotations

import json

from pathlib import Path

from typing import Any

from word_parser.extraction.table_values.presentation import final_result_with_table_values, table_value_details

from word_parser.extraction.table_values.primitives import json_safe

from word_parser.extraction.table_values.resolver import TableValueResolver


def enhance_result_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path = "configs/table_field_extractors.yaml",
    details_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取 result.json，写出二次抽取结果和过程明细。"""
    input_file = Path(input_path)
    result = json.loads(input_file.read_text(encoding="utf-8"))
    enhanced = TableValueResolver.from_config_file(config_path).enhance_result(result)
    if output_path is None:
        output_path = input_file
    if details_output_path is None:
        details_output_path = default_table_value_details_path(input_file)
    Path(output_path).write_text(json.dumps(json_safe(final_result_with_table_values(enhanced)), ensure_ascii=False, indent=2), encoding="utf-8")
    write_table_value_details(details_output_path, table_value_details(enhanced))
    return enhanced

def default_table_value_details_path(input_file: str | Path) -> Path:
    """根据主 result 路径生成 details 路径。"""
    path = Path(input_file)
    base = _base_result_stem(path)
    return path.with_name(f"{base}_details.json")

def _base_result_stem(path: Path) -> str:
    """剥离 result/enhanced_result 后缀，避免重复生成 enhanced_enhanced。"""
    stem = path.stem
    if stem.endswith("_enhanced_result"):
        return stem[: -len("_enhanced_result")]
    if stem.endswith("_result"):
        return stem[: -len("_result")]
    return stem

def write_table_value_details(path: str | Path, details: dict[str, Any]) -> None:
    """把二次抽取过程写入 details JSON；若主 details 已存在则追加字段。"""
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
