"""Backward-compatible structure, layout and section exports."""

from word_parser.document.layout_sidecar import LayoutTable, OpenDataLoaderLayoutSidecar
from word_parser.document.section_detector import SectionDetector
from word_parser.document.structure_parser import StructureParser

__all__ = ["LayoutTable", "OpenDataLoaderLayoutSidecar", "SectionDetector", "StructureParser"]
