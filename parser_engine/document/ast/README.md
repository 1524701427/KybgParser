# ast

定义解析过程中共享的数据结构。

## 主要对象

| 对象 | 作用 |
|---|---|
| `DocumentAST` | Word 文档解析后的统一结构，包含段落块和表格 |
| `DocumentBlock` | 段落、标题等文本块 |
| `DocumentTable` | 表格结构和单元格内容 |
| `Candidate` | 某字段的候选文本或候选表格区域 |
| `FieldMatch` | 字段匹配结果，包含匹配方法和分数 |
| `Extraction` | 抽取出的候选字段值 |
| `FieldEvidence` | 结果证据，记录来源文本、页码、章节等 |
| `ParsedField` | 最终导出的字段结果 |

这些对象贯穿整个流水线，不应放入具体模型或业务逻辑。
