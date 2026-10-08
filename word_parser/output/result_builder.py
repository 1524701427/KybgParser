"""Compatibility facade assembling domain rules and result presentation.

The existing build sequence and mutable field precedence remain unchanged.
"""

from __future__ import annotations

from pathlib import Path

from typing import Any

from parser_engine.document.ast.document import DocumentAST

from parser_engine.document.ast.evidence import ParsedField

from word_parser.config.loader import ConfigLoader

from parser_engine.output.cover_ocr import CoverOcrExtractor, CoverOcrResult

from parser_engine.extraction.normalizer import Normalizer

from parser_engine.tables import OriginalTableResolver

from word_parser.config.result_schema import ResultSchemaMixin

from word_parser.config.result_defaults import ResultDefaults

from word_parser.extraction.document_support import DocumentSupportMixin

from word_parser.extraction.deterministic_rules import DeterministicRulesMixin

from word_parser.output.presentation import ResultPresentationMixin

from word_parser.domains.generation import GenerationRulesMixin

from word_parser.domains.electrical import ElectricalRulesMixin

from word_parser.domains.civil import CivilRulesMixin

from word_parser.domains.wind_resource import WindResourceRulesMixin

from word_parser.domains.finance import FinanceRulesMixin

from word_parser.domains.investment import InvestmentRulesMixin

from word_parser.domains.project_overview import ProjectOverviewRulesMixin

from word_parser.domains.environment import EnvironmentRulesMixin


class ResultBuilder(
    ResultSchemaMixin,
    ResultDefaults,
    DocumentSupportMixin,
    DeterministicRulesMixin,
    ResultPresentationMixin,
    GenerationRulesMixin,
    ElectricalRulesMixin,
    CivilRulesMixin,
    WindResourceRulesMixin,
    FinanceRulesMixin,
    InvestmentRulesMixin,
    ProjectOverviewRulesMixin,
    EnvironmentRulesMixin,
):
    """Assemble the same business result through responsibility-specific modules."""

    def __init__(
        self,
        cover_ocr_extractor: CoverOcrExtractor | None = None,
        output_schema: dict[str, Any] | None = None,
        field_configs: dict[str, dict[str, Any]] | None = None,
        config_root: str | Path = "configs",
    ):
        self.cover_ocr_extractor = cover_ocr_extractor or CoverOcrExtractor()
        self._cover_ocr_cache: dict[str, CoverOcrResult] = {}
        self.config_root = Path(config_root)
        self.field_configs = field_configs if field_configs is not None else ConfigLoader(self.config_root).load_field_configs()
        self.normalizer = Normalizer(self.field_configs)
        schema = output_schema if output_schema is not None else self._load_output_schema(self.config_root)
        self._configure_output_schema(schema or {})
        self.deterministic_rules = ConfigLoader(self.config_root).load_yaml("deterministic_rules.yaml")
        self._merge_field_meta_from_field_configs()
        self.original_table_resolver = OriginalTableResolver(self)

    def build(self, ast: DocumentAST | None, fields: dict[str, ParsedField], file_path: str | None = None) -> dict[str, Any]:
        """构建最终结果 JSON。"""
        details = self._build_details(ast)
        fields = dict(fields)
        if file_path and ast is not None:
            ast.meta.setdefault("file_path", file_path)
        if ast is not None:
            self._apply_deterministic_overrides(ast, fields, details)
            self._apply_quality_filters(fields, ast)
        tables = self._build_tables(ast, details, fields)
        sections = self._build_sections(fields, tables)
        field_traces = self._build_field_traces(fields)
        return {
            "fields": self._build_fields(fields),
            "fieldTraces": field_traces,
            "parsedFields": fields,
            "extractionFields": self._build_extraction_fields(fields),
            "details": details,
            "tables": tables,
            "sections": sections,
        }
