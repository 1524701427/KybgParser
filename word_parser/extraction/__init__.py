"""Public extraction capabilities; legacy imports stay available on demand."""

from importlib import import_module

_EXPORTS = {
    **{name: ("word_parser.extraction.engine", name) for name in (
        "BgeEmbeddingMatcher", "CandidateResolver", "CandidateRetriever", "FieldMatcher",
        "FunnelPruner", "GlobalPointerExtractor", "Normalizer", "SemanticAnalyzer",
        "SemanticVerifier", "UIEExtractor", "Validator", "ValueExtractor",
    )},
    "CoverOcrExtractor": ("word_parser.extraction.ocr", "CoverOcrExtractor"),
    "CoverOcrResult": ("word_parser.extraction.ocr", "CoverOcrResult"),
    "DataFrameBuilder": ("parser_engine.tables.dataframe_builder", "DataFrameBuilder"),
    "OriginalTableResolver": ("parser_engine.tables.original_table_resolver", "OriginalTableResolver"),
    "StandardTableExtractor": ("parser_engine.tables.standard_table_extractor", "StandardTableExtractor"),
    "TableValueResolver": ("word_parser.extraction.table_values.resolver", "TableValueResolver"),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        module, attribute = _EXPORTS[name]
        value = getattr(import_module(module), attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
