# 最终抽取字段与表格清单

> 生成依据：`configs/output_schema.yaml` 与 `configs/table_field_extractors.yaml`。
>
> “固定字段”会出现在章节结构中（未抽到时值可能为空）；“二次追加字段/派生表”和“可选原表”仅在规则命中且结果有效时进入最终结果。带 `{tower_clean}` 等占位符的编码会按实际塔号动态展开。
>
> 《设备及安装工程概算表》的 89 个设备单价字段统一使用 `cell_items`：只创建一次 DataFrame、定位一次名称列和设备费列、遍历一次数据行。其中 9 个是固定字段，另外 80 个仅在命中时追加，所以总览中的“二次追加字段”仍按 80 个统计。

## 总览

- 固定字段：**307** 个
- 命中时追加的二次字段：**119** 个（含动态模板字段）
- 固定/可选原表：**56** 张
- 二次派生表：**33** 张
- 动态原表家族：**20** 类

| 章节 | 固定字段 | 二次追加字段 | 固定/可选原表 | 派生表 | 动态表族 |
|---|---:|---:|---:|---:|---:|
| 通用 | 8 | 0 | 0 | 0 | 0 |
| 资源章节 | 24 | 22 | 7 | 0 | 8 |
| 发电量章节 | 19 | 10 | 2 | 1 | 1 |
| 地勘章节 | 3 | 0 | 0 | 0 | 0 |
| 电气一次 | 60 | 5 | 2 | 0 | 1 |
| 电气二次 | 12 | 0 | 2 | 2 | 1 |
| 集电线路 | 16 | 2 | 7 | 1 | 1 |
| 土建升压站 | 2 | 0 | 1 | 1 | 1 |
| 风机基础 | 20 | 0 | 1 | 1 | 1 |
| 箱变基础 | 0 | 0 | 1 | 0 | 1 |
| 道路 | 13 | 0 | 1 | 0 | 1 |
| 用地面积 | 14 | 0 | 4 | 1 | 1 |
| 土石方平衡 | 16 | 0 | 1 | 1 | 1 |
| 环保水保 | 2 | 0 | 0 | 0 | 0 |
| 技经概算 | 49 | 80 | 6 | 6 | 1 |
| 财务 | 49 | 0 | 21 | 19 | 1 |

## 通用

### 固定字段（8）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `projectName` | 项目名称 | — | 否 |
| `investmentOwnerCompany` | 投资（建设）单位 | — | 否 |
| `projectAddressCity` | 项目地址-所属市 | — | 否 |
| `projectAddressCounty` | 项目地址-所属县区 | — | 否 |
| `projectAddressTown` | 项目地址-所属乡镇 | — | 否 |
| `projectAddressDetail` | 项目地址-详细地址 | — | 否 |
| `designUnit` | 设计单位 | — | 否 |
| `designUnitQualification` | 设计单位资质等级 | — | 否 |

## 资源章节

### 固定字段（24）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `selectedTurbineSafetyClass` | 最终宜选机型 | — | 否 |
| `maxWindSpeed50Year` | 50年一遇最大风速值 | m/s | 否 |
| `windResourceTowerCodes` | 测风塔编号 | — | 是 |
| `windTowerLongitude` | 测风塔经度 | — | 是 |
| `windTowerLatitude` | 测风塔纬度 | — | 是 |
| `windMeasurementPeriod` | 测风周期 | — | 是 |
| `windFarmAirDensities` | 该风电场的空气密度 | kg/m³ | 否 |
| `windResourceAirDensities` | 高度对应的空气密度 | kg/m³ | 否 |
| `windResourceAirDensity10m` | 10m高度空气密度 | kg/m³ | 否 |
| `windResourceAirDensity160m` | 160m高度空气密度 | kg/m³ | 否 |
| `windResourceAirDensityRecords` | 各测风塔各高度空气密度 | kg/m³ | 否 |
| `hubHeightAnnualAverageWindSpeed` | 轮毂高度平均风速 | m/s | 否 |
| `hubHeightWindPowerDensity` | 轮毂高度平均风功率密度 | W/m² | 否 |
| `hubHeightAverageWindSpeedRecords` | 各测风塔轮毂高度平均风速 | m/s | 否 |
| `hubHeightAverageWindPowerDensityRecords` | 各测风塔轮毂高度平均风功率密度 | W/m² | 否 |
| `windResourceMainWindDirections` | 轮毂高度处的主风向 | — | 否 |
| `windResourceSecondaryWindDirections` | 轮毂高度处的次风向 | — | 否 |
| `windResourceMainWindEnergyDirections` | 轮毂高度处的主风能方向 | — | 否 |
| `windResourceSecondaryWindEnergyDirections` | 轮毂高度处的次风能方向 | — | 否 |
| `representativeTurbulenceIntensity` | 最大高度处代表性湍流强度 | — | 否 |
| `windResourceTurbulenceIntensityRecords` | 各测风塔各高度湍流强度 | — | 否 |
| `windPowerDensityGrade` | 风功率密度等级 | 级 | 否 |
| `windShearExponent` | 综合风切变 | — | 否 |
| `windResourceGenerationUses` | 发电量计算是否使用 | — | 否 |

### 二次抽取命中时追加字段（22）

| 字段编码/模板 | 中文名 | 单位 | 操作 |
|---|---|---|---|
| `windResource{tower_clean}PowerDensity160m` | {tower}测风塔160m平均风功率密度 | W/m² | `cell` |
| `windResource{tower_clean}ShearComprehensive` | {tower}测风塔风切变综合值 | — | `cell` |
| `windResource{tower_clean}Turbulence140m10ms` | {tower}测风塔140m代表湍流强度（10m/s） | — | `cell` |
| `windResource{tower_clean}Turbulence160m15ms` | {tower}测风塔160m代表湍流强度（15m/s） | — | `cell` |
| `windResource{tower_clean}Turbulence140mV15` | {tower}测风塔140m代表性湍流强度（V=15m/s） | — | `cell` |
| `windResource{tower_clean}Turbulence160mV15` | {tower}测风塔160m代表性湍流强度（V=15m/s） | — | `cell` |
| `windResource{tower_clean}Extrapolated160mSpeed` | {tower}测风塔160m（推算）风速 | m/s | `cell` |
| `windResource{tower_clean}Extrapolated160mPowerDensity` | {tower}测风塔160m（推算）风功率密度 | W/m² | `cell` |
| `windResourceShear{tower_clean}FittedValue` | {tower}测风塔风切变拟合值 | — | `cell` |
| `windResource{tower_clean}SpeedAverage` | {tower}测风塔平均风速 | m/s | `cell` |
| `windResource{tower_clean}PowerAverage` | {tower}测风塔平均风功率密度 | W/m² | `cell` |
| `windResource{tower_clean}MaxWindDirectionSector` | {tower}测风塔最大风速（风向频率）对应扇区 | — | `sector_max` |
| `windResource{tower_clean}MaxPowerSector` | {tower}测风塔最大风功率对应扇区 | — | `sector_max` |
| `windResource{tower_clean}SecondWindDirectionSector` | {tower}测风塔风向第二大值对应扇区 | — | `sector_max` |
| `windResource{tower_clean}SecondPowerSector` | {tower}测风塔风功率第二大值对应扇区 | — | `sector_max` |
| `windResource{tower_clean}Turbulence90m` | {tower}测风塔90m代表湍流强度 | — | `cell` |
| `windResource8688Turbulence90m` | 8688#测风塔90m代表湍流强度 | — | `cell` |
| `windResource{tower_clean}Extrapolated120mSpeed` | {tower}测风塔120m-推算风速 | m/s | `cell` |
| `windResource{tower_clean}Extrapolated120mPowerDensity` | {tower}测风塔120m-推算风功率密度 | W/m² | `cell` |
| `windDirectionMax{tower_clean}` | {tower}最大风能频率对应风向 | — | `max_row_label` |
| `windTurbulence{tower_clean}Representative90m` | {tower}测风塔90m代表湍流强度 | — | `cell` |
| `windShear{tower_clean}ComprehensiveValue` | {tower}测风塔风速切变指数综合值 | — | `cell` |

### 原表（固定 0 / 可选 7）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `windResourceTowerBasic` | 表2.4.1-1 测风塔基本情况表 | 可选，命中时输出 |
| `windResourceShearStatistics` | 表2.5.2.1-1 测风塔不同高度测风资料风切变指数统计表 | 可选，命中时输出 |
| `windResourceSpeedPowerStatistics` | 表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表 | 可选，命中时输出 |
| `windResourceSectorDistribution` | 表2.5.3.3-1 测风塔110m高度代表年各扇区风向和风能分布统计（%） | 可选，命中时输出 |
| `windResourceDirectionEnergyFrequency` | 测风塔风向风能频率统计成果表 | 可选，命中时输出 |
| `windResourceTurbulenceComparison` | 表2.5.2.2-1 测风塔不同高度湍流强度比较表 | 可选，命中时输出 |
| `windResourceTurbulenceIntensity` | 湍流强度 | 可选，命中时输出 |

### 动态原表家族（8）

| Key 前缀 | 名称/用途 |
|---|---|
| `windResourceEnergyParameter*` | 同章节原表，按命中顺序动态编号 |
| `windResourceSpeedPower*` | 同章节原表，按命中顺序动态编号 |
| `windResourceShear*` | 同章节原表，按命中顺序动态编号 |
| `windResourceTurbulence*` | 同章节原表，按命中顺序动态编号 |
| `windResourceGenericEnergyParameter*` | 同章节原表，按命中顺序动态编号 |
| `windResourceGenericShear*` | 同章节原表，按命中顺序动态编号 |
| `windResourceGenericTurbulence*` | 同章节原表，按命中顺序动态编号 |
| `resourceOriginalTable*` | 资源章节原表 |

## 发电量章节

### 固定字段（19）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `installedCapacity` | 装机容量 | MW | 否 |
| `turbineCount` | 风机台数 | 台 | 否 |
| `turbineCapacity` | 单机容量 | KW | 否 |
| `generationHubHeight` | 轮毂高度 | m | 否 |
| `nonWakeLossFactor` | 不考虑尾流效应的折减系数 | % | 否 |
| `gridAnnualEnergy` | 年上网发电量 | 万kW·h | 否 |
| `equivalentFullLoadHours` | 年等效满负荷小时数 | h | 否 |
| `generationSingleTurbineLabels` | 标签 | — | 是 |
| `generationSingleTurbineXMeters` | X（m） | m | 是 |
| `generationSingleTurbineYMeters` | Y（m） | m | 是 |
| `generationSingleTurbineZMeters` | Z（m） | m | 是 |
| `generationSingleTurbineHubHeights` | H（m） | m | 是 |
| `generationSingleTurbineTheoreticalEnergyMwh` | 理论发电量 | 兆瓦时/年 | 是 |
| `generationSingleTurbineAverageWindSpeeds` | 平均风速 | m/s | 是 |
| `generationSingleTurbineWakeLossFactors` | 尾流系数 | % | 是 |
| `generationSingleTurbineWakeAdjustedEnergyMwh` | 考虑尾流效应的发电量 | 兆瓦时/年 | 是 |
| `generationSingleTurbineFinalOnGridEnergyMwh` | 最终上网电量 | 兆瓦时/年 | 是 |
| `generationSingleTurbineEquivalentHours` | 等效小时数 | h | 是 |
| `generationSingleTurbineAverageWakeReductionRates` | 尾流效应导致的平均折减率 | % | 是 |

### 二次抽取命中时追加字段（10）

| 字段编码/模板 | 中文名 | 单位 | 操作 |
|---|---|---|---|
| `generationInstalledCapacityUnit` | 装机容量单位 | — | `cell` |
| `generationInstalledCapacityRecommended` | 装机容量推荐方案 | — | `cell` |
| `generationTurbineCapacityUnit` | 单机容量单位 | — | `cell` |
| `generationTurbineCapacityRecommended` | 单机容量推荐方案 | — | `cell` |
| `generationTurbineCountUnit` | 台数单位 | — | `cell` |
| `generationTurbineCountRecommended` | 台数推荐方案 | — | `cell` |
| `generationAnnualOnGridEnergyUnit` | 年上网电量单位 | — | `cell` |
| `generationAnnualOnGridEnergyRecommended` | 年上网电量推荐方案 | — | `cell` |
| `generationEquivalentHoursUnit` | 年等效满负荷小时数单位 | — | `cell` |
| `generationEquivalentFullLoadHoursRecommended` | 年等效满负荷小时数推荐方案 | — | `cell` |

### 原表（固定 0 / 可选 2）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `generationSummary` | generationSummary | 可选，命中时输出 |
| `singleTurbineAnnualEnergy` | singleTurbineAnnualEnergy | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `generationSingleTurbineAnnualEnergyProjected` | 单台风机发电量明细表投影 | `table_projection` | `singleTurbineAnnualEnergy` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `generationOriginalTable*` | 发电量章节原表 |

## 地勘章节

### 固定字段（3）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `projectGeomorphology` | 项目地貌 | — | 否 |
| `surfaceVegetationType` | 地表类型 | — | 否 |
| `siteElevationRange` | 场区海拔高度 | m | 否 |

## 电气一次

### 固定字段（60）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `accessStationName` | 接入站名称 | — | 否 |
| `accessibleVoltage` | 可接入电压 | kv | 否 |
| `accessibleCapacity` | 可接入容量 | MVA | 否 |
| `plannedCapacity` | 升压站电气主接线规划总规模 | MW | 否 |
| `currentCapacity` | 升压站电气主接线本期规模 | MW | 否 |
| `connectionType` | 主接线形式 | — | 否 |
| `electricalPrimaryCurrentOutgoingLineCount` | 升压站本期出线回数 | 回 | 是 |
| `electricalPrimaryFutureOutgoingLineCount` | 升压站远期出线回数 | 回 | 是 |
| `mainTransformerType` | 主变压器类型 | — | 是 |
| `mainTransformerModel` | 主变压器型号 | — | 是 |
| `mainTransformerRatedCapacity` | 主变压器额定容量 | kVA | 是 |
| `mainTransformerNum` | 主变本期台数 | 台 | 是 |
| `futureMainTransformerCount` | 主变远期台数 | 台 | 是 |
| `mainTransformerVoltageRatio` | 主变压器额定电压比 | — | 是 |
| `connectionGroupType` | 主变压器接线组别 | — | 是 |
| `groundingStationTransformerModel` | 接地变兼站用变型号 | — | 是 |
| `groundingStationTransformerVoltage` | 接地变兼站用变电压 | kV | 是 |
| `groundingStationTransformerCapacity` | 接地变兼站用变容量 | kVA | 是 |
| `groundingStationTransformerQuantity` | 接地变兼站用变数量 | — | 是 |
| `groundingStationTransformerUnit` | 接地变兼站用变单位 | — | 是 |
| `groundingStationTransformerResistance` | 接地变兼站用变接地电阻 | — | 是 |
| `groundingTransformerModel` | 接地变型号 | — | 是 |
| `groundingTransformerVoltage` | 接地变电压 | kV | 是 |
| `groundingTransformerCapacity` | 接地变容量 | kVA | 是 |
| `groundingTransformerQuantity` | 接地变数量 | — | 是 |
| `groundingTransformerUnit` | 接地变单位 | — | 是 |
| `groundingTransformerResistance` | 接地变接地电阻 | — | 是 |
| `electricalPrimaryGisModelInfo` | GIS型号信息 | — | 是 |
| `electricalPrimaryGisQuantity` | 110kV架空出线间隔数量 | — | 是 |
| `electricalPrimaryGisUnit` | 110kV架空出线间隔单位 | — | 是 |
| `electricalPrimaryGisRemark` | 110kV架空出线间隔备注 | — | 是 |
| `electricalPrimaryCircuitBreakerModel` | 断路器型号 | — | 是 |
| `electricalPrimaryDisconnectorModel` | 隔离开关型号 | — | 是 |
| `electricalPrimaryCurrentTransformerModel` | 电流互感器型号 | — | 是 |
| `electricalPrimaryVoltageTransformerModel` | 电压互感器型号 | — | 是 |
| `electricalPrimaryTransformerSpec` | 主变压器型号、规格及技术数据 | — | 是 |
| `electricalPrimarySvgSpec` | 35kV SVG型号、规格及技术数据 | — | 是 |
| `electricalPrimarySvgUnit` | 35kV SVG单位 | — | 是 |
| `electricalPrimarySvgQuantity` | 35kV SVG数量 | — | 是 |
| `electricalPrimaryGroundingTransformerSetSpec` | 35kV接地变成套装置型号、规格及技术数据 | — | 是 |
| `electricalPrimaryExternalPowerTransformerSpec` | 站外电源变压器型号、规格及技术数据 | — | 是 |
| `electricalPrimaryFrameLightningRodHeight` | 构架避雷针高度 | m | 否 |
| `electricalPrimaryIndependentLightningRodHeight` | 独立避雷针高度 | m | 否 |
| `electricalPrimaryBoxTransformerType` | 箱变类型 | — | 否 |
| `electricalPrimaryBoxTransformerModel` | 箱变型号 | — | 否 |
| `electricalPrimaryBoxTransformerVoltageLevel` | 箱变电压等级 | kV | 否 |
| `electricalPrimaryBoxTransformerCapacity` | 箱变容量 | kVA | 否 |
| `electricalPrimaryBoxTransformerHighVoltageSideConfig` | 高压侧配置信息 | — | 否 |
| `electricalPrimaryBoxTransformerLowVoltageSideConfig` | 低压侧配置信息 | — | 否 |
| `electricalPrimaryGridConnectionDistance` | 接入距离 | km | 否 |
| `electricalPrimaryGridConnectionLineType` | 接入站送出线路方式 | — | 否 |
| `electricalPrimarySubstationConstructionType` | 升压站建设类型 | — | 否 |
| `electricalPrimaryExpandedSubstationName` | 扩建升压站 | — | 否 |
| `electricalPrimarySubstationVoltageLevel` | 升压站电压等级 | kV | 否 |
| `stationTransformerCapacity10kv` | 10kV站用变容量 | — | 否 |
| `groundingTransformerCapacity35kv` | 35kV接地变容量 | — | 否 |
| `groundingStationTransformerCapacity35kv` | 35kV接地变兼站用变容量 | — | 否 |
| `svgReactiveCompensationCapacity` | SVG无功补偿装置容量 | — | 否 |
| `independentLightningRodCount` | 独立避雷针座数 | 座 | 否 |
| `frameLightningRodCount` | 构架避雷针座数 | 座 | 否 |

### 二次抽取命中时追加字段（5）

| 字段编码/模板 | 中文名 | 单位 | 操作 |
|---|---|---|---|
| `electricalPrimaryGisSpec` | 110kV GIS成套设备型号、规格及技术数据 | — | `cell` |
| `electricalPrimary110kvDistributionSpec` | 110kV配电装置型号、规格及技术数据 | — | `cell` |
| `electricalPrimaryGroundingStationTransformerSpec` | 35kV接地兼站用变型号、规格及技术数据 | — | `cell` |
| `electricalPrimary10kvStationTransformerSpec` | 10kV站用变型号、规格及技术数据 | — | `cell` |
| `electricalPrimaryBoxTransformerSpec` | 箱变型号、规格及技术数据 | — | `cell` |

### 原表（固定 0 / 可选 2）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `electricalPrimaryStationScale` | 表6.3-1 110kV升压站本期规模 | 可选，命中时输出 |
| `electricalPrimaryEquipmentMaterial` | 表6.3.3-10 升压站电气一次主要设备材料工程量表 | 可选，命中时输出 |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `electricalPrimaryOriginalTable*` | 电气一次原表 |

## 电气二次

### 固定字段（12）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `communicationPowerDesign` | 通讯电源设计 | — | 否 |
| `communicationPowerUnitType` | 通讯电源设计单位 | — | 是 |
| `communicationPowerQuantityValue` | 通讯电源设计数量 | — | 是 |
| `communicationPowerDesignDescription` | 通讯电源设计描述 | — | 否 |
| `dcBatteryConfiguration` | 直流蓄电池配置 | — | 否 |
| `upsPowerConfiguration` | UPS电源配置 | — | 否 |
| `electricalSecondaryBatterySpec` | 蓄电池屏型号及规格 | — | 是 |
| `electricalSecondaryBatteryUnit` | 蓄电池屏单位 | — | 是 |
| `electricalSecondaryBatteryQuantity` | 蓄电池屏数量 | — | 是 |
| `electricalSecondaryUpsSpec` | UPS电源屏型号及规格 | — | 是 |
| `electricalSecondaryUpsUnit` | UPS电源屏单位 | — | 是 |
| `electricalSecondaryUpsQuantity` | UPS电源屏数量 | — | 是 |

### 原表（固定 0 / 可选 2）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `electricalSecondaryMainEquipment` | 表6.4.4-3 升压站电气二次主要设备表 | 可选，命中时输出 |
| `electricalSecondaryCommunicationEquipment` | 表6.5-1 主要通信设备表 | 可选，命中时输出 |

### 二次派生表（2）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `electricalSecondaryMainEquipmentCopy` | 风电场主要电气二次工程量 | `copy_table` | `electricalSecondaryMainEquipment` |
| `electricalSecondaryCommunicationEquipmentCopy` | 主要通信设备表 | `copy_table` | `electricalSecondaryCommunicationEquipment` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `electricalSecondaryOriginalTable*` | 电气二次原表 |

## 集电线路

### 固定字段（16）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `collectorLineNames` | 线路名称 | — | 否 |
| `collectorVoltage` | 集电线路电压 | kv | 否 |
| `circuitCount` | 回路数 | 回 | 否 |
| `newRouteLength` | 新建线路路径长度 | km | 否 |
| `newOverheadLineLength` | 新建架空线路长度 | km | 否 |
| `newSingleCircuitLineLength` | 新建单回路线路长度 | km | 否 |
| `newDoubleCircuitLineLength` | 新建双回路线路长度 | km | 否 |
| `newCableLineLength` | 新建电缆线路长度 | km | 否 |
| `totalCollectorRouteLength` | 全线集电线路路径长度 | km | 否 |
| `doubleCircuitOverheadRouteLength` | 双回架空线路路径长度 | km | 否 |
| `singleCircuitOverheadRouteLength` | 单回架空线路路径长度 | km | 否 |
| `boxToTerminalTowerCableRouteLength` | 箱变至终端塔电缆路径长度 | km | 否 |
| `singleCircuitCableRouteLength` | 单回电缆线路路径长度 | km | 否 |
| `doubleCircuitCableRouteLength` | 双回路电缆路径长度 | km | 否 |
| `collectorCableCoreMaterial` | 电缆电芯材质 | — | 否 |
| `collectorLayingMethod` | 敷设方式 | — | 否 |

### 二次抽取命中时追加字段（2）

| 字段编码/模板 | 中文名 | 单位 | 操作 |
|---|---|---|---|
| `newOverheadLineLengthCalculated` | 新建架空线路长度 | km | `sum_fields` |
| `newCableLineLengthCalculated` | 新建电缆线路长度 | km | `sum_fields` |

### 原表（固定 0 / 可选 7）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `collectorElectricalMaterial` | 6.6.16.1电气部分材料清册 | 可选，命中时输出 |
| `collectorTowerMaterial` | 6.6.16.2杆塔部分材料清册 | 可选，命中时输出 |
| `collectorFoundationMaterial` | 6.6.16.3基础部分材料清册 | 可选，命中时输出 |
| `collectorOpticalCableMaterial` | 6.6.16.4光缆部分材料清册 | 可选，命中时输出 |
| `collectorCableMaterial` | 6.6.16.5电缆部分材料清册 | 可选，命中时输出 |
| `collectorTowerGroundingMaterial` | 6.6.16.6铁塔接地装置材料 | 可选，命中时输出 |
| `collectorMainEquipmentMaterial` | 集电线路部分主要设备及材料清册 | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `collectorMainEquipmentMaterialCopy` | 集电线路部分主要设备及材料清册 | `copy_table` | `collectorMainEquipmentMaterial` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `collectorLineOriginalTable*` | 集电线路原表 |

## 土建升压站

### 固定字段（2）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `totalLandArea` | 总占地面积 | ㎡ | 否 |
| `insideWallLandArea` | 围墙内占地面积 | ㎡ | 否 |

### 原表（固定 0 / 可选 1）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `substationCivil` | 表9.7-1 升压站主要土建工程量表 | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `substationCivilCopy` | 升压站主要土建工程量表 | `copy_table` | `substationCivil` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `substationCivilOriginalTable*` | 土建升压站原表 |

## 风机基础

### 固定字段（20）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `windFoundationType` | 风机基础类型 | — | 否 |
| `windFoundationExcavationQuantity` | 风机基础开挖量 | m³ | 否 |
| `windFoundationBackfillQuantity` | 风机基础回填量 | m³ | 否 |
| `windFoundationC15Concrete` | 风机基础-C15混凝土 | m³ | 否 |
| `windFoundationC20Concrete` | 风机基础-C20混凝土 | m³ | 否 |
| `windFoundationC40Concrete` | 风机基础-C40混凝土 | m³ | 否 |
| `windFoundationC45Concrete` | 风机基础-C45混凝土 | m³ | 否 |
| `foundationCapDiameter` | 承台直径 | m | 否 |
| `foundationColumnDiameter` | 台柱直径 | m | 否 |
| `foundationCapBottomRadius` | 承台底面半径R | m | 否 |
| `foundationTopRadius` | 棱台顶面半径R1 | m | 否 |
| `foundationColumnRadius` | 承台台柱半径R2 | m | 否 |
| `foundationOuterEdgeHeight` | 承台底板外缘高度H1 | m | 否 |
| `foundationConeHeight` | 承台底板棱台高度H2 | m | 否 |
| `foundationColumnHeight` | 台柱高度H3 | m | 否 |
| `foundationBuriedDepth` | 基础埋深Hd | m | 否 |
| `pileOuterDiameter` | 桩截面外径(直径) | m | 否 |
| `pileCount` | 桩数 | 根 | 否 |
| `pileLength` | 桩长 | m | 否 |
| `pileRingCount` | 桩圈数 | — | 否 |

### 原表（固定 0 / 可选 1）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `windFoundationConstruction` | 表9.4-5 基础断面表 | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `windFoundationProfileCopy` | 基础断面表 | `copy_table` | `windFoundationConstruction` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `windFoundationOriginalTable*` | 风机基础原表 |

## 箱变基础

### 固定字段（0）

无。

### 原表（固定 0 / 可选 1）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `boxFoundationTechnical` | 表9.5-1 箱变基础单台工程量表（配事故油池） | 可选，命中时输出 |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `boxFoundationOriginalTable*` | 箱变基础原表 |

## 道路

### 固定字段（13）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `accessRoadLength` | 进站道路长度 | km | 否 |
| `siteEntryRoadLength` | 进场道路长度 | km | 否 |
| `accessRoadSubgradeWidth` | 进站道路路基宽度 | m | 否 |
| `accessRoadPavementWidth` | 进站道路路面宽度 | m | 否 |
| `newRoadLength` | 新建道路长度 | km | 否 |
| `rebuiltRoadLength` | 改建道路长度 | km | 否 |
| `subgradeWidth` | 路基宽度 | m | 否 |
| `pavementWidth` | 路面宽度 | m | 否 |
| `siteRoadLength` | 场内道路长度 | km | 否 |
| `maintenanceRoadLength` | 检修道路长度 | km | 否 |
| `maintenanceRoadSubgradeWidth` | 检修道路路基宽度 | m | 否 |
| `maintenanceRoadPavementWidth` | 检修道路路面宽度 | m | 否 |
| `offsiteTrafficConditionDescription` | 场外交通运输条件描述 | — | 否 |

### 原表（固定 0 / 可选 1）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `roadTechnical` | roadTechnical | 可选，命中时输出 |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `roadOriginalTable*` | 道路原表 |

## 用地面积

### 固定字段（16）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `permanentLandTotalArea` | 永久征地总面积 | ㎡ | 否 |
| `permanentLandWindFoundationArea` | 风机基础征地面积 | ㎡ | 否 |
| `permanentLandBoxTransformerArea` | 箱变基础征地面积 | ㎡ | 否 |
| `permanentLandSubstationArea` | 升压站征地面积 | ㎡ | 否 |
| `permanentLandAccessRoadArea` | 进站道路征地面积 | ㎡ | 否 |
| `longTermLeaseTotalArea` | 长期征地总面积 | ㎡ | 否 |
| `longTermLeaseMaintenanceRoadArea` | 检修道路征地总面积 | ㎡ | 否 |
| `longTermLeaseAccessRoadArea` | 进站道路征地总面积 | ㎡ | 否 |
| `longTermLeaseTowerFoundationArea` | 铁塔基础征地总面积 | ㎡ | 否 |
| `temporaryLandTotalArea` | 临时征地总面积 | ㎡ | 否 |
| `temporaryLandPlatformArea` | 施工吊装平台征地总面积 | ㎡ | 否 |
| `temporaryLandConstructionRoadArea` | 施工道路征地总面积 | ㎡ | 否 |
| `temporaryLandDirectBuriedCableArea` | 直埋电缆征地总面积 | ㎡ | 否 |
| `temporaryLandConstructionSiteArea` | 临时施工区征地总面积 | ㎡ | 否 |

### 原表（固定 0 / 可选 4）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `permanentLandSummary` | 表9.4-1 工程永久征地面积汇总表 | 可选，命中时输出 |
| `temporaryLandSummary` | 表9.4-2 工程临时征地面积汇总表 | 可选，命中时输出 |
| `permanentLandArea` | 表10.4-1 工程征用地计算合计表 | 可选，命中时输出 |
| `landTotalAcquisition` | 9.4.1.工程总征地 | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `landTotalAcquisitionCopy` | 工程征用地计算合计表 | `copy_table` | `landTotalAcquisition` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `landOriginalTable*` | 用地面积原表 |

## 土石方平衡

### 固定字段（14）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `roadEarthworkExcavation` | 道路土方开挖 | m3 | 否 |
| `roadEarthworkBackfill` | 道路土方回填 | m3 | 否 |
| `windPlatformEarthworkExcavation` | 风机平台土方开挖 | m3 | 否 |
| `windPlatformEarthworkBackfill` | 风机平台土方回填 | m3 | 否 |
| `windFoundationEarthworkExcavation` | 风机基础土方开挖 | m3 | 否 |
| `windFoundationEarthworkBackfill` | 风机基础土方回填 | m3 | 否 |
| `boxFoundationEarthworkExcavation` | 箱变基础土方开挖 | m3 | 否 |
| `boxFoundationEarthworkBackfill` | 箱变基础土方回填 | m3 | 否 |
| `collectorLineEarthworkExcavation` | 集电线路土方开挖 | m3 | 否 |
| `collectorLineEarthworkBackfill` | 集电线路土方回填 | m3 | 否 |
| `substationEarthworkExcavation` | 升压站土方开挖 | m3 | 否 |
| `substationEarthworkBackfill` | 升压站土方回填 | m3 | 否 |
| `totalEarthworkExcavation` | 合计土方开挖 | m3 | 否 |
| `totalEarthworkBackfill` | 合计土方回填 | m3 | 否 |
| `spoilDisposalSiteCount` | 弃渣场数量 | 个 | 否 |
| `spoilDisposalSiteArea` | 弃渣场面积 | ㎡ | 否 |

### 原表（固定 0 / 可选 1）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `earthworkBalance` | 表10.2-2土石方平衡表（万m(3)） | 可选，命中时输出 |

### 二次派生表（1）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `earthworkBalanceCopy` | 土石方平衡表 | `copy_table` | `earthworkBalance` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `earthworkOriginalTable*` | 土石方平衡原表 |

## 环保水保

### 固定字段（2）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `environmentalInvestment` | 环保总投资 | 万元 | 否 |
| `waterSoilConservationInvestment` | 水保总投资 | 万元 | 否 |

## 技经概算

### 固定字段（49）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `investmentCostStandard` | 费用标准 | — | 否 |
| `investmentQuotaSystem` | 定额体系 | — | 否 |
| `investmentPriceLevel` | 价格水平 | — | 否 |
| `investmentStaticPartTotal` | 工程静态投资（一～五）部分合计 | 万元 | 是 |
| `investmentTotalPartTotal` | 工程总投资（一～七）部分合计 | 万元 | 是 |
| `investmentDeductibleVatWindFarm` | 可抵扣增值税（风电场工程） | 万元 | 是 |
| `investmentOutgoingLineStaticInvestment` | 110kV送出工程静态投资 | 万元 | 是 |
| `investmentOutgoingLineConstructionInterest` | 110kV送出工程建设期利息 | 万元 | 是 |
| `investmentOutgoingLineProjectTotal` | 110kV送出工程工程总投资 | 万元 | 是 |
| `investmentDeductibleVatOutgoingLine` | 可抵扣增值税（110kV送出工程） | 万元 | 是 |
| `investmentCaochengShareStaticInvestment` | 接入曹城变电站分摊费用静态投资 | 万元 | 是 |
| `investmentCaochengShareConstructionInterest` | 接入曹城变电站分摊费用建设期利息 | 万元 | 是 |
| `investmentCaochengShareProjectTotal` | 接入曹城变电站分摊费用工程总投资 | 万元 | 是 |
| `investmentSupportingCostStaticInvestment` | 配套费静态投资 | 万元 | 是 |
| `investmentSupportingCostConstructionInterest` | 配套费建设期利息 | 万元 | 是 |
| `investmentSupportingCostProjectTotal` | 配套费工程总投资 | 万元 | 是 |
| `investmentManagementBuildingStaticInvestment` | 片区管理综合楼静态投资 | 万元 | 是 |
| `investmentManagementBuildingConstructionInterest` | 片区管理综合楼建设期利息 | 万元 | 是 |
| `investmentManagementBuildingProjectTotal` | 片区管理综合楼工程总投资 | 万元 | 是 |
| `investmentSmartWindFarmStaticInvestment` | 智慧风场静态投资 | 万元 | 是 |
| `investmentSmartWindFarmConstructionInterest` | 智慧风场建设期利息 | 万元 | 是 |
| `investmentSmartWindFarmDynamicInvestment` | 智慧风场动态投资 | 万元 | 是 |
| `investmentStaticInvestmentTotal` | 静态投资（部分） | 万元 | 是 |
| `investmentConstructionInterestGrandTotal` | 建设期利息合计 | 万元 | 是 |
| `investmentDynamicInvestmentTotal` | 动态投资（部分） | 万元 | 是 |
| `investmentProjectTotalCost` | 工程总投资合计 | 万元 | 是 |
| `unitKwStaticInvestmentPartTotal` | 单位千瓦静态投资（部分） | 元/kW | 是 |
| `unitKwInvestmentPartTotal` | 单位千瓦动态投资（部分） | 元/kW | 是 |
| `unitKwStaticInvestmentEstimate` | 单位千瓦静态投资 | 元/kW | 是 |
| `unitKwDynamicInvestmentEstimate` | 单位千瓦动态投资 | 元/kW | 是 |
| `investmentSmartManagementPlatformTotal` | 智慧管理平台合计 | 万元 | 是 |
| `investment110kvOutgoingLineProjectTotal` | 110kV送出线路工程合计 | 万元 | 是 |
| `investmentOppositeBayExpansionTotal` | 对侧间隔扩建工程合计 | 万元 | 是 |
| `investment330kvOutgoingLineShareTotal` | 330kV送出线路分摊费合计 | 万元 | 是 |
| `investmentProductSupportingCostTotal` | 产品配套费合计 | 万元 | 是 |
| `investmentNewEnergyStationPerceptionEquipmentTotal` | 新能源场站感知设备合计 | 万元 | 是 |
| `investmentTechnologySpecialTotal` | 科技专篇合计 | 万元 | 是 |
| `investmentStaticTotalItoIv` | 静态投资 | 万元 | 是 |
| `investmentConstructionInterestTotal` | 建设期利息合计 | 万元 | 是 |
| `investmentDynamicTotalItoIv` | 动态投资 | 万元 | 是 |
| `windTurbineUnitPrice` | 风机单价 | 万元 | 是 |
| `turbineTowerUnitPrice` | 风机（含塔筒）单价 | 万元 | 是 |
| `mainTransformerUnitPrice` | 主变单价 | 万元 | 是 |
| `transformerCompleteSetUnitPrice` | 主变整套单价 | 万元 | 是 |
| `windTurbineTowerUnitPrice` | 塔筒单价 | 万元 | 是 |
| `anchorBoltUnitPrice` | 预应力锚栓单价 | 万元 | 是 |
| `containerSubstationUnitPrice` | 箱变单价 | 万元 | 是 |
| `cableBranchBoxUnitPrice` | 电缆分支箱单价 | 万元 | 是 |
| `disconnectorSwitchUnitPrice` | 隔离开关单价 | 万元 | 是 |

### 《设备及安装工程概算表》批量设备单价字段（89）

来源列：`名称及规格/项目名称及规格/名称/项目名称/设备名称`、`单位`、`数量`、`设备费/设备购置费`。名称列用于匹配设备别名，单价字段取设备费列；来源明确标注“元”时换算为万元。下表前 9 项属于固定字段，其余 80 项命中时追加。

| 字段编码 | 中文名 | 单位 | 操作 |
|---|---|---|---|
| `windTurbineUnitPrice` | 风机单价 | 万元 | `cell_items`（固定） |
| `turbineTowerUnitPrice` | 风机（含塔筒）单价 | 万元 | `cell_items`（固定） |
| `mainTransformerUnitPrice` | 主变单价 | 万元 | `cell_items`（固定） |
| `transformerCompleteSetUnitPrice` | 主变整套单价 | 万元 | `cell_items`（固定） |
| `windTurbineTowerUnitPrice` | 塔筒单价 | 万元 | `cell_items`（固定） |
| `anchorBoltUnitPrice` | 预应力锚栓单价 | 万元 | `cell_items`（固定） |
| `containerSubstationUnitPrice` | 箱变单价 | 万元 | `cell_items`（固定） |
| `cableBranchBoxUnitPrice` | 电缆分支箱单价 | 万元 | `cell_items`（固定） |
| `disconnectorSwitchUnitPrice` | 隔离开关单价 | 万元 | `cell_items`（固定） |
| `surgeArresterHy5wzUnitPrice` | 避雷器HY5WZ单价 | 万元 | `cell_items` |
| `mainTransformerNeutralEquipmentUnitPrice` | 主变中性点设备单价 | 万元 | `cell_items` |
| `mediumVoltageNeutralGroundingResistorUnitPrice` | 中压侧中性点接地电阻装置单价 | 万元 | `cell_items` |
| `terminalBoxUnitPrice` | 端子箱单价 | 万元 | `cell_items` |
| `maintenanceBoxUnitPrice` | 检修箱单价 | 万元 | `cell_items` |
| `voltageTransformerUnitPrice` | 电压互感器单价 | 万元 | `cell_items` |
| `zincOxideSurgeArresterUnitPrice` | 氧化锌避雷器单价 | 万元 | `cell_items` |
| `lineTransformerBayUnitPrice` | 线变组开关间隔单价 | 万元 | `cell_items` |
| `incomingCabinetUnitPrice` | 进线柜单价 | 万元 | `cell_items` |
| `outgoingCabinetUnitPrice` | 出线柜单价 | 万元 | `cell_items` |
| `reactiveCompensationCabinetUnitPrice` | 无功补偿柜单价 | 万元 | `cell_items` |
| `busEquipmentCabinetUnitPrice` | 母线设备柜单价 | 万元 | `cell_items` |
| `stationServiceTransformerCabinetUnitPrice` | 站用变柜单价 | 万元 | `cell_items` |
| `wallBushingUnitPrice` | 穿墙套管单价 | 万元 | `cell_items` |
| `enclosedBusBridgeUnitPrice` | 封闭母线桥单价 | 万元 | `cell_items` |
| `copperBusbarUnitPrice` | 铜排单价 | 万元 | `cell_items` |
| `postInsulatorUnitPrice` | 支柱绝缘子单价 | 万元 | `cell_items` |
| `reactiveCompensationDeviceUnitPrice` | 无功补偿装置单价 | 万元 | `cell_items` |
| `stationServiceTransformerUnitPrice` | 站用变压器单价 | 万元 | `cell_items` |
| `lowVoltageAcPanelUnitPrice` | 低压交流屏单价 | 万元 | `cell_items` |
| `distributionBoxUnitPrice` | 配电箱单价 | 万元 | `cell_items` |
| `windFarmScadaSystemUnitPrice` | 风电场计算机监控系统单价 | 万元 | `cell_items` |
| `operatorWorkstationUnitPrice` | 操作员工作站单价 | 万元 | `cell_items` |
| `hostOperatorStationUnitPrice` | 主机兼操作员站单价 | 万元 | `cell_items` |
| `microcomputerFivePreventionWorkstationUnitPrice` | 微机五防工作站单价 | 万元 | `cell_items` |
| `telecontrolCommunicationCabinetUnitPrice` | 远动通讯柜单价 | 万元 | `cell_items` |
| `networkEquipmentCabinetUnitPrice` | 网络设备柜单价 | 万元 | `cell_items` |
| `publicMeasurementControlCabinetUnitPrice` | 公用测控柜单价 | 万元 | `cell_items` |
| `timeSynchronizationCabinetUnitPrice` | 时间同步系统柜单价 | 万元 | `cell_items` |
| `networkSwitchUnitPrice` | 网络交换机单价 | 万元 | `cell_items` |
| `networkPrinterUnitPrice` | 网络打印机单价 | 万元 | `cell_items` |
| `lineProtectionCabinetUnitPrice` | 线路保护柜单价 | 万元 | `cell_items` |
| `lineMeasurementControlCabinetUnitPrice` | 线路测控柜单价 | 万元 | `cell_items` |
| `lineMeasurementControlDeviceUnitPrice` | 线路测控装置单价 | 万元 | `cell_items` |
| `lineProtectionMeasurementControlDeviceUnitPrice` | 线路保护测控装置单价 | 万元 | `cell_items` |
| `svgIncomingProtectionControlDeviceUnitPrice` | SVG进线保护测控装置单价 | 万元 | `cell_items` |
| `stationServiceTransformerProtectionControlDeviceUnitPrice` | 站用变保护测控装置单价 | 万元 | `cell_items` |
| `busDifferentialProtectionCabinetUnitPrice` | 母线差动保护柜单价 | 万元 | `cell_items` |
| `faultRecorderCabinetUnitPrice` | 故障录波柜单价 | 万元 | `cell_items` |
| `relayProtectionTestPowerCabinetUnitPrice` | 继电保护试验电源柜单价 | 万元 | `cell_items` |
| `mainTransformerProtectionCabinetUnitPrice` | 主变压器保护柜单价 | 万元 | `cell_items` |
| `mainTransformerMeasurementControlCabinetUnitPrice` | 主变压器测控柜单价 | 万元 | `cell_items` |
| `stabilityControlCabinetUnitPrice` | 安全稳定控制柜单价 | 万元 | `cell_items` |
| `mainTransformerMicrocomputerProtectionPanelUnitPrice` | 主变压器微机保护屏单价 | 万元 | `cell_items` |
| `intelligentHighFrequencySwitchPowerCabinetUnitPrice` | 智能高频开关电源柜单价 | 万元 | `cell_items` |
| `dcFeederCabinetUnitPrice` | 直流馈线柜单价 | 万元 | `cell_items` |
| `batteryUnitPrice` | 蓄电池单价 | 万元 | `cell_items` |
| `batteryOnlineMonitoringDeviceUnitPrice` | 蓄电池在线监测装置单价 | 万元 | `cell_items` |
| `upsAcUninterruptiblePowerCabinetUnitPrice` | UPS交流不停电电源柜单价 | 万元 | `cell_items` |
| `dispatchDataNetworkCabinetUnitPrice` | 调度数据专网柜单价 | 万元 | `cell_items` |
| `phasorMeasurementUnitPrice` | 同步相量测量装置单价 | 万元 | `cell_items` |
| `windPowerForecastSystemUnitPrice` | 风电功率预测系统单价 | 万元 | `cell_items` |
| `powerQualityMonitoringPanelUnitPrice` | 电能质量监测屏单价 | 万元 | `cell_items` |
| `agcAvcAutomaticControlSystemUnitPrice` | AGC/AVC自动控制系统单价 | 万元 | `cell_items` |
| `dualRulesAssessmentManagementSystemUnitPrice` | 双细则考核管理系统单价 | 万元 | `cell_items` |
| `dispatchManagementOmsUnitPrice` | 调度管理系统(OMS)单价 | 万元 | `cell_items` |
| `securityProtectionEquipmentUnitPrice` | 安全防护设备单价 | 万元 | `cell_items` |
| `primaryFrequencyRegulationSystemUnitPrice` | 一次调频系统单价 | 万元 | `cell_items` |
| `switchAndMaterialsUnitPrice` | 交换机及材料单价 | 万元 | `cell_items` |
| `gatewayMeteringCabinetUnitPrice` | 关口计量柜单价 | 万元 | `cell_items` |
| `threePhaseFourWireMultifunctionMeterUnitPrice` | 三相四线制多功能电度表单价 | 万元 | `cell_items` |
| `imageMonitoringSystemUnitPrice` | 图像监控系统单价 | 万元 | `cell_items` |
| `fireAlarmSystemUnitPrice` | 火灾报警系统单价 | 万元 | `cell_items` |
| `sf6EnvironmentalMonitorUnitPrice` | SF6环境监测仪单价 | 万元 | `cell_items` |
| `protectionFaultInformationSubsystemUnitPrice` | 保护及故障信息管理子系统单价 | 万元 | `cell_items` |
| `opticalTerminalUnitPrice` | 光端机单价 | 万元 | `cell_items` |
| `dataNetworkAccessRouterUnitPrice` | 数据通信网接入路由器单价 | 万元 | `cell_items` |
| `dispatchIadEquipmentUnitPrice` | 调度IAD设备单价 | 万元 | `cell_items` |
| `integratedDistributionFrameUnitPrice` | 综合配线架单价 | 万元 | `cell_items` |
| `stateGridTmsTerminalUnitPrice` | 国网通信管理系统（TMS）终端单价 | 万元 | `cell_items` |
| `intelligentHighFrequencySwitchPowerPanelUnitPrice` | 智能高频开关电源屏单价 | 万元 | `cell_items` |
| `batteryBankUnitPrice` | 蓄电池组单价 | 万元 | `cell_items` |
| `walkieTalkieUnitPrice` | 无线对讲机单价 | 万元 | `cell_items` |
| `programControlledDispatchExchangeUnitPrice` | 程控调度交换机单价 | 万元 | `cell_items` |
| `primaryEquipmentPrefabricatedCabinUnitPrice` | 一次设备预制舱单价 | 万元 | `cell_items` |
| `heatingVentilationAirConditioningSystemUnitPrice` | 采暖通风及空调系统单价 | 万元 | `cell_items` |
| `fireProtectionWaterSupplyDrainageSystemUnitPrice` | 消防及给排水系统单价 | 万元 | `cell_items` |
| `outdoorLightingSystemUnitPrice` | 室外照明系统单价 | 万元 | `cell_items` |
| `occupationalSafetyHealthEquipmentUnitPrice` | 劳动安全与职业卫生设备单价 | 万元 | `cell_items` |
| `productionOperationsVehicleUnitPrice` | 生产运维车辆单价 | 万元 | `cell_items` |

### 原表（固定 0 / 可选 6）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `investmentTechnicalEconomicIndicators` | 15.3.9.1 主要技术经济指标表 | 可选，命中时输出 |
| `investmentEstimate` | 15.2.1工程总概算表 | 可选，命中时输出 |
| `investmentConstructionAuxiliary` | 15.2.2 施工辅助工程概算表 | 可选，命中时输出 |
| `investmentEquipmentInstallation` | 15.2.3设备及安装工程概算表 | 可选，命中时输出 |
| `investmentBuilding` | 15.2.4建筑工程概算表 | 可选，命中时输出 |
| `investmentOtherCost` | 15.2.5其他费用概算表 | 可选，命中时输出 |

### 二次派生表（6）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `investmentEstimateCopy` | 工程总概算表 | `copy_table` | `investmentEstimate` |
| `investmentConstructionAuxiliaryCopy` | 施工辅助工程概算表 | `copy_table` | `investmentConstructionAuxiliary` |
| `investmentEquipmentInstallationCopy` | 设备及安装工程概算表 | `copy_table` | `investmentEquipmentInstallation` |
| `investmentEquipmentInstallationDeviceList` | 设备及安装工程概算表-设备清单 | `filter_table_projection` | `investmentEquipmentInstallation` |
| `investmentBuildingCopy` | 建筑工程概算表 | `copy_table` | `investmentBuilding` |
| `investmentOtherCostCopy` | 其他费用概算表 | `copy_table` | `investmentOtherCost` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `investmentOriginalTable*` | 技经概算原表 |

## 财务

### 固定字段（49）

| 字段编码 | 中文名 | 单位 | 表格二次规则 |
|---|---|---|---|
| `depreciationYears` | 折旧年限 | 年 | 否 |
| `salvageRate` | 残值率 | % | 否 |
| `repairCost` | 修理费 | — | 否 |
| `materialCostPerKw` | 材料费（元/KW） | — | 否 |
| `constructionPeriodYears` | 建设期（月/年) | — | 否 |
| `workingCapitalUnitKwIndicator` | 流动资金单位千瓦指标 | 元/KW | 否 |
| `workingCapitalLoanRatio` | 流动资金贷款比例 | % | 否 |
| `workingCapitalCapitalRatio` | 流动资本金比例 | % | 否 |
| `workingCapitalLoanInterestRate` | 流动资金贷款利率 | % | 否 |
| `constructionCapitalRatio` | 建设资本金比例 | % | 否 |
| `constructionFundLoanRatio` | 建设资金贷款比例 | % | 否 |
| `repaymentMethod` | 还款方式 | — | 否 |
| `repaymentPeriod` | 偿还年限 | 年 | 否 |
| `annualLoanInterestRate` | 年贷款利率 | % | 否 |
| `staffingCount` | 定员人数 | 人 | 否 |
| `staffSalary` | 人员工资 | 万元 | 否 |
| `welfareOtherRatio` | 职工福利费及其他占比 | % | 否 |
| `financeWorkingCapitalUnit` | 流动资金单位 | — | 是 |
| `financeWorkingCapitalValue` | 流动资金数值 | — | 是 |
| `financeWindSystemCapacityUnit` | 风电系统容量单位 | — | 是 |
| `financeWindSystemCapacityValue` | 风电系统容量数值 | — | 是 |
| `financeAnnualOnGridEnergyUnit` | 风电系统年上网电量单位 | — | 是 |
| `financeAnnualOnGridEnergyValue` | 风电系统年上网电量数值 | — | 是 |
| `financeLaborWelfareTotal` | 人工工资及福利费合计 | 万元 | 是 |
| `financeMaterialCostTotal` | 材料费合计 | 万元 | 是 |
| `financeMaterialCostYears1To13` | 材料费第1年至第13年 | 万元 | 是 |
| `financeRepairCostTotal` | 修理费合计 | 万元 | 是 |
| `financeRepairCostYears1To13` | 修理费第1年至第13年 | 万元 | 是 |
| `financeInsuranceCostTotal` | 保险费合计 | 万元 | 是 |
| `financeInsuranceRate` | 保险费率 | % | 是 |
| `financeOtherCostTotal` | 其他费用合计 | 万元 | 是 |
| `financeLandUseTaxTotal` | 其中：土地使用税合计 | 万元 | 是 |
| `financeMaterialCostYears14To21` | 材料费第14年至第21年 | 万元 | 是 |
| `financeRepairCostYears14To21` | 修理费第14年至第21年 | 万元 | 是 |
| `financeFixedAssetOriginalValueBuildYearAndYear1` | 固定资产原值建设期及第1年 | 万元 | 是 |
| `financeOnGridPriceWithoutTaxTotal` | 上网电价（不含税）合计 | — | 是 |
| `financeOnGridPriceWithTaxTotal` | 上网电价（含税）合计 | — | 是 |
| `financeIncomeTaxTotal` | 所得税合计 | 万元 | 是 |
| `financeOnGridPriceWithoutTaxYears2To13` | 上网电价（不含税）第2年至第13年 | 元/kWh | 是 |
| `financeOnGridPriceWithTaxYears2To13` | 上网电价（含税）第2年至第13年 | 元/kWh | 是 |
| `financeOnGridPriceWithoutTaxYears14To21` | 上网电价（不含税）第14年至第21年 | 元/kWh | 是 |
| `financeOnGridPriceWithTaxYears14To21` | 上网电价（含税）第14年至第21年 | 元/kWh | 是 |
| `financeCurtailmentRateSingle` | 限电率（单一值） | % | 否 |
| `financeCurtailmentRateSegments` | 限电率（分段值） | % | 否 |
| `financeCurtailmentAnnualOnGridEnergyMwh` | 限电后年上网电量 | MWh | 否 |
| `financeCurtailmentEquivalentFullLoadHours` | 限电等效满负荷小时数 | h | 否 |
| `windFarmGridPrice` | 上网电价 | 元/kWh | 否 |
| `financeCapitalIrrWithoutOutgoing` | 资本金财务内部收益率(不含送出) | % | 否 |
| `financeCapitalIrr` | 资本金财务内部收益率 | % | 否 |

### 原表（固定 0 / 可选 21）

| 表格编码 | 表格名称 | 类型 |
|---|---|---|
| `financialIndicatorSummary` | 附表16.1  财务指标汇总表 | 可选，命中时输出 |
| `financeInvestmentPlanFunding` | 附表16.2：项目总投资使用计划与资金筹措表（人民币单位：万元） | 可选，命中时输出 |
| `financeTotalCostEstimate` | 附表16.3：总成本费用估算表（人民币单位：万元） | 可选，命中时输出 |
| `financeTotalCostEstimateContinuation` | 附表16.3：总成本费用估算表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeDepreciationAmortization` | 附表16.4：资产折旧摊销估算表（人民币单位：万元） | 可选，命中时输出 |
| `financeDepreciationAmortizationContinuation` | 附表16.4：资产折旧摊销估算表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeProfitDistribution` | 附表16.5：利润与利润分配表（人民币单位：万元） | 可选，命中时输出 |
| `financeProfitDistributionContinuation` | 附表16.5：利润与利润分配表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeLoanRepayment` | 附表16.6：借款还本付息计划表（人民币单位：万元） | 可选，命中时输出 |
| `financeLoanRepaymentContinuation` | 附表16.6：借款还本付息计划表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeCashFlowPlan` | 附表16.7：财务计划现金流量表（人民币单位：万元） | 可选，命中时输出 |
| `financeCashFlowPlanContinuation` | 附表16.7：财务计划现金流量表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeProjectInvestmentCashFlow` | 附表16.8：项目投资现金流量表（人民币单位：万元） | 可选，命中时输出 |
| `financeProjectInvestmentCashFlowContinuation` | 附表16.8：项目投资现金流量表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeCapitalCashFlow` | 附表16.9：项目资本金现金流量表（人民币单位：万元） | 可选，命中时输出 |
| `financeCapitalCashFlowContinuation` | 附表16.9：项目资本金现金流量表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeInvestorCashFlowParty1` | 附表16.10：投资各方现金流量表（投资方1）（人民币单位：万元） | 可选，命中时输出 |
| `financeInvestorCashFlowParty1Continuation` | 附表16.10：投资各方现金流量表（投资方1）（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeBalanceSheet` | 附表16.11：资产负债表（人民币单位：万元） | 可选，命中时输出 |
| `financeBalanceSheetContinuation` | 附表16.11：资产负债表（续）（人民币单位：万元） | 可选，命中时输出 |
| `financeSensitivityAnalysis` | financeSensitivityAnalysis | 可选，命中时输出 |

### 二次派生表（19）

| 表格编码 | 表格名称 | 操作 | 来源表 |
|---|---|---|---|
| `financeSensitivityAnalysisCopy` | 敏感性分析 | `copy_table` | `financeSensitivityAnalysis` |
| `financeInvestmentPlanFundingCopy` | 项目总投资使用计划与资金筹措表 | `copy_table` | `financeInvestmentPlanFunding` |
| `financeTotalCostEstimateCopy` | 总成本费用估算表 | `copy_table` | `financeTotalCostEstimate` |
| `financeTotalCostEstimateContinuationCopy` | 总成本费用估算表（续） | `copy_table` | `financeTotalCostEstimateContinuation` |
| `financeDepreciationAmortizationCopy` | 资产折旧摊销估算表 | `copy_table` | `financeDepreciationAmortization` |
| `financeDepreciationAmortizationContinuationCopy` | 资产折旧摊销估算表（续） | `copy_table` | `financeDepreciationAmortizationContinuation` |
| `financeProfitDistributionContinuationCopy` | 利润与利润分配表（续） | `copy_table` | `financeProfitDistributionContinuation` |
| `financeLoanRepaymentCopy` | 借款还本付息计划表 | `copy_table` | `financeLoanRepayment` |
| `financeLoanRepaymentContinuationCopy` | 借款还本付息计划表（续） | `copy_table` | `financeLoanRepaymentContinuation` |
| `financeCashFlowPlanCopy` | 财务计划现金流量表 | `copy_table` | `financeCashFlowPlan` |
| `financeCashFlowPlanContinuationCopy` | 财务计划现金流量表（续） | `copy_table` | `financeCashFlowPlanContinuation` |
| `financeProjectInvestmentCashFlowCopy` | 项目投资现金流量表 | `copy_table` | `financeProjectInvestmentCashFlow` |
| `financeProjectInvestmentCashFlowContinuationCopy` | 项目投资现金流量表（续） | `copy_table` | `financeProjectInvestmentCashFlowContinuation` |
| `financeCapitalCashFlowCopy` | 项目资本金现金流量表 | `copy_table` | `financeCapitalCashFlow` |
| `financeCapitalCashFlowContinuationCopy` | 项目资本金现金流量表（续） | `copy_table` | `financeCapitalCashFlowContinuation` |
| `financeInvestorCashFlowParty1Copy` | 投资各方现金流量表（投资方1） | `copy_table` | `financeInvestorCashFlowParty1` |
| `financeInvestorCashFlowParty1ContinuationCopy` | 投资各方现金流量表（投资方1）（续） | `copy_table` | `financeInvestorCashFlowParty1Continuation` |
| `financeBalanceSheetCopy` | 资产负债表 | `copy_table` | `financeBalanceSheet` |
| `financeBalanceSheetContinuationCopy` | 资产负债表（续） | `copy_table` | `financeBalanceSheetContinuation` |

### 动态原表家族（1）

| Key 前缀 | 名称/用途 |
|---|---|
| `financeOriginalTable*` | 财务原表 |
