# Feasibility Report Parsing Comparison

Reference file: `可研报告解析（陕西华电靖边韩家沟200MW项目）.docx`
Result JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_result.json`
Detail JSON: `data\predictions\陕西华电靖边韩家沟200MW风电项目可行性研究报告_details.json`

## Summary

- Current detail status counts: {'PASS': 139, 'WARNING': 1, 'MISSING': 25}
- Compared scalar fields explicitly present in the reference docx: 85. OK=34, WRONG=39, MISSING=12.
- Current result.details keys: ['earthworkBalance'].
- The output is not empty, but many values are selected from chapter numbers, figure names, unrelated tables, or the first number in a compound specification.

## Detail Table Check

| detail | expected rows | actual rows | conclusion |
|---|---:|---:|---|
| windResourceTowers | 6 | 0 | missing: tower table is not exported |
| earthworkBalance | 6 | 95 | wrong: over-matched 95 unrelated rows |
| permanentLandArea | 1 | 0 | missing: permanent land table is not exported |
| longTermLeaseArea | 1 | 0 | missing: long-term lease table is not exported |
| temporaryLandArea | 1 | 0 | missing: temporary land table is not exported |

## Correct Fields

| code | field | expected | actual | evidence |
|---|---|---|---|---|
| annualEnergy | 年上网电量 | 47521.1 万kW·h | 47521.1 | 4 工程任务和规模 / 5.3 年上网电量估算 | 6 | 年上网电量 | 万kW·h | 47521.1 |
| equivalentHours | 等效满负荷小时数 | 2376 h | 2376 h | 1  综合说明 / 1.5 风电机组选型、布置及风电场发电量估算 | 陕西华电靖边韩家沟200MW风电项目推荐方案年上网电量为47521.1万kW·h，年等效满负荷小时数为2376h。 |
| stationTransformerCapacity10kv | 10kV站用变容量 | 315 kVA | 315 | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.2 主要电气设备参数 | 接地变变压器选用三相接地变压器，电阻柜选用成套设备，电阻丝采用优质材料。同时1#接地变考虑兼带站用变，站用变容量为315kVA，型号为DKSC-800kVA-315kVA/35kV，2#为接地变成套装置DKSC-500kVA-35kV。 |
| collectorCircuitType | 回路 | 单/双回路架设 | 单/双回路 | 6  电 气 / 6.6 集电线路 | （2）回路：单/双回路架设。 |
| doubleCircuitOverheadLength | 双回架空线路路径长 | 2x3.6 km | 2 | 6  电 气 / 6.6 集电线路 | 双回架空线路路径长约2×3.6km |
| singleCircuitOverheadLength | 单回架空线路路径长 | 1x78 km | 1 | 6  电 气 / 6.6 集电线路 | 单回架空线路路径长约1×78km |
| substationTotalArea | 总占地面积 | 6700 m2 | 6700 m2 | 9 土建工程 / 9.7 升压站 | 升压站总占地面积为6700㎡，围墙内占地面积5952㎡，其中生活区布置有生活预制舱、停车位、备品备件间、水泵房及消防水池、危废库及地下污水处理设备等；生产区布置有SVG室预制舱、主变压器、二次预制舱、35kV配电装置预制舱、配套接地变、消防小室、事故油池及户外配电设备等。 |
| substationInsideWallArea | 围墙内占地面积 | 5952 m2 | 5952 m2 | 9 土建工程 / 9.7 升压站 | 升压站总占地面积为6700㎡，围墙内占地面积5952㎡，其中生活区布置有生活预制舱、停车位、备品备件间、水泵房及消防水池、危废库及地下污水处理设备等；生产区布置有SVG室预制舱、主变压器、二次预制舱、35kV配电装置预制舱、配套接地变、消防小室、事故油池及户外配电设备等。 |
| substationVerticalDesign | 站区竖向设计 | 平坡式 | 采取平坡式 | 9 土建工程 / 9.7 升压站 | 站区竖向设计采取平坡式 |
| foundationBuriedDepth | 基础埋深 | 2.8 m | 2.8 m | 9 土建工程 / 9.4 风电机组基础设计 / 9.4.3 风机基础设计方案 | 基础埋深 | m | 2.8 |
| accessRoadLength | 进站道路工程量 | 0.4 km | 0.4 km | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 本项目新建进站道路0.4km（进站道路前20m采用混凝土路面，路基宽6.0m，路面宽4.0m；其余路段设计标准同场内道路）；场内道路122.8km，新建道路23.1km，改建道路99.7km；利用县乡道路74.2km。道路紧靠风电机组布置，以满足设备一次运输到位及大型履带式吊车的运行、基础施工及风机安装需要。根据风场地形条件及风机布置，路基设计宽度为5.5m， |
| newRoadLength | 新建道路长度 | 23.1 km | 23.1 km | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 1.2.1 | ① | 新建道路 | km | 23.1 |  |
| rebuiltRoadLength | 改建道路长度 | 99.7 km | 99.7 km | 1  综合说明 / 1.9 施工组织设计 | 本项目新建进站道路0.4km（进站道路前20m采用混凝土路面，路基宽6.0m，路面宽4.0m；其余路段设计标准同场内道路）；场内道路122.8km，新建道路23.1km，改建道路99.7km；利用县乡道路74.2km。道路紧靠风电机组布置，以满足设备一次运输到位及大型履带式吊车的运行、基础施工及风机安装需要。根据风场地形条件及风机布置，路基设计宽度为5.5m，采用级配良好的土填筑，施工期铺设 |
| permanentLandBoxTransformerArea | 永久占地-箱变基础 | 1200 m2 | 1200 m2 | 10 施工组织设计 / 10.4 工程占地 | 箱变基础 | m2 | 1200 |  |
| permanentLandCollectorTowerArea | 永久占地-集电线路杆塔征地 | 10584 m2 | 10584 m2 | 10 施工组织设计 / 10.4 工程占地 | 集电线路杆塔征地 | m2 | 10584 |  |
| permanentLandAccessRoadArea | 永久占地-进升压站道路 | 120 m2 | 120 m2 | 10 施工组织设计 / 10.4 工程占地 | 进升压站道路 | m2 | 120 |  |
| longTermLeaseCableBuriedArea | 长期租地-电缆直埋征地 | 2373 m2 | 2373 m2 | 10 施工组织设计 / 10.4 工程占地 | 电缆直埋征地(宽1m） | m2 | 2373 | 1m宽 |
| longTermLeasePermanentRoadArea | 长期租地-场内永久道路 | 103950 m2 | 103950 m2 | 10 施工组织设计 / 10.4 工程占地 | 场内永久道路 | m2 | 103950 |  |
| temporaryLandPlatformArea | 临时占地-场内平整安装平台 | 91501 m2 | 91501 m2 | 10 施工组织设计 / 10.4 工程占地 | 场地平整（安装平台） | m2 | 91501 | 每个平台占地2743平米，实际可利用面积2400平米 |
| temporaryLandConstructionRoadArea | 临时占地-临时施工道路 | 314900 m2 | 314900 m2 | 10 施工组织设计 / 10.4 工程占地 | 临时施工道路 | m2 | 314900 | 施工道路宽度减去永久道路宽度 |
| temporaryLandLivingArea | 临时占地-生活临建 | 9600 m2 | 9600 m2 | 10 施工组织设计 / 10.4 工程占地 | 生活临建 | m2 | 9600 |  |
| windPlatformEarthworkExcavation | 风机平台土方开挖 | 327450 m3 | 327450 | 10 施工组织设计 / 10.2 施工总布置 | 风机平台 | 327450 | 245588 | 81862 |  |
| windPlatformEarthworkBackfill | 风机平台土方回填 | 245588 m3 | 245588 | 10 施工组织设计 / 10.2 施工总布置 | 风机平台 | 327450 | 245588 | 81862 |  |
| windFoundationEarthworkExcavation | 风机基础土方开挖 | 34262 m3 | 34262 | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| windFoundationEarthworkBackfill | 风机基础土方回填 | 16687 m3 | 16687 | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| boxFoundationEarthworkBackfill | 箱变基础土方回填 | 1400 m3 | 1400 | 10 施工组织设计 / 10.2 施工总布置 | 箱变基础 | 2400 | 1400 | 1000 |  |
| equipmentPurchaseCost | 设备购置费 | 48826.4 万元 | 48826.4 万元 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 设备购置费（万元） | 48826.40 |
| unitKwStaticInvestment | 单位千瓦静态投资 | 6320.57 元/kW | 6320.57 元/kW | 1  综合说明 / 1.16 结论 |  | 单位千瓦静态投资 | 元/kW | 6320.57 |  |
| dynamicInvestment | 动态投资 | 6415.7 元/kW | 6415.7 | 15 设计概算 / 15.1.2.1 编制原则 / 15.1.9 主要技术经济指标表 | 单位千瓦动态投资 | 元/kW | 6415.7 | 总工期 | 月 | 12 |
| workingCapital | 流动资金 | 1600 万元 | 1600 万元 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 5 | 流动资金 | 万元 | 1600.00 |
| staffSalary | 人员工资 | 23.84 万元/人年 | 23.84 | 16 财务评价与社会效果分析 | 人均年工资按23.84万元计 |
| materialCost | 材料费 | 3800 万元 | 3800 | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 1 | 材料费 | 3800 | 0 | 100 | 100 | 100 | 100 | 100 | 220 | 220 | 220 | 220 | 220 | 220 | 220 |
| projectInvestmentIrrBeforeTax | 项目投资财务内部收益率所得税前 | 8.76 % | 8.76 % | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 14 | 项目投资财务内部收益率（所得税前） | % | 8.76 |
| capitalIRR | 资本金财务内部收益率 | 12.09 % | 12.09 % | 1  综合说明 / 1.15 财务评价 | 财务评价结果表明：投资回收期为11.02年，总投资收益率为5.54%，投资利税率为4.44%，资本金净利润率为11.57%，全部投资财务内部收益率（所得税前、税后）分别为8.76%、7.55%，资本金财务内部收益率为12.09%，项目财务上可行且具有一定的盈利能力。 |

## Missing Fields

| code | field | expected | likely cause |
|---|---|---|---|
| mainTransformerRatio | 主变压器变比 | 115±8×1.25%/37kV | missing: no candidate survived, or extractor cannot handle this table column/value type |
| svgReactiveCompensationCapacity | SVG无功补偿装置容量 | ±30Mvar Mvar | missing: no candidate survived, or extractor cannot handle this table column/value type |
| groundingTransformerCapacity35kv | 35kV接地变用变容量 | 500 kVA | missing: no candidate survived, or extractor cannot handle this table column/value type |
| groundingStationTransformerCapacity35kv | 35kV接地变兼站用变容量 | 800/315 kVA | missing: no candidate survived, or extractor cannot handle this table column/value type |
| substationRoadLayoutType | 升压站内道路布置类型 | 环形道路 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| substationFunctionalZones | 升压站包含生活区和生产区 | 包含生活区和生产区 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| pileRingCount | 桩圈数 | 两圈 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| pilesPerRing | 每圈桩数 | 第一圈布置4根，第二圈布置20根 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| boxFoundationConcreteC25Quantity | 箱变基础混凝土量C25 | 25 m3 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| boxFoundationRebarQuantity | 箱变基础钢筋工程量 | 0.5 t | missing: no candidate survived, or extractor cannot handle this table column/value type |
| totalProjectCost | 总费用 | 128313.98 万元 | missing: no candidate survived, or extractor cannot handle this table column/value type |
| constructionCost | 施工费 | 1542.64 万元 | missing: no candidate survived, or extractor cannot handle this table column/value type |

## Wrong Fields

| code | field | expected | actual | likely cause | evidence |
|---|---|---|---|---|---|
| maxWindSpeed50Year | 50年一遇最大风速 | 26.93 m/s | 37.5 m/s | wrong candidate/table cell selected | 1  综合说明 / 1.2 风能资源 | 风电场110m的50年一遇最大风速小于37.5m/s。50～90m高度15m/s风速段湍流强度介于0.117～0.164之间，湍流强度中等。根据国际电工协会IEC61400-1(2019)判定该风电场可选用适合IECⅢa类及以上安全等级的风力发电机。风电机组的湍流强度需风机厂家进行复核，以确定机组的安全性。 |
| selectedTurbineSafetyClass | 最终宜选机型 | IECIIIa+ | 风力发电机 | wrong candidate/table cell selected | 1  综合说明 / 1.2 风能资源 | 风电场110m的50年一遇最大风速小于37.5m/s。50～90m高度15m/s风速段湍流强度介于0.117～0.164之间，湍流强度中等。根据国际电工协会IEC61400-1(2019)判定该风电场可选用适合IECⅢa类及以上安全等级的风力发电机。风电机组的湍流强度需风机厂家进行复核，以确定机组的安全性。 |
| theoreticalAnnualEnergy | 年理论发电量 | 67447.2 万kW·h | 5.1 | chapter/table number captured | 4 工程任务和规模 / 5.1 风力发电机组选型 / 5.1.3 风电机组选型 | 根据比选机型最终布置方案，采用各测风塔年测风数据，依据风机厂商提供的当地空气密度下的动态功率曲线和推力系数曲线，采用WT软件计算风电机组的理论发电量和尾流后发电量，参照本阶段风电机组的报价情况，对比选机型进行了技术经济比较，结果见表5.1.3-1。 |
| wakeLossPercent | 尾流平均折减 | -4.28 % | 1.5 | chapter/table number captured | 1  综合说明 / 1.5 风电机组选型、布置及风电场发电量估算 | 1.5 风电机组选型、布置及风电场发电量估算 |
| nonWakeLossFactor | 不考虑尾流效应的折减系数 | 73.65 % | 98 % | wrong candidate/table cell selected | 4 工程任务和规模 / 5.3 年上网电量估算 | 因此根据本风电场的气候特征，考虑凝冻等气候因素影响，本次取气候影响停机折减系数98%。 |
| substationMainConnectionPlannedCapacity | 升压站电气主接线规划总规模 | 200 MW | 6.3 | chapter/table number captured | 6  电 气 / 6.3 电气一次 | 6.3 电气一次 |
| substationMainConnectionCurrentCapacity | 升压站电气主接线本期规模 | 200 MW | 6.3 | chapter/table number captured | 6  电 气 / 6.3 电气一次 | 6.3 电气一次 |
| mainConnectionType | 主接线形式 | 单母线接线 | 简单清晰 | wrong candidate/table cell selected | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.1 升压站电气主接线 |  | 单母线接线 主要特点 | 接线简单清晰，继电保护简单； 设备较少，有效减少投资； 接地变容量小，仅考虑一台主变对应电容电流； |
| mainTransformerType | 主变压器 | 三相双绕组油浸自冷式有载调压变压器 | 480 | spec/text field treated as numeric field | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 主变压器 | 480 | 550 | 530 | 200 | 185 |
| mainTransformerCapacity | 主变容量 | 110 MVA | 200 MVA | wrong candidate/table cell selected | 9 土建工程 / 9.7 升压站 / 9.7.2.1 设计依据 / 9.7.3.4 户外设备基础 | 升压站内均设一座水泵房（生活及消防共用），泵房内设置一座生活水箱、一套生活变频恒压供水设备（含两台生活供水泵，互为备用）和两台紫外线消毒器。水储存在生活水箱内，再由生活变频恒压供水设备加压并经紫外线消毒器消毒后供生活用水。室外浇洒道路由外运水车运水直接进行浇洒。站内各建筑体积均小于3000m³，二次设备室为丁类建筑物，根据GB50229 |
| independentLightningRodCount | 独立避雷针个数 | 2 座 | 1 座 | chapter/table number captured | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 独立避雷针及1座 |
| frameLightningRodCount | 构架避雷针个数 | 1 座 | 110 | wrong candidate/table cell selected | 6  电 气 / 6.3 电气一次 / 6.3.3 升压站设计 / 6.3.3.3 过电压保护及接地 | 构架避雷针进行联合保护。110 |
| collectorVoltageLevel | 集电线路电压等级 | 35 kV | 1.6 | chapter/table number captured | 1  综合说明 / 1.6 电气 | 1.6 电气 |
| collectorLineLength | 集电线路长度 | 81.6 km | 16 | chapter/table number captured | 6  电 气 / 6.3 电气一次 / 6.4.4 升压站设计 / 6.4.4.13 电工实验室 | 2 | 35kV集电线路电能表 |  | 块 | 16 |  |
| towerFoundationCount | 全线共用铁塔基数 | 316 基 | 6.6 | chapter/table number captured | 6  电 气 / 6.6 集电线路 | 6.6 集电线路 |
| collectorLineNames | 线路名称 | A-H | 线路长度 (km) | wrong candidate/table cell selected | 6  电 气 / 6.6 集电线路 | 线路名称 | 线路长度 (km) | 连接风机号 |
| foundationCapBottomRadius | 基础承台底面半径 | 8.5 m | 17 m | chapter/table number captured | 9 土建工程 / 9.4 风电机组基础设计 / 9.4.3 风机基础设计方案 | 根据基桩布置要求和桩基承台构造要求，经试算拟定承台具体尺寸为：底部直径17.0m，高1.0m的圆柱；中部为底面直径17.0m，顶面直径8.0m，高1.2m的圆台；上部为直径7.6m，高0.8m的台柱。详见附图9-1。 |
| foundationType | 风机基础型式 | 桩基础 | 箱型 | wrong candidate/table cell selected | 9 土建工程 / 9.7 升压站 / 9.7.2.1 设计依据 / 9.7.3.2 主要建筑物 | 基础形式 | 箱型 |
| permanentLandWindFoundationArea | 永久占地-风机基础 | 8695 m2 | 34262 | wrong candidate/table cell selected | 10 施工组织设计 / 10.2 施工总布置 | 风机基础 | 34262 | 16687 | 17575 |  |
| permanentLandSubstationArea | 永久占地-110kV升压站 | 9800 m2 | 110 | wrong candidate/table cell selected |  | 升压站电气主接线图 | 110kV出线间隔断面图 |
| permanentLandTotalArea | 永久占地合计 | 30399 m2 | 18 | chapter/table number captured | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 合计 | 18 |
| longTermLeaseAccessRoadArea | 长期租地-进站道路 | 1560 m2 | 25 | wrong candidate/table cell selected | 9 土建工程 / 9.4 风电机组基础设计 / 9.6.2 道路设计要求 | 进站道路 | C25混凝土路面 |
| longTermLeaseTotalArea | 长期租地合计 | 107883 m2 | 18 | chapter/table number captured | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 合计 | 18 |
| temporaryLandTotalArea | 临时性占地合计 | 416001 m2 | 18 | chapter/table number captured | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 合计 | 18 |
| roadEarthworkExcavation | 道路土方开挖 | 1048836 m3 | 110 | wrong candidate/table cell selected |  | 道路总平面布置图 | 110kV升压站竖向布置图 |
| roadEarthworkBackfill | 道路土方回填 | 1149523 m3 | 110 | wrong candidate/table cell selected |  | 道路总平面布置图 | 110kV升压站竖向布置图 |
| boxFoundationEarthworkExcavation | 箱变基础土方开挖 | 2400 m3 | 1200 | wrong candidate/table cell selected | 10 施工组织设计 / 10.4 工程占地 | 箱变基础 | m2 | 1200 |  |
| substationEarthworkExcavation | 升压站土方开挖 | 22500 m3 | 110 | wrong candidate/table cell selected |  | 升压站电气主接线图 | 110kV出线间隔断面图 |
| substationEarthworkBackfill | 升压站土方回填 | 22500 m3 | 6 | wrong candidate/table cell selected |  | 3 | 升压站电气主接线图 | 附图6-1 | 1 |
| totalEarthworkExcavation | 合计土方开挖 | 1435228 m3 | 18 | chapter/table number captured | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 合计 | 18 |
| totalEarthworkBackfill | 合计土方回填 | 1435698 m3 | 18 | chapter/table number captured | 2 风能资源 / 2.3 气象站 / 2.4.4 测风数据订正 / 2.5.2.3 50年一遇最大风速 | 合计 | 18 |
| installationCost | 安装费 | 5748.89 万元 | 398066.46 | wrong candidate/table cell selected | 15 设计概算 / 15.1.2.1 编制原则 / 15.2.2 施工辅助工程概算表 | 安装费 | 398066.46 |
| constructionPeriodYears | 建设期 | 1 年 | 1902.56 | wrong candidate/table cell selected | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 4 | 建设期利息 | 万元 | 1902.56 |
| repaymentPeriod | 偿还年限 | 15 年 | 1.15 | chapter/table number captured | 1  综合说明 / 1.15 财务评价 | 1.15 财务评价 |
| staffingCount | 定员人数 | 15 人 | 1.15 | chapter/table number captured | 1  综合说明 / 1.15 财务评价 | 1.15 财务评价 |
| welfareOtherRatio | 职工福利费及其他占比 | 70 % | 1.15 | chapter/table number captured | 1  综合说明 / 1.15 财务评价 | 1.15 财务评价 |
| lcoe | 度电成本 | 0.3345 元/kWh | 6.2 | chapter/table number captured | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 上网电价电价市场化变化分析（%） | 12.25 | 6.2 | 8.86 | 12.25 |
| incomeTax | 所得税 | 24040.44 万元 | 8.95 | chapter/table number captured | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 投资回收期(所得税后) (年) | 8.95 |
| projectInvestmentIrrAfterTax | 项目投资财务内部收益率所得税后 | 7.55 % | 8.95 | chapter/table number captured | 16 财务评价与社会效果分析 / 16.2.2.5 敏感性分析 | 投资回收期(所得税后) (年) | 8.95 |

## Multi-value Fields

| code | field | expected count | actual value | status |
|---|---|---:|---|---|
| metTowerCode | 测风塔编号 | 6 | None | MISSING |
| airDensityAtHeight | 高度对应的空气密度 | 6 | [3] | WRONG_COUNT |
| hubHeightAnnualAverageWindSpeed | 轮毂高度年平均风速 | 6 | [3] | WRONG_COUNT |
| hubHeightWindPowerDensity | 轮毂高度平均风功率密度 | 6 | [163] | WRONG_COUNT |
| hubHeightMainWindDirection | 轮毂高度处的主风向 | 6 | None | MISSING |
| hubHeightMainWindEnergyDirection | 轮毂高度处的主风能方向 | 6 | None | MISSING |
| representativeTurbulenceIntensity | 最大高度处代表性湍流强度 | 6 | 0.219 | WRONG_TYPE |
| windShearExponent | 综合风切变 | 6 | 0.043 | WRONG_TYPE |
| generationCalculationUsed | 发电量计算是否使用 | 6 | None | MISSING |

## Root Causes

1. Regex fallback is too broad: chapter numbers such as 5.1, 6.3, 9.4 and 1.15 are repeatedly extracted as values.
2. Table extraction is not strict enough: many reference answers are header-to-cell lookups, but current extraction often takes a table header, first number in a row, or a cell from another table.
3. Text/spec/compound fields need dedicated handling: examples include 115?8?1.25%/37kV, ?30Mvar, 800/315kVA, 2?3.6km and Chinese quantity words.
4. Detail table matching is inconsistent: tower/land tables are missing, while earthworkBalance over-matches 95 rows.
5. Reference parsing-data priority is insufficient: full-report candidates from summary text, sensitivity tables and figure captions can outrank the intended reference fields.
