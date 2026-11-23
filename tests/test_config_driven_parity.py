"""Parity checks for YAML-based extraction defaults (no document/OCR required)."""
from pathlib import Path

import yaml

from word_parser.discovery.indicators import IndicatorDiscovery, IndicatorValueParser, IndicatorLexicon
from word_parser.primary.value_extractor import ValueExtractor
from word_parser.primary.candidate_resolver import CandidateResolver
from word_parser.primary.normalizer import Normalizer
from word_parser.primary.field_matcher import FieldMatcher


ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8"))


def test_table_header_config_equals_legacy_defaults():
    spec = CONFIG["value_extraction"]["table_headers"]
    assert tuple(spec["value"]) == ValueExtractor.VALUE_HEADER_KEYWORDS
    assert tuple(spec["unit"]) == ValueExtractor.UNIT_HEADER_KEYWORDS
    assert tuple(spec["noise"]) == ValueExtractor.NOISE_HEADER_KEYWORDS
    configured = ValueExtractor(table_header_config=spec)
    assert configured.VALUE_HEADER_KEYWORDS == ValueExtractor.VALUE_HEADER_KEYWORDS
    assert configured.UNIT_HEADER_KEYWORDS == ValueExtractor.UNIT_HEADER_KEYWORDS
    assert configured.NOISE_HEADER_KEYWORDS == ValueExtractor.NOISE_HEADER_KEYWORDS


def test_unit_alias_map_equals_legacy_defaults():
    mapping = CONFIG["normalization"]["unit_aliases"]
    assert mapping == Normalizer.UNIT_MAP
    configured = Normalizer(unit_map=mapping)
    assert configured.UNIT_MAP == Normalizer.UNIT_MAP


def test_indicator_discovery_defaults_match_prior_behavior():
    options = CONFIG["discovery"]
    configured = IndicatorDiscovery({}, settings=options)
    legacy = IndicatorDiscovery({})
    assert configured.SCOPE_TERMS == legacy.SCOPE_TERMS
    assert configured.CONTEXT_VALUE.pattern == legacy.CONTEXT_VALUE.pattern
    assert configured.value_parser.NON_INDICATOR_LABELS == legacy.value_parser.NON_INDICATOR_LABELS
    assert configured.value_parser.column_header_exclusions == legacy.value_parser.column_header_exclusions
    assert configured.safe_fallback_min_label_length == 8
    assert configured.lexicon.matching_config["acceptance_score"] == 92
    assert configured.lexicon.matching_config["minimum_competing_gap"] == 8
    assert IndicatorValueParser(options).label_allowed("装机容量")
    assert not IndicatorValueParser(options).label_allowed("序号")


def test_scoring_config_equals_prior_behavior():
    expected_weights = {
        "table_lookup": 1.2,
        "table_rule": 0.55,
        "table_aggregate": 1.0,
        "table_list": 0.9,
        "regex": 0.15,
        "regex_multi": 0.05,
        "regex_derived": 0.25,
        "regex_fallback": -1.2,
    }
    resolved = CandidateResolver({}, CONFIG["candidate_resolution"])
    assert resolved.method_weights == expected_weights
    assert resolved.STRONG_RULE_METHODS == CandidateResolver.STRONG_RULE_METHODS
    assert FieldMatcher(CONFIG["field_matching"]).alias_bonus == FieldMatcher().alias_bonus == 1.0
