# tests

这里存放单元测试和轻量流程回归测试。

## 当前覆盖点

- 候选召回是否能通过 alias 找到段落。
- 默认解析器是否能创建。
- BGE 批量编码和内存降级逻辑。
- UIE 候选 Top-K 和单位白名单逻辑。
- 候选消解是否优先合法数值。
- 规则语义分析是否能奖励强证据、惩罚弱 fallback。
- 候选级/最终字段级归一化是否保持 raw_value。
- Reranker/NLI 语义验证器的 query/hypothesis 和打分逻辑。
- 漏斗剪枝是否按字段保留 Top-K。

## 运行

```powershell
python -m pytest -q
D:\anaconda\envs\python310\python.exe -m pytest -q
```

测试默认不解析整份 Word，也不强制加载大模型，避免单元测试变慢。
