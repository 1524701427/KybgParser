"""Backward-compatible Word/PDF loader exports."""

from word_parser.document.word.aspose_loader import AsposeWordsLoader
from word_parser.document.router import DocumentLoader
from word_parser.document.pdf.pdf_loader import OpenDataLoaderPdfLoader, PdfTextLoader
from word_parser.document.word.simple_docx_loader import SimpleDocxLoader
from word_parser.document.word.word_loader import WordLoader

__all__ = ["AsposeWordsLoader", "DocumentLoader", "OpenDataLoaderPdfLoader", "PdfTextLoader", "SimpleDocxLoader", "WordLoader"]
