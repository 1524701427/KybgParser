"""数值和单位归一化。"""

from __future__ import annotations

import re

from parser_engine.document.ast.evidence import Extraction, ParsedField
from parser_engine.core.logger import logger


class Normalizer:
    """字段值归一化器。"""

    def __init__(self, field_configs: dict[str, dict] | None = None):
        """Initialize normalizer with optional field type configuration."""
        self.field_configs = field_configs or {}

    UNIT_MAP = {
        "米/秒": "m/s",
        "m·s-1": "m/s",
        "万千瓦时": "万kWh",
        "小时": "h",
        "兆瓦": "MW",
        "千伏": "kV",
        "元/千瓦": "元/kW",
        "元/千瓦时": "元/kWh",
        "公里": "km",
        "千米": "km",
        "米": "m",
        "平方米": "m2",
        "㎡": "m2",
        "m²": "m2",
        "立方米": "m3",
        "m³": "m3",
        "公顷": "hm2",
        "kg/m³": "kg/m3",
        "W/m²": "W/m2",
        "kN/㎡": "kN/m2",
        "千牛/平方米": "kN/m2",
        "千伏安": "kVA",
        "兆伏安": "MVA",
        "个月": "月",
        "万元": "万元",
        "年": "年",
        "月": "月",
        "度": "度",
        "台": "台",
        "座": "座",
        "个": "个",
        "根": "根",
        "回": "回",
        "基": "基",
        "人": "人",
        "吨": "t",
    }

    def normalize(self, extractions: list[Extraction]) -> list[Extraction]:
        """兼容旧入口：执行候选级归一化。"""
        return self.normalize_candidates(extractions)

    def normalize_candidates(self, extractions: list[Extraction]) -> list[Extraction]:
        """候选级归一化，保留 raw_value 和 evidence 原文不变。

        Args:
            extractions: 原始抽取结果。

        Returns:
            list[Extraction]: 归一化后的抽取结果。
        """
        for extraction in extractions:
            extraction.value = self._normalize_value(extraction.field_code, extraction.value)
            extraction.unit = self._normalize_unit(extraction.unit)
            extraction.value, extraction.unit = self._convert_to_standard_unit(extraction.field_code, extraction.value, extraction.unit)
            extraction.debug["candidate_normalized"] = True
        logger.info("候选字段值归一化完成")
        return extractions

    def normalize_fields(self, fields: dict[str, ParsedField]) -> dict[str, ParsedField]:
        """最终字段级归一化，统一导出格式。"""
        for field in fields.values():
            field.value = self._normalize_value(field.field_code, field.value)
            field.unit = self._normalize_unit(field.unit)
            field.normalized_value = self._normalize_value(field.field_code, field.normalized_value)
            field.value, field.unit = self._convert_to_standard_unit(field.field_code, field.value, field.unit)
            field.normalized_value = field.value
            field.debug["field_normalized"] = True
        logger.info("最终字段值归一化完成")
        return fields

    def _normalize_value(self, field_code: str, value):
        """Normalize according to field value_type instead of forcing every value numeric."""
        config = self.field_configs.get(field_code, {})
        value_type = config.get("value_type", "number")
        if isinstance(value, list):
            return [self._normalize_value(field_code, item) for item in value]
        if value_type == "number":
            return self._normalize_number(value)
        return self._normalize_string(field_code, value)

    def _normalize_string(self, field_code: str, value):
        """Apply configured canonical mappings for string fields."""
        if value is None:
            return None
        config = self.field_configs.get(field_code, {})
        text = str(value).strip()
        value_map = config.get("value_map") or {}
        if text in value_map:
            return value_map[text]
        for source, target in value_map.items():
            if source and source in text:
                return target
        return text

    def _normalize_number(self, value):
        """归一化数值。

        Args:
            value: 原始值。

        Returns:
            float | str | int | None: 归一化值。
        """
        if value is None:
            return None
        if isinstance(value, list):
            return [self._normalize_number(item) for item in value]
        if isinstance(value, (int, float)):
            return value
        cleaned = str(value).replace(",", "").strip()
        if self._looks_like_numeric_expression(cleaned):
            return re.sub(r"\s+", "", cleaned).replace("x", "×").replace("X", "×")
        if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:\s*(?:%|[a-zA-Z\u4e00-\u9fff/·.]+))?", cleaned):
            return cleaned
        found = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if not found:
            return cleaned
        number = float(found.group(0))
        return int(number) if number.is_integer() else number

    def _looks_like_numeric_expression(self, text: str) -> bool:
        return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?\s*[×xX]\s*[-+]?\d+(?:\.\d+)?", text))

    def _normalize_unit(self, unit: str | None) -> str | None:
        """归一化单位。

        Args:
            unit: 原始单位。

        Returns:
            str | None: 标准单位。
        """
        if not unit:
            return None
        unit = re.sub(r"\s+", "", unit.strip())
        unit = unit.replace("．", ".").replace("·", "·")
        unit = re.sub(r"(?i)^万kw[·.]?h$", "万kW·h", unit)
        unit = re.sub(r"(?i)^万kwh$", "万kWh", unit)
        unit = re.sub(r"(?i)^m\s*/\s*s$", "m/s", unit)
        unit = re.sub(r"(?i)^kv$", "kV", unit)
        return self.UNIT_MAP.get(unit, unit)

    def _convert_to_standard_unit(self, field_code: str, value, unit: str | None):
        config = self.field_configs.get(field_code, {})
        standard = self._normalize_unit(config.get('standard_unit'))
        unit = self._normalize_unit(unit)
        if not standard or not unit or unit == standard:
            return value, unit or standard
        converted = self._convert_value(value, unit, standard)
        if converted is None:
            return value, unit
        return converted, standard

    def _convert_value(self, value, source_unit: str, target_unit: str):
        if isinstance(value, list):
            converted = [self._convert_value(item, source_unit, target_unit) for item in value]
            return None if any(item is None for item in converted) else converted
        if not isinstance(value, (int, float)):
            try:
                value = float(str(value).replace(',', ''))
            except (TypeError, ValueError):
                return None
        factor = self._unit_factor(source_unit, target_unit)
        if factor is None:
            return None
        result = float(value) * factor
        return int(result) if result.is_integer() else round(result, 6)

    def _unit_factor(self, source_unit: str, target_unit: str) -> float | None:
        pairs = {
            ('MWh', '万kW·h'): 0.1,
            ('MWh', '万kWh'): 0.1,
            ('kWh', '万kW·h'): 0.0001,
            ('kWh', '万kWh'): 0.0001,
            ('万kWh', '万kW·h'): 1.0,
            ('万kW·h', '万kWh'): 1.0,
            ('m', 'km'): 0.001,
            ('米', 'km'): 0.001,
            ('km', 'm'): 1000.0,
            ('千米', 'km'): 1.0,
            ('kW', 'MW'): 0.001,
            ('MW', 'kW'): 1000.0,
            ('kv', 'kV'): 1.0,
            ('kV', 'kv'): 1.0,
            ('根', '座'): 1.0,
            ('个', '座'): 1.0,
            ('座', '个'): 1.0,
            ('m3', 'm³'): 1.0,
            ('m³', 'm3'): 1.0,
            ('m2', '㎡'): 1.0,
            ('㎡', 'm2'): 1.0,
        }
        return pairs.get((source_unit, target_unit))
