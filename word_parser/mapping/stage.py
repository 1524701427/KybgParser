"""最终映射阶段：二次抽取之后，在独立临时区运行旧算子再一次性提交。

规则顺序来自 configs/mapping_pipeline.yaml；Python 仅注册与执行算子。
为了保护旧版业务值，严格保持已验证的映射后处理调用顺序。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from word_parser.config.loader import ConfigLoader
from word_parser.mapping.equipment import (
    _fill_station_transformers_from_equipment_table,
    _fill_transformers_from_installation_estimate,
    _map_final_investment_fields,
)
from word_parser.mapping.finance import _combine_finance_cost_mappings, _combine_finance_price_mappings
from word_parser.mapping.projector import mapping_from_details
from word_parser.mapping.secondary_sync import _sync_secondary_outputs
from word_parser.mapping.validation import _validate_final_mapping
from word_parser.mapping.wind import (
    _align_combined_table_mappings,
    _hide_combined_table_duplicate_fields,
    merge_turbulence_records,
)
from word_parser.secondary.table_values.primitives import json_safe
from word_parser.secondary.table_values.results import final_result_with_table_values, table_value_details
from word_parser.secondary.table_values.resolver import write_table_value_details
from word_parser.secondary.cross_validation import build_audit
from word_parser.extraction.candidate_registry import CandidateRegistry


LEGACY_OPERATOR_ORDER = (
    "sync_secondary_outputs",
    "combine_finance_cost",
    "combine_finance_price",
    "align_combined_tables",
    "hide_duplicate_combined_fields",
    "fill_transformers",
    "fill_station_transformers",
    "map_final_investment",
    "merge_turbulence",
    "fill_missing_final_fields",
    "validate_final_mapping",
)


def load_mapping_operators(config_root: str | Path) -> tuple[str, ...]:
    """只接受白名单，兼容阶段保持原执行顺序，配置错误立即失败。"""
    policy = ConfigLoader(config_root).load_yaml("mapping_pipeline.yaml")
    if policy.get("version") != 1:
        raise ValueError("mapping_pipeline.yaml: version must be 1")
    if policy.get("compatibility_mode") != "strict_legacy_order":
        raise ValueError("mapping_pipeline.yaml: unsupported compatibility mode")
    names = policy.get("operators")
    if not isinstance(names, list) or any(not isinstance(item, str) for item in names):
        raise ValueError("mapping_pipeline.yaml: operators must be a list of operator IDs")
    if tuple(names) != LEGACY_OPERATOR_ORDER:
        raise ValueError("mapping_pipeline.yaml: operator order must preserve current business mapping semantics")
    return tuple(names)


def _merge_turbulence(parse_result: dict[str, Any], config_root: str | Path) -> None:
    mapped = parse_result.get("mapped")
    if not isinstance(mapped, dict):
        return
    schema = ConfigLoader(config_root).load_required_yaml("output_schema.yaml")
    output_codes = schema.get("output_field_codes") or {}
    for code, specification in (schema.get("field_value_transforms") or {}).items():
        if not isinstance(specification, dict) or specification.get("operator") != "merge_turbulence_records":
            continue
        output_name = output_codes.get(code)
        if not output_name:
            raise ValueError(f"Missing mapped output for transform field {code}")
        placeholder = output_name if str(output_name).startswith("${") else "${" + str(output_name) + "}"
        if placeholder in mapped:
            mapped[placeholder] = merge_turbulence_records(mapped[placeholder])


def _fill_missing_final_fields(parse_result: dict[str, Any], config_root: str | Path) -> None:
    output_codes = ConfigLoader(config_root).load_yaml("output_schema.yaml").get("output_field_codes") or {}
    mapped = parse_result["mapped"]
    for section in (parse_result.get("result") or {}).get("sections") or []:
        for field in section.get("fields") or []:
            code = field.get("fieldCode")
            placeholder_name = output_codes.get(code)
            if not placeholder_name:
                continue
            placeholder = placeholder_name if str(placeholder_name).startswith("${") else "${" + str(placeholder_name) + "}"
            if mapped.get(placeholder) is None and field.get("value") is not None:
                mapped[placeholder] = field["value"]


def _operators() -> dict[str, Callable[[dict[str, Any], dict[str, Any], str | Path], None]]:
    return {
        "sync_secondary_outputs": lambda r, e, c: _sync_secondary_outputs(r, e, config_root=c),
        "combine_finance_cost": lambda r, e, c: _combine_finance_cost_mappings(r, e, config_root=c),
        "combine_finance_price": lambda r, e, c: _combine_finance_price_mappings(r, e, config_root=c),
        "align_combined_tables": lambda r, e, c: _align_combined_table_mappings(r, config_root=c),
        "hide_duplicate_combined_fields": lambda r, e, c: _hide_combined_table_duplicate_fields(r, config_root=c),
        "fill_transformers": lambda r, e, c: _fill_transformers_from_installation_estimate(r, config_root=c),
        "fill_station_transformers": lambda r, e, c: _fill_station_transformers_from_equipment_table(r, config_root=c),
        "map_final_investment": lambda r, e, c: _map_final_investment_fields(r, config_root=c),
        "merge_turbulence": lambda r, e, c: _merge_turbulence(r, c),
        "fill_missing_final_fields": lambda r, e, c: _fill_missing_final_fields(r, c),
        "validate_final_mapping": lambda r, e, c: _validate_final_mapping(r, config_root=c),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def execute_final_mapping(
    parse_result: dict[str, Any],
    enhanced: dict[str, Any],
    *,
    config_root: str | Path = "configs",
) -> dict[str, Any]:
    """二次抽取完成后生成唯一正式 mapped/result/details 输出。

    旧映射方法仍可能向 outputFiles 写中间状态；把路径重定向到独立
    临时工作区，只有全部映射算子和校验成功才提交正式文件。
    """
    names = load_mapping_operators(config_root)
    registry = _operators()
    original_files = dict(parse_result.get("outputFiles") or {})
    for key in ("detail", "result", "mapped"):
        if not original_files.get(key):
            raise RuntimeError(f"最终映射缺少 outputFiles.{key}")
    destinations = {key: Path(original_files[key]) for key in ("detail", "result", "mapped")}
    result_folder = destinations["result"].resolve().parent
    result_folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".kybg-final-mapping-", dir=result_folder) as directory:
        working = {
            key: Path(directory) / f"{key}.json"
            for key in ("detail", "result", "mapped")
        }
        # Preserve primary fieldIndex/tableIndex/source evidence exactly as the
        # legacy write_table_value_details() merge did. Replacing it with only
        # secondary sections silently destroys primary field mapping values.
        primary_details = parse_result.get("_primary_detail")
        if primary_details is not None:
            if not isinstance(primary_details, dict):
                raise ValueError("Primary extraction detail must be a JSON object")
            _write_json(working["detail"], primary_details)
        else:
            # Compatibility with saved details and the primary-only parse API.
            if not destinations["detail"].is_file():
                raise RuntimeError(f"一次抽取详情文件不存在：{destinations['detail']}")
            shutil.copy2(destinations["detail"], working["detail"])
        primary_snapshot = json.loads(working["detail"].read_text(encoding="utf-8"))
        secondary_snapshot = table_value_details(enhanced)
        candidate_registry = CandidateRegistry.from_details(primary_snapshot, secondary_snapshot)
        write_table_value_details(working["detail"], secondary_snapshot)
        _write_json(working["result"], final_result_with_table_values(enhanced))
        parse_result["outputFiles"] = {**original_files, **{key: str(path) for key, path in working.items()}}
        try:
            parse_result["mapped"] = mapping_from_details(working["detail"], config_root=config_root)
            for name in names:
                registry[name](parse_result, enhanced, config_root)
            final_detail = json.loads(working["detail"].read_text(encoding="utf-8"))
            audit = build_audit(parse_result, primary_snapshot, secondary_snapshot, final_detail, config_root, candidate_registry)
            if audit is not None:
                final_detail["crossValidation"] = audit
                _write_json(working["detail"], final_detail)
            _write_json(working["mapped"], parse_result["mapped"])
            _write_json(working["result"], parse_result["result"])
            for key in ("detail", "result", "mapped"):
                if not working[key].is_file():
                    raise RuntimeError(f"Missing final mapping stage file: {key}")
            for key in ("detail", "result", "mapped"):
                destinations[key].parent.mkdir(parents=True, exist_ok=True)
                os.replace(working[key], destinations[key])
        finally:
            parse_result["outputFiles"] = original_files
    # Internal intermediate detail is not part of the public parser return.
    parse_result.pop("_primary_detail", None)
    parse_result.pop("_recovered_tables", None)
    return parse_result
