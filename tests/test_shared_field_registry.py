"""Safely share a single alias/RapidFuzz registry without changing legacy matching."""

import yaml
from pathlib import Path

from word_parser.application.factory import create_default_parser
from word_parser.discovery.indicators import IndicatorLexicon
from word_parser.document.ast.evidence import Candidate
from word_parser.primary.field_matcher import FieldMatcher


ROOT = Path(__file__).resolve().parents[1]


def test_application_reuses_one_lexicon_instance():
    service = create_default_parser(config_root=ROOT / "configs")
    pipeline = service.pipeline
    assert pipeline.indicator_discovery is not None
    assert pipeline.field_matcher.lexicon is pipeline.indicator_discovery.lexicon
    assert pipeline.field_matcher.lexicon.match("轮毂高度") == (
        pipeline.indicator_discovery.lexicon.match("轮毂高度")
    )


def test_shared_lexicon_does_not_change_primary_match_scores():
    field_configs = {
        "hubHeight": {"name": "轮毂高度", "aliases": ["轮毂高度"]},
        "installedCapacity": {"name": "装机容量", "aliases": ["装机容量", "总装机容量"]},
    }
    settings = yaml.safe_load(
        (ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8")
    )
    shared = IndicatorLexicon(field_configs, matching_config=settings["discovery"]["rapidfuzz"])
    candidate = Candidate(
        field_code="hubHeight", field_name="轮毂高度",
        source_type="paragraph", text="风机轮毂高度为120米", score=0.5,
        field_config=field_configs["hubHeight"],
    )
    legacy = FieldMatcher(settings["field_matching"]).match([candidate])
    shared_matcher = FieldMatcher(settings["field_matching"], lexicon=shared)
    assert shared_matcher.match([candidate]) == legacy
    assert shared_matcher.inspect_label("轮毂高度") == ("hubHeight", "dictionary", 100.0)
    assert FieldMatcher().inspect_label("轮毂高度") == (None, None, 0.0)


def test_ambiguous_alias_never_autoselects_business_code():
    registry = IndicatorLexicon({
        "a": {"name": "甲", "aliases": ["规划容量"]},
        "b": {"name": "乙", "aliases": ["规划容量"]},
    })
    assert registry.match_dictionary("规划容量") == (None, "ambiguous", 100.0)
    assert FieldMatcher(lexicon=registry).inspect_label("规划容量") == (
        None, "ambiguous", 100.0
    )
