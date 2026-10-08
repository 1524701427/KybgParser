"""Stable service API, compatible with the original public entry points."""

from word_parser.application.api import create_parser, enhance_parse_result, parse_document, parse_document_with_table_values
from word_parser.application.service import ParserService

__all__ = ["ParserService", "create_parser", "enhance_parse_result", "parse_document", "parse_document_with_table_values"]
