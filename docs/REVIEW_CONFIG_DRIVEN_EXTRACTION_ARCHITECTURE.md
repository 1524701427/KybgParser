# KybgParser 代码走查：抽取配置化 → Python 算子执行 → 最终统一映射

> 走查基线：`refactor/config-driven-extraction-phase1`，提交 `b73c40c4`（2026-11-23）。只读审查，不修改生产抽取和映射行为。此文为**代码职责检查**，不是“全部迁移已完成”证明。

## 目标边界

唯一正确的业务链路应为：

1. **读取文档**：Word/PDF/OCR → DocumentAST（章节、段落、表格、页码、来源）。
2. **编译并验证 YAML 配置**：字段定义、别名/正则/来源条件/排除条件、方法名、候选优先级、校验规则、映射规则；缺失关键配置必须明确报错。
3. **Python 运行通用算子**：`regex`、`table_lookup`、`column_values`、`sum`、`derived`、`domain_calculation` 等仅实现算法；特殊工程计算可由已注册 Python 方法实现，但必须从配置中被引用。
4. **统一候选和冲突处理**：按 `fieldCode` 汇总所有方法结果、归一化、上下文过滤、规则选优，保留完整证据，不在此阶段写最终占位符。
5. **最终映射一次**：统一的 `MappingExecutor` 根据 `output_schema.yaml` 生成原有 284 个映射占位符；命名后处理算子在映射之前执行，再校验并一次性导出 `result/details/mapped`。

正确的职责划分不是“把 Python 算法转换为 YAML”，而是 YAML 声明 **抽什么/在哪里/用什么方法/以什么优先级/映射到哪里**；Python 只实现受控方法，不硬编码业务字段抽取条件或占位符名称。

## 当前真实入口

- `word_parser/application/factory.py:create_default_parser` 加载 `fields/*.yaml`、`sections.yaml`、`pipeline.yaml`、`output_schema.yaml`、`extraction_runtime.yaml`，实例化主抽取流水线、`ResultBuilder` 和 `JsonExporter`。
- `word_parser/application/pipeline.py:parse` → `document.stage.read_document` → `discovery.stage.discover_indicators` → `primary.stage.extract_primary_fields` → `JsonExporter.export`。
- `JsonExporter.export` 调用 `ResultBuilder.build(ctx.ast, ...)`。**此时并没有完成所有抽取**。
- `ResultBuilder.build`（`word_parser/output/result_builder.py`）调用 `_apply_deterministic_overrides(ast, fields, details)`、`_fill_foundation_equivalent_fields` 和 `_fill_finance_insurance_equivalent_field`，仍由结果构建层执行领域抽取、计算与覆盖逻辑。
- `word_parser/application/workflow.py:run_full_parse` 以 `defer_mapping=True` 导出一次结果；`enhance_parse_result` 运行二次表格抽取，按多个具体业务模块的固定顺序更新 `mapped/result/details`。

## 发现及优先级

### P0-1：结果构建器仍是领域抽取器

**证据**：`word_parser/output/result_builder.py:ResultBuilder.build`；`word_parser/output/builder_support/deterministic_rules.py:_apply_deterministic_overrides`。后者直接调用 `_apply_electrical_primary_table_field_overrides`、`_apply_finance_field_overrides`、`_resource_scalar_override_values`、`_finance_text_scalar_override_values` 等，写死次序、skip-code 集合和部分字段特殊条件。

**影响**：YAML 字段规则只能覆盖一部分逻辑。字段也可能在输出阶段重新被覆盖；配置单独增加字段无法保证调用到对应专项算子。

**改法**：抽离 `DomainExtractionStage`，建立命名算子注册表；把领域调用顺序、适用字段、触发条件和覆盖策略迁到 YAML，复杂计算方法继续在 Python。结果构建器改为只接收已选中的 `FieldResult`/表结果，不再接收 AST 抽取新值。

### P0-2：映射不在最后执行一次，而是分散修改

**证据**：`word_parser/application/workflow.py:enhance_parse_result` 在二次抽取完成后调用 `mapping_from_details`、`_sync_secondary_outputs`、`_combine_finance_cost_mappings`、`_combine_finance_price_mappings`、`_align_combined_table_mappings`、`_hide_combined_table_duplicate_fields`、`_fill_transformers_from_installation_estimate`、`_fill_station_transformers_from_equipment_table`、`_map_final_investment_fields` 之后，最后再次填充/校验映射。以上业务模块中有直接将 `mapped/result/details` 写回磁盘的操作（例如 `word_parser/mapping/equipment.py`、`word_parser/mapping/secondary_sync.py`）。

**影响**：映射层含业务抽取和回填，输出存在中间版本；后续任一步抛异常时磁盘上的三份 JSON 可能不一致；修改占位符可能遗漏硬编码引用。

**改法**：把这些函数分为“结果阶段派生/修正算子”和“纯投影映射”；派生/修正先在内存中完成，映射只执行一次。全部校验通过后，使用临时文件加原子替换提交三份输出。

### P0-3：YAML 还不是抽取规则的唯一权威来源

**证据**：
- `word_parser/config/domain_regex.py` 按 `domain_literal_regexes.<模块>.search_001`、`domain_literal_lists.<模块>.list_001` 查询；若缺失则**无错误地回退**到 Python 传入的字面量。
- `word_parser/domains/finance.py` 等调用处依然含 `domain_regex(self, "finance", "search_001", r"...")`、`domain_strings(..., ["..."])`。
- `configs/deterministic_rules.yaml` 目前以调用位置编号为键，未直接标明 `field_code`、执行方法、适用章节、规则目的或输出单位。
- `word_parser/config/loader.py:load_yaml` 对不存在的配置文件记录 WARNING 并返回 `{}`；两个重复字段编码仍按文件排序后加载覆盖先加载（`newRoadLength`、`rebuiltRoadLength`）。

**影响**：删掉某条 YAML 后程序仍可能成功抽取，不能证实确实按 YAML 运行；`search_001` 这类名称无业务语义，插入/调整 Python 调用时易错位。

**改法**：为字段规则引入稳定语义 ID，统一为 `fields.<fieldCode>.rules[].id/operator/source/match/priority` 或兼容现有同义结构，开启 **strict_config** 时引用不存在的规则、未知算子、重复字段或缺失输出字段须报错。过渡期间保留 Python 字面量仅为旧配置兼容，完成全量回归后去重。

### P1-1：一次与二次抽取的方法仍是两套

**证据**：`word_parser/primary/value_extractor.py`、`word_parser/secondary/table_values/resolver.py` 使用不同算子调用入口；`word_parser/extraction/candidate_facts.py` 目前只有只读审计适配器，正式 `CandidateResolver` 并不读取该适配器的统一结果。

**改法**：保留原有两套算法，但在算子返回边界统一为 `ExtractionCandidate`（字段编码、值、原值、单位、来源、页码、行列、算子、状态、优先级），再统一决策，避免二次抽取绕过主字段的冲突策略。

### P1-2：最终映射仍有硬编码字段和后处理

**证据**：`word_parser/mapping/projector.py` 的 `_FIELD_FALLBACKS = {"financeInsuranceRate": "insuranceRate"}` 和 `hubHeightAirDensityRange` 的特殊分支、`windResourceTurbulenceIntensityRecords` 特殊合并；`word_parser/mapping/equipment.py` 直接使用 `${installation_engineering_budgets_table}` 等占位符和手写 code→输出名。

**改法**：在 `output_schema.yaml` 声明源字段、备选字段、输出字段及命名 transform；Python 实现并注册 `merge_turbulence_records`、`map_air_density_range`、`equipment_from_estimate` 等算子；**不允许领域模块自己拼装 `${...}` 输出 key**。

### P1-3：流水线配置有“写了开关却没有统一生效”的风险

**证据**：`configs/pipeline.yaml` 里 `validator.enabled: false`；但 `word_parser/application/factory.py` 无条件实例化 `Validator(field_configs)`，`word_parser/primary/stage.py` 无条件调用 `parser.validator.validate(...)`。工厂使用 `DocumentLoader()`，未传入 `pipeline.yaml.modules.aspose_loader` 开关。

**改法**：建立“配置装配检查”：每个 `pipeline.yaml.modules` 开关必须有对应装配决策及测试；先调查已使用环境，不能直接改变验证行为造成输出差异。

### P1-4：配置根目录跨阶段可能不一致

**证据**：`create_default_parser(config_root=...)` 支持自定义配置根目录，但 `word_parser/application/workflow.py:run_full_parse` 默认再次使用相对 `configs` 和 `configs/table_field_extractors.yaml`。未同时传入根目录的调用方可能让一次抽取使用 A 配置、二次抽取和映射使用 B 配置。

**改法**：创建一次性的不可变 `CompiledRuleSet` / `ParserContext`，将配置根目录及版本签名传遍所有阶段，杜绝后续按当前工作目录重新载入。

### P2：历史兼容 API 和配置说明尚需整理

- `word_parser/extraction/engine.py` 仍 re-export `parser_engine.*`，而正式工厂使用 `word_parser.primary.*`，存在双实现入口。
- `configs/README.md` 仍介绍一些当前工厂没有装配的模型/模式，文档不能直接当实际实现能力证明。
- `ConfigLoader` 的字段重复覆盖策略需要显式声明和测试，不能只凭文件名排序决定规则来源。

## 当前已经可复用的内容（不应该推倒重写）

- `configs/fields/*.yaml` 已包含字段编码、别名、章节范围、正则、值类型、单位、校验约束。
- `configs/table_field_extractors.yaml` 已声明 `cell/cell_items/max_row_label/table_projection/sum_fields` 等二次表格算子。
- `word_parser/secondary/table_values/resolver.py` 已采用算子白名单注册表。
- `configs/output_schema.yaml` 已维护原有 284 项映射关系以及章节、原表和组合表定义。
- `word_parser/document/*` 的 AST/OCR/Aspose 路径应保持不动。
- 单元测试与 GitHub 的 Linux DOCX / Windows Aspose 严格对照应继续作为验收门槛，不得将单样本 0 差异视为全业务正确。

## 建议最终目录及配置结构

```text
configs/
  fields/wind_resource.yaml        # 字段 + 原/备选规则 + 调用的 operator
  fields/electrical.yaml
  fields/civil_construction.yaml
  fields/finance.yaml
  extractors.yaml                   # operator 白名单/参数合法性/默认值
  table_field_extractors.yaml      # 现有二次表格业务规则，逐步统一算子协议
  output_schema.yaml               # 唯一最终映射配置，原 284 项不变
word_parser/
  document/                         # 原文/AST/OCR
  extraction/operators/             # Python 只提供 regex/table/aggregate/formula 实现
  extraction/rule_compiler.py       # 配置校验、编译、规则索引
  extraction/executor.py            # 按配置调用算子、产出统一候选证据
  extraction/resolver.py            # 统一选值，不映射
  mapping/executor.py               # 只在最后一次执行映射
  output/exporter.py                # 只写最终文件，不再抽取新值
```

推荐单条字段配置样式（示意，**不是声称现有解析器已经支持**）：

```yaml
fields:
  hubHeight:
    name: 轮毂高度
    value_type: number
    standard_unit: m
    rules:
      - id: hub_height_table
        operator: table_lookup
        source: [table]
        section_include: [风机选型, 主要技术参数]
        row_aliases: [轮毂高度, 轮毂高]
        column_aliases: [数值, 参数]
        priority: 100
      - id: hub_height_text
        operator: regex
        source: [paragraph]
        patterns:
          - '轮毂高度\s*(?:为|是|[:：])?\s*(?P<value>\d+(?:\.\d+)?)\s*m'
        priority: 50
```

映射配置单独保留 `output_field_codes: hubHeight: ...`；字段提取算子永远不关心映射占位符。

## 验收条件

1. 每一条启用的字段规则都能在 YAML 找到 **field_code → rule ID → operator → source → priority**，未知规则不再静默回退。
2. 所有抽取和领域计算在进入结果构建前完成，`ResultBuilder` 不再从 AST 抽新字段。
3. 统一结果中完整保留来源与未选候选；一次/二次抽取不会隐式覆盖。
4. 最终结果映射只运行一次，并由 `output_schema.yaml` 完整驱动；所有代码不拼装 `${...}` 业务占位符。
5. 原 284 个映射结构保持不变，代表性 DOC/DOCX/PDF/OCR/组合表真实报告进行逐字段值、类型、单位、表行数对照。
6. 只有上述门槛通过才将 PR #1 从草稿转为可合并，不再以正则/列表迁移数量宣布完成。

**最终判断：当前实现属于“部分 YAML 配置化 + Python 领域混合抽取 + 多阶段补丁式映射”，与目标架构仍有实质差距。**
