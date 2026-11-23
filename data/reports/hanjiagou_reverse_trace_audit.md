# 韩家沟报告：映射空值反向追踪

核查对象：`陕西华电靖边韩家沟200MW风电项目可行性研究报告(1).doc`，以及 2026-11-13 16:54 的 `_mapped.json`、`_result.json`、`_details.json`。本次只核查，未改抽取规则或结果。

## 流程结论

- 最终映射共 262 个键，231 个非空、31 个空。逐一核对最终 `result` 后，未发现“最终 result 有值而 mapped 漏写”的空键。因此，映射写出本身不是这 31 个空值的主要原因。
- 二次抽取只消费一次抽取导出的 `result.json`，不能直接回 Word 中找正文或未入选的原表。`electricalPrimaryStationScale` 未进入一次结果时，二次规则报 `table_not_found`，即使正文另有“1回”。
- 最终映射一致性校验只检查键及现有值的一致性，不验证 Word 中是否还有可抽的值。当前空值清单也没有把“未提取”“未提供”“口径不符”区分开。
- 规则不是全部泛化。通用表头/数量列、动态投资分组具备一定泛化性，但仍有固定的 110kV、固定行名，以及要求“200Ah 免维护蓄电池 + DC/DC 装置”同时出现的通信描述规则。

## 有明确原文证据的漏抽或规则过窄

| 映射字段 | 原文证据 | 断点 |
| --- | --- | --- |
| `electricalPrimaryCurrentOutgoingLineCount` | p_0899：110kV 侧规划 1 回出线，本期一次建成；工程规模表也有“110kV出线｜1回” | 一次仅按有“本期规模/远期规模”表头的站规模表识别；该表未进入 `result`，二次继续报 `table_not_found`。可以按正文或项目规模表补通用候选，但需限定升压站出线，避免把 35kV 集电线路 8 回混入。 |
| `totalCollectorRouteLength` | p_1538：全线线路总计长度，新建线路路径长约 **81.6km**，后接单回、双回架空路径 | 一次规则要求“集电线路路径长/总长度”等连续字样；该句在集电线路章节却采用“全线线路总计长度/新建线路路径长”。是表达变体未覆盖。 |
| `communicationPowerDesignDescription` | p_1473～p_1484：通信电源系统、供电范围、`-48V/120A` 高频开关电源 1 套、`48V/200Ah` 电池 1 组 | 一次描述规则只接受包含特定“200Ah 免维护蓄电池 + DC/DC 电源转换装置”的句子。本报告配置形式不同，导致正文虽在，描述字段仍空。 |

## 原文有相近数字，但不能直接填入当前字段

| 字段 | 核查结果 |
| --- | --- |
| `newCableLineLength` | p_2348、p_2351 的 400m、600m 处于 **110kV 送出工程**，合计 1km；不是 35kV 集电线路电缆。集电线路正文说明采用电缆，但未找到同口径的独立路径长度。旧诊断将其标成“规则漏识别”不准确。 |
| `siteEntryRoadLength` | p_3084 明确是“新建进站道路 0.4km”，已提取到 `accessRoadLength`；“进场道路长度”未见独立值，两者不能无条件等同。 |
| `maintenanceRoadLength` | p_3084 是场内道路 122.8km，完工后修复作检修道路；概算写“检修道路（122.8km 的部分需要修复）”。未说明独立新建检修道路长度，当前留空较稳妥。 |
| `landUseTax` | 其他费用概算表有永久征地、长期租地、临时征地三行土地使用税 12.17、43.20、166.61 万元。字段没有定义要单项、总和还是财务年度税费，不能选首行或直接求和。 |
| `financeLandUseTaxTotal` | 二次规则只查“总成本费用估算表”中的“土地使用税”合计行，该行未定位到。概算表的三项金额属于另一口径。 |
| `investment110kvOutgoingLineProjectTotal` | 总概算“110KV送出工程(含对侧改造)”子行有工程总投资 **6942 万元**，动态投资分组已提取；旧字段二次规则只在同一行找“110kV送出线路工程/合计”，故 `row_not_found`。可用分组类型和子行补充，但应保留“含对侧改造”的范围。 |
| `investment330kvOutgoingLineShareTotal` | 总概算的“接入曹城变电站分摊费用”子行有工程总投资 **8000 万元**，但并未写“330kV送出线路分摊费”。字段含义需确认后才能同步。来源识别不应把“曹城”写死。 |
| `investmentProductSupportingCostTotal` | 总概算有“配套费”工程总投资 **22000 万元**，现有动态配套费字段已取到；它与“产品配套费”是否同义，单靠本表不能确定。 |
| `investmentNewEnergyStationPerceptionEquipmentTotal` | 总概算有“智慧风场”动态投资 **1005.70 万元**，是大类金额，不能当作其中“感知设备”单项金额。 |
| `investmentOppositeBayExpansionTotal` | 送出工程名称写“含对侧改造”，没有单列对侧间隔扩建金额，不能从 6942 万元拆分。 |

## 报告未见同口径独立值，或仅有未定方案

- `windResourceSecondaryWindDirections`、`windResourceSecondaryWindEnergyDirections`：一次合并表对应列均为空；只见主风向、主风能方向，未见明确的“次”值。
- `electricalPrimaryExpandedSubstationName`：正文是新建升压站，对侧曹城变备用间隔前期设备已齐，不是扩建升压站。
- `electricalPrimaryFutureOutgoingLineCount`：正文有 110kV 侧规划 1 回、本期一次建成，可作“远期同本期”候选；原表/正文未单列远期出线回数，当前规则未做该推断。
- `windFoundationC15Concrete`、`windFoundationC45Concrete`：建筑工程概算表中风机基础分项只列 C20 垫层、C40 基础混凝土。
- `spoilDisposalSiteCount`、`spoilDisposalSiteArea`：正文提及弃渣场防护，但未见数量和面积。
- `longTermLeaseMaintenanceRoadArea`、`longTermLeaseTowerFoundationArea`、`temporaryLandDirectBuriedCableArea`：未见与这些细项一一对应的面积；不能拿长期租地/临时征地总面积替代。
- `financeCapitalIrrWithoutOutgoing`：只见资本金内部收益率 12.09%，未见“不含送出”单独口径。
- `financeCurtailmentRateSingle`、`financeCurtailmentRateSegments`、`financeCurtailmentAnnualOnGridEnergyMwh`、`financeCurtailmentEquivalentFullLoadHours`：报告有“弃风限电上网电量变化分析”敏感性情景，不等于基准限电率或对应的限电后指标。
- `investmentTechnologySpecialTotal`：未见“科技专篇”独立概算行。

## 原表进入一次结果仍未解决的结构问题

- `landTotalAcquisition`：输出 schema 把原表名定为“9.4.1.工程总征地”，但本报告的 **9.4.1 是“设计依据”**，并无同名原表；一次结果未找到该表，最终映射只剩空表。正文 p_3383 另有永久 45.6 亩、长期 161.8 亩、临时 624.0 亩，可以抽成各自面积字段，但不能冒充原表。
- 固定投资旧字段与动态分组并存：动态分组能抓到 110kV 送出工程，旧的固定标签规则却报 `row_not_found`。这说明“动态识别来源”与“兼容旧映射字段”的同步边界尚未设计完整，并非单纯映射序列化问题。

## 建议的规则改进顺序

1. 给一次抽取加“章节/设备类别 + 标签变体 + 单位 + 来源证据”的候选：先处理升压站本期出线、全线集电线路路径长度、通信电源描述。
2. 二次抽取对同一张表的父子行做作用域解析，允许“父行标识工程 + 子行标识投资类型”；将旧字段映射到动态分组时先验证语义和范围相同。
3. 为每个空值写机器可读的原因：原文无值、数值有但口径不同、一次未入库、二次定位失败、映射未同步。保留证据位置与排除理由。
4. 回归样例应包括不同电压等级、不同变电站名称、概算父子行、重复小节和送出/集电线路同时出现的文档，防止把相邻工程的值串到一起。
