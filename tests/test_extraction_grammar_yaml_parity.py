"""Value and indicator grammar equivalence: injected YAML vs previous Python defaults."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from word_parser.discovery.indicators import IndicatorDiscovery, IndicatorValueParser
from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.primary.value_extractor import ValueExtractor

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8"))


def test_preextraction_regex_sources_and_parsing_match_legacy():
    default = IndicatorValueParser()
    configured = IndicatorValueParser(CFG["discovery"])
    assert configured.NUMBER_CELL.pattern == default.NUMBER_CELL.pattern
    assert configured.column_header_unit_pattern.pattern == default.column_header_unit_pattern.pattern
    assert configured.paragraph_clause_pattern.pattern == default.paragraph_clause_pattern.pattern
    assert configured.two_cell_text_max_length == default.two_cell_text_max_length
    assert configured.two_cell_value_exclusions == default.two_cell_value_exclusions
    lines = (
        "装机容量：200MW；轮毂高度：120m",
        "发电小时数：2,500h；风机台数：40台",
        "年平均风速为6.5m/s，总装机容量为100MW",
        "参考意见：依据工程概况；备注：待核对",
    )
    for line in lines:
        assert configured.parse_paragraph_pairs(line) == default.parse_paragraph_pairs(line)
        assert configured.parse_paragraph(line) == default.parse_paragraph(line)
    rows = (
        ["轮毂高度", "m", "120", "装机容量", "MW", "200"],
        ["风机台数", "40", "总装机容量", "200"],
        ["项目", "数值", "备注"],
    )
    for row in rows:
        assert configured.parse_table_pairs(row) == default.parse_table_pairs(row)
        assert configured.parse_table_row(row) == default.parse_table_row(row)
    for headers in (["风机", "轮毂高度(m)", "总装机容量（MW）", "备注"],
                    ["指标", "风机台数", "平均风速(m/s)"]):
        assert configured.parse_column_headers(headers) == default.parse_column_headers(headers)


def test_value_extractor_heading_and_window_match_legacy():
    default = ValueExtractor()
    configured = ValueExtractor(
        table_header_config=CFG["value_extraction"]["table_headers"],
        value_config=CFG["value_extraction"],
    )
    assert configured.number_near_alias_window == default.number_near_alias_window == 80
    assert configured.heading_exclusion_patterns == default.heading_exclusion_patterns
    assert configured.heading_value_markers == default.heading_value_markers
    assert configured.table_group_header_max_cells == default.table_group_header_max_cells
    fields = {"name": "总装机容量", "aliases": ["总装机容量"], "value_type": "number"}
    for text in (
        "1.2 章节标题 100MW",
        "总装机容量为200MW。",
        "2-3 风机参数表",
        "总装机容量为 20 万千瓦",
        "总装机容量：100MW；单机容量5MW",
    ):
        assert configured._number_near_alias(text, fields) == default._number_near_alias(text, fields)
        for value in ("1", "20", "200"):
            assert configured._looks_like_heading_number(text, value, fields) == default._looks_like_heading_number(text, value, fields)
    for tokens in (["风机型号"], ["工程信息", "土建工程"], ["总装机容量", "200"]):
        row = [SimpleNamespace(text=token) for token in tokens]
        assert configured._looks_like_header_or_group_row(row) == default._looks_like_header_or_group_row(row)


def test_discovery_source_facts_match_with_configured_grammar():
    fields = {
        "installedCapacity": {"name": "总装机容量", "aliases": ["总装机容量"]},
        "hubHeight": {"name": "轮毂高度", "aliases": ["轮毂高度"]},
    }
    ast = DocumentAST(
        file_name="regression.docx",
        blocks=[
            DocumentBlock("a", "paragraph", "总装机容量为200MW。", 0),
            DocumentBlock("b", "paragraph", "轮毂高度：120m；总装机容量：200MW", 1),
        ],
        tables=[
            DocumentTable(id="t", order=2, page=1, rows=[
                [TableCell("风机台数", 0, 0), TableCell("40", 0, 1)],
                [TableCell("轮毂高度", 1, 0), TableCell("m", 1, 1), TableCell("120", 1, 2)],
            ])
        ],
    )
    legacy = IndicatorDiscovery(fields)
    configured = IndicatorDiscovery(fields, settings=CFG["discovery"])
    assert [x.to_dict() for x in configured.discover_raw(ast)] == [
        x.to_dict() for x in legacy.discover_raw(ast)
    ]
    assert configured.contextual_clause_pattern.pattern == legacy.contextual_clause_pattern.pattern
    assert configured.contextual_label_min_length == legacy.contextual_label_min_length
    assert configured.contextual_prefix_guard_chars == legacy.contextual_prefix_guard_chars
