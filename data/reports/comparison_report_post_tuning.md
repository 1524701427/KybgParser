# Feasibility Report Parsing Comparison Post Tuning

Result JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_result.json`
Detail JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_details.json`

## Summary
- Detail status counts: {'PASS': 113, 'WARNING': 3, 'MISSING': 49}
- Scalar comparison: total=85, OK=30, WRONG=35, MISSING=20.
- result.details keys: ['earthworkBalance']

## Detail Table Check
| detail | expected rows | actual rows |
|---|---:|---:|
| windResourceTowers | 6 | 0 |
| earthworkBalance | 6 | 6 |
| permanentLandArea | 1 | 0 |
| longTermLeaseArea | 1 | 0 |
| temporaryLandArea | 1 | 0 |

## Correct Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| annualEnergy | 年上网电量 | 47521.1 万kW·h | 47521.1  | 4 工程任务和规模 / 5.3 年上网电量估算 | 年上网电量 | 万kW·h | 47521.1  |
| equivalentHours | 等效满负荷小时数 | 2376 h | 2376 h | 4 工程任务和规模 / 5.3 年上网电量估算 | 7 | 年等效满负荷小时数 | h | 2376 |
| collectorLineLength | 集电线路长度 | 81.6 km | 81.6  | 6  电 气 / 6.6 集电线路 | 总长 | 81.6 |  |
| substationTotalArea | 总占地面积 | 6700 m2 | 6700 m2 | 9 土建工程 / 9.7 升压站 | 总占地面积为6700㎡ |
| substationInsideWallArea | 围墙内占地面积 | 5952 m2 | 5952 m2 | 9 土建工程 / 9.7 升压站 | 围墙内占地面积5952㎡ |
| substationVerticalDesign | 站区竖向设计 | 平坡式  | 采取平坡式  | 9 土建工程 / 9.7 升压站 | 站区竖向设计采取平坡式 |
| foundationBuriedDepth | 基础埋深 | 2.8 m | 2.8 m | 9 土建工程 / 9.4 风电机组基础设计 / 9.4.3 风机基础设计方案 | 基础埋深 | m | 2.8 |
| accessRoadLength | 进站道路工程量 | 0.4 km | 0.4 km | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 1.3 | 进站道路 | km | 0.40 | 进站门前20m采用混凝土路面硬化，其余段落为泥结碎石路面 |
| newRoadLength | 新建道路长度 | 23.1 km | 23.1  | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 新建道路 | km | 23.1  |
| rebuiltRoadLength | 改建道路长度 | 99.7 km | 99.7  | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 改建道路 | km | 99.7  |
| permanentLandCollectorTowerArea | 永久占地-集电线路杆塔征地 | 10584 m2 | 10584 m2 | 10 施工组织设计 / 10.4 工程占地 | 集电线路杆塔征地 | m2 | 10584 |  |
| permanentLandAccessRoadArea | 永久占地-进升压站道路 | 120 m2 | 120 m2 | 10 施工组织设计 / 10.4 工程占地 | 进升压站道路 | m2 | 120 |  |
| longTermLeaseCableBuriedArea | 长期租地-电缆直埋征地 | 2373 m2 | 2373 m2 | 10 施工组织设计 / 10.4 工程占地 | 电缆直埋征地(宽1m） | m2 | 2373 | 1m宽 |
| longTermLeasePermanentRoadArea | 长期租地-场内永久道路 | 103950 m2 | 103950 m2 | 10 施工组织设计 / 10.4 工程占地 | 场内永久道路 | m2 | 103950 |  |
| longTermLeaseAccessRoadArea | 长期租地-进站道路 | 1560 m2 | 1560 m2 | 10 施工组织设计 / 10.4 工程占地 | 进站道路 | m2 | 1560 |  |
| temporaryLandPlatformArea | 临时占地-场内平整安装平台 | 91501 m2 | 91501 m2 | 10 施工组织设计 / 10.4 工程占地 | 场地平整（安装平台） | m2 | 91501 | 每个平台占地2743平米，实际可利用面积2400平米 |
| temporaryLandConstructionRoadArea | 临时占地-临时施工道路 | 314900 m2 | 314900 m2 | 10 施工组织设计 / 10.4 工程占地 | 临时施工道路 | m2 | 314900 | 施工道路宽度减去永久道路宽度 |
| temporaryLandLivingArea | 临时占地-生活临建 | 9600 m2 | 9600 m2 | 10 施工组织设计 / 10.4 工程占地 | 生活临建 | m2 | 9600 |  |
| windPlatformEarthworkExcavation | 风机平台土方开挖 | 327450 m3 | 327450  | 10 施工组织设计 / 10.2 施工总布置 | 风机平台 | 327450 | 245588 | 81862 |  |
| windPlatformEarthworkBackfill | 风机平台土方回填 | 245588 m3 | 245588  | 10 施工组织设计 / 10.2 施工总布置 | 风机平台 | 327450 | 245588 | 81862 |  |
| windFoundationEarthworkExcavation | 风机基础土方开挖 | 34262 m3 | 34262  | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| windFoundationEarthworkBackfill | 风机基础土方回填 | 16687 m3 | 16687  | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| boxFoundationEarthworkExcavation | 箱变基础土方开挖 | 2400 m3 | 2400  | 10 施工组织设计 / 10.2 施工总布置 | 箱变基础 | 2400 | 1400 | 1000 |  |
| boxFoundationEarthworkBackfill | 箱变基础土方回填 | 1400 m3 | 1400  | 10 施工组织设计 / 10.2 施工总布置 | 箱变基础 | 2400 | 1400 | 1000 |  |
| totalProjectCost | 总费用 | 128313.98 万元 | 128313.98 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 工程总投资 | 万元 | 128313.98 | 建筑用地面积 | 永久用地 | 亩 | 45.6 |
| equipmentPurchaseCost | 设备购置费 | 48826.4 万元 | 48826.4 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 设备购置费（万元） | 48826.40 |
| materialCost | 材料费 | 3800 万元 | 3800  | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 1 | 材料费 | 3800 | 0 | 100 | 100 | 100 | 100 | 100 | 220 | 220 | 220 | 220 | 220 | 220 | 220 |
| projectInvestmentIrrBeforeTax | 项目投资财务内部收益率所得税前 | 8.76 % | 8.76 % | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 14 | 项目投资财务内部收益率（所得税前） | % | 8.76 |
| projectInvestmentIrrAfterTax | 项目投资财务内部收益率所得税后 | 7.55 % | 7.55 % | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 15 | 项目投资财务内部收益率（所得税后） | % | 7.55 |
| capitalIRR | 资本金财务内部收益率 | 12.09 % | 12.09 % | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 18 | 资本金财务内部收益率 | % | 12.09 |

## Wrong Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| maxWindSpeed50Year | 50年一遇最大风速 | 26.93 m/s | 110  | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 50年一遇最大风速 | 标况110 |
| theoreticalAnnualEnergy | 年理论发电量 | 67447.2 万kW·h | 5.1  | 4 工程任务和规模 / 5.1 风力发电机组选型 / 5.1.3 风电机组选型 | 根据比选机型最终布置方案，采用各测风塔年测风数据，依据风机厂商提供的当地空气密度下的动态功率曲线和推力系数曲线，采用WT软件计算风电机组的理论发电量和尾流后发电量，参照本阶段风电机组的报价情况，对比选机型进行了技术经济比较，结果见表5.1.3-1。 |
| nonWakeLossFactor | 不考虑尾流效应的折减系数 | 73.65 % | 97 % | 4 工程任务和规模 / 5.3 年上网电量估算 | 折减系数取97% |
| mainConnectionType | 主接线形式 | 单母线接线  | 接线简单清晰，继电保护简单； 设备较少，有效减少投资； 接地变容量小，仅考虑一台主变对应电容电流；  | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.1 升压站电气主接线 | 单母线接线 | 接线简单清晰，继电保护简单； 设备较少，有效减少投资； 接地变容量小，仅考虑一台主变对应电容电流； |
| mainTransformerType | 主变压器 | 三相双绕组油浸自冷式有载调压变压器  | 480  | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 主变压器 | 480 | 550 | 530 | 200 | 185 |
| mainTransformerCapacity | 主变容量 | 110 MVA | 2  | 6  电 气 / 6.3 电气一次 / 6.4.4 升压站设计 / 6.4.4.5 设备状态监测 | 主变容量为2 |
| stationTransformerCapacity10kv | 10kV站用变容量 | 315 kVA | 为315kVA  | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.2 主要电气设备参数 | 站用变容量为315kVA |
| independentLightningRodCount | 独立避雷针个数 | 2 座 | 1 座 | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 独立避雷针及1座 |
| frameLightningRodCount | 构架避雷针个数 | 1 座 | 110  | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 构架避雷针进行联合保护。110 |
| collectorCircuitType | 回路 | 单/双回路架设  | 耐张塔电缆引上安装材料（终端型  | 6  电 气 / 6.6 集电线路 / 6.6.4 沿线地形、地质及交通情况 / 6.6.11.1 杆塔主要设计原则 | 回路耐张塔电缆引上安装材料（终端型 |
| doubleCircuitOverheadLength | 双回架空线路路径长 | 2x3.6 km | 约2×3.6km  | 6  电 气 / 6.6 集电线路 | 双回架空线路路径长约2×3.6km |
| singleCircuitOverheadLength | 单回架空线路路径长 | 1x78 km | 约1×78km  | 6  电 气 / 6.6 集电线路 | 单回架空线路路径长约1×78km |
| collectorLineNames | 线路名称 | A-H  | 总长  | 6  电 气 / 6.6 集电线路 | 线路名称 | 总长 |
| foundationType | 风机基础型式 | 桩基础  | 1 | 一次设备预制舱 | 预制舱 | 丙类 | 三级 | 6 | 6 | 二级 | 箱型  | 9 土建工程 / 9.7 升压站 / 9.7.2.1 设计依据 / 9.7.3.2 主要建筑物 | 基础形式 1 | 一次设备预制舱 | 预制舱 | 丙类 | 三级 | 6 | 6 | 二级 | 箱型 |
| permanentLandWindFoundationArea | 永久占地-风机基础 | 8695 m2 | 34262  | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| permanentLandBoxTransformerArea | 永久占地-箱变基础 | 1200 m2 | 2400  | 10 施工组织设计 / 10.2 施工总布置 | 箱变基础 | 2400 | 1400 | 1000 |  |
| permanentLandSubstationArea | 永久占地-110kV升压站 | 9800 m2 | 22500  | 10 施工组织设计 / 10.2 施工总布置 | 升压站 | 22500 | 22500 | 0 |  |
| permanentLandTotalArea | 永久占地合计 | 30399 m2 | 9600 m2 | 10 施工组织设计 / 10.2 施工总布置 | 合计 | 9600m2 |
| longTermLeaseTotalArea | 长期租地合计 | 107883 m2 | 9600 m2 | 10 施工组织设计 / 10.2 施工总布置 | 合计 | 9600m2 |
| temporaryLandTotalArea | 临时性占地合计 | 416001 m2 | 9600 m2 | 10 施工组织设计 / 10.2 施工总布置 | 合计 | 9600m2 |
| roadEarthworkExcavation | 道路土方开挖 | 1048836 m3 | 624  | 10 施工组织设计 / 10.4 工程占地 | 施工道路宽度减去永久道路宽度 | 624.0亩 |
| roadEarthworkBackfill | 道路土方回填 | 1149523 m3 | 624  | 10 施工组织设计 / 10.4 工程占地 | 施工道路宽度减去永久道路宽度 | 624.0亩 |
| substationEarthworkExcavation | 升压站土方开挖 | 22500 m3 | 6  |  | 3 | 升压站电气主接线图 | 附图6-1 | 1 |
| substationEarthworkBackfill | 升压站土方回填 | 22500 m3 | 6  |  | 3 | 升压站电气主接线图 | 附图6-1 | 1 |
| totalEarthworkExcavation | 合计土方开挖 | 1435228 m3 | 53931.92  | 6  电 气 / 6.7 送电线路 / 6.7.19 主要材料 | 合计（kg） | 53931.92 |
| totalEarthworkBackfill | 合计土方回填 | 1435698 m3 | 53931.92  | 6  电 气 / 6.7 送电线路 / 6.7.19 主要材料 | 合计（kg） | 53931.92 |
| installationCost | 安装费 | 5748.89 万元 | 48826.4  | 15 设计概算 / 15.1.2.1 编制原则 / 15.2.2 施工辅助工程概算表 | 序号 | 项目名称及规格 | 单位 | 数量 | 单价（元） | 合价（万元） | 合计   （万元）  |  |  |  | 设备购置费 | 安装工程费 | 设备购置费 | 安装工程费 |   |  |  |  |  | 安装费 | 装置性材料费 |  | 安装费 | 装置性材料费 | 小计 |   | 第二部分 设备及安装工程 |  |  |  |
| constructionCost | 施工费 | 1542.64 万元 | 28260.05 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 建筑及安装工程费（万元） | 28260.05 |
| unitKwStaticInvestment | 单位千瓦静态投资 | 6320.57 元/kW | 7346 元/kW | 4 工程任务和规模 / 5.1 风力发电机组选型 / 5.1.3 风电机组选型 | 9 | 单位千瓦静态投资 | 元/kW | 7346 | 7367 | 7388 | 7413 | 7430 | 7197 | 7136 | 7179 |
| dynamicInvestment | 动态投资 | 6415.7 元/kW | 67.16  | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 占总投资比例（%） | 67.16% |
| constructionPeriodYears | 建设期 | 1 年 | 90390.55  | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 建设期 | 90390.55 |
| workingCapital | 流动资金 | 1600 万元 | 2.1  | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 流动资金借款 | 负债小计（2.1+2.2+2.3+2.4） |
| staffSalary | 人员工资 | 23.84 万元/人年 | 按23.84万元计  | 16 财务评价与社会效果分析 | 人均年工资按23.84万元计 |
| lcoe | 度电成本 | 0.3345 元/kWh | 6.2  | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 上网电价电价市场化变化分析（%） | 12.25 | 6.2 | 8.86 | 12.25 |
| incomeTax | 所得税 | 24040.44 万元 | 21970.6 万元 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 16 | 项目投资财务净现值（所得税前） | 万元 | 21970.60 |

## Missing Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| selectedTurbineSafetyClass | 最终宜选机型 | IECIIIa+  | None  |  |  |
| wakeLossPercent | 尾流平均折减 | -4.28 % | None  |  |  |
| substationMainConnectionPlannedCapacity | 升压站电气主接线规划总规模 | 200 MW | None  |  |  |
| substationMainConnectionCurrentCapacity | 升压站电气主接线本期规模 | 200 MW | None  |  |  |
| mainTransformerRatio | 主变压器变比 | 115±8×1.25%/37kV  | None  |  |  |
| svgReactiveCompensationCapacity | SVG无功补偿装置容量 | ±30Mvar Mvar | None  |  |  |
| groundingTransformerCapacity35kv | 35kV接地变用变容量 | 500 kVA | None  |  |  |
| groundingStationTransformerCapacity35kv | 35kV接地变兼站用变容量 | 800/315 kVA | None  |  |  |
| collectorVoltageLevel | 集电线路电压等级 | 35 kV | None  |  |  |
| towerFoundationCount | 全线共用铁塔基数 | 316 基 | None  |  |  |
| substationRoadLayoutType | 升压站内道路布置类型 | 环形道路  | None  |  |  |
| substationFunctionalZones | 升压站包含生活区和生产区 | 包含生活区和生产区  | None  |  |  |
| foundationCapBottomRadius | 基础承台底面半径 | 8.5 m | None  |  |  |
| pileRingCount | 桩圈数 | 两圈  | None  |  |  |
| pilesPerRing | 每圈桩数 | 第一圈布置4根，第二圈布置20根  | None  |  |  |
| boxFoundationConcreteC25Quantity | 箱变基础混凝土量C25 | 25 m3 | None  |  |  |
| boxFoundationRebarQuantity | 箱变基础钢筋工程量 | 0.5 t | None  |  |  |
| repaymentPeriod | 偿还年限 | 15 年 | None  |  |  |
| staffingCount | 定员人数 | 15 人 | None  |  |  |
| welfareOtherRatio | 职工福利费及其他占比 | 70 % | None  |  |  |

## Multi-value Fields
| code | field | expected count | actual | status |
|---|---|---:|---|---|
| metTowerCode | 测风塔编号 | 6 | None | MISSING |
| airDensityAtHeight | 高度对应的空气密度 | 6 | [3] | WRONG |
| hubHeightAnnualAverageWindSpeed | 轮毂高度年平均风速 | 6 | [35] | WRONG |
| hubHeightWindPowerDensity | 轮毂高度平均风功率密度 | 6 | [163] | WRONG |
| hubHeightMainWindDirection | 轮毂高度处的主风向 | 6 | None | MISSING |
| hubHeightMainWindEnergyDirection | 轮毂高度处的主风能方向 | 6 | None | MISSING |
| representativeTurbulenceIntensity | 最大高度处代表性湍流强度 | 6 | 0.12 | WRONG |
| windShearExponent | 综合风切变 | 6 | 2.5 | WRONG |
| generationCalculationUsed | 发电量计算是否使用 | 6 | None | MISSING |
