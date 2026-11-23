"""统一文档结构与抽取证据类型。"""

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
from word_parser.document.ast.evidence import Candidate, Extraction, FieldEvidence, FieldMatch, ParsedField

__all__ = [
    "DocumentAST", "DocumentBlock", "DocumentTable", "TableCell", "TextStyle",
    "Candidate", "Extraction", "FieldEvidence", "FieldMatch", "ParsedField",
]
