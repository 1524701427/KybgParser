from __future__ import annotations

from collections import Counter
from time import perf_counter

from word_parser.logger import logger

def discover_indicators(parser, ctx) -> list:
    indicators = []
    if parser.indicator_discovery:
        stage_started = perf_counter()
        indicators = parser.indicator_discovery.discover_raw(ctx.ast)
        parser._log_stage("动态指标发现", stage_started, 发现=len(indicators))

        stage_started = perf_counter()
        indicators = parser.indicator_discovery.match_dictionary(indicators)
        dictionary_counts = Counter(item.match_method for item in indicators)
        parser._log_stage(
            "词典匹配", stage_started, 输入=len(indicators),
            精确=dictionary_counts["dictionary"], 歧义=dictionary_counts["ambiguous"],
            包含建议=dictionary_counts["dictionary_suggestion"],
        )

        stage_started = perf_counter()
        indicators = parser.indicator_discovery.match_similarity(indicators)
        similarity_counts = Counter(item.match_method for item in indicators)
        similarity_enabled = parser.indicator_discovery.lexicon.rapidfuzz_available
        parser._log_stage(
            "字段相似度", stage_started, 模式="RapidFuzz" if similarity_enabled else "未安装",
            比较=sum(1 for item in indicators if item.match_method in {"rapidfuzz", "suggestion"}),
            高分候选=similarity_counts["rapidfuzz"], 其他建议=similarity_counts["suggestion"],
        )
    else:
        logger.info("解析阶段 | 阶段=动态指标发现/词典匹配/字段相似度 | 状态=未配置")
    ctx.debug["indicators"] = [item.to_dict() for item in indicators]

    return indicators
