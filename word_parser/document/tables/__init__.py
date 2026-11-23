"""解析后表格的识别与处理工具。"""

from word_parser.document.tables.dataframe_builder import DataFrameBuilder
from word_parser.document.tables.original_table_resolver import OriginalTableResolver
from word_parser.document.tables.standard_table_extractor import StandardTableExtractor

__all__ = ["DataFrameBuilder", "OriginalTableResolver", "StandardTableExtractor"]
