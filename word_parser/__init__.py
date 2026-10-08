"""Public Word/PDF parsing API; implementations are loaded on demand."""

from importlib import import_module

__all__ = ["create_parser", "enhance_parse_result", "parse_document", "parse_document_with_table_values"]


def __getattr__(name):
    if name in __all__:
        value = getattr(import_module("word_parser.application.api"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
