# tables

表格处理和标准表确定性抽取目录。

## 模块职责

| 模块 | 职责 |
|---|---|
| `dataframe_builder.py` | 将 AST 表格转换为 DataFrame，供调试和通用表格处理使用。 |
| `standard_table_extractor.py` | 从 AST 表格中抽取需求文档规定的标准表行数据。 |

## 标准表抽取原则

标准表抽取不走“每个表一个解析器”的路线，而是逐步沉淀少量通用抽表模式：

- `key_value`：指标名和值/单位成对出现的表。
- `matrix`：有明确表头、按列映射的表。
- `grouped_list`：有分组、设备、线路、多行续写的表。

具体标准表通过锚点、章节、表头别名、行名别名和必要的轻量 hook 映射到这些通用模式。`ResultBuilder` 负责把抽取行组装成最终 JSON schema。

当前已迁入 `StandardTableExtractor` 的标准表逻辑：

- `distributionEquipment`：电气一次章节的配电装置部分。按 110kV/GIS/配电装置小段抽取断路器、隔离开关、电流互感器、电压互感器参数，并保留 220kV 需求空行。
