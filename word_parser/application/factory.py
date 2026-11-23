"""默认解析器装配工厂。"""

from __future__ import annotations

from pathlib import Path
from word_parser.config.loader import ConfigLoader
from word_parser.application.pipeline import ParserPipeline
from word_parser.application.service import ParserService
from word_parser.output.json_exporter import JsonExporter
from word_parser.output.result_builder import ResultBuilder
from word_parser.primary.candidate_resolver import CandidateResolver
from word_parser.primary.candidate_retriever import CandidateRetriever
from word_parser.primary.field_matcher import FieldMatcher
from word_parser.primary.funnel_pruner import FunnelPruner
from word_parser.primary.normalizer import Normalizer
from word_parser.primary.semantic_analyzer import SemanticAnalyzer
from word_parser.primary.validator import Validator
from word_parser.primary.value_extractor import ValueExtractor
from word_parser.discovery.indicators import IndicatorDiscovery, IndicatorLexicon
from word_parser.primary.context_filter import CandidateContextFilter
from word_parser.document.router import DocumentLoader
from word_parser.document import SectionDetector, StructureParser


def create_default_parser(config_root: str | Path = "configs") -> ParserService:
    """创建默认解析服务。

    参数：
        config_root: 配置目录。

    返回：
        ParserService: 可直接调用的解析服务。
    """
    config_loader = ConfigLoader(config_root)
    field_configs = config_loader.load_field_configs()
    section_config = config_loader.load_yaml("sections.yaml")
    pipeline_config = config_loader.load_yaml("pipeline.yaml")
    output_schema = config_loader.load_yaml("output_schema.yaml")
    extraction_runtime = config_loader.load_yaml("extraction_runtime.yaml")

    table_rule_config = pipeline_config.get("modules", {}).get("table_rule_extractor", {})
    regex_config = pipeline_config.get("modules", {}).get("regex_extractor", {})
    semantic_config = pipeline_config.get("modules", {}).get("semantic_analyzer", {})
    funnel_config = pipeline_config.get("modules", {}).get("funnel", {})
    indicator_config = pipeline_config.get("modules", {}).get("indicator_discovery", {})
    shared_lexicon = (IndicatorLexicon(field_configs, matching_config=(extraction_runtime.get("discovery") or {}).get("rapidfuzz"))
                      if indicator_config.get("enabled", True) else None)

    pipeline = ParserPipeline(
        loader=DocumentLoader(),
        structure_parser=StructureParser(),
        section_detector=SectionDetector(section_config),
        candidate_retriever=CandidateRetriever(field_configs, settings=extraction_runtime.get("retrieval")),
        field_matcher=FieldMatcher(extraction_runtime.get("field_matching"), lexicon=shared_lexicon),
        value_extractor=ValueExtractor(
            table_rule_enabled=_module_active(table_rule_config),
            regex_enabled=_module_active(regex_config),
            table_header_config=(extraction_runtime.get("value_extraction") or {}).get("table_headers"),
            value_config=extraction_runtime.get("value_extraction"),
        ),
        funnel_pruner=FunnelPruner(
            enabled=bool(funnel_config.get("enabled", True)),
            stages=funnel_config.get("stages", {}),
            field_configs=field_configs,
            strong_extraction_methods=(extraction_runtime.get("funnel") or {}).get("strong_extraction_methods"),
        ),
        normalizer=Normalizer(field_configs, unit_map=(extraction_runtime.get("normalization") or {}).get("unit_aliases")),
        context_filter=CandidateContextFilter(field_configs),
        semantic_analyzer=SemanticAnalyzer(
            field_configs,
            enabled=_module_active(semantic_config),
            near_window=int(semantic_config.get("near_window", 40)),
        ),
        resolver=CandidateResolver(field_configs, scoring_config=extraction_runtime.get("candidate_resolution")),
        validator=Validator(field_configs),
        exporter=JsonExporter(result_builder=ResultBuilder(output_schema=output_schema, field_configs=field_configs, config_root=config_root)),
        indicator_discovery=(IndicatorDiscovery(field_configs, mode=indicator_config.get("mode", "active"), settings=extraction_runtime.get("discovery"), lexicon=shared_lexicon)
                             if indicator_config.get("enabled", True) else None),
    )
    return ParserService(pipeline)


def _module_active(config: dict) -> bool:
    """统一解释模块配置的 enabled/mode 语义。"""
    return bool(config.get("enabled", False)) and config.get("mode", "active") == "active"
