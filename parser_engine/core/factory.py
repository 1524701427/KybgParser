"""Compatibility imports; implementation lives in word_parser.application.factory."""

from word_parser.application.factory import (
    create_default_parser,
    _module_active,
    _warmup_ml_imports,
)

__all__ = ['create_default_parser']
