"""Existing default schemas and field preference constants."""

from __future__ import annotations

from copy import deepcopy

from word_parser.config.output_schema import REQUIRED_FIELD_META as CONFIG_REQUIRED_FIELD_META, REQUIRED_SECTION_SCHEMA as CONFIG_REQUIRED_SECTION_SCHEMA, SECTION_ORDER as CONFIG_SECTION_ORDER

from parser_engine.tables import StandardTableExtractor


class ResultDefaults:
    STANDARD_TABLE_EXTRACTOR = StandardTableExtractor()

    WIND_TOWER_CODE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]"

    COMBINED_DETAIL_ONLY_FIELD_CODES = {
        "windResourceTowerCodes",
        "windFarmAirDensities",
        "windResourceAirDensities",
        "windResourceAirDensity10m",
        "windResourceAirDensity160m",
        "hubHeightAnnualAverageWindSpeed",
        "hubHeightWindPowerDensity",
        "windResourceMainWindDirections",
        "windResourceSecondaryWindDirections",
        "windResourceMainWindEnergyDirections",
        "windResourceSecondaryWindEnergyDirections",
        "representativeTurbulenceIntensity",
        "windShearExponent",
        "windResourceGenerationUses",
    }

    ROAD_PARAMETER_FIELD_CODES = {
        "accessRoadLength",
        "siteEntryRoadLength",
        "accessRoadSubgradeWidth",
        "accessRoadPavementWidth",
        "newRoadLength",
        "rebuiltRoadLength",
        "subgradeWidth",
        "pavementWidth",
        "siteRoadLength",
        "maintenanceRoadLength",
        "maintenanceRoadSubgradeWidth",
        "maintenanceRoadPavementWidth",
    }

    GENERATION_TABLE_PREFERRED_FIELD_CODES = {
        "installedCapacity",
        "turbineCount",
        "turbineCapacity",
        "nonWakeLossFactor",
        "gridAnnualEnergy",
        "equivalentFullLoadHours",
    }

    ELECTRICAL_PRIMARY_TABLE_PREFERRED_FIELD_CODES = {
        "accessStationName",
        "accessibleVoltage",
        "accessibleCapacity",
        "plannedCapacity",
        "currentCapacity",
        "connectionType",
        "electricalPrimaryTransformerSpec",
        "electricalPrimarySvgSpec",
        "electricalPrimarySvgUnit",
        "electricalPrimarySvgQuantity",
        "electricalPrimaryGroundingTransformerSetSpec",
        "electricalPrimaryExternalPowerTransformerSpec",
        "stationTransformerCapacity10kv",
        "groundingTransformerCapacity35kv",
        "groundingStationTransformerCapacity35kv",
        "svgReactiveCompensationCapacity",
    }

    WIND_FOUNDATION_TABLE_PREFERRED_FIELD_CODES = {
        "foundationCapDiameter",
        "foundationColumnDiameter",
        "foundationCapBottomRadius",
        "foundationTopRadius",
        "foundationColumnRadius",
        "foundationOuterEdgeHeight",
        "foundationConeHeight",
        "foundationColumnHeight",
        "foundationBuriedDepth",
        "pileOuterDiameter",
        "pileCount",
        "pileLength",
        "pileRingCount",
    }

    INVESTMENT_SUMMARY_FIELD_ROWS = {
        "investmentStaticPartTotal": ("工程静态投资（一～五）部分合计", "万元", ["工程静态投资（一～五）部分合计", "工程静态投资（一~五）部分合计", "工程静态投资"]),
        "investmentTotalPartTotal": ("工程总投资（一～七）部分合计", "万元", ["工程总投资（一～七）部分合计", "工程总投资（一~七）部分合计"]),
        "investmentProjectTotalCost": ("工程总投资合计", "万元", ["工程总投资合计"]),
        "unitKwStaticInvestmentEstimate": ("单位千瓦静态投资", "元/kW", ["单位千瓦静态投资"]),
        "unitKwDynamicInvestmentEstimate": ("单位千瓦动态投资", "元/kW", ["单位千瓦动态投资", "单位千瓦投资"]),
        "investmentSmartManagementPlatformTotal": ("智慧管理平台合计", "万元", ["智慧管理平台"]),
        "investment110kvOutgoingLineProjectTotal": ("110kV送出线路工程合计", "万元", ["110kV送出线路工程", "110千伏送出线路工程"]),
        "investmentOppositeBayExpansionTotal": ("对侧间隔扩建工程合计", "万元", ["对侧间隔扩建工程", "对侧间隔扩建"]),
        "investment330kvOutgoingLineShareTotal": ("330kV送出线路分摊费合计", "万元", ["330kV送出线路分摊费", "330千伏送出线路分摊费"]),
        "investmentProductSupportingCostTotal": ("产品配套费合计", "万元", ["产品配套费", "产业配套费"]),
        "investmentNewEnergyStationPerceptionEquipmentTotal": ("新能源场站感知设备合计", "万元", ["新能源场站感知设备", "螺栓预紧力在线监测系统"]),
        "investmentTechnologySpecialTotal": ("科技专篇合计", "万元", ["科技专篇"]),
        "investmentStaticTotalItoIv": ("静态总投资（I～IV）部分合计", "万元", ["静态总投资（I～IV）部分合计", "静态总投资（Ⅰ～Ⅳ）部分合计", "静态总投资（I~IV）部分合计", "静态总投资"]),
        "investmentConstructionInterestTotal": ("建设期利息合计", "万元", ["建设期利息"]),
        "investmentDynamicTotalItoIv": ("动态总投资（I～IV）部分合计", "万元", ["动态总投资（I～IV）部分合计", "动态总投资（Ⅰ～Ⅳ）部分合计", "动态总投资（I~IV）部分合计", "动态总投资"]),
    }

    EARTHWORK_FIELD_ROWS = {
        "道路": ("roadEarthworkExcavation", "roadEarthworkBackfill"),
        "风机平台": ("windPlatformEarthworkExcavation", "windPlatformEarthworkBackfill"),
        "风机基础": ("windFoundationEarthworkExcavation", "windFoundationEarthworkBackfill"),
        "箱变基础": ("boxFoundationEarthworkExcavation", "boxFoundationEarthworkBackfill"),
        "集电线路": ("collectorLineEarthworkExcavation", "collectorLineEarthworkBackfill"),
        "升压站": ("substationEarthworkExcavation", "substationEarthworkBackfill"),
        "合计": ("totalEarthworkExcavation", "totalEarthworkBackfill"),
    }

    DETERMINISTIC_TEXT_FIELD_CODES = {
        "selectedTurbineSafetyClass",
        "stationTransformerCapacity10kv",
        "groundingTransformerCapacity35kv",
        "groundingStationTransformerCapacity35kv",
        "svgReactiveCompensationCapacity",
        "dcBatteryConfiguration",
        "upsPowerConfiguration",
        "pileOuterDiameter",
        "pileRingCount",
        "staffSalary",
    }

    DETAIL_TABLES = [
        {
            "key": "windResourceTowerBasic",
            "section_keywords": ["\u8d44\u6e90\u7ae0\u8282", "\u98ce\u8d44\u6e90"],
            "required_headers": [],
            "caption_keywords": ["\u6d4b\u98ce\u5854\u57fa\u672c\u60c5\u51b5\u8868"],
            "columns": {},
        },
        {
            "key": "windResourceShearStatistics",
            "section_keywords": ["\u8d44\u6e90\u7ae0\u8282", "\u98ce\u8d44\u6e90"],
            "required_headers": [],
            "caption_keywords": ["\u98ce\u5207\u53d8\u6307\u6570\u7edf\u8ba1\u8868"],
            "columns": {},
        },
        {
            "key": "windResourceSpeedPowerStatistics",
            "section_keywords": ["\u8d44\u6e90\u7ae0\u8282", "\u98ce\u8d44\u6e90"],
            "required_headers": [],
            "caption_keywords": ["\u5e73\u5747\u98ce\u901f", "\u98ce\u529f\u7387\u5bc6\u5ea6"],
            "columns": {},
        },
        {
            "key": "windResourceSectorDistribution",
            "section_keywords": ["\u8d44\u6e90\u7ae0\u8282", "\u98ce\u8d44\u6e90"],
            "required_headers": [],
            "caption_keywords": ["\u6247\u533a\u98ce\u5411", "\u98ce\u80fd\u5206\u5e03"],
            "columns": {},
        },
        {
            "key": "windResourceTurbulenceComparison",
            "section_keywords": ["\u8d44\u6e90\u7ae0\u8282", "\u98ce\u8d44\u6e90"],
            "required_headers": [],
            "caption_keywords": ["\u6e4d\u6d41\u5f3a\u5ea6\u6bd4\u8f83\u8868"],
            "columns": {},
        },
        {
            "key": "earthworkBalance",
            "section_keywords": [],
            "required_headers": ["项目", "土方开挖"],
            "columns": {
                "item": ["项目"],
                "excavation": ["土方开挖"],
                "backfill": ["土方回填"],
            },
        },
        {
            "key": "permanentLandArea",
            "section_keywords": [],
            "required_headers": ["永久性占地项目"],
            "columns": {
                "item": ["永久性占地项目"],
                "windFoundation": ["风机基础"],
                "boxTransformerFoundation": ["箱变基础"],
                "substation110kv": ["110kV升压站"],
                "collectorTower": ["集电线路杆塔征地"],
                "accessRoad": ["进升压站道路"],
                "total": ["合计"],
            },
        },
        {
            "key": "longTermLeaseArea",
            "section_keywords": [],
            "required_headers": ["长期租地项目"],
            "columns": {
                "item": ["长期租地项目"],
                "directBuriedCable": ["电缆直埋征地"],
                "permanentRoad": ["场内永久道路"],
                "accessRoad": ["进站道路"],
                "total": ["合计"],
            },
        },
        {
            "key": "temporaryLandArea",
            "section_keywords": [],
            "required_headers": ["临时性占地项目"],
            "columns": {
                "item": ["临时性占地项目"],
                "platform": ["场内平整", "安装平台"],
                "temporaryRoad": ["临时施工道路"],
                "livingFacility": ["生活临建"],
                "total": ["合计"],
            },
        },
    ]

    TABLE_OUTPUT_HEADERS = {
        "windResourceTowerBasic": {"name": "表2.4.1-1 测风塔基本情况表", "headers": []},
        "windResourceShearStatistics": {"name": "表2.5.2.1-1 测风塔不同高度测风资料风切变指数统计表", "headers": []},
        "windResourceSpeedPowerStatistics": {"name": "表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表", "headers": []},
        "windResourceSectorDistribution": {"name": "表2.5.3.3-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）", "headers": []},
        "windResourceDirectionEnergyFrequency": {"name": "表2.6-16 测风塔风向风能频率统计成果表", "headers": []},
        "windResourceTurbulenceComparison": {"name": "表2.5.2.2-1 测风塔不同高度湍流强度比较表", "headers": []},
        "windResourceTurbulenceIntensity": {
            "name": "湍流强度",
            "headers": [
                {"key": "towerCode", "name": "测风塔编号"},
                {"key": "height", "name": "高度"},
                {"key": "averageTurbulenceIntensity", "name": "平均湍流强度"},
                {"key": "representativeTurbulenceIntensity", "name": "代表性湍流强度"},
            ],
        },
        "electricalPrimaryStationScale": {"name": "表6.3-1 110kV升压站本期规模", "headers": []},
        "electricalPrimaryEquipmentMaterial": {"name": "表6.3.3-10 升压站电气一次主要设备材料工程量表", "headers": []},
        "electricalSecondaryMainEquipment": {"name": "表6.4.4-3 升压站电气二次主要设备表", "headers": []},
        "electricalSecondaryCommunicationEquipment": {"name": "表6.5-1 主要通信设备表", "headers": []},
        "collectorElectricalMaterial": {"name": "6.6.16.1电气部分材料清册", "headers": []},
        "collectorTowerMaterial": {"name": "6.6.16.2杆塔部分材料清册", "headers": []},
        "collectorFoundationMaterial": {"name": "6.6.16.3基础部分材料清册", "headers": []},
        "collectorOpticalCableMaterial": {"name": "6.6.16.4光缆部分材料清册", "headers": []},
        "collectorCableMaterial": {"name": "6.6.16.5电缆部分材料清册", "headers": []},
        "collectorTowerGroundingMaterial": {"name": "6.6.16.6铁塔接地装置材料", "headers": []},
        "collectorMainEquipmentMaterial": {"name": "集电线路部分主要设备及材料清册", "headers": []},
        "substationCivil": {"name": "表9.7-1 升压站主要土建工程量表", "headers": []},
        "windFoundationConstruction": {"name": "表9.4-5 基础断面表", "headers": []},
        "boxFoundationTechnical": {"name": "表9.5-1 箱变基础单台工程量表（配事故油池）", "headers": []},
        "permanentLandSummary": {"name": "表9.4-1 工程永久征地面积汇总表", "headers": []},
        "temporaryLandSummary": {"name": "表9.4-2 工程临时征地面积汇总表", "headers": []},
        "earthworkBalance": {"name": "表10.2-2土石方平衡表（万m(3)）", "headers": []},
        "permanentLandArea": {"name": "表10.4-1 工程征用地计算合计表", "headers": []},
        "landTotalAcquisition": {"name": "9.4.1.工程总征地", "headers": []},
        "longTermLeaseArea": {"name": "长期租地面积表", "headers": [{"key": "item", "name": "长期租地项目"}, {"key": "directBuriedCable", "name": "电缆直埋征地"}, {"key": "permanentRoad", "name": "场内永久道路"}, {"key": "accessRoad", "name": "进站道路"}, {"key": "total", "name": "合计"}]},
        "temporaryLandArea": {"name": "临时性占地面积表", "headers": [{"key": "item", "name": "临时性占地项目"}, {"key": "platform", "name": "场内平整安装平台"}, {"key": "temporaryRoad", "name": "临时施工道路"}, {"key": "livingFacility", "name": "生活临建"}, {"key": "total", "name": "合计"}]},
        "investmentTechnicalEconomicIndicators": {"name": "15.3.9.1 主要技术经济指标表", "headers": []},
        "investmentEstimate": {"name": "15.2.1工程总概算表", "headers": []},
        "investmentConstructionAuxiliary": {"name": "15.2.2 施工辅助工程概算表", "headers": []},
        "investmentEquipmentInstallation": {"name": "15.2.3设备及安装工程概算表", "headers": []},
        "investmentBuilding": {"name": "15.2.4建筑工程概算表", "headers": []},
        "investmentOtherCost": {"name": "15.2.5其他费用概算表", "headers": []},
        "financialIndicatorSummary": {"name": "附表16.1  财务指标汇总表", "headers": []},
        "financeInvestmentPlanFunding": {"name": "附表16.2：项目总投资使用计划与资金筹措表（人民币单位：万元）", "headers": []},
        "financeTotalCostEstimate": {"name": "附表16.3：总成本费用估算表（人民币单位：万元）", "headers": []},
        "financeTotalCostEstimateContinuation": {"name": "附表16.3：总成本费用估算表（续）（人民币单位：万元）", "headers": []},
        "financeDepreciationAmortization": {"name": "附表16.4：资产折旧摊销估算表（人民币单位：万元）", "headers": []},
        "financeDepreciationAmortizationContinuation": {"name": "附表16.4：资产折旧摊销估算表（续）（人民币单位：万元）", "headers": []},
        "financeProfitDistribution": {"name": "附表16.5：利润与利润分配表（人民币单位：万元）", "headers": []},
        "financeProfitDistributionContinuation": {"name": "附表16.5：利润与利润分配表（续）（人民币单位：万元）", "headers": []},
        "financeLoanRepayment": {"name": "附表16.6：借款还本付息计划表（人民币单位：万元）", "headers": []},
        "financeLoanRepaymentContinuation": {"name": "附表16.6：借款还本付息计划表（续）（人民币单位：万元）", "headers": []},
        "financeCashFlowPlan": {"name": "附表16.7：财务计划现金流量表（人民币单位：万元）", "headers": []},
        "financeCashFlowPlanContinuation": {"name": "附表16.7：财务计划现金流量表（续）（人民币单位：万元）", "headers": []},
        "financeProjectInvestmentCashFlow": {"name": "附表16.8：项目投资现金流量表（人民币单位：万元）", "headers": []},
        "financeProjectInvestmentCashFlowContinuation": {"name": "附表16.8：项目投资现金流量表（续）（人民币单位：万元）", "headers": []},
        "financeCapitalCashFlow": {"name": "附表16.9：项目资本金现金流量表（人民币单位：万元）", "headers": []},
        "financeCapitalCashFlowContinuation": {"name": "附表16.9：项目资本金现金流量表（续）（人民币单位：万元）", "headers": []},
        "financeInvestorCashFlowParty1": {"name": "附表16.10：投资各方现金流量表（投资方1）（人民币单位：万元）", "headers": []},
        "financeInvestorCashFlowParty1Continuation": {"name": "附表16.10：投资各方现金流量表（投资方1）（续）（人民币单位：万元）", "headers": []},
        "financeBalanceSheet": {"name": "附表16.11：资产负债表（人民币单位：万元）", "headers": []},
        "financeBalanceSheetContinuation": {"name": "附表16.11：资产负债表（续）（人民币单位：万元）", "headers": []},
    }

    SECTION_ORDER = list(CONFIG_SECTION_ORDER)

    COMMON_SECTION_FIELDS = {
        "projectName",
        "investmentOwnerCompany",
        "projectAddressCity",
        "projectAddressCounty",
        "projectAddressTown",
        "projectAddressDetail",
        "designUnit",
        "designUnitQualification",
    }

    INVESTMENT_TABLE_PATTERNS = {
        "investmentTechnicalEconomicIndicators": [r"主要技术经济指标表", r"(?:表\s*[一二三四五六七八九十]+|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*主要技术经济指标表"],
        "investmentEstimate": [r"工程总概算表", r"(?:表\s*一|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*工程总概算表"],
        "investmentConstructionAuxiliary": [r"施工辅助工程概算表", r"(?:表\s*二|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*施工辅助工程概算表"],
        "investmentEquipmentInstallation": [r"设备及安装工程概算表", r"(?:表\s*三|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*设备及安装工程概算表"],
        "investmentBuilding": [r"建筑工程概算表", r"(?:表\s*四|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*建筑工程概算表"],
        "investmentOtherCost": [r"其他费用概算表", r"(?:表\s*五|\d+(?:\.\d+)*(?:-\d+)?\.?)\s*其他费用概算表"],
    }

    FINANCE_TABLE_PATTERNS = {
        "financialIndicatorSummary": [r"附表\s*(?:16\.)?1\s*[：:]?\s*财务指标汇总表"],
        "financeInvestmentPlanFunding": [r"附表\s*(?:16\.)?2\s*[：:]?\s*项目总投资使用计划与资金筹措表"],
        "financeTotalCostEstimate": [r"附表\s*(?:16\.)?3\s*[：:]?\s*总成本费用估算表(?![^\n]*续)"],
        "financeTotalCostEstimateContinuation": [r"附表\s*(?:16\.)?3\s*[：:]?\s*总成本费用估算表[^\n]*续"],
        "financeDepreciationAmortization": [r"附表\s*(?:16\.)?4\s*[：:]?\s*资产折旧摊销估算表(?![^\n]*续)"],
        "financeDepreciationAmortizationContinuation": [r"附表\s*(?:16\.)?4\s*[：:]?\s*资产折旧摊销估算表[^\n]*续"],
        "financeProfitDistribution": [r"附表\s*(?:16\.)?5\s*[：:]?\s*利润与利润分配表(?![^\n]*续)"],
        "financeProfitDistributionContinuation": [r"附表\s*(?:16\.)?5\s*[：:]?\s*利润与利润分配表[^\n]*续"],
        "financeLoanRepayment": [r"附表\s*(?:16\.)?6\s*[：:]?\s*借款还本付息计划表(?![^\n]*续)"],
        "financeLoanRepaymentContinuation": [r"附表\s*(?:16\.)?6\s*[：:]?\s*借款还本付息计划表[^\n]*续"],
        "financeCashFlowPlan": [r"附表\s*(?:16\.)?7\s*[：:]?\s*财务计划现金流量表(?![^\n]*续)"],
        "financeCashFlowPlanContinuation": [r"附表\s*(?:16\.)?7\s*[：:]?\s*财务计划现金流量表[^\n]*续"],
        "financeProjectInvestmentCashFlow": [r"附表\s*(?:16\.)?8\s*[：:]?\s*项目投资现金流量表(?![^\n]*续)"],
        "financeProjectInvestmentCashFlowContinuation": [r"附表\s*(?:16\.)?8\s*[：:]?\s*项目投资现金流量表[^\n]*续"],
        "financeCapitalCashFlow": [r"附表\s*(?:16\.)?9\s*[：:]?\s*项目资本金现金流量表(?![^\n]*续)"],
        "financeCapitalCashFlowContinuation": [r"附表\s*(?:16\.)?9\s*[：:]?\s*项目资本金现金流量表[^\n]*续"],
        "financeInvestorCashFlowParty1": [r"附表\s*(?:16\.)?10\s*[：:]?\s*投资各方现金流量表[^\n]*投资方\s*1(?![^\n]*续)"],
        "financeInvestorCashFlowParty1Continuation": [r"附表\s*(?:16\.)?10\s*[：:]?\s*投资各方现金流量表[^\n]*投资方\s*1[^\n]*续"],
        "financeBalanceSheet": [r"附表\s*(?:16\.)?11\s*[：:]?\s*资产负债表(?![^\n]*续)"],
        "financeBalanceSheetContinuation": [r"附表\s*(?:16\.)?11\s*[：:]?\s*资产负债表[^\n]*续"],
    }

    REQUIRED_SECTION_SCHEMA = deepcopy(CONFIG_REQUIRED_SECTION_SCHEMA)

    REQUIRED_FIELD_META = deepcopy(CONFIG_REQUIRED_FIELD_META)

    REQUIRED_TABLE_SCHEMAS = {
        "generationSummary": (
            "表5.3-1 风电场工程推荐方案发电量计算表",
            [("nonWakeLossFactor", "不考虑尾流效应的折减系数%")],
        ),
        "collectorLineTechnical": (
            "集电线路技术参数表",
            [
                ("layingMethod", "线路敷设方式"),
                ("circuitCount", "回路数（回）"),
                ("ratedVoltage", "线路额定电压"),
                ("circuit", "回路"),
                ("totalLength", "线路总长度"),
                ("doubleCircuitOverheadLength", "双回架空线路路径长"),
                ("singleCircuitOverheadLength", "单回架空线路路径长"),
                ("towerFoundationCount", "全线共用铁塔基数"),
                ("cableLength", "电缆长度"),
            ],
        ),
        "substationCivil": (
            "表9.7-1 升压站主要土建工程量表",
            [
                ("totalArea", "总占地面积"),
                ("insideWallArea", "围墙内占地面积"),
            ],
        ),
        "windFoundationConstruction": (
            "表9.4-5 基础断面表",
            [],
        ),
        "boxFoundationTechnical": (
            "表9.5-1 箱变基础单台工程量表（配事故油池）",
            [],
        ),
        "earthworkBalance": (
            "表10.2-2土石方平衡表（万m(3)）",
            [],
        ),
        "investmentConstructionAuxiliary": (
            "15.2.2 施工辅助工程概算表",
            [],
        ),
        "investmentEquipmentInstallation": (
            "15.2.3设备及安装工程概算表",
            [],
        ),
        "investmentBuilding": (
            "15.2.4建筑工程概算表",
            [],
        ),
        "investmentOtherCost": (
            "15.2.5其他费用概算表",
            [],
        ),
        "financialIndicatorSummary": (
            "附表16.1  财务指标汇总表",
            [],
        ),
        "financeInvestmentPlanFunding": (
            "附表16.2：项目总投资使用计划与资金筹措表（人民币单位：万元）",
            [],
        ),
        "financeTotalCostEstimate": (
            "附表16.3：总成本费用估算表（人民币单位：万元）",
            [],
        ),
        "financeTotalCostEstimateContinuation": (
            "附表16.3：总成本费用估算表（续）（人民币单位：万元）",
            [],
        ),
        "financeDepreciationAmortization": (
            "附表16.4：资产折旧摊销估算表（人民币单位：万元）",
            [],
        ),
        "financeDepreciationAmortizationContinuation": (
            "附表16.4：资产折旧摊销估算表（续）（人民币单位：万元）",
            [],
        ),
        "financeProfitDistribution": (
            "附表16.5：利润与利润分配表（人民币单位：万元）",
            [],
        ),
        "financeProfitDistributionContinuation": (
            "附表16.5：利润与利润分配表（续）（人民币单位：万元）",
            [],
        ),
        "financeLoanRepayment": (
            "附表16.6：借款还本付息计划表（人民币单位：万元）",
            [],
        ),
        "financeLoanRepaymentContinuation": (
            "附表16.6：借款还本付息计划表（续）（人民币单位：万元）",
            [],
        ),
        "financeCashFlowPlan": (
            "附表16.7：财务计划现金流量表（人民币单位：万元）",
            [],
        ),
        "financeCashFlowPlanContinuation": (
            "附表16.7：财务计划现金流量表（续）（人民币单位：万元）",
            [],
        ),
        "financeProjectInvestmentCashFlow": (
            "附表16.8：项目投资现金流量表（人民币单位：万元）",
            [],
        ),
        "financeProjectInvestmentCashFlowContinuation": (
            "附表16.8：项目投资现金流量表（续）（人民币单位：万元）",
            [],
        ),
        "financeCapitalCashFlow": (
            "附表16.9：项目资本金现金流量表（人民币单位：万元）",
            [],
        ),
        "financeCapitalCashFlowContinuation": (
            "附表16.9：项目资本金现金流量表（续）（人民币单位：万元）",
            [],
        ),
        "financeInvestorCashFlowParty1": (
            "附表16.10：投资各方现金流量表（投资方1）（人民币单位：万元）",
            [],
        ),
        "financeInvestorCashFlowParty1Continuation": (
            "附表16.10：投资各方现金流量表（投资方1）（续）（人民币单位：万元）",
            [],
        ),
        "financeBalanceSheet": (
            "附表16.11：资产负债表（人民币单位：万元）",
            [],
        ),
        "financeBalanceSheetContinuation": (
            "附表16.11：资产负债表（续）（人民币单位：万元）",
            [],
        ),
        "roadTechnical": (
            "道路原表",
            [],
        ),
        "roadParameters": (
            "道路参数组合表",
            [
                ("accessRoadLength", "进站道路长度（km）"),
                ("siteEntryRoadLength", "进场道路长度（km）"),
                ("accessRoadSubgradeWidth", "进站道路路基宽度（m）"),
                ("accessRoadPavementWidth", "进站道路路面宽度（m）"),
                ("newRoadLength", "新建道路长度（km）"),
                ("rebuiltRoadLength", "改建道路长度（km）"),
                ("subgradeWidth", "路基宽度（m）"),
                ("pavementWidth", "路面宽度（m）"),
                ("siteRoadLength", "场内道路长度（km）"),
                ("maintenanceRoadLength", "检修道路长度（km）"),
                ("maintenanceRoadSubgradeWidth", "检修道路路基宽度（m）"),
                ("maintenanceRoadPavementWidth", "检修道路路面宽度（m）"),
            ],
        ),
        "permanentLandArea": (
            "表10.4-1 工程征用地计算合计表",
            [],
        ),
        "longTermLeaseArea": (
            "长期租地面积表",
            [("category", "长期租地项目"), ("item", "项目"), ("area", "面积（m²）"), ("compensationCategory", "临征永补项目"), ("compensationItem", "项目"), ("compensationArea", "面积（m²）")],
        ),
        "temporaryLandArea": (
            "临时性占地面积表",
            [("item", "临时性占地项目"), ("road", "风场道路"), ("platform", "吊装平台"), ("collectorLine", "集电线路"), ("directBuriedCable", "电缆直埋"), ("constructionSite", "施工临建场地"), ("total", "合计")],
        ),
        "earthworkBalance": ("土石方平衡表", [("item", "项目"), ("excavation", "土方开挖m³"), ("backfill", "土方回填m³")]),
        "investmentEstimate": (
            "15.2.1工程总概算表",
            [],
        ),
        "financingAssumptions": (
            "建设资金参数表",
            [
                ("constructionPeriodYears", "建设期（年）"),
                ("projectTotalInvestment", "项目总投资（万元）"),
                ("totalCost", "总成本费用（万元）"),
                ("workingCapital", "流动资金金额（万元）"),
                ("workingCapitalUnitKwIndicator", "流动资金单位千瓦指标（元/KW）"),
                ("workingCapitalLoanRatio", "流动资金贷款比例%"),
                ("workingCapitalCapitalRatio", "流动资本金比例%"),
                ("workingCapitalLoanInterestRate", "流动资金贷款利率%"),
                ("constructionCapitalRatio", "建设资本金比例%"),
                ("constructionFundLoanRatio", "建设资金贷款比例%"),
                ("repaymentMethod", "还款方式"),
                ("repaymentPeriod", "偿还年限（年）"),
                ("annualLoanInterestRate", "年贷款利率"),
            ],
        ),
        "staffingCost": (
            "人员费用表",
            [("staffingCount", "定员人数（人）"), ("staffSalary", "人员工资"), ("welfareOtherRatio", "职工福利费及其他占比（%）")],
        ),
        "financialEvaluation": (
            "财务评价表",
            [
                ("insuranceRate", "保险费率"),
                ("depreciationYears", "折旧年限（年）"),
                ("salvageRate", "残值率%"),
                ("repairCost", "修理费（元/KW）"),
                ("materialCostPerKw", "材料费（元/KW）"),
                ("materialCost", "材料费（万元）"),
                ("otherCost", "其他费用"),
                ("landUseTax", "土地使用税"),
                ("windFarmGridPrice", "风电场上网电价（元/kWh）"),
                ("incomeTax", "所得税（万元）"),
            ],
        ),
    }

    TABLE_FIELD_SOURCES = {
        "collectorLineTechnical": ["collectorVoltageLevel", "collectorCircuitType", "collectorLineLength", "doubleCircuitOverheadLength", "singleCircuitOverheadLength", "towerFoundationCount"],
        "substationCivil": ["substationVoltageLevel", "substationTotalArea", "substationInsideWallArea", "substationVerticalDesign", "substationRoadLayoutType"],
        "windFoundationConstruction": ["foundationType", "pileSectionRadius", "pileRingCount", "pilesPerRing", "windFoundationConcreteQuantity", "windFoundationRebarQuantity"],
        "boxFoundationTechnical": ["boxFoundationConcreteC25Quantity", "boxFoundationRebarQuantity"],
        "roadParameters": ["accessRoadLength", "siteRoadLength", "newRoadLength", "rebuiltRoadLength", "maintenanceRoadLength", "maintenanceRoadSubgradeWidth", "maintenanceRoadPavementWidth"],
        "investmentEstimate": ["totalProjectCost", "equipmentPurchaseCost", "installationCost", "constructionCost", "mainEquipmentUnitPrice", "materialPriceLevel", "unitKwStaticInvestment", "dynamicInvestment"],
        "financingAssumptions": ["constructionPeriodYears", "workingCapital", "workingCapitalUnitKwIndicator", "workingCapitalLoanRatio", "workingCapitalCapitalRatio", "workingCapitalLoanInterestRate", "constructionCapitalRatio", "constructionFundLoanRatio", "repaymentMethod", "repaymentPeriod", "annualLoanInterestRate"],
        "staffingCost": ["staffingCount", "staffSalary", "welfareOtherRatio"],
        "financialEvaluation": ["insuranceRate", "depreciationYears", "salvageRate", "repairCost", "materialCostPerKw", "materialCost", "otherCost", "landUseTax", "windFarmGridPrice", "incomeTax"],
    }

    FIELD_TABLE_COLUMN_MAP = {
        "windFoundationTechnical": {
            "foundationCapBottomRadius": "capBottomRadius",
            "foundationTopRadius": "topRadius",
            "foundationColumnRadius": "columnRadius",
            "foundationOuterEdgeHeight": "outerEdgeHeight",
            "foundationConeHeight": "coneHeight",
            "foundationColumnHeight": "columnHeight",
            "foundationBuriedDepth": "buriedDepth",
            "pileOuterDiameter": "pileDiameter",
            "pileLength": "averagePileLength",
        }
    }
