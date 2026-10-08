"""表内字段二次抽取测试。"""

from __future__ import annotations

import json

from parser_engine.tables.table_values import TableValueResolver, enhance_result_file
from parser_engine.tables.table_values import final_result_with_table_values


def test_table_value_resolver_extracts_cell_and_max_row_label():
    """验证二次抽取可按行列取值，也可按最大值返回同行标签。"""
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financialIndicatorSummary",
                        "name": "附表 1：财务指标汇总表",
                        "columns": ["序号", "项目", "单位", "数值"],
                        "data": [[1, "流动资金", "万元", "123.5"], [2, "总投资", "万元", "8000"]],
                    }
                ],
            },
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceDirectionEnergyFrequency",
                        "name": "表2.6-16 测风塔风向风能频率统计成果表",
                        "columns": ["风向", "0822#", "0823#"],
                        "data": [["N", 10, 6], ["NE", 13, 8], ["E", 7, 12]],
                    }
                ],
            },
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "financeWorkingCapitalValue",
                "field_name": "流动资金数值",
                "section": "财务",
                "source_table": {"key": "financialIndicatorSummary"},
                "row": {"type": "label", "column": "项目", "aliases": ["流动资金"]},
                "column": {"aliases": ["数值"]},
                "value_type": "number",
            },
            {
                "field_code": "windDirectionMax0822",
                "field_name": "0822#最大风能频率对应风向",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0822#"]},
                "label_column": {"aliases": ["风向"]},
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    finance = next(section for section in enhanced["sections"] if section["name"] == "财务")
    resource = next(section for section in enhanced["sections"] if section["name"] == "资源章节")

    assert finance["tableFields"][0]["value"] == 123.5
    assert finance["tableFields"][0]["source"]["column"] == "数值"
    assert resource["tableFields"][0]["value"] == "NE"
    assert resource["tableFields"][0]["maxValue"] == 13


def test_filter_table_projection_extracts_equipment_rows_by_alias():
    """验证设备概算表可按别名筛选行，并投影固定列。"""
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentEquipmentInstallation",
                        "name": "设备及安装工程概算表",
                        "columns": ["序号", "项目名称", "规格型号", "单位", "数量", "设备购置费（万元）"],
                        "data": [
                            ["1", "无线对讲机", "5W", "台", "12", "3.5"],
                            ["2", "蓄电池组", "200Ah", "组", "1", "8.0"],
                            ["3", "蓄电池", "100Ah", "只", "104", "20.0"],
                            ["4", "无关设备", "X", "套", "1", "2.0"],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "investmentEquipmentInstallationDeviceList",
                "table_name": "设备及安装工程概算表-设备清单",
                "section": "技经概算",
                "operation": "filter_table_projection",
                "source_table": {"key": "investmentEquipmentInstallation"},
                "match_column_name": "设备类别",
                "match_columns": ["项目名称", "规格型号"],
                "strict": False,
                "columns": [
                    {"name": "名称", "aliases": ["项目名称"]},
                    {"name": "规格", "aliases": ["规格型号"]},
                    {"name": "单位", "aliases": ["单位"]},
                    {"name": "数量", "aliases": ["数量"]},
                    {"name": "设备费/设备购置费", "aliases": ["设备购置费"]},
                ],
                "items": [
                    {"name": "蓄电池", "aliases": ["蓄电池"]},
                    {"name": "通信电池屏/通信动环境监控系统屏/蓄电池组", "aliases": ["通信电池屏", "蓄电池组"]},
                    {"name": "对讲机/无线对讲机", "aliases": ["对讲机", "无线对讲机"]},
                ],
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    derived = enhanced["sections"][0]["derivedTables"][0]

    assert derived["columns"] == ["设备类别", "名称", "规格", "单位", "数量", "设备费/设备购置费"]
    assert derived["data"] == [
        ["对讲机/无线对讲机", "无线对讲机", "5W", "台", "12", "3.5"],
        ["通信电池屏/通信动环境监控系统屏/蓄电池组", "蓄电池组", "200Ah", "组", "1", "8.0"],
        ["蓄电池", "蓄电池", "100Ah", "只", "104", "20.0"],
    ]


def test_filter_table_projection_distinguishes_plain_and_complete_set_equipment():
    """风机/主变普通单价与含配套设备的整套单价必须互斥分类。"""
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentEquipmentInstallation",
                        "name": "设备及安装工程概算表",
                        "columns": ["项目名称", "单价（元）"],
                        "data": [
                            ["风电机组", 100],
                            ["风电机组（含塔筒）", 120],
                            ["主变压器", 200],
                            ["主变压器及中性点设备", 230],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "equipmentUnitPrices",
                "table_name": "设备单价",
                "section": "技经概算",
                "operation": "filter_table_projection",
                "source_table": {"key": "investmentEquipmentInstallation"},
                "match_columns": ["项目名称"],
                "columns": [{"name": "单价", "aliases": ["单价（元）"]}],
                "items": [
                    {"name": "风机单价", "aliases": ["风电机组"], "exclude_aliases": ["塔筒"]},
                    {"name": "风机（含塔筒）单价", "all_aliases": ["风电机组", "塔筒"]},
                    {"name": "主变单价", "aliases": ["主变压器"], "exclude_aliases": ["中性点设备"]},
                    {"name": "主变整套单价", "all_aliases": ["主变压器", "中性点设备"]},
                ],
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    derived = enhanced["sections"][0]["derivedTables"][0]

    assert derived["data"] == [
        ["风机单价", 100],
        ["风机（含塔筒）单价", 120],
        ["主变单价", 200],
        ["主变整套单价", 230],
    ]


def test_investment_extracts_nine_equipment_unit_price_fields():
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentEquipmentInstallation",
                        "name": "设备及安装工程概算表",
                        "columns": ["名称及规格", "单位", "数量", "设备费(万元)"],
                        "data": [
                            ["风电机组", "台", 20, 100],
                            ["风电机组（含塔筒）", "台", 20, 120],
                            ["主变压器", "台", 1, 200],
                            ["主变压器及中性点设备", "套", 1, 230],
                            ["塔筒（架）", "套", 20, 30],
                            ["预应力锚栓", "套", 20, 8],
                            ["带在线式UPS电源/箱变", "台", 20, 15],
                            ["电缆分支箱", "台", 5, 3],
                            ["隔离开关", "组", 6, 2],
                            ["避雷器 YH5W5", "组", 3, 4],
                            ["主变中性点设备", "套", 1, 12],
                            ["线路测控装置", "套", 2, 5],
                            ["线路保护测控装置", "套", 2, 6],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}
    batch_fields = [field for field in enhanced["sections"][0]["tableFields"] if field.get("operation") == "cell_items"]

    assert len(batch_fields) == 89
    assert len({field["fieldCode"] for field in batch_fields}) == 89

    expected = {
        "windTurbineUnitPrice": 100,
        "turbineTowerUnitPrice": 120,
        "mainTransformerUnitPrice": 200,
        "transformerCompleteSetUnitPrice": 230,
        "windTurbineTowerUnitPrice": 30,
        "anchorBoltUnitPrice": 8,
        "containerSubstationUnitPrice": 15,
        "cableBranchBoxUnitPrice": 3,
        "disconnectorSwitchUnitPrice": 2,
        "surgeArresterHy5wzUnitPrice": 4,
        "mainTransformerNeutralEquipmentUnitPrice": 12,
        "lineMeasurementControlDeviceUnitPrice": 5,
        "lineProtectionMeasurementControlDeviceUnitPrice": 6,
    }
    for field_code, value in expected.items():
        assert fields[field_code]["status"] == "OK"
        assert fields[field_code]["value"] == value
        assert fields[field_code]["unit"] == "万元"


def test_investment_equipment_price_converts_explicit_yuan_header_to_wan_yuan():
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentEquipmentInstallation",
                        "name": "设备及安装工程概算表",
                        "columns": ["名称", "单位", "数量", "设备费（元）"],
                        "data": [["避雷器HY5WZ", "组", 1, 37000]],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["surgeArresterHy5wzUnitPrice"]["value"] == 3.7
    assert fields["surgeArresterHy5wzUnitPrice"]["unit"] == "万元"


def test_filter_table_projection_falls_back_to_equipment_content_when_table_key_is_stale():
    """验证设备概算表 key 错归时，可按“第二部分设备及安装工程”内容兜底定位。"""
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentOriginalTable001",
                        "name": "主要技术经济指标表",
                        "columns": ["序号", "项目名称及规格", "单位", "数量", "单价（元）", "合价（万元）", "合计   （万元）", "col_7"],
                        "data": [
                            ["", "", "", "", "设备购置费", "安装工程费", "设备购置费", "安装工程费"],
                            ["", "第二部分 设备及安装工程", "", "", "", "", "", "48826.4"],
                            ["1", "风电机组", "项", "1", "315425000", "", "", "31542.5"],
                            ["", "无线对讲机", "台", "12", "300", "", "", "3.6"],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "investmentEquipmentInstallationDeviceList",
                "table_name": "设备及安装工程概算表-设备清单",
                "section": "技经概算",
                "operation": "filter_table_projection",
                "source_table": {
                    "key": "investmentEquipmentInstallation",
                    "name_patterns": ["设备及安装工程概算表", r"第二部分\s*设备及安装工程"],
                    "name_match_content": True,
                    "required_columns": [
                        {"aliases": ["项目名称及规格", "项目名称", "名称"]},
                        {"aliases": ["单位"]},
                        {"aliases": ["数量"]},
                    ],
                },
                "match_column_name": "设备类别",
                "match_columns": ["项目名称及规格"],
                "strict": False,
                "columns": [
                    {"name": "名称", "aliases": ["项目名称及规格"]},
                    {"name": "规格", "aliases": ["规格型号"]},
                    {"name": "单位", "aliases": ["单位"]},
                    {"name": "数量", "aliases": ["数量"]},
                    {"name": "设备费/设备购置费", "aliases": ["设备购置费", "合计   （万元）", "合计"], "offset": 1, "offset_when_source_matches": ["合计"]},
                ],
                "items": [
                    {"name": "风电机组", "aliases": ["风电机组"]},
                    {"name": "对讲机/无线对讲机", "aliases": ["对讲机", "无线对讲机"]},
                ],
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    derived = enhanced["sections"][0]["derivedTables"][0]

    assert derived["status"] == "OK"
    assert derived["source"]["tableKey"] == "investmentOriginalTable001"
    assert derived["data"] == [
        ["风电机组", "风电机组", None, "项", "1", "31542.5"],
        ["对讲机/无线对讲机", "无线对讲机", None, "台", "12", "3.6"],
    ]


def test_enhance_result_file_merges_result_and_details(tmp_path):
    input_path = tmp_path / "sample_result.json"
    output_path = tmp_path / "sample_result_final.json"
    details_path = tmp_path / "sample_table_values_details.json"
    config_path = tmp_path / "table_field_extractors.yaml"
    input_path.write_text(
        json.dumps(
            {
                "filePath": "sample.docx",
                "sections": [
                    {
                        "name": "财务",
                        "fields": [],
                        "tables": [
                            {
                                "key": "financialIndicatorSummary",
                                "name": "附表 1：财务指标汇总表",
                                "columns": ["项目", "单位", "数值"],
                                "data": [["流动资金", "万元", "123.5"]],
                            },
                            {
                                "key": "windResourceDirectionEnergyFrequency",
                                "name": "风向风能频率统计成果表",
                                "columns": ["风向", "0822#"],
                                "data": [["N", 10], ["NE", 13]],
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        """
version: 2
rules:
  - field_code: financeWorkingCapitalValue
    field_name: 流动资金数值
    section: 财务
    source_table: {key: financialIndicatorSummary}
    row: {type: label, column: 项目, aliases: ['流动资金']}
    column: {aliases: ['数值']}
    value_type: number
  - field_code: windDirectionMax0822
    field_name: 0822#最大风能频率对应风向
    section: 财务
    operation: max_row_label
    source_table: {key: windResourceDirectionEnergyFrequency}
    value_column: {aliases: ['0822#']}
    label_column: {aliases: ['风向']}
  - table_code: financialIndicatorSummaryCopy
    table_name: 财务指标汇总表原表
    section: 财务
    operation: copy_table
    source_table: {key: financialIndicatorSummary}
""".strip(),
        encoding="utf-8",
    )

    enhance_result_file(input_path, output_path, config_path, details_path)
    result_json = json.loads(output_path.read_text(encoding="utf-8"))
    details_json = json.loads(details_path.read_text(encoding="utf-8"))
    result_text = json.dumps(result_json, ensure_ascii=False)

    assert result_json == {
        "filePath": "sample.docx",
        "sections": [
            {
                "name": "财务",
                "fields": [
                    {
                        "fieldCode": "financeWorkingCapitalValue",
                        "name": "流动资金数值",
                        "value": 123.5,
                        "unit": None,
                    },
                    {
                        "fieldCode": "windDirectionMax0822",
                        "name": "0822#最大风能频率对应风向",
                        "value": "NE",
                        "unit": None,
                    },
                ],
                "tables": [
                    {
                        "key": "financialIndicatorSummary",
                        "name": "附表 1：财务指标汇总表",
                        "columns": ["项目", "单位", "数值"],
                        "data": [["流动资金", "万元", "123.5"]],
                    },
                    {
                        "key": "windResourceDirectionEnergyFrequency",
                        "name": "风向风能频率统计成果表",
                        "columns": ["风向", "0822#"],
                        "data": [["N", 10], ["NE", 13]],
                    },
                    {
                        "key": "financialIndicatorSummaryCopy",
                        "tableCode": "financialIndicatorSummaryCopy",
                        "name": "财务指标汇总表原表",
                        "tableRef": {
                            "section": "财务",
                            "tableKey": "financialIndicatorSummary",
                            "tableName": "附表 1：财务指标汇总表",
                        },
                        "columns": ["项目", "单位", "数值"],
                        "data": [["流动资金", "万元", "123.5"]],
                    },
                ],
            }
        ],
    }
    assert '"source":' not in result_text
    assert '"trace":' not in result_text
    table_value_details = details_json["tableValueExtraction"]
    assert table_value_details["sections"][0]["tableFields"][0]["source"]["tableKey"] == "financialIndicatorSummary"
    assert table_value_details["sections"][0]["derivedTables"][0]["source"]["tableKey"] == "financialIndicatorSummary"


def test_final_result_keeps_precise_electrical_primary_fields_when_secondary_is_noisier():
    enhanced = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [
                    {
                        "fieldCode": "electricalPrimaryTransformerSpec",
                        "name": "主变压器型号、规格及技术数据",
                        "value": "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV，接线组别：YN，d11",
                        "unit": None,
                    },
                    {
                        "fieldCode": "electricalPrimaryExternalPowerTransformerSpec",
                        "name": "站外电源变压器型号、规格及技术数据",
                        "value": None,
                        "unit": None,
                    },
                ],
                "tables": [],
                "tableFields": [
                    {
                        "fieldCode": "electricalPrimaryTransformerSpec",
                        "fieldName": "主变压器型号、规格及技术数据",
                        "value": "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV，短路阻抗：，U%=10.5，接线组别：YN，d11，智能控制柜",
                        "unit": None,
                        "status": "OK",
                    },
                    {
                        "fieldCode": "electricalPrimaryExternalPowerTransformerSpec",
                        "fieldName": "站外电源变压器型号、规格及技术数据",
                        "value": "S13-315/10.5 10.5±2×2.5%/0.4kV",
                        "unit": None,
                        "status": "OK",
                    },
                ],
            }
        ]
    }

    final = final_result_with_table_values(enhanced)
    fields = {field["fieldCode"]: field["value"] for field in final["sections"][0]["fields"]}

    assert fields["electricalPrimaryTransformerSpec"] == "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV，接线组别：YN，d11"
    assert fields["electricalPrimaryExternalPowerTransformerSpec"] == "S13-315/10.5 10.5±2×2.5%/0.4kV"


def test_table_value_resolver_projects_table_and_keeps_nil_on_missing_column():
    """验证子表投影和 NIL 机制，缺列时不乱取其它列。"""
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "singleTurbineAnnualEnergy",
                        "name": "WTG204-6250 方案各风电机组发电量成果表",
                        "columns": ["标签", "X (m)", "Y (m)", "上网电量 (兆瓦时/年)"],
                        "data": [["F01", 1, 2, 1000]],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "generationProjection",
                "table_name": "发电量投影",
                "section": "发电量章节",
                "operation": "table_projection",
                "source_table": {"key": "singleTurbineAnnualEnergy"},
                "columns": [
                    {"name": "标签", "aliases": ["标签"]},
                    {"name": "上网电量", "aliases": ["上网电量"]},
                ],
            },
            {
                "field_code": "missingValue",
                "field_name": "缺失字段",
                "section": "发电量章节",
                "source_table": {"key": "singleTurbineAnnualEnergy"},
                "row": {"type": "label", "aliases": ["不存在的行"]},
                "column": {"aliases": ["不存在的列"]},
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    section = enhanced["sections"][0]

    assert section["derivedTables"][0]["columns"] == ["标签", "上网电量"]
    assert section["derivedTables"][0]["data"] == [["F01", 1000]]
    assert section["tableFields"][0]["status"] == "NIL"
    assert section["tableFields"][0]["nilReason"] == "row_not_found"


def test_table_value_projection_can_select_duplicate_column_by_occurrence():
    """验证同名列可按出现顺序投影，避免两个“年发电量”列互相冲突。"""
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "singleTurbineAnnualEnergy",
                        "name": "表5.3-2 推荐机型单机发电量统计表",
                        "columns": ["风机编号", "年发电量 [万kW·h]", "年发电量 [万kW·h]", "利用小时 [h]"],
                        "data": [["H07", 1602.9, 1118.0, 2033]],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "generationSingleTurbineAnnualEnergyProjected",
                "table_name": "单台风机发电量明细表投影",
                "section": "发电量章节",
                "operation": "table_projection",
                "source_table": {"key": "singleTurbineAnnualEnergy"},
                "columns": [
                    {"name": "风机编号", "aliases": ["风机编号"]},
                    {"name": "年发电量", "aliases": ["年发电量"], "occurrence": 0},
                    {"name": "年发电量（折减后）", "aliases": ["年发电量"], "occurrence": 1},
                    {"name": "利用小时", "aliases": ["利用小时"]},
                ],
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    projected = enhanced["sections"][0]["derivedTables"][0]

    assert projected["status"] == "OK"
    assert projected["columns"] == ["风机编号", "年发电量", "年发电量（折减后）", "利用小时"]
    assert projected["data"] == [["H07", 1602.9, 1118.0, 2033]]


def test_generation_projection_can_use_generation_summary_table_with_detail_columns():
    """验证发电量成果表即使归为 generationSummary，也能按明细列投影。"""
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "generationSummary",
                        "name": "表5.3-1 风电场发电量计算成果表",
                        "columns": [
                            "标签",
                            "X (m)",
                            "Y (m)",
                            "Z (m)",
                            "年发电量 [万kW·h]",
                            "年上网电量 [万kW·h]",
                            "等效小时数 [h]",
                            "尾流效应导致的平均折减率(%)",
                        ],
                        "data": [["F01", 1, 2, 3, 30000, 27093.92, 1806, 75.6]],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    section = enhanced["sections"][0]
    projected = next(table for table in section["derivedTables"] if table["key"] == "generationSingleTurbineAnnualEnergyProjected")

    assert projected["status"] == "OK"
    assert projected["data"][0][0] == "F01"
    assert projected["data"][0][9] == 27093.92
    assert projected["data"][0][16] == 1806
    assert projected["data"][0][18] == 75.6


def test_generation_secondary_columns_extract_single_turbine_metrics_and_convert_energy():
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "singleTurbineAnnualEnergy",
                        "name": "表5.3-2 推荐机型单机发电量统计表",
                        "columns": [
                            "风机编号",
                            "X（m）",
                            "Y（m）",
                            "Z（m）",
                            "H（m）",
                            "年发电量(万kW·h)",
                            "平均风速（m/s）",
                            "尾流系数（%）",
                            "考虑尾流效应的发电量 [万kW·h]",
                            "年上网电量 [万kW·h]",
                            "等效小时数（h）",
                            "尾流效应导致的平均折减率（%）",
                        ],
                        "data": [
                            ["F01", 36523976, 3857371, 1280, 160, 2850.1, 6.32, 95.5, 2709.392, 2600.2, 2107.1, -1.9],
                            ["F02", 36523977, 3857372, 1285, 160, 2800.0, 6.28, 94.8, 2680.1, 2550.0, 2080, -2.1],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["generationSingleTurbineLabels"]["value"] == ["F01", "F02"]
    assert fields["generationSingleTurbineXMeters"]["value"] == [36523976, 36523977]
    assert fields["generationSingleTurbineYMeters"]["value"] == [3857371, 3857372]
    assert fields["generationSingleTurbineZMeters"]["value"] == [1280, 1285]
    assert fields["generationSingleTurbineHubHeights"]["value"] == [160, 160]
    assert fields["generationSingleTurbineHubHeights"]["unit"] == "m"
    assert fields["generationSingleTurbineTheoreticalEnergyMwh"]["value"] == [28501, 28000]
    assert fields["generationSingleTurbineAverageWindSpeeds"]["value"] == [6.32, 6.28]
    assert fields["generationSingleTurbineAverageWindSpeeds"]["unit"] == "m/s"
    assert fields["generationSingleTurbineWakeLossFactors"]["value"] == [95.5, 94.8]
    assert fields["generationSingleTurbineWakeLossFactors"]["unit"] == "%"
    assert fields["generationSingleTurbineWakeAdjustedEnergyMwh"]["value"] == [27093.92, 26801]
    assert fields["generationSingleTurbineWakeAdjustedEnergyMwh"]["unit"] == "兆瓦时/年"
    assert fields["generationSingleTurbineFinalOnGridEnergyMwh"]["value"] == [26002, 25500]
    assert fields["generationSingleTurbineEquivalentHours"]["value"] == [2107.1, 2080]
    assert fields["generationSingleTurbineAverageWakeReductionRates"]["value"] == [-1.9, -2.1]


def test_generation_mwh_columns_are_not_multiplied_by_ten():
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "singleTurbineAnnualEnergy",
                        "name": "单台风机年上网电量计算成果表",
                        "columns": [
                            "标签",
                            "年发电量(兆瓦时/年)",
                            "考虑尾流效应的发电量（兆瓦时/年）",
                            "最终上网电量（兆瓦时/年）",
                        ],
                        "data": [["1", 14315.1, 14047.4, 105353.5]],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["generationSingleTurbineTheoreticalEnergyMwh"]["value"] == [14315.1]
    assert fields["generationSingleTurbineWakeAdjustedEnergyMwh"]["value"] == [14047.4]
    assert fields["generationSingleTurbineFinalOnGridEnergyMwh"]["value"] == [105353.5]


def test_generation_summary_extracts_recommended_scheme_units_and_values():
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "generationSummary",
                        "name": "表5.3-1 风电场工程推荐方案发电量计算表",
                        "columns": ["序号", "项目", "单位", "推荐方案"],
                        "data": [
                            [1, "装机容量", "MW", 200],
                            [2, "单机容量", "kW", 5000],
                            [3, "台数", "台", "30+7"],
                            [6, "年上网电量", "万kW·h", 47521.1],
                            [7, "年等效满负荷小时数", "h", 2376],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["generationInstalledCapacityUnit"]["value"] == "MW"
    assert fields["generationInstalledCapacityRecommended"]["value"] == 200
    assert fields["generationTurbineCapacityUnit"]["value"] == "kW"
    assert fields["generationTurbineCapacityRecommended"]["value"] == 5000
    assert fields["generationTurbineCountUnit"]["value"] == "台"
    assert fields["generationTurbineCountRecommended"]["value"] == "30+7"
    assert fields["generationAnnualOnGridEnergyUnit"]["value"] == "万kW·h"
    assert fields["generationAnnualOnGridEnergyRecommended"]["value"] == 47521.1
    assert fields["generationEquivalentHoursUnit"]["value"] == "h"
    assert fields["generationEquivalentFullLoadHoursRecommended"]["value"] == 2376


def test_table_value_resolver_can_sum_existing_fields():
    """验证二次抽取可从主 result 已有字段计算派生值。"""
    result = {
        "sections": [
            {
                "name": "集电线路",
                "fields": [
                    {"fieldCode": "doubleCircuitOverheadRouteLength", "value": 28.514, "unit": "km"},
                    {"fieldCode": "singleCircuitOverheadRouteLength", "value": 13.93, "unit": "km"},
                ],
                "tables": [],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "newOverheadLineLengthCalculated",
                "field_name": "新建架空线路长度",
                "section": "集电线路",
                "operation": "sum_fields",
                "source_fields": ["doubleCircuitOverheadRouteLength", "singleCircuitOverheadRouteLength"],
                "unit": "km",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "OK"
    assert field["value"] == 42.444


def test_table_value_resolver_merges_following_blank_name_rows():
    """验证设备参数可配置合并后续空名称续行。"""
    result = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalPrimaryEquipmentMaterial",
                        "name": "升压站电气一次主要设备材料工程量表",
                        "columns": ["序号", "名称", "型号、规格及技术数据", "单位", "数量"],
                        "data": [
                            [1.1, "主变压器", "三相双绕组油浸自冷式有载调压变压器", "台", 1],
                            ["", "", "型号：SZ20-100000/110", "", ""],
                            ["", "", "115±8×1.25%/37kV", "", ""],
                            [2.1, "GIS组合电器", "126kV", "个", 1],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "electricalPrimaryTransformerSpec",
                "section": "电气一次",
                "source_table": {"key": "electricalPrimaryEquipmentMaterial"},
                "row": {"type": "label", "column": "名称", "aliases": ["主变压器"]},
                "column": {"aliases": ["型号、规格及技术数据"]},
                "merge_following_rows": {"max_rows": 6},
                "value_type": "text",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "OK"
    assert field["value"] == "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV"


def test_table_value_resolver_extracts_electrical_primary_station_outgoing_line_counts():
    result = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalPrimaryStationScale",
                        "name": "表6.3-1 110kV升压站本期规模",
                        "columns": ["名称", "本期规模", "远期规模"],
                        "data": [
                            ["主变压器", "1台", "2台"],
                            ["110kV出线", "1回", "2回"],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)

    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}
    assert fields["electricalPrimaryCurrentOutgoingLineCount"]["value"] == 1
    assert fields["electricalPrimaryCurrentOutgoingLineCount"]["unit"] == "回"
    assert fields["electricalPrimaryFutureOutgoingLineCount"]["value"] == 2
    assert fields["electricalPrimaryFutureOutgoingLineCount"]["unit"] == "回"


def test_electrical_primary_extracts_transformer_detail_fields():
    result = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalPrimaryStationScale",
                        "name": "表6.3-1 110kV升压站本期规模",
                        "columns": ["名称", "本期规模", "远期规模"],
                        "data": [["主变压器", "1台", "2台"]],
                    },
                    {
                        "key": "electricalPrimaryEquipmentMaterial",
                        "name": "升压站电气一次主要设备材料工程量表",
                        "columns": ["序号", "名称", "型号、规格及技术数据", "单位", "数量"],
                        "data": [
                            ["1.1", "主变压器", "三相双绕组油浸自冷式有载调压变压器", "台", 1],
                            ["", "", "型号：SZ20-100000/110", "", ""],
                            ["", "", "115±8×1.25%/37kV", "", ""],
                            ["", "", "接线组别：YN，d11", "", ""],
                            ["5.1", "35kV接地兼站用变成套装置", "DKSC-800/35-315/0.4", "台", 1],
                            ["", "", "接地变容量：800/315kVA", "", ""],
                            ["", "", "小电阻型号：NGR-37/200A—10s,106.8Ω", "", ""],
                            ["5.2", "35kV接地变成套装置", "DKSC-500/35", "台", 1],
                            ["", "", "接地变容量：500kVA", "", ""],
                            ["", "", "小电阻型号：DR-35/280,101Ω", "", ""],
                        ],
                    },
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["mainTransformerType"]["value"] == "三相双绕组油浸自冷式有载调压变压器"
    assert fields["mainTransformerModel"]["value"] == "SZ20-100000/110"
    assert fields["mainTransformerRatedCapacity"]["value"] == 100000
    assert fields["mainTransformerNum"]["value"] == 1
    assert fields["futureMainTransformerCount"]["value"] == 2
    assert fields["mainTransformerVoltageRatio"]["value"] == "115±8×1.25%"
    assert fields["connectionGroupType"]["value"] == "YN，d11"
    assert fields["groundingStationTransformerModel"]["value"] == "DKSC-800/35-315/0.4"
    assert fields["groundingStationTransformerVoltage"]["value"] == 35
    assert fields["groundingStationTransformerCapacity"]["value"] == "800/315"
    assert fields["groundingStationTransformerQuantity"]["value"] == 1
    assert fields["groundingStationTransformerUnit"]["value"] == "台"
    assert fields["groundingStationTransformerResistance"]["value"] == "NGR-37/200A—10s,106.8Ω"
    assert fields["groundingTransformerModel"]["value"] == "DKSC-500/35"
    assert fields["groundingTransformerVoltage"]["value"] == 35
    assert fields["groundingTransformerCapacity"]["value"] == 500
    assert fields["groundingTransformerQuantity"]["value"] == 1
    assert fields["groundingTransformerUnit"]["value"] == "台"
    assert fields["groundingTransformerResistance"]["value"] == "DR-35/280,101Ω"


def test_compound_row_match_fills_down_group_label_for_wind_power_average():
    """验证塔号空白续行时，风功率平均值仍能按塔号+项目联合定位。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "resourceOriginalTable002",
                        "name": "表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表",
                        "columns": ["测风塔", "项目", "1", "2", "年均"],
                        "data": [
                            ["0821#", "风速", 6.2, 7.3, 6.42],
                            ["", "风功率", 217, 316, 232],
                            ["0822#", "风速", 5.6, 6.8, 5.75],
                            ["", "风功率", 151, 273, 163],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windResource0821PowerAverage",
                "section": "资源章节",
                "source_table": {"name_patterns": ["平均风速.*风功率密度统计表"], "required_columns": ["项目", "年均"]},
                "row": {
                    "type": "label",
                    "match": [
                        {"column": ["测风塔"], "patterns": ["0821#"]},
                        {"column": ["项目"], "patterns": ["风功率"]},
                    ],
                },
                "column": {"aliases": ["年均", "平均"]},
                "value_type": "number",
            },
            {
                "field_code": "windResource0822PowerAverage",
                "section": "资源章节",
                "source_table": {"name_patterns": ["平均风速.*风功率密度统计表"], "required_columns": ["项目", "年均"]},
                "row": {
                    "type": "label",
                    "match": [
                        {"column": ["测风塔"], "patterns": ["0822#"]},
                        {"column": ["项目"], "patterns": ["风功率"]},
                    ],
                },
                "column": {"aliases": ["年均", "平均"]},
                "value_type": "number",
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["windResource0821PowerAverage"]["value"] == 232
    assert fields["windResource0822PowerAverage"]["value"] == 163


def test_sector_max_scans_grouped_tower_block_and_rank():
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceSectorDistribution",
                        "name": "表2.5.3.3-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）",
                        "columns": ["测风塔", "扇区", "N", "NNE", "NE", "ENE"],
                        "data": [
                            ["0821#", "风向（%）", 7.25, 3.61, 2.53, 1.67],
                            ["", "风功率（%）", 5.8, 1.58, 1.37, 0.29],
                            ["", "扇区", "S", "SSW", "SW", "WSW"],
                            ["", "风向（%）", 11.68, 7.26, 6.83, 5.41],
                            ["", "风功率（%）", 12.65, 8.35, 8.24, 5.04],
                            ["0822#", "扇区", "N", "NNE", "NE", "ENE"],
                            ["", "风向（%）", 6.3, 3.68, 2.51, 1.91],
                            ["", "风功率（%）", 6.57, 3.26, 0.98, 0.53],
                            ["", "扇区", "S", "SSW", "SW", "WSW"],
                            ["", "风向（%）", 9.2, 7.73, 7.47, 6.68],
                            ["", "风功率（%）", 7.14, 5.98, 6.7, 6.3],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windResource0822MaxWindDirectionSector",
                "section": "资源章节",
                "operation": "sector_max",
                "source_table": {"name_patterns": ["风向和风能分布统计"], "required_columns": ["测风塔", "扇区"]},
                "tower": {"patterns": ["0822#"]},
                "tower_column": {"aliases": ["测风塔"]},
                "metric_column": {"aliases": ["扇区"]},
                "metric": {"patterns": ["风向"]},
                "label": {"patterns": ["扇区"]},
                "value_type": "text",
            },
            {
                "field_code": "windResource0822SecondPowerSector",
                "section": "资源章节",
                "operation": "sector_max",
                "rank": 2,
                "source_table": {"name_patterns": ["风向和风能分布统计"], "required_columns": ["测风塔", "扇区"]},
                "tower": {"patterns": ["0822#"]},
                "tower_column": {"aliases": ["测风塔"]},
                "metric_column": {"aliases": ["扇区"]},
                "metric": {"patterns": ["风功率"]},
                "label": {"patterns": ["扇区"]},
                "value_type": "text",
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["windResource0822MaxWindDirectionSector"]["value"] == "S"
    assert fields["windResource0822MaxWindDirectionSector"]["maxValue"] == 9.2
    assert fields["windResource0822SecondPowerSector"]["value"] == "SW"
    assert fields["windResource0822SecondPowerSector"]["rankValue"] == 6.7


def test_table_value_resolver_merges_grounding_transformer_capacity_and_resistor_rows():
    """验证接地变成套装置可合并同一设备块内的容量和小电阻型号续行。"""
    result = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalPrimaryEquipmentMaterial",
                        "name": "升压站电气一次主要设备材料工程量表",
                        "columns": ["序号", "名称", "型号、规格及技术数据", "单位", "数量"],
                        "data": [
                            [5.1, "35kV接地变兼站用变成套装置", "DKSC-800/35-315/0.4", "台", 1],
                            ["", "", "接地变容量：800/315kVA", "", ""],
                            ["", "", "小电阻型号：DR-35/280, 101Ω", "", ""],
                            [5.2, "35kV接地变成套装置", "DKSC-500/35", "台", 1],
                            ["", "", "接地变容量：500kVA", "", ""],
                            ["", "", "小电阻型号：DR-35/280, 101Ω", "", ""],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "electricalPrimaryGroundingStationTransformerSpec",
                "section": "电气一次",
                "source_table": {"key": "electricalPrimaryEquipmentMaterial"},
                "row": {"type": "label", "column": "名称", "aliases": ["35kV接地兼站用变", "接地变兼站用变成套装置"]},
                "column": {"aliases": ["型号、规格及技术数据"]},
                "merge_following_rows": {"max_rows": 6},
                "value_type": "text",
            },
            {
                "field_code": "electricalPrimaryGroundingTransformerSetSpec",
                "section": "电气一次",
                "source_table": {"key": "electricalPrimaryEquipmentMaterial"},
                "row": {"type": "label", "column": "名称", "aliases": ["35kV接地变成套装置", "接地变成套装置"]},
                "column": {"aliases": ["型号、规格及技术数据"]},
                "merge_following_rows": {"max_rows": 6},
                "value_type": "text",
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["electricalPrimaryGroundingStationTransformerSpec"]["value"] == "DKSC-800/35-315/0.4，接地变容量：800/315kVA，小电阻型号：DR-35/280, 101Ω"
    assert fields["electricalPrimaryGroundingTransformerSetSpec"]["value"] == "DKSC-500/35，接地变容量：500kVA，小电阻型号：DR-35/280, 101Ω"


def test_electrical_primary_specs_can_filter_required_fragments_from_merged_rows():
    result = {
        "sections": [
            {
                "name": "电气一次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalPrimaryEquipmentMaterial",
                        "name": "表6.3.3-10 升压站电气一次主要设备材料工程量表",
                        "columns": ["序号", "名称", "型号、规格及技术数据", "单位", "数量", "备注"],
                        "data": [
                            [1.1, "主变压器", "三相双绕组油浸自冷式有载调压变压器", "台", 2, ""],
                            ["", "", "型号：SZ18-100000/110", "", "", ""],
                            ["", "", "115±8×1.25%/37kV", "", "", ""],
                            ["", "", "短路阻抗：", "", "", ""],
                            ["", "", "接线组别：YN，d11", "", "", ""],
                            [2.1, "GIS组合电器", "126kV，2000A，40kA/3s", "个", 1, "110kV架空出线间隔"],
                            ["", "每间隔包含：", "SF6断路器：126kV，2000A，40kA/3s，配弹簧操作机构", "", "", ""],
                            ["", "", "三工位隔离接地开关：126kV，2000A，40kA/3s，100kA，含微动开关", "", "", ""],
                            ["", "", "快速接地开关：126kV，40kA/3s，100kA", "", "", ""],
                            ["", "", "电流互感器：126kV，600 600-1200/1A， 0.2S/0.5/0.5/5P30/5P30/5P30/5P30", "", "", ""],
                            ["", "", "电压互感器：（110/√3）/（0.1/√3）/（0.1√3）/（0.1/√3）/0.1kV，0.5/0.5/0.2/3P，50/50/50/100VA", "", "", ""],
                            [5.1, "35kV接地变兼站用变成套装置", "DKSC-800/35-315/0.4，隔离开关-630/4", "台", 1, ""],
                            ["", "", "接地变容量：800/315kVA", "", "", ""],
                            ["", "", "小电阻型号：DR-35/280,101Ω", "", "", ""],
                            [5.2, "35kV接地变成套装置", "DKSC-500/35，隔离开关-630/4", "台", 1, ""],
                            ["", "", "接地变容量：500kVA", "", "", ""],
                            ["", "", "小电阻型号：DR-35/280,101Ω", "", "", ""],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["electricalPrimaryTransformerSpec"]["value"] == "三相双绕组油浸自冷式有载调压变压器，型号：SZ18-100000/110，115±8×1.25%/37kV，接线组别：YN，d11"
    assert fields["electricalPrimaryGisModelInfo"]["value"] == "126kV，2000A，40kA/3s"
    assert fields["electricalPrimaryGisQuantity"]["value"] == 1
    assert fields["electricalPrimaryGisUnit"]["value"] == "个"
    assert fields["electricalPrimaryGisRemark"]["value"] == "110kV架空出线间隔"
    assert fields["electricalPrimaryCircuitBreakerModel"]["value"] == "SF6断路器：126kV，2000A，40kA/3s，配弹簧操作机构"
    assert fields["electricalPrimaryDisconnectorModel"]["value"] == "三工位隔离接地开关：126kV，2000A，40kA/3s，100kA，含微动开关"
    assert fields["electricalPrimaryCurrentTransformerModel"]["value"] == "电流互感器：126kV，600 600-1200/1A， 0.2S/0.5/0.5/5P30/5P30/5P30/5P30"
    assert fields["electricalPrimaryVoltageTransformerModel"]["value"] == "电压互感器：（110/√3）/（0.1/√3）/（0.1√3）/（0.1/√3）/0.1kV，0.5/0.5/0.2/3P，50/50/50/100VA"
    assert fields["electricalPrimary110kvDistributionSpec"]["value"] == "126kV，2000A，40kA/3s，三工位隔离接地开关：126kV，2000A，40kA/3s，100kA，含微动开关，快速接地开关：126kV，40kA/3s，100kA，电流互感器：126kV，600 600-1200/1A， 0.2S/0.5/0.5/5P30/5P30/5P30/5P30"
    assert fields["electricalPrimaryGroundingStationTransformerSpec"]["value"] == "DKSC-800/35-315/0.4，接地变容量：800/315kVA，小电阻型号：DR-35/280,101Ω"
    assert fields["electricalPrimaryGroundingTransformerSetSpec"]["value"] == "DKSC-500/35，接地变容量：500kVA，小电阻型号：DR-35/280,101Ω"


def test_electrical_secondary_table_values_extract_battery_and_ups_fields_from_main_equipment():
    """验证电气二次设备表中蓄电池屏/UPS电源屏三列字段可配置抽取。"""
    result = {
        "sections": [
            {
                "name": "电气二次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalSecondaryMainEquipment",
                        "name": "表6.4.4-3 升压站电气二次主要设备表",
                        "columns": ["序号", "名称", "型号及规格", "单位", "数量"],
                        "data": [
                            [1, "蓄电池屏", "220V/250Ah阀控式密封铅酸蓄电池", "组", 2],
                            [2, "通信电池", "48V/200Ah阀控式密封铅酸蓄电池", "组", 1],
                            [3, "UPS电源屏", "7.5kVA", "套", 2],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["communicationPowerUnitType"]["value"] == "组"
    assert fields["communicationPowerQuantityValue"]["value"] == 1
    assert fields["electricalSecondaryBatterySpec"]["value"] == "220V/250Ah阀控式密封铅酸蓄电池"
    assert fields["electricalSecondaryBatteryUnit"]["value"] == "组"
    assert fields["electricalSecondaryBatteryQuantity"]["value"] == 2
    assert fields["electricalSecondaryUpsSpec"]["value"] == "7.5kVA"
    assert fields["electricalSecondaryUpsUnit"]["value"] == "套"
    assert fields["electricalSecondaryUpsQuantity"]["value"] == 2


def test_communication_power_unit_quantity_does_not_use_generic_dc_battery_panel():
    """普通直流蓄电池屏不能冒充通信电源设备。"""
    result = {
        "sections": [
            {
                "name": "电气二次",
                "fields": [],
                "tables": [
                    {
                        "key": "electricalSecondaryMainEquipment",
                        "name": "升压站电气二次主要设备表",
                        "columns": ["名称", "型号及规格", "单位", "数量"],
                        "data": [["蓄电池屏", "220V/250Ah阀控式密封铅酸蓄电池", "组", 2]],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["communicationPowerUnitType"]["status"] == "NIL"
    assert fields["communicationPowerQuantityValue"]["status"] == "NIL"


def test_investment_estimate_table_values_extract_required_summary_fields():
    """验证工程总概算表中的概算字段可配置抽取。"""
    result = {
        "sections": [
            {
                "name": "技经概算",
                "fields": [],
                "tables": [
                    {
                        "key": "investmentEstimate",
                        "name": "15.2.1工程总概算表",
                        "columns": ["序号", "项目名称", "合计（万元）"],
                        "data": [
                            [1, "工程静态投资（一～五）部分合计", 48364.34],
                            [2, "工程总投资（一～七）部分合计", 50120.12],
                            [3, "工程总投资合计", 50180.12],
                            [4, "单位千瓦静态投资（元/kW）", 4836.43],
                            [5, "单位千瓦动态投资（元/kW）", 5012.01],
                            [6, "智慧管理平台", 230],
                            [7, "110kV送出线路工程", 1200],
                            [8, "对侧间隔扩建工程", 500],
                            [9, "330kV送出线路分摊费", 800],
                            [10, "产品配套费", 90],
                            [11, "新能源场站感知设备（含螺栓预紧力在线监测系统等）", 310],
                            [12, "科技专篇", 60],
                            [13, "静态总投资（I～IV）部分合计", 49820.12],
                            [14, "建设期利息", 700],
                            [15, "动态总投资（I～IV）部分合计", 50520.12],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}
    tables = {table["key"]: table for table in enhanced["sections"][0]["derivedTables"] if table.get("key")}

    assert fields["investmentStaticPartTotal"]["value"] == 48364.34
    assert fields["investmentTotalPartTotal"]["value"] == 50120.12
    assert fields["investmentProjectTotalCost"]["value"] == 50180.12
    assert fields["unitKwStaticInvestmentEstimate"]["value"] == 4836.43
    assert fields["unitKwDynamicInvestmentEstimate"]["value"] == 5012.01
    assert fields["investmentSmartManagementPlatformTotal"]["value"] == 230
    assert fields["investment110kvOutgoingLineProjectTotal"]["value"] == 1200
    assert fields["investmentOppositeBayExpansionTotal"]["value"] == 500
    assert fields["investment330kvOutgoingLineShareTotal"]["value"] == 800
    assert fields["investmentProductSupportingCostTotal"]["value"] == 90
    assert fields["investmentNewEnergyStationPerceptionEquipmentTotal"]["value"] == 310
    assert fields["investmentTechnologySpecialTotal"]["value"] == 60
    assert fields["investmentStaticTotalItoIv"]["value"] == 49820.12
    assert fields["investmentConstructionInterestTotal"]["value"] == 700
    assert fields["investmentDynamicTotalItoIv"]["value"] == 50520.12
    assert tables["investmentEstimateCopy"]["source"]["tableName"] == "15.2.1工程总概算表"


def test_investment_repeated_summary_rows_follow_partial_and_project_fallback_rules():
    """部分值仅在重复行中取第一条，项目值取第二条且单条时回退。"""

    def resolve(rows):
        result = {
            "sections": [
                {
                    "name": "技经概算",
                    "fields": [],
                    "tables": [
                        {
                            "key": "investmentEstimate",
                            "name": "工程总概算表",
                            "columns": ["项目名称", "合计（万元）"],
                            "data": rows,
                        }
                    ],
                }
            ]
        }
        enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
        return {field["fieldCode"]: field.get("value") for field in enhanced["sections"][0]["tableFields"]}

    repeated = resolve(
        [
            ["静态投资（部分）", 100],
            ["静态投资", 200],
            ["动态投资（部分）", 110],
            ["动态投资（部分）", 111],
            ["动态总投资", 210],
            ["动态总投资", 220],
            ["单位千瓦静态投资", 10],
            ["单位千瓦静态投资", 20],
            ["单位千瓦动态投资", 11],
            ["单位千瓦动态投资", 22],
        ]
    )
    assert repeated["investmentStaticInvestmentTotal"] == 100
    assert repeated["investmentStaticTotalItoIv"] == 200
    assert repeated["investmentDynamicInvestmentTotal"] == 110
    assert repeated["investmentDynamicTotalItoIv"] == 220
    assert repeated["unitKwStaticInvestmentPartTotal"] == 10
    assert repeated["unitKwStaticInvestmentEstimate"] == 20
    assert repeated["unitKwInvestmentPartTotal"] == 11
    assert repeated["unitKwDynamicInvestmentEstimate"] == 22

    singleton = resolve(
        [
            ["静态投资", 200],
            ["动态投资（部分）", 110],
            ["动态总投资", 220],
            ["单位千瓦静态投资", 20],
            ["单位千瓦动态投资", 22],
        ]
    )
    assert singleton["investmentStaticInvestmentTotal"] is None
    assert singleton["investmentDynamicInvestmentTotal"] is None
    assert singleton["unitKwStaticInvestmentPartTotal"] is None
    assert singleton["unitKwInvestmentPartTotal"] is None
    assert singleton["investmentStaticTotalItoIv"] == 200
    assert singleton["investmentDynamicTotalItoIv"] == 220
    assert singleton["unitKwStaticInvestmentEstimate"] == 20
    assert singleton["unitKwDynamicInvestmentEstimate"] == 22


def test_table_value_resolver_promotes_year_header_row():
    """验证横向年份在首行时会提升为真实表头，避免年份错位。"""
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financeTotalCostEstimate",
                        "name": "总成本费用估算表",
                        "columns": ["序号", "项目", "合计", "运行期", "col_4", "col_5"],
                        "data": [
                            ["", "", "", "第 1 年", "第 2 年", "第 3 年"],
                            [1, "材料费", 100, 0, 50, 60],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "financeMaterialCostYears",
                "section": "财务",
                "operation": "cell_series",
                "source_table": {"key": "financeTotalCostEstimate"},
                "row": {"type": "label", "column": "项目", "aliases": ["材料费"]},
                "columns": [
                    {"name": "第1年", "aliases": ["第1年"]},
                    {"name": "第2年", "aliases": ["第2年"]},
                    {"name": "第3年", "aliases": ["第3年"]},
                ],
                "value_type": "number",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "OK"
    assert field["value"] == {"第1年": 0, "第2年": 50, "第3年": 60}


def test_finance_table_values_extract_indicator_summary_capacity_and_energy():
    """验证财务指标汇总表中的风电系统容量和年上网电量单位/数值。"""
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financialIndicatorSummary",
                        "name": "附表16.1 财务指标汇总表",
                        "columns": ["序号", "项目", "单位", "数值"],
                        "data": [
                            [1, "装机容量", "MW", 200],
                            [2, "年上网电量", "MWh", 475211.0],
                            [3, "流动资金", "万元", 1200],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["financeWindSystemCapacityUnit"]["value"] == "MW"
    assert fields["financeWindSystemCapacityValue"]["value"] == 200
    assert fields["financeAnnualOnGridEnergyUnit"]["value"] == "MWh"
    assert fields["financeAnnualOnGridEnergyValue"]["value"] == 475211


def test_finance_table_values_extract_insurance_rate_from_parameter_table():
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financeAssumptionParameters",
                        "name": "财务参数表",
                        "columns": ["字段", "数据"],
                        "data": [
                            ["折旧年限（年）", 20],
                            ["残值率（%）", 5],
                            ["保险费率（%）", 0.1],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["financeInsuranceRate"]["value"] == 0.1


def test_finance_table_values_extract_cost_depreciation_and_continuation_years():
    """验证财务成本、续表、电价和折旧首年字段从表中抽取且年份不串列。"""
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financeTotalCostEstimate",
                        "name": "附表16.3：总成本费用估算表（人民币单位：万元）",
                        "columns": ["序号", "项目", "合计", "建设期", "运行期", "col_5", "col_6", "col_7", "col_8", "col_9", "col_10", "col_11", "col_12", "col_13", "col_14", "col_15"],
                        "data": [
                            ["", "", "", "第1年", "第2年", "第3年", "第4年", "第5年", "第6年", "第7年", "第8年", "第9年", "第10年", "第11年", "第12年", "第13年"],
                            [1, "材料费", 3800, 0, 100, 100, 100, 100, 100, 220, 220, 220, 220, 220, 220, 220],
                            [3, "修理费", 14600, 0, 320, 320, 320, 320, 320, 800, 800, 800, 800, 800, 900, 900],
                        ],
                    },
                    {
                        "key": "financeTotalCostEstimateContinuation",
                        "name": "附表16.3：总成本费用估算表（续）（人民币单位：万元）",
                        "columns": ["序号", "项目", "第14年", "第15年", "第16年", "第17年", "第18年", "第19年", "第20年", "第21年"],
                        "data": [
                            [1, "材料费", 220, 220, 220, 220, 220, 220, 220, 220],
                            [3, "修理费", 900, 900, 900, 900, 900, 900, 900, 900],
                        ],
                    },
                    {
                        "key": "financeDepreciationAmortization",
                        "name": "附表16.4：资产折旧摊销估算表（人民币单位：万元）",
                        "columns": ["序号", "项目", "合计", "建设期", "第1年"],
                        "data": [[1, "1.1.1 固定资产原值", 1000, 0, 1000]],
                    },
                    {
                        "key": "financeProfitDistributionContinuation",
                        "name": "附表16.5：利润与利润分配表（续）（人民币单位：万元）",
                        "columns": ["序号", "项目", "第14年", "第15年", "第16年", "第17年", "第18年", "第19年", "第20年", "第21年"],
                        "data": [
                            [1, "上网电价（不含税）（元/kWh）", 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25],
                            [2, "上网电价（含税）（元/kWh）", 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28],
                        ],
                    },
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["financeMaterialCostYears1To13"]["value"]["第2年"] == 100
    assert fields["financeMaterialCostYears1To13"]["value"]["第7年"] == 220
    assert fields["financeRepairCostYears1To13"]["value"]["第2年"] == 320
    assert fields["financeRepairCostYears1To13"]["value"]["第7年"] == 800
    assert fields["financeMaterialCostYears14To21"]["value"]["第14年"] == 220
    assert fields["financeRepairCostYears14To21"]["value"]["第14年"] == 900
    assert fields["financeFixedAssetOriginalValueBuildYearAndYear1"]["value"] == {"建设期": 0, "第1年": 1000}
    assert fields["financeOnGridPriceWithoutTaxYears14To21"]["value"]["第14年"] == 0.25
    assert fields["financeOnGridPriceWithTaxYears14To21"]["value"]["第14年"] == 0.28


def test_finance_year_series_treats_merged_operation_period_as_year_one():
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {
                        "key": "financeTotalCostEstimate",
                        "name": "附表16.3：总成本费用估算表（人民币单位：万元）",
                        "columns": ["序号", "项目", "合计", "建设期", "运行期", "第2年", "第3年", "第4年", "第5年", "第6年", "第7年", "第8年", "第9年", "第10年", "第11年", "第12年", "第13年"],
                        "data": [
                            [1, "材料费", 2850, 0, 75, 75, 75, 75, 75, 75, 165, 165, 165, 165, 165, 165, 165],
                            [3, "修理费", 10950, 0, 240, 240, 240, 240, 240, 240, 600, 600, 600, 600, 600, 600, 600],
                        ],
                    }
                ],
            }
        ]
    }

    enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["financeMaterialCostYears1To13"]["value"] == {
        "第1年": 75,
        "第2年": 75,
        "第3年": 75,
        "第4年": 75,
        "第5年": 75,
        "第6年": 75,
        "第7年": 165,
        "第8年": 165,
        "第9年": 165,
        "第10年": 165,
        "第11年": 165,
        "第12年": 165,
        "第13年": 165,
    }
    assert fields["financeRepairCostYears1To13"]["value"]["第1年"] == 240
    assert fields["financeRepairCostYears1To13"]["value"]["第7年"] == 600


def test_dynamic_tower_discovery_fallback_scans_table_columns():
    """验证测风塔号写在列名时也能展开动态规则。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceTowerBasic",
                        "name": "测风塔基本情况一览表",
                        "columns": ["测风塔", "2001#测风塔", "B03#雷达测风"],
                        "data": [["海拔", "1096m", "1112m"]],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "tower{tower_clean}",
                "section": "资源章节",
                "towers": {
                    "from_table": {
                        "section": "资源章节",
                        "source_table": {"name_patterns": ["不存在的表"]},
                        "value_pattern": r"[A-Za-z0-9]{2,10}\s*[#＃]",
                    }
                },
                "source_table": {"key": "windResourceTowerBasic"},
                "row": {"type": "label", "aliases": ["海拔"]},
                "column": {"aliases": ["{tower}"]},
                "value_type": "text",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    assert fields["tower2001"]["status"] == "OK"
    b03_key = next(key for key in fields if key.lower() == "towerb03")
    assert fields[b03_key]["status"] == "OK"


def test_wind_tower_basic_table_extracts_coordinates_and_measurement_periods():
    """测风塔基本情况表支持合并坐标列和独立经纬度列。"""

    def resolve(columns, data):
        result = {
            "sections": [
                {
                    "name": "资源章节",
                    "fields": [],
                    "tables": [
                        {
                            "key": "windResourceTowerBasic",
                            "name": "测风塔基本情况表",
                            "columns": columns,
                            "data": data,
                        }
                    ],
                }
            ]
        }
        enhanced = TableValueResolver.from_config_file("configs/table_field_extractors.yaml").enhance_result(result)
        return {field["fieldCode"]: field for field in enhanced["sections"][0]["tableFields"]}

    combined = resolve(
        ["测风塔编号", "坐标", "观测时段"],
        [
            ["0821#", "E108.123 N37.456", "2021年1月—2021年12月"],
            ["0822#", "东经109°12′30″ 北纬38°15′20″", "2022.01—2022.12"],
        ],
    )
    assert combined["windTowerLongitude"]["value"] == ["E108.123", "东经109°12′30″"]
    assert combined["windTowerLatitude"]["value"] == ["N37.456", "北纬38°15′20″"]
    assert combined["windMeasurementPeriod"]["value"] == ["2021年1月—2021年12月", "2022.01—2022.12"]

    separate = resolve(
        ["测风塔编号", "经度", "纬度", "测风周期"],
        [["0821#", "108.765", "37.654", "2020年全年"]],
    )
    assert separate["windTowerLongitude"]["value"] == ["108.765"]
    assert separate["windTowerLatitude"]["value"] == ["37.654"]
    assert separate["windMeasurementPeriod"]["value"] == ["2020年全年"]


def test_table_value_resolver_requires_configured_table_name_pattern():
    """验证 key 命中但表号/表名不符时返回 NIL，不把近似表当目标表。"""
    result = {
        "sections": [
            {
                "name": "发电量章节",
                "fields": [],
                "tables": [
                    {
                        "key": "generationSummary",
                        "name": "表 5.4-1 风电场工程年上网电量计算成果表",
                        "columns": ["项目", "单位", "指标"],
                        "data": [["年上网电量", "MW·h", 1000]],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "generationAnnualOnGridEnergyWTG2046250",
                "section": "发电量章节",
                "source_table": {"key": "generationSummary", "name_patterns": [r"表\s*5\.3-1\s*风电场120m轮毂高度年上网电量估算表"]},
                "row": {"type": "label", "aliases": ["年上网电量"]},
                "column": {"aliases": ["指标"]},
                "value_type": "number",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "NIL"
    assert field["nilReason"] == "table_constraints_mismatch"


def test_table_value_resolver_numeric_row_alias_does_not_match_decimal_substring():
    """验证 90m 这类行标签不会误命中 0.096 等小数文本。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceTurbulence2001",
                        "name": "表 2.5-13 2001#测风塔 140m 高度各风速段湍流强度",
                        "columns": ["风速段", "代表湍流强度"],
                        "data": [[18, 0.096], [19, 0.09]],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windTurbulence0822Representative90m",
                "section": "资源章节",
                "source_table": {"key": "windResourceTurbulence2001"},
                "row": {"type": "label", "aliases": ["90m"]},
                "column": {"aliases": ["代表湍流强度"]},
                "value_type": "number",
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "NIL"
    assert field["nilReason"] == "row_not_found"


def test_table_value_resolver_can_locate_table_by_required_columns_when_key_is_stale():
    """验证 key 错挂时，可以用必备列定位真正的目标表。"""
    result = {
        "sections": [
            {
                "name": "财务",
                "fields": [],
                "tables": [
                    {"key": "financeSensitivityAnalysis", "name": "敏感性分析表明：", "columns": ["col_0", "电缆"], "data": [["A", "B"]]},
                    {"key": "financeOriginalTable002", "name": "敏感性分析表明：", "columns": ["变化因素", "变化率", "资本金内部收益率（%）"], "data": [["投资额", "-10%", 9.78]]},
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "table_code": "financeSensitivityAnalysisCopy",
                "section": "财务",
                "operation": "copy_table",
                "source_table": {
                    "key": "financeSensitivityAnalysis",
                    "name_patterns": ["敏感性分析"],
                    "required_columns": ["变化因素", "变化率", "资本金内部收益率"],
                },
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    table = enhanced["sections"][0]["derivedTables"][0]

    assert table["status"] == "OK"
    assert table["source"]["tableKey"] == "financeOriginalTable002"


def test_table_value_resolver_max_row_label_skips_header_rows():
    """验证 max_row_label 会跳过分组表头，不把表头行当作最大值候选。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceDirectionEnergyFrequency",
                        "name": "表2.6-16 测风塔风向风能频率统计成果表",
                        "columns": ["col_0", "0822#", "0823#", "0824#"],
                        "data": [
                            ["风向", "90m风向频率", "90m风能频率", "90m风向频率"],
                            ["N", "10", "20", "30"],
                            ["NW", "20", "5", "40"],
                            ["NNW", "15", "35", "10"],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windDirectionMax0822",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0822#"]},
                "label_column": {"aliases": ["风向"]},
            }
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "OK"
    assert field["value"] == "NW"
    assert field["maxValue"] == 20


def test_table_value_resolver_uses_direction_table_after_header_skip():
    """验证 0822#、0823#、0824# 的最大风向规则都能跳过表头行。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceDirectionEnergyFrequency",
                        "name": "表2.6-16 测风塔风向风能频率统计成果表",
                        "columns": ["col_0", "0822#", "0823#", "0824#", "col_4", "col_5", "col_6"],
                        "data": [
                            ["风向", "90m风向频率", "90m风能频率", "90m风向频率", "90m风能频率", "90m风向频率", "90m风能频率"],
                            ["N", "6.68", "7.23", "7.55", "8.37", "7.39", "10.7"],
                            ["NW", "20", "21", "4", "5", "8", "9"],
                            ["NNW", "10", "11", "30", "31", "9", "41"],
                            ["S", "5", "6", "6", "7", "40", "10"],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windDirectionMax0822",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0822#"]},
                "label_column": {"aliases": ["风向"]},
            },
            {
                "field_code": "windDirectionMax0823",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0823#"]},
                "label_column": {"aliases": ["风向"]},
            },
            {
                "field_code": "windDirectionMax0824",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0824#"]},
                "label_column": {"aliases": ["风向"]},
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {item["fieldCode"]: item for item in enhanced["sections"][0]["tableFields"]}

    assert fields["windDirectionMax0822"]["value"] == "NW"
    assert fields["windDirectionMax0823"]["value"] == "NNW"
    assert fields["windDirectionMax0824"]["value"] == "NNW"



def test_direction_frequency_ignores_merged_numeric_continuation_rows():
    """验证风向频率表合并续表后，不把数字行当作风向返回。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceDirectionEnergyFrequency",
                        "name": "表2.6-16 测风塔风向风能频率统计成果表",
                        "columns": ["col_0", "0822#", "0823#", "0824#", "col_4", "col_5", "col_6"],
                        "data": [
                            ["风向", "90m风向频率", "90m风能频率", "90m风向频率", "90m风能频率", "90m风向频率", "90m风能频率"],
                            ["N", "6", "7", "8", "9", "10", "11"],
                            ["NW", "20", "21", "4", "5", "8", "9"],
                            ["NNW", "10", "11", "30", "31", "9", "41"],
                            ["8", "99", "99", "99", "99", "99", "99"],
                        ],
                    }
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windDirectionMax0822",
                "section": "资源章节",
                "operation": "max_row_label",
                "source_table": {"key": "windResourceDirectionEnergyFrequency"},
                "value_column": {"aliases": ["0822#风能频率", "0822#"]},
                "label_column": {"aliases": ["风向"]},
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    field = enhanced["sections"][0]["tableFields"][0]

    assert field["status"] == "OK"
    assert field["value"] == "NW"
    assert field["maxValue"] == 21


def test_wind_shear_values_use_merged_table_occurrences_when_title_key_is_stale():
    """验证风切变连续表被合并后，可按原始表号选择对应的综合值行。"""
    result = {
        "sections": [
            {
                "name": "资源章节",
                "fields": [],
                "tables": [
                    {
                        "key": "windResourceTurbulence0823",
                        "name": "表 2.5 15 0823#测风塔90m高度各风速段湍流强度",
                        "columns": ["风速段", "数据量", "代表湍流强度"],
                        "data": [["3-4", "10", "0.1"]],
                    },
                    {
                        "key": "resourceOriginalTable002",
                        "name": "由以上图表可以看出，测风塔湍流强度随高度变化",
                        "columns": ["高度(m)", "80", "70", "50", "30", "10"],
                        "data": [
                            [90, 0.147, 0.134, 0.138, 0.151, 0.115],
                            ["综合值", "0.137（不考虑10m\30m）", None, None, None, None],
                            [90, 0.191, 0.149, 0.134, 0.12, 0.094],
                            ["综合值", "0.130（不考虑10m\30m）", None, None, None, None],
                            [90, 0.18, 0.14, 0.13, 0.12, 0.09],
                            ["综合值", "0.122（不考虑10m\30m）", None, None, None, None],
                        ],
                    },
                ],
            }
        ]
    }
    config = {
        "rules": [
            {
                "field_code": "windShear2517",
                "section": "资源章节",
                "source_table": {"key": "windResourceTurbulence0823", "name_patterns": [r"表\s*2\.5-17\s*0823#测风塔各高度风速切变指数统计"]},
                "row": {"type": "label", "aliases": ["综合值"]},
                "column": {"aliases": ["综合值", "风切变", "风切变指数"]},
                "value_type": "number",
            },
            {
                "field_code": "windShear2518",
                "section": "资源章节",
                "source_table": {"name_patterns": [r"表\s*2\.5-18\s*0823#测风塔各高度风速切变指数统计"]},
                "row": {"type": "label", "aliases": ["综合值"]},
                "column": {"aliases": ["综合值", "风切变", "风切变指数"]},
                "value_type": "number",
            },
            {
                "field_code": "windShear2519",
                "section": "资源章节",
                "source_table": {"key": "windResourceShearB03", "name_patterns": [r"表\s*2\.5-19\s*0824#测风塔各高度风速切变指数统计"]},
                "row": {"type": "label", "aliases": ["综合值"]},
                "column": {"aliases": ["综合值", "风切变", "风切变指数"]},
                "value_type": "number",
            },
        ]
    }

    enhanced = TableValueResolver(config).enhance_result(result)
    fields = {item["fieldCode"]: item for item in enhanced["sections"][0]["tableFields"]}

    assert fields["windShear2517"]["value"] == 0.137
    assert fields["windShear2518"]["value"] == 0.13
    assert fields["windShear2519"]["value"] == 0.122
