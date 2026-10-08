# Latest Parse Audit

Detail JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_details.json`
Result JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_result.json`

Status counts: {'PASS': 141, 'WARNING': 2, 'MISSING': 22}

## Key fields
- turbineCount: (37, '台', 'PASS')
- boxTransformerCount: (37, '台', 'PASS')
- substationVoltageLevel: (110, 'kV', 'PASS')
- allInvestmentAfterTaxIRR: (7.55, '%', 'PASS')
- projectCapitalRatio: (30, '%', 'PASS')
- loanRatio: (70, '%', 'PASS')
- constructionFundLoanRatio: (70, '%', 'PASS')
- mainTransformerRatio: ('115±8×1.25%/37kV', None, 'PASS')
- svgReactiveCompensationCapacity: ('±30', 'Mvar', 'PASS')
- workingCapital: (1600, '万元', 'PASS')
- incomeTax: (24040.44, '万元', 'PASS')
- installationCost: (5748.89, '万元', 'PASS')
- selectedTurbineSafetyClass: ('IECIIIa+', None, 'PASS')
- foundationCapBottomRadius: (8.5, 'm', 'PASS')
- loanInterestRate: (4.2, '％', 'WARNING')
- paybackPeriod: (11.02, '年', 'PASS')
- dynamicInvestment: (6415.7, '元/kW', 'PASS')
- unitKwStaticInvestment: (6320.57, '元/kW', 'PASS')

## Missing (22)
- constructionStartDate: 开工时间
- operationDate: 投产时间
- ecologicalImpactConclusion: 生态环境影响结论
- projectNature: 项目性质
- metTowerCode: 测风塔编号
- hubHeightMainWindDirection: 轮毂高度处的主风向
- hubHeightMainWindEnergyDirection: 轮毂高度处的主风能方向
- generationCalculationUsed: 发电量计算是否使用
- dcBatteryConfiguration: 直流蓄电池配置
- upsPowerConfiguration: UPS电源配置
- communicationPowerDesign: 通讯电源设计
- pileSectionRadius: 桩界面半径
- foundationExcavationQuantity: 基础开挖量
- foundationBackfillQuantity: 基础回填量
- windFoundationConcreteQuantity: 风机基础混凝土量
- windFoundationRebarQuantity: 风机基础钢筋工程量
- mainEquipmentUnitPrice: 主要设备单价
- materialPriceLevel: 材料价格水平
- insuranceRate: 保险费率
- basicSnowPressure: 基本雪压
- nearestRoadDistance: 距既有道路距离
- turbineModel: 风机型号