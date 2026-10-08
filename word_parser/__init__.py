"""Simplified public package for the Word/PDF parser.

The implementation still lives in ``parser_engine`` during the compatibility
migration. New code should import from this package's four coarse modules:
``document``, ``extraction``, ``output`` and ``core``.
"""

from word_parser.core import create_parser, enhance_parse_result, parse_document, parse_document_with_table_values

__all__ = [
    "create_parser",
    "enhance_parse_result",
    "parse_document",
    "parse_document_with_table_values",
]
