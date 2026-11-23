"""四阶段完整解析：预抽取 → 一次抽取 → 二次抽取 → 最终映射。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from word_parser.mapping.stage import execute_final_mapping
from word_parser.secondary.stage import enhance_primary_result
from word_parser.secondary.table_values import default_table_value_details_path


DEFAULT_TABLE_VALUE_CONFIG = Path("configs") / "table_field_extractors.yaml"


def enhance_parse_result(
    parse_result: dict[str, Any],
    config_path: str | Path = DEFAULT_TABLE_VALUE_CONFIG,
    config_root: str | Path = "configs",
) -> dict[str, Any]:
    """第三阶段执行二次抽取，第四阶段统一映射并写出最终 JSON。"""
    output_files = parse_result.get("outputFiles", {}) or {}
    result_path = output_files.get("result")
    if not result_path:
        raise RuntimeError("主解析结果中没有 outputFiles.result，无法执行二次抽取。")

    # 二次抽取先保存在内存；不要提前发布尚未映射校验的中间结果。
    enhanced = enhance_primary_result(
        parse_result, config_path=config_path, write_outputs=False,
    )
    output_files["detail"] = str(default_table_value_details_path(Path(result_path)))
    parse_result["outputFiles"] = output_files
    parse_result["tableValueSummary"] = enhanced.get("tableValueExtraction", {}).get("summary", {})
    return execute_final_mapping(parse_result, enhanced, config_root=config_root)


def run_full_parse(
    parser,
    file_path: str,
    config_root: str | Path | None = None,
    table_value_config: str | Path | None = None,
) -> dict[str, Any]:
    """完整四阶段：使用同一个 config_root 装配全部抽取和映射规则。"""
    if config_root is None:
        builder = getattr(getattr(parser.pipeline, "exporter", None), "result_builder", None)
        config_root = getattr(builder, "config_root", Path("configs"))
    if table_value_config is None:
        table_value_config = Path(config_root) / "table_field_extractors.yaml"
    primary_result = parser.pipeline.parse(file_path, defer_mapping=True)
    return enhance_parse_result(
        primary_result,
        config_path=table_value_config,
        config_root=config_root,
    )
