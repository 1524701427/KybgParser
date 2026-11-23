"""公共入口与实际模块的导入检查。"""

from importlib import import_module
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "public_module, implementation_module, names",
    [
        ("word_parser.core", "word_parser.application.api", (
            "create_parser", "parse_document", "enhance_parse_result",
            "parse_document_with_table_values",
        )),
        ("word_parser.document", "word_parser.document.ast.document", ("DocumentAST",)),
        ("word_parser.document", "word_parser.document.router", ("DocumentLoader",)),
        ("word_parser.output", "word_parser.output.result_builder", ("ResultBuilder",)),
        ("word_parser.output", "word_parser.output.json_exporter", ("JsonExporter",)),
        ("word_parser.extraction", "word_parser.primary.value_extractor", ("ValueExtractor",)),
        ("word_parser.extraction", "word_parser.secondary.table_values.resolver", ("TableValueResolver",)),
        ("word_parser.extraction", "word_parser.document.tables", ("StandardTableExtractor",)),
    ],
)
def test_public_imports_share_one_implementation(public_module, implementation_module, names):
    old = import_module(public_module)
    new = import_module(implementation_module)
    for name in names:
        assert getattr(old, name) is getattr(new, name)


def test_public_extraction_exports_remain_available():
    from word_parser import extraction

    assert all(getattr(extraction, name) is not None for name in extraction.__all__)


@pytest.mark.parametrize("first_import", [
    "word_parser.domains.wind_resource",
    "word_parser.domains.project_overview",
    "word_parser.config.result_defaults",
    "word_parser.output.result_builder",
    "word_parser.secondary.table_values.primitives",
    "word_parser.secondary.table_values.resolver",
])
def test_modules_can_be_imported_first_without_a_cycle(first_import):
    root = Path(__file__).resolve().parents[1]
    script = (
        f"import {first_import}\n"
        "from word_parser import create_parser\n"
        "from word_parser.core import create_parser as core_create_parser\n"
        "assert create_parser is core_create_parser\n"
        "from word_parser.extraction import TableValueResolver\n"
        "assert TableValueResolver().enhance_result({'sections': []})"
        "['tableValueExtraction']['summary']['fieldCount'] == 0\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=root,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
