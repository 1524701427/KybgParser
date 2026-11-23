"""保留历史公共抽取导入路径，按需加载当前模块中的实现。"""

from importlib import import_module

_EXPORTS = {
    **{name: (f"word_parser.primary.{module}", name) for name, module in {
        "CandidateResolver": "candidate_resolver",
        "CandidateRetriever": "candidate_retriever",
        "FieldMatcher": "field_matcher",
        "FunnelPruner": "funnel_pruner",
        "Normalizer": "normalizer",
        "SemanticAnalyzer": "semantic_analyzer",
        "Validator": "validator",
        "ValueExtractor": "value_extractor",
    }.items()},
    "CoverOcrExtractor": ("word_parser.document.cover_ocr", "CoverOcrExtractor"),
    "CoverOcrResult": ("word_parser.document.cover_ocr", "CoverOcrResult"),
    "DataFrameBuilder": ("word_parser.document.tables.dataframe_builder", "DataFrameBuilder"),
    "OriginalTableResolver": ("word_parser.document.tables.original_table_resolver", "OriginalTableResolver"),
    "StandardTableExtractor": ("word_parser.document.tables.standard_table_extractor", "StandardTableExtractor"),
    "TableValueResolver": ("word_parser.secondary.table_values.resolver", "TableValueResolver"),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        module, attribute = _EXPORTS[name]
        value = getattr(import_module(module), attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
