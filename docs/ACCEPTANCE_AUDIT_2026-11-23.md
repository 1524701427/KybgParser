# KybgParser 生产替换前双项验收核查（2026-11-23）

本文件区分：领域规则配置化完成度、GitHub 云端运行验证、用户 Windows 生产运行验证。
所有统计与运行结果来自当前 PR #1；本 PR 保持草稿，**不得视为可以直接合并 main**。

## 一、领域规则是否已经全部 Python → YAML？

**结论：未完成。** 本轮以 Python AST 静态审计扫描 word_parser/domains 下的全部 20 个 Python 模块（不含 __init__.py）。

| 核查指标 | 数量 |
|---|---:|
| 领域模块 | 20 |
| 含直接字面量 re.* 正则调用的模块 | 15 |
| 使用 YAML 规则入口的模块 | 7 |
| 直接字面量正则调用点 | 268 |
| 正则抽取辅助方法调用点 | 38 |
| 字段别名辅助方法调用点 | 71 |
| YAML 配置相关调用点 | 26 |

这些数字是 AST **调用点**，不是未迁移字段数量。保留 Python 兼容兜底正则并不意味着没有对应 YAML；还需要逐个核对这些调用点。复杂工程计算不应强行配置化。

### 逐模块清单如何获得

```bash
python tools/scripts/audit_domain_migration.py --root . --json-out domain_migration_inventory.json --markdown-out domain_migration_inventory.md
```

GitHub Actions 的 config-parity job 会自动上传 domain-migration-inventory 审计工件，包含每个模块中疑似需要复核的代码行号。

## 二、Windows Aspose/OCR 的实际运行情况

### 已确认的托管 Windows 测试

1. .NET 8 CoreCLR 与项目自带的 Aspose.Words.dll 加载成功；明确为 dotnet-dll 模式，未回退到 SimpleDocxLoader；SkiaSharp 加载成功。
2. 一份仓库内真实 DOCX 在 GitHub Windows runner 上使用实际 Aspose 完整解析 main/refactor，两份 mapped.json 和 result.json 严格递归对比，**0 差异**。
3. 在 Windows runner 上安装 RapidOCR 后，经 CoverOcrExtractor 对生成的图片执行实际 OCR，识别出 Wind / Power / 200 / MW。
4. Linux 备用解析路径仍有原来的一份 DOCX 严格对比 0 差异，另外两份旧版会失败的 DOCX 已在新版本生成 54、51 个非空字段；后两份不是新旧对照通过。

证据：
- Windows Aspose 通过：https://github.com/1524701427/KybgParser/actions/runs/45105340506
- Windows RapidOCR 成功：https://github.com/1524701427/KybgParser/actions/runs/45105554675
- 最新静态领域审计：https://github.com/1524701427/KybgParser/actions/runs/45104994932

### 尚不能确认的部分

- 用户本机 Windows + 当前 Aspose/.NET/SkiaSharp 版本、许可证和 OCR 模型是否与 GitHub runner 相同。
- 使用真实可研报告封面图的 OCR 内容是否准确；目前 RapidOCR 属于生成测试图片的推理烟测。
- 原始 .doc、复杂多表 DOCX、PDF、分期/规划版本与图表组合抽取是否在同一生产环境全部通过。
- 全部 284 个最终映射字段在每份报告上的值、单位、组合表行数和证据是否正确；现有字段契约防止结构删除，但不能保证每个字段的正确值。

### 用户 Windows 生产环境一次跑完整回归

要求：两个独立工作目录分别为旧 main 和当前重构分支，使用同一个已安装 pythonnet、Aspose 和 OCR 的 Python 解释器；输出目录须在两仓库外。

```bash
python tools/scripts/run_real_report_parity.py \
  --baseline-root ../KybgParser-main \
  --candidate-root . \
  --report '../KybgParser-main/samples/reports/5.陕西华电咸阳永寿常宁镇10万千瓦风电项目可行性研究报告.docx' \
  --report '../KybgParser-main/samples/reports/陕西华电靖边韩家沟200MW风电项目可行性研究报告.doc' \
  --out-dir ../KybgParser-parity \
  --timeout-seconds 1800
```

可重复指定 --report 增加本机真实报告。该脚本把各输入分别交给旧版和新版，比较 mapped.json 和 result.json 的键、数值类型、数值、嵌套表与行数，产生 regression_summary.json。原版不能解析的报告必须单独标为“基线失败”，不得写为“0 差异已验收”。

## 发布门槛（目前不满足）

- [ ] 所有领域 Python 抽取调用点完成逐个分类：可配置规则已经迁入 YAML，工程算法保留在 Python 并附说明。
- [ ] 用户本机 Aspose .NET / OCR 前置检查成功，并记录实际版本与模型。
- [ ] 至少覆盖已有 DOC、DOCX、PDF、带封面 OCR、分期项目及复杂组合表的代表报告。
- [ ] 原版可成功运行的报告逐字段 JSON 0 未解释差异；原版已有缺陷的报告需要人工校核预期结果。
- [ ] 对每份报告的 284 映射键结构、非空字段、单位、表格行数及关键字段来源进行复核。

当前结论：托管 Windows 的局部运行能力已证实；完整领域配置迁移和真实生产报告的全量业务正确性 **尚未完成验收**。
