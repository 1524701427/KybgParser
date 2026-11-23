"""用已保存的报告结果检查二次抽取后能否从映射反推字段和关联表行。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from word_parser.application.api import enhance_parse_result
from word_parser.config.loader import ConfigLoader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS = PROJECT_ROOT / "data" / "predictions"
WIND_COLUMNS = {
    "windResourceTowerCodes": "测风塔编号",
    "windTowerLongitude": "测风塔经度",
    "windTowerLatitude": "测风塔纬度",
    "windMeasurementPeriod": "测风周期",
    "windResourceAirDensities": "高度对应的空气密度",
    "windResourceMainWindDirections": "轮毂高度处的主风向",
    "windResourceSecondaryWindDirections": "轮毂高度处的次风向",
    "windResourceMainWindEnergyDirections": "轮毂高度处的主风能方向",
    "windResourceSecondaryWindEnergyDirections": "轮毂高度处的次风能方向",
    "windShearExponent": "综合风切变",
}
RECORD_COLUMNS = {
    "hubHeightAverageWindSpeedRecords": "各测风塔轮毂高度平均风速",
    "hubHeightAverageWindPowerDensityRecords": "各测风塔轮毂高度平均风功率密度",
    "windResourceTurbulenceIntensityRecords": "各测风塔各高度湍流强度",
}


def _records(value):
    if isinstance(value, list):
        for item in value:
            yield from _records(item)
    elif isinstance(value, dict):
        yield value


def test_saved_reports_reconstruct_mapped_fields_and_related_rows(tmp_path):
    output_codes = ConfigLoader(PROJECT_ROOT / "configs").load_yaml("output_schema.yaml")["output_field_codes"]
    reports = sorted(PREDICTIONS.glob("*_result.json"))
    if not reports:
        pytest.skip("仓库未包含 data/predictions 中的本地报告产物；有样本时执行重建检查")

    for number, report in enumerate(reports):
        result_path = tmp_path / f"report_{number}_result.json"
        mapped_path = tmp_path / f"report_{number}_mapped.json"
        result_path.write_bytes(report.read_bytes())
        mapped_path.write_bytes(report.with_name(report.name.replace("_result.json", "_mapped.json")).read_bytes())
        parsed = enhance_parse_result({
            "mapped": json.loads(mapped_path.read_text(encoding="utf-8")),
            "outputFiles": {"result": str(result_path), "mapped": str(mapped_path)},
        }, config_root=PROJECT_ROOT / "configs", config_path=PROJECT_ROOT / "configs" / "table_field_extractors.yaml")
        result, mapped = parsed["result"], parsed["mapped"]
        assert len(mapped) == len(set(output_codes.values()))
        assert json.loads(result_path.read_text(encoding="utf-8")) == result
        assert json.loads(mapped_path.read_text(encoding="utf-8")) == mapped

        tables = {}
        for section in result["sections"]:
            for field in section.get("fields", []):
                code = field.get("fieldCode")
                if code in output_codes:
                    assert mapped[f"${{{output_codes[code]}}}"] == field.get("value"), (report.name, code)
            for table in section.get("tables", []):
                code = table.get("key")
                tables[code] = table
                if code in output_codes:
                    assert mapped[f"${{{output_codes[code]}}}"]["data"] == table.get("data"), (report.name, code)

        wind = tables["windResourceCombined"]
        wind_headers = wind["columns"]
        tower_codes = [row[wind_headers.index("测风塔编号")] for row in wind["data"]]
        for code, column in WIND_COLUMNS.items():
            expected = [row[wind_headers.index(column)] for row in wind["data"]]
            assert mapped[f"${{{output_codes[code]}}}"] == expected, (report.name, code)
            assert len(expected) == len(tower_codes)

        for code, column in RECORD_COLUMNS.items():
            mapped_records = Counter(json.dumps(item, ensure_ascii=False, sort_keys=True)
                                     for item in _records(mapped[f"${{{output_codes[code]}}}"]))
            table_records = Counter()
            for row in wind["data"]:
                for record in _records(row[wind_headers.index(column)]):
                    assert record["tower_code"] == row[wind_headers.index("测风塔编号")]
                    table_records[json.dumps(record, ensure_ascii=False, sort_keys=True)] += 1
            assert all(mapped_records[record] >= count for record, count in table_records.items())

        generation = tables.get("generationSingleTurbineAligned")
        if generation:
            for code, name in output_codes.items():
                if code.startswith("generationSingleTurbine") and code != "generationSingleTurbineAligned":
                    column = {
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
                    }.get(code)
                    if column:
                        index = generation["columns"].index(column)
                        assert mapped[f"${{{name}}}"] == [row[index] for row in generation["data"]], (report.name, code)

        for placeholder in ("${material_cost}", "${repair_cost}"):
            if mapped[placeholder] is None:
                continue
            headers, values = mapped[placeholder]
            assert headers == ["合计", *(f"第{year}年" for year in range(1, 22))]
            assert len(values) == 22
            if all(value is not None for value in values):
                assert abs(sum(values[1:]) - values[0]) < 0.01
