"""抽取结束后按输出配置生成占位符映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from word_parser.mapping.wind import merge_turbulence_records


def _density_records_to_height_range(value: Any) -> list[dict[str, Any]]:
    """Registered transform. Preserve original record ordering and shapes."""
    return [
        {"tower_code": record.get("tower_code"), "height": record["height"], "value": record["value"]}
        for record in (value if isinstance(value, list) else [])
        if isinstance(record, dict) and record.get("height") is not None and record.get("value") is not None
    ]


TRANSFORMS = {
    "density_records_to_height_range": _density_records_to_height_range,
    "merge_turbulence_records": merge_turbulence_records,
}


def _resolve_field_value(
    field_code: str,
    field_index: dict[str, Any],
    *,
    fallbacks: dict[str, str],
    transforms: dict[str, Any],
) -> tuple[bool, Any]:
    """Apply only transforms referenced by output_schema.yaml."""
    specification = transforms.get(field_code)
    if specification is not None and not isinstance(specification, dict):
        raise ValueError(f"output_schema.yaml: invalid field_value_transforms.{field_code}")
    if specification is not None:
        operator = specification.get("operator")
        if operator not in TRANSFORMS:
            raise ValueError(f"output_schema.yaml: unknown mapping operator {operator!r} for {field_code}")
        source_code = specification.get("source_field", field_code)
        if not isinstance(source_code, str) or not source_code:
            raise ValueError(f"output_schema.yaml: invalid mapping source for {field_code}")
        if specification.get("always", False):
            value = (field_index.get(source_code) or {}).get("value")
            return True, TRANSFORMS[operator](value)

    if field_code not in field_index:
        return False, None

    value = (field_index.get(field_code) or {}).get("value")
    fallback_code = fallbacks.get(field_code)
    if value is None and fallback_code:
        value = (field_index.get(fallback_code) or {}).get("value")
    if specification is not None:
        value = TRANSFORMS[specification["operator"]](value)
    return True, value


def mapping_from_detail_json(detail_json: dict[str, Any], result_builder: Any) -> dict[str, Any]:
    """Project completed fields/tables by YAML, without extracting new values."""
    field_index = detail_json.get("fieldIndex", {}) or {}
    table_index = detail_json.get("tableIndex", {}) or {}
    table_codes = set(result_builder._required_table_keys())
    fallbacks = getattr(result_builder, "field_value_fallbacks", {})
    transforms = getattr(result_builder, "field_value_transforms", {})
    if not isinstance(fallbacks, dict) or not isinstance(transforms, dict):
        raise ValueError("output_schema.yaml: invalid field fallback/transform mappings")
    mapped: dict[str, Any] = {}
    for internal_code, placeholder in result_builder.output_field_codes.items():
        found, value = _resolve_field_value(
            internal_code, field_index, fallbacks=fallbacks, transforms=transforms,
        )
        if found:
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
