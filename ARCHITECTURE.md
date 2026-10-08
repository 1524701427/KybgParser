# 架构与兼容迁移说明

本次重构针对 `c277c982e14eacc9699fe44ca25fb55108ce0019`，目标是在保持现有
业务行为的前提下，让应用编排、配置、领域规则、表格操作和输出展示各自有明确位置。

## 当前职责

| 目录或模块 | 职责 |
| --- | --- |
| `word_parser/application/api.py` | 对外函数和原有二次抽取文件调用 |
| `word_parser/application/factory.py` | 按现有方式装配组件 |
| `word_parser/application/pipeline.py` | 保留现有主解析阶段和顺序 |
| `word_parser/application/context.py` | 单次解析过程中的数据 |
| `word_parser/application/service.py` | `ParserService` |
| `word_parser/config/loader.py` | 原有 YAML/JSON 配置加载 |
| `word_parser/config/output_schema.py` | 配置生成的字段、章节和 schema 索引 |
| `word_parser/config/result_schema.py` | 输出配置解释与原有 fallback 定义 |
| `word_parser/config/result_defaults.py` | 原有类常量、默认表结构和字段优先集合 |
| `word_parser/domains/` | 按专业归类的原有业务规则 |
| `word_parser/extraction/deterministic_rules.py` | 配置化标量抽取、覆盖顺序和质量过滤 |
| `word_parser/extraction/document_support.py` | 共享文档查询、表格读取、数值与证据方法 |
| `word_parser/extraction/table_values/` | 二次表内抽取及其结果、文件适配 |
| `word_parser/output/result_builder.py` | 初始化共享状态，保留原有 `build()` 调用序列 |
| `word_parser/output/presentation.py` | 字段展示、章节、表格结构和审计 trace 组装 |
| `word_parser/output/json_exporter.py` | 业务 JSON、details JSON 与文件写出 |

`document/`、`extraction/engine.py`、`extraction/ocr.py` 等公共接口仍转发到原有
文档加载器、通用抽取和模型实现。这些底层能力没有在本次重构中重新实现。

## 领域规则位置

| 模块 | 业务范围 |
| --- | --- |
| `project_overview.py` | 项目名称、投资方、地址、封面、设计单位、场址地质 |
| `wind_resource.py` | 测风塔、风向、风能方向、风速、密度、湍流、切变 |
| `generation.py` | 发电量汇总、等效小时、尾流、机型安全等级 |
| `electrical.py` | 电气一次、二次、主变、接入站、集电线路、通讯电源 |
| `civil.py` | 风机基础、道路、土方、永久与临时占地 |
| `investment.py` | 概算、设备和安装费用、编制依据、价格水平 |
| `finance.py` | 融资、税费、电价、收益率、限电与财务参数 |
| `environment.py` | 环保、水保及其投资 |

这些类是内部 mixin，依赖同一个 `ResultBuilder` 实例的配置、normalizer、原表解析器、
OCR 缓存及共享辅助方法。它们应通过 `ResultBuilder` 使用，不应单独实例化。
不使用多个独立实例，是为了保留原有 `self` 方法分派、缓存和字段覆盖语义。

领域规则仍在原有 `build()` 阶段执行。`_apply_deterministic_overrides()` 的调用
顺序与原实现相同，各专业间的跨方法调用也保留。这是职责归位的迁移阶段，尚未
把领域规则改造成独立候选生产器，也没有引入新的 `TableStore` 或 `ParseResult` 协议。

## 二次表内抽取

| 模块 | 职责 |
| --- | --- |
| `resolver.py` | 配置创建、规则分派，保留原有规则执行顺序 |
| `context.py` | result 章节、表格、字段索引与增强结果写入 |
| `models.py` | `NormalizedTable` |
| `expansion.py` | 模板规则、设备条目、塔号发现与规则展开 |
| `locator.py` | DataFrame 缓存、来源表、目标行列与结构兜底定位 |
| `cells.py` | 单元格、整列、多列、比率、最大值及字段求和 |
| `projection.py` | 表格投影、筛选投影和复制表 |
| `selectors.py` | 表格标准化与基础行列选择 |
| `primitives.py` | 文本匹配、值解析、单位转换、JSON 标量处理 |
| `results.py` | 字段与表格命中、NIL 和来源 trace 构造 |
| `presentation.py` | 最终结果合并、简化结果和二次抽取 details |
| `files.py` | 原有 result/details JSON 读写适配 |
| `constants.py` | 原有 NIL 状态常量 |

原有 `parser_engine.tables.table_values` 的函数导入继续可用；历史路径
`parser_engine.tables.table_values.resolver.TableValueResolver` 也仍可用。
它们指向新实现，不会创建第二套规则引擎或第二份缓存。

## 修改入口

| 修改内容 | 首选位置 |
| --- | --- |
| 普通字段的别名、正则和校验约束 | 原有 `configs/fields/*.yaml` |
| 输出章节、字段和原表展示 | 原有 `configs/output_schema.yaml` |
| 二次表格取值规则 | 原有 `configs/table_field_extractors.yaml` |
| 确定性正文配置规则 | 原有 `configs/deterministic_rules.yaml` |
| 某个专业的特殊抽取算法 | `word_parser/domains/` 对应模块 |
| 多专业字段的覆盖顺序 | `word_parser/extraction/deterministic_rules.py` |
| 新增通用表格操作 | `word_parser/extraction/table_values/` |
| JSON 结构和审计展示 | `word_parser/output/` |
| Pipeline 编排和组件装配 | `word_parser/application/` |

避免往兼容转发模块添加新的业务逻辑。新增专业规则应尽量复用已抽出的共用方法；
某个规则只能用于单一专业时，留在对应领域模块。

## 兼容范围

原有 `word_parser.core`、`main.py` 和 `parser_engine` 函数入口继续使用。
迁移的配置加载器、服务、流水线、构建器和导出器在旧、新路径下是同一个对象。
包级导入改为按需解析，以避免从兼容路径进入应用装配时形成循环依赖。

以下行为刻意保留，未作为重构顺带修复：

- YAML 配置的文件名、格式、内容和默认值。
- 校验器的现有装配与执行行为。
- 主解析和二次抽取之间的文件读取、写回流程。
- 二次抽取后返回值中 `result`、`fields` 的现有行为。
- 输出目录和按输入文件名生成输出路径的方式。
- 模型路径、启用状态、加载与释放策略。
- 原表选择、字段覆盖、单位换算、NIL 与证据 trace 规则。

## 验证

在 Python 3.12 环境对重构前后分别执行原有 295 项测试，全部通过。
从相同测试和相同 `PYTHONHASHSEED=0` 下记录的 217 次 `ResultBuilder.build()`、
`TableValueResolver.enhance_result()` 返回结果逐项对比，字段值、表格、证据、
调试信息和状态无差异。临时记录固定了测试目录，避免路径差异干扰比较。

另外检查了 528 个有效 `ResultBuilder` 方法以及 110 个二次抽取函数/方法的
语法树，函数体、签名和装饰器保持一致。原构建器有同名方法的重复定义；迁移时
将它们留在同一模块，保留 Python 原先最后一个定义生效的行为。

新增 `tests/test_architecture_compatibility.py`，覆盖旧、新导入对象身份，以及
领域、配置和表格模块在独立进程中首先导入时不会出现循环依赖。最终完整回归为 313 项全部通过。

```bash
python -m pytest -q
```

这些验证覆盖现有自动化测试和合成场景。本仓库未附带完整样例报告，也未在当前
环境加载 Aspose 或大模型，因此不能据此声称真实报告、DLL 或模型端到端行为已验证。
