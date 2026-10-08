"""Word 加载器。"""

from parser_engine.document.loaders.aspose_loader import AsposeWordsLoader
from parser_engine.document.loaders.simple_docx_loader import SimpleDocxLoader
from parser_engine.document.loaders.word_loader import WordLoader

__all__ = ["AsposeWordsLoader", "SimpleDocxLoader", "WordLoader"]
