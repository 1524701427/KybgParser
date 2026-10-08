# loaders

Word 文档加载层，将 `.doc/.docx` 转成统一的 `DocumentAST`。

## 加载器

| 加载器 | 作用 |
|---|---|
| `AsposeWordsLoader` | 生产优先，支持 `runtime/` 下 DLL/license 或 Python 包 |
| `SimpleDocxLoader` | 轻量 docx 兜底解析，适合没有 Aspose 时调试 |

加载器只负责读取文档和基础块/表格结构，不负责字段抽取。
