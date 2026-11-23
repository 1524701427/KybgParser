# WordParser

WordParser 将风电可行性研究报告（`.doc`、`.docx`、`.pdf`）解析为结构化 JSON。项目采用配置和确定性规则，不依赖生成式大模型。输入文件可以放在任意目录；默认输出到 `data/predictions/`。

## 先用起来

在项目根目录运行，建议使用 Python 3.10。把示例中的报告路径替换为实际文件：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py "samples/reports/你的报告.docx"
```

也可以使用已有的 Conda 环境。直接运行 `python main.py` 会提示输入报告路径，也可在命令后传入实际存在的报告路径；`python main.py --help` 可查看选项。默认运行**完整流程**；仅需一次抽取时加 `--primary-only`。在项目根目录运行，因为默认配置目录为 `configs/`、输出目录为 `data/predictions/`。使用其他配置目录时加 `--config-root 路径`。

```python
from word_parser.core import parse_document_with_table_values, parse_document

full = parse_document_with_table_values("report.pdf")  # 完整流程
primary = parse_document("report.docx")                # 仅一次解析
print(full["outputFiles"])
```

命令行结束后会打印输出文件路径和二次抽取摘要。正式对接通常读取 `*_mapped.json`；排查错误先看 `*_details.json`。

## 架构与执行顺序

```text
报告 Word/PDF
  → document：读取、统一文档结构、识别章节和原表
  → discovery：前置指标扫描，建立带原文位置的候选指标索引
  → primary：一次抽取，按字段配置召回、匹配、取值、归一化、选值
  → output：构建一次结果并保留原表
  → secondary：基于一次结果中的表格执行二次取值
  → mapping：同步二次结果、组合最终字段、检查一致性
  → result / details / mapped 三种 JSON
```

完整入口在 `word_parser/application/workflow.py`。它调用 `ParserPipeline.parse(..., defer_mapping=True)`，二次抽取完成后才生成最终映射。一次抽取入口 `parse_document()` 保持原有行为：一次解析后直接映射并输出三种 JSON。前置扫描从段落中的多组名称和值、并列表格和横向表头记录数值或短文本、单位、行列及原文位置。名称变体在单位和章节相容时向一次抽取提供定位提示；唯一精确命中的数值即使字段已有其他候选，也会进入一次抽取候选池。名称包含关系和模糊匹配仍须满足字段唯一、单位及口径等约束才能参与最终选值。一次抽取默认不按每字段 Top-K 丢弃候选，最终值由字段规则、上下文约束和冲突消解决定。多实体表格的列值保留行身份，不自动写入单值字段。二次抽取按现有优先级处理原表。

`details.json` 中的 `discoveredIndicators` 是前置扫描的原文观测，`extractionCandidates` 是一次抽取产生的全部字段候选，均不等于最终映射。候选包含取值、方法、位置、规则分和上下文拒绝原因。排查缺值时先查预抽取有没有原文观测，再查一次抽取有没有字段候选，最后查看 `fieldIndex` 的选值证据和映射规则。扫描依赖解析器得到的文本和表格；图片、扫描页或解析失败的内容仍可能漏掉。

| 目录 | 职责 | 常看文件 |
| --- | --- | --- |
| `word_parser/application/` | 对外 API、完整流程、一次流水线、组件装配、HTTP 服务 | `api.py`、`workflow.py`、`pipeline.py`、`http_api.py` |
| `word_parser/document/word/`、`pdf/` | Word/PDF 加载 | `aspose_loader.py`、`pdf_loader.py` |
| `word_parser/document/ast/`、`tables/` | 统一文档结构及原始表格 | 文档类型、原表解析 |
| `word_parser/document/` | 章节、版面、封面 OCR | `section_detector.py`、`cover_ocr.py` |
| `word_parser/discovery/` | 前置指标发现 | `stage.py`、`indicators.py` |
| `word_parser/primary/` | 一次抽取及候选消解 | `stage.py`、`value_extractor.py` |
| `word_parser/secondary/table_values/` | 二次表格取值原语 | `resolver.py`、`results.py` |
| `word_parser/mapping/` | 最终映射、二次同步、一致性检查 | `projector.py`、`validation.py` |
| `word_parser/domains/` | 风资源、电气、土建、财务等专业规则 | 各领域文件 |
| `word_parser/output/` | 结果构建、共用规则辅助方法与三种 JSON 导出 | `result_builder.py`、`builder_support/`、`json_exporter.py` |
| `word_parser/extraction/` | 兼容旧版公共导入路径，新规则不再放这里 | `__init__.py` |
| `word_parser/config/`、`configs/` | 读取配置与存放规则 | `loader.py`、各 YAML |
| `tests/` | 单元与轻量流程回归 | `test_pipeline.py`、`test_table_values.py` |
| `tools/` | 手工脚本、离线评估和训练辅助；不参与线上解析流程 | `scripts/`、`evaluation/`、`training/` |
| `samples/`、`data/`、`runtime/` | 样例、输出、商业运行时 | 见下文 |

`word_parser.core` 是稳定的 Python 导入入口，实现位于单文件 `word_parser/core.py`。`word_parser/config/` 是读取配置的 Python 代码，根目录 `configs/` 是实际 YAML 规则。旧的 `word_parser.http_api:app` 仍转发至服务实现。模块拆分只标明职责；专业规则的调用顺序、覆盖顺序和 NIL 行为仍以现有代码与配置为准。

## 输出与排查

| 文件 | 用途 |
| --- | --- |
| `<报告名>_result.json` | 按章节组织的业务字段和表格 |
| `<报告名>_details.json` | `fieldIndex`、`tableIndex`、来源、规则、候选和二次抽取过程 |
| `<报告名>_mapped.json` | 按 `configs/output_schema.yaml` 输出的 `${...}` 占位符键，供回调或下游系统使用 |

未取到的标量映射通常为 `null`，必需表格保留空表结构；具体结构以输出配置和当前映射器为准。需要核对“值为什么是这个”时，先在 `details.fieldIndex.<字段编码>` 看 `rule`、`source` 和 `articleLocation`；原表没出现时看 `tableIndex`、表题和 `output_schema.yaml`；二次抽取未命中时看 `tableValueExtraction` 中的行列定位与 NIL 原因。最终字段清单另见 `FINAL_EXTRACTION_INVENTORY.md`。

`samples/reports/` 可放原始报告，`samples/parsed/` 可放人工参考文档；`data/predictions/` 是默认 JSON 输出，`data/reports/` 用于人工核对报告，`data/logs/` 和 `data/debug-images/` 可存放调试产物。解析器不要求输入文件位于这些目录。

## 配置从哪里改

| 需求 | 配置或代码 |
| --- | --- |
| 开关一次抽取模块、候选截断 | `configs/pipeline.yaml`（默认关闭 `funnel`，保留全部候选） |
| 普通字段别名、正则、单位、章节和校验 | `configs/fields/*.yaml` |
| 字段证据上下文约束 | `configs/field_constraints.yaml` |
| 章节标题别名、通用单位别名 | `configs/sections.yaml`、`configs/units.yaml` |
| 跨句或正文确定性规则 | `configs/deterministic_rules.yaml` |
| 输出章节、字段、原表和占位符映射 | `configs/output_schema.yaml` |
| 已保留表格中的二次取值 | `configs/table_field_extractors.yaml` |
| 规则无法表达的专业算法 | `word_parser/domains/` 或对应抽取模块 |

### 一次抽取字段

`configs/fields/` 按业务领域拆分，例如 `wind_resource.yaml`、`finance.yaml`、`electrical.yaml`。每个文件以 `fields:` 为根节点，字段编码为子键。建议复制相近字段并按报告证据修改：

```yaml
fields:
  exampleWindSpeed:
    name: 示例平均风速
    value_type: number
    standard_unit: m/s
    sections:
      include: [资源章节, 风能资源]
      exclude: [财务]
    aliases: [平均风速, 年平均风速]
    unit_aliases: [m/s, 米/秒]
    patterns:
      - '年?平均风速.{0,30}?([0-9]+(?:\.[0-9]+)?)\s*(m/s|米/秒)?'
    validators:
      min: 0
      max: 50
```

`aliases` 负责召回，`sections.include/exclude` 调整候选章节，`patterns` 提供字段专用正则（第一组通常取值，第二组通常取单位），`unit_aliases` 和 `standard_unit` 约束单位，`validators` 限制明显不合理的值。正则尽量限制字段名与数值间的距离，避免跨句误抽。表格定位可使用 `table_lookup`（行/列别名）、`table_aggregate`（如求和）、`table_list`（整列列表）和 `row_context`（行内要求词/排除词）；相关字段已有可复制的实际配置。字段级 `extractors.table_rule`、`extractors.regex` 与 `pipeline.yaml` 的模块开关共同决定抽取器是否参与。 `value_map` 可把原文写法归一为标准值，`source_priority`、`preferred_methods` 和证据校验项影响候选选择。

需要在固定结果中展示新字段时，还要将字段编码加入 `output_schema.yaml` 对应 `sections[].fields`，并在该文件的 `fields:` 中登记名称与单位。`field_constraints.yaml` 可为特定字段配置 `required_context_any`、`negative_context`、`detect_conflicts`；未配置的字段不受此约束。修改 `sections.yaml` 或 `units.yaml` 时沿用其 `sections.<类别>.aliases`、`units.<类别>.aliases/standard` 结构。

下游占位符名由 `output_schema.yaml` 的 `output_field_codes` 指定，例如 `projectName: project_name` 会输出 `${project_name}`。字段值来源于一次或二次抽取；少数需要重组列表或跨字段合并的映射由 `word_parser/mapping/` 中的代码完成。修改占位符时要同时核对下游接口与映射测试。

### 正文确定性规则与原表

`configs/deterministic_rules.yaml` 适合需要跨句、排除词、取最后一个值等逻辑的正文规则。按现有业务领域条目增加 `sections`、`fallback_keywords`、`fields.<编码>.patterns`、`evidence_keywords` 和 `validators`；正则可使用 `(?P<value>...)` 标明值。若需要透传原文整表，在 `output_schema.yaml` 对应章节登记 `optional_tables` 或 `optional_table_prefixes`，再在 `original_table_groups[].key_patterns` 配置表题匹配。报告间表号常变化，优先匹配表题内容、列名和必要正文，而非固定表号。

### 二次表格抽取

`configs/table_field_extractors.yaml` 的 `rules:` 声明二次抽取规则。最常用的 `operation: cell` 先用 `source_table` 找表，再用 `row`、`column` 定位单元格；还支持 `column_values`、`cell_items`、`table_projection`、`copy_table`、`sum_fields` 等操作。表题可写 `name_patterns`，列名用 `required_columns`，正文用 `required_text`；`name_match_content: true` 可在表题不贴着表格时按内容回退。行列的 `aliases` 接受不同报告写法，`exclude_aliases` 排除相近但错误的行，`value_pattern` 在长文本中截取局部值，`conversion` 做单位换算。

附表若落在其他章节，一次抽取会把带“附表/附录/附件”章节、明确附表题、`01…表` 一类编号表题，或命中字段配置表题的内容作为跨章节候选，继续执行字段原有的表格、正则、单位及上下文规则；目标章节已有通过校验的值时优先使用目标章节。普通其他章节和字段明确排除的章节仍不参与这个兜底。二次抽取会在目标章节找不到表时，按全篇唯一的表格 `key` 和原有表名、列名约束查找。明确需要全篇搜索时也可在 `source_table` 中设置 `search_all_sections: true`。原表识别允许带明确表题的附表跨章节匹配；不要只凭章节名或相似标题取值。

```yaml
rules:
  - field_code: exampleFinancialRate
    field_name: 示例收益率
    section: 财务
    source_table:
      name_patterns: ['财务指标汇总表']
      required_columns: ['项目', '数值']
    row: {type: label, column: 项目, aliases: ['资本金财务内部收益率']}
    column: {aliases: ['数值', '指标']}
    value_type: number
    unit: '%'
```

多测风塔、不同高度可使用配置中的 `towers.from_table` 和 `variables.*.from_table` 动态发现，不必把塔号和高度写死。新增固定输出字段时，依次更新二次规则、`output_schema.yaml` 的章节字段及字段元数据，再增加相关回归用例；只在命中时出现的动态字段可不注册为固定字段。修改字段清单后同步核对 `FINAL_EXTRACTION_INVENTORY.md`。

## 运行环境与部署

### 本地运行

Python 要求见 `pyproject.toml`（至少 3.10）。`requirements.txt` 安装项目常规 Python 依赖；PDF 加载需要基础镜像中的 `opendataloader_pdf` 等组件，直接在本机解析 PDF 时需另行准备对应依赖。Word 优先使用 Aspose；`.docx` 在 Aspose 不可用时可退回简化加载器，复杂表格和图片的效果可能不同；`.doc` 应准备 Aspose 运行时。默认从 `runtime/` 读取 `Aspose.Words.dll`、`Aspose.Total.NET.lic` 和 SkiaSharp 库。也可设置 `ASPOSE_WORDS_DLL_DIR`、`ASPOSE_WORDS_LICENSE_PATH` 指向外部位置。封面 OCR 可使用 RapidOCR 或 PaddleOCR；使用 `COVER_OCR_DEBUG_DIR` 保存扫描图片，`COVER_OCR_MAX_IMAGES` 和 `COVER_OCR_MIN_IMAGE_BYTES` 控制扫描范围。

运行测试：

```powershell
python -m pytest -q
python -m pytest -q tests/test_pipeline.py tests/test_table_values.py
```

多数测试使用合成文档；真实报告的准确率及 Aspose/PDF/OCR 运行时需要在目标环境另行核对。

### HTTP 服务

```powershell
python -m uvicorn word_parser.application.http_api:app --host 0.0.0.0 --port 8000
```

`POST /parse` 接收 `bizId`、`reportType`、`fileUrl`、`fileName`、`callbackUrl`，立即返回 `taskId`。后台下载报告（上限 200 MB）并解析，随后向请求指定的回调地址 POST `reportId`、`parseTaskId`、`parseStatus`、`rawData`、`errorMsg`；成功时 `rawData` 为映射 JSON 的字符串，失败时带错误信息。回调会重试。接口文档：`http://127.0.0.1:8000/docs`。仅浏览器直接访问该服务时，才需要通过 `WORD_PARSER_CORS_ORIGINS` 设置逗号分隔的允许来源。

```bash
curl -X POST http://127.0.0.1:8000/parse -H 'Content-Type: application/json' \
  -d '{"bizId":2001,"reportType":"FEASIBILITY_STUDY","fileUrl":"https://example.com/report.pdf","fileName":"风电可研报告.pdf","callbackUrl":"https://example.com/parse/callback"}'
```

### Docker 与 GitLab

`Dockerfile` 基于 `docker.wh-ge.com/document-processing-base:1.0`，该基础镜像提供 Python、.NET、Java 和 PDF/OCR 系统依赖。构建环境须能访问基础镜像；`runtime/` 须包含 Dockerfile 检查的 Aspose、SkiaSharp 和 Linux 运行时文件。镜像构建时会检查导入和 Aspose 加载，容器启动时监听 8000 端口：

```bash
docker build -t word-parser:local .
docker run --rm -p 8000:8000 word-parser:local
```

CI 配置在 `.gitlab-ci.yml`：`test` 分支构建、测试并自动部署测试环境，`main` 分支构建、测试后由人工触发生产部署。部署默认映射宿主机 9994 到容器 8000。构建及部署需要 Docker、仓库访问和 SSH 连通性。调整服务 worker 数可设置 `UVICORN_WORKERS`；现有部署默认 1。

当前部署凭据写在 `.gitlab-ci.yml` 的 `variables` 中：镜像仓库使用 `NEXUS_USERNAME`、`NEXUS_PASSWORD`；测试和生产环境分别使用 `TEST_SSH_PRIVATE_KEY_B64` / `PROD_SSH_PRIVATE_KEY_B64`，或对应的 `TEST_SSH_PASSWORD` / `PROD_SSH_PASSWORD`。SSH 私钥变量保存私钥文件内容的 Base64 编码。`FEISHU_WEBHOOK_URL` 为可选通知地址。镜像仓库、目标主机和端口也在该文件中配置，部署到其他环境时按实际地址修改。

## 新人上手路径

1. 先读本页“架构与执行顺序”，再看 `application/workflow.py` 与 `application/pipeline.py`。
2. 用一份已有报告运行 `python main.py <路径>`，打开三个输出文件。
3. 选一个字段，在 `details.fieldIndex` 查证据与规则，再到 `configs/fields/` 或 `table_field_extractors.yaml` 找对应配置。
4. 修改相近规则，增加一个命中和一个易混淆场景的回归测试，运行相关测试与完整测试。
5. 调整最终字段或表格时同步检查 `output_schema.yaml` 和 `FINAL_EXTRACTION_INVENTORY.md`。

日志消息、注释和 docstring 使用中文；配置键、Python 标识符、JSON 键与外部 API 字段保持既有英文写法，避免破坏接口兼容。
