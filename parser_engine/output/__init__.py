"""Legacy JSON exporter import."""

from importlib import import_module

__all__ = ["JsonExporter"]


def __getattr__(name):
    if name == "JsonExporter":
        value = getattr(import_module("word_parser.output.json_exporter"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
