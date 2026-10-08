# export

结果导出层。`JsonExporter` 为每个解析文档写出两个 JSON 文件：

- `*_result.json`：精简业务结果，给业务系统或后续程序使用。
- `*_details.json`：按结果顺序组织的人工核对视图，用来看每个值从哪来、过程怎么走、模型有没有参与。

## result JSON

`result` 文件只包含：

- `filePath`
- `sections`

字段值和表格都放在需求模块对应的 `sections` 里。它不包含候选、证据、模型打分、调试过程。

示例：

```json
{
  "filePath": "sample.docx",
  "sections": [
    {
      "name": "发电量章节",
      "fields": [],
      "tables": [
        {
          "key": "generationSummary",
          "name": "发电量指标表",
          "columns": ["年理论发电量[万kW·h]", "尾流平均折减[%]"],
          "data": [[37177.93, 5]]
        }
      ]
    }
  ]
}
```

## details JSON

`details` 文件用于人工核对。它的 `sections` 顺序与 `result.sections` 一致，所以讲解和排查时可以按同一个章节顺序看。

顶层结构：

| 字段 | 类型 | 含义 |
|---|---|---|
| `filePath` | string | 被解析的原始 Word 文件路径。 |
| `summary` | object | 文档块数、表格数、候选数、抽取数等总览。 |
| `sections` | array | 按 `result.json` 章节顺序组织的人工核对视图。 |
| `fieldIndex` | object | 按 `fieldCode` 建立的字段索引，便于程序或人工快速搜索。 |
| `tableIndex` | object | 按表 `key` 建立的表格索引。 |

### summary

| 字段 | 含义 |
|---|---|
| `blockCount` | 文档解析出的段落/块数量。 |
| `tableCount` | 文档解析出的表格数量。 |
| `resolvedFieldCount` | 有 trace 的字段数量。 |
| `finalFieldCount` | 最终输出字段数量。 |

### sections[]

每个章节结构：

```json
{
  "name": "发电量章节",
  "fields": [],
  "tables": []
}
```

| 字段 | 含义 |
|---|---|
| `name` | 章节/需求模块名。 |
| `fields` | 该章节下字段的人工核对摘要。顺序跟 `result` 中字段顺序一致。 |
| `tables` | 该章节下表格的人工核对摘要。顺序跟 `result` 中表格顺序一致。 |

## 字段 Trace

`sections[].fields[]` 是简化核对视图，`fieldIndex.<fieldCode>` 是按字段索引的完整视图。

章节内字段结构：

| 字段 | 含义 |
|---|---|
| `fieldCode` | 内部字段编码。 |
| `name` | 字段中文名。 |
| `value` | 最终值。 |
| `unit` | 单位。 |
| `status` | `PASS`、`MISSING` 等状态。 |
| `rule` | 命中的配置规则、正则、resolver 或 builder。 |
| `articleLocation` | 原文定位摘要。 |
| `sourceText` | 简短原文证据文本。 |

`fieldIndex.<fieldCode>` 额外保留主来源对象和多来源列表：

| 字段 | 含义 |
|---|---|
| `fieldCode` | 内部字段编码。 |
| `name` | 字段中文名。 |
| `value` | 最终值。 |
| `unit` | 单位。 |
| `status` | `PASS`、`MISSING` 等状态。 |
| `source` | 最终采用值的主要来源。 |
| `sources` | 多来源字段的来源列表，存在时出现。 |
| `rule` | 命中的配置规则、正则、resolver 或 builder。 |
| `articleLocation` | 原文定位摘要。 |

### source

| 字段 | 含义 |
|---|---|
| `sourceType` | 来源类型，常见为 `paragraph`、`table`。 |
| `text` | 原始证据文本或确定性来源说明。 |
| `score` | 来源或证据分数。 |
| `matchMethod` | 来源方法，例如 `regex`、`table_rule`、`deterministic_override`。 |
| `blockId` | 段落 ID。没有精确段落定位时为 null。 |
| `tableId` | 表格 ID。不是表格来源时为 null。 |
| `page` | 页码；解析器未提供时为 null。 |
| `sectionPath` | 原文证据所在章节路径。 |
| `meta` | 规则或 resolver 附加的来源元信息。 |

### rule

`rule` 用于说明值是怎么来的。常见形态：

```json
{
  "ruleSource": "configs\\fields\\report_required_data.yaml",
  "configuredField": "accessStationName",
  "configuredRule": "电气一次正文接入汇集站名称",
  "matchedPattern": "...",
  "matchedText": "打捆送至曹城330kV汇集站"
}
```

resolver 或 builder 字段可能只有：

```json
{"resolver": "cover_ocr"}
```

## 表格 Trace

`sections[].tables[]` 是简化核对视图，`tableIndex.<key>` 是表格索引视图。原表在章节视图里只保留定位摘要；完整数据看 `result.json`，完整表级索引看 `tableIndex`。

| 字段 | 含义 |
|---|---|
| `key` | 表格内部代码，例如 `generationSummary`。 |
| `name` | 表中文名。 |
| `section` | 所属章节。 |
| `tableType` | `original_table` 或 `combined_table`。 |
| `columns` | 输出列名。 |
| `columnKeys` | 输出列内部 key。 |
| `rowCount` | 输出表行数。 |
| `sampleRows` | 前 1 行数据样例。完整数据看 `result.json`。 |
| `valueTraces` | 表格首行每一列对应的来源和过程说明。 |
| `source` | 表级代表性来源摘要。 |
| `articleLocation` | 原文定位摘要。 |
| `rule` | 原表或组合表命中的规则摘要。 |
| `extractionTrace` | 原表标题命中、配置 key、表位置等 trace。 |

原表章节视图示例：

```json
{
  "key": "windResourceDirectionEnergyFrequency",
  "name": "表2.6-16 测风塔风向风能频率统计成果表",
  "tableType": "original_table",
  "source": {
    "tableId": "t_0040",
    "sectionPath": ["2 风能资源", "2.6 代表年分析"],
    "caption": "表2.6-16 测风塔风向风能频率统计成果表"
  },
  "articleLocation": {
    "sectionPath": ["2 风能资源", "2.6 代表年分析"],
    "tableId": "t_0040",
    "caption": "表2.6-16 测风塔风向风能频率统计成果表"
  }
}
```

### valueTraces[]

`valueTraces` 是表格核对的主要入口。它按 `columns` 顺序排列，每个对象解释这一列首行值从哪来。

| 字段 | 含义 |
|---|---|
| `column` | 列中文名。 |
| `columnKey` | 列内部 key。 |
| `value` | 该列首行输出值。 |
| `fieldCode` | 若该列对应某个字段，则给出字段编码。 |
| `source` | 该列值采用的主要来源。 |
| `pipeline` | 兼容旧 trace 的过程统计，当前简化 details 中可能为空。 |
| `decision` | 兼容旧 trace 的选择过程，当前简化 details 中可能为空。 |

示例：

```json
{
  "column": "尾流平均折减[%]",
  "columnKey": "wakeLossPercent",
  "value": 5,
  "fieldCode": "wakeLossPercent",
  "source": {
    "sourceType": "paragraph",
    "text": "...平均尾流影响为5.0%...",
    "matchMethod": "deterministic_override"
  }
}
```

### table.source

表级 `source` 是代表性来源摘要，用于快速定位原文表格。列级准确来源优先看 `valueTraces[]`。

| 字段 | 含义 |
|---|---|
| `kind` | 来源粒度，例如 `document_table_cell`、`document_table`、`result_builder_table`。 |
| `tableId` | 原文 AST 表格 ID。 |
| `sourceRow` | 原文表格行号。 |
| `sourceColumn` | 原文表格列号。 |
| `sourceText` | 原文单元格文本。 |
| `caption` | 原文表题。 |
| `description` | 表级来源说明。 |

## 讲解建议

对外讲 `details.json` 时按这三句话解释即可：

1. `result.json` 是最终答案，`details.json` 是同样章节顺序下的取值过程。
2. 字段看 `sections[].fields[]`，原表看 `sections[].tables[]`，需要快速搜索时看 `fieldIndex` 和 `tableIndex`。
3. 每个值重点看三块：`rule` 看命中规则，`articleLocation` 看原文位置，`source/sourceText` 看证据文本或表题。

## 职责边界

导出层不重新做业务判断，只结构化输出 resolver、validator 和确定性表格逻辑已经确定的数据，并暴露足够的过程信息用于人工核对。
