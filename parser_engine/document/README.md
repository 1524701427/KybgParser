# document

文档输入和结构识别层。

| 位置 | 职责 |
|---|---|
| `loaders/` | DOCX、PDF 等不同输入格式的加载适配。 |
| `ast/` | 文档块、表格、证据等稳定数据模型。 |
| `layout_sidecar.py` | OpenDataLoader 版面分析结果的旁路合并。 |
| `structure_parser.py` | 标题、层级和块结构识别。 |
| `section_detector.py` | 为段落和表格挂载规范化章节路径。 |

处理顺序：加载文档 → 构建 AST → 补充版面 → 识别结构 → 识别章节。
