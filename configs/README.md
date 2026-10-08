# configs

这里存放解析流水线、字段、单位、章节和模型注册配置。配置文件决定解析器启用哪些模块、每个字段如何召回、抽取、校验和排序。

## 文件说明

| 文件 | 作用 |
|---|---|
| `pipeline.yaml` | 主流水线配置，控制 BGE、UIE、漏斗剪枝、Reranker、NLI 等模块 |
| `model_registry.yaml` | 模型登记表，用于记录模型名称、用途和模式 |
| `units.yaml` | 通用单位标准名和别名配置 |
| `sections.yaml` | 通用章节类别和别名配置 |
| `output_schema.yaml` | 最终输出章节、字段、原表、组合表和 details trace 规则配置 |
| `validators.yaml` | 通用字段范围校验配置，当前主要字段也会在 `fields/*.yaml` 中内联配置 |
| `fields/*.yaml` | 具体字段定义，是召回、抽取、校验的核心配置 |
| `extraction_fields.json` | 需要抽取的字段清单 JSON，由 `fields/*.yaml` 汇总生成，不是解析结果 |

## pipeline.yaml 核心配置

`pipeline.yaml` 使用 `modules` 作为根节点，每个模块常见字段如下：

| 字段 | 含义 |
|---|---|
| `enabled` | 是否启用模块 |
| `mode` | 运行模式，见下方说明 |
| `threshold` | 模型或抽取置信度阈值 |
| `top_k_per_field` | 每个字段保留多少候选；小于等于 0 表示不剪枝 |
| `max_text_length` | 送入模型的最大文本长度 |
| `batch_size` | 模型批处理大小 |

### enabled 和 mode

模块是否真正参与解析同时看 `enabled` 和 `mode`。当前工厂函数里的统一判断是：只有 `enabled: true` 且 `mode: active` 时，模块才作为有效模块接入主流水线。

| mode | 含义 | 当前效果 |
|---|---|---|
| `active` | 正式运行模式。模块会参与解析，输出会影响候选分数、抽取结果或最终校验。 | 与 `enabled: true` 同时使用时生效。 |
| `shadow` | 影子/旁路模式。用于保留配置、开发调试或未来对比实验，不应影响最终结果。 | 当前大多数模块在工厂装配时不会作为有效模块接入主流程。只有组件内部显式实现 shadow 行为时，才可能加载但不产出最终结果。 |
| `disabled` | 关闭模式。模块不参与解析。 | 不接入主流程。 |

推荐配置方式：

```yaml
# 真正启用
enabled: true
mode: active

# 临时关闭但保留配置
enabled: false
mode: disabled

# 预留/开发观察，不影响最终结果
enabled: true
mode: shadow
```

注意：不要只看 `enabled`。如果 `mode` 不是 `active`，当前解析结果通常不会使用该模块。

### BGE 配置

```yaml
bge_matcher:
  enabled: true
  model_name: C:\Users\EDY\Desktop\WordParser\models\bge\bge-base-zh-v1.5
  threshold: 0.72
  max_text_length: 128
  batch_size: 1
  release_after_match: true
  top_k_per_field: 50
```

BGE 用于字段匹配阶段，判断候选区域和字段描述是否语义相关。它不抽值，只影响候选匹配分。

字段说明：

| 字段 | 含义 |
|---|---|
| `model_name` | BGE 模型本地路径或模型名。 |
| `threshold` | BGE 相似度低于该值时返回 0 分，不参与加权。 |
| `max_text_length` | 候选文本和 query 送入 BGE 前的最大长度。 |
| `batch_size` | BGE 编码批大小。 |
| `memory_aware` | 是否根据可用内存动态降低实际批大小。 |
| `memory_safety_ratio` | 内存感知模式下预留内存比例。 |
| `min_free_memory_mb` | 内存感知模式下至少保留的可用内存。 |
| `release_after_match` | 每个文档 BGE 匹配完成后是否释放模型内存。 |
| `top_k_per_field` | 每个字段最多送入 BGE 的候选数。 |
| `min_match_score` | 候选基础分低于该值时不送入 BGE。 |

### UIE 配置

```yaml
uie_extractor:
  enabled: true
  model_name: uie-base
  threshold: 0.75
  max_text_length: 256
  release_after_extract: true
  top_k_per_field: 15
```

UIE 用于从候选文本中补充抽值。它只处理经过前面阶段筛选的候选，不扫全文。

字段说明：

| 字段 | 含义 |
|---|---|
| `model_name` | UIE 模型名或本地路径。 |
| `threshold` | UIE 输出低于该置信度时丢弃。 |
| `max_text_length` | 送入 UIE 的候选文本最大长度。 |
| `batch_size` | 同一字段 schema 下的 UIE 批处理大小。 |
| `release_after_extract` | 每个文档 UIE 抽取完成后是否释放模型内存。 |
| `top_k_per_field` | 每个字段最多送入 UIE 的候选数。 |
| `min_match_score` | 匹配分低于该值的候选不送入 UIE。 |

### 其它模块开关

| 模块 | 作用 | 主要配置 |
|---|---|---|
| `aspose_loader` | 使用 Aspose 后端加载 Word。 | `enabled`、`mode` |
| `rule_heading_detector` | 规则标题识别。 | `enabled`、`mode` |
| `sklearn_heading_classifier` | 预留的标题分类器。 | `enabled`、`mode` |
| `alias_matcher` | 字段别名匹配。 | `enabled`、`mode` |
| `table_rule_extractor` | 表格规则抽值。 | `enabled`、`mode` |
| `regex_extractor` | 字段正则抽值。 | `enabled`、`mode` |
| `global_pointer_extractor` | 预留实体抽取器。 | `enabled`、`mode` |
| `candidate_ranker` | 预留候选排序模型。 | `enabled`、`mode` |
| `semantic_analyzer` | 规则语义加减分。 | `enabled`、`mode`、`near_window` |
| `validator` | 最终字段校验。 | `enabled`、`mode` |

`near_window` 表示语义分析中字段别名和值之间的近邻窗口大小，窗口内命中会给候选加分。

### funnel 配置

```yaml
funnel:
  enabled: true
  stages:
    extraction_matches: 50
    semantic_candidates: 20
    reranker_candidates: 5
    nli_candidates: 3
```

漏斗剪枝按字段分组保留 Top-K。越往后模型越贵，候选越少。

阶段说明：

| stage | 含义 |
|---|---|
| `extraction_matches` | 抽值前保留的字段匹配候选数。 |
| `semantic_candidates` | 语义分析前保留的抽取候选数。 |
| `reranker_candidates` | Reranker 前保留的抽取候选数。 |
| `nli_candidates` | NLI 前保留的抽取候选数。 |

### semantic_verifier 配置

```yaml
semantic_verifier:
  enabled: true
  reranker_enabled: true
  reranker_model_name: C:\Users\EDY\Desktop\WordParser\models\reranker\bge-reranker-base
  nli_enabled: true
  nli_model_name: C:\Users\EDY\Desktop\WordParser\models\nli\erlangshen-roberta-110m-nli
```

Reranker 判断“字段+候选值”和证据是否相关；NLI 判断证据是否支持“字段=候选值”的声明。

字段说明：

| 字段 | 含义 |
|---|---|
| `reranker_enabled` | 是否启用 Reranker。还需要 `semantic_verifier.enabled: true` 且 `mode: active`。 |
| `reranker_backend` | Reranker 后端，目前支持 `onnx` 或 CrossEncoder 方式。 |
| `reranker_model_name` | Reranker 模型路径。ONNX 后端会读取其 `onnx/model.onnx`。 |
| `reranker_weight` | Reranker 分数对候选总分的加权系数。 |
| `nli_enabled` | 是否启用 NLI。还需要 `semantic_verifier.enabled: true` 且 `mode: active`。 |
| `nli_model_name` | NLI 模型路径。 |
| `nli_weight` | NLI 支持/矛盾标签对候选总分的加权系数。 |
| `batch_size` | Reranker/NLI 验证批大小。 |
| `release_after_verify` | 每个文档验证完成后是否释放模型内存。 |

## model_registry.yaml 配置

`model_registry.yaml` 是模型登记表，记录模型用途和计划运行模式，不直接决定 pipeline 是否启用模块；实际启用以 `pipeline.yaml` 为准。

```yaml
models:
  bge:
    name: 模型名称或路径
    task: semantic_matching
    mode: active
```

字段说明：

| 字段 | 含义 |
|---|---|
| `models.<key>` | 模型登记 key，例如 `bge`、`uie`、`global_pointer`。 |
| `name` | 模型名称或本地路径。 |
| `task` | 模型用途标识。 |
| `mode` | 登记模式，用于说明模型计划状态；具体语义同 pipeline 的 `mode`。 |

## sections.yaml 配置

`sections.yaml` 定义 canonical 章节和别名。章节检测后会把原始标题归一到统一章节名，供字段召回使用。

```yaml
sections:
  wind_resource:
    name: 资源章节
    aliases: [风资源, 风能资源]
```

字段说明：

| 字段 | 含义 |
|---|---|
| `sections.<key>` | 章节类别代码。 |
| `name` | 归一后的 canonical 章节名。 |
| `aliases` | 可匹配的原始标题关键词或别名。 |

## units.yaml 配置

`units.yaml` 定义单位类别、标准单位和别名，用于抽值后的单位识别和归一。

```yaml
units:
  wind_speed:
    standard: m/s
    aliases: [m/s, 米/秒]
```

字段说明：

| 字段 | 含义 |
|---|---|
| `units.<key>` | 单位类别代码。 |
| `standard` | 标准单位写法。 |
| `aliases` | 可识别为该标准单位的别名。 |

## validators.yaml 配置

`validators.yaml` 定义通用字段范围。当前主要字段也会在 `fields/*.yaml` 中内联配置；如果二者同时存在，以实际加载和字段配置使用逻辑为准。

```yaml
validators:
  avgWindSpeed:
    min: 0
    max: 50
```

字段说明：

| 字段 | 含义 |
|---|---|
| `validators.<fieldCode>` | 字段代码。 |
| `min` | 允许的最小值。 |
| `max` | 允许的最大值。 |

## 字段配置格式

字段配置在 `configs/fields/*.yaml` 下，格式如下：

```yaml
fields:
  avgWindSpeed:
    name: 平均风速
    value_type: number
    standard_unit: m/s
    sections:
      include: [风资源, 风能资源]
      exclude: [投资估算]
    aliases: [平均风速, 年平均风速]
    unit_aliases: [m/s, 米/秒]
    patterns:
      - "(?:平均风速).{0,30}?([0-9]+(?:\\.[0-9]+)?)\\s*(m/s|米/秒)?"
    validators:
      min: 0
      max: 50
```

字段含义：

| 字段 | 含义 |
|---|---|
| `name` | 字段中文名，用于导出、UIE schema、语义验证 query |
| `value_type` | 值类型，当前主要支持 `number`、`string` |
| `standard_unit` | 标准单位，最终归一化和单位判断使用 |
| `sections.include` | 推荐召回章节，命中会提高候选基础分 |
| `sections.exclude` | 排除章节，命中会降权或过滤 |
| `aliases` | 字段别名，召回、匹配、语义分析都会使用 |
| `unit_aliases` | 允许识别的单位别名；有单位时只接受白名单内单位 |
| `patterns` | 字段专用正则，第一组通常是值，第二组通常是单位 |
| `validators` | 数值范围校验，用于 resolver 加权和最终 validator |
| `extractors` | 字段级抽取器开关，如 `uie: true` |
| `source_priority` | 来源优先级配置，目前主要用于后续扩展 |

## output_schema.yaml 配置

`output_schema.yaml` 决定最终 JSON 怎么组织，不负责扫描全文抽值。它主要配置：

| 配置项 | 含义 |
|---|---|
| `section_order` | result/details 中章节顺序。 |
| `sections[].fields` | 每个章节展示哪些字段。 |
| `sections[].optional_tables` | 该章节允许输出的稳定表格 key。 |
| `sections[].optional_table_prefixes` | 该章节允许输出的动态表格 key 前缀。 |
| `original_table_groups` | 按表题匹配原文表格，并透传为原表。 |
| `original_table_groups[].key_patterns` | 把命中的表题映射为稳定 key 或动态 key。 |
| `resource_table_key_patterns` | 资源章节原表的稳定 key 补充匹配规则。 |
| `wind_resource_direction_table_rules` | 从风向/风能频率表按最大值推主方向的字段规则。 |

资源章节原表示例：

```yaml
sections:
  - name: 资源章节
    optional_tables:
      - windResourceDirectionEnergyFrequency

original_table_groups:
  - key_prefix: resourceOriginalTable
    title_only: true
    key_patterns:
      - key: windResourceDirectionEnergyFrequency
        patterns:
          - '测风塔.*风向风能频率统计成果表'
          - '风向风能频率统计成果表'

resource_table_key_patterns:
  - key: windResourceDirectionEnergyFrequency
    patterns:
      - '测风塔.*风向风能频率统计成果表'
      - '风向风能频率统计成果表'
```

这样命中的原文表会以 `windResourceDirectionEnergyFrequency` 输出到资源章节，details 中会带 `source.rule.ruleSource = configs/output_schema.yaml` 和原文 `articleLocation`。

## table_field_extractors.yaml 配置（二次抽取）

主解析导出 `result.json` 之后，`parser_engine.tables.table_values` 会按 `table_field_extractors.yaml`
从已抽取的表格里做第二次抽取。规则是声明式的，核心原语：

| 原语 | 作用 |
|---|---|
| `source_table.name_patterns` | 表题正则，优先用它定位来源表；支持 `\s*` 容忍空格差异。 |
| `source_table.required_columns` | 列名约束，必须全部命中。 |
| `source_table.required_text` | 正文内容约束，必须全部命中（扫描整表，不只看前几行）。 |
| `source_table.name_match_content` | `true` 时，表题不命中可回退到“列名+前几行”内容匹配，兼容表题不贴在表前的报告。 |
| `row.type` | `label`（默认）/ `index` / `last` / `first`。 |
| `row.column` / `row.column_aliases` | 只在指定列里匹配行标签。 |
| `row.aliases` | 任一业务别名命中即可。 |
| `row.all_aliases` | 声明的关键词必须全部命中，用于“风机+塔筒”等组合设备。 |
| `row.exclude_aliases` | 命中排除词就拒绝该行，用于区分普通设备与成套设备。 |
| `row.match` | 多列联合匹配（例如塔号列 + 指标列），用于“某塔的某指标”行。 |
| `row.allow_ambiguous` | `true` 时多行同分取第一行，不再报歧义。 |
| `column.type` | `label`（默认）/ `index` / `row_number`（从行文本解析数值，适合“综合风切变 0.258”这类行）。 |
| `column.aliases` | 兼容同一业务列的不同列名。 |
| `column.occurrence` | 同名列按从 0 开始的出现顺序选择。 |
| `column.offset` | 命中表头后向左或向右偏移，适配多层合并表头。 |
| `value_pattern(s)` | 从目标单元格或合并后的规格文本中截取局部值。 |
| `value_groups` / `value_join` | 将多个正则捕获组合并为一个结果。 |
| `conversion` | 声明单位换算。 |
| `dedupe` | `column_values` 是否去重；逐行对齐数据应设为 `false`。 |
| `operation` | `cell` / `cell_items` / `max_row_label` / `sector_max` / `column_values` / `cell_series` / `cell_ratio` / `table_projection` / `filter_table_projection` / `copy_table` / `sum_fields`。`cell_items` 用一套表、行列规则按 `items` 批量生成字段。 |
| `towers` | 把一条规则按测风塔号模板展开成 N 条：`{tower}` 原始塔号、`{tower_clean}` 去符号塔号。可写固定列表，也可用 `from_table` 从表格动态发现塔号（推荐，避免塔号写死）。 |

塔号建议动态发现，表号建议用内容锚点，避免不同报告编号不一致时失效。文件顶部定义了动态塔号源：

```yaml
x_dynamic_wind_towers: &dynamic_wind_towers
  from_table:
    section: 资源章节
    source_table:
      name_patterns: ['测风塔基本情况表', '测风塔\s*基本情况表']
      required_columns: ['测风塔']
    column: {aliases: ['测风塔', '测风塔编号', '塔号']}
    value_pattern: '[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]'
```

常用示例：

```yaml
# 塔号和高度都动态展开；表题不写死表号、塔号或160m等固定高度。
- field_code: windResource{tower_clean}PowerDensity{height_clean}
  field_name: '{tower}测风塔{height}平均风功率密度'
  section: 资源章节
  towers: *dynamic_wind_towers
  variables:
    height: *dynamic_resource_heights
  source_table:
    name_patterns: ['{tower}.*(?:风能参数|平均风速|风功率密度)']
    name_match_content: true
    required_columns: ['平均风功率密度', '高度']
  row: {type: label, column: [高度], patterns: ['{height}']}
  column: {aliases: ['平均风功率密度', '风功率密度']}
  value_type: number
  unit: W/m²

# 机型列名也可用正则动态匹配，例如任意 WTG 机型都命中 WTG\d+-\d+。
- field_code: generationAnnualOnGridEnergySelected
  section: 发电量章节
  source_table: {key: generationSummary, name_patterns: ['年上网电量估算表', '风电场.*(?:发电量|上网电量)计算(?:成果)?表']}
  row: {type: label, column: 项目, aliases: ['年上网电量']}
  column: {aliases: ['WTG\d+-\d+', 'WTG\d+', '指标']}
  value_type: number
```

`from_table` 定位不到“测风塔基本情况表”时，会回退到扫描该章节全部表格，按 `value_pattern` 统一发现塔号，兼容塔号散落在其它表里的报告。

### 新增最终固定字段的操作清单

1. 在 `table_field_extractors.yaml` 增加二次抽取规则。
2. 在 `output_schema.yaml` 对应 `sections[].fields` 中加入字段编码。
3. 在 `output_schema.yaml` 的 `fields:` 中登记中文名和单位。
4. 在 `tests/test_table_values.py` 增加回归测试。

最终章节、字段名和单位只以 `output_schema.yaml` 为准，Python 中不再维护重复字段清单。若字段只需要命中时出现，可以省略第 2、3 步。


## 配置原则

- 召回阶段宁可略宽，后续漏斗逐步减少。
- 单位缺失不直接判错；只有出现单位且不在白名单时才降权或告警。
- `regex_fallback` 只作为兜底，最终排序会给较低权重。
- Reranker/NLI 模型较重，优先通过 `funnel.stages` 控制候选数。
