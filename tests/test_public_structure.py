from word_parser.core import create_parser, parse_document, parse_document_with_table_values
from word_parser.document import DocumentAST, DocumentBlock, DocumentLoader, DocumentTable, TableCell
from word_parser.extraction import OriginalTableResolver, StandardTableExtractor, TableValueResolver, ValueExtractor
from word_parser.output import JsonExporter, ResultBuilder
from word_parser.output.schema import REQUIRED_FIELD_META, REQUIRED_SECTION_SCHEMA


def test_legacy_parser_engine_import_paths_remain_compatible():
    from parser_engine.document.layout.opendataloader_sidecar import OpenDataLoaderLayoutSidecar
    from parser_engine.document.sections.section_detector import SectionDetector
    from parser_engine.document.structure.structure_parser import StructureParser
    from parser_engine.extraction.matching.field_matcher import FieldMatcher
    from parser_engine.extraction.normalization.normalizer import Normalizer
    from parser_engine.extraction.pruning.funnel_pruner import FunnelPruner
    from parser_engine.extraction.resolving.candidate_resolver import CandidateResolver
    from parser_engine.extraction.retrieval.candidate_retriever import CandidateRetriever
    from parser_engine.extraction.semantic.semantic_verifier import SemanticVerifier
    from parser_engine.extraction.validation.validator import Validator
    from parser_engine.tables.table_values.resolver import TableValueResolver

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
            SemanticVerifier,
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
