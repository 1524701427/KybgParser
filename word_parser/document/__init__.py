"""Document loading, unified document model and structure parsing."""

from word_parser.document.loaders import AsposeWordsLoader, DocumentLoader, OpenDataLoaderPdfLoader, PdfTextLoader, SimpleDocxLoader, WordLoader
from word_parser.document.model import (
    Candidate,
    DocumentAST,
    DocumentBlock,
    DocumentTable,
    Extraction,
    FieldEvidence,
    FieldMatch,
    ParsedField,
    TableCell,
    TextStyle,
)
from word_parser.document.parser import OpenDataLoaderLayoutSidecar, SectionDetector, StructureParser

__all__ = [
    "AsposeWordsLoader",
    "Candidate",
    "DocumentAST",
    "DocumentBlock",
    "DocumentLoader",
    "DocumentTable",
    "Extraction",
    "FieldEvidence",
    "FieldMatch",
    "OpenDataLoaderLayoutSidecar",
    "OpenDataLoaderPdfLoader",
    "ParsedField",
    "PdfTextLoader",
    "SectionDetector",
    "SimpleDocxLoader",
    "StructureParser",
    "TableCell",
    "TextStyle",
    "WordLoader",
]
