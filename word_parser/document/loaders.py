"""Word/PDF document loaders."""

from parser_engine.document.loaders.aspose_loader import AsposeWordsLoader
from parser_engine.document.loaders.document_loader import DocumentLoader
from parser_engine.document.loaders.pdf_loader import OpenDataLoaderPdfLoader, PdfTextLoader
from parser_engine.document.loaders.simple_docx_loader import SimpleDocxLoader
from parser_engine.document.loaders.word_loader import WordLoader

__all__ = [
    "AsposeWordsLoader",
    "DocumentLoader",
    "OpenDataLoaderPdfLoader",
    "PdfTextLoader",
    "SimpleDocxLoader",
    "WordLoader",
]
