"""解析流水线。"""

from __future__ import annotations

from parser_engine.core.context import ParseContext
from parser_engine.core.logger import logger


class ParserPipeline:
    """可研报告解析流水线。"""

    def __init__(
        self,
        loader,
        structure_parser,
        section_detector,
        candidate_retriever,
        field_matcher,
        value_extractor,
        funnel_pruner,
        normalizer,
        semantic_analyzer,
        semantic_verifier,
        resolver,
        validator,
        exporter,
    ):
        """初始化流水线。

        Args:
            loader: Word 加载器。
            structure_parser: 文档结构解析器。
            section_detector: 章节识别器。
            candidate_retriever: 候选区域召回器。
            field_matcher: 字段匹配器。
            value_extractor: 字段值抽取器。
            funnel_pruner: 漏斗剪枝器。
            normalizer: 归一化器。
            semantic_analyzer: 语义一致性分析器。
            semantic_verifier: Reranker/NLI 语义验证器。
            resolver: 多候选冲突消解器。
            validator: 校验器。
            exporter: JSON 导出器。
        """
        self.loader = loader
        self.structure_parser = structure_parser
        self.section_detector = section_detector
        self.candidate_retriever = candidate_retriever
        self.field_matcher = field_matcher
        self.value_extractor = value_extractor
        self.funnel_pruner = funnel_pruner
        self.normalizer = normalizer
        self.semantic_analyzer = semantic_analyzer
        self.semantic_verifier = semantic_verifier
        self.resolver = resolver
        self.validator = validator
        self.exporter = exporter

    def parse(self, file_path: str) -> dict:
        """执行完整解析。

        Args:
            file_path: Word 文档路径。

        Returns:
            dict: 标准 JSON 结果。
        """
        logger.info(f"开始解析文档：{file_path}")
        ctx = ParseContext(file_path=file_path)

        ctx.ast = self.loader.load(file_path)
        logger.info(f"文档加载完成：块 {len(ctx.ast.blocks)} 个，表格 {len(ctx.ast.tables)} 个")

        ctx.ast = self.structure_parser.parse(ctx.ast)
        ctx.ast = self.section_detector.detect(ctx.ast)

        ctx.candidates = self.candidate_retriever.retrieve(ctx.ast)
        logger.info(f"候选区域召回完成：{len(ctx.candidates)} 条")

        ctx.matches = self.field_matcher.match(ctx.candidates)
        logger.info(f"字段匹配完成：{len(ctx.matches)} 条")

        ctx.matches = self.funnel_pruner.prune_matches(ctx.matches, "extraction_matches")
        ctx.extractions = self.value_extractor.extract(ctx.matches)
        logger.info(f"字段值抽取完成：{len(ctx.extractions)} 条")

        ctx.normalized = self.normalizer.normalize_candidates(ctx.extractions)
        ctx.normalized = self.funnel_pruner.prune_extractions(ctx.normalized, "semantic_candidates")
        ctx.normalized = self.semantic_analyzer.analyze(ctx.normalized)
        if self._semantic_verifier_enabled():
            ctx.normalized = self.funnel_pruner.prune_extractions(ctx.normalized, "reranker_candidates")
            ctx.normalized = self.semantic_verifier.verify_reranker(ctx.normalized)
            ctx.normalized = self.funnel_pruner.prune_extractions(ctx.normalized, "nli_candidates")
            ctx.normalized = self.semantic_verifier.verify_nli(ctx.normalized)
        ctx.resolved = self.resolver.resolve(ctx.normalized)
        ctx.resolved = self.normalizer.normalize_fields(ctx.resolved)
        ctx.validated = self.validator.validate(ctx.resolved)

        logger.info("文档解析完成，准备导出标准 JSON")
        return self.exporter.export(ctx)

    def _semantic_verifier_enabled(self) -> bool:
        return bool(getattr(self.semantic_verifier, "enabled", True))
