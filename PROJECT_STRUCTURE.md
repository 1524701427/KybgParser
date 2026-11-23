# 项目结构与解析流程

日常使用入口是 `word_parser.core`。完整流程从
`word_parser/application/workflow.py` 开始；一次抽取内部流程见
`word_parser/application/pipeline.py`。

```text
word_parser/
  application/
    api.py                 对外 Python 函数
    workflow.py            完整解析编排：一次、二次、最终映射
    pipeline.py            文档、预扫描及一次抽取编排
    factory.py             组件装配
    http_api.py            HTTP 接口
  document/
    word/                   .doc/.docx 读取
    pdf/                    .pdf 读取
    ast/                    统一文档结构及抽取证据类型
    tables/                 原始表格识别与标准化
    cover_ocr.py            封面 OCR
    layout_sidecar.py       PDF 版面信息
    section_detector.py    章节识别
    structure_parser.py    文档结构整理
    router.py               按扩展名选择读取器；Word 可附加 PDF 版面信息
    stage.py                统一文档结构和章节识别
  discovery/               前置指标发现，暂存名称和值
  primary/                 一次抽取：召回、匹配、取值、归一化、选值
  domains/                 风资源、电气、土建、财务等现有专业规则
  secondary/
    table_values/           二次表内取值的规则执行器
    stage.py                从一次结果中已有的表补取值
  mapping/                 二次结果同步、映射组合和一致性检查
  extraction/              ResultBuilder 共用的规则与文档辅助方法
  output/                  一次结果的章节、详情及 JSON 组装
  config/                  读取 configs/ 中的配置
configs/                   字段、章节、表格和输出规则；格式保持不变
```

## 完整入口的数据顺序

`parse_document_with_table_values()` 执行：

1. Word/PDF 读取和章节识别，形成统一文档结构。
2. 前置扫描发现指标，暂存证据。
3. 一次抽取按现有规则取值；前置扫描只补一次未取到的数值字段。
4. 结果构建器按现有优先级运行专业规则，并形成一次结果。
5. 二次抽取读取一次结果中保留的表，只补空字段，不覆盖已有值。
6. 在二次抽取后创建映射，沿用现有映射组合规则并检查 `result` 与 `mapped` 一致性。

完整入口的二次阶段直接使用内存中的一次结果；旧的文件增强入口仍可读取
`*_result.json`。`parse_document()` 只执行一次抽取，并保持原有的三种 JSON 输出。

## 兼容与修改位置

- 普通字段名称、别名和校验条件：`configs/fields/*.yaml`
- 章节别名：`configs/sections.yaml`
- 二次表格规则：`configs/table_field_extractors.yaml`
- 输出字段及占位符：`configs/output_schema.yaml`
- 特殊专业规则：`word_parser/domains/`
- 二次抽取实现位于 `word_parser/secondary/table_values/`。
- `word_parser.core`、`word_parser.document`、`word_parser.extraction` 和
  `word_parser.output` 提供简短的包级导入，直接指向对应实现。

此次迁移保持字段规则、优先级、NIL 行为和输出 schema。目录整理本身不提高
跨报告抽取准确率；它让每一步的修改位置和数据来源更清楚。
