"""Regression: restore legacy ResultBuilder cell-by-column-label support.

This had been called from civil_land and finance, but was missing from the
composed ResultBuilder MRO; real DOCX parsing raised AttributeError.
"""
from pathlib import Path

from word_parser.output.result_builder import ResultBuilder


ROOT = Path(__file__).resolve().parents[1]


def test_composed_resultbuilder_has_column_alias_cell_lookup():
    builder = ResultBuilder(config_root=ROOT / "configs")
    assert hasattr(builder, "_cell_at_alias")
    header = ["永久性占地项目", "风机基础", "合计"]
    row = ["风机基础", "12.5", "34.50"]
    assert builder._cell_at_alias(header, row, ["风机基础"]) == 12.5
    assert builder._cell_at_alias(header, row, ["合计"]) == 34.5
    assert builder._cell_at_alias(header, row, ["永久性占地项目"]) == "风机基础"


def test_missing_or_short_column_does_not_read_wrong_neighbor():
    builder = ResultBuilder(config_root=ROOT / "configs")
    header = ["项目", "流动资金贷款比例", "贷款年利率"]
    assert builder._cell_at_alias(header, ["风电场", "30%"], ["贷款年利率"]) is None
    assert builder._cell_at_alias(header, ["风电场", "30%"], ["不存在"]) is None
    assert builder._cell_at_alias(header, ["风电场", "30%"], ["流动资金贷款比例"]) == "30%"
    assert builder._cell_at_alias(header, ["风电场", "--", None], ["贷款年利率"]) is None


def test_different_alias_forms_match_existing_find_header_index_semantics():
    builder = ResultBuilder(config_root=ROOT / "configs")
    header = ["名称", "110kV升压站（亩）", "其他"]
    row = ["永久占地", "5.8", "1.2"]
    assert builder._cell_at_alias(header, row, ["升压站", "110kV升压站"]) == 5.8
