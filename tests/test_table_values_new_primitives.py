"""二次抽取新增原语的回归测试。

覆盖：towers 模板展开、last 行、row_number 列、多列联合匹配、column_values、
cell_series、cell_ratio、sector_max、以及“测风塔”列名对“测风塔配置(m)”的精确优先匹配。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser_engine.tables.table_values import TableValueResolver


def _run(config: dict, tables: list[dict]) -> dict[str, dict]:
    resolver = TableValueResolver(config)
    result = {"sections": [{"name": "资源章节", "fields": [], "tables": tables}]}
    enhanced = resolver.enhance_result(result)
    fields = {}
    for section in enhanced.get("sections", []):
        for field in section.get("tableFields", []):
            fields[field["fieldCode"]] = field
    return fields


def _table(key, name, columns, data):
    return {"key": key, "name": name, "columns": columns, "data": data}


def test_row_last_and_row_number():
    config = {
        "rules": [
            {
                "field_code": "shear",
                "section": "资源章节",
                "source_table": {"name_patterns": [r"2\.5-16.*风切变"], "required_text": ["综合风切变"]},
                "row": {"type": "last"},
                "column": {"type": "row_number", "patterns": ["综合风切变", "综合值"]},
                "value_type": "number",
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表 2.5-16 2001#测风塔风切变指数计算成果表",
            ["高度(m)", "10m", "50m", "80m"],
            [["50", "0.177", "", ""], ["80", "0.174", "0.161", ""], ["综合风切变系数为 0.186（50m～140m）", "综合风切变系数为 0.186（50m～140m）", "", ""]],
        )
    ]
    fields = _run(config, tables)
    assert fields["shear"]["value"] == 0.186


def test_towers_expansion_and_compound_row():
    config = {
        "rules": [
            {
                "field_code": "speed{tower_clean}",
                "field_name": "{tower}平均风速",
                "section": "资源章节",
                "towers": ["0821#", "0822#"],
                "source_table": {"name_patterns": [r"平均风速.*风功率密度统计表"], "required_columns": ["项目", "年均"]},
                "row": {
                    "type": "label",
                    "match": [
                        {"column": ["测风塔"], "patterns": ["{tower}"]},
                        {"column": ["项目"], "patterns": ["风速"]},
                    ],
                },
                "column": {"aliases": ["年均", "平均"]},
                "value_type": "number",
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表",
            ["测风塔", "项目", "1", "12", "年均"],
            [["0821#", "风速", "6.2", "5.4", "6.42"], ["0821#", "风功率", "217", "206", "232"],
             ["0822#", "风速", "5.6", "5.1", "5.75"], ["0822#", "风功率", "151", "158", "163"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["speed0821"]["value"] == 6.42
    assert fields["speed0822"]["value"] == 5.75


def test_variables_expand_static_heights_with_towers():
    config = {
        "rules": [
            {
                "field_code": "power{tower_clean}{height_clean}",
                "field_name": "{tower}{height}平均风功率密度",
                "section": "资源章节",
                "towers": ["0821#", "0822#"],
                "variables": {
                    "height": {"values": ["120m-推算", "160m（推算）"]},
                },
                "source_table": {
                    "name_patterns": ["{tower}.*平均风速.*风功率密度统计表"],
                    "name_match_content": True,
                    "required_columns": ["高度", "风功率密度"],
                    "required_text": ["{tower}"],
                },
                "row": {"type": "label", "column": ["高度"], "patterns": ["{height}"]},
                "column": {"aliases": ["风功率密度"]},
                "value_type": "number",
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表2.6-2 0821#测风塔平均风速、风功率密度统计表",
            ["高度", "风速", "风功率密度"],
            [["120m-推算", "6.1", "220"], ["160m（推算）", "6.6", "280"]],
        ),
        _table(
            "k2",
            "表2.6-3 0822#测风塔平均风速、风功率密度统计表",
            ["高度", "风速", "风功率密度"],
            [["120m-推算", "5.9", "200"], ["160m（推算）", "6.4", "260"]],
        ),
    ]
    fields = _run(config, tables)
    assert fields["power0821120m推算"]["value"] == 220
    assert fields["power0821160m推算"]["value"] == 280
    assert fields["power0822120m推算"]["value"] == 200
    assert fields["power0822160m推算"]["value"] == 260


def test_variables_can_be_discovered_from_table_column():
    config = {
        "rules": [
            {
                "field_code": "speed{height_clean}",
                "field_name": "{height}风速",
                "section": "资源章节",
                "variables": {
                    "height": {
                        "from_table": {
                            "source_table": {
                                "name_patterns": ["平均风速.*风功率密度统计表"],
                                "required_columns": ["高度", "风速"],
                            },
                            "column": {"aliases": ["高度"]},
                            "value_pattern": r"\d+\s*m(?:[-－]?\s*推算|（推算）)?",
                        }
                    }
                },
                "source_table": {"name_patterns": ["平均风速.*风功率密度统计表"], "required_columns": ["高度", "风速"]},
                "row": {"type": "label", "column": ["高度"], "patterns": ["{height}"]},
                "column": {"aliases": ["风速"]},
                "value_type": "number",
            }
        ]
    }
    tables = [_table("k", "表2.6-2 测风塔平均风速、风功率密度统计表", ["高度", "风速"], [["90m", "5.6"], ["120m-推算", "6.2"]])]
    fields = _run(config, tables)
    assert fields["speed90m"]["value"] == 5.6
    assert fields["speed120m推算"]["value"] == 6.2


def test_variables_from_table_can_use_rendered_tower_placeholder():
    config = {
        "rules": [
            {
                "field_code": "speed{tower_clean}{height_clean}",
                "section": "资源章节",
                "towers": ["0821#", "0822#"],
                "variables": {
                    "height": {
                        "from_table": {
                            "source_table": {
                                "name_patterns": ["{tower}.*平均风速.*风功率密度统计表"],
                                "name_match_content": True,
                                "required_columns": ["高度", "风速"],
                                "required_text": ["{tower}"],
                            },
                            "column": {"aliases": ["高度"]},
                            "value_pattern": r"\d+\s*m(?:[-－]?\s*推算|（推算）)?",
                        }
                    }
                },
                "source_table": {
                    "name_patterns": ["{tower}.*平均风速.*风功率密度统计表"],
                    "name_match_content": True,
                    "required_columns": ["高度", "风速"],
                    "required_text": ["{tower}"],
                },
                "row": {"type": "label", "column": ["高度"], "patterns": ["{height}"]},
                "column": {"aliases": ["风速"]},
                "value_type": "number",
            }
        ]
    }
    tables = [
        _table("t1", "表2.6-2 0821#测风塔平均风速、风功率密度统计表", ["高度", "风速"], [["90m", "5.6"]]),
        _table("t2", "表2.6-3 0822#测风塔平均风速、风功率密度统计表", ["高度", "风速"], [["120m-推算", "6.2"]]),
    ]
    fields = _run(config, tables)
    assert "speed082190m" in fields
    assert "speed0822120m推算" in fields
    assert "speed082290m" not in fields


def test_column_values_and_exact_column_preference():
    config = {
        "rules": [
            {
                "field_code": "towers",
                "section": "资源章节",
                "operation": "column_values",
                "source_table": {"name_patterns": ["测风塔基本情况表"], "required_columns": ["测风塔"]},
                "column": {"aliases": ["测风塔"]},
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表2.4.1-1 测风塔基本情况表",
            ["测风塔", "塔高（m）", "测风塔配置(m)"],
            [["0821#", "90", "风速：90/80"], ["0822#", "90", "风速：90/80"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["towers"]["value"] == ["0821#", "0822#"]


def test_column_values_can_filter_by_value_pattern():
    config = {
        "rules": [
            {
                "field_code": "towers",
                "section": "资源章节",
                "operation": "column_values",
                "source_table": {"name_patterns": ["测风塔基本情况表"], "required_columns": ["测风塔"]},
                "column": {"aliases": ["测风塔"]},
                "value_pattern": r"[A-Za-z0-9]{2,8}#",
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表2.4.1-1 测风塔基本情况表",
            ["测风塔", "塔高（m）"],
            [["7123#", "160"], ["数据通道", ""], ["Speed 160 m A", ""], ["6601#", "120"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["towers"]["value"] == ["7123#", "6601#"]


def test_sector_max():
    config = {
        "rules": [
            {
                "field_code": "maxDir",
                "section": "资源章节",
                "operation": "sector_max",
                "source_table": {"name_patterns": [r"风向和风能分布统计"], "required_columns": ["测风塔", "扇区"]},
                "tower": {"patterns": ["0821#"]},
                "tower_column": {"aliases": ["测风塔"]},
                "metric_column": {"aliases": ["扇区"]},
                "metric": {"patterns": ["风向", "风速"]},
                "label": {"patterns": ["扇区"]},
            }
        ]
    }
    tables = [
        _table(
            "k",
            "表2.5.3.3-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）",
            ["测风塔", "扇区", "N", "NNE", "S", "NNW"],
            [["0821#", "风向（%）", "7.25", "3.61", "11.68", "12.23"],
             ["0821#", "风功率（%）", "5.8", "1.58", "12.65", "15.07"],
             ["0821#", "扇区", "S", "SSW", "NW", "NNW"],
             ["0821#", "风向（%）", "11.68", "7.26", "10.63", "12.23"],
             ["0821#", "风功率（%）", "12.65", "8.35", "14.44", "15.07"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["maxDir"]["value"] == "NNW"


def test_cell_series_extracts_finance_year_columns():
    config = {
        "rules": [
            {
                "field_code": "materialYears",
                "section": "资源章节",
                "operation": "cell_series",
                "source_table": {"name_patterns": ["总成本费用估算表"], "required_columns": ["项目", "第1年"]},
                "row": {"type": "label", "column": "项目", "aliases": ["材料费"]},
                "columns": [{"name": f"第{index}年", "aliases": [f"第{index}年"]} for index in range(1, 4)],
                "value_type": "number",
                "unit": "万元",
            }
        ]
    }
    tables = [
        _table(
            "cost",
            "附表3：总成本费用估算表（人民币单位：万元）",
            ["项目", "合计", "第1年", "第2年", "第3年"],
            [["材料费", "60", "10", "20", "30"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["materialYears"]["value"] == {"第1年": 10, "第2年": 20, "第3年": 30}


def test_cell_ratio_calculates_insurance_rate():
    config = {
        "rules": [
            {
                "field_code": "insuranceRate",
                "section": "资源章节",
                "operation": "cell_ratio",
                "source_table": {"name_patterns": ["总成本费用估算表"], "required_columns": ["项目", "合计"]},
                "numerator": {
                    "row": {"type": "label", "column": "项目", "aliases": ["保险费"]},
                    "column": {"aliases": ["合计"]},
                },
                "denominator": {
                    "row": {"type": "label", "column": "项目", "aliases": ["固定资产原值"]},
                    "column": {"aliases": ["合计"]},
                },
                "precision": 3,
                "unit": "%",
            }
        ]
    }
    tables = [
        _table(
            "cost",
            "附表3：总成本费用估算表（人民币单位：万元）",
            ["项目", "合计"],
            [["固定资产原值", "50000"], ["保险费", "150"]],
        )
    ]
    fields = _run(config, tables)
    assert fields["insuranceRate"]["value"] == 0.3
    assert fields["insuranceRate"]["unit"] == "%"
