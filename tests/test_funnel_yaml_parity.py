"""Legacy Top-K rule-first retention must not change with YAML injection."""
from pathlib import Path

import yaml

from word_parser.document.ast.evidence import Extraction, FieldEvidence
from word_parser.primary.funnel_pruner import FunnelPruner

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load(
    (ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8")
)["funnel"]


def _extraction(method, score, value):
    return Extraction(
        field_code="turbineCount", field_name="风机台数",
        raw_value=str(value), value=value, unit="台", score=score,
        method=method, evidence=FieldEvidence(
            source_type="table", text=f"风机台数：{value}", score=score,
        ),
    )


def _ranked_result(pruner):
    candidates = [
        _extraction("regex_fallback", 8.0, 40),
        _extraction("table_lookup", 7.5, 42),
        _extraction("table_list", 6.0, 41),
    ]
    return [(item.method, item.value, item.score)
            for item in pruner.prune_extractions(candidates, stage="post_extraction")]


def test_configured_funnel_preserves_rule_first_candidate():
    field_configs = {"turbineCount": {"extraction_policy": "rule_first"}}
    old = FunnelPruner(enabled=True, stages={"post_extraction": 1}, field_configs=field_configs)
    new = FunnelPruner(
        enabled=True, stages={"post_extraction": 1}, field_configs=field_configs,
        strong_extraction_methods=POLICY["strong_extraction_methods"],
    )
    assert set(POLICY["strong_extraction_methods"]) == old.STRONG_EXTRACTION_METHODS
    assert _ranked_result(old) == _ranked_result(new)
    assert _ranked_result(new) == [("table_lookup", 42, 7.5)]


def test_configured_funnel_preserves_normal_score_order():
    field_configs = {"turbineCount": {"extraction_policy": "score"}}
    old = FunnelPruner(enabled=True, stages={"post_extraction": 1}, field_configs=field_configs)
    new = FunnelPruner(
        enabled=True, stages={"post_extraction": 1}, field_configs=field_configs,
        strong_extraction_methods=POLICY["strong_extraction_methods"],
    )
    assert _ranked_result(old) == _ranked_result(new)
    assert _ranked_result(new) == [("regex_fallback", 40, 8.0)]
