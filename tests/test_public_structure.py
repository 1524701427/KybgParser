from word_parser.core import create_parser, parse_document, parse_document_with_table_values
from word_parser.document import DocumentAST, DocumentBlock, DocumentLoader, DocumentTable, TableCell
from word_parser.extraction import OriginalTableResolver, StandardTableExtractor, TableValueResolver, ValueExtractor
from word_parser.output import JsonExporter, ResultBuilder
from word_parser.config.output_schema import REQUIRED_FIELD_META, REQUIRED_SECTION_SCHEMA


def test_modular_import_paths_are_available():
    from word_parser.document.layout_sidecar import OpenDataLoaderLayoutSidecar
    from word_parser.document.section_detector import SectionDetector
    from word_parser.document.structure_parser import StructureParser
    from word_parser.primary.field_matcher import FieldMatcher
    from word_parser.primary.normalizer import Normalizer
    from word_parser.primary.funnel_pruner import FunnelPruner
    from word_parser.primary.candidate_resolver import CandidateResolver
    from word_parser.primary.candidate_retriever import CandidateRetriever
    from word_parser.primary.validator import Validator
    from word_parser.secondary.table_values.resolver import TableValueResolver

    assert all(
        item is not None
        for item in (
            OpenDataLoaderLayoutSidecar,
            SectionDetector,
            StructureParser,
            FieldMatcher,
            Normalizer,
            FunnelPruner,
            CandidateResolver,
            CandidateRetriever,
            Validator,
            TableValueResolver,
        )
    )


def test_simplified_public_imports_are_available():
    assert create_parser is not None
    assert parse_document is not None
    assert parse_document_with_table_values is not None
    assert DocumentAST is not None
    assert DocumentBlock is not None
    assert DocumentLoader is not None
    assert DocumentTable is not None
    assert TableCell is not None
    assert OriginalTableResolver is not None
    assert StandardTableExtractor is not None
    assert TableValueResolver is not None
    assert ValueExtractor is not None
    assert JsonExporter is not None
    assert ResultBuilder is not None
    assert "财务" in REQUIRED_SECTION_SCHEMA
    assert "projectName" in REQUIRED_FIELD_META
    assert "windTurbineUnitPrice" in REQUIRED_SECTION_SCHEMA["技经概算"]["fields"]
    assert REQUIRED_FIELD_META["windTurbineUnitPrice"] == ("风机单价", "万元")
