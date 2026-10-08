"""文档读取、结构识别和章节定位。"""

from parser_engine.document.ast import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
from parser_engine.document.loaders import AsposeWordsLoader, SimpleDocxLoader, WordLoader
from parser_engine.document.section_detector import SectionDetector
from parser_engine.document.structure_parser import StructureParser

__all__ = [
    "DocumentAST",
    "DocumentBlock",
    "DocumentTable",
    "TableCell",
    "TextStyle",
    "AsposeWordsLoader",
    "SimpleDocxLoader",
    "WordLoader",
    "SectionDetector",
    "StructureParser",
]
