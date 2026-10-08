"""Compatibility imports; implementation lives in word_parser.application.api."""

from word_parser.application.api import (
    DEFAULT_TABLE_VALUE_CONFIG,
    create_parser,
    parse_document,
    enhance_parse_result,
    parse_document_with_table_values,
)

__all__ = ['DEFAULT_TABLE_VALUE_CONFIG', 'create_parser', 'parse_document', 'enhance_parse_result', 'parse_document_with_table_values']
