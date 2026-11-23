"""抽取结束后按输出配置生成占位符映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from word_parser.mapping.wind import merge_turbulence_records


# 同一业务指标在一次和二次抽取中的历史代码不同，优先保留二次抽取结果。
_FIELD_FALLBACKS = {"financeInsuranceRate": "insuranceRate"}


def mapping_from_detail_json(detail_json: dict[str, Any], result_builder: Any) -> dict[str, Any]:
    """按输出 schema 将一次抽取详情投影成占位符映射。"""
    field_index = detail_json.get("fieldIndex", {}) or {}
    table_index = detail_json.get("tableIndex", {}) or {}
    table_codes = set(result_builder._required_table_keys())
    mapped: dict[str, Any] = {}
    for internal_code, placeholder in result_builder.output_field_codes.items():
        if internal_code == "hubHeightAirDensityRange":
            source = (field_index.get("windResourceAirDensityRecords") or {}).get("value")
            mapped[placeholder] = [
                {"tower_code": record.get("tower_code"), "height": record["height"], "value": record["value"]}
                for record in (source if isinstance(source, list) else [])
                if isinstance(record, dict) and record.get("height") is not None and record.get("value") is not None
            ]
            continue
        if internal_code in field_index:
            value = field_index[internal_code].get("value")
            if value is None and internal_code in _FIELD_FALLBACKS:
                value = (field_index.get(_FIELD_FALLBACKS[internal_code]) or {}).get("value")
            if internal_code == "windResourceTurbulenceIntensityRecords":
                value = merge_turbulence_records(value)
            mapped[placeholder] = value
            continue
        table = table_index.get(internal_code)
        if table is None and internal_code in table_codes:
            table = result_builder._empty_required_table(internal_code)
        if table is not None:
            mapped[placeholder] = {
                "name": table.get("name"),
                "columns": table.get("columns", []),
                "columnKeys": table.get("columnKeys", []),
                "data": table.get("data", []),
            }
            continue
        mapped[placeholder] = None
    return mapped


def mapping_from_details(details_path: str | Path, config_root: str | Path = "configs") -> dict:
    """读取详情文件，并复用一次导出的配置投影生成映射。"""
    from word_parser.config.loader import ConfigLoader
    from word_parser.output.result_builder import ResultBuilder

    details = json.loads(Path(details_path).read_text(encoding="utf-8"))
    schema = ConfigLoader(config_root).load_yaml("output_schema.yaml")
    builder = ResultBuilder(output_schema=schema, config_root=config_root)
    return mapping_from_detail_json(details, builder)
