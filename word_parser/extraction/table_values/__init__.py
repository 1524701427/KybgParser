"""Configuration-driven table value extraction and compatibility file APIs."""

from word_parser.extraction.table_values.resolver import TableValueResolver
from word_parser.extraction.table_values.files import default_table_value_details_path, enhance_result_file
from word_parser.extraction.table_values.presentation import compact_table_value_result, final_result_with_table_values, table_value_details

__all__ = ["TableValueResolver", "compact_table_value_result", "default_table_value_details_path", "enhance_result_file", "final_result_with_table_values", "table_value_details"]
