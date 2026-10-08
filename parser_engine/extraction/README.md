# extraction

完整字段抽取流水线。各处理器都在本目录中，通过 `parser_engine.extraction`
统一导入，避免为单个类建立一层子包。

## 处理顺序

```text
CandidateRetriever
  -> FieldMatcher
  -> FunnelPruner
  -> ValueExtractor
  -> Normalizer
  -> SemanticAnalyzer / SemanticVerifier
  -> CandidateResolver
  -> Validator
```

| 文件 | 职责 |
|---|---|
| `candidate_retriever.py` | 从文档 AST 召回可能的段落和表格。 |
| `field_matcher.py` | 结合别名、章节和 BGE 分数匹配字段。 |
| `funnel_pruner.py` | 分阶段保留 Top-K 候选。 |
| `value_extractor.py` | 使用表格规则、正则或模型抽取原始值。 |
| `normalizer.py` | 统一值和单位格式。 |
| `semantic_analyzer.py` | 规则语义加减分。 |
| `semantic_verifier.py` | 可选 Reranker/NLI 验证。 |
| `candidate_resolver.py` | 解决同字段多候选冲突。 |
| `validator.py` | 校验最终字段的缺失、范围和单位。 |

## 抽取方式

| 方法 | 作用 |
|---|---|
| `table_rule` | 从表格行中抽值，适合指标表 |
| `regex` | 使用字段配置的专用正则抽值 |
| `regex_fallback` | 通用数字兜底，分数较低 |
| `uie` | UIE 模型补充抽值 |
| `global_pointer` | 预留实体抽取模型 |

抽取器应保留 `raw_value` 和原始 `evidence.text`，后续语义验证依赖这些原始信息。
