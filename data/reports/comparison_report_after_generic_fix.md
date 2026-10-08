# Feasibility Report Parsing Comparison After Generic Fix

Result JSON: `data/predictions/?????????200MW???????????_result.json`
Detail JSON: `data/predictions/?????????200MW???????????_details.json`

## Summary
- Scalar comparison: total=85, OK=50, WRONG=15, MISSING=20.
- result.details keys: ['earthworkBalance']

## Improved Key Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| annualEnergy | 年上网电量 | 47521.1 万kW·h | 47521.1 万kWh | 4 工程任务和规模 / 5.3 年上网电量估算 / 年上网电量 / 万kW·h / 47521.1 /  |
| maxWindSpeed50Year | 50年一遇最大风速 | 26.93 m/s | 26.93 m/s | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 / 标况110m高度50年一遇最大风速 / max=26.93 / rows=6 / 0821# / 21.6 / 27.37 / 24.96 / 0822# / 20.1 / 25.47 / 23.23 / 0823# / 19.5 / 24.71 /  |
| theoreticalAnnualEnergy | 年理论发电量 | 67447.2 万kW·h | 67447.2 万kWh | 4 工程任务和规模 / 5.3 年上网电量估算 / 年发电量 [万kW·h] / sum=67447.2 / rows=1 / H07 / 561312.3 / 4127896.4 / 1732 / 113 / 1602.9 / 5.4 / -5.3 / 1518.0 / 5.28 / 0.19 |
| nonWakeLossFactor | 不考虑尾流效应的折减系数 | 73.65 % | 73.65 % | 4 工程任务和规模 / 5.3 年上网电量估算 / 综合折减后（综合折减系数为73.65% |
| mainConnectionType | 主接线形式 | 单母线接线 | 单母线接线 | 6  电 气 / 6.1 概述 / 6.1.1 工程规模及设计范围 / 2 / 110kV接线型式 / 单母线接线 |
| mainTransformerType | 主变压器 | 三相双绕组油浸自冷式有载调压变压器 | 三相双绕组油浸自冷式有载调压变压器 | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.6 主要电气一次设备表 / 1.1 / 主变压器 / 三相双绕组油浸自冷式有载调压变压器 / 台 / 2 /  |
| permanentLandTotalArea | 永久占地合计 | 30399 m2 | 30399 m2 | 10 施工组织设计 / 10.4 工程占地 / 永久性占地合计 / m2 / 30399 / 45.6亩 |
| longTermLeaseTotalArea | 长期租地合计 | 107883 m2 | 107883 m2 | 10 施工组织设计 / 10.4 工程占地 / 长期租地合计 / m2 / 107883 / 161.8亩 |
| temporaryLandTotalArea | 临时性占地合计 | 416001 m2 | 416001 m2 | 10 施工组织设计 / 10.4 工程占地 / 临时性占地合计 / m2 / 416001 / 624.0亩 |
| roadEarthworkExcavation | 道路土方开挖 | 1048836 m3 | 1048836 m3 | 10 施工组织设计 / 10.2 施工总布置 / 道路 / 1048836 / 1149523 / -100687 / 进场、场内、升压站、改建和新建道路 |
| constructionCost | 施工费 | 1542.64 万元 | 1542.64 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 / 一 / 施工辅助工程 /  / 1542.64 /  / 1542.64 / 1.20% |

## Wrong Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| mainTransformerCapacity | 主变容量 | 110 MVA | 100 MVA | 6  电 气 / 6.3 电气一次 / 6.4.4 升压站设计 / 6.4.4.5 设备状态监测 / 2×100MVA |
| independentLightningRodCount | 独立避雷针个数 | 2 座 | 1 座 | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 / 独立避雷针及1座 |
| frameLightningRodCount | 构架避雷针个数 | 1 座 | 110 座 | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 / 构架避雷针进行联合保护。110 |
| collectorCircuitType | 回路 | 单/双回路架设 | 耐张塔电缆引上安装材料（终端型 | 6  电 气 / 6.6 集电线路 / 6.6.4 沿线地形、地质及交通情况 / 6.6.11.1 杆塔主要设计原则 / 回路耐张塔电缆引上安装材料（终端型 |
| collectorLineNames | 线路名称 | A-H | 总长 | 6  电 气 / 6.6 集电线路 / 线路名称 / 总长 |
| foundationType | 风机基础型式 | 桩基础 | / 基础数量 / 小计 | 6  电 气 / 6.6 集电线路 / 6.6.4 沿线地形、地质及交通情况 / 6.6.11.1 杆塔主要设计原则 / 基础型式 / 基础数量 / 小计 |
| substationEarthworkExcavation | 升压站土方开挖 | 22500 m3 | 1048836 m3 | 10 施工组织设计 / 10.2 施工总布置 / 道路 / 1048836 / 1149523 / -100687 / 进场、场内、升压站、改建和新建道路 |
| substationEarthworkBackfill | 升压站土方回填 | 22500 m3 | 1149523 m3 | 10 施工组织设计 / 10.2 施工总布置 / 道路 / 1048836 / 1149523 / -100687 / 进场、场内、升压站、改建和新建道路 |
| installationCost | 安装费 | 5748.89 万元 | 48826.4 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.2.2 施工辅助工程概算表 / 第二部分 设备及安装工程 /  /  /  /  /  / 48826.40  |
| unitKwStaticInvestment | 单位千瓦静态投资 | 6320.57 元/kW | 7346 元/kW | 4 工程任务和规模 / 5.1 风力发电机组选型 / 5.1.3 风电机组选型 / 9 / 单位千瓦静态投资 / 元/kW / 7346 / 7367 / 7388 / 7413 / 7430 / 7197 / 7136 / 7179 |
| dynamicInvestment | 动态投资 | 6415.7 元/kW | 67.16 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 / 占总投资比例（%） / 67.16% |
| constructionPeriodYears | 建设期 | 1 年 | 90390.55 年 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 / 建设期 / 90390.55 |
| workingCapital | 流动资金 | 1600 万元 | 2.1 万元 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 / 流动资金借款 / 负债小计（2.1+2.2+2.3+2.4） |
| lcoe | 度电成本 | 0.3345 元/kWh | 6.2 元/kWh | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 / 上网电价电价市场化变化分析（%） / 12.25 / 6.2 / 8.86 / 12.25 |
| incomeTax | 所得税 | 24040.44 万元 | 21970.6 万元 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 / 16 / 项目投资财务净现值（所得税前） / 万元 / 21970.60 |

## Missing Fields
| code | field | expected | actual | evidence |
|---|---|---|---|---|
| selectedTurbineSafetyClass | 最终宜选机型 | IECIIIa+ |  |  |
| wakeLossPercent | 尾流平均折减 | -4.28 % |  |  |
| substationMainConnectionPlannedCapacity | 升压站电气主接线规划总规模 | 200 MW |  |  |
| substationMainConnectionCurrentCapacity | 升压站电气主接线本期规模 | 200 MW |  |  |
| mainTransformerRatio | 主变压器变比 | 115±8×1.25%/37kV |  |  |
| svgReactiveCompensationCapacity | SVG无功补偿装置容量 | ±30Mvar Mvar |  |  |
| groundingTransformerCapacity35kv | 35kV接地变用变容量 | 500 kVA |  |  |
| groundingStationTransformerCapacity35kv | 35kV接地变兼站用变容量 | 800/315 kVA |  |  |
| collectorVoltageLevel | 集电线路电压等级 | 35 kV |  |  |
| towerFoundationCount | 全线共用铁塔基数 | 316 基 |  |  |
| substationRoadLayoutType | 升压站内道路布置类型 | 环形道路 |  |  |
| substationFunctionalZones | 升压站包含生活区和生产区 | 包含生活区和生产区 |  |  |
| foundationCapBottomRadius | 基础承台底面半径 | 8.5 m |  |  |
| pileRingCount | 桩圈数 | 两圈 |  |  |
| pilesPerRing | 每圈桩数 | 第一圈布置4根，第二圈布置20根 |  |  |
| boxFoundationConcreteC25Quantity | 箱变基础混凝土量C25 | 25 m3 |  |  |
| boxFoundationRebarQuantity | 箱变基础钢筋工程量 | 0.5 t |  |  |
| repaymentPeriod | 偿还年限 | 15 年 |  |  |
| staffingCount | 定员人数 | 15 人 |  |  |
| welfareOtherRatio | 职工福利费及其他占比 | 70 % |  |  |