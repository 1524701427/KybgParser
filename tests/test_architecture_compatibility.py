"""Compatibility checks for the responsibility-based module migration."""

from importlib import import_module
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "legacy, canonical, names",
    [
        ("parser_engine.api", "word_parser.application.api", (
            "create_parser", "parse_document", "enhance_parse_result",
            "parse_document_with_table_values", "DEFAULT_TABLE_VALUE_CONFIG",
        )),
        ("parser_engine.core.factory", "word_parser.application.factory", ("create_default_parser",)),
        ("parser_engine.core.pipeline", "word_parser.application.pipeline", ("ParserPipeline",)),
        ("parser_engine.core.context", "word_parser.application.context", ("ParseContext",)),
        ("parser_engine.core.service", "word_parser.application.service", ("ParserService",)),
        ("parser_engine.core.config_loader", "word_parser.config.loader", ("ConfigLoader",)),
        ("parser_engine.output.result_builder", "word_parser.output.result_builder", ("ResultBuilder",)),
        ("parser_engine.output.json_exporter", "word_parser.output.json_exporter", ("JsonExporter",)),
        ("parser_engine.output.schema_registry", "word_parser.config.output_schema", (
            "REQUIRED_FIELD_META", "REQUIRED_SECTION_SCHEMA", "SECTION_ORDER",
        )),
        ("parser_engine.tables.table_values.resolver", "word_parser.extraction.table_values.resolver", ("TableValueResolver",)),
        ("parser_engine.tables.table_values", "word_parser.extraction.table_values.files", ("enhance_result_file",)),
    ],
)
def test_legacy_and_canonical_imports_share_one_implementation(legacy, canonical, names):
    old = import_module(legacy)
    new = import_module(canonical)
    for name in names:
        assert getattr(old, name) is getattr(new, name)


def test_public_extraction_exports_remain_available():
    from word_parser import extraction
    from word_parser.extraction import engine, ocr, tables

    for module in (engine, ocr, tables):
        for name in module.__all__:
            # File-oriented helper functions were not exposed by the old package.
            if name in extraction.__all__:
                assert getattr(extraction, name) is getattr(module, name)


@pytest.mark.parametrize("first_import", [
    "word_parser.domains.wind_resource",
    "word_parser.domains.project_overview",
    "word_parser.config.result_defaults",
    "word_parser.output.result_builder",
    "word_parser.extraction.table_values.primitives",
    "parser_engine.tables.table_values.resolver",
])
def test_modules_can_be_imported_first_without_a_cycle(first_import):
    root = Path(__file__).resolve().parents[1]
    script = (
        f"import {first_import}\n"
        "from word_parser import create_parser\n"
        "from parser_engine import create_parser as old_create_parser\n"
        "assert create_parser is old_create_parser\n"
        "from word_parser.extraction import TableValueResolver\n"
        "assert TableValueResolver().enhance_result({'sections': []})"
        "['tableValueExtraction']['summary']['fieldCount'] == 0\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=root,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
