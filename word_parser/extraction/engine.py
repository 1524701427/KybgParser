"""Compatibility exports for the active, deterministic primary extraction engine.

Optional ML/experimental operators from the retired parser_engine are not in
the production pipeline; the canonical components live in word_parser.primary.
"""

from word_parser.primary.candidate_resolver import CandidateResolver
from word_parser.primary.candidate_retriever import CandidateRetriever
from word_parser.primary.field_matcher import FieldMatcher
from word_parser.primary.funnel_pruner import FunnelPruner
from word_parser.primary.normalizer import Normalizer
from word_parser.primary.semantic_analyzer import SemanticAnalyzer
from word_parser.primary.validator import Validator
from word_parser.primary.value_extractor import ValueExtractor

__all__ = ["CandidateResolver", "CandidateRetriever", "FieldMatcher", "FunnelPruner", "Normalizer", "SemanticAnalyzer", "Validator", "ValueExtractor"]
