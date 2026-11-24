"""Guard against accidentally restoring the retired parser engine or its imports."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_engine_removed_and_no_live_imports():
    assert not (ROOT / "parser_engine").exists()
    roots = [ROOT / "word_parser", ROOT / "tools", ROOT / "tests"]
    for source_root in roots:
        for path in source_root.rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module.split(".")[0] != "parser_engine", path
                if isinstance(node, ast.Import):
                    assert all(alias.name.split(".")[0] != "parser_engine" for alias in node.names), path


def test_current_public_service_and_compatibility_paths():
    from word_parser import create_parser
    from word_parser.application.api import create_parser as implementation
    from word_parser.application.service import ParserService
    from word_parser.core import create_parser as core_create_parser
    from word_parser.core.service import ParserService as core_service
    from word_parser.core.pipeline import ParserPipeline
    from word_parser.application.pipeline import ParserPipeline as pipeline_impl
    from word_parser.core.config import ConfigLoader
    from word_parser.config.loader import ConfigLoader as loader_impl

    assert create_parser is core_create_parser is implementation
    assert core_service is ParserService
    assert ParserPipeline is pipeline_impl
    assert ConfigLoader is loader_impl


def test_historical_module_aliases_resolve_to_current_implementations():
    from word_parser.document.loaders import DocumentLoader
    from word_parser.document.router import DocumentLoader as active_loader
    from word_parser.document.model import DocumentAST
    from word_parser.document.ast.document import DocumentAST as active_ast
    from word_parser.document.parser import SectionDetector
    from word_parser.document.section_detector import SectionDetector as active_sections
    from word_parser.extraction.engine import CandidateResolver
    from word_parser.primary.candidate_resolver import CandidateResolver as active_resolver
    from word_parser.extraction.tables import TableValueResolver
    from word_parser.secondary.table_values import TableValueResolver as active_table_values
    from word_parser.extraction.ocr import CoverOcrExtractor
    from word_parser.document.cover_ocr import CoverOcrExtractor as active_ocr
    from word_parser.output.builder import ResultBuilder
    from word_parser.output.result_builder import ResultBuilder as active_builder
    from word_parser.output.schema import REQUIRED_SECTION_SCHEMA
    from word_parser.config.output_schema import REQUIRED_SECTION_SCHEMA as current_schema

    assert DocumentLoader is active_loader
    assert DocumentAST is active_ast
    assert SectionDetector is active_sections
    assert CandidateResolver is active_resolver
    assert TableValueResolver is active_table_values
    assert CoverOcrExtractor is active_ocr
    assert ResultBuilder is active_builder
    assert REQUIRED_SECTION_SCHEMA is current_schema
