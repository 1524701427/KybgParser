from __future__ import annotations

from time import perf_counter

from word_parser.logger import logger

def extract_primary_fields(parser, ctx, indicators: list) -> None:
    stage_started = perf_counter()
    hints = parser.indicator_discovery.recall_hints(indicators) if parser.indicator_discovery else {}
    ctx.candidates = parser.candidate_retriever.retrieve(ctx.ast, observation_hints=hints)
    parser._log_stage("已知字段召回", stage_started, 候选=len(ctx.candidates),
                      预抽取定位=sum(len(ids) for sources in hints.values() for ids in sources.values()),
                      定位候选=sum(bool(item.meta.get("observation_hint")) for item in ctx.candidates))

    stage_started = perf_counter()
    ctx.matches = parser.field_matcher.match(ctx.candidates)
    parser._log_stage("已知字段匹配", stage_started, 匹配=len(ctx.matches))

    stage_started = perf_counter()
    ctx.matches = parser.funnel_pruner.prune_matches(ctx.matches, "extraction_matches")
    ctx.extractions = parser.value_extractor.extract(ctx.matches)
    rule_count = len(ctx.extractions)
    parser._log_stage("候选值抽取", stage_started, 规则=rule_count)

    stage_started = perf_counter()
    ctx.normalized = parser.normalizer.normalize_candidates(ctx.extractions)
    rejected = []
    if parser.context_filter is not None:
        ctx.normalized, rejected = parser.context_filter.filter(ctx.normalized)

    stage_started_discovery = perf_counter()
    proposed = []
    admitted = []
    accepted_discovered = []
    if parser.indicator_discovery:
        usable = [item for item in ctx.normalized
                  if item.value is not None and str(item.value).strip()]
        proposed = parser.indicator_discovery.fallback_extractions(
            indicators, usable, include_covered=True)
        if parser.indicator_discovery.mode == "active":
            admitted = proposed
            if admitted:
                ctx.extractions.extend(admitted)
                accepted_discovered = parser.normalizer.normalize_candidates(admitted)
                if parser.context_filter is not None:
                    accepted_discovered, rejected_discovered = parser.context_filter.filter(accepted_discovered)
                    rejected.extend(rejected_discovered)
                ctx.normalized.extend(accepted_discovered)
    parser._log_stage("动态指标补漏", stage_started_discovery,
                    动态候选=len(proposed), 动态入选=len(admitted),
                    动态通过约束=len(accepted_discovered),
                    动态精确入选=sum(item.debug.get("name_match") == "dictionary" for item in admitted),
                    动态包含入选=sum(item.debug.get("name_match") == "dictionary_contextual" for item in admitted),
                    动态相似入选=sum(item.debug.get("name_match") == "rapidfuzz" for item in admitted),
                    动态模式=getattr(parser.indicator_discovery, "mode", "关闭"),
                    合计=len(ctx.normalized))
    if parser.context_filter is not None:
        ctx.debug["context_rejections"] = [
            {"field_code": item.field_code, "reason": item.debug.get("context_rejection"),
             "evidence": item.evidence.text, "page": item.evidence.page}
            for item in rejected
        ]
        parser._log_stage("字段上下文约束", stage_started, 接受=len(ctx.normalized), 拒绝=len(rejected))
    ctx.normalized = parser.funnel_pruner.prune_extractions(ctx.normalized, "semantic_candidates")
    ctx.normalized = parser.semantic_analyzer.analyze(ctx.normalized)
    parser._log_stage("候选归一化与语义规则", stage_started, 候选=len(ctx.normalized))
    stage_started = perf_counter()
    ctx.normalized = parser.resolver.score_candidates(ctx.normalized)
    parser._log_stage("规则评分", stage_started, 候选=len(ctx.normalized))
    stage_started = perf_counter()
    ctx.resolved = parser.resolver.resolve(ctx.normalized)
    ctx.debug["candidate_conflicts"] = {
        code: field.debug.get("conflict_values") for code, field in ctx.resolved.items()
        if field.debug.get("conflict_values")
    }
    ctx.resolved = parser.normalizer.normalize_fields(ctx.resolved)
    ctx.validated = parser.validator.validate(ctx.resolved)
    parser._log_stage("候选选值与字段校验", stage_started, 已选=len(ctx.resolved),
                    通过=sum(field.status == "PASS" for field in ctx.validated.values()))

