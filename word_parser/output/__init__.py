"""Business result assembly and JSON export."""

from importlib import import_module

__all__ = ["JsonExporter", "ResultBuilder"]


def __getattr__(name):
    if name in __all__:
        module = "word_parser.output.result_builder" if name == "ResultBuilder" else "word_parser.output.json_exporter"
        value = getattr(import_module(module), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
