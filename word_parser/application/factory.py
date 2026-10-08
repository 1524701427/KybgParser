"""默认解析器装配工厂。"""

from __future__ import annotations

from pathlib import Path
from word_parser.config.loader import ConfigLoader
from parser_engine.core.logger import logger
from word_parser.application.pipeline import ParserPipeline
from word_parser.application.service import ParserService
from word_parser.output.json_exporter import JsonExporter
from word_parser.output.result_builder import ResultBuilder
from parser_engine.extraction import (
    CandidateResolver,
    CandidateRetriever,
    FieldMatcher,
    FunnelPruner,
    Normalizer,
    SemanticAnalyzer,
    SemanticVerifier,
    Validator,
    ValueExtractor,
)
from parser_engine.extraction.global_pointer_extractor import GlobalPointerExtractor
from parser_engine.extraction.uie_extractor import UIEExtractor
from parser_engine.document.loaders.document_loader import DocumentLoader
from parser_engine.ml.embedding_model import BgeEmbeddingMatcher
from parser_engine.document import SectionDetector, StructureParser


def create_default_parser(config_root: str | Path = "configs") -> ParserService:
    """创建默认解析服务。

    Args:
        config_root: 配置目录。

    Returns:
        ParserService: 可直接调用的解析服务。
    """
    config_loader = ConfigLoader(config_root)
    field_configs = config_loader.load_field_configs()
    section_config = config_loader.load_yaml("sections.yaml")
    pipeline_config = config_loader.load_yaml("pipeline.yaml")
    output_schema = config_loader.load_yaml("output_schema.yaml")

    # 模型默认先接入但不启用真实推理，后续有数据和模型后可切换为 active。
    bge_config = pipeline_config.get("modules", {}).get("bge_matcher", {})
    table_rule_config = pipeline_config.get("modules", {}).get("table_rule_extractor", {})
    regex_config = pipeline_config.get("modules", {}).get("regex_extractor", {})
    uie_config = pipeline_config.get("modules", {}).get("uie_extractor", {})
    semantic_config = pipeline_config.get("modules", {}).get("semantic_analyzer", {})
    verifier_config = pipeline_config.get("modules", {}).get("semantic_verifier", {})
    funnel_config = pipeline_config.get("modules", {}).get("funnel", {})
    bge_enabled = _module_active(bge_config)
    uie_enabled = _module_active(uie_config)
    gp_config = pipeline_config.get("modules", {}).get("global_pointer_extractor", {})
    gp_enabled = _module_active(gp_config)
    _warmup_ml_imports(bge_enabled=bge_enabled, uie_enabled=uie_enabled)

    pipeline = ParserPipeline(
        loader=DocumentLoader(),
        structure_parser=StructureParser(),
        section_detector=SectionDetector(section_config),
        candidate_retriever=CandidateRetriever(field_configs),
        field_matcher=FieldMatcher(
            bge_matcher=BgeEmbeddingMatcher(
                enabled=bge_enabled,
                model_name=bge_config.get("model_name", "BAAI/bge-base-zh-v1.5"),
                threshold=float(bge_config.get("threshold", 0.72)),
                max_text_length=int(bge_config.get("max_text_length", 256)),
                batch_size=int(bge_config.get("batch_size", 8)),
                memory_aware=bool(bge_config.get("memory_aware", True)),
                memory_safety_ratio=float(bge_config.get("memory_safety_ratio", 0.25)),
                min_free_memory_mb=int(bge_config.get("min_free_memory_mb", 1024)),
                release_after_match=bool(bge_config.get("release_after_match", True)),
            ),
            bge_top_k_per_field=int(bge_config.get("top_k_per_field", 30)),
            bge_min_score=float(bge_config.get("min_match_score", 0.0)),
        ),
        value_extractor=ValueExtractor(
            table_rule_enabled=_module_active(table_rule_config),
            regex_enabled=_module_active(regex_config),
            uie_extractor=UIEExtractor(
                enabled=uie_enabled,
                mode=uie_config.get("mode", "shadow"),
                model_name=uie_config.get("model_name", "uie-base"),
                threshold=float(uie_config.get("threshold", 0.65)),
                max_text_length=int(uie_config.get("max_text_length", 512)),
                batch_size=int(uie_config.get("batch_size", 4)),
                release_after_extract=bool(uie_config.get("release_after_extract", True)),
            ),
            uie_top_k_per_field=int(uie_config.get("top_k_per_field", 5)),
            uie_min_score=float(uie_config.get("min_match_score", 0.0)),
            entity_extractor=GlobalPointerExtractor(enabled=gp_enabled, mode=gp_config.get("mode", "shadow")),
        ),
        funnel_pruner=FunnelPruner(
            enabled=bool(funnel_config.get("enabled", True)),
            stages=funnel_config.get("stages", {}),
            field_configs=field_configs,
        ),
        normalizer=Normalizer(field_configs),
        semantic_analyzer=SemanticAnalyzer(
            field_configs,
            enabled=_module_active(semantic_config),
            near_window=int(semantic_config.get("near_window", 40)),
        ),
        semantic_verifier=SemanticVerifier(
            field_configs,
            enabled=_module_active(verifier_config),
            reranker_enabled=bool(verifier_config.get("reranker_enabled", False)) and _module_active(verifier_config),
            reranker_model_name=verifier_config.get("reranker_model_name"),
            reranker_backend=verifier_config.get("reranker_backend", "cross_encoder"),
            reranker_weight=float(verifier_config.get("reranker_weight", 0.6)),
            nli_enabled=bool(verifier_config.get("nli_enabled", False)) and _module_active(verifier_config),
            nli_model_name=verifier_config.get("nli_model_name"),
            nli_weight=float(verifier_config.get("nli_weight", 0.8)),
            release_after_verify=bool(verifier_config.get("release_after_verify", True)),
            batch_size=int(verifier_config.get("batch_size", 16)),
        ),
        resolver=CandidateResolver(field_configs),
        validator=Validator(field_configs),
        exporter=JsonExporter(result_builder=ResultBuilder(output_schema=output_schema, field_configs=field_configs, config_root=config_root)),
    )
    return ParserService(pipeline)


def _module_active(config: dict) -> bool:
    """统一解释模块配置的 enabled/mode 语义。"""
    return bool(config.get("enabled", False)) and config.get("mode", "active") == "active"


def _warmup_ml_imports(bge_enabled: bool, uie_enabled: bool) -> None:
    """按 Windows 上更稳定的顺序预热 ML 依赖导入。"""
    if not bge_enabled and not uie_enabled:
        return
    try:
        import torch  # noqa: F401
    except Exception as exc:
        logger.warning(f"Torch 预导入失败，BGE/UIE 将在各自加载时降级处理：{exc}")
        return
    if uie_enabled:
        try:
            import paddlenlp  # noqa: F401
        except Exception as exc:
            logger.warning(f"PaddleNLP 预导入失败，UIE 将在加载时降级处理：{exc}")
    if bge_enabled:
        try:
            import sentence_transformers  # noqa: F401
        except Exception as exc:
            logger.warning(f"sentence-transformers 预导入失败，BGE 将在加载时降级处理：{exc}")
