"""Output schema accessors backed by ``configs/output_schema.yaml``."""

from word_parser.output.result_builder import ResultBuilder
from word_parser.config.output_schema import REQUIRED_FIELD_META, REQUIRED_SECTION_SCHEMA, SECTION_ORDER

TABLE_OUTPUT_HEADERS = ResultBuilder.TABLE_OUTPUT_HEADERS

__all__ = [
    "REQUIRED_FIELD_META",
    "REQUIRED_SECTION_SCHEMA",
    "SECTION_ORDER",
    "TABLE_OUTPUT_HEADERS",
]
