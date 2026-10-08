# WordParser

WordParser 是一个面向风电可研报告 Word 文档的结构化解析引擎。它负责加载 `.doc/.docx`，识别章节和表格，召回候选证据，抽取配置字段，校验结果，并输出业务 JSON 和人工核对用的 details JSON。

当前设计约束：

- 不使用生成式 LLM。
- 主入口是 Python API：`word_parser.core`；旧 `parser_engine.*` 入口保留兼容，不再作为新代码首选入口。
- 规则、BGE、UIE、Reranker、NLI 都通过 `configs/pipeline.yaml` 控制。
- Word 解析优先使用 Aspose，缺失时 `.docx` 可退回轻量解析器。

## 项目结构

主实现按职责放在 `word_parser/`，旧入口继续兼容：

```text
word_parser/
  application/              # API、服务、装配工厂、主流水线和单次解析上下文
  core/                     # 原有公共入口的兼容转发
  config/                   # 配置加载、输出 schema 和已有默认配置
  document/                 # 文档加载、模型和章节识别公共接口
  domains/                  # 风资源、发电量、电气、土建、投资、财务等规则
  extraction/
    engine.py               # 通用抽取组件公共接口
    deterministic_rules.py  # 配置化标量抽取和原有覆盖顺序
    document_support.py     # 原文、表格、数值和证据共用方法
    table_values/           # 表内二次抽取、定位、操作、结果合并和文件适配
  output/                   # 结果组装入口、展示结构和 JSON 导出
parser_engine/              # 保留旧导入路径，以及尚未迁移的 loader/ML/通用抽取实现
configs/                    # 现有 YAML 配置，结构和内容保持不变
```

现有业务调用方式不变：

```python
from word_parser.core import parse_document_with_table_values
```

新代码也可直接使用 `word_parser.application.api`。两个入口调用同一份实现。
`parser_engine.*` 中已经迁移的模块只做兼容转发；文档 loader、ML 和部分通用
抽取组件仍保留原实现，避免本次职责拆分扩大到模型和底层文档行为。

本次重构保留原有规则、默认值、覆盖优先级、执行阶段、文件路径及返回格式。
领域规则通过 mixin 共享原 `ResultBuilder` 的状态，作为兼容迁移阶段；这还不是
互相独立的领域服务。主解析与二次抽取仍保留原有文件交互流程。
详细职责、修改位置和验证记录见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 目录

- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [安装](#安装)
- [模型下载](#模型下载)
- [配置](#配置)
- [运行解析](#运行解析)
- [部署建议](#部署建议)
- [OCR 调试](#ocr-调试)
- [BGE/UIE 调试](#bgeuie-调试)
- [输出文件](#输出文件)
- [新增抽取规则](#新增抽取规则)
- [测试](#测试)
- [常见问题](#常见问题)

## 环境要求

推荐环境：

- Windows 10/11
- Python 3.10
- Anaconda 或 Miniconda
- 8GB 以上内存，启用 BGE/UIE/Reranker/NLI 时建议 16GB 以上
- 网络仅用于首次安装依赖和下载模型，运行时可离线

本项目当前在如下环境中验证较多：

```text
Python 3.10
paddlepaddle 2.6.2
paddleocr 2.10.0
numpy 1.26.4
torch CPU wheel
```

## 安装

### 1. 创建环境

```powershell
conda create -n python310 python=3.10 -y
conda activate python310
python -m pip install --upgrade pip
```

### 2. 安装基础依赖

```powershell
cd C:\Users\EDY\Desktop\WordParser
python -m pip install -r requirements.txt
```

基础依赖包含：配置、日志、表格处理、Aspose DLL 加载、传统机器学习和部分 ML 运行依赖。

### 3. 安装 PyTorch CPU 版本

如果只使用 CPU，建议显式安装 CPU wheel，避免 CUDA DLL 问题：

```powershell
python -m pip install --no-cache-dir --force-reinstall torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cpu
```

如果环境里有 `docling-ibm-models` 等依赖，它通常要求 `torch>=2.2.2`，不建议长期停在 `torch==2.1.2`。

### 4. 安装 UIE / Paddle 依赖

UIE 依赖 PaddlePaddle 和 PaddleNLP。建议分步安装，避免 pip 解析出不兼容依赖：

```powershell
python -m pip install -r requirements-uie.txt
python -m pip install paddlenlp==2.6.1 --no-deps
```

如需 PaddleOCR 封面图片识别：

```powershell
python -m pip install paddleocr==2.10.0
python -m pip install "numpy<2"
```

`numpy<2` 是为了避免部分二进制扩展在 NumPy 2.x 下出现 `_ARRAY_API not found` 或 ABI 警告。

### 5. 验证关键依赖

```powershell
python -c "import torch; print(torch.__version__)"
python -c "from paddleocr import PaddleOCR; print('paddleocr ok')"
python -c "from sentence_transformers import SentenceTransformer; print('sentence-transformers ok')"
python -c "from paddlenlp import Taskflow; print('paddlenlp ok')"
```

## 模型下载

项目默认使用本地模型目录：

```text
models/
  bge/bge-base-zh-v1.5/
  reranker/bge-reranker-base/
  nli/erlangshen-roberta-110m-nli/
```

`configs/pipeline.yaml` 里的路径需要和本地目录一致。

### 方式一：使用 huggingface-cli

先安装下载工具：

```powershell
python -m pip install -U huggingface_hub
```

下载 BGE：

```powershell
huggingface-cli download BAAI/bge-base-zh-v1.5 --local-dir models/bge/bge-base-zh-v1.5
```

下载 Reranker：

```powershell
huggingface-cli download BAAI/bge-reranker-base --local-dir models/reranker/bge-reranker-base
```

下载 NLI：

```powershell
huggingface-cli download IDEA-CCNL/Erlangshen-Roberta-110M-NLI --local-dir models/nli/erlangshen-roberta-110m-nli
```

如果网络访问 HuggingFace 不稳定，可以设置镜像：

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
huggingface-cli download BAAI/bge-base-zh-v1.5 --local-dir models/bge/bge-base-zh-v1.5
```

### 方式二：使用 ModelScope

```powershell
python -m pip install modelscope
```

示例：

```powershell
modelscope download --model BAAI/bge-base-zh-v1.5 --local_dir models/bge/bge-base-zh-v1.5
modelscope download --model BAAI/bge-reranker-base --local_dir models/reranker/bge-reranker-base
```

NLI 模型如 ModelScope 无对应条目，建议用 HuggingFace 或手工下载。

### Reranker ONNX 模型

当前配置使用 ONNX Reranker：

```yaml
semantic_verifier:
  reranker_backend: onnx
  reranker_model_name: C:\Users\EDY\Desktop\WordParser\models\reranker\bge-reranker-base
```

代码会寻找：

```text
models/reranker/bge-reranker-base/onnx/model.onnx
```

如果下载的 reranker 目录没有 `onnx/model.onnx`，有两个选择：

1. 改用 `cross_encoder` 后端：

```yaml
semantic_verifier:
  reranker_backend: cross_encoder
```

2. 自行导出 ONNX，并放到：

```text
models/reranker/bge-reranker-base/onnx/model.onnx
```

## Aspose 配置

项目默认从 `runtime/` 读取以下本地文件：

```text
runtime/Aspose.Words.dll
runtime/Aspose.Total.NET.lic
runtime/SkiaSharp.dll
```

也可以用环境变量覆盖：

```powershell
$env:ASPOSE_WORDS_DLL_DIR="C:\Users\EDY\Desktop\WordParser\runtime"
$env:ASPOSE_WORDS_LICENSE_PATH="C:\Users\EDY\Desktop\WordParser\runtime\Aspose.Total.NET.lic"
```

说明：

- `.doc` 文件建议使用 Aspose。
- `.docx` 文件在 Aspose 不可用时可以退回 `SimpleDocxLoader`，但复杂文本框、浮动图片、合并单元格支持会弱一些。

## 配置

主配置文件：

```text
configs/pipeline.yaml
configs/output_schema.yaml
configs/fields/*.yaml
configs/sections.yaml
```

关键模块：

```yaml
bge_matcher:
  enabled: true
  mode: active
  model_name: C:\Users\EDY\Desktop\WordParser\models\bge\bge-base-zh-v1.5

uie_extractor:
  enabled: true
  mode: active
  model_name: uie-base

semantic_verifier:
  enabled: true
  mode: active
  reranker_enabled: true
  reranker_backend: onnx
  nli_enabled: true
```

建议准备两套配置：

- 快速调试：关闭 BGE/UIE/Reranker/NLI，只看规则和表格抽取。
- 准确率模式：打开 BGE/UIE/Reranker/NLI。

`configs/output_schema.yaml` 控制最终输出结构，包括章节顺序、每个章节展示哪些字段/表格、原表抽取规则、组合表映射和资源章节表格 key。资源章节原表通常配置在 `original_table_groups` 和 `resource_table_key_patterns` 下，例如 `windResourceDirectionEnergyFrequency` 对应《测风塔风向风能频率统计成果表》。

`configs/deterministic_rules.yaml` 控制配置化的确定性业务规则。它适合放跨句、正文兜底、组合判断类规则，例如：

- 资源章节的本期测风塔优先判断、空气密度、风速、风功率密度、湍流、风切变。
- 电气一次的主变容量、主接线形式、SVG 无功补偿容量、接入站脏值过滤。
- 风机基础的桩数、桩径、桩长、承台直径、基础埋深、台柱直径。
- 财务的材料费、流动资金单位千瓦指标、人员工资。

快速调试可参考：

```yaml
bge_matcher:
  enabled: false

uie_extractor:
  enabled: false

semantic_verifier:
  enabled: false
```

## 运行解析

### Python API

完整解析，包含二次表内抽取：

```python
from word_parser.core import parse_document_with_table_values

result = parse_document_with_table_values(r"C:\Users\EDY\Desktop\WordParser\samples\reports\sample.docx")
print(result.get("outputFiles", {}))
```

只跑主解析：

```python
from word_parser.core import parse_document

result = parse_document(r"C:\Users\EDY\Desktop\WordParser\samples\reports\sample.docx")
```

### 命令行示例

`main.py` 目前只是本地示例入口。可以直接运行：

```powershell
python main.py
```

如果需要正式命令行入口，建议后续把 `main.py` 改成 argparse，例如：

```powershell
python main.py --input report.docx --output data/predictions
```

## 部署建议

### 单机部署

推荐目录结构：

```text
WordParser/
  word_parser/
  configs/
  models/
  runtime/
  samples/
  tools/
  data/predictions/
  main.py
```

部署步骤：

1. 拷贝代码和配置。
2. 拷贝本地模型到 `models/`。
3. 拷贝 Aspose DLL/license。
4. 创建 Python 3.10 环境。
5. 安装依赖。
6. 运行一次 `python -m pytest tests/test_pipeline.py -q` 验证基础功能。
7. 使用 `parse_document()` 或服务封装调用。

### 服务化部署

如需要做 HTTP 服务，建议新增 FastAPI 包装层，不要把服务逻辑塞进解析实现层：

```python
from fastapi import FastAPI
from word_parser.core import create_parser

app = FastAPI()
parser = create_parser()

@app.post("/parse")
def parse(file_path: str):
    return parser.parse(file_path)
```

服务化时建议：

- `release_after_match: false`，避免每个请求重复加载 BGE。
- `release_after_extract: false`，避免每个请求重复加载 UIE。
- `release_after_verify: false`，避免每个请求重复加载 Reranker/NLI。
- 单机内存不足时再改回 `true`。

## OCR 调试

封面 OCR 使用 `CoverOcrExtractor`，主要用于从目录前正文图片中提取：

- 项目名称
- 设计单位
- 设计单位资质等级

### 保存 OCR 扫描到的图片

设置环境变量：

```powershell
$env:COVER_OCR_DEBUG_DIR="C:\Users\EDY\Desktop\WordParser\data\debug-images"
```

如果不是命令行运行，可以在 Python 入口最前面设置：

```python
import os
os.environ["COVER_OCR_DEBUG_DIR"] = r"C:\Users\EDY\Desktop\WordParser\data\debug-images"
```

可选参数：

```powershell
$env:COVER_OCR_MAX_IMAGES="32"
$env:COVER_OCR_MIN_IMAGE_BYTES="4096"
```

说明：

- `COVER_OCR_MAX_IMAGES` 控制最多 OCR 几张目录前正文图片。
- `COVER_OCR_MIN_IMAGE_BYTES` 过滤太小的图标或碎片图。
- 当前 OCR 只扫描正文 `word/document.xml` 中目录前图片，不扫描页眉页脚。
- 支持 `a:blip` 和 `v:imagedata` 两类 Word 图片表示。

### 手动测试单张证书图

```powershell
python tools\ocr_cert_test.py .\1.png
```

这个脚本会打印：

- PaddleOCR 原始输出
- OCR 文本行
- 项目规则提取结果
- `designUnit`
- `designUnitQualification`

## BGE/UIE 调试

### BGE 用途

BGE 只做候选语义匹配，不直接抽值。它解决的问题是：候选文本和字段语义是否相关。

重点配置：

```yaml
bge_matcher:
  threshold: 0.72
  max_text_length: 128
  batch_size: 4
  top_k_per_field: 50
  min_match_score: 0.0
```

调参建议：

- 误判多：提高 `threshold` 到 `0.75 ~ 0.80`。
- 漏候选：提高 `top_k_per_field`，或降低 `min_match_score`。
- 长句语义不完整：提高 `max_text_length` 到 `256`。
- 内存不足：降低 `batch_size`，保持 `memory_aware: true`。

### UIE 用途

UIE 从候选文本中补充抽取字段值，不负责全文扫描。

重点配置：

```yaml
uie_extractor:
  threshold: 0.75
  max_text_length: 256
  batch_size: 2
  top_k_per_field: 3
  min_match_score: 1.0
```

调参建议：

- 漏抽：降低 `threshold` 到 `0.65 ~ 0.70`。
- 截断：提高 `max_text_length` 到 `512`。
- 候选太少：提高 `top_k_per_field` 到 `5`。
- 速度慢：降低 `top_k_per_field` 或关闭 UIE。

### 判断问题在哪一步

优先看 `data/predictions/*_details.json`：

- 字段值不对：先看 `fieldIndex.<fieldCode>.rule`，确认命中的配置文件、规则名、正则和 `matchedText`。
- 来源段落不对：看 `articleLocation.sectionPath` 和 `source.text`，确认是否落在字段允许的章节或强上下文兜底范围内。
- 原表没出来：看 `tableIndex` 是否有目标表 key；没有则检查 `configs/output_schema.yaml` 的 `original_table_groups`、`optional_tables` 和表题正则。
- 原表出来但字段没算出：说明原表透传已命中，字段 resolver 还需要适配该表的行列结构。

## 输出文件

默认输出目录：

```text
data/predictions/
```

解析输出两类文件；执行二次抽取后会把二次结果合并回最终结果：

```text
*_result.json
*_details.json
```

### result JSON

给业务系统使用，只包含最终结构化结果：

```json
{
  "filePath": "sample.docx",
  "sections": [
    {
      "name": "通用",
      "fields": [
        {"fieldCode": "projectName", "name": "项目名称", "value": "...", "unit": null}
      ],
      "tables": []
    }
  ]
}
```

二次抽取成功的字段会按同样的 `fieldCode/name/value/unit` 结构合入对应章节的 `fields`。涉及原表保留的二次结果会合入对应章节的 `tables`，并用 `tableRef` 指向已有原表。二次抽取的 NIL、行列命中、来源表、trace 和完整表数据都写入 `*_details.json` 的 `tableValueExtraction`。

### details JSON

给人工核对和调试使用，包含：

- summary
- sections
- fieldIndex
- tableIndex

字段详情重点看：

- `rule`：命中的配置规则、正则、resolver 或 builder 来源。
- `articleLocation`：原文定位，包括 `sectionPath`、`blockId`、`tableId`、`caption` 等。
- `sourceText`：章节视图中的简短原文证据；完整索引用 `fieldIndex`。

原表详情重点看：

- `key`：稳定表格编码，例如 `windResourceDirectionEnergyFrequency`。
- `source.caption`：原文表题。
- `source.rule.ruleSource`：原表命中的配置文件，通常是 `configs/output_schema.yaml`。
- `articleLocation.sectionPath`：原表所在原文章节。

排查字段问题时优先看 `fieldIndex`。

## 新增抽取规则

新增规则前先判断属于哪一类：

| 场景 | 改哪个配置 |
|---|---|
| 新增一个普通字段，从正文或表格候选中抽值 | `configs/fields/*.yaml` |
| 控制最终 JSON 哪个章节展示哪些字段/表 | `configs/output_schema.yaml` |
| 原文里有一整张表，要透传到最终 JSON | `configs/output_schema.yaml` 的 `original_table_groups` / `resource_table_key_patterns` |
| 已经抽到表，还要从表里二次取单元格或派生表 | `configs/table_field_extractors.yaml` |
| 正文里跨句、多字段、要优先级/过滤/兜底的业务规则 | `configs/deterministic_rules.yaml` |

### 新增一次抽取字段

一次抽取优先放在 `configs/fields/*.yaml`。适合“字段名附近有值”的情况。

示例：

```yaml
fields:
  exampleWindSpeed:
    name: 示例平均风速
    value_type: number
    standard_unit: m/s
    sections:
      include: [资源章节, 风能资源]
      exclude: [财务, 投资]
    aliases: [平均风速, 年平均风速]
    unit_aliases: [m/s, 米/秒]
    patterns:
      - '年?平均风速(?:为)?\s*([0-9]+(?:\.[0-9]+)?)\s*(m/s|米/秒)'
    validators:
      min: 0
      max: 50
```

加完字段后，如果要出现在最终 JSON，还要把字段 code 加到 `configs/output_schema.yaml` 对应章节的 `sections[].fields`，并在 `fields:` 下配置中文名和单位。

### 新增确定性正文规则

如果字段不是简单“字段名: 值”，而是需要正文兜底、跨句判断、取最后一个值、过滤脏值，就放到 `configs/deterministic_rules.yaml`。

示例：

```yaml
finance:
  sections: ['财务']
  fallback_keywords: ['材料费', '流动资金', '工资']
  fields:
    materialCostPerKw:
      name: 材料费（元/KW）
      unit: 元/KW
      value_type: number
      evidence_keywords: ['材料费']
      patterns:
        - '材料费(?:定额)?取\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*元\s*/\s*kW'
```

常用配置项：

| 配置项 | 说明 |
|---|---|
| `sections` | 优先扫描哪些章节 |
| `fallback_keywords` | 章节识别不到时，用哪些关键词筛正文块 |
| `patterns` | 正则，推荐用 `(?P<value>...)` 标出值 |
| `value_type` | `number` 或 `text` |
| `select` | `last` 表示同一段里取最后一个命中值 |
| `require_keywords` | 文本必须包含这些词才允许命中 |
| `reject_keywords` | 文本包含这些词就拒绝 |
| `validators.min/max` | 数值范围保护 |
| `evidence_keywords` | details 里定位证据时优先找这些词 |

### 新增原表透传

如果需求要保留原文表，先在 `configs/output_schema.yaml` 对应章节加入 `optional_tables` 或 `optional_table_prefixes`，再在 `original_table_groups` 里加表题规则。

示例：

```yaml
original_table_groups:
  - key_prefix: resourceOriginalTable
    title_only: true
    key_patterns:
      - key: windResourceDirectionEnergyFrequency
        patterns:
          - '测风塔.*风向风能频率统计成果表'
          - '风向.*风能.*频率统计'
```

如果表名编号经常变化，不要把 `表2.6-16` 写死，优先写内容关键词。

### 新增二次抽取规则

二次抽取改 `configs/table_field_extractors.yaml`。它只处理已经进入 `result.json` 的表，不重新读 Word。

新增一个“最终固定输出的表格字段”只需要维护配置和测试，不需要再同步修改 `ResultBuilder`：

1. 在 `configs/table_field_extractors.yaml` 声明如何定位表、行、列和值。
2. 在 `configs/output_schema.yaml` 的 `sections[].fields` 注册字段所属章节。
3. 在同一文件的 `fields:` 配置字段中文名和标准单位。
4. 在 `tests/test_table_values.py` 增加正常命中、易混淆行和缺列场景测试。
5. 更新 `FINAL_EXTRACTION_INVENTORY.md`，供业务确认最终字段清单。

`configs/output_schema.yaml` 是最终字段结构的唯一数据源。未命中时仍需输出空字段，就必须在这里注册；只想命中时追加，则只配置二次抽取规则。

示例：从某张表里按行列取一个字段：

```yaml
rules:
  - field_code: exampleField
    field_name: 示例字段
    section: 财务
    source_table:
      key: financialIndicatorSummary
      name_patterns: ['财务指标汇总表']
      required_columns: ['项目', '数值']
    row:
      type: label
      column: 项目
      patterns: ['资本金财务内部收益率']
    column:
      aliases: ['数值', '指标']
    value_type: number
    unit: '%'
```

表格字段通用模板：

```yaml
- field_code: exampleEquipmentPrice
  field_name: 示例设备单价
  section: 技经概算
  source_table:
    key: investmentEquipmentInstallation
    name_patterns: ['设备及安装工程概算表', '第二部分\s*设备及安装工程']
    name_match_content: true
    required_columns:
      - {aliases: ['项目名称及规格', '项目名称', '名称']}
      - {aliases: ['单位']}
      - {aliases: ['数量']}
  row:
    type: label
    column: ['项目名称及规格', '项目名称', '名称']
    aliases: ['示例设备', '设备别名']
    all_aliases: ['必须词A', '必须词B']
    exclude_aliases: ['排除词']
  column:
    aliases: ['设备费', '设备购置费', '设备购置费（万元）']
  value_type: number
  unit: 万元
```

常用规则：

| 配置 | 用途 |
|---|---|
| `aliases` | 任一别名命中即可。 |
| `all_aliases` | 所有关键词必须同时出现，例如“主变压器 + 中性点设备”。 |
| `exclude_aliases` | 出现任一排除词就拒绝，例如普通风机排除“塔筒”。 |
| `exact: true` | 归一化后精确匹配列名或行标签。 |
| `occurrence` | 同名行或列按从 0 开始的出现顺序选择。 |
| `merge_following_rows.max_rows` | 合并设备规格的后续空名称行。 |
| `value_pattern` / `value_patterns` | 从长文本中截取目标值。 |
| `value_groups` + `value_join` | 组合多个正则捕获组，例如把 `800` 和 `315` 组成 `800/315`。 |
| `conversion` | 单位换算，例如 `wan_kwh_to_mwh`。 |
| `dedupe: false` | 整列抽取时保留重复值，维持逐行对应关系。 |

常用操作：

| operation | 适用场景 |
|---|---|
| `cell`（默认） | 按目标行和目标列抽取一个值。 |
| `cell_items` | 复用同一张表和目标列，按设备别名目录批量生成多个字段。 |
| `column_values` | 抽取整列为列表。 |
| `table_projection` | 从原表投影指定列。 |
| `filter_table_projection` | 按设备别名分类并投影多行。 |
| `copy_table` | 原样复制已经进入结果的表。 |
| `sum_fields` | 对已有字段求和。 |

示例：二次结果涉及原表保留时，用派生表引用原表：

```yaml
rules:
  - key: generationCorrectionFactors
    name: 折减修正系数表
    section: 发电量章节
    operation: copy_table
    source_table:
      name_patterns: ['折减修正系数表']
      required_columns: ['项目', '取值']
```

二次抽取成功后会合并到最终 `*_result.json`；完整命中过程、NIL 原因、行列定位保留在 `*_details.json` 的 `tableValueExtraction`。

### 修改后的验证

每次新增规则后建议至少跑：

```powershell
python -m pytest -q tests/test_pipeline.py
python main.py
```

如果改了二次抽取，再加跑：

```powershell
python -m pytest -q tests/test_table_values.py
```

## 测试

运行全部测试：

```powershell
python -m pytest -q
```

只跑主回归：

```powershell
python -m pytest tests/test_pipeline.py -q
```

语法检查：

```powershell
python -m compileall word_parser parser_engine main.py
```

## 常见问题

### 1. PaddleOCR 导入时报 `shm.dll` 或 WinError 127

通常是 `torch / torchvision / torchaudio` 混装或 DLL 依赖损坏。建议统一重装 CPU 版本：

```powershell
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install --no-cache-dir torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cpu
```

### 2. 出现 NumPy 2.x ABI 警告

降级到 NumPy 1.x：

```powershell
python -m pip install --force-reinstall "numpy<2"
```

### 3. Reranker 报 ONNX 输入类型错误

当前代码会把 tokenizer 的整型输入转成 `int64`。如果仍然报错，检查 ONNX 模型输入签名和 tokenizer 输出字段是否匹配。

### 4. OCR 没识别到证书图

开启图片调试：

```powershell
$env:COVER_OCR_DEBUG_DIR="C:\Users\EDY\Desktop\WordParser\data\debug-images"
$env:COVER_OCR_MAX_IMAGES="64"
```

重新解析后检查 `data/debug-images`。如果证书图仍不存在，说明它可能不在正文目录前，或者 Word 将其放在页眉/页脚/特殊对象中。

### 5. `.doc` 解析失败

`.doc` 推荐安装并配置 Aspose。轻量 loader 只支持 `.docx`。
