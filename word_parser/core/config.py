"""Backward-compatible configuration imports."""

from word_parser.config.loader import ConfigLoader
from word_parser.logger import logger

__all__ = ["ConfigLoader", "logger"]
