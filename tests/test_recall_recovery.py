"""验证缺失章节归属和候选被拒绝后的保守补漏。"""

import re

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.document.ast.evidence import Extraction, FieldEvidence
from word_parser.primary.candidate_retriever import CandidateRetriever
from word_parser.application.factory import create_default_parser
from word_parser.config.loader import ConfigLoader


def test_alias_recall_keeps_unsectioned_evidence_but_rejects_other_section():
    configs = {
        "installedCapacity": {
            "name": "装机容量",
            "aliases": ["总装机容量"],
            "sections": {"include": ["工程概况"], "exclude": ["财务"]},
        }
    }
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="heading", type="paragraph", text="财务说明", order=0,
                          section_path=["财务"]),
            DocumentBlock(id="orphan", type="paragraph", text="总装机容量为200MW", order=1),
            DocumentBlock(id="other", type="paragraph", text="总装机容量为300MW", order=2,
                          section_path=["其他章节"]),
        ],
        tables=[DocumentTable(id="orphan_table", order=3, rows=[
            [TableCell("总装机容量", 0, 0), TableCell("200", 0, 1)],
        ])],
    )

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert {item.block_id for item in candidates if item.source_type == "paragraph"} == {"orphan"}
    assert {item.table_id for item in candidates if item.source_type == "table"} == {"orphan_table"}


def test_rejected_rule_candidate_allows_indicator_fallback(tmp_path):
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="capacity_table", order=0, page=2, rows=[
            [TableCell("项目总装机容量", 0, 0), TableCell("MW", 0, 1), TableCell("200", 0, 2)],
        ],
    )])

    class StaticLoader:
        @staticmethod
        def load(_path):
            return ast

    parser = create_default_parser()
    parser.pipeline.loader = StaticLoader()
    parser.pipeline.exporter.output_dir = tmp_path
    parser.pipeline.value_extractor.extract = lambda _matches: [Extraction(
        field_code="installedCapacity", field_name="装机容量", raw_value="5", value="5",
        unit="MW", score=3.0, method="regex",
        evidence=FieldEvidence(source_type="paragraph", text="单机容量为5MW。", page=1),
    )]

    result = parser.parse("sample.pdf")

    assert result["fields"]["installedCapacity"]["value"] == 200
    assert result["fields"]["installedCapacity"]["status"] == "PASS"


def test_new_installed_capacity_alias_preserves_wan_kw_unit():
    config = ConfigLoader("configs").load_field_configs()["installedCapacity"]
    match = re.search(config["patterns"][0], "总装机规模为10万千瓦")

    assert match is not None
    assert match.group(1) == "10"
    assert match.group(2) == "万千瓦"
