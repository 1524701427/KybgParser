# parser_engine

这个目录里是解析引擎内部实现。日常使用和业务规则调整不需要从每个子目录看起，优先看下面 4 个入口。

## 日常只看

| 文件 | 用途 |
|---|---|
| `parser_engine/api.py` | 业务侧统一入口：主解析、二次抽取、完整解析。 |
| `configs/output_schema.yaml` | 主解析输出章节、字段、原表清单。 |
| `configs/table_field_extractors.yaml` | 二次抽取规则，处理“从已抽到的表里按行列再取值”。 |
| `data/predictions/*_details.json` | 排错入口，查看来源、表定位、NIL 原因。 |

## 运行链路

```text
文档 -> 主解析 -> result.json
              \-> details.json
result.json -> 二次抽取 -> result.json 合并最终结果
                         \-> details.json 追加 tableValueExtraction 过程数据
```

主解析负责把文档、章节、字段和原表抽出来；二次抽取只基于 `result.json` 做表内行列取值，不重新读 Word。

## 当前顶层模块

| 模块 | 说明 |
|---|---|
| `api.py` | 业务侧统一入口。 |
| `core/` | 配置加载、流程编排、解析服务。 |
| `document/` | 文档加载、AST、版面、章节和结构识别；单文件处理器直接放在本层。 |
| `extraction/` | 字段召回、匹配、抽取、归一、剪枝、语义验证、冲突消解和校验；通过 `extraction/__init__.py` 统一引用。 |
| `tables/` | 原表、标准表和二次表内抽取。 |
| `output/` | `result.json` 和 `details.json` 导出。 |
| `ml/` | BGE、Reranker 等模型适配。 |

训练、评估、弱标注等开发辅助代码放在项目根目录的 `tools/`，不再放进 `parser_engine` 主运行包。

## 改代码时怎么选位置

- 只改要抽哪些字段/表：改 `configs/output_schema.yaml` 或 `configs/fields/*.yaml`。
- 已经有表，但还要从表里取具体单元格：改 `configs/table_field_extractors.yaml`。
- 表没有进入 `result.json`：先看 `tables/` 和 `output/` 的原表定位。
- 字段值错了：先看 `details.json`，再决定是否改 `extraction/`。
- 二次抽取格式、行列选择、动态塔号/高度：改 `tables/table_values.py`。

固定输出字段的章节、中文名和单位以 `configs/output_schema.yaml` 为唯一来源；新增普通字段不需要再到 `output/result_builder.py` 同步 Python 清单。完整示例见根目录 README 的“新增抽取规则”和 `configs/README.md`。

## 当前简化原则

外部只暴露 `parser_engine/api.py`。其他子目录都当内部实现看，不建议业务脚本直接 import 内部类。

目录只按稳定的领域职责拆分。单文件能力不再额外建立一层目录，例如：

- `document/section_detector.py`，而不是 `document/sections/section_detector.py`；
- `extraction/normalizer.py`，而不是 `extraction/normalization/normalizer.py`；
- `tables/table_values.py`，而不是 `tables/table_values/resolver.py`。

后续如果继续瘦身，优先拆小超大文件，而不是改业务逻辑：

- `output/result_builder.py` 过大，适合按资源、发电量、电气、财务拆成 builder helper。
- `tables/table_values.py` 仍然偏大，后续适合按 DSL 展开、行列选择和结果合并拆成同层 helper。
