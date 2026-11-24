"""Backward-compatible document AST and evidence exports."""

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
from word_parser.document.ast.evidence import Candidate, Extraction, FieldEvidence, FieldMatch, ParsedField

__all__ = ["Candidate", "DocumentAST", "DocumentBlock", "DocumentTable", "Extraction", "FieldEvidence", "FieldMatch", "ParsedField", "TableCell", "TextStyle"]
