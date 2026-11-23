"""解析流水线。"""

from __future__ import annotations

from time import perf_counter

from word_parser.application.context import ParseContext
from word_parser.document.stage import read_document
from word_parser.discovery.stage import discover_indicators
from word_parser.primary.stage import extract_primary_fields
from word_parser.logger import logger


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
        resolver,
        validator,
        exporter,
        indicator_discovery=None,
        context_filter=None,
    ):
        """初始化流水线。

        参数：
            loader: 根据文件类型选择 Word/PDF 加载器。
            structure_parser: 文档结构解析器。
            section_detector: 章节识别器。
            candidate_retriever: 候选区域召回器。
            field_matcher: 字段匹配器。
            value_extractor: 字段值抽取器。
            funnel_pruner: 漏斗剪枝器。
            normalizer: 归一化器。
            semantic_analyzer: 语义一致性分析器。
            resolver: 多候选冲突消解器。
            validator: 校验器。
            exporter: JSON 导出器。
            indicator_discovery: 可选的文档原生指标发现器。
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
        self.resolver = resolver
        self.validator = validator
        self.exporter = exporter
        self.indicator_discovery = indicator_discovery
        self.context_filter = context_filter

    def parse(self, file_path: str, *, defer_mapping: bool = False) -> dict:
        """执行前置扫描和一次抽取，可按需延后最终映射。

        参数：
            file_path: Word 或 PDF 文档路径。
            defer_mapping: 是否等待二次抽取结束后再生成映射。

        返回：
            dict: 一次抽取结果及输出文件路径。
        """
        parse_started = perf_counter()
        logger.info(f"解析开始 | 文件={file_path}")
        ctx = ParseContext(file_path=file_path)

        read_document(self, ctx)
        indicators = discover_indicators(self, ctx)
        extract_primary_fields(self, ctx, indicators)

        stage_started = perf_counter()
        result = self.exporter.export(ctx, defer_mapping=True) if defer_mapping else self.exporter.export(ctx)
        mapped = result.get("mapped", {})
        self._log_stage("映射输出", stage_started, 映射键=len(mapped),
                        非空=sum(value is not None for value in mapped.values()))
        logger.info(f"解析完成 | 文件={file_path} | 总耗时={perf_counter() - parse_started:.3f}s")
        return result

    @staticmethod
    def _log_stage(name: str, started_at: float, **metrics: object) -> None:
        """使用统一的计时方式和具名计数记录已完成阶段。

        参数：
            name: 便于阅读的流水线阶段名称。
            started_at: 阶段开始前读取的 ``perf_counter`` 值。
            **metrics: 与该阶段相关的计数或模式标签。
        """
        details = " | ".join(f"{key}={value}" for key, value in metrics.items())
        logger.info(f"解析阶段 | 阶段={name} | 状态=完成 | {details} | 耗时={perf_counter() - started_at:.3f}s")
