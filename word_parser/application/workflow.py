"""完整解析编排：一次抽取、二次抽取，再生成最终映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from word_parser.mapping.equipment import (
    _fill_station_transformers_from_equipment_table,
    _fill_transformers_from_installation_estimate,
    _map_final_investment_fields,
)
from word_parser.mapping.finance import (
    _combine_finance_cost_mappings,
    _combine_finance_price_mappings,
)
from word_parser.mapping.projector import mapping_from_details
from word_parser.config.loader import ConfigLoader
from word_parser.mapping.secondary_sync import _sync_secondary_outputs
from word_parser.mapping.validation import _validate_final_mapping
from word_parser.mapping.wind import (
    _align_combined_table_mappings,
    _hide_combined_table_duplicate_fields,
    merge_turbulence_records,
)
from word_parser.secondary.stage import enhance_primary_result
from word_parser.secondary.table_values import default_table_value_details_path


DEFAULT_TABLE_VALUE_CONFIG = Path("configs") / "table_field_extractors.yaml"


def enhance_parse_result(
    parse_result: dict[str, Any],
    config_path: str | Path = DEFAULT_TABLE_VALUE_CONFIG,
    config_root: str | Path = "configs",
) -> dict[str, Any]:
    """对一次结果运行二次抽取，再同步业务结果和最终映射。"""
    output_files = parse_result.get("outputFiles", {}) or {}
    result_path = output_files.get("result")
    if not result_path:
        raise RuntimeError("主解析结果中没有 outputFiles.result，无法执行二次抽取。")

    enhanced = enhance_primary_result(parse_result, config_path=config_path)
    result_file = Path(result_path)
    output_files["detail"] = str(default_table_value_details_path(result_file))
    parse_result["outputFiles"] = output_files
    parse_result["tableValueSummary"] = enhanced.get("tableValueExtraction", {}).get("summary", {})
    if not parse_result.get("mapped"):
        parse_result["mapped"] = mapping_from_details(output_files["detail"], config_root=config_root)
    _sync_secondary_outputs(parse_result, enhanced, config_root=config_root)
    _combine_finance_cost_mappings(parse_result, enhanced, config_root=config_root)
    _combine_finance_price_mappings(parse_result, enhanced, config_root=config_root)
    _align_combined_table_mappings(parse_result, config_root=config_root)
    _hide_combined_table_duplicate_fields(parse_result, config_root=config_root)
    _fill_transformers_from_installation_estimate(parse_result)
    _fill_station_transformers_from_equipment_table(parse_result)
    _map_final_investment_fields(parse_result)
    turbulence_key = "${eachTierHeightTurbulenceTableList}"
    if isinstance(parse_result.get("mapped"), dict) and turbulence_key in parse_result["mapped"]:
        parse_result["mapped"][turbulence_key] = merge_turbulence_records(parse_result["mapped"][turbulence_key])
    # 二次抽取可能在业务结果中补出一次详情缺失的字段；映射也必须采用最终值。
    output_codes = ConfigLoader(config_root).load_yaml("output_schema.yaml").get("output_field_codes") or {}
    for section in (parse_result.get("result") or {}).get("sections") or []:
        for field in section.get("fields") or []:
            code = field.get("fieldCode")
            placeholder_name = output_codes.get(code)
            if not placeholder_name:
                continue
            placeholder = placeholder_name if str(placeholder_name).startswith("${") else "${" + str(placeholder_name) + "}"
            if parse_result["mapped"].get(placeholder) is None and field.get("value") is not None:
                parse_result["mapped"][placeholder] = field["value"]
    _validate_final_mapping(parse_result, config_root=config_root)
    mapped_path = output_files.get("mapped")
    if mapped_path and isinstance(parse_result.get("mapped"), dict):
        Path(mapped_path).write_text(json.dumps(parse_result["mapped"], ensure_ascii=False, indent=2), encoding="utf-8")
    return parse_result


def run_full_parse(
    parser,
    file_path: str,
    config_root: str | Path = "configs",
    table_value_config: str | Path = DEFAULT_TABLE_VALUE_CONFIG,
) -> dict[str, Any]:
    """预扫描和一次抽取 → 二次表格抽取 → 最终映射。"""
    primary_result = parser.pipeline.parse(file_path, defer_mapping=True)
    return enhance_parse_result(
        primary_result,
        config_path=table_value_config,
        config_root=config_root,
    )
