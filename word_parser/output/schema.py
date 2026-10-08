"""Output schema accessors backed by ``configs/output_schema.yaml``."""

from parser_engine.output.result_builder import ResultBuilder
from parser_engine.output.schema_registry import REQUIRED_FIELD_META, REQUIRED_SECTION_SCHEMA, SECTION_ORDER

TABLE_OUTPUT_HEADERS = ResultBuilder.TABLE_OUTPUT_HEADERS

__all__ = [
    "REQUIRED_FIELD_META",
    "REQUIRED_SECTION_SCHEMA",
    "SECTION_ORDER",
    "TABLE_OUTPUT_HEADERS",
]
