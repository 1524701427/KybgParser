"""Compatibility imports; implementation lives in word_parser.config.output_schema."""

from word_parser.config.output_schema import (
    DEFAULT_CONFIG_ROOT,
    load_default_output_schema,
    section_schema_from_config,
    field_meta_from_config,
    DEFAULT_OUTPUT_SCHEMA,
    SECTION_ORDER,
    REQUIRED_SECTION_SCHEMA,
    REQUIRED_FIELD_META,
)

__all__ = ['DEFAULT_CONFIG_ROOT', 'DEFAULT_OUTPUT_SCHEMA', 'REQUIRED_FIELD_META', 'REQUIRED_SECTION_SCHEMA', 'SECTION_ORDER', 'field_meta_from_config', 'load_default_output_schema', 'section_schema_from_config']
