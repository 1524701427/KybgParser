"""Table operator registry and score parity, using the original extraction behavior."""
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from word_parser.document.ast.document import DocumentTable, TableCell
from word_parser.document.ast.evidence import Candidate, FieldMatch
from word_parser.primary.value_extractor import ValueExtractor

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load(
    (ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8")
)["value_extraction"]


def _table(rows):
    return DocumentTable(
        id="table-1", page=1, order=1, caption="主要技术经济指标",
        section_path=["工程特性表"],
        rows=[
            [TableCell(text, i, j) for j, text in enumerate(row)]
            for i, row in enumerate(rows)
        ],
    )


def _match(config, rows):
    table = _table(rows)
    candidate = Candidate(
        field_code="probe", field_name=config.get("name", "测试指标"),
        source_type="table", text="\n".join(" | ".join(row) for row in rows),
        score=0.8, table_id=table.id, page=table.page,
        section_path=table.section_path, field_config=config,
        meta={"table": table},
    )
    return FieldMatch(candidate=candidate, method="alias", score=1.8)


def _snapshot(extractions):
    return [(item.field_code, item.raw_value, item.value, item.unit,
             item.score, item.method, asdict(item.evidence), item.debug)
            for item in extractions]


@pytest.mark.parametrize("config,rows", [
    (
        {"name": "装机容量", "aliases": ["装机容量"], "value_type": "number",
         "table_lookup": {"row_aliases": ["装机容量"], "column_aliases": ["指标值"]}},
        [["项目", "指标值"], ["装机容量", "200"], ["备注", "不参与抽取"]],
    ),
    (
        {"name": "机组容量", "aliases": ["机组容量"], "value_type": "number",
         "table_aggregate": {"op": "sum", "value_headers": ["容量"]}},
        [["机组", "容量"], ["一号", "3"], ["二号", "5"]],
    ),
    (
        {"name": "测风塔编号", "aliases": ["测风塔编号"], "value_type": "string",
         "table_list": {"column_aliases": ["塔号"], "format": "comma"}},
        [["塔号", "备注"], ["A01", "主塔"], ["A02", "辅塔"]],
    ),
    (
        {"name": "轮毂高度", "aliases": ["轮毂高度"], "value_type": "number",
         "unit_aliases": ["m", "米"]},
        [["轮毂高度", "m", "120"]],
    ),
])
def test_table_extractions_keep_all_values_scores_and_evidence(config, rows):
    match = _match(config, rows)
    legacy = ValueExtractor()
    configured = ValueExtractor(table_header_config=POLICY["table_headers"], value_config=POLICY)
    assert _snapshot(configured._extract_from_table(match)) == _snapshot(legacy._extract_from_table(match))
    assert _snapshot(configured.extract([match])) == _snapshot(legacy.extract([match]))


def test_lookup_success_still_skips_coarse_table_rule():
    config = {
        "name": "装机容量", "aliases": ["装机容量"], "value_type": "number",
        "table_lookup": {"row_aliases": ["装机容量"], "column_aliases": ["指标值"]},
    }
    match = _match(config, [["项目", "指标值"], ["装机容量", "200"]])
    configured = ValueExtractor(table_header_config=POLICY["table_headers"], value_config=POLICY)
    results = configured._extract_from_table(match)
    assert results, "the lookup fixture must actually exercise the short-circuit"
    assert all(item.method != "table_rule" for item in results)
    assert any(item.method == "table_lookup" for item in results)


def test_score_bonuses_and_order_equal_legacy_defaults():
    configured = ValueExtractor(table_header_config=POLICY["table_headers"], value_config=POLICY)
    assert configured.table_operator_order == ValueExtractor.DEFAULT_TABLE_OPERATORS
    assert configured.score_bonuses == ValueExtractor.DEFAULT_SCORE_BONUSES


def test_unapproved_reordering_is_rejected_before_extraction():
    altered = {**POLICY, "table_operator_order": ["table_lookup", "table_list", "table_aggregate"]}
    with pytest.raises(ValueError, match="table_operator_order"):
        ValueExtractor(value_config=altered)
