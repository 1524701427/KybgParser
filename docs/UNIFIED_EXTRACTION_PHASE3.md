# 统一抽取增量迁移
- 预抽取在结构诊断之后将安全恢复的表格投影回同一个 AST，所有旧抽取器通过 AST 读取；存在诊断或歧义的表回退。模式由 document_structure.yaml 的 table_recovery.extraction_view 控制，audit 可用于旧行为对照。
- 共享候选选择基础工具，保留旧 primary 评分与 secondary fill-only。22 条旧单位转换迁移 YAML，不改变原换算。
- 概算列角色、设备价格目录继承、表头显式货币单位、数量/单价/合价区分；仍为审计，不自动修改业务值。
- 投资汇总的行规则、层级边界、别名、补值规则配置在 investment_completion.yaml，纯计算在 secondary，mapping 兼容适配器只负责应用和同步此算子的结果。其余变压器和财务等旧 mapping 算子仍待迁移。
- 已迁移投资依据的正则与上下文别名，未删除其他领域规则。统一候选评分及归一化尚未彻底合并。
- 主分支 CI 扩大到既有配置回归测试与新结构测试；真实报告 DOC/DOCX/PDF 的值与来源需要独立回归。
