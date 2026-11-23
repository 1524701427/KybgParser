# 四阶段架构改造落地记录

目标：**预抽取 → 一次抽取 → 二次抽取 → 最终映射**。YAML 声明字段/抽取/映射规则，Python 实现并调度方法。此改造严格保留旧业务调用顺序和 284 项输出映射关系；尚未声称所有复杂 Python 规则已配置化。

## 本次真正修改的执行路径

```text
DocumentLoader → DocumentAST
  ↓
discover_indicators()                  预抽取
  ↓
extract_primary_fields()               一次抽取：候选/选值/校验
  ↓
extract_domain_fields()                一次抽取：风资源/电气/土建/财务领域专项算子
  ↓
ResultBuilder.build_prepared()          仅组装一次抽取字段/详情/原表；不再抽新字段
  ↓
TableValueResolver.enhance_result()     二次抽取，纯内存（write_outputs=False）
  ↓
execute_final_mapping()                最终映射：先完整投影，再按 YAML 注册算子处理，校验
  ↓
写入 result/details/mapped              校验通过后才发布正式 JSON
```

## 修改的文件及意图

| 文件 | 作用 |
|---|---|
| `word_parser/primary/domain_stage.py` | 抽离 ResultBuilder 旧业务抽取调用时序，提供明确的一次领域抽取中间状态 |
| `word_parser/output/result_builder.py` | `prepare()` 抽取、`build_prepared()` 纯组装，保留 `build()` 兼容旧 API |
| `word_parser/application/pipeline.py` | 真正把 `prepare()` 放在一次抽取之后、导出之前 |
| `word_parser/output/json_exporter.py` | 接收 `prepared` 结果时不再额外执行领域抽取 |
| `word_parser/secondary/stage.py` | 新增 `write_outputs=False` 纯内存二次抽取模式；旧调用方默认仍写文件 |
| `configs/mapping_pipeline.yaml` | 声明白名单映射算子及原业务顺序 |
| `word_parser/mapping/stage.py` | 独立临时工作区运行旧映射算子、统一校验后提交正式 JSON |
| `word_parser/application/workflow.py` | 执行四阶段主入口；从同一个 `config_root` 派生二次和映射配置 |

## 重要兼容细节

- `ResultBuilder.build()` 没有删除，旧 API 和直接调用仍然保留同一套领域规则。
- `build_prepared()` 不会再次执行 `ResultBuilder._apply_deterministic_overrides()`，避免字段重复抽取和覆盖。
- 二次抽取原始结果在内存中形成，进入最终映射前不会覆盖正式文件。
- 旧二次详情必须**合并到现有 primary details**，保留 `fieldIndex`、`tableIndex`、原有来源证据和 `extractionCandidates`；直接用二次详情替换会造成风资源、土方等字段丢失，本轮由真实报告回归发现并修复。
- 旧映射函数内部仍会读写文件。当前兼容阶段把这些读写定向到临时工作区，因此最终 `result/details/mapped` 只在映射和校验成功后才发布。每个文件通过 `os.replace` 替换，非跨文件单事务；极端磁盘错误仍可能使三个文件部分写入。
- `mapping_pipeline.yaml` 现阶段锁定旧算子执行顺序；修改顺序会失败。未来完成跨领域样本覆盖后才能开放可配置次序。
- `run_full_parse(parser, ...)` 未传配置根目录时自动复用工厂 `ResultBuilder.config_root`，保证预抽取/一次/二次/映射使用相同 YAML 目录。

## 验收和现存限制

- `tests/test_four_stage_pipeline.py`：阶段顺序、领域抽取不重复、旧字段对象不被输入改写。
- `tests/test_mapping_stage_contract.py`：YAML 算子顺序、映射失败不覆盖既有正式文件、一次详情不丢失、二次无中间写盘、自定义配置路径贯穿四阶段。
- GitHub Actions 继续比较 Linux 真实 DOCX、Windows Aspose 实际解析下的原版/重构版 `mapped.json`、`result.json`；另外两份原版会崩溃的报告做重构版烟测。
- 领域算法和映射后处理方法仍在 Python；其中个别**业务条件**仍有硬编码，不能把此阶段描述为全面的『配置单一真源』。复杂计算应保持 Python，抽取/匹配/优先级条件应继续迁入 YAML。
- 完整 DOC/PDF/OCR 及用户生产环境全字段验收仍需要更多真实报告。只有新旧全部符合约定后才合并 main。

## 调用方式

完整四阶段对外 API：

```python
from word_parser.application.factory import create_default_parser

parser = create_default_parser(config_root='configs')
result = parser.parse_full('项目可研报告.docx')
print(result['outputFiles']['mapped'])
```

`parser.parse()` 和 `parse_document()` **仍保留原来的一次解析兼容接口**，避免现有调用方因为升级被意外改变返回结构。
要完整运行预抽取、一次抽取、二次抽取及最终映射，应使用
`parse_full()`、`run_full_parse()` 或现有 `parse_document_with_table_values()`。

若调用方指定非默认 `config_root`，四阶段会使用同一个配置目录，二次表格配置默认从该目录的 `table_field_extractors.yaml` 获取。
