"""文档模块的公共导入，延迟加载以避免循环依赖。"""

from importlib import import_module

_EXPORTS = {
    "AsposeWordsLoader": "word_parser.document.word.aspose_loader",
    "DocumentLoader": "word_parser.document.router",
    "OpenDataLoaderPdfLoader": "word_parser.document.pdf.pdf_loader",
    "PdfTextLoader": "word_parser.document.pdf.pdf_loader",
    "SimpleDocxLoader": "word_parser.document.word.simple_docx_loader",
    "WordLoader": "word_parser.document.word.word_loader",
    **{name: "word_parser.document.ast.document" for name in (
        "DocumentAST", "DocumentBlock", "DocumentTable", "TableCell", "TextStyle",
    )},
    **{name: "word_parser.document.ast.evidence" for name in (
        "Candidate", "Extraction", "FieldEvidence", "FieldMatch", "ParsedField",
    )},
    "OpenDataLoaderLayoutSidecar": "word_parser.document.layout_sidecar",
    "SectionDetector": "word_parser.document.section_detector",
    "StructureParser": "word_parser.document.structure_parser",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value
