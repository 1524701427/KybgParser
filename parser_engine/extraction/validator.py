"""字段结果校验器。"""

from __future__ import annotations

from parser_engine.document.ast.evidence import ParsedField
from parser_engine.core.logger import logger


class Validator:
    """范围、必填和单位校验器。"""

    def __init__(self, field_configs: dict[str, dict]):
        """初始化校验器。

        Args:
            field_configs: 字段配置。
        """
        self.field_configs = field_configs

    def validate(self, fields: dict[str, ParsedField]) -> dict[str, ParsedField]:
        """校验字段结果。

        Args:
            fields: 字段结果。

        Returns:
            dict[str, ParsedField]: 校验后的字段结果。
        """
        for code, config in self.field_configs.items():
            if code not in fields:
                fields[code] = ParsedField(
                    field_code=code,
                    field_name=config.get("name", code),
                    value=None,
                    status="MISSING",
                    messages=["未抽取到字段值"],
                )
                continue
            self._validate_range(fields[code], config)
            self._validate_unit(fields[code], config)
        logger.info("字段校验完成")
        return fields

    def _validate_range(self, field: ParsedField, config: dict) -> None:
        """校验数值范围。"""
        validators = config.get("validators") or {}
        values = field.normalized_value if isinstance(field.normalized_value, list) else [field.normalized_value]
        numeric_values = [value for value in values if isinstance(value, (int, float))]
        if not numeric_values:
            return
        min_value = validators.get("min")
        max_value = validators.get("max")
        for value in numeric_values:
            if min_value is not None and value < min_value:
                field.status = "WARNING"
                field.messages.append(f"字段值低于最小范围：{min_value}")
            if max_value is not None and value > max_value:
                field.status = "WARNING"
                field.messages.append(f"字段值高于最大范围：{max_value}")

    def _validate_unit(self, field: ParsedField, config: dict) -> None:
        """校验单位。"""
        standard_unit = config.get("standard_unit")
        if standard_unit and field.unit and field.unit != standard_unit:
            field.status = "WARNING"
            field.messages.append(f"单位与标准单位不一致：标准={standard_unit}，实际={field.unit}")
