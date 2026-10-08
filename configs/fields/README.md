# configs/fields

这里按业务领域拆分字段配置。每个 YAML 文件都以 `fields` 为根节点，下面每个 key 是字段代码。

## 文件说明

| 文件 | 字段范围 |
|---|---|
| `wind_resource.yaml` | 风资源指标，如平均风速、50 年一遇最大风速 |
| `investment.yaml` | 投资指标，如装机容量、单位千瓦投资 |
| `investment_breakdown.yaml` | 投资构成，如设备购置费、建安工程费、预备费、建设期利息 |
| `generation.yaml` | 发电量指标，如年上网电量、等效满负荷小时数 |
| `finance.yaml` | 财务指标，如资本金 IRR、全投资税后 IRR |
| `finance_extended.yaml` | 财务扩展指标，如资本金比例、营业收入、净现值、偿债备付率 |
| `electrical.yaml` | 电气指标，如电压等级 |
| `electrical_system.yaml` | 电气系统指标，如集电线路、箱变、升压站、主变、接入点 |
| `project_overview.yaml` | 项目概况，如项目名称、地点、建设单位、建设规模、用地面积 |
| `site_conditions.yaml` | 场址建设条件，如地形地貌、工程地质、抗震烈度、风压雪压、交通距离 |
| `turbine.yaml` | 风机选型参数，如机型、轮毂高度、风轮直径、切入/额定/切出风速 |
| `civil_construction.yaml` | 土建施工指标，如道路长度、基础型式、建设工期、开工/投产时间 |
| `environment.yaml` | 环保水保指标，如环保投资、水保投资、环境影响结论、噪声措施 |
| `report_required_data.yaml` | 来自 `可研报告解析（陕西华电靖边韩家沟200MW项目）.docx` 中各章节 `解析数据` 下的实际字段清单 |

## 字段配置模板

```yaml
fields:
  fieldCode:
    name: 字段中文名
    value_type: number
    standard_unit: 标准单位
    sections:
      include: [推荐章节关键词]
      exclude: [排除章节关键词]
    aliases: [字段别名]
    unit_aliases: [允许识别的单位]
    patterns:
      - "字段正则"
    validators:
      min: 0
      max: 100
```

## 关键字段含义

| 字段 | 说明 |
|---|---|
| `fieldCode` | 程序内部字段代码，也是最终 JSON 的 key |
| `name` | 字段中文名，进入 UIE schema、Reranker query、NLI hypothesis |
| `value_type` | 字段类型，`number` 会参与数值校验和候选降权 |
| `standard_unit` | 标准单位；最终输出尽量归一到该单位 |
| `sections.include` | 候选所在章节包含这些关键词时加分 |
| `sections.exclude` | 候选所在章节包含这些关键词时降权或排除 |
| `aliases` | 字段召回、alias 匹配、语义近邻分析使用 |
| `unit_aliases` | 抽到单位时必须在该列表或等于 `standard_unit` |
| `patterns` | 正则抽取规则；优先使用字段专用正则 |
| `validators.min/max` | 合理范围；参与 resolver 加权和最终校验 |
| `extractors` | 控制该字段是否允许 UIE/实体模型等增强抽取 |

## 字段配置完整说明

### 基础字段

| 字段 | 说明 |
|---|---|
| `name` | 字段中文名，进入导出、UIE schema、Reranker query、NLI hypothesis。 |
| `value_type` | 字段值类型。常见值为 `number`、`string`；`number` 会参与数值归一和范围校验。 |
| `standard_unit` | 标准单位。最终归一化和单位白名单判断会参考它。 |
| `aliases` | 字段别名。用于候选召回、alias 匹配和语义近邻分析。 |
| `unit_aliases` | 允许识别的单位别名。抽到单位时必须匹配该列表或 `standard_unit`。 |
| `patterns` | 字段专用正则。第一捕获组通常是值，第二捕获组通常是单位。 |
| `derived_patterns` | 派生正则。用于从更复杂的上下文中构造字段值。 |
| `multi_number_pattern` | 多数值正则。用于同一证据里抽多个数字并由后续逻辑选择或组合。 |
| `value_headers` | 表格规则抽取时可被视为“值列”的表头关键词。 |
| `preferred_values` | 优先值列表。resolver 可据此偏好符合业务预期的候选。 |
| `preferred_methods` | 优先抽取方法列表，例如偏好 `table_lookup` 或 `regex`。 |
| `extraction_policy` | 字段级抽取策略标识，用于 resolver 或后处理区分字段行为。 |
| `regex_fallback_enabled` | 是否允许正则兜底抽取。关闭后只使用专用正则或其它抽取器。 |
| `coarse_table_rule_enabled` | 是否允许较宽松的表格规则兜底。用于减少误抽时可关闭。 |

### 章节配置

| 字段 | 说明 |
|---|---|
| `sections.include` | 推荐召回章节。候选位于这些章节时加分。 |
| `sections.exclude` | 排除章节。候选位于这些章节时降权或过滤。 |

### 抽取器开关

`extractors` 控制单个字段允许哪些抽取器参与。模块本身仍需在 `configs/pipeline.yaml` 中启用。

| 字段 | 说明 |
|---|---|
| `extractors.table_rule` | 是否允许表格规则抽取。 |
| `extractors.regex` | 是否允许正则抽取。 |
| `extractors.uie` | 是否允许 UIE 对该字段补充抽取。 |
| `extractors.global_pointer` | 是否允许 GlobalPointer 实体抽取器。当前主要为预留。 |

### 表格 lookup 配置

`table_lookup` 用于“按行名/列名定位一个单元格”的表格。

| 字段 | 说明 |
|---|---|
| `table_lookup.header_rows` | 表头行数。用于从前几行识别列名。 |
| `table_lookup.row_aliases` | 目标行名别名。命中这些行后取对应值列。 |
| `table_lookup.row_label_columns` | 可作为行名的列索引列表。 |
| `table_lookup.row_label_match` | 行名匹配方式，例如包含匹配或更严格匹配。 |
| `table_lookup.row_label_reject_any` | 行名中出现这些关键词时拒绝该行。 |
| `table_lookup.column_aliases` | 目标值列别名。 |
| `table_lookup.column_occurrence` | 同名/相似列出现多次时取第几列。 |

字段级快捷项也可直接使用：

| 字段 | 说明 |
|---|---|
| `row_label_aliases` | 行名别名，作用类似 `table_lookup.row_aliases`。 |
| `row_label_columns` | 行名列索引，作用类似 `table_lookup.row_label_columns`。 |
| `row_label_match` | 行名匹配方式。 |
| `row_label_reject_any` | 行名拒绝关键词。 |

### 表格聚合配置

`table_aggregate` 用于从一列或多列中聚合多个数值，例如求和。

| 字段 | 说明 |
|---|---|
| `table_aggregate.op` | 聚合操作，目前主要为 `sum`。 |
| `table_aggregate.header_rows` | 表头行数。 |
| `table_aggregate.value_headers` | 可作为聚合值列的表头关键词。 |
| `table_aggregate.column_occurrence` | 多个候选列时选择第几列。 |
| `table_aggregate.require_any` | 表格文本中至少需要出现的锚点关键词之一。 |
| `table_aggregate.min_values` | 至少需要聚合到多少个数值才接受。 |
| `table_aggregate.precision` | 聚合结果保留小数位。 |
| `table_aggregate.unit` | 聚合结果单位。 |
| `table_aggregate.prefer_summary` | 是否优先使用汇总行或合计行。 |
| `combine_table_aggregates` | 当一个逻辑表被 Word 拆成多个相邻表时，是否组合多个聚合结果。 |
| `min_aggregate_parts` | 组合聚合时至少需要多少个片段。 |
| `aggregate_precision` | 组合聚合结果保留小数位。 |

### 表格列表配置

`table_list` 用于从表格中抽取列表型值。

| 字段 | 说明 |
|---|---|
| `table_list.header_rows` | 表头行数。 |
| `table_list.column_aliases` | 目标列别名。 |
| `table_list.reject_any` | 行文本中出现这些关键词时跳过。 |
| `table_list.format` | 列表输出格式，例如拼接方式。 |

### 行上下文配置

`row_context` 用于约束表格候选行，避免抽到相邻但不属于目标字段的行。

| 字段 | 说明 |
|---|---|
| `row_context.require_any` | 候选行或附近上下文至少需要出现的关键词之一。 |
| `row_context.reject_any` | 候选行或附近上下文出现这些关键词时拒绝。 |
| `row_context.row_require_any` | 当前行文本至少需要出现的关键词之一。 |

### 多值和值映射

| 字段 | 说明 |
|---|---|
| `multi_value` | 字段是否允许输出多个值。 |
| `value_map` | 将原始抽取值映射为标准值。用于同义写法、机型等级、线路形式等归一。 |

`value_map` 下一级 key 是动态原始值，不是固定配置字段。例如：

```yaml
value_map:
  IECIIIa: IEC IIIa
  桩基: 基桩
  生活区: 生活区
```

含义是“抽到左侧文本时，输出右侧标准值”。因此 `value_map.IECIIIa`、`value_map.桩基` 这类项不需要逐个在 README 中枚举，只需要说明 `value_map` 的映射规则。

### 来源优先级

`source_priority` 用于 resolver 对来源证据加权。

| 字段 | 说明 |
|---|---|
| `source_priority.sections` | 命中特定章节时的加权配置，key 为章节名或章节关键词。 |
| `source_priority.table_captions` | 命中特定表题/caption 时的加权配置。 |

### 校验配置

`validators` 用于候选级加权和最终字段校验。

| 字段 | 说明 |
|---|---|
| `validators.min` | 数值最小值。 |
| `validators.max` | 数值最大值。 |
| `validators.allow_pattern` | 字符串值必须匹配的允许正则。 |
| `validators.reject_patterns` | 字符串值命中这些正则时拒绝。 |
| `validators.reject_contains` | 值文本包含这些关键词时拒绝。 |
| `validators.prefer_evidence_contains` | 证据文本包含这些关键词时加权。 |
| `validators.reject_evidence_contains` | 证据文本包含这些关键词时拒绝或降权。 |
| `validators.require_evidence_all` | 证据文本必须同时包含这些关键词。 |

## 正则约定

- 第一捕获组通常是字段值。
- 第二捕获组通常是单位。
- 字段名到数值之间建议限制距离，例如 `.{0,30}?`，避免跨句误抽。
- 正则应尽量围绕字段 alias 编写，不建议写过宽的纯数字规则。

示例：

```yaml
patterns:
  - "(?:平均风速|年平均风速).{0,30}?([0-9]+(?:\\.[0-9]+)?)\\s*(m/s|米/秒)?"
```

## 调整建议

- 如果漏抽字段，优先增加 `aliases` 和 `sections.include`。
- 如果误抽字段，优先收紧 `patterns` 和 `sections.exclude`。
- 如果单位异常，检查 `unit_aliases` 是否过宽或缺失。
- 如果候选最终选错，检查 `validators` 范围和证据章节是否合理。
