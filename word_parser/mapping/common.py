"""最终映射使用的通用辅助函数。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from word_parser.config.loader import ConfigLoader
from word_parser.output.presentation import ResultPresentationMixin
from word_parser.secondary.table_values.results import final_result_with_table_values


_COMBINED_TABLE_DISPLAY_FIELDS = {
    "windResourceCombined": {
        "windResourceTowerCodes": "测风塔编号",
        "windTowerLongitude": "测风塔经度",
        "windTowerLatitude": "测风塔纬度",
        "windMeasurementPeriod": "测风周期",
        "windFarmAirDensities": "该风电场的空气密度",
        "windResourceAirDensities": "高度对应的空气密度",
        "windResourceAirDensity10m": "10m高度空气密度",
        "windResourceAirDensity160m": "160m高度空气密度",
        "windResourceAirDensityRecords": "各测风塔各高度空气密度",
        "hubHeightAnnualAverageWindSpeed": "轮毂高度平均风速",
        "hubHeightWindPowerDensity": "轮毂高度平均风功率密度",
        "hubHeightAverageWindSpeedRecords": "各测风塔轮毂高度平均风速",
        "hubHeightAverageWindPowerDensityRecords": "各测风塔轮毂高度平均风功率密度",
        "windResourceMainWindDirections": "轮毂高度处的主风向",
        "windResourceSecondaryWindDirections": "轮毂高度处的次风向",
        "windResourceMainWindEnergyDirections": "轮毂高度处的主风能方向",
        "windResourceSecondaryWindEnergyDirections": "轮毂高度处的次风能方向",
        "representativeTurbulenceIntensity": "最大高度处代表性湍流强度",
        "windResourceTurbulenceIntensityRecords": "各测风塔各高度湍流强度",
        "windShearExponent": "综合风切变",
        "windResourceGenerationUses": "发电量计算是否使用",
    },
    "generationSingleTurbineAligned": {
        "generationSingleTurbineLabels": "标签",
        "generationSingleTurbineXMeters": "X（m）",
        "generationSingleTurbineYMeters": "Y（m）",
        "generationSingleTurbineZMeters": "Z（m）",
        "generationSingleTurbineHubHeights": "H（m）",
        "generationSingleTurbineTheoreticalEnergyMwh": "理论发电量",
        "generationSingleTurbineAverageWindSpeeds": "平均风速",
        "generationSingleTurbineWakeLossFactors": "尾流系数",
        "generationSingleTurbineWakeAdjustedEnergyMwh": "考虑尾流效应的发电量",
        "generationSingleTurbineFinalOnGridEnergyMwh": "最终上网电量",
        "generationSingleTurbineEquivalentHours": "等效小时数",
        "generationSingleTurbineAverageWakeReductionRates": "尾流效应导致的平均折减率",
    },
}

_TOWER_ROW_FIELDS = ("windResourceTowerCodes", "windTowerLongitude", "windTowerLatitude")
_WIND_ROW_FIELDS = (
    *_TOWER_ROW_FIELDS,
    "windMeasurementPeriod",
    "windResourceAirDensities",
    "windResourceMainWindDirections",
    "windResourceSecondaryWindDirections",
    "windResourceMainWindEnergyDirections",
    "windResourceSecondaryWindEnergyDirections",
    "windShearExponent",
)
_WIND_RECORD_FIELDS = (
    "hubHeightAverageWindSpeedRecords",
    "hubHeightAverageWindPowerDensityRecords",
    "windResourceTurbulenceIntensityRecords",
)


def _is_present(value: Any) -> bool:
    return value is not None and value not in ("", "---", "--")

def _flatten_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [part for item in value for part in _flatten_values(item)]
    return [value] if _is_present(value) else []

def _comparable(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().rstrip("'’").replace(" ", "")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def _values_covered(original: Any, aligned: list[Any]) -> bool:
    """要求原始值按相同的行顺序出现。"""
    remaining = iter(_comparable(value) for value in _flatten_values(aligned))
    for value in _flatten_values(original):
        comparable = _comparable(value)
        if not any(candidate == comparable for candidate in remaining):
            return False
    return True

def _combined_columns(result: dict[str, Any]):
    for section in result.get("sections") or []:
        for table in section.get("tables") or []:
            codes = _COMBINED_TABLE_DISPLAY_FIELDS.get(table.get("key"))
            columns = table.get("columns") or []
            rows = table.get("data") or []
            if not codes or not rows or columns != list(codes.values()):
                continue
            if any(not isinstance(row, list) or len(row) != len(codes) for row in rows):
                continue
            for index, code in enumerate(codes):
                yield section, table, code, columns[index], [row[index] for row in rows]

def _invalid_tower_metadata(code: str, value: Any) -> bool:
    """排除误识别为测风塔坐标的正文或表格标签。"""
    if code not in {"windTowerLongitude", "windTowerLatitude", "windMeasurementPeriod"}:
        return False
    values = _flatten_values(value)
    if not values:
        return False
    if code == "windMeasurementPeriod":
        return any(re.search(r"(?:19|20)\d{2}", str(item)) is None for item in values)
    return any(re.search(r"\d", str(item)) is None for item in values)

