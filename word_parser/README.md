# WordParser 代码结构

生产解析实现统一在 `word_parser/`；根目录 `parser_engine/` 已退役。
`word_parser.core`、`word_parser.document`、`word_parser.extraction` 和
`word_parser.output` 是保留的公共导入入口，具体实现不再委托旧引擎。

```text
word_parser/
  application/      对外 API、装配、流水线及 HTTP 服务
  document/         Word/PDF 读取、AST、结构及原表识别
  discovery/        预抽取指标扫描
  primary/          一次抽取
  domains/          专业业务规则
  secondary/        二次表格取值、概算补充与校验
  mapping/          最终映射与一致性检查
  output/           result/details/mapped 结果构建
  config/           YAML 配置读取
  core/             历史公共导入路径，轻量兼容层
  extraction/       公共导入与规则辅助代码
```

正式调用使用 `from word_parser.core import parse_document_with_table_values`
或 `from word_parser.application.api import create_parser`。
字段和原表配置位于 `configs/`。不要在新代码中引入已退役的 `parser_engine`。
历史来源标签 `ruleSource` 可能仍保留旧路径文本；它们是审计数据，不是 Python 导入。
