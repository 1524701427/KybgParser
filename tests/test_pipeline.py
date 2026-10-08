"""解析流水线基础测试。"""

from __future__ import annotations

import json
import re
import sys
import types

from parser_engine.document.ast.document import DocumentAST, DocumentBlock
from parser_engine.document.ast.document import DocumentTable, TableCell
from parser_engine.document.ast.evidence import Candidate, Extraction, FieldEvidence, FieldMatch, ParsedField
from parser_engine.core.factory import create_default_parser
from parser_engine.core.config_loader import ConfigLoader
from parser_engine.extraction.uie_extractor import UIEExtractor
from parser_engine.extraction.value_extractor import ValueExtractor
from parser_engine.extraction import FieldMatcher
from parser_engine.ml.embedding_model import BgeEmbeddingMatcher
from parser_engine.extraction import CandidateResolver, FunnelPruner, Normalizer, SemanticAnalyzer, SemanticVerifier
from parser_engine.extraction.semantic_verifier import OnnxReranker
from parser_engine.tables import StandardTableExtractor
from parser_engine.extraction import CandidateRetriever
from parser_engine.document import SectionDetector, StructureParser
from parser_engine.output.json_exporter import JsonExporter
from parser_engine.output.result_builder import ResultBuilder
from parser_engine.output.cover_ocr import CoverOcrExtractor, CoverOcrResult
from tools.evaluation.metrics import FieldMetrics
from parser_engine.core.context import ParseContext


def test_candidate_retriever_with_alias():
    """验证 alias 能召回候选段落。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p_0001",
                type="paragraph",
                text="本项目轮毂高度平均风速为6.42m/s。",
                order=1,
                section_path=["风资源"],
            )
        ],
    )
    configs = {
        "avgWindSpeed": {
            "name": "平均风速",
            "aliases": ["平均风速"],
            "sections": {"include": ["风资源"], "exclude": []},
        }
    }
    candidates = CandidateRetriever(configs).retrieve(ast)
    assert len(candidates) == 1
    assert candidates[0].field_code == "avgWindSpeed"


def test_common_project_owner_and_address_fields_from_project_overview_config():
    """通用章节新增字段应从投资方和“项目位于”段落抽取。"""
    all_configs = ConfigLoader("configs").load_field_configs()
    field_codes = [
        "investmentOwnerCompany",
        "projectAddressCity",
        "projectAddressCounty",
        "projectAddressTown",
        "projectAddressDetail",
    ]
    field_configs = {code: all_configs[code] for code in field_codes}
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="1.1.2 投资方及项目单位概况",
                order=1,
                section_path=["总论", "投资方及项目单位概况"],
            ),
            DocumentBlock(
                id="b2",
                type="paragraph",
                text="中国华电集团有限公司（ChinaHuadian Corporation）简称中国华电（CHD），成立于2002年12月29日。",
                order=2,
                section_path=["总论", "投资方及项目单位概况"],
            ),
            DocumentBlock(
                id="b3",
                type="paragraph",
                text="陕西华电靖边韩家沟200MW风电项目位于陕西省榆林市靖边县王渠则镇南部韩家沟，距离靖边县城约45km。",
                order=3,
                section_path=["总论", "项目概况"],
            ),
        ],
    )

    candidates = CandidateRetriever(field_configs).retrieve(ast)
    matches = FieldMatcher().match(candidates)
    extractions = ValueExtractor().extract(matches)
    normalized = {field.field_code: field for field in Normalizer(field_configs).normalize(extractions)}

    assert normalized["investmentOwnerCompany"].value == "中国华电集团有限公司"
    assert normalized["projectAddressCity"].value == "榆林市"
    assert normalized["projectAddressCounty"].value == "靖边县"
    assert normalized["projectAddressTown"].value == "王渠则镇"
    assert normalized["projectAddressDetail"].value == "陕西省榆林市靖边县王渠则镇南部韩家沟"


def test_common_project_owner_fallback_uses_nearby_heading_when_section_path_missing():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="b1", type="paragraph", text="1.1.2  投资方及项目单位概况", order=1),
            DocumentBlock(
                id="b2",
                type="paragraph",
                text="中国华电集团有限公司（ChinaHuadian Corporation）简称中国华电（CHD），成立于2002年12月29日。",
                order=2,
            ),
        ],
    )

    overrides = ResultBuilder()._common_project_overview_scalar_override_values(ast)

    assert overrides["investmentOwnerCompany"][1] == "中国华电集团有限公司"


def test_geology_section_extracts_geomorphology_vegetation_and_elevation(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="陕西华电靖边韩家沟200MW风电项目位于榆林市靖边县南部的周河镇，海拔高度在1500m~1600m。",
                order=1,
                section_path=["综合说明", "工程概况"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="工程区位于华北地台西南边陲的陕西北部，属陕甘宁盆地，主要地貌为黄土梁与沟壑相间分布，梁顶地形较为平坦，地势较开阔。",
                order=2,
                section_path=["地勘章节", "地形地貌"],
            ),
            DocumentBlock(
                id="p3",
                type="paragraph",
                text="风电场址中心东经108°33′12.6453″，北纬37°15′7.0416″，海拔高度在1560m~1750m。",
                order=3,
                section_path=["地勘章节", "工程概况"],
            ),
            DocumentBlock(
                id="p4",
                type="paragraph",
                text="地表为荒漠，生长有耐旱植物。",
                order=4,
                section_path=["地勘章节", "机位情况"],
            ),
            DocumentBlock(
                id="p5",
                type="paragraph",
                text="F1风机点位位于农田中，地表为果树，点位距离南侧大棚约45米。F2风机点位位于农田中，地表为果树。",
                order=5,
                section_path=["地勘章节", "机位情况"],
            ),
        ],
        tables=[
            DocumentTable(
                id="t1",
                order=5,
                caption="机位情况表",
                section_path=["地勘章节", "机位情况"],
                rows=[
                    [TableCell(text="机位编号", row=0, col=0), TableCell(text="地表植被", row=0, col=1)],
                    [TableCell(text="F1", row=1, col=0), TableCell(text="果树", row=1, col=1)],
                    [TableCell(text="F2", row=2, col=0), TableCell(text="果树", row=2, col=1)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "地勘章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["projectGeomorphology"]["value"] == "黄土梁与沟壑相间分布"
    assert fields["surfaceVegetationType"]["value"] == "果树"
    assert fields["siteElevationRange"]["value"] == "1560m~1750m"
    assert fields["siteElevationRange"]["unit"] == "m"


def test_candidate_retriever_uses_canonical_section_aliases():
    """验证正文标题别名归一后，可按字段汇总章节优先召回。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p_0001",
                type="paragraph",
                text="轮毂高度处年平均风速为5.21m/s。",
                order=1,
                section_path=["风能资源", "测风资料"],
            )
        ],
    )
    SectionDetector(
        {"sections": {"wind": {"name": "资源章节", "aliases": ["风能资源", "风资源"]}}}
    ).detect(ast)
    configs = {
        "hubHeightAnnualAverageWindSpeed": {
            "name": "轮毂高度年平均风速",
            "aliases": ["年平均风速"],
            "sections": {"include": ["资源章节"], "exclude": []},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert len(candidates) == 1
    assert candidates[0].meta["section_origin"] == "target_section"
    assert candidates[0].section_path[:1] == ["资源章节"]


def test_candidate_retriever_skips_toc_paragraphs():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="toc1",
                type="paragraph",
                text='目录 TOC \\o "1-2" HYPERLINK \\l _Toc1 1.6 电气 PAGEREF _Toc1 5 接入站名称 110kV张洪变电站',
                order=1,
            ),
            DocumentBlock(id="p1", type="paragraph", text="接入站名称 接入站名称 110kV张洪变电站", order=2, section_path=["电气一次"]),
        ],
    )
    configs = {
        "accessStationName": {
            "name": "接入站名称",
            "aliases": ["接入站名称"],
            "sections": {"include": ["电气一次"], "exclude": []},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert [candidate.block_id for candidate in candidates] == ["p1"]


def test_section_detector_inherits_heading_path_for_following_blocks():
    """验证标题之后的段落和表格会继承当前章节路径。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="4. 电气一次", order=1, meta={"structure_type": "heading", "heading_level": 1}),
            DocumentBlock(id="p_0002", type="paragraph", text="主变压器容量为100MVA。", order=2),
            DocumentBlock(id="tb_0001", type="table", text="", order=3, meta={"table_id": "t_0001"}),
        ],
        tables=[
            DocumentTable(id="t_0001", order=3, rows=[[TableCell(text="主变压器", row=0, col=0)]])
        ],
    )

    detected = SectionDetector({"sections": {"electrical_primary": {"name": "电气一次", "aliases": ["电气一次"]}}}).detect(ast)

    assert detected.blocks[1].section_path == ["4. 电气一次"]
    assert detected.tables[0].section_path == ["4. 电气一次"]


def test_section_detector_uses_table_title_as_section_anchor():
    """验证表题能在章节路径丢失时给原表补章节锚点。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="tb1", type="table", text="", order=1, meta={"table_id": "t1"})],
        tables=[DocumentTable(id="t1", order=1, caption="附表 1：财务指标汇总表", section_path=["技经概算"], rows=[[TableCell(text="项目", row=0, col=0)]])],
    )

    detected = SectionDetector({"sections": {"finance": {"name": "财务", "aliases": ["财务"]}}}).detect(ast)

    assert detected.blocks[0].section_path == ["财务"]
    assert detected.tables[0].section_path == ["财务"]
    assert detected.tables[0].meta["canonical_sections"] == ["财务"]


def test_structure_parser_records_multi_source_table_title_candidates():
    """验证结构层会把表题、样式标题和表内首行一起记入候选元信息。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="表 9.5-1 箱变基础单台工程量表（配事故油池）", order=1),
            DocumentBlock(id="tb1", type="table", text="", order=2, meta={"table_id": "t1"}),
        ],
        tables=[
            DocumentTable(
                id="t1",
                order=2,
                rows=[
                    [TableCell(text="表 9.5-1 箱变基础单台工程量表（配事故油池）", row=0, col=0)],
                    [TableCell(text="项目", row=1, col=0), TableCell(text="数值", row=1, col=1)],
                ],
            )
        ],
    )

    structured = StructureParser().parse(ast)

    table = structured.tables[0]
    assert table.caption == "表 9.5-1 箱变基础单台工程量表（配事故油池）"
    assert table.meta["best_title"] == "表 9.5-1 箱变基础单台工程量表（配事故油池）"
    assert table.meta["caption_source"] == "table_caption"
    assert any(candidate["source"] == "table_caption" for candidate in table.meta["title_candidates"])
    assert any("table_first_row" in candidate.get("sources", []) for candidate in table.meta["title_candidates"])


def test_structure_parser_prefers_styled_paragraph_title_for_caption():
    """验证居中加粗的表前标题也能作为表题候选。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="箱变基础单台工程量表",
                order=1,
                style=type("Style", (), {"bold": True, "alignment": "center", "style_name": None})(),
            ),
            DocumentBlock(id="tb1", type="table", text="", order=2, meta={"table_id": "t1"}),
        ],
        tables=[DocumentTable(id="t1", order=2, rows=[[TableCell(text="项目", row=0, col=0), TableCell(text="数值", row=0, col=1)]])],
    )

    structured = StructureParser().parse(ast)

    table = structured.tables[0]
    assert table.caption == "箱变基础单台工程量表"
    assert table.meta["caption_source"] == "styled_title"


def test_structure_parser_uses_layout_title_candidates_before_weak_word_context():
    """验证 PDF layout 候选能参与 Word 表题判定。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本工程财务评价采用资本金财务现金流量表。", order=1),
            DocumentBlock(id="tb1", type="table", text="", order=2, meta={"table_id": "t1"}),
        ],
        tables=[
            DocumentTable(
                id="t1",
                order=2,
                meta={"layout_title_candidates": [{"source": "layout_nearby_title", "text": "附表 1：财务指标汇总表", "score": 5.5}]},
                rows=[[TableCell(text="项目", row=0, col=0), TableCell(text="数值", row=0, col=1)]],
            )
        ],
    )

    structured = StructureParser().parse(ast)

    table = structured.tables[0]
    assert table.caption == "附表 1：财务指标汇总表"
    assert table.meta["caption_source"] == "layout_nearby_title"


def test_original_table_resolver_matches_generalized_finance_and_civil_titles(tmp_path):
    """验证原表 resolver 仍能命中财务、概算、箱变基础和土石方的常见标题变体。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_finance", 1, "附表 1：财务指标汇总表", ["项目", "数值"], ["A", "1"]),
            _table_with_caption("t_investment", 2, "15.3.9.1 主要技术经济指标表", ["项目", "数值"], ["B", "2"]),
            _table_with_caption("t_box", 3, "箱变基础单台工程量表", ["项目", "数值"], ["C", "3"]),
            _table_with_caption("t_earthwork", 4, "土石方平衡表", ["项目", "数值"], ["D", "4"]),
        ],
    )

    detail_json = _detail_sections_for_tables(tmp_path, ast.tables)

    finance = next(section for section in detail_json["sections"] if section["name"] == "财务")
    investment = next(section for section in detail_json["sections"] if section["name"] == "技经概算")
    box = next(section for section in detail_json["sections"] if section["name"] == "箱变基础")
    earthwork = next(section for section in detail_json["sections"] if section["name"] == "土石方平衡")

    assert [table["key"] for table in finance["tables"]] == ["financialIndicatorSummary"]
    assert [table["key"] for table in investment["tables"]] == ["investmentTechnicalEconomicIndicators"]
    assert [table["key"] for table in box["tables"]] == ["boxFoundationTechnical"]
    assert [table["key"] for table in earthwork["tables"]] == ["earthworkBalance"]


def test_default_parser_can_be_created():
    """验证默认解析器可以被代码直接创建。"""
    parser = create_default_parser()
    assert parser is not None


def test_field_matcher_scores_short_alias_hits_with_bge():
    """验证短别名仍会让 BGE 参与消歧。"""

    class FakeBgeMatcher:
        def __init__(self):
            self.scored_candidates = []

        def score_many(self, candidates):
            self.scored_candidates = candidates
            return [0.2] * len(candidates)

    short_alias_candidate = Candidate(
        field_code="collectorCircuitType",
        field_name="loop",
        source_type="paragraph",
        text="loop: single-circuit overhead line",
        score=0.0,
        field_config={"aliases": ["loop"]},
    )
    long_alias_candidate = Candidate(
        field_code="avgWindSpeed",
        field_name="average wind speed",
        source_type="paragraph",
        text="average wind speed is 6.42m/s.",
        score=0.0,
        field_config={"aliases": ["average wind speed"]},
    )
    bge_matcher = FakeBgeMatcher()

    matches = FieldMatcher(bge_matcher=bge_matcher).match([short_alias_candidate, long_alias_candidate])

    assert bge_matcher.scored_candidates == [short_alias_candidate]
    assert [match.method for match in matches] == ["alias+bge", "alias"]
def test_field_matcher_prefers_target_section_candidates_for_bge():
    """验证 BGE 仅优先处理目标章节候选，避免全局候选干扰。"""

    class FakeBgeMatcher:
        def __init__(self):
            self.scored_candidates = []

        def score_many(self, candidates):
            self.scored_candidates = candidates
            return [0.2] * len(candidates)

    target_candidate = Candidate(
        field_code="avgWindSpeed",
        field_name="平均风速",
        source_type="paragraph",
        text="资源章节中的风速为6.42m/s。",
        score=1.0,
        section_path=["资源章节"],
        field_config={"aliases": ["平均风速"]},
        meta={"section_origin": "target_section"},
    )
    fallback_candidate = Candidate(
        field_code="avgWindSpeed",
        field_name="平均风速",
        source_type="paragraph",
        text="摘要中出现的风速为6.10m/s。",
        score=2.0,
        section_path=["摘要"],
        field_config={"aliases": ["平均风速"]},
        meta={"section_origin": "global_fallback"},
    )

    bge_matcher = FakeBgeMatcher()
    matches = FieldMatcher(bge_matcher=bge_matcher).match([target_candidate, fallback_candidate])

    assert bge_matcher.scored_candidates == [target_candidate]
    assert [match.candidate for match in matches if match.method == "bge"] == [target_candidate]


def test_candidate_retriever_uses_section_priority_weight_and_reuses_table_text():
    """验证召回器使用章节权重，并把表格文本预计算到 meta。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p_0001", type="paragraph", text="平均风速为6.42m/s", order=1, section_path=["摘要"])],
        tables=[
            DocumentTable(
                id="t_0001",
                order=2,
                section_path=["风资源"],
                rows=[[TableCell(text="平均风速", row=0, col=0), TableCell(text="m/s", row=0, col=1), TableCell(text="6.42", row=0, col=2)]],
            )
        ],
    )
    configs = {
        "avgWindSpeed": {
            "name": "平均风速",
            "aliases": ["平均风速"],
            "sections": {"include": ["摘要", "风资源"], "exclude": []},
            "source_priority": {"sections": {"摘要": 0.6, "风资源": 1.0}},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    paragraph = next(candidate for candidate in candidates if candidate.source_type == "paragraph")
    table = next(candidate for candidate in candidates if candidate.source_type == "table")
    assert paragraph.score == 1.1
    assert table.score == 1.6
    assert ast.tables[0].meta["table_text"] == "平均风速 | m/s | 6.42"



def test_candidate_retriever_keeps_alias_hits_inside_configured_section():
    """字段配置了章节时，别名命中也不能跨到章节外。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="target section body", order=1, section_path=["风资源"]),
            DocumentBlock(id="p_0002", type="paragraph", text="external paragraph with avgWindSpeed 6.42m/s", order=2, section_path=["其他"]),
        ],
    )
    configs = {
        "avgWindSpeed": {
            "name": "avgWindSpeed",
            "aliases": ["avgWindSpeed"],
            "sections": {"include": ["风资源"], "exclude": []},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert {candidate.block_id for candidate in candidates} == {"p_0001"}


def test_candidate_retriever_allows_alias_global_when_no_section_include():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="external paragraph with avgWindSpeed 6.42m/s", order=1, section_path=["其他"]),
        ],
    )
    configs = {"avgWindSpeed": {"name": "avgWindSpeed", "aliases": ["avgWindSpeed"]}}

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert {candidate.block_id for candidate in candidates} == {"p_0001"}


def test_candidate_retriever_does_not_fallback_to_other_sections_when_document_is_sectioned():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="其他章节 avgWindSpeed 6.42m/s", order=1, section_path=["其他"]),
        ],
    )
    configs = {
        "avgWindSpeed": {
            "name": "avgWindSpeed",
            "aliases": ["avgWindSpeed"],
            "sections": {"include": ["风资源"], "exclude": []},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert candidates == []


def test_candidate_retriever_respects_section_exclude_even_for_alias_hits():
    """验证排除章节不会被别名命中绕过。"""
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="财务评价中出现 avgWindSpeed 6.42m/s", order=1, section_path=["财务评价"]),
            DocumentBlock(id="p_0002", type="paragraph", text="风资源中出现 avgWindSpeed 6.10m/s", order=2, section_path=["风资源"]),
        ],
    )
    configs = {
        "avgWindSpeed": {
            "name": "avgWindSpeed",
            "aliases": ["avgWindSpeed"],
            "sections": {"include": ["风资源"], "exclude": ["财务评价"]},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert {candidate.block_id for candidate in candidates} == {"p_0002"}
def test_bge_batch_encoding_retries_with_smaller_batch_on_memory_error():
    """验证 BGE 批量编码遇到内存不足时会自动降低 batch_size。"""

    class FakeModel:
        def __init__(self):
            self.batch_lengths = []

        def encode(self, texts, **kwargs):
            self.batch_lengths.append(len(texts))
            if len(texts) > 2:
                raise RuntimeError("DefaultCPUAllocator: not enough memory")
            return [f"vector:{text}" for text in texts]

    matcher = BgeEmbeddingMatcher(enabled=True, batch_size=4, memory_aware=False)
    matcher.model = FakeModel()

    vectors = matcher._encode_texts(["a", "b", "c", "d", "e"])

    assert vectors == ["vector:a", "vector:b", "vector:c", "vector:d", "vector:e"]
    assert matcher.model.batch_lengths == [4, 2, 2, 1]


def test_bge_selects_batch_size_from_available_memory():
    """验证 BGE 会根据可用内存动态降低实际批次。"""
    matcher = BgeEmbeddingMatcher(
        enabled=True,
        batch_size=8,
        memory_aware=True,
        memory_safety_ratio=0.5,
        min_free_memory_mb=100,
    )
    matcher._available_memory_bytes = lambda: 300 * 1024 * 1024
    matcher._estimate_encode_memory_bytes = lambda texts: 50 * 1024 * 1024

    assert matcher._select_batch_size(["a"] * 10) == 2


def test_bge_selects_one_batch_when_free_memory_is_below_reserve():
    """验证可用内存低于保留阈值时仍以最小批次继续。"""
    matcher = BgeEmbeddingMatcher(
        enabled=True,
        batch_size=8,
        memory_aware=True,
        min_free_memory_mb=1024,
    )
    matcher._available_memory_bytes = lambda: 512 * 1024 * 1024

    assert matcher._select_batch_size(["a"] * 10) == 1


def test_value_extractor_limits_uie_matches_per_field():
    """验证 UIE 只处理每个字段的高分候选。"""

    class FakeUIE:
        enabled = True
        mode = "active"

    matches = [
        FieldMatch(
            candidate=Candidate(
                field_code="avgWindSpeed",
                field_name="平均风速",
                source_type="paragraph",
                text=f"候选{i}",
                score=0.0,
                field_config={"extractors": {"uie": True}},
            ),
            method="section",
            score=float(i),
        )
        for i in range(4)
    ]

    extractor = ValueExtractor(uie_extractor=FakeUIE(), uie_top_k_per_field=2)

    selected = extractor._select_uie_matches(matches)

    assert [match.score for match in selected] == [3.0, 2.0]


def test_value_extractor_uses_uie_batch_interface_when_available():
    """验证 ValueExtractor 优先调用 UIE 批量接口。"""

    class FakeUIE:
        enabled = True
        mode = "active"
        release_after_extract = False

        def __init__(self):
            self.batch_sizes = []

        def extract_many(self, matches):
            self.batch_sizes.append(len(matches))
            return []

    matches = [
        FieldMatch(
            candidate=Candidate(
                field_code="avgWindSpeed",
                field_name="平均风速",
                source_type="paragraph",
                text="平均风速为6.42m/s",
                score=0.0,
                field_config={"extractors": {"uie": True}},
            ),
            method="alias",
            score=2.0,
        )
        for _ in range(3)
    ]
    fake_uie = FakeUIE()

    ValueExtractor(uie_extractor=fake_uie, uie_top_k_per_field=2).extract(matches)

    assert fake_uie.batch_sizes == [2]


def test_value_extractor_respects_regex_switch_and_reads_table_neighbor_cell():
    """验证抽值器尊重正则开关，并从别名单元格右侧读取表格值。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [
                TableCell(text="1", row=0, col=0),
                TableCell(text="平均风速", row=0, col=1),
                TableCell(text="m/s", row=0, col=2),
                TableCell(text="6.42", row=0, col=3),
                TableCell(text="备注2026", row=0, col=4),
            ]
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="avgWindSpeed",
            field_name="平均风速",
            source_type="table",
            text="平均风速 | m/s | 6.42 | 备注2026",
            score=1.0,
            table_id="t_0001",
            field_config={"aliases": ["平均风速"], "unit_aliases": ["m/s"], "standard_unit": "m/s"},
            meta={"table": table},
        ),
        method="alias",
        score=2.0,
    )

    extracted = ValueExtractor(regex_enabled=False).extract([match])

    assert len(extracted) == 1
    assert extracted[0].raw_value == "6.42"
    assert extracted[0].unit == "m/s"


def test_value_extractor_prefers_value_header_over_remark_number():
    """验证表格抽值优先读取指标值列，不被备注列中的数字干扰。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [
                TableCell(text="序号", row=0, col=0),
                TableCell(text="指标名称", row=0, col=1),
                TableCell(text="单位", row=0, col=2),
                TableCell(text="推荐值", row=0, col=3),
                TableCell(text="备注", row=0, col=4),
            ],
            [
                TableCell(text="1", row=1, col=0),
                TableCell(text="平均风速", row=1, col=1),
                TableCell(text="m/s", row=1, col=2),
                TableCell(text="6.42", row=1, col=3),
                TableCell(text="2026版", row=1, col=4),
            ],
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="avgWindSpeed",
            field_name="平均风速",
            source_type="table",
            text="平均风速 | m/s | 6.42 | 2026版",
            score=1.0,
            table_id="t_0001",
            field_config={"aliases": ["平均风速"], "unit_aliases": ["m/s"], "standard_unit": "m/s"},
            meta={"table": table},
        ),
        method="alias",
        score=2.0,
    )

    extracted = ValueExtractor(regex_enabled=False).extract([match])

    assert extracted[0].raw_value == "6.42"
    assert extracted[0].unit == "m/s"


def test_value_extractor_does_not_fallback_to_remark_number_when_table_columns_are_noise():
    """验证表格规则在只剩序号/备注数字时不再回退取最后一个数字。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [
                TableCell(text="平均风速", row=0, col=0),
                TableCell(text="备注2026", row=0, col=1),
            ]
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="avgWindSpeed",
            field_name="平均风速",
            source_type="table",
            text="平均风速 | 备注2026",
            score=1.0,
            table_id="t_0001",
            field_config={"aliases": ["平均风速"], "unit_aliases": ["m/s"], "standard_unit": "m/s"},
            meta={"table": table},
        ),
        method="alias",
        score=2.0,
    )

    assert ValueExtractor(regex_enabled=False).extract([match]) == []


def test_value_extractor_table_lookup_reads_row_label_and_annual_column():
    """验证表格行列交叉配置可抽取风速/风功率的年均列。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [
                TableCell(text="测风塔", row=0, col=0),
                TableCell(text="项目", row=0, col=1),
                TableCell(text="1", row=0, col=2),
                TableCell(text="年均", row=0, col=3),
            ],
            [
                TableCell(text="0821#", row=1, col=0),
                TableCell(text="风速", row=1, col=1),
                TableCell(text="6.2", row=1, col=2),
                TableCell(text="6.42", row=1, col=3),
            ],
            [
                TableCell(text="0821#", row=2, col=0),
                TableCell(text="风功率", row=2, col=1),
                TableCell(text="217", row=2, col=2),
                TableCell(text="232", row=2, col=3),
            ],
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="hubHeightAnnualAverageWindSpeed",
            field_name="轮毂高度年平均风速",
            source_type="table",
            text="风速 年均 6.42",
            score=1.0,
            table_id="t_0001",
            field_config={
                "aliases": ["风速"],
                "value_type": "number",
                "standard_unit": "m/s",
                "unit_aliases": ["m/s"],
                "table_lookup": {"row_aliases": ["风速"], "column_aliases": ["年均"]},
            },
            meta={"table": table},
        ),
        method="alias",
        score=2.0,
    )

    extracted = ValueExtractor(regex_enabled=False).extract([match])

    assert len(extracted) == 1
    assert extracted[0].raw_value == "6.42"
    assert extracted[0].method == "table_lookup"


def test_value_extractor_multi_number_pattern_extracts_all_values():
    """验证正文中的多个数值可作为多值候选全部抽出。"""
    match = FieldMatch(
        candidate=Candidate(
            field_code="airDensityAtHeight",
            field_name="高度对应的空气密度",
            source_type="paragraph",
            text="计算得到本项目区域空气密度分别为1.011kg/m³、1.013kg/m³、1.015kg/m³。",
            score=1.0,
            field_config={
                "value_type": "number",
                "standard_unit": "kg/m3",
                "multi_number_pattern": "空气密度分别为([^。；;\\n]+)",
            },
        ),
        method="alias",
        score=2.0,
    )

    extracted = ValueExtractor().extract([match])

    assert [item.raw_value for item in extracted] == ["1.011", "1.013", "1.015"]


def test_uie_split_number_unit_uses_field_unit_aliases():
    """验证 UIE 单位拆分不会把普通中文误识别为单位。"""
    extractor = UIEExtractor()
    field_config = {"unit_aliases": ["m/s", "米/秒"], "standard_unit": "m/s"}

    assert extractor._split_number_unit("6.42m/s", field_config) == ("6.42", "m/s")
    assert extractor._split_number_unit("1.15财务评价", field_config) == ("1.15", None)



def test_field_metrics_reports_value_and_unit_accuracy():
    """Evaluation should track field, value, and unit correctness separately."""
    metrics = FieldMetrics()
    predictions = [
        {"file": "a.docx", "field_code": "foo", "value": 6.42, "unit": "m/s"},
        {"file": "a.docx", "field_code": "bar", "value": 12, "unit": "kV"},
    ]
    golden = [
        {"file": "a.docx", "field_code": "foo", "value": "6.42", "unit": "m/s"},
        {"file": "a.docx", "field_code": "bar", "value": 12, "unit": "MW"},
    ]

    result = metrics.calculate(predictions, golden)

    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["exact_match"] == 0.5
    assert result["value_accuracy"] == 1.0
    assert result["unit_accuracy"] == 0.5

def test_resolver_prefers_valid_numeric_candidate_over_higher_invalid_score():
    """验证候选消解会优先选择合法数值，而不是单纯最高原始分。"""
    field_configs = {
        "maxWindSpeed50Year": {
            "value_type": "number",
            "standard_unit": "m/s",
            "validators": {"min": 0, "max": 80},
        }
    }
    invalid = Extraction(
        field_code="maxWindSpeed50Year",
        field_name="50年一遇最大风速",
        raw_value="计算",
        value="计算",
        unit=None,
        score=3.0,
        method="uie",
        evidence=FieldEvidence(source_type="paragraph", text="计算"),
    )
    valid = Extraction(
        field_code="maxWindSpeed50Year",
        field_name="50年一遇最大风速",
        raw_value="50",
        value=50,
        unit="m/s",
        score=2.2,
        method="regex",
        evidence=FieldEvidence(source_type="paragraph", text="50m/s"),
    )

    resolved = CandidateResolver(field_configs).resolve([invalid, valid])

    assert resolved["maxWindSpeed50Year"].value == 50
    assert resolved["maxWindSpeed50Year"].debug["resolver"] == "quality_score"


def test_resolver_preserves_multi_value_fields():
    """验证 multi_value 字段不会被消解成单个最高分。"""
    field_configs = {"airDensityAtHeight": {"multi_value": True, "value_type": "number", "standard_unit": "kg/m3"}}
    extractions = [
        Extraction(
            field_code="airDensityAtHeight",
            field_name="高度对应的空气密度",
            raw_value=str(value),
            value=value,
            unit="kg/m3",
            score=float(index),
            method="regex_multi",
            evidence=FieldEvidence(source_type="paragraph", text=str(value)),
        )
        for index, value in enumerate([1.011, 1.013, 1.015], start=1)
    ]

    resolved = CandidateResolver(field_configs).resolve(extractions)["airDensityAtHeight"]

    assert resolved.value == [1.015, 1.013, 1.011]
    assert resolved.debug["resolver"] == "multi_value_quality_score"


def test_semantic_analyzer_boosts_value_near_alias_and_penalizes_weak_fallback():
    """验证语义一致性分析能奖励近邻证据并惩罚弱兜底候选。"""
    field_configs = {
        "avgWindSpeed": {
            "name": "平均风速",
            "aliases": ["平均风速"],
            "value_type": "number",
            "sections": {"include": ["风资源"], "exclude": ["财务评价"]},
        }
    }
    strong = Extraction(
        field_code="avgWindSpeed",
        field_name="平均风速",
        raw_value="6.42",
        value=6.42,
        unit="m/s",
        score=1.0,
        method="regex",
        evidence=FieldEvidence(source_type="paragraph", text="平均风速为6.42m/s", section_path=["风资源"]),
    )
    weak = Extraction(
        field_code="avgWindSpeed",
        field_name="平均风速",
        raw_value="2.19",
        value=2.19,
        unit="m/s",
        score=1.0,
        method="regex_fallback",
        evidence=FieldEvidence(source_type="paragraph", text="序号2.19，其他说明", section_path=["风资源"]),
    )

    analyzed = SemanticAnalyzer(field_configs).analyze([strong, weak])

    assert analyzed[0].score > analyzed[1].score
    assert analyzed[0].debug["semantic_value_near_alias"] is True
    assert analyzed[1].debug["semantic_penalty"] == "fallback_without_alias"


def test_normalizer_preserves_raw_value_and_normalizes_final_fields():
    """验证候选级归一化不破坏 raw_value，最终字段级归一化统一输出。"""
    extraction = Extraction(
        field_code="avgWindSpeed",
        field_name="平均风速",
        raw_value="6.42米/秒",
        value="6.42米/秒",
        unit="米/秒",
        score=1.0,
        method="regex",
        evidence=FieldEvidence(source_type="paragraph", text="平均风速为6.42米/秒"),
    )
    normalizer = Normalizer()

    normalized = normalizer.normalize_candidates([extraction])[0]

    assert normalized.raw_value == "6.42米/秒"
    assert normalized.value == 6.42
    assert normalized.unit == "m/s"

    fields = {
        "avgWindSpeed": ParsedField(
            field_code="avgWindSpeed",
            field_name="平均风速",
            value="6.42",
            unit="米/秒",
            normalized_value="6.42",
        )
    }
    final = normalizer.normalize_fields(fields)["avgWindSpeed"]

    assert final.value == 6.42
    assert final.unit == "m/s"
    assert final.normalized_value == 6.42


def test_semantic_verifier_builds_queries_and_applies_nli_scores():
    """验证语义验证器按 Reranker/NLI 结果给候选加分。"""

    class FakeVerifier(SemanticVerifier):
        def _reranker_score(self, extraction):
            return 0.9

        def _nli_score(self, extraction):
            return "entailment", 0.8

    extraction = Extraction(
        field_code="avgWindSpeed",
        field_name="平均风速",
        raw_value="6.42",
        value=6.42,
        unit="m/s",
        score=1.0,
        method="regex",
        evidence=FieldEvidence(source_type="paragraph", text="平均风速为6.42m/s"),
    )
    verifier = FakeVerifier({}, enabled=True, reranker_enabled=True, nli_enabled=True)

    verified = verifier.verify([extraction])[0]

    assert verifier._build_reranker_query(extraction) == "平均风速：6.42m/s"
    assert verifier._build_nli_hypothesis(extraction) == "该项目的平均风速为6.42m/s。"
    assert verified.score > 1.0
    assert verified.debug["reranker_score"] == 0.9
    assert verified.debug["nli_label"] == "entailment"


def test_onnx_reranker_casts_numpy_inputs_to_int64():
    import numpy as np

    class FakeTokenizer:
        def __call__(self, queries, passages, **kwargs):
            return {
                "input_ids": np.array([[1, 2, 3]], dtype=np.int32),
                "attention_mask": np.array([[1, 1, 1]], dtype=np.int32),
                "token_type_ids": np.array([[0, 0, 0]], dtype=np.int32),
            }

    class FakeInput:
        def __init__(self, name):
            self.name = name

    class FakeSession:
        def __init__(self):
            self.feed = None

        def get_inputs(self):
            return [FakeInput("input_ids"), FakeInput("attention_mask"), FakeInput("token_type_ids")]

        def run(self, _outputs, feed):
            self.feed = feed
            assert feed["input_ids"].dtype == np.int64
            assert feed["attention_mask"].dtype == np.int64
            assert feed["token_type_ids"].dtype == np.int64
            return [np.array([[0.25]], dtype=np.float32)]

    reranker = OnnxReranker(session=FakeSession(), tokenizer=FakeTokenizer())
    score = reranker.predict([("query", "passage")])[0]

    assert score == 0.25


def test_semantic_verifier_batches_reranker_and_nli():
    """验证语义验证器批量调用 Reranker 和 NLI。"""

    class FakeReranker:
        def __init__(self):
            self.calls = []

        def predict(self, pairs, batch_size=None):
            self.calls.append((pairs, batch_size))
            return [0.9 for _ in pairs]

    class FakeVerifier(SemanticVerifier):
        def __init__(self):
            super().__init__({}, enabled=True, reranker_enabled=True, nli_enabled=True, batch_size=8)
            self.fake_reranker = FakeReranker()
            self.nli_calls = []

        def _load_reranker(self):
            return self.fake_reranker

        def _nli_scores(self, extractions):
            self.nli_calls.append(list(extractions))
            return [("entailment", 0.8) for _ in extractions]

    extractions = [
        Extraction(
            field_code="avgWindSpeed",
            field_name="平均风速",
            raw_value="6.42",
            value=6.42,
            unit="m/s",
            score=1.0,
            method="regex",
            evidence=FieldEvidence(source_type="paragraph", text="平均风速为6.42m/s"),
        )
        for _ in range(3)
    ]
    verifier = FakeVerifier()

    verifier.verify(extractions)

    assert len(verifier.fake_reranker.calls) == 1
    assert len(verifier.fake_reranker.calls[0][0]) == 3
    assert verifier.fake_reranker.calls[0][1] == 8
    assert len(verifier.nli_calls) == 1


def test_funnel_pruner_keeps_top_k_per_field_and_marks_debug():
    """验证漏斗剪枝按字段分组保留 Top-K。"""
    extractions = [
        Extraction(
            field_code="avgWindSpeed",
            field_name="平均风速",
            raw_value=str(i),
            value=i,
            unit="m/s",
            score=float(i),
            method="regex",
            evidence=FieldEvidence(source_type="paragraph", text=str(i)),
        )
        for i in range(4)
    ]
    pruner = FunnelPruner(enabled=True, stages={"nli_candidates": 2})

    kept = pruner.prune_extractions(extractions, "nli_candidates")

    assert [item.value for item in kept] == [3, 2]
    assert kept[0].debug["nli_candidates_rank"] == 1
    assert kept[0].debug["nli_candidates_top_k"] == 2
    assert extractions[0].debug["nli_candidates_kept"] is False


def test_json_exporter_adds_sections_only_result_and_detail_rows(tmp_path):
    """Verify detail JSON contains section traces and source/process information."""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_0001",
                order=1,
                section_path=["资源章节"],
                rows=[
                    [
                        TableCell(text="测风塔编号", row=0, col=0),
                        TableCell(text="轮毫高度平均风速 m/s", row=0, col=1),
                    ],
                    [TableCell(text="0821#", row=1, col=0), TableCell(text="6.42", row=1, col=1)],
                ],
            )
        ],
    )
    ctx = ParseContext(
        file_path="sample.docx",
        ast=ast,
        validated={
            "projectName": ParsedField(
                field_code="projectName",
                field_name="项目名称",
                value="工程静态投资（一期）部分合计",
                unit=None,
                normalized_value="工程静态投资（一期）部分合计",
                evidence=[
                    FieldEvidence(
                        source_type="table",
                        text="工程静态投资（一期）部分合计",
                        score=1.0,
                        table_id="t_0001",
                        section_path=["资源章节"],
                        match_method="deterministic_override",
                    )
                ],
                debug={"resolver": "deterministic_override"},
            ),
            "collectorLineNames": ParsedField(
                field_code="collectorLineNames",
                field_name="线路名称",
                value="A-C",
                unit=None,
                normalized_value="A-C",
                evidence=[
                    FieldEvidence(
                        source_type="table",
                        text="A线、B线、C线",
                        score=1.0,
                        table_id="t_0001",
                        section_path=["资源章节"],
                        match_method="deterministic_override",
                    )
                ],
                debug={"resolver": "deterministic_override"},
            ),
        },
    )

    exported = JsonExporter(output_dir=tmp_path).export(ctx)

    assert exported["result"] == {"filePath": "sample.docx", "sections": exported["result"]["sections"]}
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    common_section = next(section for section in detail_json["sections"] if section["name"] == "通用")
    collector_section = next(section for section in detail_json["sections"] if section["name"] == "集电线路")
    assert common_section["fields"][0]["value"] is None
    assert common_section["fields"][0]["value"] is None
    assert common_section["fields"][0]["value"] is None
    assert collector_section["fields"][0]["fieldCode"] == "collectorLineNames"
    assert collector_section["fields"][0]["value"] == "A-C"
    assert detail_json["fieldIndex"]["collectorLineNames"]["value"] == "A-C"
    assert result_json == {"filePath": "sample.docx", "sections": result_json["sections"]}


def test_result_builder_overrides_project_and_collector_line_names(tmp_path):
    """Verify the module sections reflect the final normalized field values."""
    ast = DocumentAST(
        file_name="陕西华电靖边韩家沟200MW风电项目可行性研究报告.docx",
        blocks=[
            DocumentBlock(
                id="p_0001",
                type="paragraph",
                text="陕西华电靖边韩家沟200MW风电项目",
                order=1,
            )
        ],
        tables=[
            DocumentTable(
                id="t_0001",
                order=1,
                rows=[
                    [TableCell(text="线路名称", row=0, col=0)],
                    [TableCell(text="A线", row=1, col=0)],
                    [TableCell(text="B线", row=2, col=0)],
                    [TableCell(text="C线", row=3, col=0)],
                ],
            )
        ],
    )
    ctx = ParseContext(
        file_path=ast.file_name,
        ast=ast,
        validated={
            "projectName": ParsedField(
                field_code="projectName",
                field_name="项目名称",
                value="工程静态投资（一期）部分合计",
                unit=None,
                normalized_value="工程静态投资（一期）部分合计",
            ),
            "collectorLineNames": ParsedField(
                field_code="collectorLineNames",
                field_name="线路名称",
                value="A-C",
                unit=None,
                normalized_value="A-C",
            ),
        },
    )

    JsonExporter(output_dir=tmp_path).export(ctx)

    common_section = next(section for section in ctx.result["sections"] if section["name"] == "通用")
    collector_section = next(section for section in ctx.result["sections"] if section["name"] == "集电线路")
    assert common_section["fields"][0]["value"] == "陕西华电靖边韩家沟200MW风电项目"
    assert collector_section["fields"][0]["value"] == "A-C"


def test_result_builder_recovers_cover_secondary_and_wind_fields():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="陕西华电靖边10万千瓦风电项目", order=1),
            DocumentBlock(id="p_0006", type="paragraph", text="中国电建集团西北勘测设计研究院有限公司", order=6),
            DocumentBlock(id="p_0007", type="paragraph", text="工程设计甲级资质", order=7),
            DocumentBlock(id="p_0008", type="paragraph", text="50年一遇最大风速值为30.13m/s，湍流强度为0.252。", order=8, section_path=["资源章节"]),
        ],
    )

    validated = {
        "projectName": ParsedField(field_code="projectName", field_name="项目名称", value="陕西华电靖边10万千瓦风电项目", unit=None, normalized_value="陕西华电靖边10万千瓦风电项目"),
        "designUnit": ParsedField(field_code="designUnit", field_name="设计单位", value="中国电建集团西北勘测设计研究院有限公司", unit=None, normalized_value="中国电建集团西北勘测设计研究院有限公司"),
        "designUnitQualification": ParsedField(field_code="designUnitQualification", field_name="设计单位资质等级", value="甲级", unit=None, normalized_value="甲级"),
        "maxWindSpeed50Year": ParsedField(field_code="maxWindSpeed50Year", field_name="50年一遇最大风速值", value=30.13, unit="m/s", normalized_value="30.13"),
        "communicationPowerDesign": ParsedField(field_code="communicationPowerDesign", field_name="通讯电源设计", value="直流220V", unit=None, normalized_value="直流220V"),
    }

    built = ResultBuilder().build(ast, validated)
    fields = built["fields"]
    secondary_section = next(section for section in built["sections"] if section["name"] == "电气二次")

    assert fields["communicationPowerDesign"]["value"] == "直流220V"
    assert secondary_section["tables"] == []


def test_result_builder_keeps_secondary_electrical_tables_and_field_in_secondary_section(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="电气二次", order=1, section_path=["电气二次"]),
        ],
        tables=[
            DocumentTable(
                id="t_secondary_main",
                order=3,
                caption="表6.4.4-3 升压站电气二次主要设备表",
                section_path=["电气二次"],
                rows=[
                    [TableCell(text="名称", row=0, col=0), TableCell(text="规格", row=0, col=1)],
                    [TableCell(text="直流电源", row=1, col=0), TableCell(text="250Ah", row=1, col=1)],
                ],
            ),
            DocumentTable(
                id="t_secondary_comm",
                order=4,
                caption="表6.5-1 主要通信设备表",
                section_path=["电气二次"],
                rows=[
                    [TableCell(text="名称", row=0, col=0), TableCell(text="规格", row=0, col=1)],
                    [TableCell(text="通信电源", row=1, col=0), TableCell(text="220V", row=1, col=1)],
                ],
            ),
        ],
    )
    validated = {
        "communicationPowerDesign": ParsedField(field_code="communicationPowerDesign", field_name="通讯电源设计", value="200Ah 蓄电池 1 组 1 套 DC/DC 转换装置", unit=None, normalized_value="200Ah 蓄电池 1 组 1 套 DC/DC 转换装置"),
    }

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated=validated))
    secondary_section = next(section for section in exported["result"]["sections"] if section["name"] == "电气二次")
    values = {field["fieldCode"]: field["value"] for field in secondary_section["fields"]}
    assert values["communicationPowerDesign"] == "200Ah 蓄电池 1 组 1 套 DC/DC 转换装置"
    assert [table["key"] for table in secondary_section["tables"]] == ["electricalSecondaryMainEquipment", "electricalSecondaryCommunicationEquipment"]
    assert secondary_section["tables"][0]["name"] == "表6.4.4-3 升压站电气二次主要设备表"
    assert secondary_section["tables"][1]["name"] == "表6.5-1 主要通信设备表"
    assert secondary_section["tables"][0]["data"][0] == ["直流电源", "250Ah"]
    assert secondary_section["tables"][1]["data"][0] == ["通信电源", "220V"]


def test_electrical_secondary_original_tables_match_generalized_captions(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_main", 1, "表 6.3.16-1 升压站电气二次主要设备表", ["设备", "数量"], ["保护装置", "2"]),
            _table_with_caption("t_comm", 2, "表 6.5-1 主要通信设备表", ["设备", "数量"], ["通信电源", "1"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    secondary = next(section for section in result_json["sections"] if section["name"] == "电气二次")
    tables = {table["key"]: table for table in secondary["tables"]}
    assert tables["electricalSecondaryMainEquipment"]["name"] == "表 6.3.16-1 升压站电气二次主要设备表"
    assert tables["electricalSecondaryMainEquipment"]["data"] == [["保护装置", 2]]
    assert tables["electricalSecondaryCommunicationEquipment"]["name"] == "表 6.5-1 主要通信设备表"
    assert tables["electricalSecondaryCommunicationEquipment"]["data"] == [["通信电源", 1]]


def test_electrical_secondary_material_list_caption_maps_to_main_equipment(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_material", 1, "6.5.3 电气二次设备材料清册表", ["设备", "数量"], ["直流屏", "1"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    secondary = next(section for section in result_json["sections"] if section["name"] == "电气二次")
    tables = {table["key"]: table for table in secondary["tables"]}
    assert tables["electricalSecondaryMainEquipment"]["name"] == "6.5.3 电气二次设备材料清册表"
    assert tables["electricalSecondaryMainEquipment"]["data"] == [["直流屏", 1]]


def test_electrical_secondary_uses_previous_heading_and_section_path(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p_caption", type="paragraph", text="表 6.3.16-1 升压站电气二次主要设备表", order=1)],
        tables=[
            DocumentTable(
                id="t_main",
                order=2,
                rows=[
                    [TableCell(text="设备", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="保护装置", row=1, col=0), TableCell(text="2", row=1, col=1)],
                ],
            ),
            DocumentTable(
                id="t_comm",
                order=3,
                section_path=["电气二次", "主要通信设备表"],
                rows=[
                    [TableCell(text="设备", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="通信设备", row=1, col=0), TableCell(text="1", row=1, col=1)],
                ],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    secondary = next(section for section in result_json["sections"] if section["name"] == "电气二次")
    tables = {table["key"]: table for table in secondary["tables"]}
    assert tables["electricalSecondaryMainEquipment"]["name"] == "表 6.3.16-1 升压站电气二次主要设备表"
    assert tables["electricalSecondaryMainEquipment"]["data"] == [["保护装置", 2]]
    assert tables["electricalSecondaryCommunicationEquipment"]["name"] == "主要通信设备表"
    assert tables["electricalSecondaryCommunicationEquipment"]["data"] == [["通信设备", 1]]


def test_electrical_primary_uses_original_table_and_combined_fields(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_electrical_primary",
                order=1,
                caption="表6.3.3-10 升压站电气一次主要设备材料工程量表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="接入站名称", row=0, col=0), TableCell(text="可接入电压（kv）", row=0, col=1), TableCell(text="可接入容量（MW）", row=0, col=2)],
                    [TableCell(text="330kV曹城变电站", row=1, col=0), TableCell(text="110、330", row=1, col=1), TableCell(text="200", row=1, col=2)],
                    [TableCell(text="升压站电气主接线规划总规模（MW）", row=2, col=0), TableCell(text="升压站电气主接线本期规模（MW）", row=2, col=1), TableCell(text="主接线形式", row=2, col=2)],
                    [TableCell(text="200", row=3, col=0), TableCell(text="200", row=3, col=1), TableCell(text="110kV侧拟采用简单清晰的单母线接线方案\n35kV侧电气接线可采用双段母线接线形式", row=3, col=2)],
                    [TableCell(text="独立避雷针座数", row=4, col=0), TableCell(text="构架避雷针座数", row=4, col=1)],
                    [TableCell(text="2", row=5, col=0), TableCell(text="1", row=5, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    electrical = next(section for section in exported["result"]["sections"] if section["name"] == "电气一次")
    assert [table["key"] for table in electrical["tables"]] == ["electricalPrimaryEquipmentMaterial"]
    original = next(table for table in electrical["tables"] if table["key"] == "electricalPrimaryEquipmentMaterial")
    assert original["data"][0] == ["330kV曹城变电站", "110、330", 200]
    fields = {field["fieldCode"]: field["value"] for field in electrical["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == "110、330"
    assert fields["accessibleCapacity"] == 200
    assert fields["plannedCapacity"] == 200
    assert fields["currentCapacity"] == 200
    assert "35kV侧电气接线" in fields["connectionType"]
    assert fields["independentLightningRodCount"] == 2
    assert fields["frameLightningRodCount"] == 1


def test_electrical_primary_access_station_table_overrides_text_voltage(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="通过主变升压后拟以一回110kV线路接至330kV曹城变电站。", order=1, section_path=["电气一次"]),
        ],
        tables=[
            DocumentTable(
                id="t_access",
                order=2,
                caption="接入系统资料表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="接入站名称", row=0, col=0), TableCell(text="可接入电压（kv）", row=0, col=1), TableCell(text="可接入容量（MW）", row=0, col=2)],
                    [TableCell(text="330kV曹城变电站", row=1, col=0), TableCell(text="110", row=1, col=1), TableCell(text="200", row=1, col=2)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 200


def test_electrical_primary_access_voltage_ignores_station_voltage_level(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="通过主变升压后拟以一回110kV线路接至330kV曹城变电站。", order=1, section_path=["电气一次"]),
        ],
        tables=[
            DocumentTable(
                id="t_access",
                order=2,
                caption="接入系统资料表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="接入站名称", row=0, col=0), TableCell(text="可接入电压（kV）", row=0, col=1), TableCell(text="可接入容量（MW）", row=0, col=2)],
                    [TableCell(text="330kV曹城变电站", row=1, col=0), TableCell(text="110", row=1, col=1), TableCell(text="150", row=1, col=2)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 150


def test_electrical_primary_prefers_table_values_for_access_and_equipment_capacity(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="通过主变升压后拟以一回110kV线路接至330kV曹城变电站。", order=1, section_path=["电气一次"]),
            DocumentBlock(id="p2", type="paragraph", text="35kV侧母线各安装1组容量为-50Mvar动态无功补偿装置。", order=2, section_path=["电气一次"]),
        ],
        tables=[
            DocumentTable(
                id="t_access",
                order=1,
                caption="接入系统资料表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="接入站名称", row=0, col=0), TableCell(text="可接入电压（kv）", row=0, col=1), TableCell(text="可接入容量（MW）", row=0, col=2)],
                    [TableCell(text="330kV曹城变电站", row=1, col=0), TableCell(text="110", row=1, col=1), TableCell(text="150", row=1, col=2)],
                ],
            ),
            DocumentTable(
                id="t_equipment",
                order=2,
                caption="表6.3.3-10 升压站电气一次主要设备材料工程量表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="名称", row=0, col=1), TableCell(text="型号、规格及技术数据", row=0, col=2), TableCell(text="单位", row=0, col=3), TableCell(text="数量", row=0, col=4)],
                    [TableCell(text="5.1", row=1, col=0), TableCell(text="35kV接地兼站用变成套装置", row=1, col=1), TableCell(text="DKSC-800/35-315/0.4", row=1, col=2), TableCell(text="台", row=1, col=3), TableCell(text="1", row=1, col=4)],
                    [TableCell(text="", row=2, col=0), TableCell(text="", row=2, col=1), TableCell(text="接地变容量：800/315kVA", row=2, col=2), TableCell(text="", row=2, col=3), TableCell(text="", row=2, col=4)],
                    [TableCell(text="5.2", row=3, col=0), TableCell(text="35kV接地变成套装置", row=3, col=1), TableCell(text="DKSC-500/35", row=3, col=2), TableCell(text="台", row=3, col=3), TableCell(text="1", row=3, col=4)],
                    [TableCell(text="", row=4, col=0), TableCell(text="", row=4, col=1), TableCell(text="接地变容量：500kVA", row=4, col=2), TableCell(text="", row=4, col=3), TableCell(text="", row=4, col=4)],
                    [TableCell(text="10", row=5, col=0), TableCell(text="10kV站用变", row=5, col=1), TableCell(text="315kVA", row=5, col=2), TableCell(text="台", row=5, col=3), TableCell(text="1", row=5, col=4)],
                    [TableCell(text="16", row=6, col=0), TableCell(text="SVG无功补偿装置", row=6, col=1), TableCell(text="±50Mvar", row=6, col=2), TableCell(text="套", row=6, col=3), TableCell(text="1", row=6, col=4)],
                ],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 150
    assert fields["svgReactiveCompensationCapacity"] == "±50Mvar"
    assert fields["groundingTransformerCapacity35kv"] == "500kVA"
    assert fields["groundingStationTransformerCapacity35kv"] == "315kVA"
    assert fields["stationTransformerCapacity10kv"] == "315kVA"


def test_electrical_primary_equipment_table_extracts_detailed_specs(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_equipment",
                order=1,
                caption="6.2.9.升压站电气一次主要设备材料工程量表",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="名称", row=0, col=1), TableCell(text="型号、规格及技术数据", row=0, col=2), TableCell(text="单位", row=0, col=3), TableCell(text="数量", row=0, col=4), TableCell(text="备注", row=0, col=5)],
                    [TableCell(text="1.1", row=1, col=0), TableCell(text="主变压器", row=1, col=1), TableCell(text="三相双绕组油浸自冷式有载调压变压器", row=1, col=2), TableCell(text="台", row=1, col=3), TableCell(text="1", row=1, col=4), TableCell(text="", row=1, col=5)],
                    [TableCell(text="", row=2, col=0), TableCell(text="", row=2, col=1), TableCell(text="型号：SZ20-100000/110", row=2, col=2), TableCell(text="", row=2, col=3), TableCell(text="", row=2, col=4), TableCell(text="", row=2, col=5)],
                    [TableCell(text="", row=3, col=0), TableCell(text="", row=3, col=1), TableCell(text="115±8×1.25%/37kV", row=3, col=2), TableCell(text="", row=3, col=3), TableCell(text="", row=3, col=4), TableCell(text="", row=3, col=5)],
                    [TableCell(text="", row=4, col=0), TableCell(text="", row=4, col=1), TableCell(text="接线组别：YN，d11", row=4, col=2), TableCell(text="", row=4, col=3), TableCell(text="", row=4, col=4), TableCell(text="", row=4, col=5)],
                    [TableCell(text="2.1", row=5, col=0), TableCell(text="GIS组合电器", row=5, col=1), TableCell(text="126kV，2000A，40kA/3s", row=5, col=2), TableCell(text="个", row=5, col=3), TableCell(text="1", row=5, col=4), TableCell(text="110kV架空出线间隔", row=5, col=5)],
                    [TableCell(text="", row=6, col=0), TableCell(text="每间隔包含：", row=6, col=1), TableCell(text="SF6断路器：126kV，2000A，40kA/3s，配弹簧操作机构", row=6, col=2), TableCell(text="", row=6, col=3), TableCell(text="", row=6, col=4), TableCell(text="", row=6, col=5)],
                    [TableCell(text="", row=7, col=0), TableCell(text="", row=7, col=1), TableCell(text="三工位隔离接地开关：126kV，2000A，40kA/3s，100kA，含微动开关", row=7, col=2), TableCell(text="", row=7, col=3), TableCell(text="", row=7, col=4), TableCell(text="", row=7, col=5)],
                    [TableCell(text="", row=8, col=0), TableCell(text="", row=8, col=1), TableCell(text="电流互感器：126kV，600 600-1200/1A，0.2S/0.5/0.5/5P30/5P30/5P30/5P30", row=8, col=2), TableCell(text="", row=8, col=3), TableCell(text="", row=8, col=4), TableCell(text="", row=8, col=5)],
                    [TableCell(text="", row=9, col=0), TableCell(text="", row=9, col=1), TableCell(text="电压互感器：（110/√3）/（0.1/√3）/（0.1√3）/（0.1/√3）/0.1kV，0.5/0.5/0.2/3P，50/50/50/100VA", row=9, col=2), TableCell(text="", row=9, col=3), TableCell(text="", row=9, col=4), TableCell(text="", row=9, col=5)],
                    [TableCell(text="16", row=10, col=0), TableCell(text="35kv SVG", row=10, col=1), TableCell(text="±50Mvar", row=10, col=2), TableCell(text="套", row=10, col=3), TableCell(text="1", row=10, col=4), TableCell(text="", row=10, col=5)],
                    [TableCell(text="5.1", row=11, col=0), TableCell(text="35kV接地变成套装置", row=11, col=1), TableCell(text="DKSC-800/37-315/0.4", row=11, col=2), TableCell(text="台", row=11, col=3), TableCell(text="1", row=11, col=4), TableCell(text="", row=11, col=5)],
                    [TableCell(text="", row=12, col=0), TableCell(text="", row=12, col=1), TableCell(text="接地变容量：500kVA", row=12, col=2), TableCell(text="", row=12, col=3), TableCell(text="", row=12, col=4), TableCell(text="", row=12, col=5)],
                    [TableCell(text="", row=13, col=0), TableCell(text="", row=13, col=1), TableCell(text="小电阻型号：NGR-37/200A—10s,106.8Ω", row=13, col=2), TableCell(text="", row=13, col=3), TableCell(text="", row=13, col=4), TableCell(text="", row=13, col=5)],
                    [TableCell(text="8", row=14, col=0), TableCell(text="站外电源变压器", row=14, col=1), TableCell(text="SCB14-800/10.5", row=14, col=2), TableCell(text="台", row=14, col=3), TableCell(text="1", row=14, col=4), TableCell(text="", row=14, col=5)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["electricalPrimaryTransformerSpec"] == "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV，接线组别：YN，d11"
    assert fields["electricalPrimaryGisModelInfo"] == "126kV，2000A，40kA/3s"
    assert fields["electricalPrimaryGisQuantity"] == 1
    assert fields["electricalPrimaryGisUnit"] == "个"
    assert fields["electricalPrimaryGisRemark"] == "110kV架空出线间隔"
    assert fields["electricalPrimaryCircuitBreakerModel"] == "SF6断路器：126kV，2000A，40kA/3s，配弹簧操作机构"
    assert fields["electricalPrimaryDisconnectorModel"] == "三工位隔离接地开关：126kV，2000A，40kA/3s，100kA，含微动开关"
    assert fields["electricalPrimaryCurrentTransformerModel"] == "电流互感器：126kV，600 600-1200/1A，0.2S/0.5/0.5/5P30/5P30/5P30/5P30"
    assert fields["electricalPrimaryVoltageTransformerModel"] == "电压互感器：（110/√3）/（0.1/√3）/（0.1√3）/（0.1/√3）/0.1kV，0.5/0.5/0.2/3P，50/50/50/100VA"
    assert fields["electricalPrimarySvgSpec"] == "±50Mvar"
    assert fields["electricalPrimarySvgUnit"] == "套"
    assert fields["electricalPrimarySvgQuantity"] == 1
    assert fields["electricalPrimaryGroundingTransformerSetSpec"] == "DKSC-800/37-315/0.4，接地变容量：500kVA，小电阻型号：NGR-37/200A—10s,106.8Ω"
    assert fields["electricalPrimaryExternalPowerTransformerSpec"] == "SCB14-800/10.5"


def test_electrical_primary_equipment_table_handles_polluted_caption_and_continuation_rows(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_primary_1",
                order=1,
                caption="防火墙的耐火极限为 4h。",
                section_path=["第六章 电气", "6.2 电气一次"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="名 称", row=0, col=1), TableCell(text="型号、规格及技术数据", row=0, col=2), TableCell(text="单位", row=0, col=3), TableCell(text="数量", row=0, col=4), TableCell(text="备 注", row=0, col=5)],
                    [TableCell(text="1.1", row=1, col=0), TableCell(text="主变压器", row=1, col=1), TableCell(text="三相双绕组油浸自冷式有 载调压变压器", row=1, col=2), TableCell(text="台", row=1, col=3), TableCell(text="1", row=1, col=4), TableCell(text="", row=1, col=5)],
                    [TableCell(text="", row=2, col=0), TableCell(text="", row=2, col=1), TableCell(text="型号：SZ20-100000/110", row=2, col=2), TableCell(text="", row=2, col=3), TableCell(text="", row=2, col=4), TableCell(text="", row=2, col=5)],
                    [TableCell(text="", row=3, col=0), TableCell(text="", row=3, col=1), TableCell(text="115±8×1.25%/37kV", row=3, col=2), TableCell(text="", row=3, col=3), TableCell(text="", row=3, col=4), TableCell(text="", row=3, col=5)],
                    [TableCell(text="", row=4, col=0), TableCell(text="", row=4, col=1), TableCell(text="短路阻抗：", row=4, col=2), TableCell(text="", row=4, col=3), TableCell(text="", row=4, col=4), TableCell(text="", row=4, col=5)],
                    [TableCell(text="", row=5, col=0), TableCell(text="", row=5, col=1), TableCell(text="U%=10.5", row=5, col=2), TableCell(text="", row=5, col=3), TableCell(text="", row=5, col=4), TableCell(text="", row=5, col=5)],
                    [TableCell(text="", row=6, col=0), TableCell(text="", row=6, col=1), TableCell(text="接线组别：YN，d11", row=6, col=2), TableCell(text="", row=6, col=3), TableCell(text="", row=6, col=4), TableCell(text="", row=6, col=5)],
                    [TableCell(text="", row=7, col=0), TableCell(text="", row=7, col=1), TableCell(text="智能控制柜", row=7, col=2), TableCell(text="", row=7, col=3), TableCell(text="", row=7, col=4), TableCell(text="", row=7, col=5)],
                ],
            ),
            DocumentTable(
                id="t_primary_2",
                order=2,
                caption=None,
                section_path=["第六章 电气", "6.2 电气一次"],
                rows=[
                    [TableCell(text="4.1", row=0, col=0), TableCell(text="35kV SVG", row=0, col=1), TableCell(text="±30Mvar 直挂式 SVG", row=0, col=2), TableCell(text="套", row=0, col=3), TableCell(text="1", row=0, col=4), TableCell(text="含预制舱", row=0, col=5)],
                    [TableCell(text="5.1", row=1, col=0), TableCell(text="35kV 接地变成套装置", row=1, col=1), TableCell(text="DKSC-800/37-315/0.4, 隔离开关 GN19-40.5/630", row=1, col=2), TableCell(text="台", row=1, col=3), TableCell(text="1", row=1, col=4), TableCell(text="小电阻接地", row=1, col=5)],
                    [TableCell(text="", row=2, col=0), TableCell(text="内含", row=2, col=1), TableCell(text="应含组件：控制屏，电压互感器，电流互感器", row=2, col=2), TableCell(text="", row=2, col=3), TableCell(text="", row=2, col=4), TableCell(text="", row=2, col=5)],
                    [TableCell(text="", row=3, col=0), TableCell(text="", row=3, col=1), TableCell(text="接地变容量：500kVA", row=3, col=2), TableCell(text="", row=3, col=3), TableCell(text="", row=3, col=4), TableCell(text="", row=3, col=5)],
                    [TableCell(text="", row=4, col=0), TableCell(text="", row=4, col=1), TableCell(text="小电阻型号： NGR-37/200A— 10s,106.8Ω", row=4, col=2), TableCell(text="", row=4, col=3), TableCell(text="", row=4, col=4), TableCell(text="", row=4, col=5)],
                    [TableCell(text="", row=5, col=0), TableCell(text="", row=5, col=1), TableCell(text="安装形式：户外箱壳式", row=5, col=2), TableCell(text="", row=5, col=3), TableCell(text="", row=5, col=4), TableCell(text="", row=5, col=5)],
                ],
            ),
            DocumentTable(
                id="t_primary_3",
                order=3,
                caption=None,
                section_path=["第六章 电气", "6.2 电气一次"],
                rows=[
                    [TableCell(text="7.13", row=0, col=0), TableCell(text="电缆埋管 DN25~ 150", row=0, col=1), TableCell(text="", row=0, col=2), TableCell(text="米", row=0, col=3), TableCell(text="500", row=0, col=4), TableCell(text="", row=0, col=5)],
                    [TableCell(text="8", row=1, col=0), TableCell(text="站外电源", row=1, col=1), TableCell(text="", row=1, col=2), TableCell(text="", row=1, col=3), TableCell(text="", row=1, col=4), TableCell(text="", row=1, col=5)],
                    [TableCell(text="8.1", row=2, col=0), TableCell(text="站外电源变压器", row=2, col=1), TableCell(text="S13-315/10.5 10.5±2×2.5%/0.4kV", row=2, col=2), TableCell(text="台", row=2, col=3), TableCell(text="1", row=2, col=4), TableCell(text="", row=2, col=5)],
                ],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["electricalPrimaryTransformerSpec"] == "三相双绕组油浸自冷式有载调压变压器，型号：SZ20-100000/110，115±8×1.25%/37kV，接线组别：YN，d11"
    assert fields["electricalPrimarySvgSpec"] == "±30Mvar 直挂式 SVG"
    assert fields["electricalPrimarySvgUnit"] == "套"
    assert fields["electricalPrimarySvgQuantity"] == 1
    assert fields["electricalPrimaryGroundingTransformerSetSpec"] == "DKSC-800/37-315/0.4，接地变容量：500kVA，小电阻型号： NGR-37/200A— 10s,106.8Ω"
    assert fields["electricalPrimaryExternalPowerTransformerSpec"] == "S13-315/10.5 10.5±2×2.5%/0.4kV"


def test_electrical_primary_optional_tables_do_not_emit_empty_placeholders(tmp_path):
    ast = DocumentAST(file_name="sample.docx")

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    electrical = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    assert electrical["tables"] == []


def test_electrical_primary_original_tables_match_generalized_captions(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_scale", 1, "表6.3-1   110kV升压站本期规模", ["项目", "规模"], ["主变", "2台"]),
            _table_with_caption("t_material", 2, "6.2.9.升压站电气一次主要设备材料工程量表", ["设备", "数量"], ["主变", "2"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    electrical = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    tables = {table["key"]: table for table in electrical["tables"]}
    assert tables["electricalPrimaryStationScale"]["name"] == "表6.3-1 110kV升压站本期规模"
    assert tables["electricalPrimaryStationScale"]["data"] == [["主变", "2台"]]
    assert tables["electricalPrimaryEquipmentMaterial"]["name"] == "6.2.9.升压站电气一次主要设备材料工程量表"
    assert tables["electricalPrimaryEquipmentMaterial"]["data"] == [["主变", 2]]


def test_electrical_primary_station_scale_extracts_outgoing_line_counts(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_scale",
                order=1,
                caption="表6.3-1 110kV升压站本期规模",
                section_path=["电气一次"],
                rows=[
                    [TableCell(text="名称", row=0, col=0), TableCell(text="本期规模", row=0, col=1), TableCell(text="远期规模", row=0, col=2)],
                    [TableCell(text="110kV出线", row=1, col=0), TableCell(text="1回", row=1, col=1), TableCell(text="2回", row=1, col=2)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    electrical = next(section for section in exported["result"]["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field for field in electrical["fields"]}
    assert fields["electricalPrimaryCurrentOutgoingLineCount"]["value"] == 1
    assert fields["electricalPrimaryCurrentOutgoingLineCount"]["unit"] == "回"
    assert fields["electricalPrimaryFutureOutgoingLineCount"]["value"] == 2
    assert fields["electricalPrimaryFutureOutgoingLineCount"]["unit"] == "回"


def test_electrical_primary_uses_numbered_previous_heading_for_major_primary_equipment(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p_caption", type="paragraph", text="6.3.11 主要电气一次设备", order=1)],
        tables=[
            DocumentTable(
                id="t_material",
                order=2,
                rows=[
                    [TableCell(text="设备", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="主变压器", row=1, col=0), TableCell(text="2", row=1, col=1)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    electrical = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    original = next(table for table in electrical["tables"] if table["key"] == "electricalPrimaryEquipmentMaterial")
    assert original["name"] == "6.3.11 主要电气一次设备"
    assert original["data"] == [["主变压器", 2]]


def test_electrical_primary_uses_section_path_for_major_primary_equipment(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_material",
                order=2,
                section_path=["电气一次", "升压站电气一次", "主要电气一次设备"],
                rows=[
                    [TableCell(text="设备", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="主变压器", row=1, col=0), TableCell(text="2", row=1, col=1)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    electrical = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    original = next(table for table in electrical["tables"] if table["key"] == "electricalPrimaryEquipmentMaterial")
    assert original["name"] == "主要电气一次设备"
    assert original["data"] == [["主变压器", 2]]


def test_electrical_primary_uses_embedded_previous_paragraph_heading_for_material_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p_caption",
                type="paragraph",
                text="以及风机塔筒内各层塔筒电缆孔洞均应封堵。6.2.9.升压站电气一次主要设备材料工程量表",
                order=1,
            )
        ],
        tables=[
            DocumentTable(
                id="t_material",
                order=2,
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="名称", row=0, col=1), TableCell(text="数量", row=0, col=2)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="主变压器", row=1, col=1), TableCell(text="2", row=1, col=2)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    electrical = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    original = next(table for table in electrical["tables"] if table["key"] == "electricalPrimaryEquipmentMaterial")
    assert original["name"] == "6.2.9.升压站电气一次主要设备材料工程量表"
    assert original["data"] == [[1, "主变压器", 2]]


def test_substation_civil_uses_original_major_civil_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_substation_civil",
                order=1,
                caption="表9.7-1 升压站主要土建工程量表",
                section_path=["土建升压站"],
                rows=[
                    [TableCell(text="总占地面积（㎡）", row=0, col=0), TableCell(text="围墙内占地面积（㎡）", row=0, col=1)],
                    [TableCell(text="6700", row=1, col=0), TableCell(text="5952", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "土建升压站")
    table = next(table for table in section["tables"] if table["key"] == "substationCivil")
    assert table["name"] == "表9.7-1 升压站主要土建工程量表"
    assert table["columns"] == ["总占地面积（㎡）", "围墙内占地面积（㎡）"]
    assert table["data"] == [[6700, 5952]]


def test_substation_civil_original_table_matches_generalized_captions(tmp_path):
    captions = [
        "表8.6-3      土建主要工程量表",
        "表9.7-1    升压站主要土建工程量表",
        "7.6.6.升压站土建清单",
    ]
    for caption in captions:
        ast = DocumentAST(
            file_name="sample.docx",
            tables=[
                DocumentTable(
                    id="t_substation_civil",
                    order=1,
                    caption=caption,
                    section_path=["土建升压站"],
                    rows=[
                        [TableCell(text="序号", row=0, col=0), TableCell(text="名称", row=0, col=1), TableCell(text="数量", row=0, col=2)],
                        [TableCell(text="1", row=1, col=0), TableCell(text="围墙", row=1, col=1), TableCell(text="100", row=1, col=2)],
                    ],
                )
            ],
        )

        exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
        section = next(section for section in exported["result"]["sections"] if section["name"] == "土建升压站")
        table = next(table for table in section["tables"] if table["key"] == "substationCivil")
        assert table["name"] == caption.replace("      ", " ").replace("    ", " ")
        assert table["data"] == [[1, "围墙", 100]]


def test_substation_civil_uses_previous_heading_when_caption_missing(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p_caption", type="paragraph", text="7.6.6.升压站土建清单", order=1)],
        tables=[
            DocumentTable(
                id="t_substation_civil",
                order=2,
                rows=[
                    [TableCell(text="名称", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="围墙", row=1, col=0), TableCell(text="100", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "土建升压站")
    table = next(table for table in section["tables"] if table["key"] == "substationCivil")
    assert table["name"] == "7.6.6.升压站土建清单"
    assert table["data"] == [["围墙", 100]]


def test_substation_civil_combined_fields_from_layout_paragraph(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="9.7.1 总体布置设计", order=1),
            DocumentBlock(id="p2", type="paragraph", text="升压站总占地面积为6700㎡，围墙内占地面积5952㎡，其中生活区布置有生活预制舱。", order=2),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "土建升压站")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["totalLandArea"] == 6700
    assert fields["insideWallLandArea"] == 5952


def test_road_section_builds_parameter_fields_from_paragraph_without_original_title(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目新建进站道路0.4km（进站道路前20m采用混凝土路面，路基宽6.0m，路面宽4.0m，其余路段设计标准同场内道路）；场内道路122.8km，新建道路23.1km，改建道路99.7km。根据风场地形条件及风机布置，路基设计宽度为5.5m，施工期铺设20cm厚泥结碎石路面，风电场施工完成后将路面修复成4.5m宽作为检修道路路基，路面宽3.5m。",
                order=1,
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "道路")
    assert not any(table["key"] == "roadTechnical" for table in section["tables"])
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessRoadLength"] == 0.4
    assert fields["accessRoadSubgradeWidth"] == 6
    assert fields["accessRoadPavementWidth"] == 4
    assert fields["newRoadLength"] == 23.1
    assert fields["rebuiltRoadLength"] == 99.7
    assert fields["subgradeWidth"] == 5.5
    assert fields["pavementWidth"] is None
    assert fields["siteRoadLength"] == 122.8
    assert fields["maintenanceRoadLength"] is None
    assert fields["maintenanceRoadSubgradeWidth"] == 4.5
    assert fields["maintenanceRoadPavementWidth"] == 3.5


def test_road_parameter_table_values_are_not_overwritten_by_access_or_maintenance_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目新建进站道路0.4km，场内道路122.8km，新建道路23.1km，改建道路99.7km。检修道路，按路基宽4.5m，路面宽3.5m考虑。",
                order=1,
                section_path=["道路"],
            )
        ],
        tables=[
            DocumentTable(
                id="t_road_params",
                order=2,
                caption="道路参数组合表",
                section_path=["道路"],
                rows=[
                    [
                        TableCell(text="进站道路长度（km）", row=0, col=0),
                        TableCell(text="场内道路长度（km）", row=0, col=1),
                        TableCell(text="新建道路长度（km）", row=0, col=2),
                        TableCell(text="改建道路长度（km）", row=0, col=3),
                        TableCell(text="路基宽度（m）", row=0, col=4),
                        TableCell(text="路面宽度（m）", row=0, col=5),
                        TableCell(text="检修道路路基宽度（m）", row=0, col=6),
                        TableCell(text="检修道路路面宽度（m）", row=0, col=7),
                    ],
                    [
                        TableCell(text="0.4", row=1, col=0),
                        TableCell(text="122.8", row=1, col=1),
                        TableCell(text="23.1", row=1, col=2),
                        TableCell(text="99.7", row=1, col=3),
                        TableCell(text="5.5", row=1, col=4),
                        TableCell(text="——", row=1, col=5),
                        TableCell(text="4.5", row=1, col=6),
                        TableCell(text="3.5", row=1, col=7),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessRoadLength"] == 0.4
    assert fields["siteRoadLength"] == 122.8
    assert fields["newRoadLength"] == 23.1
    assert fields["rebuiltRoadLength"] == 99.7
    assert fields["subgradeWidth"] == 5.5
    assert fields["pavementWidth"] is None
    assert fields["maintenanceRoadSubgradeWidth"] == 4.5
    assert fields["maintenanceRoadPavementWidth"] == 3.5


def test_road_parameter_table_new_and_rebuilt_lengths_override_narrative_variants(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="新建施工道路长约12.26km，改建道路长约24.04km，作为检修道路。",
                order=1,
                section_path=["道路"],
            )
        ],
        tables=[
            DocumentTable(
                id="t_road_params",
                order=2,
                caption="道路参数组合表",
                section_path=["道路"],
                rows=[
                    [
                        TableCell(text="新建道路长度（km）", row=0, col=0),
                        TableCell(text="改建道路长度（km）", row=0, col=1),
                    ],
                    [
                        TableCell(text="10.35", row=1, col=0),
                        TableCell(text="20.8", row=1, col=1),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["newRoadLength"] == 10.35
    assert fields["rebuiltRoadLength"] == 20.8


def test_road_parameter_table_reads_split_unit_header_before_narrative(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="场内检修道路约12.26km，其中24.04km为改建道路。",
                order=1,
                section_path=["道路"],
            )
        ],
        tables=[
            DocumentTable(
                id="t_road_params",
                order=2,
                caption="道路参数组合表",
                section_path=["道路"],
                rows=[
                    [
                        TableCell(text="新建道路长度", row=0, col=0),
                        TableCell(text="改建道路长度", row=0, col=1),
                    ],
                    [
                        TableCell(text="(km)", row=1, col=0),
                        TableCell(text="(km)", row=1, col=1),
                    ],
                    [
                        TableCell(text="10.35", row=2, col=0),
                        TableCell(text="20.8", row=2, col=1),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["newRoadLength"] == 10.35
    assert fields["rebuiltRoadLength"] == 20.8


def test_wind_foundation_uses_original_section_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_wind_foundation",
                order=1,
                caption="表9.4-5 基础断面表",
                section_path=["风机基础"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="数值", row=0, col=1)],
                    [TableCell(text="R", row=1, col=0), TableCell(text="10", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "风机基础")
    assert [table["key"] for table in section["tables"]] == ["windFoundationConstruction"]
    table = section["tables"][0]
    assert table["name"] == "表9.4-5 基础断面表"
    assert table["data"] == [["R", 10]]


def test_wind_foundation_matches_generalized_original_captions(tmp_path):
    captions = ["表1.8-1  基础尺寸及参数表", "表 7.3.4-5 基础断面表", "表9.4-5  基础断面表"]
    for caption in captions:
        ast = DocumentAST(
            file_name="sample.docx",
            tables=[_table_with_caption("t_wind", 1, caption, ["基础形式", "混凝土量"], ["天然地基", "1200m3"])],
        )

        exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
        section = next(section for section in exported["result"]["sections"] if section["name"] == "风机基础")
        table = next(table for table in section["tables"] if table["key"] == "windFoundationConstruction")
        assert table["name"] == re.sub(r"\s+", " ", caption).strip()
        assert table["data"] == [["天然地基", "1200m3"]]


def test_wind_foundation_extracts_type_and_quantity_fields(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本工程风机基础采用灌注桩基础，满足地基承载力要求。",
                order=1,
                section_path=["风机基础"],
            )
        ],
        tables=[
            DocumentTable(
                id="t_wind_quantity",
                order=2,
                caption="表 7.3.4-8 风机基础工程量",
                section_path=["风机基础"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="单位", row=0, col=2), TableCell(text="单台", row=0, col=3), TableCell(text="合计", row=0, col=4)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="土方开挖", row=1, col=1), TableCell(text="m³", row=1, col=2), TableCell(text="2225", row=1, col=3), TableCell(text="53400", row=1, col=4)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="土方回填", row=2, col=1), TableCell(text="m³", row=2, col=2), TableCell(text="1255", row=2, col=3), TableCell(text="30120", row=2, col=4)],
                    [TableCell(text="3", row=3, col=0), TableCell(text="风机基础 C15混凝土", row=3, col=1), TableCell(text="m³", row=3, col=2), TableCell(text="80", row=3, col=3), TableCell(text="1920", row=3, col=4)],
                    [TableCell(text="4", row=4, col=0), TableCell(text="风机基础 C20混凝土", row=4, col=1), TableCell(text="m³", row=4, col=2), TableCell(text="120", row=4, col=3), TableCell(text="2880", row=4, col=4)],
                    [TableCell(text="5", row=5, col=0), TableCell(text="风机基础 C40混凝土", row=5, col=1), TableCell(text="m³", row=5, col=2), TableCell(text="760", row=5, col=3), TableCell(text="18240", row=5, col=4)],
                    [TableCell(text="6", row=6, col=0), TableCell(text="风机基础 C45混凝土", row=6, col=1), TableCell(text="m³", row=6, col=2), TableCell(text="30", row=6, col=3), TableCell(text="720", row=6, col=4)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "风机基础")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["windFoundationType"]["value"] == "灌注桩基础"
    assert fields["windFoundationExcavationQuantity"]["value"] == 2225
    assert fields["windFoundationExcavationQuantity"]["unit"] == "m3"
    assert fields["windFoundationBackfillQuantity"]["value"] == 1255
    assert fields["windFoundationBackfillQuantity"]["unit"] == "m3"
    assert fields["windFoundationC15Concrete"]["value"] == "C15混凝土：80m³"
    assert fields["windFoundationC20Concrete"]["value"] == "C20混凝土：120m³"
    assert fields["windFoundationC40Concrete"]["value"] == "C40混凝土：760m³"
    assert fields["windFoundationC45Concrete"]["value"] == "C45混凝土：30m³"


def test_candidate_retriever_honors_paragraph_only_source_types_for_wind_foundation_fields():
    config = {"pileCount": _wind_foundation_paragraph_field_configs()["pileCount"]}
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p1", type="paragraph", text="桩数=38", order=1, section_path=["风机基础"])],
        tables=[
            DocumentTable(
                id="t1",
                order=2,
                section_path=["风机基础"],
                rows=[[TableCell(text="桩数", row=0, col=0), TableCell(text="99", row=0, col=1)]],
            )
        ],
    )

    candidates = CandidateRetriever(config).retrieve(ast)

    assert [(candidate.field_code, candidate.source_type) for candidate in candidates] == [("pileCount", "paragraph")]


def test_wind_foundation_paragraph_fields_build_technical_table(tmp_path):
    selected_configs = _wind_foundation_paragraph_field_configs()
    codes = list(selected_configs)
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text=(
                    "承台底面半径 R=10.5m\n"
                    "棱台顶面半径 R1=5.1m\n"
                    "承台台柱半径 R2=5.1m\n"
                    "承台底板外缘高度 H1=1.0m\n"
                    "承台底板棱台高度 H2=1.9m\n"
                    "台柱高度 H3=1.4m\n"
                    "基础埋深 Hd=6.0m\n"
                    "桩截面外径(直径)=0.8m\n"
                    "桩数=38\n"
                    "桩长=30m\n"
                    "桩圈数=2"
                ),
                order=1,
                section_path=["风机基础"],
            )
        ],
        tables=[
            DocumentTable(
                id="t1",
                order=2,
                section_path=["风机基础"],
                rows=[[TableCell(text="桩数", row=0, col=0), TableCell(text="99", row=0, col=1)]],
            )
        ],
    )

    candidates = CandidateRetriever(selected_configs).retrieve(ast)
    matches = FieldMatcher().match(candidates)
    extractions = ValueExtractor().extract(matches)
    fields = CandidateResolver(selected_configs).resolve(extractions)
    built = ResultBuilder(field_configs=selected_configs).build(ast, fields)
    section = next(section for section in built["result"]["sections"] if section["name"] == "风机基础") if "result" in built else next(section for section in built["sections"] if section["name"] == "风机基础")

    assert {code: fields[code].value for code in codes} == {
        "foundationCapBottomRadius": "10.5",
        "foundationTopRadius": "5.1",
        "foundationColumnRadius": "5.1",
        "foundationOuterEdgeHeight": "1.0",
        "foundationConeHeight": "1.9",
        "foundationColumnHeight": "1.4",
        "foundationBuriedDepth": "6.0",
        "pileOuterDiameter": "0.8",
        "pileCount": "38",
        "pileLength": "30",
        "pileRingCount": "2",
    }
    assert {candidate.source_type for candidate in candidates} == {"paragraph"}
    assert all(table["key"] != "windFoundationTechnical" for table in section["tables"])


def test_wind_foundation_default_text_fallback_extracts_supplement_logic_fields(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text=(
                    "补充逻辑\n"
                    "基础主要参数如下：承台底面半径R=10.5m，棱台顶面半径R1=5.1m，"
                    "承台台柱半径R2=5.1m，承台底板外缘高度H1=1.0m，"
                    "承台底板棱台高度H2=1.9m，台柱高度H3=1.4m，基础埋深Hd=6.0m。"
                    "桩截面外径(直径)=0.8m，桩数=38，桩长=30m，桩圈数=2。"
                ),
                order=1,
                section_path=["补充逻辑"],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "风机基础")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert float(fields["foundationCapDiameter"]) == 21
    assert float(fields["foundationColumnDiameter"]) == 10.2
    assert fields["foundationCapBottomRadius"] == 10.5
    assert fields["foundationTopRadius"] == 5.1
    assert fields["foundationColumnRadius"] == 5.1
    assert fields["foundationOuterEdgeHeight"] == 1.0
    assert fields["foundationConeHeight"] == 1.9
    assert fields["foundationColumnHeight"] == 1.4
    assert fields["foundationBuriedDepth"] == 6.0
    assert float(fields["pileOuterDiameter"]) == 0.8
    assert fields["pileCount"] == 38
    assert fields["pileLength"] == 30
    assert float(fields["pileRingCount"]) == 2


def test_wind_foundation_technical_table_reads_section_profile_table():
    """基础断面表是三列表时，也要能生成风机基础参数表。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_profile",
                order=2,
                caption="表 7.3.4-5 基础断面表",
                section_path=["风机基础"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="单位", row=0, col=1), TableCell(text="WTG5.5MW", row=0, col=2)],
                    [TableCell(text="圆形基础底面直径 D", row=1, col=0), TableCell(text="m", row=1, col=1), TableCell(text="21", row=1, col=2)],
                    [TableCell(text="基础圆台顶面半径为 R1", row=2, col=0), TableCell(text="m", row=2, col=1), TableCell(text="5.5", row=2, col=2)],
                    [TableCell(text="基础底板外缘高度 H1", row=3, col=0), TableCell(text="m", row=3, col=1), TableCell(text="1.0", row=3, col=2)],
                    [TableCell(text="基础底板圆台高度 H2", row=4, col=0), TableCell(text="m", row=4, col=1), TableCell(text="1.2", row=4, col=2)],
                    [TableCell(text="台柱高度 H3", row=5, col=0), TableCell(text="m", row=5, col=1), TableCell(text="1.0", row=5, col=2)],
                    [TableCell(text="基础埋深", row=6, col=0), TableCell(text="m", row=6, col=1), TableCell(text="3.0", row=6, col=2)],
                    [TableCell(text="桩数", row=7, col=0), TableCell(text="个", row=7, col=1), TableCell(text="34", row=7, col=2)],
                    [TableCell(text="桩身直径", row=8, col=0), TableCell(text="m", row=8, col=1), TableCell(text="0.8", row=8, col=2)],
                    [TableCell(text="平均桩长", row=9, col=0), TableCell(text="m", row=9, col=1), TableCell(text="22（含扩底部分 1.5m）", row=9, col=2)],
                ],
            )
        ],
    )

    table = ResultBuilder()._wind_foundation_technical_table_from_document(ast)

    assert table is not None
    assert table["data"] == [[10.5, 5.5, None, 1, 1.2, 1, 3, 0.8, 34, 22, None]]


def test_wind_foundation_no_space_profile_caption_exports_original_and_standard_table(tmp_path):
    """表号和表名没有空格时，仍应同时导出原表和标准参数表。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_profile_no_space",
                order=2,
                caption="表9.4-5基础断面表",
                section_path=["风机基础"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="单位", row=0, col=1), TableCell(text="WTG5.5MW", row=0, col=2)],
                    [TableCell(text="圆形基础底面直径 D", row=1, col=0), TableCell(text="m", row=1, col=1), TableCell(text="21", row=1, col=2)],
                    [TableCell(text="基础圆台顶面半径为 R1", row=2, col=0), TableCell(text="m", row=2, col=1), TableCell(text="5.5", row=2, col=2)],
                    [TableCell(text="基础底板外缘高度 H1", row=3, col=0), TableCell(text="m", row=3, col=1), TableCell(text="1.0", row=3, col=2)],
                    [TableCell(text="基础底板圆台高度 H2", row=4, col=0), TableCell(text="m", row=4, col=1), TableCell(text="1.2", row=4, col=2)],
                    [TableCell(text="台柱高度 H3", row=5, col=0), TableCell(text="m", row=5, col=1), TableCell(text="1.0", row=5, col=2)],
                    [TableCell(text="基础埋深", row=6, col=0), TableCell(text="m", row=6, col=1), TableCell(text="3.0", row=6, col=2)],
                    [TableCell(text="桩数", row=7, col=0), TableCell(text="个", row=7, col=1), TableCell(text="34", row=7, col=2)],
                    [TableCell(text="桩身直径", row=8, col=0), TableCell(text="m", row=8, col=1), TableCell(text="0.8", row=8, col=2)],
                    [TableCell(text="平均桩长", row=9, col=0), TableCell(text="m", row=9, col=1), TableCell(text="22（含扩底部分 1.5m）", row=9, col=2)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "风机基础")
    tables = {table["key"]: table for table in section["tables"]}

    assert tables["windFoundationConstruction"]["name"] == "表9.4-5基础断面表"
    assert tables["windFoundationConstruction"]["data"][:2] == [["圆形基础底面直径 D", "m", 21], ["基础圆台顶面半径为 R1", "m", 5.5]]
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["foundationCapBottomRadius"] == 10.5
    assert fields["foundationTopRadius"] == 5.5
    assert fields["foundationOuterEdgeHeight"] == 1
    assert fields["foundationConeHeight"] == 1.2
    assert fields["foundationColumnHeight"] == 1
    assert fields["foundationBuriedDepth"] == 3
    assert float(fields["pileOuterDiameter"]) == 0.8
    assert fields["pileCount"] == 34
    assert fields["pileLength"] == 22
    assert "windFoundationTechnical" not in tables


def _wind_foundation_paragraph_field_configs() -> dict[str, dict]:
    """构造不依赖 YAML 的风机基础段落字段配置。"""
    specs = {
        "foundationCapBottomRadius": ("承台底面半径R", "m", ["承台底面半径", "底面半径"], [r"承台底面半径\s*R\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationTopRadius": ("棱台顶面半径R1", "m", ["棱台顶面半径", "顶面半径"], [r"棱台顶面半径\s*R1\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationColumnRadius": ("承台台柱半径R2", "m", ["承台台柱半径", "台柱半径"], [r"承台台柱半径\s*R2\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationOuterEdgeHeight": ("承台底板外缘高度H1", "m", ["承台底板外缘高度", "外缘高度"], [r"承台底板外缘高度\s*H1\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationConeHeight": ("承台底板棱台高度H2", "m", ["承台底板棱台高度", "棱台高度"], [r"承台底板棱台高度\s*H2\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationColumnHeight": ("台柱高度H3", "m", ["台柱高度"], [r"台柱高度\s*H3\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "foundationBuriedDepth": ("基础埋深Hd", "m", ["基础埋深"], [r"基础埋深\s*Hd\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "pileOuterDiameter": ("桩截面外径(直径)", "m", ["桩截面外径", "桩径"], [r"桩截面外径\(直径\)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "pileCount": ("桩数", "根", ["桩数"], [r"桩数\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(根)?"]),
        "pileLength": ("桩长", "m", ["桩长"], [r"桩长\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"]),
        "pileRingCount": ("桩圈数", "圈", ["桩圈数"], [r"桩圈数\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(圈)?"]),
    }
    return {
        code: {
            "name": name,
            "value_type": "number",
            "standard_unit": unit,
            "source_types": ["paragraph"],
            "sections": {"include": ["风机基础"], "exclude": []},
            "aliases": aliases,
            "patterns": patterns,
        }
        for code, (name, unit, aliases, patterns) in specs.items()
    }


def test_box_foundation_uses_original_single_unit_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_box_foundation",
                order=1,
                caption="表9.5-1 箱变基础单台工程量表（配事故油池）",
                section_path=["箱变基础"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="工程量", row=0, col=1)],
                    [TableCell(text="混凝土", row=1, col=0), TableCell(text="12.5", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "箱变基础")
    assert [table["key"] for table in section["tables"]] == ["boxFoundationTechnical"]
    table = section["tables"][0]
    assert table["name"] == "表9.5-1 箱变基础单台工程量表（配事故油池）"
    assert table["data"] == [["混凝土", 12.5]]


def test_box_foundation_matches_generalized_original_captions(tmp_path):
    cases = [
        ("表8.5-2     箱变基础工程量表", ["项目", "工程量"], ["混凝土", "15"]),
        ("表9.5-1  箱变基础单台工程量表（配事故油池）", ["项目", "工程量"], ["混凝土", "15"]),
        ("7.3.11.风电场主要工程量清单", ["项目", "工程量"], ["箱变基础混凝土", "15"]),
    ]
    for caption, columns, row in cases:
        ast = DocumentAST(
            file_name="sample.docx",
            tables=[_table_with_caption("t_box", 1, caption, columns, row)],
        )

        exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
        section = next(section for section in exported["result"]["sections"] if section["name"] == "箱变基础")
        table = next(table for table in section["tables"] if table["key"] == "boxFoundationTechnical")
        assert table["name"] == re.sub(r"\s+", " ", caption).strip()
        assert table["data"] == [[row[0], 15]]


def test_box_foundation_original_table_matches_title_only(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_box_content_only",
                order=1,
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="工程量", row=0, col=1)],
                    [TableCell(text="箱变基础工程量表", row=1, col=0), TableCell(text="15", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "箱变基础")
    assert section["tables"] == []


def test_box_foundation_quantity_list_uses_cross_page_title_when_caption_is_stale(tmp_path):
    """跨页工程量清单被拆表且 caption 错挂时，应使用结构层命中的真实表题。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_box_title_fragment",
                order=2,
                caption="7.3.11 风电场主要工程量清单",
                section_path=["箱变基础"],
                rows=[
                    [TableCell(text="1", row=0, col=0), TableCell(text="风电机组基础工程", row=0, col=1), TableCell(text="", row=0, col=2), TableCell(text="", row=0, col=3)],
                ],
            ),
            DocumentTable(
                id="t_box_data_fragment",
                order=3,
                caption="表 7.3.4-8 风机基础工程量",
                section_path=["箱变基础"],
                meta={
                    "best_title": "7.3.11 风电场主要工程量清单",
                    "title_candidates": [
                        {
                            "source": "table_caption",
                            "text": "7.3.11 风电场主要工程量清单",
                            "score": 6.4,
                            "order": 1,
                            "crossedTable": True,
                        }
                    ],
                },
                rows=[
                    [TableCell(text="", row=0, col=0), TableCell(text="土方开挖", row=0, col=1), TableCell(text="m3", row=0, col=2), TableCell(text="6000", row=0, col=3)],
                    [TableCell(text="", row=1, col=0), TableCell(text="混凝土 C30", row=1, col=1), TableCell(text="m3", row=1, col=2), TableCell(text="427.05", row=1, col=3)],
                ],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "箱变基础")
    table = next(table for table in section["tables"] if table["key"] == "boxFoundationTechnical")

    assert table["name"] == "7.3.11 风电场主要工程量清单"
    assert table["columns"] == ["编号", "名称", "单位", "数量"]
    assert table["data"] == [["", "土方开挖", "m3", 6000], ["", "混凝土 C30", "m3", 427.05]]


def test_road_section_prefers_original_access_road_quantity_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_road", 1, "表8.6-7 -2      进站道路主要工程数量表", ["项目", "单位", "数量"], ["进站道路", "km", "0.4"]),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    table = next(table for table in section["tables"] if table["key"] == "roadTechnical")
    assert table["name"] == "表8.6-7 -2 进站道路主要工程数量表"
    assert table["columns"] == ["项目", "单位", "数量"]
    assert table["data"] == [["进站道路", "km", 0.4]]


def test_road_original_table_matches_title_only(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_road_content_only",
                order=1,
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="数量", row=0, col=1)],
                    [TableCell(text="进站道路主要工程数量表", row=1, col=0), TableCell(text="0.4", row=1, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    assert section["tables"] == []


def test_road_parameters_from_other_report_road_paragraph(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="场内通往各风机点位的运输道路约31.15km，其中20.80km为改建道路，10.35km为新建道路。场内运输道路路基宽度5.5m，路面宽度4.5m。场内通往各风机点位的检修道路约36.30km，采用泥结碎石路面。",
                order=1,
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessRoadLength"] is None
    assert fields["accessRoadSubgradeWidth"] is None
    assert fields["accessRoadPavementWidth"] is None
    assert fields["newRoadLength"] == 10.35
    assert fields["rebuiltRoadLength"] == 20.8
    assert fields["subgradeWidth"] == 5.5
    assert fields["pavementWidth"] == 4.5
    assert fields["siteRoadLength"] == 31.15
    assert fields["maintenanceRoadLength"] == 36.3
    assert fields["maintenanceRoadSubgradeWidth"] is None
    assert fields["maintenanceRoadPavementWidth"] is None


def test_road_parameters_do_not_read_width_as_site_length_and_accept_spaced_maintenance_length(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text=(
                    "场内运输道路路基宽度 5.5m，路面宽度 4.5m，施工完成后恢复为原状。"
                    "通往各风机点位的检修道路 约 36.30km，其中 24.04km 为改建道路，12.26km 为新建道路。"
                ),
                order=1,
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["newRoadLength"] == 12.26
    assert fields["rebuiltRoadLength"] == 24.04
    assert fields["subgradeWidth"] == 5.5
    assert fields["pavementWidth"] == 4.5
    assert fields["siteRoadLength"] is None
    assert fields["maintenanceRoadLength"] == 36.3
    assert fields["maintenanceRoadSubgradeWidth"] == 5.5
    assert fields["maintenanceRoadPavementWidth"] == 4.5


def test_road_parameters_from_access_road_width_paragraph(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="场内运输道路及进站道路设计路基宽5.5m，路面宽4.5m，两侧路肩各宽0.5m。",
                order=1,
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessRoadLength"] is None
    assert fields["accessRoadSubgradeWidth"] == 5.5
    assert fields["accessRoadPavementWidth"] == 4.5
    assert fields["newRoadLength"] is None
    assert fields["rebuiltRoadLength"] is None
    assert fields["subgradeWidth"] == 5.5
    assert fields["pavementWidth"] == 4.5
    assert fields["siteRoadLength"] is None
    assert fields["maintenanceRoadLength"] is None
    assert fields["maintenanceRoadSubgradeWidth"] is None
    assert fields["maintenanceRoadPavementWidth"] is None


def test_road_entry_length_and_offsite_traffic_description_from_text(tmp_path):
    description = "本项目场外交通运输条件较好，规划从风机组装厂一(旬邑北收费站)一包含G211国道一G342国道等一改扩建道路一新建道路-风电场场内道路一各风机点位，对外交通较为便利，满足大件设备运输要求。"
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="道靖志路属于本项目的进场道路45.3km，道路改造点18处。",
                order=1,
                section_path=["道路"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text=description,
                order=2,
                section_path=["道路"],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["siteEntryRoadLength"] == 45.3
    assert fields["accessRoadLength"] is None
    assert fields["offsiteTrafficConditionDescription"] == description.rstrip("。")


def test_road_maintenance_width_is_not_used_as_maintenance_length(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="新建施工道路（检修道路）。场内施工道路长约3.68km，扩建道路25.2km，进站道路0.02km。施工期路基宽度为5.5m，路面宽度4.5m。检修道路，按路基宽4.5m，路面宽3.5m考虑。",
                order=1,
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "道路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["siteRoadLength"] == 3.68
    assert fields["newRoadLength"] is None
    assert fields["rebuiltRoadLength"] == 25.2
    assert fields["maintenanceRoadLength"] is None
    assert fields["maintenanceRoadSubgradeWidth"] == 4.5
    assert fields["maintenanceRoadPavementWidth"] == 3.5


def test_road_maintenance_length_ignores_construction_road_parenthetical_label():
    values = ResultBuilder()._road_parameter_values_from_text(
        "新建施工道路（检修道路）长约3.68km。检修道路，按路基宽4.5m，路面宽3.5m考虑。"
    )

    assert values["maintenanceRoadLength"] is None
    assert values["maintenanceRoadSubgradeWidth"] == 4.5
    assert values["maintenanceRoadPavementWidth"] == 3.5


def test_road_maintenance_length_ignores_construction_road_matrix_label():
    values = ResultBuilder()._road_parameter_values_from_matrix([
        ["项目", "单位", "数量"],
        ["新建施工道路（检修道路）", "km", "3.68"],
        ["检修道路路基宽度", "m", "4.5"],
    ])

    assert values["maintenanceRoadLength"] is None
    assert values["maintenanceRoadSubgradeWidth"] == 4.5


def test_json_exporter_adds_source_to_every_detail_table(tmp_path):
    """Verify every table in details exposes source metadata."""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_land",
                order=1,
                caption="表10.4-1 工程征用地计算合计表",
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="面积", row=0, col=1)],
                    [TableCell(text="升压站", row=1, col=0), TableCell(text="120", row=1, col=1)],
                ],
            ),
            DocumentTable(
                id="t_earthwork",
                order=2,
                caption="表10.2-2 土石方平衡表（万m(3)）",
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="挖方", row=0, col=1), TableCell(text="填方", row=0, col=2)],
                    [TableCell(text="道路", row=1, col=0), TableCell(text="10", row=1, col=1), TableCell(text="8", row=1, col=2)],
                ],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    tables = detail_json["tableIndex"]
    assert tables
    assert all(table.get("source") for table in tables.values())
    permanent = tables["permanentLandArea"]
    assert permanent["source"]["kind"] == "document_table"
    assert permanent["sampleRows"] == [["升压站", 120]]
    earthwork = tables["earthworkBalance"]
    assert earthwork["columns"] == ["项目", "挖方", "填方"]


def test_detail_table_cells_include_original_table_coordinates(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_land",
                order=1,
                caption="表10.4-1 工程征用地计算合计表",
                section_path=["用地面积"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="面积", row=0, col=1)],
                    [TableCell(text="升压站", row=1, col=0), TableCell(text="120", row=1, col=1)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    permanent = detail_json["tableIndex"]["permanentLandArea"]
    source = permanent["source"]
    assert source["kind"] == "document_table"


def test_wind_resource_monthly_summary_cells_include_original_coordinates(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_wind_monthly",
                order=1,
                caption="表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表",
                section_path=["资源章节", "风能资源"],
                rows=[
                    [
                        TableCell(text="测风塔", row=0, col=0),
                        TableCell(text="项目", row=0, col=1),
                        TableCell(text="1", row=0, col=2),
                        TableCell(text="年均", row=0, col=3),
                    ],
                    [
                        TableCell(text="0821#", row=1, col=0),
                        TableCell(text="风速", row=1, col=1),
                        TableCell(text="6.0", row=1, col=2),
                        TableCell(text="6.42", row=1, col=3),
                    ],
                    [
                        TableCell(text="", row=2, col=0),
                        TableCell(text="风功率", row=2, col=1),
                        TableCell(text="220", row=2, col=2),
                        TableCell(text="232", row=2, col=3),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    wind_table = detail_json["tableIndex"]["windResourceSpeedPowerStatistics"]
    speed_source = wind_table["source"]
    assert wind_table["sampleRows"][0][3] == 6.42
    assert speed_source["kind"] == "document_table"
    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    assert "_cellSources" not in json.dumps(result_json, ensure_ascii=False)


def test_wind_resource_combined_fields_use_speed_power_annual_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_wind_monthly",
                order=1,
                caption="表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表",
                section_path=["资源章节", "风能资源"],
                rows=[
                    [TableCell(text="测风塔", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="1", row=0, col=2), TableCell(text="年均", row=0, col=3)],
                    [TableCell(text="0821#", row=1, col=0), TableCell(text="风速", row=1, col=1), TableCell(text="6.2", row=1, col=2), TableCell(text="6.42", row=1, col=3)],
                    [TableCell(text="", row=2, col=0), TableCell(text="风功率", row=2, col=1), TableCell(text="217", row=2, col=2), TableCell(text="232", row=2, col=3)],
                    [TableCell(text="0822#", row=3, col=0), TableCell(text="风速", row=3, col=1), TableCell(text="5.6", row=3, col=2), TableCell(text="5.75", row=3, col=3)],
                    [TableCell(text="", row=4, col=0), TableCell(text="风功率", row=4, col=1), TableCell(text="151", row=4, col=2), TableCell(text="163", row=4, col=3)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0821#", "0822#"]
    assert fields["hubHeightAnnualAverageWindSpeed"] == [6.42, 5.75]
    assert fields["hubHeightWindPowerDensity"] == [232, 163]


def test_wind_resource_combined_fields_use_sector_distribution_table_for_each_tower(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_sector",
                order=1,
                caption="表2.5.3.3-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）",
                section_path=["资源章节", "风能资源"],
                rows=[
                    [TableCell(text="测风塔", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="N", row=0, col=2), TableCell(text="NNE", row=0, col=3)],
                    [TableCell(text="0821#", row=1, col=0), TableCell(text="扇区", row=1, col=1), TableCell(text="N", row=1, col=2), TableCell(text="NNE", row=1, col=3), TableCell(text="SSE", row=1, col=4)],
                    [TableCell(text="", row=2, col=0), TableCell(text="风向（%）", row=2, col=1), TableCell(text="7.25", row=2, col=2), TableCell(text="3.61", row=2, col=3), TableCell(text="11.85", row=2, col=4)],
                    [TableCell(text="", row=3, col=0), TableCell(text="风功率（%）", row=3, col=1), TableCell(text="5.8", row=3, col=2), TableCell(text="1.58", row=3, col=3), TableCell(text="11.18", row=3, col=4)],
                    [TableCell(text="", row=4, col=0), TableCell(text="扇区", row=4, col=1), TableCell(text="S", row=4, col=2), TableCell(text="SSW", row=4, col=3), TableCell(text="NNW", row=4, col=4)],
                    [TableCell(text="", row=5, col=0), TableCell(text="风向（%）", row=5, col=1), TableCell(text="11.68", row=5, col=2), TableCell(text="7.26", row=5, col=3), TableCell(text="12.23", row=5, col=4)],
                    [TableCell(text="", row=6, col=0), TableCell(text="风功率（%）", row=6, col=1), TableCell(text="12.65", row=6, col=2), TableCell(text="8.35", row=6, col=3), TableCell(text="15.07", row=6, col=4)],
                    [TableCell(text="0822#", row=7, col=0), TableCell(text="扇区", row=7, col=1), TableCell(text="N", row=7, col=2), TableCell(text="NNE", row=7, col=3), TableCell(text="SSE", row=7, col=4)],
                    [TableCell(text="", row=8, col=0), TableCell(text="风向（%）", row=8, col=1), TableCell(text="6.3", row=8, col=2), TableCell(text="3.68", row=8, col=3), TableCell(text="8.6", row=8, col=4)],
                    [TableCell(text="", row=9, col=0), TableCell(text="风功率（%）", row=9, col=1), TableCell(text="6.57", row=9, col=2), TableCell(text="3.26", row=9, col=3), TableCell(text="6.44", row=9, col=4)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0821#", "0822#"]
    assert fields["windResourceMainWindDirections"] == ["NNW", "SSE"]
    assert fields["windResourceMainWindEnergyDirections"] == ["NNW", "N"]


def test_wind_resource_combined_fields_use_highest_turbulence_table_column(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_turbulence",
                order=1,
                caption="表2.5.2.2-1 测风塔不同高度湍流强度比较表",
                section_path=["资源章节", "风能资源"],
                rows=[
                    [TableCell(text="高度", row=0, col=0), TableCell(text="90m", row=0, col=1), TableCell(text="80m", row=0, col=2), TableCell(text="10m", row=0, col=3)],
                    [TableCell(text="0821#", row=1, col=0), TableCell(text="0.114", row=1, col=1), TableCell(text="0.117", row=1, col=2), TableCell(text="0.149", row=1, col=3)],
                    [TableCell(text="0822#", row=2, col=0), TableCell(text="0.15", row=2, col=1), TableCell(text="0.155", row=2, col=2), TableCell(text="0.192", row=2, col=3)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0821#", "0822#"]
    assert fields["representativeTurbulenceIntensity"] == [0.114, 0.15]


def test_finance_section_uses_tables_and_merges_field_values_over_zero_placeholders():
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_finance",
                order=1,
                section_path=["财务", "财务评价"],
                rows=[
                    [TableCell(text="财务评价", row=0, col=0), TableCell(text="数值", row=0, col=1)],
                    [TableCell(text="其他费用", row=1, col=0), TableCell(text="0", row=1, col=1)],
                    [TableCell(text="材料费", row=2, col=0), TableCell(text="3800", row=2, col=1)],
                ],
            )
        ],
    )
    fields = {
        "otherCost": ParsedField(
            field_code="otherCost",
            field_name="其他费用",
            value=9083.63,
            unit="万元",
            normalized_value=9083.63,
            evidence=[FieldEvidence(source_type="table", text="其他费用 9083.63")],
        ),
        "materialCost": ParsedField(
            field_code="materialCost",
            field_name="材料费",
            value=3800,
            unit="万元",
            normalized_value=3800,
            evidence=[FieldEvidence(source_type="table", text="材料费 3800")],
        ),
    }

    built = ResultBuilder().build(ast, fields)

    finance = next(section for section in built["sections"] if section["name"] == "财务")
    finance_fields = {field["fieldCode"]: field["value"] for field in finance["fields"]}
    assert "otherCost" not in finance_fields
    assert "materialCost" not in finance_fields
    assert all(value is None for value in finance_fields.values())
    assert "financialEvaluation" not in [table["key"] for table in finance["tables"]]


def test_finance_section_includes_raw_financial_indicator_summary_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_financial_indicator",
                order=1,
                caption="附表16.1  财务指标汇总表",
                section_path=["财务", "财务评价"],
                rows=[
                    [
                        TableCell(text="序号", row=0, col=0),
                        TableCell(text="指标", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数值", row=0, col=3),
                    ],
                    [
                        TableCell(text="1", row=1, col=0),
                        TableCell(text="项目投资财务内部收益率（税后）", row=1, col=1),
                        TableCell(text="%", row=1, col=2),
                        TableCell(text="7.55", row=1, col=3),
                    ],
                    [
                        TableCell(text="2", row=2, col=0),
                        TableCell(text="资本金财务内部收益率", row=2, col=1),
                        TableCell(text="%", row=2, col=2),
                        TableCell(text="12.09", row=2, col=3),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    finance = next(section for section in detail_json["sections"] if section["name"] == "财务")
    assert "financialIndicatorSummary" in [table["key"] for table in finance["tables"]]
    summary = detail_json["tableIndex"]["financialIndicatorSummary"]
    assert summary["name"] == "附表16.1 财务指标汇总表"
    assert summary["columns"] == ["序号", "指标", "单位", "数值"]
    assert summary["sampleRows"][0] == [1, "项目投资财务内部收益率（税后）", "%", 7.55]
    source = summary["source"]
    assert source["kind"] == "document_table"


def test_finance_capital_irr_fields_from_financial_indicator_summary(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_financial_indicator",
                order=1,
                caption="附表16.1  财务指标汇总表",
                section_path=["财务"],
                rows=[
                    [
                        TableCell(text="序号", row=0, col=0),
                        TableCell(text="项目", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数值", row=0, col=3),
                        TableCell(text="不含送出", row=0, col=4),
                    ],
                    [
                        TableCell(text="18", row=1, col=0),
                        TableCell(text="资本金财务内部收益率", row=1, col=1),
                        TableCell(text="%", row=1, col=2),
                        TableCell(text="12.09", row=1, col=3),
                        TableCell(text="13.56", row=1, col=4),
                    ],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["financeCapitalIrr"] == 12.09
    assert fields["financeCapitalIrrWithoutOutgoing"] == 13.56


def test_finance_capital_irr_single_value_goes_to_regular_field(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_financial_indicator",
                order=1,
                caption="附表16.1  财务指标汇总表",
                section_path=["财务"],
                rows=[
                    [
                        TableCell(text="序号", row=0, col=0),
                        TableCell(text="项目", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数值", row=0, col=3),
                    ],
                    [
                        TableCell(text="18", row=1, col=0),
                        TableCell(text="资本金财务内部收益率", row=1, col=1),
                        TableCell(text="%", row=1, col=2),
                        TableCell(text="12.09", row=1, col=3),
                    ],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["financeCapitalIrr"] == 12.09
    assert fields["financeCapitalIrrWithoutOutgoing"] is None


def test_finance_capital_irr_works_with_generic_indicator_table_title(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_financial_indicator",
                order=1,
                caption="主要财务评价指标表",
                section_path=["财务", "经济评价"],
                rows=[
                    [
                        TableCell(text="序号", row=0, col=0),
                        TableCell(text="指标", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数值", row=0, col=3),
                    ],
                    [TableCell(text="1", row=1, col=0), TableCell(text="风电系统容量", row=1, col=1), TableCell(text="MW", row=1, col=2), TableCell(text="200", row=1, col=3)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="年售电量", row=2, col=1), TableCell(text="MWh", row=2, col=2), TableCell(text="475211", row=2, col=3)],
                    [TableCell(text="3", row=3, col=0), TableCell(text="项目总投资", row=3, col=1), TableCell(text="万元", row=3, col=2), TableCell(text="129913.97", row=3, col=3)],
                    [TableCell(text="4", row=4, col=0), TableCell(text="项目投资财务内部收益率", row=4, col=1), TableCell(text="%", row=4, col=2), TableCell(text="8.76", row=4, col=3)],
                    [TableCell(text="5", row=5, col=0), TableCell(text="资本金财务内部收益率", row=5, col=1), TableCell(text="%", row=5, col=2), TableCell(text="12.09", row=5, col=3)],
                    [TableCell(text="6", row=6, col=0), TableCell(text="度电成本", row=6, col=1), TableCell(text="元/kWh", row=6, col=2), TableCell(text="0.2871", row=6, col=3)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["financeCapitalIrr"] == 12.09


def test_financial_indicator_summary_prefers_appendix_16_1_caption():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p_0001", type="paragraph", text="附表 16.1 财务指标汇总表", order=1),
            DocumentBlock(id="tb_0001", type="table", text="", order=2, meta={"table_id": "t_target"}),
        ],
        tables=[
            DocumentTable(
                id="t_decoy",
                order=0,
                caption="主要财务指标",
                section_path=["财务", "财务评价"],
                rows=[
                    [TableCell(text="指标", row=0, col=0), TableCell(text="数值", row=0, col=1)],
                    [TableCell(text="资本金财务内部收益率", row=1, col=0), TableCell(text="12.09", row=1, col=1)],
                ],
            ),
            DocumentTable(
                id="t_target",
                order=2,
                section_path=["财务", "财务评价"],
                rows=[
                    [
                        TableCell(text="序号", row=0, col=0),
                        TableCell(text="项目", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数值", row=0, col=3),
                    ],
                    [TableCell(text="1", row=1, col=0), TableCell(text="风电系统容量", row=1, col=1), TableCell(text="MW", row=1, col=2), TableCell(text="200", row=1, col=3)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="年售电量", row=2, col=1), TableCell(text="MWh", row=2, col=2), TableCell(text="475211.00", row=2, col=3)],
                    [TableCell(text="3", row=3, col=0), TableCell(text="项目总投资", row=3, col=1), TableCell(text="万元", row=3, col=2), TableCell(text="129913.97", row=3, col=3)],
                    [TableCell(text="14", row=4, col=0), TableCell(text="项目投资财务内部收益率（所得税前）", row=4, col=1), TableCell(text="%", row=4, col=2), TableCell(text="8.76", row=4, col=3)],
                    [TableCell(text="18", row=5, col=0), TableCell(text="资本金财务内部收益率", row=5, col=1), TableCell(text="%", row=5, col=2), TableCell(text="12.09", row=5, col=3)],
                    [TableCell(text="25", row=6, col=0), TableCell(text="度电成本（LCOE）", row=6, col=1), TableCell(text="元/kWh", row=6, col=2), TableCell(text="0.2871", row=6, col=3)],
                ],
            ),
        ],
    )

    structured = StructureParser().parse(ast)
    table = ResultBuilder()._financial_indicator_summary_table_from_document(structured)

    assert table is not None
    assert table["name"] == "附表 16.1 财务指标汇总表"
    assert table["data"][0] == [1, "风电系统容量", "MW", 200]
    assert table["_cellSources"][0][3]["source"]["tableId"] == "t_target"


def test_finance_sensitive_analysis_table_is_exposed_as_original_table(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(
                "t_sensitive",
                1,
                "附表16.2.7 敏感性分析表",
                ["项目", "数值"],
                ["A", "1"],
            )
        ],
    )

    finance = next(section for section in detail_json["sections"] if section["name"] == "财务")
    assert "financeSensitivityAnalysis" in [table["key"] for table in finance["tables"]]


def test_finance_fields_use_paragraphs_and_preserve_month_values():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="项目建设总工期为12个月。", order=1, section_path=["财务"]),
            DocumentBlock(id="p2", type="paragraph", text="流动资金估算指标为80元/kW，其中30%为自有资金，70%采用银行贷款，贷款年利率为3%。", order=2, section_path=["财务"]),
            DocumentBlock(id="p3", type="paragraph", text="资本金占动态投资的30%，其余的资金由银行贷款。贷款偿还期为15年，宽限期后每年按贷款等额还本利息照付，五年期及以上年贷款利率按4.2%。", order=3, section_path=["财务"]),
            DocumentBlock(id="p4", type="paragraph", text="本风电场定员为10人，人均年工资按25.57万元计，职工福利费及其他按工资总额的70%。", order=4, section_path=["财务"]),
        ],
    )
    fields = {
        "constructionPeriodYears": ParsedField(field_code="constructionPeriodYears", field_name="建设期", value=12, unit="月", normalized_value=12),
        "workingCapitalLoanRatio": ParsedField(field_code="workingCapitalLoanRatio", field_name="流动资金贷款比例", value=30, unit="%", normalized_value=30),
        "staffingCount": ParsedField(field_code="staffingCount", field_name="定员人数", value=8, unit="人", normalized_value=8),
        "staffSalary": ParsedField(field_code="staffSalary", field_name="人员工资", value=25.57, unit="万元", normalized_value=25.57),
        "welfareOtherRatio": ParsedField(field_code="welfareOtherRatio", field_name="职工福利费及其他占比", value=70, unit="%", normalized_value=70),
    }

    built = ResultBuilder().build(ast, fields)
    finance = next(section for section in built["sections"] if section["name"] == "财务")
    values = {field["fieldCode"]: field for field in finance["fields"]}

    assert values["constructionPeriodYears"]["value"] == 12
    assert values["constructionPeriodYears"]["unit"] in (None, "月", "年")
    assert values["workingCapitalLoanRatio"]["value"] == 70
    assert values["workingCapitalCapitalRatio"]["value"] == 30
    assert values["workingCapitalLoanInterestRate"]["value"] == 3
    assert values["constructionCapitalRatio"]["value"] == 30
    assert values["constructionFundLoanRatio"]["value"] == 70
    assert values["repaymentPeriod"]["value"] == 15
    assert values["annualLoanInterestRate"]["value"] == 4.2
    assert values["staffingCount"]["value"] == 10
    assert values["staffSalary"]["value"] == 25.57
    assert values["welfareOtherRatio"]["value"] == 70


def test_finance_screenshot_phrases_are_extracted_from_paragraphs():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="根据施工进度安排，项目建设总工期为12个月，其中建设期12个月，运行期20年。", order=1, section_path=["财务"]),
            DocumentBlock(id="p2", type="paragraph", text="本项目流动资金按风电机组容量估算，估算指标为80元/kW，总计1200万元，其中30%为自有资金，70%采用银行贷款，贷款年利率为3%。", order=2, section_path=["财务"]),
            DocumentBlock(id="p3", type="paragraph", text="工程固定资产静态投资为81771万元，建设资金来源为资本金和银行贷款。资本金占动态投资的30%，其余的资金由银行贷款。贷款偿还期为15年，宽限期为1年，宽限期后每年按贷款等额本利息照付，五年期及以上年贷款利率按4.2%。", order=3, section_path=["财务"]),
            DocumentBlock(id="p4", type="paragraph", text="本风电场定员为10人，人均年工资按25.57万元计，职工福利费及其他按工资总额的70%。", order=4, section_path=["财务"]),
        ],
    )

    built = ResultBuilder().build(ast, {})
    finance = next(section for section in built["sections"] if section["name"] == "财务")
    values = {field["fieldCode"]: field for field in finance["fields"]}

    assert values["constructionPeriodYears"]["value"] == 12
    assert values["workingCapitalLoanRatio"]["value"] == 70
    assert values["workingCapitalCapitalRatio"]["value"] == 30
    assert values["workingCapitalLoanInterestRate"]["value"] == 3
    assert values["constructionCapitalRatio"]["value"] == 30
    assert values["constructionFundLoanRatio"]["value"] == 70
    assert values["repaymentMethod"]["value"] == "每年按贷款等额还本利息照付"
    assert values["repaymentPeriod"]["value"] == 15
    assert values["annualLoanInterestRate"]["value"] == 4.2
    assert values["staffingCount"]["value"] == 10
    assert values["staffSalary"]["value"] == 25.57
    assert values["welfareOtherRatio"]["value"] == 70


def test_value_extractor_rejects_heading_number_fallback():
    """验证兜底抽取不会把章节号当成字段值。"""
    match = FieldMatch(
        candidate=Candidate(
            field_code="capacity",
            field_name="capacity",
            source_type="paragraph",
            text="6.3 capacity",
            score=1.0,
            field_config={"name": "capacity", "aliases": ["capacity"], "value_type": "number"},
        ),
        method="alias",
        score=1.0,
    )

    assert ValueExtractor().extract([match]) == []


def test_result_builder_matches_detail_tables_by_header_signature():
    """验证明细表匹配必须命中表头签名。"""
    builder = JsonExporter().result_builder
    spec = {
        "required_headers": ["Item", "Excavation"],
        "columns": {"item": ["Item"], "excavation": ["Excavation"]},
    }
    body_only_table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [TableCell(text="Item", row=0, col=0), TableCell(text="Remark", row=0, col=1)],
            [TableCell(text="Road", row=1, col=0), TableCell(text="Excavation 100", row=1, col=1)],
        ],
    )
    header_table = DocumentTable(
        id="t_0002",
        order=2,
        rows=[
            [TableCell(text="Item", row=0, col=0), TableCell(text="Excavation", row=0, col=1)],
            [TableCell(text="Road", row=1, col=0), TableCell(text="100", row=1, col=1)],
        ],
    )

    assert not builder._table_matches(body_only_table, "", spec)
    assert builder._table_matches(header_table, "", spec)


def test_value_extractor_fallback_starts_at_alias_not_prefix_number():
    """验证兜底抽取从别名附近开始，不取前缀编号。"""
    match = FieldMatch(
        candidate=Candidate(
            field_code="maxWindSpeed",
            field_name="max wind speed",
            source_type="paragraph",
            text="50-year max wind speed: 26.93m/s",
            score=1.0,
            field_config={
                "name": "max wind speed",
                "aliases": ["max wind speed"],
                "value_type": "number",
                "unit_aliases": ["m/s"],
                "standard_unit": "m/s",
            },
        ),
        method="alias",
        score=1.0,
    )

    extracted = ValueExtractor().extract([match])

    assert len(extracted) == 1
    assert extracted[0].raw_value == "26.93"
    assert extracted[0].unit == "m/s"


def test_normalizer_preserves_string_field_values_with_numbers():
    """验证字符串字段会保留包含数字的原值。"""
    field = ParsedField(
        field_code="ratio",
        field_name="ratio",
        value="115?8?1.25%/37kV",
        unit=None,
        normalized_value="115?8?1.25%/37kV",
        status="PASS",
    )
    normalizer = Normalizer({"ratio": {"value_type": "string"}})

    normalized = normalizer.normalize_fields({"ratio": field})["ratio"]

    assert normalized.value == "115?8?1.25%/37kV"
    assert normalized.normalized_value == "115?8?1.25%/37kV"


def test_value_extractor_filters_regex_heading_numbers():
    """验证正则抽取会过滤标题编号。"""
    match = FieldMatch(
        candidate=Candidate(
            field_code="energy",
            field_name="energy",
            source_type="paragraph",
            text="5.1 energy calculation",
            score=1.0,
            field_config={
                "name": "energy",
                "aliases": ["energy"],
                "value_type": "number",
                "patterns": [r"(?:energy).{0,40}?([0-9]+(?:\.[0-9]+)?)"],
            },
        ),
        method="alias",
        score=1.0,
    )

    assert ValueExtractor().extract([match]) == []


def test_value_extractor_reads_horizontal_header_without_row_alias():
    """验证横向表头字段无需行别名也能抽取。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [TableCell(text="Annual energy [MWh]", row=0, col=0), TableCell(text="Hours", row=0, col=1)],
            [TableCell(text="67447.2", row=1, col=0), TableCell(text="2376", row=1, col=1)],
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="annualEnergy",
            field_name="annual energy",
            source_type="table",
            text="Annual energy [MWh] | Hours\n67447.2 | 2376",
            score=1.0,
            table_id="t_0001",
            field_config={"aliases": ["Annual energy"], "value_type": "number"},
            meta={"table": table},
        ),
        method="alias",
        score=1.0,
    )

    extracted = ValueExtractor(regex_enabled=False).extract([match])

    assert len(extracted) == 1
    assert extracted[0].raw_value == "67447.2"


def test_standard_table_extractor_scopes_distribution_equipment_to_110kv_gis():
    """验证配电装置抽取限定在 110kV GIS 小段，避免串入 35kV 柜。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_0001",
                order=1,
                rows=[
                    [TableCell(text="9", row=0, col=0), TableCell(text="110kV GIS成套设备", row=0, col=1), TableCell(text="线路-变压器组间隔", row=0, col=2)],
                    [TableCell(text="", row=1, col=0), TableCell(text="", row=1, col=1), TableCell(text="三工位隔离开关TPS 126kV 2000A-40kA", row=1, col=2)],
                    [TableCell(text="", row=2, col=0), TableCell(text="", row=2, col=1), TableCell(text="电流互感器1000-2000/1A 0.2S/0.5/5P30", row=2, col=2)],
                    [TableCell(text="", row=3, col=0), TableCell(text="", row=3, col=1), TableCell(text="5/5/10VA", row=3, col=2)],
                    [TableCell(text="", row=4, col=0), TableCell(text="", row=4, col=1), TableCell(text="SF6断路器GCB 126kV,3150A,40kA/3s", row=4, col=2)],
                    [TableCell(text="14", row=5, col=0), TableCell(text="35kV开关柜", row=5, col=1), TableCell(text="", row=5, col=2)],
                    [TableCell(text="", row=6, col=0), TableCell(text="35kV主变进线柜", row=6, col=1), TableCell(text="KYN61-40.5，真空断路器，3150A,31.5kA", row=6, col=2)],
                ],
            )
        ],
    )

    specs = StandardTableExtractor().distribution_equipment_specs(ast)

    assert specs["circuitBreakerSpec"] == "GCB 126kV,3150A,40kA/3s"
    assert specs["disconnectorSpec"] == "TPS 126kV 2000A-40kA"
    assert specs["currentTransformerSpec"] == "1000-2000/1A 0.2S/0.5/5P30 5/5/10VA"


def test_standard_table_extractor_keeps_required_220kv_null_rows():
    """验证需求表里的 220kV 设备行固定保留，缺值输出 None。"""
    rows = StandardTableExtractor().distribution_equipment_rows(None, lambda _code, _with_unit=False: None)

    assert rows[-4:] == [
        {"voltageLevel": "220kV", "equipment": "断路器", "parameter": None},
        {"voltageLevel": None, "equipment": "隔离开关", "parameter": None},
        {"voltageLevel": None, "equipment": "电流互感器", "parameter": None},
        {"voltageLevel": None, "equipment": "电压互感器", "parameter": None},
    ]


def test_json_exporter_maps_table_column_key_alias_to_field_code():
    """验证标准表列 key 和内部字段 code 不一致时仍能挂上来源字段。"""
    field = ParsedField(
        field_code="hubHeightAnnualAverageWindSpeed",
        field_name="轮毂高度年平均风速",
        value=[6.42, 5.75],
        unit="m/s",
        normalized_value=[6.42, 5.75],
        evidence=[FieldEvidence(source_type="table", text="windResourceSpeedPowerStatistics detail table")],
    )

    matched = JsonExporter()._match_table_column_to_field(
        "轮毂高度平均风速m/s",
        [6.42, 5.75],
        {"hubHeightAnnualAverageWindSpeed": field},
        {},
        column_key="hubHeightAvgWindSpeed",
    )

    assert matched == "hubHeightAnnualAverageWindSpeed"

def test_value_extractor_filters_material_grade_noise_cells():
    """验证材料等级单元格会作为噪声过滤。"""
    ve = ValueExtractor()

    assert ve._looks_like_non_value_cell('C30混凝土', '备注', {'value_type': 'number'}) is True
    assert ve._looks_like_non_value_cell('HRB400钢筋', '说明', {'value_type': 'number'}) is True


def test_value_extractor_skips_summary_rows_not_normal_rows_in_long_header_tables():
    """验证长横表会跳过汇总行而不是正常数据行。"""
    table = DocumentTable(
        id="t_0001",
        order=1,
        rows=[
            [TableCell(text="Annual energy [MWh]", row=0, col=0), TableCell(text="Hours", row=0, col=1)],
            [TableCell(text="67447.2", row=1, col=0), TableCell(text="2376", row=1, col=1)],
            [TableCell(text="68000.0", row=2, col=0), TableCell(text="2400", row=2, col=1)],
            [TableCell(text="合计", row=3, col=0), TableCell(text="134447.2", row=3, col=1)],
            [TableCell(text="备注", row=4, col=0), TableCell(text="2026", row=4, col=1)],
            [TableCell(text="说明", row=5, col=0), TableCell(text="2027", row=5, col=1)],
        ],
    )
    match = FieldMatch(
        candidate=Candidate(
            field_code="annualEnergy",
            field_name="annual energy",
            source_type="table",
            text="Annual energy [MWh] | Hours\n67447.2 | 2376",
            score=1.0,
            table_id="t_0001",
            field_config={"aliases": ["Annual energy"], "value_type": "number"},
            meta={"table": table},
        ),
        method="alias",
        score=1.0,
    )

    extracted = ValueExtractor(regex_enabled=False).extract([match])

    assert extracted
    assert extracted[0].raw_value == "67447.2"


def test_result_builder_uses_cover_ocr_only_as_common_field_fallback(tmp_path):
    class FakeCoverOcr:
        def __init__(self):
            self.calls = 0

        def extract(self, file_path, ast):
            self.calls += 1
            return CoverOcrResult(
                values={
                    "designUnit": "信息产业电子第十一设计研究院科技工程股份有限公司",
                    "designUnitQualification": "甲级",
                },
                text="\u5355\u4f4d\u540d\u79f0 \u4fe1\u606f\u4ea7\u4e1a\u7535\u5b50\u7b2c\u5341\u4e00\u8bbe\u8ba1\u7814\u7a76\u9662\u79d1\u6280\u5de5\u7a0b\u80a1\u4efd\u6709\u9650\u516c\u53f8\n\u7532\u7ea7",
                image_count=1,
            )

    ast = DocumentAST(file_name="sample.docx", blocks=[])
    fake = FakeCoverOcr()

    built = ResultBuilder(cover_ocr_extractor=fake).build(ast, {}, file_path=str(tmp_path / "sample.docx"))

    assert built["parsedFields"]["designUnit"].value == "信息产业电子第十一设计研究院科技工程股份有限公司"
    assert built["parsedFields"]["designUnitQualification"].value == "甲级"
    assert built["parsedFields"]["designUnit"].evidence[0].source_type == "image"
    assert built["parsedFields"]["designUnitQualification"].evidence[0].source_type == "image"
    assert fake.calls == 1


def test_cover_ocr_reads_cover_ocr_env_limits(monkeypatch, tmp_path):
    import zipfile

    docx_path = tmp_path / "sample.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:blip r:embed="rId2"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:t>目录</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
</Relationships>"""
    with zipfile.ZipFile(docx_path, "w") as package:
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/_rels/document.xml.rels", rels_xml)
        package.writestr("word/media/image1.png", b"a" * 5000)
        package.writestr("word/media/image2.png", b"b" * 5000)

    monkeypatch.setenv("COVER_OCR_MAX_IMAGES", "1")
    extractor = CoverOcrExtractor(ocr_runner=lambda content, name: [], min_image_bytes=1)
    result = extractor.extract(str(docx_path), DocumentAST(file_name="sample.docx"))

    assert extractor.max_images == 1
    assert result.image_count == 1


def test_cover_ocr_saves_debug_images_when_enabled(tmp_path):
    import zipfile

    docx_path = tmp_path / "sample.docx"
    debug_dir = tmp_path / "debug-images"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:t>目录</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""
    with zipfile.ZipFile(docx_path, "w") as package:
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/_rels/document.xml.rels", rels_xml)
        package.writestr("word/media/image1.png", b"abcde")

    extractor = CoverOcrExtractor(ocr_runner=lambda content, name: [], debug_save_dir=debug_dir, min_image_bytes=1)
    result = extractor.extract(str(docx_path), DocumentAST(file_name="sample.docx"))

    assert result.image_count == 1
    assert (debug_dir / "01_image1.png").read_bytes() == b"abcde"


def test_cover_ocr_extracts_only_images_before_toc(tmp_path):
    import zipfile

    docx_path = tmp_path / "sample.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:t>\u76ee\u5f55</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><a:blip r:embed="rId2"/></w:drawing></w:r></w:p>
  </w:body>
</w:document>"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
</Relationships>"""
    with zipfile.ZipFile(docx_path, "w") as package:
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/_rels/document.xml.rels", rels_xml)
        package.writestr("word/media/image1.png", b"a" * 5000)
        package.writestr("word/media/image2.png", b"b" * 5000)

    calls = []

    def fake_ocr(content, name):
        calls.append((name, content[:1]))
        return ["\u5355\u4f4d\u540d\u79f0:\u4fe1\u606f\u4ea7\u4e1a\u7535\u5b50\u7b2c\u5341\u4e00\u8bbe\u8ba1\u7814\u7a76\u9662\u79d1\u6280\u5de5\u7a0b\u80a1\u4efd\u6709\u9650\u516c\u53f8", "\u7532\u7ea7"]

    result = CoverOcrExtractor(ocr_runner=fake_ocr).extract(str(docx_path), DocumentAST(file_name="sample.docx"))

    assert calls == [("word/media/image1.png", b"a")]
    assert result.values["designUnit"] == "\u4fe1\u606f\u4ea7\u4e1a\u7535\u5b50\u7b2c\u5341\u4e00\u8bbe\u8ba1\u7814\u7a76\u9662\u79d1\u6280\u5de5\u7a0b\u80a1\u4efd\u6709\u9650\u516c\u53f8"
    assert result.values["designUnitQualification"] == "\u7532\u7ea7"


def test_cover_ocr_converts_legacy_doc_before_extracting_images(monkeypatch, tmp_path):
    import zipfile

    doc_path = tmp_path / "sample.doc"
    doc_path.write_bytes(b"legacy word")

    class FakeDocument:
        def __init__(self, path):
            self.path = path

        def save(self, output_path):
            document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:t>目录</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><a:blip r:embed="rId2"/></w:drawing></w:r></w:p>
  </w:body>
</w:document>"""
            rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
</Relationships>"""
            with zipfile.ZipFile(output_path, "w") as package:
                package.writestr("word/document.xml", document_xml)
                package.writestr("word/_rels/document.xml.rels", rels_xml)
                package.writestr("word/media/image1.png", b"a" * 5000)
                package.writestr("word/media/image2.png", b"b" * 5000)

    class FakeAspose:
        Document = FakeDocument

    monkeypatch.setattr("parser_engine.output.cover_ocr.AsposeWordsLoader._load_aspose_runtime", lambda self: ("fake", FakeAspose))

    calls = []

    def fake_ocr(content, name):
        calls.append((name, content[:1]))
        return []

    result = CoverOcrExtractor(ocr_runner=fake_ocr).extract(str(doc_path), DocumentAST(file_name="sample.doc"))

    assert result.image_count == 1
    assert calls == [("word/media/image1.png", b"a")]


def test_cover_ocr_renders_pdf_pages_before_toc(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")

    class FakePixmap:
        def __init__(self, page_number):
            self.page_number = page_number

        def tobytes(self, _format):
            return f"page-{self.page_number}".encode() * 200

    class FakePage:
        def __init__(self, page_number, text, images=None):
            self.page_number = page_number
            self._text = text
            self._images = images or []

        def get_text(self, _format):
            return self._text

        def get_images(self, full=True):
            return self._images

        def get_pixmap(self, matrix=None, alpha=False):
            return FakePixmap(self.page_number)

    class FakeDoc:
        def __init__(self):
            self.pages = [
                FakePage(1, "封面", ["cover"]),
                FakePage(2, "证书", ["cert"]),
                FakePage(3, "目录\n1.1 概述....................1"),
                FakePage(4, "正文", ["body"]),
            ]
            self.page_count = len(self.pages)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def load_page(self, index):
            return self.pages[index]

    fake_fitz = types.SimpleNamespace(open=lambda path: FakeDoc(), Matrix=lambda *_args: object())
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    calls = []

    def fake_ocr(content, name):
        calls.append(name)
        if name == "pdf_page_002.png":
            return ["工程咨询单位甲级资信证书", "单位名称：西安特变电工电力设计有限责任公司", "资信等级：甲级"]
        return []

    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[DocumentBlock(id="p_0001", type="paragraph", text="目录", order=1, page=3)],
    )
    result = CoverOcrExtractor(ocr_runner=fake_ocr, min_image_bytes=1).extract(str(pdf_path), ast)

    assert calls == ["pdf_page_001.png", "pdf_page_002.png"]
    assert result.image_count == 2
    assert result.values["designUnit"] == "西安特变电工电力设计有限责任公司"
    assert result.values["designUnitQualification"] == "甲级"


def test_cover_ocr_flattens_rapidocr_txts_output():
    result = types.SimpleNamespace(txts=("工程咨询单位甲级资信证书", "资信等级：甲级"))

    assert CoverOcrExtractor()._flatten_ocr_result(result) == ["工程咨询单位甲级资信证书", "资信等级：甲级"]


def test_cover_ocr_retries_without_show_log_for_newer_paddleocr():
    calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "show_log" in kwargs:
                raise ValueError("Unknown argument: show_log")

    ocr = CoverOcrExtractor()._create_paddle_ocr(FakePaddleOCR)

    assert isinstance(ocr, FakePaddleOCR)
    assert calls == [
        {"use_angle_cls": True, "lang": "ch", "show_log": False},
        {"use_angle_cls": True, "lang": "ch"},
    ]


def test_cover_ocr_marks_paddleocr_unavailable_after_initialization_failure(monkeypatch):
    calls = []
    extractor = CoverOcrExtractor()

    def fake_create(_paddle_ocr_cls):
        calls.append(1)
        raise AttributeError("'AnalysisConfig' object has no attribute 'set_optimization_level'")

    monkeypatch.setattr(extractor, "_create_paddle_ocr", fake_create)
    monkeypatch.setitem(__import__("sys").modules, "paddleocr", type("FakeModule", (), {"PaddleOCR": object}))

    assert extractor._load_paddle_ocr() is None
    assert extractor._load_paddle_ocr() is None
    assert calls == [1]


def test_cover_ocr_extracts_consulting_certificate_unit_and_grade_when_text_is_split():
    text = "\n".join(
        [
            "工程咨询单位甲级资信证书",
            "资信类别：专业资信",
            "单位名称：信息产业电子第十一设计研究院科技工程股份有限公",
            "司",
            "统一社会信用代码：915101002019764990",
        ]
    )

    result = CoverOcrExtractor()._extract_common_fields(text)

    assert result["designUnit"] == "信息产业电子第十一设计研究院科技工程股份有限公司"
    assert result["designUnitQualification"] == "甲级"


def test_cover_ocr_extracts_grade_with_common_ocr_confusions():
    extractor = CoverOcrExtractor()

    assert extractor._design_unit_qualification_from_ocr("工程咨询单位申级资信证书") == "甲级"
    assert extractor._design_unit_qualification_from_ocr("工程咨询单位甲极资信证书") == "甲级"
    assert extractor._design_unit_qualification_from_ocr("等级：申级") == "甲级"




def _table_with_caption(table_id, order, caption, columns, row):
    return DocumentTable(
        id=table_id,
        order=order,
        caption=caption,
        rows=[
            [TableCell(text=value, row=0, col=index) for index, value in enumerate(columns)],
            [TableCell(text=value, row=1, col=index) for index, value in enumerate(row)],
        ],
    )


def _detail_sections_for_tables(tmp_path, tables):
    ast = DocumentAST(file_name="sample.docx", tables=tables)
    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    return json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))


def test_output_schema_config_controls_sections_and_original_tables():
    schema = {
        "sections": [
            {"name": "自定义章节", "fields": ["customField"], "tables": ["customOriginalTable"]},
        ],
        "fields": {"customField": {"name": "自定义字段", "unit": "MW"}},
        "table_outputs": {"customOriginalTable": {"name": "自定义原表", "headers": []}},
        "original_tables": [
            {"key": "customOriginalTable", "patterns": [r"9\.9-1.*自定义原表"]},
        ],
        "combined_tables": [],
    }
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[_table_with_caption("t_custom", 1, "表9.9-1 自定义原表", ["项目", "数值"], ["A", "10"])],
    )
    fields = {
        "customField": ParsedField(field_code="customField", field_name="自定义字段", value=200, unit="MW", normalized_value="200"),
    }

    built = ResultBuilder(output_schema=schema).build(ast, fields)

    assert [section["name"] for section in built["sections"]] == ["自定义章节"]
    section = built["sections"][0]
    assert section["fields"] == [{"fieldCode": "customField", "name": "自定义字段", "value": 200, "unit": "MW"}]
    assert section["tables"][0]["key"] == "customOriginalTable"
    assert section["tables"][0]["data"] == [["A", 10]]


def test_output_schema_can_disable_default_combined_builders():
    schema = {
        "sections": [{"name": "集电线路", "fields": [], "tables": ["collectorLineCombined"]}],
        "table_outputs": {
            "collectorLineCombined": {
                "name": "集电线路组合表",
                "headers": [{"key": "collectorVoltage", "name": "集电线路电压（kv）"}],
            }
        },
        "original_tables": [],
        "combined_tables": [],
    }
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p1", type="paragraph", text="35kV集电线路本期共建设8回。", order=1)],
    )

    built = ResultBuilder(output_schema=schema).build(ast, {})

    table = built["sections"][0]["tables"][0]
    assert table["key"] == "collectorLineCombined"
    assert table["data"] == [[None]]


def test_configured_combined_detail_field_mappings_merge_with_defaults():
    rb = ResultBuilder(
        output_schema={
            "combined_detail_field_mappings": {
                "windResourceCombined": {
                    "fields": {"windResourceTowerCodes": "自定义测风塔编号"},
                }
            }
        }
    )

    spec = rb.combined_detail_field_specs["windResourceCombined"]

    assert spec["multi"] is True
    assert spec["fields"]["windResourceTowerCodes"] == "自定义测风塔编号"
    assert spec["fields"]["windResourceAirDensities"] == "高度对应的空气密度"
    assert spec["fields"]["windResourceMainWindDirections"] == "轮毂高度处的主风向"


def test_configured_resource_table_key_patterns_extend_defaults_without_broadening_sector_match():
    rb = ResultBuilder(
        output_schema={
            "resource_table_key_patterns": [
                {"key": "windResourceTowerBasic", "patterns": [r"自定义测风塔表"]},
            ]
        }
    )

    assert rb._resource_table_key("表1 自定义测风塔表") == "windResourceTowerBasic"
    assert rb._resource_table_key("表3.1-8 测风塔基本情况表") == "windResourceTowerBasic"
    assert rb._resource_table_key("表8-1 测风塔各扇区统计表") is None
    assert rb._resource_table_key("表8-2 测风塔110m高度代表年各扇区风向和风能分布统计（%）") == "windResourceSectorDistribution"
    assert rb._resource_table_key("表2.6-16 测风塔风向风能频率统计成果表") == "windResourceDirectionEnergyFrequency"


def test_configured_electrical_secondary_table_key_patterns_extend_defaults():
    rb = ResultBuilder(
        output_schema={
            "electrical_secondary_table_key_patterns": [
                {"key": "electricalSecondaryCommunicationEquipment", "patterns": [r"调度通信设备清单"]},
            ]
        }
    )

    assert rb._electrical_secondary_table_key("表6.5-1 主要通信设备表") == "electricalSecondaryCommunicationEquipment"
    assert rb._electrical_secondary_table_key("表9 调度通信设备清单") == "electricalSecondaryCommunicationEquipment"


def test_resource_section_includes_optional_tables_for_other_report_variants(tmp_path):
    captions = [
        ("windResourceEnergyParameter2001", "表 2.6-1 2001#测风塔各高度风能参数统计成果表"),
        ("windResourceShear2001", "表 2.5-16 2001#测风塔风切变指数计算成果表"),
        ("windResourceShearB03", "表 2.5-17 B03#测风塔风切变指数计算成果表"),
        ("windResourceTurbulence10ms2001", "表 2.5-12 2001#测风塔不同高度 10m/s 湍流强度统计结果"),
        ("windResourceTurbulence15msB03", "表 2.5-14 B03#测风塔不同高度 15m/s 湍流强度统计结果"),
        ("windResourceTurbulence7123", "表2.5-12 7123#测风塔不同高度湍流计算成果表"),
        ("windResourceTurbulence6601", "表2.5-12 6601#测风塔不同高度湍流计算成果表"),
        ("windResourceTurbulence6602", "表2.5-12 6602#测风塔不同高度湍流计算成果表"),
        ("windResourceSpeedPower7123", "表2.6-1 7123#测风塔各高度实测年年平均风速及风功率密度统计表"),
        ("windResourceShear7123", "表2.5-14 7123#测风塔切变统计表"),
        ("windResourceShear6601", "表2.5-14 6601#测风塔切变统计表"),
        ("windResourceShear6602", "表2.5-14 6602#测风塔切变统计表"),
    ]
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(f"t_{key}", index, caption, ["高度", "数值"], ["100m", str(index)])
            for index, (key, caption) in enumerate(captions, start=1)
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in section["tables"]}
    for index, (key, caption) in enumerate(captions, start=1):
        assert key in tables
        assert tables[key]["name"] == caption.replace("  ", " ")
        assert tables[key]["data"] == [["100m", index]]


def test_resource_original_tables_do_not_duplicate_same_source_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_energy",
                1,
                "表 2.6-1 2001#测风塔各高度风能参数统计成果表",
                ["高度", "平均风速 m/s", "平均风功率密度 W/m²"],
                ["10m", "3.23", "38"],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    keys = [table["key"] for table in section["tables"]]
    assert "windResourceEnergyParameter2001" in keys
    assert "windResourceSpeedPowerStatistics" not in keys


def test_resource_original_table_rejects_long_body_caption_for_speed_power_table(tmp_path):
    """资源章节长正文即使包含风速/风功率密度，也不能作为原表标题。"""
    body_caption = (
        "榆林市南部、延安市北部地区为风能资源次丰富区，该区域风能成因与风能丰富区成因类似，但强度稍弱。"
        "该区域70m高度实测年平均风速在5.1～6.2m/s之间，年平均风功率密度在102～215W/m2，盛行风向主要为偏南风。"
        "此外，渭北高海拔区域也存在局部风能资源可利用区。"
    )
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_body", 1, body_caption, ["年份", "年平均风速(m/s)"], ["2023", "4.62"]),
            _table_with_caption("t_title", 2, "表 2.6-2 0822#测风塔平均风速、风功率密度统计表", ["高度", "平均风速", "平均风功率密度"], ["120m-推算", "6.1", "230"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    table = next(table for table in section["tables"] if table["key"] == "windResourceSpeedPowerStatistics")
    assert table["name"] == "表 2.6-2 0822#测风塔平均风速、风功率密度统计表"
    assert body_caption not in [table["name"] for table in section["tables"]]


def test_resource_table_name_drops_previous_figure_caption(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_turbulence",
                1,
                "图 2.5-9 7123#测风塔 140m 高度各风速段湍流强度曲线 表 2.5-12 6601#测风塔不同高度湍流强度比较表",
                ["风速段（m/s）", "样本量", "占比（%）", "平均湍流", "代表性湍流"],
                ["10", "100", "20", "0.12", "0.14"],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    table = next(table for table in section["tables"] if table["key"] == "windResourceTurbulence6601")
    assert table["name"] == "表 2.5-12 6601#测风塔不同高度湍流强度比较表"


def test_resource_table_name_drops_previous_figure_caption_before_repeatable_tower_match(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_turbulence",
                1,
                "图 2.5-9 7123#测风塔 140m 高度各风速段湍流强度曲线 表 2.5-12 6601#测风塔不同高度湍流计算成果表",
                ["高度", "样本量", "平均湍流", "代表性湍流"],
                ["140m", "100", "0.12", "0.14"],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert "windResourceTurbulence6601" in tables
    assert "windResourceTurbulence7123" not in tables
    assert tables["windResourceTurbulence6601"]["name"] == "表 2.5-12 6601#测风塔不同高度湍流计算成果表"


def test_resource_turbulence_intensity_table_and_power_density_grade(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="综合判定风电场风功率密度等级为D-2级。",
                order=1,
                section_path=["资源章节", "风电场风况综合分析"],
            )
        ],
        tables=[
            DocumentTable(
                id="t_turbulence",
                order=2,
                caption="表 2.5-12 2001#测风塔不同高度10m/s湍流强度统计结果",
                section_path=["资源章节", "湍流强度"],
                rows=[
                    [
                        TableCell(text="高度", row=0, col=0),
                        TableCell(text="平均湍流强度", row=0, col=1),
                        TableCell(text="代表湍流强度", row=0, col=2),
                    ],
                    [
                        TableCell(text="140m", row=1, col=0),
                        TableCell(text="0.068", row=1, col=1),
                        TableCell(text="0.111", row=1, col=2),
                    ],
                    [
                        TableCell(text="120m", row=2, col=0),
                        TableCell(text="0.070", row=2, col=1),
                        TableCell(text="0.121", row=2, col=2),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    tables = {table["key"]: table for table in section["tables"]}
    assert fields["windPowerDensityGrade"]["value"] == "D-2"
    assert fields["windPowerDensityGrade"]["unit"] == "级"
    assert tables["windResourceTurbulenceIntensity"]["columns"] == ["测风塔编号", "高度", "平均湍流强度", "代表性湍流强度"]
    assert tables["windResourceTurbulenceIntensity"]["data"] == [
        ["2001#", "140m", 0.068, 0.111],
        ["2001#", "120m", 0.07, 0.121],
    ]


def test_resource_original_speed_power_table_uses_tower_specific_key(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_speed_power",
                1,
                "表2.6-1 7123#测风塔各高度实测年年平均风速及风功率密度统计表",
                ["高度", "平均风速", "平均风功率密度"],
                ["140m", "6.2", "232"],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert tables["windResourceSpeedPower7123"]["name"] == "表2.6-1 7123#测风塔各高度实测年年平均风速及风功率密度统计表"
    assert tables["windResourceSpeedPower7123"]["data"] == [["140m", 6.2, 232]]


def test_resource_section_uses_generic_repeatable_rules_for_new_tower_tables(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_energy", 1, "表 2.7-3 8890#测风塔各高度风能参数统计成果表", ["高度", "风速"], ["120m", "6.8"]),
            _table_with_caption("t_shear", 2, "表 2.7-4 8890#测风塔切变统计表", ["层段", "指数"], ["90-120", "0.12"]),
            _table_with_caption("t_turb", 3, "表 2.7-5 8890#测风塔不同高度湍流计算成果表", ["高度", "湍流"], ["120m", "0.11"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert tables["windResourceEnergyParameter8890"]["data"] == [["120m", 6.8]]
    assert tables["windResourceShear8890"]["data"] == [["90-120", 0.12]]
    assert tables["windResourceTurbulence8890"]["data"] == [["120m", 0.11]]
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    trace = detail_json["tableIndex"]["windResourceShear8890"]["extractionTrace"]
    assert trace["extractionType"] == "repeatable_original_table"
    assert trace["ruleSource"] == "configs/output_schema.yaml"
    assert "切变统计表" in trace["matchedRule"]


def test_resource_core_tables_match_by_semantic_caption_without_fixed_table_number(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_basic", 1, "表3.1-8 测风塔基本情况表", ["编号", "高度"], ["M01#", "120"]),
            _table_with_caption("t_shear", 2, "表4.2-6 测风塔不同高度测风资料风切变指数统计表", ["层段", "指数"], ["90-120", "0.15"]),
            _table_with_caption("t_speed", 3, "表7-3 测风塔各高度平均风速、风功率密度统计表", ["高度", "平均风速"], ["120m", "6.9"]),
            _table_with_caption("t_sector", 4, "表8-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）", ["扇区", "风能"], ["N", "10"]),
            _table_with_caption("t_direction", 5, "表2.6-16 测风塔风向风能频率统计成果表", ["塔号", "风向", "风向频率", "风能频率"], ["0822#", "NW", "20", "21"]),
            _table_with_caption("t_turb", 6, "表9-2 测风塔不同高度湍流强度比较表", ["高度", "湍流"], ["120m", "0.12"]),
        ],
    )
    for table in ast.tables:
        table.section_path = ["资源章节"]

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert tables["windResourceTowerBasic"]["name"] == "表3.1-8 测风塔基本情况表"
    assert tables["windResourceShearStatistics"]["name"] == "表4.2-6 测风塔不同高度测风资料风切变指数统计表"
    assert tables["windResourceSpeedPowerStatistics"]["name"] == "表7-3 测风塔各高度平均风速、风功率密度统计表"
    assert tables["windResourceSectorDistribution"]["name"] == "表8-1 测风塔110m高度代表年各扇区风向和风能分布统计（%）"
    assert tables["windResourceDirectionEnergyFrequency"]["name"] == "表2.6-16 测风塔风向风能频率统计成果表"
    assert tables["windResourceTurbulenceComparison"]["name"] == "表9-2 测风塔不同高度湍流强度比较表"
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    detail_section = next(section for section in detail_json["sections"] if section["name"] == "资源章节")
    detail_table = next(table for table in detail_section["tables"] if table["key"] == "windResourceSpeedPowerStatistics")
    assert detail_table["articleLocation"]["sectionPath"] == ["资源章节"]
    assert detail_table["source"]["sectionPath"] == ["资源章节"]
    source = detail_json["tableIndex"]["windResourceTowerBasic"]["source"]
    assert source["rule"]["extractionType"] == "original_table"
    assert source["rule"]["matchedRule"] == "测风塔基本情况表"
    direction_source = detail_json["tableIndex"]["windResourceDirectionEnergyFrequency"]["source"]
    assert direction_source["rule"]["ruleSource"] == "configs/output_schema.yaml"
    assert direction_source["rule"]["matchedRule"] == "测风塔.*风向风能频率统计成果表"


def test_wind_resource_direction_frequency_table_rule_uses_max_values(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_direction",
                order=1,
                caption="表2.6-16 测风塔风向风能频率统计成果表",
                section_path=["风能资源", "结论与建议"],
                rows=[
                    [TableCell(text="塔号", row=0, col=0), TableCell(text="风向", row=0, col=1), TableCell(text="风向频率", row=0, col=2), TableCell(text="风能频率", row=0, col=3)],
                    [TableCell(text="0822#", row=1, col=0), TableCell(text="N", row=1, col=1), TableCell(text="10", row=1, col=2), TableCell(text="11", row=1, col=3)],
                    [TableCell(text="", row=2, col=0), TableCell(text="NW", row=2, col=1), TableCell(text="20", row=2, col=2), TableCell(text="21", row=2, col=3)],
                    [TableCell(text="0823#", row=3, col=0), TableCell(text="NNW", row=3, col=1), TableCell(text="30", row=3, col=2), TableCell(text="31", row=3, col=3)],
                    [TableCell(text="", row=4, col=0), TableCell(text="S", row=4, col=1), TableCell(text="5", row=4, col=2), TableCell(text="6", row=4, col=3)],
                    [TableCell(text="0824#", row=5, col=0), TableCell(text="S", row=5, col=1), TableCell(text="40", row=5, col=2), TableCell(text="10", row=5, col=3)],
                    [TableCell(text="", row=6, col=0), TableCell(text="NNW", row=6, col=1), TableCell(text="8", row=6, col=2), TableCell(text="41", row=6, col=3)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceMainWindDirections"] == ["NW", "NNW", "S"]
    assert fields["windResourceMainWindEnergyDirections"] == ["NW", "NNW", "NNW"]


def test_wind_resource_direction_frequency_grouped_header_table_uses_max_values(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_direction_grouped",
                order=1,
                caption="表2.6-16 测风塔风向风能频率统计成果表",
                section_path=["风能资源", "代表年分析"],
                rows=[
                    [TableCell(text="", row=0, col=0), TableCell(text="0822#", row=0, col=1), TableCell(text="0823#", row=0, col=2), TableCell(text="0824#", row=0, col=3), TableCell(text="", row=0, col=4), TableCell(text="", row=0, col=5), TableCell(text="", row=0, col=6)],
                    [TableCell(text="风向", row=1, col=0), TableCell(text="90m风向频率", row=1, col=1), TableCell(text="90m风能频率", row=1, col=2), TableCell(text="90m风向频率", row=1, col=3), TableCell(text="90m风能频率", row=1, col=4), TableCell(text="90m风向频率", row=1, col=5), TableCell(text="90m风能频率", row=1, col=6)],
                    [TableCell(text="N", row=2, col=0), TableCell(text="6.68", row=2, col=1), TableCell(text="7.23", row=2, col=2), TableCell(text="7.55", row=2, col=3), TableCell(text="8.37", row=2, col=4), TableCell(text="7.39", row=2, col=5), TableCell(text="10.7", row=2, col=6)],
                    [TableCell(text="NW", row=3, col=0), TableCell(text="20", row=3, col=1), TableCell(text="21", row=3, col=2), TableCell(text="4", row=3, col=3), TableCell(text="5", row=3, col=4), TableCell(text="8", row=3, col=5), TableCell(text="9", row=3, col=6)],
                    [TableCell(text="NNW", row=4, col=0), TableCell(text="10", row=4, col=1), TableCell(text="11", row=4, col=2), TableCell(text="30", row=4, col=3), TableCell(text="31", row=4, col=4), TableCell(text="9", row=4, col=5), TableCell(text="41", row=4, col=6)],
                    [TableCell(text="S", row=5, col=0), TableCell(text="5", row=5, col=1), TableCell(text="6", row=5, col=2), TableCell(text="6", row=5, col=3), TableCell(text="7", row=5, col=4), TableCell(text="40", row=5, col=5), TableCell(text="10", row=5, col=6)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceMainWindDirections"] == ["NW", "NNW", "S"]
    assert fields["windResourceMainWindEnergyDirections"] == ["NW", "NNW", "NNW"]


def test_wind_resource_shear_table_matches_generic_title_variants(tmp_path):
    """验证风速切变指数表的原表识别能覆盖 2.5-17/18/19 这类标题变体。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_shear_17",
                1,
                "表2.5-17 0823#测风塔各高度风速切变指数统计",
                ["高度", "综合值"],
                ["综合值", "0.12"],
            ),
            _table_with_caption(
                "t_shear_18",
                2,
                "表2.5-18 0823#测风塔各高度风速切变指数统计",
                ["高度", "综合值"],
                ["综合值", "0.13"],
            ),
            _table_with_caption(
                "t_shear_19",
                3,
                "表2.5-19 0824#测风塔各高度风速切变指数统计",
                ["高度", "综合值"],
                ["综合值", "0.14"],
            ),
        ],
    )
    for table in ast.tables:
        table.section_path = ["资源章节"]

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    tables = {table["key"]: table for table in resource["tables"]}
    assert tables["windResourceShearStatistics"]["name"] == "表2.5-17 0823#测风塔各高度风速切变指数统计"
    assert tables["windResourceShearStatistics"]["data"] == [["综合值", 0.12]]


def test_original_table_group_does_not_match_table_from_other_section(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_other", 1, "表3.1-8 测风塔基本情况表", ["编号", "高度"], ["M01#", "120"]),
        ],
    )
    ast.tables[0].section_path = ["财务"]

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")

    assert all(table["key"] != "windResourceTowerBasic" for table in resource["tables"])


def test_details_sections_group_rules_locations_and_combined_value_traces(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="测风塔编号为2001#，雷达测风编号B03#。", order=1, section_path=["资源章节"]),
            DocumentBlock(id="p2", type="paragraph", text="本次只采用2001#测风塔进行空气密度计算。2001#测风塔10m高度空气密度为1.085kg/m³，推算至160m高度空气密度为1.069kg/m³。", order=2, section_path=["资源章节"]),
            DocumentBlock(id="p3", type="paragraph", text="2001#测风塔160m高度主风向为ESE，主风能方向为NNW。", order=3, section_path=["资源章节"]),
            DocumentBlock(id="p4", type="paragraph", text="50年一遇最大风速取值：以上方法结果取较大值，最终为30.13m/s，小于37.5m/s。", order=4, section_path=["资源章节"]),
        ],
        tables=[
            _table_with_caption("t_basic", 5, "表3.1-8 测风塔基本情况表", ["编号", "高度"], ["2001#", "140m"]),
        ],
    )
    ast.tables[0].section_path = ["资源章节"]

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    resource = next(section for section in detail_json["sections"] if section["name"] == "资源章节")
    max_wind = next(field for field in resource["fields"] if field["fieldCode"] == "maxWindSpeed50Year")
    assert max_wind["rule"].get("matchedPattern") or max_wind["rule"].get("configuredRule")
    assert detail_json["fieldIndex"]["maxWindSpeed50Year"]["source"]["text"]
    assert "source" not in max_wind
    assert "candidates" not in max_wind
    original = next(table for table in resource["tables"] if table["tableType"] == "original_table" and "测风塔基本情况表" in str(table["source"]))
    assert original["tableType"] == "original_table"
    assert set(original) == {"key", "name", "tableType", "source", "articleLocation", "section"}
    assert original["section"] == "资源章节"
    assert original["articleLocation"]["sectionPath"] == ["资源章节"]
    density_field = next(field for field in resource["fields"] if field["fieldCode"] == "windResourceAirDensities")
    assert density_field["value"] == [1.069]
    density_trace = detail_json["fieldIndex"]["windResourceAirDensities"]
    assert density_trace["source"]["sourceType"] == "paragraph"
    assert density_trace["source"]["blockId"] == "p2"
    energy_trace = detail_json["fieldIndex"]["windResourceMainWindEnergyDirections"]
    assert energy_trace["source"]["sourceType"] == "paragraph"
    assert energy_trace["source"]["blockId"] == "p3"
    assert energy_trace["rule"]["resolver"] == "wind_resource_direction_text"
    assert "source" not in density_field
    assert not any(table["key"] == "windResourceCombined" for table in resource["tables"])


def test_land_original_section_uses_only_specified_original_table(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(
                "t_land_original",
                1,
                "表10.4-1 工程征用地计算合计表",
                ["项目", "面积"],
                ["升压站", "120"],
            )
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "用地面积")
    assert [table["key"] for table in section["tables"]] == ["permanentLandArea"]
    table = detail_json["tableIndex"]["permanentLandArea"]
    assert table["name"] == "表10.4-1 工程征用地计算合计表"
    assert table["sampleRows"] == [["升压站", 120]]


def test_land_area_section_matches_generalized_original_tables(tmp_path):
    captions = [
        ("permanentLandSummary", "表9.4-1      工程永久征地面积汇总表"),
        ("temporaryLandSummary", "表9.4-2     工程临时征地面积汇总表"),
        ("permanentLandArea", "表10.4-1  工程征用地计算合计表"),
        ("landTotalAcquisition", "9.4.1.工程总征地"),
    ]
    tables = [
        _table_with_caption(f"t_{key}", index, caption, ["项目", "面积"], ["升压站", str(index * 10)])
        for index, (key, caption) in enumerate(captions, start=1)
    ]

    detail_json = _detail_sections_for_tables(tmp_path, tables)

    section = next(section for section in detail_json["sections"] if section["name"] == "用地面积")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    for index, (key, caption) in enumerate(captions, start=1):
        table = detail_json["tableIndex"][key]
        assert table["name"] == re.sub(r"\s+", " ", caption).strip()
        assert table["sampleRows"] == [["升压站", index * 10]]


def test_land_total_acquisition_uses_matched_heading_and_adjacent_fragment(tmp_path):
    """工程总征地表 caption 错挂旧标题时，应使用命中标题并合并紧邻续表。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_land_main",
                order=2,
                caption="9.3.3 大件设备运输方案",
                section_path=["用地"],
                meta={
                    "best_title": "9.3.3 大件设备运输方案",
                    "title_candidates": [
                        {"source": "table_caption", "text": "9.3.3 大件设备运输方案", "score": 8.1, "order": 1, "crossedTable": False},
                        {"source": "styled_title", "text": "9.4.1 工程总征地", "score": 1.9, "order": 1, "crossedTable": False},
                    ],
                },
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="征地（单位 m2）", row=0, col=1), TableCell(text="长期租地（单位 m2）", row=0, col=2), TableCell(text="短期租地（单位 m2）", row=0, col=3), TableCell(text="备注", row=0, col=4)],
                    [TableCell(text="升压站", row=1, col=0), TableCell(text="4956", row=1, col=1), TableCell(text="", row=1, col=2), TableCell(text="", row=1, col=3), TableCell(text="", row=1, col=4)],
                ],
            ),
            DocumentTable(
                id="t_land_fragment",
                order=3,
                section_path=["用地"],
                rows=[
                    [TableCell(text="电缆直埋", row=0, col=0), TableCell(text="", row=0, col=1), TableCell(text="", row=0, col=2), TableCell(text="17850", row=0, col=3), TableCell(text="", row=0, col=4)],
                    [TableCell(text="合计", row=1, col=0), TableCell(text="13086", row=1, col=1), TableCell(text="79280.26", row=1, col=2), TableCell(text="119899", row=1, col=3), TableCell(text="", row=1, col=4)],
                ],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "用地面积")
    table = next(table for table in section["tables"] if table["key"] == "landTotalAcquisition")

    assert table["name"] == "9.4.1 工程总征地"
    assert table["data"] == [["升压站", 4956, "", "", ""], ["电缆直埋", "", "", 17850, ""], ["合计", 13086, 79280.26, 119899, ""]]


def test_land_area_extracts_acquisition_fields_from_total_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_land_total",
                order=1,
                caption="9.4.1 工程总征地",
                section_path=["用地面积"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="征地（单位 m2）", row=0, col=1), TableCell(text="长期租地（单位 m2）", row=0, col=2), TableCell(text="短期租地（单位 m2）", row=0, col=3)],
                    [TableCell(text="风机基础", row=1, col=0), TableCell(text="8695", row=1, col=1), TableCell(text="", row=1, col=2), TableCell(text="", row=1, col=3)],
                    [TableCell(text="箱变", row=2, col=0), TableCell(text="1200", row=2, col=1), TableCell(text="", row=2, col=2), TableCell(text="", row=2, col=3)],
                    [TableCell(text="升压站", row=3, col=0), TableCell(text="0", row=3, col=1), TableCell(text="", row=3, col=2), TableCell(text="", row=3, col=3)],
                    [TableCell(text="进站道路", row=4, col=0), TableCell(text="110", row=4, col=1), TableCell(text="0", row=4, col=2), TableCell(text="", row=4, col=3)],
                    [TableCell(text="检修道路", row=5, col=0), TableCell(text="", row=5, col=1), TableCell(text="71100", row=5, col=2), TableCell(text="", row=5, col=3)],
                    [TableCell(text="塔基础", row=6, col=0), TableCell(text="", row=6, col=1), TableCell(text="9625", row=6, col=2), TableCell(text="", row=6, col=3)],
                    [TableCell(text="吊装平台", row=7, col=0), TableCell(text="", row=7, col=1), TableCell(text="", row=7, col=2), TableCell(text="61770", row=7, col=3)],
                    [TableCell(text="施工道路", row=8, col=0), TableCell(text="", row=8, col=1), TableCell(text="", row=8, col=2), TableCell(text="314900", row=8, col=3)],
                    [TableCell(text="电缆直埋", row=9, col=0), TableCell(text="", row=9, col=1), TableCell(text="", row=9, col=2), TableCell(text="17850", row=9, col=3)],
                    [TableCell(text="施工临建", row=10, col=0), TableCell(text="", row=10, col=1), TableCell(text="", row=10, col=2), TableCell(text="9600", row=10, col=3)],
                    [TableCell(text="合计", row=11, col=0), TableCell(text="18630", row=11, col=1), TableCell(text="118.92", row=11, col=2), TableCell(text="179.85", row=11, col=3)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "用地面积")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["permanentLandTotalArea"] == 18630
    assert fields["permanentLandWindFoundationArea"] == 8695
    assert fields["permanentLandBoxTransformerArea"] == 1200
    assert fields["permanentLandSubstationArea"] == 0
    assert fields["permanentLandAccessRoadArea"] == 110
    assert fields["longTermLeaseTotalArea"] == 118.92
    assert fields["longTermLeaseMaintenanceRoadArea"] == 71100
    assert fields["longTermLeaseAccessRoadArea"] == 0
    assert fields["longTermLeaseTowerFoundationArea"] == 9625
    assert fields["temporaryLandTotalArea"] == 179.85
    assert fields["temporaryLandPlatformArea"] == 61770
    assert fields["temporaryLandConstructionRoadArea"] == 314900
    assert fields["temporaryLandDirectBuriedCableArea"] == 17850
    assert fields["temporaryLandConstructionSiteArea"] == 9600


def test_earthwork_balance_uses_styled_title_when_caption_is_stale_and_merges_fragment(tmp_path):
    """土石方表 caption 错挂上一节标题时，应使用表前样式标题并合并紧邻续表。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_earthwork_main",
                order=2,
                caption="9.2.5 施工供水、供电及建筑材料",
                section_path=["土石方平衡"],
                meta={
                    "best_title": "9.2.5 施工供水、供电及建筑材料",
                    "title_candidates": [
                        {"source": "table_caption", "text": "9.2.5 施工供水、供电及建筑材料", "score": 8.1, "order": 1, "crossedTable": False},
                        # Word 转换后常把真实标题保留成表前样式段落，而不是 table.caption。
                        {"source": "styled_title", "text": "9.2.6 场内土石方平衡", "score": 3.7, "order": 1, "crossedTable": False},
                    ],
                },
                rows=[
                    [TableCell(text="", row=0, col=0), TableCell(text="", row=0, col=1), TableCell(text="开挖", row=0, col=2), TableCell(text="回填", row=0, col=3), TableCell(text="弃方", row=0, col=4)],
                    [TableCell(text="一", row=1, col=0), TableCell(text="机组", row=1, col=1), TableCell(text="", row=1, col=2), TableCell(text="", row=1, col=3), TableCell(text="", row=1, col=4)],
                    [TableCell(text="1", row=2, col=0), TableCell(text="风机基础", row=2, col=1), TableCell(text="29219.48", row=2, col=2), TableCell(text="13219.48", row=2, col=3), TableCell(text="16000", row=2, col=4)],
                ],
            ),
            DocumentTable(
                id="t_earthwork_fragment",
                order=3,
                caption="本工程土石方开挖量主要来源：场区道路开挖。",
                section_path=["土石方平衡"],
                rows=[
                    [TableCell(text="五", row=0, col=0), TableCell(text="升压站", row=0, col=1), TableCell(text="", row=0, col=2), TableCell(text="", row=0, col=3), TableCell(text="0", row=0, col=4)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="升压站", row=1, col=1), TableCell(text="7300", row=1, col=2), TableCell(text="6300", row=1, col=3), TableCell(text="1000", row=1, col=4)],
                    [TableCell(text="", row=2, col=0), TableCell(text="合计", row=2, col=1), TableCell(text="358800", row=2, col=2), TableCell(text="358800", row=2, col=3), TableCell(text="0", row=2, col=4)],
                ],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "土石方平衡")
    table = next(table for table in section["tables"] if table["key"] == "earthworkBalance")

    assert table["name"] == "9.2.6 场内土石方平衡"
    assert table["columns"] == ["col_0", "col_1", "开挖", "回填", "弃方"]
    assert table["data"] == [["一", "机组", "", "", ""], [1, "风机基础", 29219.48, 13219.48, 16000], ["五", "升压站", "", "", 0], [1, "升压站", 7300, 6300, 1000], ["", "合计", 358800, 358800, 0]]


def test_earthwork_original_section_uses_specified_original_table(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(
                "t_earthwork_original",
                1,
                "表10.2-2 土石方平衡表（万m(3)）",
                ["项目", "挖方", "填方"],
                ["道路", "10", "8"],
            )
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "土石方平衡")
    assert [table["key"] for table in section["tables"]] == ["earthworkBalance"]
    table = detail_json["tableIndex"]["earthworkBalance"]
    assert table["columns"] == ["项目", "挖方", "填方"]
    assert table["sampleRows"] == [["道路", 10, 8]]


def test_earthwork_original_section_matches_generalized_titles(tmp_path):
    captions = ["9.2.6.场内土石方平衡", "表10.2-2土石方平衡表（万m(3)）"]
    for caption in captions:
        detail_json = _detail_sections_for_tables(
            tmp_path,
            [_table_with_caption("t_earthwork_original", 1, caption, ["项目", "挖方", "填方"], ["道路", "10", "8"])],
        )

        section = next(section for section in detail_json["sections"] if section["name"] == "土石方平衡")
        assert [table["key"] for table in section["tables"]] == ["earthworkBalance"]
        table = detail_json["tableIndex"]["earthworkBalance"]
        assert table["name"] == re.sub(r"\s+", " ", caption).strip()
        assert table["sampleRows"] == [["道路", 10, 8]]


def test_earthwork_original_table_matches_title_only(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            DocumentTable(
                id="t_earthwork_content_only",
                order=1,
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="挖方", row=0, col=1)],
                    [TableCell(text="土石方平衡表", row=1, col=0), TableCell(text="10", row=1, col=1)],
                ],
            )
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "土石方平衡")
    assert section["tables"] == []


def test_earthwork_balance_falls_back_to_major_quantity_table(tmp_path):
    """没有土石方平衡标题时，从主要工程量表抽土方开挖/回填合计。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_major_quantity",
                order=1,
                rows=[
                    [
                        TableCell(text="单位电量投资(静态)", row=0, col=0),
                        TableCell(text="元/kWh", row=0, col=1),
                        TableCell(text="3.0185", row=0, col=2),
                        TableCell(text="主要工程量", row=0, col=3),
                        TableCell(text="土方开挖", row=0, col=4),
                        TableCell(text="万m³", row=0, col=5),
                        TableCell(text="14.99", row=0, col=6),
                    ],
                    [
                        TableCell(text="静态总投资", row=1, col=0),
                        TableCell(text="万元", row=1, col=1),
                        TableCell(text="81771.00", row=1, col=2),
                        TableCell(text="", row=1, col=3),
                        TableCell(text="土方回填", row=1, col=4),
                        TableCell(text="万m³", row=1, col=5),
                        TableCell(text="14.99", row=1, col=6),
                    ],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    section = next(section for section in exported["result"]["sections"] if section["name"] == "土石方平衡")
    table = next(table for table in section["tables"] if table["key"] == "earthworkBalance")
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))

    assert table["columns"] == ["项目", "土方开挖m³", "土方回填m³"]
    assert table["data"] == [["合计", 149900, 149900]]
    assert detail_json["tableIndex"]["earthworkBalance"]["data"] == [["合计", 149900, 149900]]


def test_earthwork_balance_reads_content_table_without_earthwork_caption(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_earthwork_content",
                order=1,
                caption="工程量表",
                section_path=["土石方平衡"],
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="土方开挖（m3）", row=0, col=1), TableCell(text="土方回填（m3）", row=0, col=2)],
                    [TableCell(text="风机基础工程（单台）", row=1, col=0), TableCell(text="2028", row=1, col=1), TableCell(text="1200", row=1, col=2)],
                    [TableCell(text="电缆工程", row=2, col=0), TableCell(text="960", row=2, col=1), TableCell(text="960", row=2, col=2)],
                    [TableCell(text="110kV升压站场地平整", row=3, col=0), TableCell(text="1500", row=3, col=1), TableCell(text="2000", row=3, col=2)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "土石方平衡")
    table = next(table for table in section["tables"] if table["key"] == "earthworkBalance")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert table["data"] == [
        ["风机基础", 2028, 1200],
        ["集电线路", 960, 960],
        ["升压站", 1500, 2000],
        ["合计", 4488, 4160],
    ]
    assert fields["windFoundationEarthworkExcavation"] == 2028
    assert fields["windFoundationEarthworkBackfill"] == 1200
    assert fields["collectorLineEarthworkExcavation"] == 960
    assert fields["collectorLineEarthworkBackfill"] == 960
    assert fields["substationEarthworkExcavation"] == 1500
    assert fields["substationEarthworkBackfill"] == 2000
    assert fields["totalEarthworkExcavation"] == 4488
    assert fields["totalEarthworkBackfill"] == 4160


def test_earthwork_balance_total_fields_prefer_explicit_total_row(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_earthwork_total",
                order=1,
                caption="表10.2-2 土石方平衡表",
                section_path=["土石方平衡"],
                rows=[
                    [TableCell(text="", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="开挖", row=0, col=2), TableCell(text="回填", row=0, col=3)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="风机基础", row=1, col=1), TableCell(text="100", row=1, col=2), TableCell(text="80", row=1, col=3)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="道路", row=2, col=1), TableCell(text="200", row=2, col=2), TableCell(text="180", row=2, col=3)],
                    [TableCell(text="", row=3, col=0), TableCell(text="合计", row=3, col=1), TableCell(text="1435448", row=3, col=2), TableCell(text="1435698", row=3, col=3)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "土石方平衡")
    table = next(table for table in section["tables"] if table["key"] == "earthworkBalance")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert table["data"][-1][-3:] == ["合计", 1435448, 1435698]
    assert fields["totalEarthworkExcavation"]["value"] == 1435448
    assert fields["totalEarthworkBackfill"]["value"] == 1435698
    assert fields["totalEarthworkExcavation"]["unit"] == "m3"
    assert fields["totalEarthworkBackfill"]["unit"] == "m3"


def test_earthwork_spoil_disposal_site_count_and_area_from_section_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="其它章节提到设置9个弃渣场，总占地面积为9999㎡。",
                order=1,
                section_path=["道路"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="本项目初步考虑设置1个弃渣场，总占地面积约6345m²。",
                order=2,
                section_path=["土石方平衡", "渣场规划"],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "土石方平衡")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["spoilDisposalSiteCount"] == {"fieldCode": "spoilDisposalSiteCount", "name": "弃渣场数量", "value": 1, "unit": "个"}
    assert fields["spoilDisposalSiteArea"] == {"fieldCode": "spoilDisposalSiteArea", "name": "弃渣场面积", "value": 6345, "unit": "m2"}


def test_investment_original_section_uses_five_specified_tables(tmp_path):
    captions = [
        ("investmentEstimate", "15.2.1 工程总概算表"),
        ("investmentConstructionAuxiliary", "15.2.2 施工辅助工程概算表"),
        ("investmentEquipmentInstallation", "15.2.3 设备及安装工程概算表"),
        ("investmentBuilding", "15.2.4 建筑工程概算表"),
        ("investmentOtherCost", "15.2.5 其他费用概算表"),
    ]
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(f"t_{key}", index, caption, ["序号", "项目"], [str(index), "A"])
            for index, (key, caption) in enumerate(captions, start=1)
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "技经概算")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    assert detail_json["tableIndex"]["investmentOtherCost"]["sampleRows"] == [[5, "A"]]


def test_investment_summary_fields_read_additional_total_rows(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_investment",
                order=1,
                caption="15.2.1 工程总概算表",
                section_path=["技经概算"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="项目名称", row=0, col=1), TableCell(text="合计（万元）", row=0, col=2)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="工程静态投资（一～五）部分合计", row=1, col=1), TableCell(text="64000", row=1, col=2)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="工程总投资（一～七）部分合计", row=2, col=1), TableCell(text="64416.67", row=2, col=2)],
                    [TableCell(text="3", row=3, col=0), TableCell(text="工程总投资合计", row=3, col=1), TableCell(text="64500", row=3, col=2)],
                    [TableCell(text="4", row=4, col=0), TableCell(text="单位千瓦静态投资（元/kW）", row=4, col=1), TableCell(text="3220.83", row=4, col=2)],
                    [TableCell(text="5", row=5, col=0), TableCell(text="单位千瓦动态投资（元/kW）", row=5, col=1), TableCell(text="3225.03", row=5, col=2)],
                    [TableCell(text="6", row=6, col=0), TableCell(text="智慧管理平台", row=6, col=1), TableCell(text="230", row=6, col=2)],
                    [TableCell(text="7", row=7, col=0), TableCell(text="110kV送出线路工程", row=7, col=1), TableCell(text="1200", row=7, col=2)],
                    [TableCell(text="8", row=8, col=0), TableCell(text="对侧间隔扩建工程", row=8, col=1), TableCell(text="500", row=8, col=2)],
                    [TableCell(text="9", row=9, col=0), TableCell(text="330kV送出线路分摊费", row=9, col=1), TableCell(text="800", row=9, col=2)],
                    [TableCell(text="10", row=10, col=0), TableCell(text="产业配套费", row=10, col=1), TableCell(text="90", row=10, col=2)],
                    [TableCell(text="11", row=11, col=0), TableCell(text="新能源场站感知设备（含螺栓预紧力在线监测系统等）", row=11, col=1), TableCell(text="310", row=11, col=2)],
                    [TableCell(text="12", row=12, col=0), TableCell(text="科技专篇", row=12, col=1), TableCell(text="60", row=12, col=2)],
                    [TableCell(text="13", row=13, col=0), TableCell(text="静态总投资（I～IV）部分合计", row=13, col=1), TableCell(text="63800", row=13, col=2)],
                    [TableCell(text="14", row=14, col=0), TableCell(text="建设期利息", row=14, col=1), TableCell(text="700", row=14, col=2)],
                    [TableCell(text="15", row=15, col=0), TableCell(text="动态总投资（I～IV）部分合计", row=15, col=1), TableCell(text="64580", row=15, col=2)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "技经概算")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["investmentStaticPartTotal"] == 64000
    assert fields["investmentTotalPartTotal"] == 64416.67
    assert fields["investmentProjectTotalCost"] == 64500
    assert fields["unitKwStaticInvestmentEstimate"] == 3220.83
    assert fields["unitKwDynamicInvestmentEstimate"] == 3225.03
    assert fields["investmentSmartManagementPlatformTotal"] == 230
    assert fields["investment110kvOutgoingLineProjectTotal"] == 1200
    assert fields["investmentOppositeBayExpansionTotal"] == 500
    assert fields["investment330kvOutgoingLineShareTotal"] == 800
    assert fields["investmentProductSupportingCostTotal"] == 90
    assert fields["investmentNewEnergyStationPerceptionEquipmentTotal"] == 310
    assert fields["investmentTechnologySpecialTotal"] == 60
    assert fields["investmentStaticTotalItoIv"] == 63800
    assert fields["investmentConstructionInterestTotal"] == 700
    assert fields["investmentDynamicTotalItoIv"] == 64580


def test_finance_insurance_rate_reads_field_data_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_finance_params",
                order=1,
                caption="财务参数表",
                section_path=["财务"],
                rows=[
                    [TableCell(text="字段", row=0, col=0), TableCell(text="数据", row=0, col=1)],
                    [TableCell(text="折旧年限（年）", row=1, col=0), TableCell(text="20", row=1, col=1)],
                    [TableCell(text="残值率（%）", row=2, col=0), TableCell(text="5", row=2, col=1)],
                    [TableCell(text="保险费率（%）", row=3, col=0), TableCell(text="0.1", row=3, col=1)],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["financeInsuranceRate"]["value"] == 0.1
    assert fields["financeInsuranceRate"]["unit"] == "%"


def test_finance_curtailment_and_grid_price_text_fields(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目限电率为5%，限电后年上网电量为27093.92万kWh，限电后等效满负荷小时数为1806h。",
                order=1,
                section_path=["财务"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="本项目上网电价按0.3345元/kWh测算。",
                order=2,
                section_path=["财务"],
            ),
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["financeCurtailmentRateSingle"]["value"] == 5
    assert fields["financeCurtailmentRateSingle"]["unit"] == "%"
    assert fields["financeCurtailmentAnnualOnGridEnergyMwh"]["value"] == 270939.2
    assert fields["financeCurtailmentAnnualOnGridEnergyMwh"]["unit"] == "MWh"
    assert fields["financeCurtailmentEquivalentFullLoadHours"]["value"] == 1806
    assert fields["financeCurtailmentEquivalentFullLoadHours"]["unit"] == "h"
    assert fields["windFarmGridPrice"]["name"] == "上网电价"
    assert fields["windFarmGridPrice"]["value"] == 0.3345
    assert fields["windFarmGridPrice"]["unit"] == "元/kWh"


def test_finance_curtailment_segment_rates_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="考虑限电率：第1年至第5年限电率为3%，第6年至第20年限电率为2%。",
                order=1,
                section_path=["财务"],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "财务")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["financeCurtailmentRateSingle"]["value"] is None
    assert fields["financeCurtailmentRateSegments"]["value"] == {"第1年至第5年": 3, "第6年至第20年": 2}
    assert fields["financeCurtailmentRateSegments"]["unit"] == "%"


def test_investment_original_section_matches_generalized_captions(tmp_path):
    captions = [
        ("investmentTechnicalEconomicIndicators", "15.3.9.1 主要技术经济指标表"),
        ("investmentEstimate", "表一     工程总概算表"),
        ("investmentConstructionAuxiliary", "表二     施工辅助工程概算表"),
        ("investmentEquipmentInstallation", "15.3.9.4 设备及安装工程概算表"),
        ("investmentBuilding", "表四      建筑工程概算表"),
        ("investmentOtherCost", "15.3.9.5 其他费用概算表"),
    ]
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(f"t_{key}", index, caption, ["序号", "项目"], [str(index), "A"])
            for index, (key, caption) in enumerate(captions, start=1)
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "技经概算")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    for index, (key, caption) in enumerate(captions, start=1):
        table = detail_json["tableIndex"][key]
        assert table["name"] == re.sub(r"\s+", " ", caption).strip()
        assert table["sampleRows"] == [[index, "A"]]


def test_investment_original_tables_match_title_only(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            DocumentTable(
                id="t_investment_content_only",
                order=1,
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="项目", row=0, col=1)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="工程总概算表", row=1, col=1)],
                ],
            )
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "技经概算")
    assert section["tables"] == []


def test_finance_original_section_uses_specified_appendix_tables(tmp_path):
    captions = [
        ("financialIndicatorSummary", "附表16.1  财务指标汇总表"),
        ("financeTotalCostEstimateContinuation", "附表16.3：总成本费用估算表（续）（人民币单位：万元）"),
        ("financeBalanceSheetContinuation", "附表16.11：资产负债表（续）（人民币单位：万元）"),
    ]
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(f"t_{key}", index, caption, ["项目", "数值"], ["A", str(index)])
            for index, (key, caption) in enumerate(captions, start=1)
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "财务")
    keys = [table["key"] for table in section["tables"]]
    assert keys == [key for key, _ in captions]
    assert detail_json["tableIndex"]["financialIndicatorSummary"]["sampleRows"] == [["A", 1]]
    assert detail_json["tableIndex"]["financeTotalCostEstimateContinuation"]["sampleRows"] == [["A", 2]]
    assert detail_json["tableIndex"]["financeBalanceSheetContinuation"]["sampleRows"] == [["A", 3]]


def test_finance_original_section_matches_generalized_appendix_numbers(tmp_path):
    captions = [
        ("financialIndicatorSummary", "附表 1：财务指标汇总表"),
        ("financeInvestmentPlanFunding", "附表2：项目总投资使用计划与资金筹措表（人民币单位：万元）"),
        ("financeTotalCostEstimate", "附表 3：总成本费用估算表（人民币单位：万元）"),
        ("financeTotalCostEstimateContinuation", "附表3：总成本费用估算表（续）（人民币单位：万元）"),
        ("financeDepreciationAmortization", "附表 4：资产折旧摊销估算表（人民币单位：万元）"),
        ("financeDepreciationAmortizationContinuation", "附表4：资产折旧摊销估算表（续）（人民币单位：万元）"),
        ("financeProfitDistribution", "附表5：利润与利润分配表（人民币单位：万元）"),
        ("financeProfitDistributionContinuation", "附表5：利润与利润分配表（续）（人民币单位：万元）"),
        ("financeLoanRepayment", "附表6：借款还本付息计划表（人民币单位：万元）"),
        ("financeLoanRepaymentContinuation", "附表6：借款还本付息计划表（续）（人民币单位：万元）"),
        ("financeCashFlowPlan", "附表7：财务计划现金流量表（人民币单位：万元）"),
        ("financeCashFlowPlanContinuation", "附表7：财务计划现金流量表（续）（人民币单位：万元）"),
        ("financeProjectInvestmentCashFlow", "附表8：项目投资现金流量表（人民币单位：万元）"),
        ("financeProjectInvestmentCashFlowContinuation", "附表8：项目投资现金流量表（续）（人民币单位：万元）"),
        ("financeCapitalCashFlow", "附表9：项目资本金现金流量表（人民币单位：万元）"),
        ("financeCapitalCashFlowContinuation", "附表9：项目资本金现金流量表（续）（人民币单位：万元）"),
        ("financeInvestorCashFlowParty1", "附表 10：投资各方现金流量表（投资方 1）（人民币单位：万元）"),
        ("financeInvestorCashFlowParty1Continuation", "附表10：投资各方现金流量表（投资方1）（续）（人民币单位：万元）"),
        ("financeBalanceSheet", "附表11：资产负债表（人民币单位：万元）"),
        ("financeBalanceSheetContinuation", "附表11：资产负债表（续）（人民币单位：万元）"),
    ]
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            _table_with_caption(f"t_{key}", index, caption, ["项目", "数值"], ["A", str(index)])
            for index, (key, caption) in enumerate(captions, start=1)
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "财务")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    assert detail_json["tableIndex"]["financeInvestorCashFlowParty1"]["sampleRows"] == [["A", 17]]
    assert detail_json["tableIndex"]["financeBalanceSheetContinuation"]["sampleRows"] == [["A", 20]]


def test_finance_original_tables_match_title_only(tmp_path):
    detail_json = _detail_sections_for_tables(
        tmp_path,
        [
            DocumentTable(
                id="t_finance_content_only",
                order=1,
                rows=[
                    [TableCell(text="项目", row=0, col=0), TableCell(text="数值", row=0, col=1)],
                    [TableCell(text="附表1：财务指标汇总表", row=1, col=0), TableCell(text="1", row=1, col=1)],
                ],
            )
        ],
    )

    section = next(section for section in detail_json["sections"] if section["name"] == "财务")
    assert section["tables"] == []


def test_finance_original_section_keeps_all_appendix_tables_when_section_path_is_noisy(tmp_path):
    """验证财务附表即使章节路径不稳，也能按标题把整套附表都抽出来。"""
    captions = [
        ("financialIndicatorSummary", "附表 1：财务指标汇总表"),
        ("financeInvestmentPlanFunding", "附表 2：项目总投资使用计划与资金筹措表（人民币单位：万元）"),
        ("financeTotalCostEstimate", "附表 3：总成本费用估算表（人民币单位：万元）"),
        ("financeTotalCostEstimateContinuation", "附表 3：总成本费用估算表（续）（人民币单位：万元）"),
        ("financeDepreciationAmortization", "附表 4：资产折旧摊销估算表（人民币单位：万元）"),
        ("financeDepreciationAmortizationContinuation", "附表 4：资产折旧摊销估算表（续）（人民币单位：万元）"),
        ("financeProfitDistribution", "附表 5：利润与利润分配表（人民币单位：万元）"),
        ("financeLoanRepayment", "附表 6：借款还本付息计划表（人民币单位：万元）"),
        ("financeLoanRepaymentContinuation", "附表 6：借款还本付息计划表（续）（人民币单位：万元）"),
        ("financeCashFlowPlan", "附表 7：财务计划现金流量表（人民币单位：万元）"),
        ("financeCashFlowPlanContinuation", "附表 7：财务计划现金流量表（续）（人民币单位：万元）"),
        ("financeProjectInvestmentCashFlow", "附表 8：项目投资现金流量表（人民币单位：万元）"),
        ("financeProjectInvestmentCashFlowContinuation", "附表 8：项目投资现金流量表（续）（人民币单位：万元）"),
        ("financeCapitalCashFlow", "附表 9：项目资本金现金流量表（人民币单位：万元）"),
        ("financeCapitalCashFlowContinuation", "附表 9：项目资本金现金流量表（续）（人民币单位：万元）"),
        ("financeInvestorCashFlowParty1", "附表 10：投资各方现金流量表（投资方 1）（人民币单位：万元）"),
        ("financeInvestorCashFlowParty1Continuation", "附表 10：投资各方现金流量表（投资方 1）（续）（人民币单位：万元）"),
        ("financeBalanceSheet", "附表 11：资产负债表（人民币单位：万元）"),
        ("financeBalanceSheetContinuation", "附表 11：资产负债表（续）（人民币单位：万元）"),
    ]
    tables = [
        _table_with_caption(f"t_{key}", index, caption, ["项目", "数值"], ["A", str(index)])
        for index, (key, caption) in enumerate(captions, start=1)
    ]
    for table in tables:
        table.section_path = ["技经概算", "财务说明", "附录"]

    detail_json = _detail_sections_for_tables(tmp_path, tables)

    section = next(section for section in detail_json["sections"] if section["name"] == "财务")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    assert detail_json["tableIndex"]["financialIndicatorSummary"]["sampleRows"] == [["A", 1]]
    assert detail_json["tableIndex"]["financeBalanceSheetContinuation"]["sampleRows"] == [["A", 19]]


def test_common_fields_filter_bad_body_values_and_fallback_to_filename():
    ast = DocumentAST(file_name="6.陕西华电白水15万千瓦风电项目可行性研究报告.docx")
    fields = {
        "projectName": ParsedField(
            field_code="projectName",
            field_name="项目名称",
            value="箱式变电站（华变）",
            normalized_value="箱式变电站（华变）",
        ),
        "designUnit": ParsedField(
            field_code="designUnit",
            field_name="设计单位",
            value="进行专项设计确定",
            normalized_value="进行专项设计确定",
        ),
    }

    built = ResultBuilder().build(ast, fields)

    common = next(section for section in built["sections"] if section["name"] == "通用")
    values = {field["fieldCode"]: field["value"] for field in common["fields"]}
    assert values["projectName"] == "陕西华电白水15万千瓦风电项目"
    assert values["designUnit"] is None


def test_cover_ocr_overrides_bad_common_field_candidates(tmp_path):
    class FakeCoverOcr:
        def extract(self, file_path, ast):
            return CoverOcrResult(
                values={
                    "projectName": "陕西华电白水15万千瓦风电项目",
                    "designUnit": "信息产业电子第十一设计研究院科技工程股份有限公司",
                    "designUnitQualification": "甲级",
                },
                text="cover ocr",
                image_count=1,
            )

    ast = DocumentAST(file_name="sample.docx")
    fields = {
        "projectName": ParsedField(field_code="projectName", field_name="项目名称", value="箱式变电站（华变）", normalized_value="箱式变电站（华变）"),
        "designUnit": ParsedField(field_code="designUnit", field_name="设计单位", value="进行专项设计确定", normalized_value="进行专项设计确定"),
    }

    built = ResultBuilder(cover_ocr_extractor=FakeCoverOcr()).build(ast, fields, file_path=str(tmp_path / "sample.docx"))

    parsed = built["parsedFields"]
    assert parsed["projectName"].value == "陕西华电白水15万千瓦风电项目"
    assert parsed["designUnit"].value == "信息产业电子第十一设计研究院科技工程股份有限公司"
    assert parsed["designUnitQualification"].value == "甲级"
    assert parsed["projectName"].evidence[0].source_type == "image"


def test_cover_ocr_field_details_include_cover_section_path(tmp_path):
    class FakeCoverOcr:
        def extract(self, file_path, ast):
            return CoverOcrResult(values={"designUnitQualification": "甲级"}, text="工程咨询单位甲级资信证书", image_count=1)

    ast = DocumentAST(file_name="sample.docx")
    builder = ResultBuilder(cover_ocr_extractor=FakeCoverOcr())

    JsonExporter(result_builder=builder, output_dir=tmp_path).export(ParseContext(file_path=str(tmp_path / "sample.docx"), ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    section = next(section for section in detail_json["sections"] if section["name"] == "通用")
    field = next(field for field in section["fields"] if field["fieldCode"] == "designUnitQualification")
    assert field["articleLocation"]["sectionPath"] == ["封面", "资质证书"]
    assert detail_json["fieldIndex"]["designUnitQualification"]["articleLocation"]["sectionPath"] == ["封面", "资质证书"]


def test_common_fields_from_cover_text_before_toc():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="陕西华电靖边韩家沟 200MW 风电项目", order=1),
            DocumentBlock(id="p2", type="paragraph", text="可行性研究报告", order=2),
            DocumentBlock(id="p3", type="paragraph", text="北京恒华伟业科技股份有限公司", order=3),
            DocumentBlock(id="p4", type="paragraph", text="工程咨询甲级证书 甲 012019010008", order=4),
            DocumentBlock(id="p5", type="paragraph", text="工程设计甲级证书 A111012429", order=5),
            DocumentBlock(id="p6", type="paragraph", text="目录", order=6),
        ],
    )

    built = ResultBuilder().build(ast, {})

    values = built["parsedFields"]
    assert values["projectName"].value == "陕西华电靖边韩家沟200MW风电项目"
    assert values["designUnit"].value == "北京恒华伟业科技股份有限公司"
    assert values["designUnitQualification"].value == "甲级"
    assert values["designUnit"].evidence[0].source_type == "cover_text"


def test_resource_speed_power_table_uses_caption_before_table_when_caption_missing(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="表2.5.3.1-1 测风塔各高度平均风速、风功率密度统计表", order=1),
            DocumentBlock(id="tb1", type="table", text="", order=2, meta={"table_id": "t_speed_power"}),
        ],
        tables=[
            DocumentTable(
                id="t_speed_power",
                order=2,
                rows=[
                    [TableCell(text="测风塔", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="100m", row=0, col=2)],
                    [TableCell(text="0821#", row=1, col=0), TableCell(text="平均风速", row=1, col=1), TableCell(text="6.42", row=1, col=2)],
                ],
            )
        ],
    )

    detail_json = _detail_sections_for_tables(tmp_path, ast.tables)

    # Helper above only passes tables, so use exporter directly for caption-before-table context.
    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    table = detail_json["tableIndex"]["windResourceSpeedPowerStatistics"]
    assert table["columns"] == ["测风塔", "项目", "100m"]
    assert table["sampleRows"] == [["0821#", "平均风速", 6.42]]


def test_wind_resource_combined_fields_from_text_and_tower_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="根据0821#、8688#、8899#测风塔实测气温、气压资料，计算得到本项目区域空气密度分别为1.011kg/m³、1.013kg/m³、1.015kg/m³。",
                order=1,
            )
        ],
        tables=[
            DocumentTable(
                id="t_tower",
                order=2,
                caption="表2.4.1-1 测风塔基本情况表",
                rows=[
                    [TableCell(text="测风塔编号", row=0, col=0)],
                    [TableCell(text="0821#", row=1, col=0)],
                    [TableCell(text="0822#", row=2, col=0)],
                    [TableCell(text="0823#", row=3, col=0)],
                    [TableCell(text="0824#", row=4, col=0)],
                    [TableCell(text="8688#", row=5, col=0)],
                    [TableCell(text="8899#", row=6, col=0)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0821#", "0822#", "0823#", "0824#", "8688#", "8899#"]
    assert fields["windResourceAirDensities"] == [1.011, "---", "---", "---", 1.013, 1.015]
    assert fields["windResourceMainWindDirections"] == ["---", "---", "---", "---", "---", "---"]
    assert fields["windResourceMainWindEnergyDirections"] == ["---", "---", "---", "---", "---", "---"]
    assert fields["windResourceGenerationUses"] == ["是", "是", "是", "是", "是", "是"]
    assert not any(table["key"] == "windResourceCombined" for table in resource["tables"])


def test_wind_resource_combined_fields_from_summary_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本期风电场内设有一座0827#测风塔。", order=1),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="图3.2-1所示点位海拔1600m，年平均风速5.40m/s，空气密度1.05kg/m³，年平均风功率密度为137.35W/m²。由图可以看出，拟建风电场内春季风速较大，主导风向为NNW，次主导风向为S。",
                order=2,
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0827#"]
    assert fields["windResourceAirDensities"] == [1.05]
    assert fields["hubHeightAnnualAverageWindSpeed"] == [5.4]
    assert fields["hubHeightWindPowerDensity"] == [137.35]
    assert fields["windResourceMainWindDirections"] == ["NNW"]
    assert fields["windResourceGenerationUses"] == ["是"]


def test_wind_resource_combined_fields_ignore_primary_candidates(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本期风电场内设有一座0827#测风塔。", order=1),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="年平均风速5.40m/s，空气密度1.05kg/m³，年平均风功率密度为137.35W/m²。主导风向为NNW。",
                order=2,
            ),
        ],
    )
    bad_primary_field = ParsedField(
        field_code="hubHeightAnnualAverageWindSpeed",
        field_name="轮毂高度平均风速",
        value=["Speed 160 m A", 999],
        unit="m/s",
        confidence=0.9,
        evidence=[
            FieldEvidence(
                source_type="paragraph",
                text="一次抽取的错误候选",
                score=0.9,
                match_method="primary_candidate",
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(
        ParseContext(
            file_path="sample.docx",
            ast=ast,
            validated={"hubHeightAnnualAverageWindSpeed": bad_primary_field},
        )
    )

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["hubHeightAnnualAverageWindSpeed"] == [5.4]
    assert detail_json["fieldIndex"]["hubHeightAnnualAverageWindSpeed"]["source"]["matchMethod"] == "wind_resource_summary_text"


def test_wind_resource_combined_fields_from_summary_text_with_chinese_directions(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本期风电场内设有一座0888#测风塔。", order=1),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="由以上分析可知，风电场区域主风向和主风能方向一致，以东北（NE）、东东北（ENE）风的风向和风能分布频率高。根据测风塔代表年风速数据统计，0888#测风塔166m高度年平均风速为5.07m/s，风功率密度为170W/m2。测风塔120m高度15m/s风速段平均湍流强度0.109，综合风切变为0.263。",
                order=2,
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0888#"]
    assert fields["hubHeightAnnualAverageWindSpeed"] == [5.07]
    assert fields["hubHeightWindPowerDensity"] == [170]
    assert fields["windResourceMainWindDirections"] == ["东北（NE）、东东北（ENE）"]
    assert fields["windResourceMainWindEnergyDirections"] == ["东北（NE）、东东北（ENE）"]
    assert fields["representativeTurbulenceIntensity"] == [0.109]
    assert fields["windShearExponent"] == [0.263]


def test_wind_resource_combined_prefers_summary_tower_over_basic_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="根据0888#测风塔实测气温（14.1℃）、气压（97.2kPa）资料，计算得到风电场区域空气密度为1.18kg/m³。本次风电场区域空气密度采用1.18kg/m³。",
                order=1,
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="经分析，由于下垫面原因，测风塔10m～30m风切变较大，本次推算测风塔120m以上高度风速时，采用30～120m风切变值，即风切变指数取0.263。",
                order=2,
            ),
            DocumentBlock(
                id="p3",
                type="paragraph",
                text="由以上分析可知，风电场区域主风向和主风能方向一致，以东北（NE）、东东北（ENE）风的风向和风能分布频率高。根据测风塔代表年风速数据统计，0888#测风塔166m高度年平均风速为5.07m/s，风功率密度为170W/m2。测风塔120m高度15m/s风速段平均湍流强度0.109，小于0.12。",
                order=3,
            ),
        ],
        tables=[
            _table_with_caption(
                "t_basic",
                4,
                "表2.4.1-1 测风塔基本情况表",
                ["测风塔编号", "高度"],
                ["7123#", "160"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0888#"]
    assert fields["windResourceAirDensities"] == [1.18]
    assert fields["hubHeightAnnualAverageWindSpeed"] == [5.07]
    assert fields["hubHeightWindPowerDensity"] == [170]
    assert fields["windResourceMainWindDirections"] == ["东北（NE）、东东北（ENE）"]
    assert fields["windResourceMainWindEnergyDirections"] == ["东北（NE）、东东北（ENE）"]
    assert fields["representativeTurbulenceIntensity"] == [0.109]
    assert fields["windShearExponent"] == [0.263]
    assert fields["windResourceGenerationUses"] == ["是"]


def test_wind_resource_combined_single_tower_pdf_summary_blocks(tmp_path):
    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[
            DocumentBlock(
                id="p_density_intro",
                type="paragraph",
                text="根据 6972#测风塔实测气温、气压资料，计算本项目的空气密度，计算公式如下：",
                order=1,
            ),
            DocumentBlock(
                id="p_density",
                type="paragraph",
                text="式中：P 实测平均气压；R 为气体常数；T 为实测平均气温。计算得到本项目区域空气密度为 1.113kg/m3。",
                order=2,
            ),
            DocumentBlock(
                id="p_direction",
                type="paragraph",
                text="测风塔 125m 高度主风向为北西北（NNW）、东北（NE）及东东北（ENE）扇区，主风能方向为北西北（NNW）、东北（NE）及东东北（ENE）扇区，主风向与主风能方向基本一致。",
                order=3,
            ),
            DocumentBlock(
                id="p_speed",
                type="paragraph",
                text="测风塔 125m 高度代表年年平均风速为 5.463m/s，年平均风功率密度为 221W/m2。",
                order=4,
            ),
        ],
        tables=[
            _table_with_caption(
                "t_basic",
                5,
                "表 2.4.1-1 测风塔基本情况表",
                ["测风塔", "塔高（m）"],
                ["6972#", "90"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.pdf", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["6972#"]
    assert fields["windResourceAirDensities"] == [1.113]
    assert fields["hubHeightAnnualAverageWindSpeed"] == [5.463]
    assert fields["hubHeightWindPowerDensity"] == [221]
    assert fields["windResourceMainWindDirections"] == ["北西北（NNW）、东北（NE）及东东北（ENE）"]
    assert fields["windResourceMainWindEnergyDirections"] == ["北西北（NNW）、东北（NE）及东东北（ENE）"]
    assert fields["windResourceGenerationUses"] == ["是"]


def test_electrical_text_fields_from_pdf_like_blocks(tmp_path):
    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="110kV 升压站选用 2 台容量为 50MVA 的主变压器。110kV 侧拟采用单母线接线方案，35kV 侧拟采用双段母线接线形式。35kV 侧母线各安装 1 组容量为±15Mvar 动态无功补偿装置。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="经计算，本次在升压站 35kV 母线上配置 1 台容量为 500kVA 接地变。", order=2),
            DocumentBlock(id="p3", type="paragraph", text="同时 1# 接地变考虑兼带站用变，站用变容量为 315kVA，型号为 DKSC-800kVA-315kVA/35kV，2#为接地变成套装置 DKSC-500kVA-35kV。", order=3),
            DocumentBlock(id="p4", type="paragraph", text="备用电源引自站外 10kV 线路，选用 1 台容量为 315kVA 的外来变压器布置于站外。", order=4),
            DocumentBlock(id="p5", type="paragraph", text="在 110kV 升压站内，配置 2 座 30m 独立避雷针及 1 座 30m 构架避雷针进行联合保护。", order=5),
            DocumentBlock(id="p6", type="paragraph", text="蓄电池容量计算采用阶梯法，从上表得出本升压站选用一组 220V、250Ah 阀控式密封铅酸蓄电池组，单体浮充电压 2.23V。", order=6),
            DocumentBlock(id="p7", type="paragraph", text="设置 2 套 7.5kVA 双冗余互为备用的交流不间断电源装置（UPS）。", order=7),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.pdf", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    fields = {field["fieldCode"]: field["value"] for section in result_json["sections"] for field in section.get("fields", [])}
    assert fields["plannedCapacity"] == 100
    assert fields["currentCapacity"] == 100
    assert fields["stationTransformerCapacity10kv"] == "315kVA"
    assert fields["groundingTransformerCapacity35kv"] == "500kVA"
    assert fields["groundingStationTransformerCapacity35kv"] == "315kVA"
    assert fields["svgReactiveCompensationCapacity"] == "±15Mvar"
    assert fields["independentLightningRodCount"] == 2
    assert fields["frameLightningRodCount"] == 1
    assert fields["dcBatteryConfiguration"] == "一组220V、250Ah阀控式密封铅酸蓄电池组"
    assert fields["upsPowerConfiguration"] == "2套7.5kVA双冗余互为备用"


def test_communication_power_uses_pdf_page_text_fallback(tmp_path):
    ast = DocumentAST(
        file_name="sample.pdf",
        meta={
            "pdf_page_texts": [
                {
                    "page": 128,
                    "text": "6.5.5.2. 设备配置 （1）-48V/120A 高频开关电源：1 套 （2）48V/200Ah 阀控式密封铅酸蓄电池：1 组",
                }
            ]
        },
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.pdf", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    fields = {field["fieldCode"]: field["value"] for section in result_json["sections"] for field in section.get("fields", [])}
    assert fields["communicationPowerDesign"] == "48V/200Ah阀控式密封铅酸蓄电池：1组"
    assert fields["communicationPowerUnitType"] == "组"
    assert fields["communicationPowerQuantityValue"] == 1


def test_generation_section_uses_two_original_tables_and_non_wake_field(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="p1", type="paragraph", text="不考虑尾流效应的折减系数：73.65%", order=1)],
        tables=[
            _table_with_caption("t_generation", 2, "表5.3-1   风电场工程推荐方案发电量计算表", ["项目", "数值"], ["A", "1"]),
            _table_with_caption("t_single", 3, "表5.3-2   推荐机型单机发电量统计表", ["机型", "电量"], ["WTG", "100"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["nonWakeLossFactor"]["value"] == 73.65
    summary = next(table for table in section["tables"] if table["key"] == "generationSummary")
    single = next(table for table in section["tables"] if table["key"] == "singleTurbineAnnualEnergy")
    assert summary["name"] == "表5.3-1 风电场工程推荐方案发电量计算表"
    assert summary["data"] == [["A", 1]]
    assert single["name"] == "表5.3-2 推荐机型单机发电量统计表"
    assert single["data"] == [["WTG", 100]]


def test_generation_single_turbine_ignores_5_3_2b_backup_model_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_backup", 1, "表5.3-2B   备选机型单机发电量统计表", ["机型", "电量"], ["BACKUP", "200"]),
            _table_with_caption("t_selected", 2, "表5.3-2   推荐机型单机发电量统计表", ["机型", "电量"], ["SELECTED", "100"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    single = next(table for table in section["tables"] if table["key"] == "singleTurbineAnnualEnergy")
    assert single["name"] == "表5.3-2 推荐机型单机发电量统计表"
    assert single["data"] == [["SELECTED", 100]]


def test_generation_section_matches_generalized_generation_table_names(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_field", 1, "表 5.4-1 风电场工程年上网电量计算成果表", ["项目", "数值"], ["发电量", "1"]),
            _table_with_caption("t_single", 2, "表 5.4-2 单台风机年上网电量计算成果表", ["风机编号", "上网电量"], ["WTG01", "100"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert tables["generationSummary"]["name"] == "表 5.4-1 风电场工程年上网电量计算成果表"
    assert tables["generationSummary"]["data"] == [["发电量", 1]]
    assert tables["singleTurbineAnnualEnergy"]["name"] == "表 5.4-2 单台风机年上网电量计算成果表"
    assert tables["singleTurbineAnnualEnergy"]["data"] == [["WTG01", 100]]


def test_generation_tables_match_by_strong_title_when_section_path_is_noisy(tmp_path):
    """验证发电量原表可用强表题覆盖上游误挂的风资源章节路径。"""
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_generation_summary",
                1,
                "表5.3-1风电场120m轮毂高度年上网电量估算表",
                ["项目", "单位", "WTG204-6250"],
                ["年上网电量", "万kW.h", "22482.0"],
            ),
            _table_with_caption(
                "t_generation_single",
                2,
                "表5.3-4 WTG204-6250 方案各风电机组发电量成果表",
                ["标签", "X (m)", "Y (m)", "Z (m)", "年发电量 (兆瓦时/年)", "上网电量(兆瓦时/年)", "等效小时数(h)", "尾流效应导致的平均折减率(%)"],
                ["J19", "36555001", "4112572", "1776", "21897.8", "15940.5", "2550.5", "-2.9"],
            ),
        ],
    )
    for table in ast.tables:
        table.section_path = ["2 风能资源", "5.2 风电场总体布置"]

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    tables = {table["key"]: table for table in section["tables"]}
    assert tables["generationSummary"]["name"] == "表5.3-1风电场120m轮毂高度年上网电量估算表"
    assert tables["generationSummary"]["data"] == [["年上网电量", "万kW.h", 22482.0]]
    assert tables["singleTurbineAnnualEnergy"]["name"] == "表5.3-4 WTG204-6250 方案各风电机组发电量成果表"
    assert tables["singleTurbineAnnualEnergy"]["data"][0][0] == "J19"


def test_generation_summary_matches_wind_farm_generation_calculation_result_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_generation", 1, "表5.3-1  风电场发电量计算成果表", ["项目", "数值"], ["上网电量", "88"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    summary = next(table for table in section["tables"] if table["key"] == "generationSummary")
    assert summary["name"] == "表5.3-1 风电场发电量计算成果表"
    assert summary["data"] == [["上网电量", 88]]


def test_generation_section_extracts_scalar_fields_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="拟建风电场规划容量为150MW。", order=1, section_path=["发电量章节"]),
            DocumentBlock(id="p2", type="paragraph", text="综上所述，整个风电场不考虑尾流效应的折减系数为75.6%。", order=2, section_path=["发电量章节"]),
            DocumentBlock(
                id="p3",
                type="paragraph",
                text="拟建风电场安装24台单机容量为6250kW的WTG1风力发电机组，年上网电量为27093.92万kWh，年等效满负荷小时数为1806h。",
                order=3,
                section_path=["发电量章节"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["installedCapacity"]["value"] == 150
    assert fields["turbineCount"]["value"] == 24
    assert fields["turbineCapacity"]["value"] == 6250
    assert fields["nonWakeLossFactor"]["value"] == 75.6
    assert fields["gridAnnualEnergy"]["value"] == 27093.92
    assert fields["equivalentFullLoadHours"]["value"] == 1806

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    detail_section = next(section for section in detail_json["sections"] if section["name"] == "发电量章节")
    turbine_count = next(field for field in detail_section["fields"] if field["fieldCode"] == "turbineCount")
    grid_energy = next(field for field in detail_section["fields"] if field["fieldCode"] == "gridAnnualEnergy")
    assert turbine_count["rule"]["matchedPattern"] == r"(?:安装|选择安装|拟建风电场安装|拟建风电场选择安装)\s*([0-9]+)\s*台"
    assert turbine_count["rule"]["matchedText"] == "拟建风电场安装24台"
    assert grid_energy["rule"]["ruleSource"].replace("\\", "/") == "configs/fields/generation.yaml"
    assert "拟建风电场安装24台" in turbine_count["sourceText"]
    assert detail_json["fieldIndex"]["turbineCount"]["articleLocation"]["blockId"] == "p3"


def test_generation_summary_prefers_horizontal_table_energy_over_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目年上网发电量为1999.753万kWh。",
                order=1,
                section_path=["发电量章节"],
            ),
        ],
        tables=[
            _table_with_caption(
                "t_generation",
                2,
                "表5.3-1 风电场工程推荐方案发电量计算表",
                ["不考虑尾流效应的折减系数%", "年上网电量 [万kW·h]", "年等效满负荷小时数 [h]"],
                ["75.6", "27093.92", "1806"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["nonWakeLossFactor"]["value"] == 75.6
    assert fields["gridAnnualEnergy"]["value"] == 27093.92
    assert fields["equivalentFullLoadHours"]["value"] == 1806


def test_generation_text_prefers_annual_grid_energy_in_multi_metric_sentence(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目年上网发电量为1999.753万kWh。",
                order=1,
                section_path=["发电量章节"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text=(
                    "综上所述，整个风电场不考虑尾流效应的折减系数为75.6%。"
                    "拟建风电场安装24台单机容量为6250kW的WTG1风力发电机组，"
                    "轮毂高度160m，经计算本项目年理论发电量为37177.93万kWh，"
                    "平均尾流影响为5.0%，尾流后发电量为35342.97万kWh，"
                    "年上网发电量为27093.92万kWh，年等效满负荷小时数为1806h。"
                ),
                order=2,
                section_path=["发电量章节"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["nonWakeLossFactor"]["value"] == 75.6
    assert fields["turbineCount"]["value"] == 24
    assert fields["turbineCapacity"]["value"] == 6250
    assert fields["generationHubHeight"]["value"] == 160
    assert fields["generationHubHeight"]["unit"] == "m"
    assert fields["gridAnnualEnergy"]["value"] == 27093.92
    assert fields["equivalentFullLoadHours"]["value"] == 1806


def test_generation_turbine_count_sums_table_count_expression(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_generation",
                order=1,
                caption="表5.3-1 风电场工程推荐方案发电量计算表",
                section_path=["发电量章节"],
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="项目", row=0, col=1), TableCell(text="单位", row=0, col=2), TableCell(text="推荐方案 WTG200/5000", row=0, col=3)],
                    [TableCell(text="1", row=1, col=0), TableCell(text="装机容量", row=1, col=1), TableCell(text="MW", row=1, col=2), TableCell(text="200", row=1, col=3)],
                    [TableCell(text="2", row=2, col=0), TableCell(text="单机容量", row=2, col=1), TableCell(text="kW", row=2, col=2), TableCell(text="5000", row=2, col=3)],
                    [TableCell(text="3", row=3, col=0), TableCell(text="台数", row=3, col=1), TableCell(text="台", row=3, col=2), TableCell(text="30+7", row=3, col=3)],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["installedCapacity"] == 200
    assert fields["turbineCapacity"] == 5000
    assert fields["turbineCount"] == 37


def test_generation_text_field_fallback_rule_source_points_to_output_schema(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="年上网电量22482.0万kWh。",
                order=1,
                section_path=["发电量章节"],
            )
        ],
    )
    builder = ResultBuilder(field_configs={})

    JsonExporter(result_builder=builder, output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    detail_section = next(section for section in detail_json["sections"] if section["name"] == "发电量章节")
    grid_energy = next(field for field in detail_section["fields"] if field["fieldCode"] == "gridAnnualEnergy")
    assert grid_energy["rule"]["ruleSource"] == "configs/output_schema.yaml"
    assert grid_energy["rule"]["configuredRule"] == "generation_text_fields"
    assert grid_energy["rule"]["matchedPattern"] == r"年上网(?:发)?电量\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*万\s*kW\s*[·\.]?\s*h"


def test_generation_section_missing_scalar_fields_are_empty(tmp_path):
    ast = DocumentAST(file_name="sample.docx")

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    for code in ["installedCapacity", "turbineCount", "turbineCapacity", "nonWakeLossFactor", "gridAnnualEnergy", "equivalentFullLoadHours"]:
        assert fields[code]["value"] is None
    assert section["tables"] == []


def test_generation_optional_original_tables_do_not_emit_empty_placeholders(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption("t_generation", 1, "表5.3-1  风电场发电量计算成果表", ["项目", "数值"], ["上网电量", "88"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "发电量章节")
    table_keys = [table["key"] for table in section["tables"]]
    assert table_keys == ["generationSummary"]


def test_investment_tables_use_numbered_paragraph_before_table(tmp_path):
    captions = [
        ("investmentEstimate", "15.2.1工程总概算表"),
        ("investmentConstructionAuxiliary", "15.2.2 施工辅助工程概算表"),
        ("investmentEquipmentInstallation", "15.2.3设备及安装工程概算表"),
        ("investmentBuilding", "15.2.4建筑工程概算表"),
        ("investmentOtherCost", "15.2.5其他费用概算表"),
    ]
    blocks = []
    tables = []
    order = 1
    for key, caption in captions:
        blocks.append(DocumentBlock(id=f"p_{key}", type="paragraph", text=caption, order=order))
        order += 1
        tables.append(
            DocumentTable(
                id=f"t_{key}",
                order=order,
                rows=[
                    [TableCell(text="序号", row=0, col=0), TableCell(text="名称", row=0, col=1), TableCell(text="金额", row=0, col=2)],
                    [TableCell(text="1", row=1, col=0), TableCell(text=caption, row=1, col=1), TableCell(text="10", row=1, col=2)],
                ],
            )
        )
        order += 1
    ast = DocumentAST(file_name="sample.docx", blocks=blocks, tables=tables)

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    section = next(section for section in detail_json["sections"] if section["name"] == "技经概算")
    keys = [table["key"] for table in section["tables"]]
    for key, caption in captions:
        assert key in keys
        assert detail_json["tableIndex"][key]["name"] == caption
        assert detail_json["tableIndex"][key]["sampleRows"][0][2] == 10


def test_investment_basis_fields_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本工程执行《陆上风电场工程设计概算编制规定及费用标准》和《陆上风电场工程概算定额》(NB/T31010-2019)，按2024年第1季度价格水平编制。",
                order=1,
                section_path=["技经概算", "编制依据"],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "技经概算")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["investmentCostStandard"] == "《陆上风电场工程设计概算编制规定及费用标准》"
    assert fields["investmentQuotaSystem"] == "《陆上风电场工程概算定额》(NB/T31010-2019)"
    assert fields["investmentPriceLevel"] == "2024年第1季度"


def test_environment_section_extracts_investments_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本期工程所需的环境保护投资为715万元，水土保持投资为104.3万元，水保设施补偿费190.66万元。",
                order=1,
                section_path=["环保水保"],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "环保水保")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["environmentalInvestment"]["name"] == "环保总投资"
    assert fields["environmentalInvestment"]["value"] == 715
    assert fields["environmentalInvestment"]["unit"] == "万元"
    assert fields["waterSoilConservationInvestment"]["name"] == "水保总投资"
    assert fields["waterSoilConservationInvestment"]["value"] == 104.3
    assert fields["waterSoilConservationInvestment"]["unit"] == "万元"


def test_environment_section_falls_back_to_other_cost_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_other_cost",
                order=1,
                caption="15.2.5 其他费用概算表",
                section_path=["技经概算"],
                rows=[
                    [
                        TableCell(text="编号", row=0, col=0),
                        TableCell(text="工程或费用名称", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="合计（万元）", row=0, col=3),
                    ],
                    [
                        TableCell(text="4", row=1, col=0),
                        TableCell(text="环境保护", row=1, col=1),
                        TableCell(text="项", row=1, col=2),
                        TableCell(text="72.18", row=1, col=3),
                    ],
                    [
                        TableCell(text="6.1", row=2, col=0),
                        TableCell(text="水土保持补偿费", row=2, col=1),
                        TableCell(text="项", row=2, col=2),
                        TableCell(text="72.81", row=2, col=3),
                    ],
                ],
            )
        ],
    )

    exported = JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    section = next(section for section in exported["result"]["sections"] if section["name"] == "环保水保")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["environmentalInvestment"]["value"] == 72.18
    assert fields["waterSoilConservationInvestment"]["value"] == 72.81


def test_electrical_primary_combined_fields_from_paragraphs_without_original_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p0", type="paragraph", text="陕西华电靖边10万千瓦风电项目 可行性研究报告 信息产业电子第十一设计研究院科技工程股份有限公司 目录 TOC HYPERLINK PAGEREF", order=0),
            DocumentBlock(id="p1", type="paragraph", text="本项目总容量为200MW，通过主变升压后拟以一回110kV线路接至330kV曹城变电站", order=1),
            DocumentBlock(id="p2", type="paragraph", text="110kV侧拟采用简单清晰的单母线接线方案，35kV侧电气接线可采用双段母线接线形式", order=2),
            DocumentBlock(id="p3", type="paragraph", text="配置2座30m独立避雷针及1座30m构架避雷针", order=3),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 200
    assert fields["plannedCapacity"] == 200
    assert fields["currentCapacity"] == 200
    assert "110kV" in fields["connectionType"]
    assert "35kV" in fields["connectionType"]
    assert fields["independentLightningRodCount"] == 2
    assert fields["frameLightningRodCount"] == 1
    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    voltage = detail_json["fieldIndex"]["accessibleVoltage"]
    assert voltage["articleLocation"]["blockId"] == "p1"
    assert not voltage["source"]["text"].startswith("陕西华电靖边10万千瓦风电项目")


def test_electrical_primary_text_combined_does_not_use_other_section_when_sectioned(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本项目总容量为100MW，通过主变升压后拟以一回110kV线路接至330kV曹城变电站。", order=1, section_path=["资源章节"]),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    assert detail_json["fieldIndex"]["accessibleVoltage"]["status"] == "MISSING"


def test_electrical_primary_combined_fields_from_hanjiagou_paragraphs(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本项目总容量为200MW，安装30台单机容量为5.5MW和7台单机容量为5.0MW的风电机组。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="本期风电场采用8回35kV集电线路送至配套新建的110kV升压站35kV侧，升压站新建2台容量为100MVA的主变，通过主变升压后拟以一回110kV线路接至330kV曹城变电站110kV备用出线间隔。", order=2),
            DocumentBlock(id="p3", type="paragraph", text="本工程项目规划总装机容量为200MW，在场内新建1座110kV升压站。", order=3),
            DocumentBlock(id="p4", type="paragraph", text="110kV侧拟采用简单清晰的单母线接线方案，单母线接线可以满足本升压站及风电场安全运行要求。", order=4),
            DocumentBlock(id="p5", type="paragraph", text="35kV侧电气接线可采用双段母线接线形式，每台主变下设置1段35kV母线。", order=5),
            DocumentBlock(id="p6", type="paragraph", text="在110kV升压站内，配置2座30m独立避雷针及1座30m构架避雷针进行联合保护。", order=6),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 200
    assert fields["plannedCapacity"] == 200
    assert fields["currentCapacity"] == 200
    assert fields["connectionType"] == "110kV侧拟采用简单清晰的单母线接线方案\n35kV侧电气接线可采用双段母线接线形式"
    assert fields["independentLightningRodCount"] == 2
    assert fields["frameLightningRodCount"] == 1


def test_electrical_primary_additional_text_fields(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="接入系统方案：本项目以一回110kV架空线路接入330kV曹城变电站，线路长度约15.5km。",
                order=1,
                section_path=["电气一次", "接入系统方式"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="本工程在场内新建1座110kV升压站，升压站电气主接线采用110kV单母线接线。",
                order=2,
                section_path=["电气一次", "电气主接线"],
            ),
            DocumentBlock(
                id="p3",
                type="paragraph",
                text="在110kV升压站内，配置2座30m独立避雷针及1座30m构架避雷针进行联合保护。",
                order=3,
                section_path=["电气一次", "防雷接地"],
            ),
            DocumentBlock(
                id="p4",
                type="paragraph",
                text="机组变压器选用华式变电站，箱式变电站变压器型号为S20-5500/35。",
                order=4,
                section_path=["电气一次", "箱式变电站"],
            ),
            DocumentBlock(
                id="p5",
                type="paragraph",
                text="箱式变电站35kV高压侧装设熔断器和负荷开关，负荷开关浸在变压器油里，采用绝缘操作杆来操作负荷开关，可免维护。",
                order=5,
                section_path=["电气一次", "箱式变电站"],
            ),
            DocumentBlock(
                id="p6",
                type="paragraph",
                text="选用的箱式变的熔断器每台装有2只熔断器：插入式熔断器和后备保护熔断器，插入式熔断器功能是保护变压器低压侧的过载。",
                order=6,
                section_path=["电气一次", "箱式变电站"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["electricalPrimaryFrameLightningRodHeight"] == 30
    assert fields["electricalPrimaryIndependentLightningRodHeight"] == 30
    assert fields["electricalPrimaryBoxTransformerType"] == "华式变电站"
    assert fields["electricalPrimaryBoxTransformerModel"] == "S20-5500/35"
    assert fields["electricalPrimaryBoxTransformerVoltageLevel"] == 35
    assert fields["electricalPrimaryBoxTransformerCapacity"] == 5500
    assert "高压侧" in fields["electricalPrimaryBoxTransformerHighVoltageSideConfig"]
    assert "低压侧" in fields["electricalPrimaryBoxTransformerLowVoltageSideConfig"]
    assert fields["electricalPrimaryGridConnectionDistance"] == 15.5
    assert fields["electricalPrimaryGridConnectionLineType"] == "架空"
    assert fields["electricalPrimarySubstationConstructionType"] == "新建"
    assert fields["electricalPrimaryExpandedSubstationName"] is None
    assert fields["electricalPrimarySubstationVoltageLevel"] == 110


def test_electrical_primary_expanded_substation_name_from_expansion_keyword(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本工程扩建1座110kV张洪升压站，新增一台主变压器。",
                order=1,
                section_path=["电气一次", "升压站"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["electricalPrimaryExpandedSubstationName"] == "扩建-110kV张洪升压站"


def test_electrical_primary_expanded_substation_name_from_shared_station_keyword(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="本项目与相邻风电场共用一座220kV东岭升压站。",
                order=1,
                section_path=["电气一次", "接入系统"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["electricalPrimaryExpandedSubstationName"] == "扩建-220kV东岭升压站"


def test_electrical_primary_access_station_prefers_330kv_access_target(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="周边已有裕芯变电站、其它110kV变电站。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="本项目总容量为200MW，通过主变升压后拟以一回110kV线路接至330kV曹城变电站110kV备用出线间隔。", order=2),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] == "330kV曹城变电站"
    assert fields["accessibleVoltage"] == 110
    assert fields["accessibleCapacity"] == 200


def test_configured_scalar_rejects_field_label_as_value(tmp_path):
    ast = DocumentAST(file_name="sample.docx")
    validated = {
        "accessStationName": ParsedField(
            field_code="accessStationName",
            field_name="接入站名称",
            value="接入站名称",
            normalized_value="接入站名称",
        )
    }

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated=validated))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "电气一次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["accessStationName"] is None


def test_electrical_secondary_communication_power_design_from_battery_paragraph():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="6.5.5.2 设备配置", order=1),
            DocumentBlock(id="p2", type="paragraph", text="（1）-48V/120A 高频开关电源：1套", order=2),
            DocumentBlock(id="p3", type="paragraph", text="（2）48V/200Ah 阀控式密封铅酸蓄电池：1组", order=3),
        ],
    )

    built = ResultBuilder().build(ast, {})

    section = next(section for section in built["sections"] if section["name"] == "电气二次")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["communicationPowerDesign"]["value"] == "48V/200Ah阀控式密封铅酸蓄电池：1组"
    assert fields["communicationPowerUnitType"]["value"] == "组"
    assert fields["communicationPowerQuantityValue"]["value"] == 1


def test_electrical_secondary_communication_power_description_from_second_method():
    sentence = "本期为风电升压站配备高频开关电源1台，输出容量为100A的直流系统，200Ah免维护蓄电池 1 组及 1 套 DC/DC 电源转换装置。"
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="6.4.3 通信电源系统", order=1),
            DocumentBlock(id="p2", type="paragraph", text=sentence, order=2),
        ],
    )

    built = ResultBuilder().build(ast, {})

    section = next(section for section in built["sections"] if section["name"] == "电气二次")
    fields = {field["fieldCode"]: field for field in section["fields"]}
    assert fields["communicationPowerDesign"]["value"] == "200Ah免维护蓄电池1组及1套DC/DC电源转换装置"
    assert fields["communicationPowerUnitType"]["value"] == "组"
    assert fields["communicationPowerQuantityValue"]["value"] == 1
    assert fields["communicationPowerDesignDescription"]["value"] == sentence.rstrip("。")


def test_communication_power_unit_quantity_ignores_generic_dc_battery_panel():
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            DocumentTable(
                id="t_dc_battery",
                order=1,
                caption="升压站电气二次主要设备表",
                section_path=["电气二次"],
                rows=[
                    [
                        TableCell(text="名称", row=0, col=0),
                        TableCell(text="型号及规格", row=0, col=1),
                        TableCell(text="单位", row=0, col=2),
                        TableCell(text="数量", row=0, col=3),
                    ],
                    [
                        TableCell(text="蓄电池屏", row=1, col=0),
                        TableCell(text="220V/250Ah阀控式密封铅酸蓄电池", row=1, col=1),
                        TableCell(text="组", row=1, col=2),
                        TableCell(text="2", row=1, col=3),
                    ],
                ],
            )
        ],
    )

    built = ResultBuilder().build(ast, {})
    section = next(section for section in built["sections"] if section["name"] == "电气二次")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}

    assert fields["communicationPowerUnitType"] is None
    assert fields["communicationPowerQuantityValue"] is None


def test_collector_line_section_uses_six_material_original_tables(tmp_path):
    captions = [
        ("collectorElectricalMaterial", "6.6.16.1电气部分材料清册"),
        ("collectorTowerMaterial", "6.6.16.2杆塔部分材料清册"),
        ("collectorFoundationMaterial", "6.6.16.3基础部分材料清册"),
        ("collectorOpticalCableMaterial", "6.6.16.4光缆部分材料清册"),
        ("collectorCableMaterial", "6.6.16.5电缆部分材料清册"),
        ("collectorTowerGroundingMaterial", "6.6.16.6铁塔接地装置材料"),
    ]
    tables = [
        _table_with_caption(f"t_{key}", index, caption, ["序号", "名称", "数量"], [str(index), "材料", "10"])
        for index, (key, caption) in enumerate(captions, start=1)
    ]

    detail_json = _detail_sections_for_tables(tmp_path, tables)

    section = next(section for section in detail_json["sections"] if section["name"] == "集电线路")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    assert detail_json["tableIndex"]["collectorElectricalMaterial"]["sampleRows"] == [[1, "材料", 10]]
    assert detail_json["tableIndex"]["collectorTowerGroundingMaterial"]["sampleRows"] == [[6, "材料", 10]]


def test_collector_line_material_tables_match_semantic_captions_without_fixed_numbers(tmp_path):
    captions = [
        ("collectorElectricalMaterial", "7.1.2 电气部分材料清册"),
        ("collectorTowerMaterial", "7.1.3 杆塔部分材料清册"),
        ("collectorFoundationMaterial", "7.1.4 基础部分材料清册"),
        ("collectorOpticalCableMaterial", "7.1.5 光缆部分材料清册"),
        ("collectorCableMaterial", "7.1.6 电缆部分材料清册"),
        ("collectorTowerGroundingMaterial", "7.1.7 铁塔接地装置材料"),
        ("collectorMainEquipmentMaterial", "6.5.16.集电线路部分主要设备及材料清册"),
    ]
    tables = [
        _table_with_caption(f"t_{key}", index, caption, ["序号", "名称", "数量"], [str(index), "材料", "10"])
        for index, (key, caption) in enumerate(captions, start=1)
    ]

    detail_json = _detail_sections_for_tables(tmp_path, tables)

    section = next(section for section in detail_json["sections"] if section["name"] == "集电线路")
    assert [table["key"] for table in section["tables"]] == [key for key, _ in captions]
    assert detail_json["tableIndex"]["collectorMainEquipmentMaterial"]["name"] == "6.5.16.集电线路部分主要设备及材料清册"
    assert detail_json["tableIndex"]["collectorMainEquipmentMaterial"]["sampleRows"] == [[7, "材料", 10]]


def test_collector_line_combined_fields_from_route_paragraph_and_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="35kV集电线路本期共建设8回，分为A、B、C、D、E、F、G、H共八段。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="新建线路路径长约81.6km，其中双回架空线路路径长约2×3.6km，单回架空线路路径长约1×78km。", order=2),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "集电线路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["collectorVoltage"] == 35
    assert fields["circuitCount"] == 8
    assert fields["newRouteLength"] == 81.6
    assert fields["doubleCircuitOverheadRouteLength"] == "2×3.6"
    assert fields["singleCircuitOverheadRouteLength"] == "1×78"
    assert not any(table["key"] == "collectorLineCombined" for table in section["tables"])


def test_collector_line_combined_fields_use_union_headers_from_source_tables(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        tables=[
            _table_with_caption(
                "t_collector",
                1,
                "集电线路技术参数表",
                ["集电线路电压（kv）", "回路数（回）", "新建架空线路长度（km）", "新建单回路线路长度（km）", "新建双回路线路长度（km）", "新建电缆线路长度（km）"],
                ["35", "6", "40.7", "33", "7.7", "5.6"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "集电线路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["collectorVoltage"] == 35
    assert fields["circuitCount"] == 6
    assert fields["newRouteLength"] is None
    assert fields["newOverheadLineLength"] == 40.7
    assert fields["newSingleCircuitLineLength"] == 33
    assert fields["newDoubleCircuitLineLength"] == 7.7
    assert fields["newCableLineLength"] == 5.6


def test_collector_line_combined_fields_extract_total_and_cable_lengths_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="35kV集电线路本期共建设4回。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="全线集电线路路径长约41.131km，其中单回集电线路路径长约34.715km，架空路径长29.065km，箱变至终端塔电缆路径长5.65km，双回架空集电线路路径长6.116km，双回进站电缆路径长约0.3km。", order=2),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "集电线路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["collectorVoltage"] == 35
    assert fields["circuitCount"] == 4
    assert fields["totalCollectorRouteLength"] == 41.131
    assert fields["doubleCircuitOverheadRouteLength"] == 6.116
    assert fields["boxToTerminalTowerCableRouteLength"] == 5.65
    assert fields["doubleCircuitCableRouteLength"] == 0.3


def test_collector_line_text_fields_extract_cable_material_and_laying_method(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="根据35kV线路输送能力，本期建设6回35kV集电线路。新建架空线路长度约40.7km，其中新建单回路线路长度约33km，新建双回路线路长度约7.7km。",
                order=1,
                section_path=["集电线路", "建设规模"],
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="本工程采用交联聚乙烯铝芯钢带铠装聚氯乙烯护套电力电缆。",
                order=2,
                section_path=["集电线路", "电缆的选型"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "集电线路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["collectorCableCoreMaterial"] == "本工程采用交联聚乙烯铝芯钢带铠装聚氯乙烯护套电力电缆"
    assert fields["collectorLayingMethod"] == "架空+电缆直埋"


def test_collector_line_laying_method_defaults_to_direct_buried_without_overhead(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="35kV集电线路采用电缆直埋方式敷设。",
                order=1,
                section_path=["集电线路"],
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    section = next(section for section in result_json["sections"] if section["name"] == "集电线路")
    fields = {field["fieldCode"]: field["value"] for field in section["fields"]}
    assert fields["collectorLayingMethod"] == "电缆直埋"


def test_max_wind_speed_requires_50_year_context():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="普通最大风速为50m/s，不是设计值。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="50年一遇最大风速值：26.93m/s", order=2),
        ],
    )

    built = ResultBuilder().build(ast, {})

    assert built["parsedFields"]["maxWindSpeed50Year"].value == 26.93


def test_max_wind_speed_prefers_value_before_less_than_limit():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="初步估算风电场区域110m高度标准空气密度条件下50年一遇最大风速为26.93m/s，小于37.5m/s；50m～90m高度15m/s风速段平均湍流强度在0.117～0.164之间。",
                order=1,
            ),
        ],
    )

    built = ResultBuilder().build(ast, {})

    assert built["parsedFields"]["maxWindSpeed50Year"].value == 26.93


def test_max_wind_speed_uses_largest_final_value_from_multiple_methods():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="方法一：实测最大风速统计，50年一遇最大风速为24.35m/s。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="方法二：根据测风塔实测最大风速推算本风电场50年一遇最大风速，推算至160m高度为30.13m/s。", order=2),
            DocumentBlock(id="p3", type="paragraph", text="方法三：经验公式法统计，得到160m高度50年一遇最大风速为26.65m/s。", order=3),
            DocumentBlock(id="p4", type="paragraph", text="50年一遇最大风速取值：以上方法结果取较大值，最终为30.13m/s，小于37.5m/s。", order=4),
        ],
    )

    built = ResultBuilder().build(ast, {})

    assert built["parsedFields"]["maxWindSpeed50Year"].value == 30.13


def test_configured_max_wind_speed_prefers_160m_projection_across_sentences():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="根据上述公式计算，本风电场 140m 高度 50 年一遇最大风速为 30.88m/s，换算成标准空气密度下为 29.06m/s。推算至 160m 高度为 30.13m/s。",
                order=1,
                section_path=["资源章节", "第二章 风能资源"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["maxWindSpeed50Year"][1] == 30.13


def test_max_wind_speed_prefers_standard_air_density_corrected_value():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="综上，测风塔140m高度50年一遇最大10min平均风速介于25.35～33.05m/s，订正到标准空气密度下50年一遇最大10min平均风速介于23.78～31.00m/s，利用大风切变推算到160m高度为26.30～34.29m/s，订正到标准空气密度下50年一遇最大10min平均风速介于24.67～32.17m/s。根据气象站近30年实测最大风速，使用I型概率分布推算气象站位置50年一遇最大风速为24.45m/s，根据大风切变推算到轮毂高度50年一遇最大风速为35.56m/s，订正到标准空气密度下50年一遇最大风速为34.15m/s。",
                order=1,
            ),
        ],
    )

    built = ResultBuilder().build(ast, {})

    assert built["parsedFields"]["maxWindSpeed50Year"].value == 34.15


def test_wind_resource_combined_fields_can_use_air_density_text_without_tower_table(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="根据0821#、8688#、8899#测风塔实测气温、气压资料，计算本项目的空气密度，计算得到本项目区域空气密度分别为1.011kg/m³、1.013kg/m³、1.015kg/m³。",
                order=1,
            ),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["0821#", "8688#", "8899#"]
    assert fields["windResourceAirDensities"] == [1.011, 1.013, 1.015]
    assert fields["windResourceGenerationUses"] == ["是", "是", "是"]


def test_wind_resource_combined_fields_extract_density_direction_and_generation_use_from_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本次收集到风电场周边三座测风塔测风资料，测风塔编号为7123#、6601#和6602#。", order=1),
            DocumentBlock(id="p1a", type="paragraph", text="风电场6601#、6602#测风塔测风时长不足一个完整年，本次使用7123#测风塔进行分析，测风塔测得年平均气温为15.6℃，年平均气压为91.31kPa，计算得到该风电场的空气密度为1.102kg/m³。", order=2),
            DocumentBlock(id="p2", type="paragraph", text="以7123#测风塔为基准，推算至本风电场机位点平均海拔轮毂高度处的空气密度为1.078kg/m³。", order=2),
            DocumentBlock(id="p3", type="paragraph", text="7123#测风塔140m高度主导风向为NNW，次主导风向为ESE；140m高度主导风能方向为N，次主导风能方向NNW。", order=3),
            DocumentBlock(id="p4", type="paragraph", text="综合考虑本次初步选用7123#测风塔作为发电量评估的依据。", order=4),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["7123#", "6601#", "6602#"]
    assert fields["windFarmAirDensities"] == [1.102, "---", "---"]
    assert fields["windResourceAirDensities"] == [1.078, "---", "---"]
    assert fields["windResourceMainWindDirections"] == ["NNW", "---", "---"]
    assert fields["windResourceSecondaryWindDirections"] == ["ESE", "---", "---"]
    assert fields["windResourceMainWindEnergyDirections"] == ["N", "---", "---"]
    assert fields["windResourceSecondaryWindEnergyDirections"] == ["NNW", "---", "---"]
    assert fields["windResourceGenerationUses"] == ["是", "否", "否"]


def test_wind_resource_combined_fields_handle_radar_tower_report_text(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="本阶段收集到风电场周边1座塔高为140m测风塔数据，测风塔编号为2001#，雷达测风编号B03#。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="B03#测风塔数据只有两个月，本次只采用2001#测风塔进行空气密度计算。2001#测风塔10m高度空气密度为1.085kg/m³，推算至160m高度空气密度为1.069kg/m³。", order=2),
            DocumentBlock(id="p3", type="paragraph", text="通过对风电场测风数据的分析处理，根据2001#测风塔数据推算各风能要素。", order=3),
            DocumentBlock(id="p4", type="paragraph", text="2001#测风塔160m高度主风向为ESE，占比12.06%；次主风向为NNW，占比11.40%；主风能方向为NNW，占比39.43%。", order=4),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["2001#", "B03#"]
    assert fields.get("windFarmAirDensities") in (None, ["---", "---"])
    assert fields["windResourceAirDensities"] == [1.069, "---"]
    assert fields["windResourceAirDensityRecords"] == [
        {"tower_code": "2001#", "height": 10, "height_unit": "m", "value": 1.085, "unit": "kg/m³"},
        {"tower_code": "2001#", "height": 160, "height_unit": "m", "value": 1.069, "unit": "kg/m³"},
    ]
    assert fields["windResourceAirDensity10m"] == [1.085, "---"]
    assert fields["windResourceAirDensity160m"] == [1.069, "---"]
    assert fields["windResourceMainWindDirections"] == ["ESE", "---"]
    assert fields["windResourceSecondaryWindDirections"] == ["NNW", "---"]
    assert fields["windResourceMainWindEnergyDirections"] == ["NNW", "---"]
    assert fields["windResourceSecondaryWindEnergyDirections"] == ["---", "---"]
    assert fields["windResourceGenerationUses"] == ["是", "否"]


def test_wind_resource_records_support_dynamic_tower_height_and_speed_segment(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="p1",
                type="paragraph",
                text="测风塔编号为WX-TOWER_01＃。WX-TOWER_01＃测风塔137.5m高度年平均风速为6.18m/s，年平均风功率密度为243W/m²。",
                order=1,
            ),
            DocumentBlock(
                id="p2",
                type="paragraph",
                text="WX-TOWER_01＃测风塔37.5m高度空气密度为1.120kg/m³，推算至137.5m高度空气密度为1.080kg/m³。",
                order=2,
            ),
        ],
        tables=[
            DocumentTable(
                id="t_turbulence_dynamic",
                order=3,
                caption="WX-TOWER_01#测风塔12.5m/s湍流强度统计表",
                rows=[
                    [
                        TableCell(text="高度", row=0, col=0),
                        TableCell(text="平均湍流强度", row=0, col=1),
                        TableCell(text="代表性湍流强度", row=0, col=2),
                    ],
                    [
                        TableCell(text="137.5m", row=1, col=0),
                        TableCell(text="0.046", row=1, col=1),
                        TableCell(text="0.083", row=1, col=2),
                    ],
                ],
            )
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["WX-TOWER_01#"]
    assert fields["hubHeightAverageWindSpeedRecords"] == [
        {"tower_code": "WX-TOWER_01#", "height": 137.5, "height_unit": "m", "value": 6.18, "unit": "m/s"}
    ]
    assert fields["hubHeightAverageWindPowerDensityRecords"] == [
        {"tower_code": "WX-TOWER_01#", "height": 137.5, "height_unit": "m", "value": 243, "unit": "W/m²"}
    ]
    assert fields["windResourceAirDensityRecords"] == [
        {"tower_code": "WX-TOWER_01#", "height": 37.5, "height_unit": "m", "value": 1.12, "unit": "kg/m³"},
        {"tower_code": "WX-TOWER_01#", "height": 137.5, "height_unit": "m", "value": 1.08, "unit": "kg/m³"},
    ]
    assert fields["windResourceTurbulenceIntensityRecords"] == [
        {
            "tower_code": "WX-TOWER_01#",
            "height": 137.5,
            "height_unit": "m",
            "wind_speed_segment": 12.5,
            "wind_speed_unit": "m/s",
            "average_value": 0.046,
            "representative_value": 0.083,
        }
    ]


def test_wind_farm_air_density_prefers_selected_tower_over_last_mentioned_tower(tmp_path):
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="p1", type="paragraph", text="测风塔编号为7123#、6601#和6602#。", order=1),
            DocumentBlock(id="p2", type="paragraph", text="本次使用7123#测风塔进行分析，风电场6601#、6602#测风塔测风时长不足一个完整年，计算得到该风电场的空气密度为1.102kg/m³。", order=2),
        ],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    result_json = json.loads((tmp_path / "sample_result.json").read_text(encoding="utf-8"))
    resource = next(section for section in result_json["sections"] if section["name"] == "资源章节")
    fields = {field["fieldCode"]: field["value"] for field in resource["fields"]}
    assert fields["windResourceTowerCodes"] == ["7123#", "6601#", "6602#"]
    assert fields["windFarmAirDensities"] == [1.102, "---", "---"]


def test_configured_scalar_rules_tolerate_spaces_and_convert_units():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="年 上网电量 182940 MWh，年 等效 满负荷 小时数 为 1829 h。",
                order=1,
                page=1,
                section_path=["发电量"],
            ),
            DocumentBlock(
                id="b2",
                type="paragraph",
                text="最终宜选 IEC ⅢC 类及以上等级的风机。",
                order=2,
                page=1,
                section_path=["风资源"],
            ),
            DocumentBlock(
                id="b3",
                type="paragraph",
                text="本期共设1根35m独立避雷针，2根构架避雷针。",
                order=3,
                page=1,
                section_path=["电气一次"],
            ),
            DocumentBlock(
                id="b4",
                type="paragraph",
                text="接入站名称 接入站名称 110kV张洪变电站",
                order=4,
                page=1,
                section_path=["电气一次"],
            ),
            DocumentBlock(
                id="b5",
                type="paragraph",
                text="新 建 道 路 910.34 m，改 建 道 路 754.38 m。",
                order=5,
                page=1,
                section_path=["道路"],
            ),
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["gridAnnualEnergy"][1:3] == (18294, "万kW·h")
    assert overrides["gridAnnualEnergy"][5]["rawUnit"] == "MWh"
    assert overrides["equivalentFullLoadHours"][1:3] == (1829, "h")
    assert overrides["selectedTurbineSafetyClass"][1] == "IECⅢC类及以上等级的风机"
    assert overrides["independentLightningRodCount"][1:3] == (1, "座")
    assert overrides["independentLightningRodCount"][5]["rawUnit"] == "根"
    assert overrides["frameLightningRodCount"][1:3] == (2, "座")
    assert overrides["accessStationName"][1] == "110kV张洪变电站"
    assert overrides["newRoadLength"][1:3] == (0.91034, "km")
    assert overrides["newRoadLength"][5]["rawUnit"] == "m"
    assert overrides["rebuiltRoadLength"][1:3] == (0.75438, "km")


def test_selected_turbine_safety_class_value_starts_at_iec_phrase():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="根据国际电工协会IEC61400-1（2019）标准判定本风电场选用适合IECⅢB及其以上安全等级的风机。",
                order=1,
                section_path=["风能资源", "结论与建议"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["selectedTurbineSafetyClass"][1] == "IECⅢB及其以上安全等级的风机"


def test_selected_turbine_safety_class_prefers_final_standard_judgement_after_turbulence_classes():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="初步估算风电场区域120m高度标准空气密度条件下50年一遇最大风速为28.56m/s，小于37.5m/s；90m高度15m/s风速段平均湍流强度在0.114～0.149之间，综合考虑本风电场湍流强度为IEC A类。根据0822#、0823#和0824#三座测风塔处各层实测湍流强度和各机位点处模拟值判定本项目场区范围内120m拟选轮毂高度处湍流强度为IEC A类、IEC B类。根据NB/T31107-2017标准判定本风电场选用适合IECⅢB及其以上安全等级的风机，下阶段请风机厂家复核风电机组安全性并出具风机安全复核报告。",
                order=1,
                section_path=["风能资源", "结论与建议"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["selectedTurbineSafetyClass"][1] == "IECⅢB及其以上安全等级的风机"


def test_access_station_name_rejects_internal_wind_farm_substation():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="本工程线路最终接入至1期风电场升压站。",
                order=1,
                section_path=["电气一次"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert "accessStationName" not in overrides


def test_configured_scalar_sources_skip_toc_blocks():
    rb = ResultBuilder()
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="toc1",
                type="paragraph",
                text='目录 TOC \\o "1-2" HYPERLINK \\l _Toc1 1.6 电气 PAGEREF _Toc1 5 接入站名称 接入站名称 110kV张洪变电站',
                order=1,
                section_path=["电气一次"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert "accessStationName" not in overrides


def test_invalid_access_station_filters_related_voltage():
    rb = ResultBuilder()
    rb.deterministic_rules = {
        "electrical_primary": {
            "access_station_patterns": [
                {"score": 20, "pattern": r"接入(?P<value>对侧变电站)"},
            ],
            "invalid_access_station_patterns": ["对侧变电站"],
        }
    }
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="本工程 110kV 线路接入对侧变电站，站内另有 330kV 电气设备。",
                order=1,
                section_path=["电气一次"],
            )
        ],
    )

    built = rb.build(ast, {})

    assert "accessStationName" not in built["parsedFields"]
    assert "accessibleVoltage" not in built["parsedFields"]


def test_field_index_source_text_is_compacted_for_long_paragraphs(tmp_path):
    long_text = "接入站名称 接入站名称 110kV张洪变电站 " + "目录 " * 120
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[DocumentBlock(id="b1", type="paragraph", text=long_text, order=1, section_path=["电气一次"])],
    )

    JsonExporter(output_dir=tmp_path).export(ParseContext(file_path="sample.docx", ast=ast, validated={}))

    detail_json = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    source_text = detail_json["fieldIndex"]["accessStationName"]["source"]["text"]
    assert len(source_text) < len(long_text)
    assert len(source_text) <= 260


def test_configured_scalar_rules_can_use_pdf_page_text_fallback():
    rb = ResultBuilder(
        field_configs={
            "siteRoadLength": {
                "name": "场内道路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_rules": [
                    {
                        "name": "PDF 文本层道路长度",
                        "source_types": ["pdf_page_text"],
                        "value_type": "number",
                        "value_group": "value",
                        "unit": "km",
                        "require_any": ["场内"],
                        "patterns": [r"场内通往各风机点位的运输道路约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km)"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.pdf",
        meta={"pdf_page_texts": [{"page": 257, "text": "场内通往各风机点位的运输道路约31.15km。"}]},
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["siteRoadLength"][1:3] == (31.15, "km")
    assert overrides["siteRoadLength"][5]["page"] == 257


def test_pdf_page_text_uses_page_section_path_for_configured_rules():
    rb = ResultBuilder(
        field_configs={
            "siteRoadLength": {
                "name": "场内道路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_rules": [
                    {
                        "name": "PDF 文本层道路长度",
                        "source_types": ["pdf_page_text"],
                        "value_type": "number",
                        "value_group": "value",
                        "section_include": ["道路"],
                        "require_any": ["场内"],
                        "patterns": [r"场内道路约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km)"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[
            DocumentBlock(id="b1", type="paragraph", text="财务章节", order=1, page=1, section_path=["财务"]),
            DocumentBlock(id="b2", type="paragraph", text="道路章节", order=2, page=2, section_path=["道路"]),
        ],
        meta={
            "pdf_page_texts": [
                {"page": 1, "text": "场内道路约99km。"},
                {"page": 2, "text": "场内道路约31.15km。"},
            ]
        },
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["siteRoadLength"][1:3] == (31.15, "km")
    assert overrides["siteRoadLength"][5]["page"] == 2


def test_pdf_page_text_with_section_include_requires_section_unless_allowed():
    rb = ResultBuilder(
        field_configs={
            "siteRoadLength": {
                "name": "场内道路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_rules": [
                    {
                        "name": "PDF 文本层道路长度",
                        "source_types": ["pdf_page_text"],
                        "value_type": "number",
                        "value_group": "value",
                        "section_include": ["道路"],
                        "require_any": ["场内"],
                        "patterns": [r"场内道路约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km)"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.pdf",
        meta={"pdf_page_texts": [{"page": 2, "text": "场内道路约31.15km。"}]},
    )

    assert "siteRoadLength" not in rb._configured_scalar_overrides(ast)


def test_configured_scalar_rule_does_not_use_inferred_section_as_actual_section():
    rb = ResultBuilder(
        field_configs={
            "rebuiltRoadLength": {
                "name": "改建道路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_rules": [
                    {
                        "name": "道路正文改建道路长度",
                        "source_types": ["paragraph"],
                        "value_type": "number",
                        "value_group": "value",
                        "section_include": ["道路"],
                        "require_any": ["道路"],
                        "patterns": [r"改建长度约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km)"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="进场道路改建长度约7.3km。",
                order=1,
                section_path=["消防"],
            )
        ],
    )

    assert "rebuiltRoadLength" not in rb._configured_scalar_overrides(ast)


def test_configured_scalar_rule_can_use_explicit_strong_section_fallback():
    rb = ResultBuilder(
        field_configs={
            "rebuiltRoadLength": {
                "name": "改建道路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_rules": [
                    {
                        "name": "道路正文改建道路长度",
                        "source_types": ["paragraph"],
                        "value_type": "number",
                        "value_group": "value",
                        "section_include": ["道路"],
                        "section_fallback_require_all": ["进场道路", "道路改造", "改建长度"],
                        "require_any": ["道路"],
                        "patterns": [r"改建长度约\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>km)"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(
                id="b1",
                type="paragraph",
                text="道靖志路属于本项目的进场道路45.3km，道路改造点18处，改建长度约7.3km。",
                order=1,
                section_path=["消防"],
            )
        ],
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["rebuiltRoadLength"][1:3] == (7.3, "km")
    assert overrides["rebuiltRoadLength"][5]["sectionPath"] == ["消防"]
    assert overrides["rebuiltRoadLength"][5]["inferredSections"] == ["道路"]


def test_configured_scalar_sum_can_dedupe_by_configured_identity():
    rb = ResultBuilder(
        field_configs={
            "newCableLineLength": {
                "name": "新建电缆线路长度",
                "value_type": "number",
                "standard_unit": "km",
                "scalar_selection": {"strategy": "sum"},
                "scalar_rules": [
                    {
                        "name": "电缆长度合计",
                        "source_types": ["paragraph", "pdf_page_text"],
                        "value_type": "number",
                        "value_group": "value",
                        "dedupe_by": ["value", "unit", "page", "matched_pattern", "matched_text"],
                        "require_any": ["电缆"],
                        "patterns": [r"电缆\s*(?P<unit>米)\s+(?P<value>[0-9]+(?:\.[0-9]+)?)(?![0-9])"],
                    }
                ],
            }
        }
    )
    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[DocumentBlock(id="b1", type="paragraph", text="电缆 米 1800", order=1, page=1)],
        meta={"pdf_page_texts": [{"page": 1, "text": "电缆 米 1800"}]},
    )

    overrides = rb._configured_scalar_overrides(ast)

    assert overrides["newCableLineLength"][1:3] == (1.8, "km")


def test_candidate_retriever_compact_alias_hit():
    ast = DocumentAST(
        file_name="sample.docx",
        blocks=[
            DocumentBlock(id="b1", type="paragraph", text="年 上网电量 182940 MWh。", order=1, section_path=["发电量"])
        ],
    )
    configs = {
        "gridAnnualEnergy": {
            "name": "年上网发电量",
            "aliases": ["年上网电量"],
            "sections": {"include": ["发电量"], "exclude": []},
        }
    }

    candidates = CandidateRetriever(configs).retrieve(ast)

    assert len(candidates) == 1
    assert candidates[0].meta["alias_hit"] is True


def test_normalizer_converts_extracted_units_to_standard_units():
    normalizer = Normalizer(
        {
            "gridAnnualEnergy": {"value_type": "number", "standard_unit": "万kW·h"},
            "newRoadLength": {"value_type": "number", "standard_unit": "km"},
            "independentLightningRodCount": {"value_type": "number", "standard_unit": "座"},
        }
    )

    assert normalizer._convert_to_standard_unit("gridAnnualEnergy", 182940, "MWh") == (18294, "万kW·h")
    assert normalizer._convert_to_standard_unit("newRoadLength", 910.34, "m") == (0.91034, "km")
    assert normalizer._convert_to_standard_unit("independentLightningRodCount", 1, "根") == (1, "座")
