"""从 ``output_schema.yaml`` 构建默认输出结构。

这里不保存业务字段清单，只把配置转换成 ResultBuilder 和公共 API 使用的结构，
避免字段同时维护在 YAML 与 Python 常量中。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from parser_engine.core.config_loader import ConfigLoader


DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"


def load_default_output_schema() -> dict[str, Any]:
    """读取项目自带的最终输出配置。"""
    return ConfigLoader(DEFAULT_CONFIG_ROOT).load_yaml("output_schema.yaml")


def section_schema_from_config(sections: Any) -> dict[str, dict[str, list[str]]]:
    """把 YAML 的章节列表转换成按章节名索引的结构。"""
    if not isinstance(sections, list):
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    for section in sections:
        if not isinstance(section, dict) or not section.get("name"):
            continue
        result[str(section["name"])] = {
            "fields": list(section.get("fields") or []),
            "tables": list(section.get("tables") or []),
            "optional_tables": list(section.get("optional_tables") or []),
            "optional_table_prefixes": list(section.get("optional_table_prefixes") or []),
        }
    return result


def field_meta_from_config(fields: Any) -> dict[str, tuple[str, str | None]]:
    """把 YAML 字段元数据转换成 ``fieldCode -> (名称, 单位)``。"""
    if not isinstance(fields, dict):
        return {}
    result: dict[str, tuple[str, str | None]] = {}
    for code, spec in fields.items():
        if isinstance(spec, dict):
            result[str(code)] = (str(spec.get("name", code)), spec.get("unit"))
    return result


DEFAULT_OUTPUT_SCHEMA = load_default_output_schema()
SECTION_ORDER = list(DEFAULT_OUTPUT_SCHEMA.get("section_order") or [])
REQUIRED_SECTION_SCHEMA = section_schema_from_config(DEFAULT_OUTPUT_SCHEMA.get("sections"))
REQUIRED_FIELD_META = field_meta_from_config(DEFAULT_OUTPUT_SCHEMA.get("fields"))


__all__ = [
    "DEFAULT_CONFIG_ROOT",
    "DEFAULT_OUTPUT_SCHEMA",
    "REQUIRED_FIELD_META",
    "REQUIRED_SECTION_SCHEMA",
    "SECTION_ORDER",
    "field_meta_from_config",
    "load_default_output_schema",
    "section_schema_from_config",
]
