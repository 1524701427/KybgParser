"""Regression tests for config-driven retrieval with an unchanged AST and field YAML."""

from pathlib import Path

import yaml

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.primary.candidate_retriever import CandidateRetriever


ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "configs" / "extraction_runtime.yaml").read_text(encoding="utf-8"))["retrieval"]


def _sample():
    fields = {
        "installedCapacity": {
            "name": "装机容量",
            "aliases": ["总装机容量"],
            "value_type": "number",
            "sections": {"include": ["工程概况"], "exclude": ["财务评价"]},
            "source_priority": {"table_captions": ["主要技术经济指标"]},
        }
    }
    ast = DocumentAST(
        file_name="test.docx",
        blocks=[
            DocumentBlock("toc", "paragraph", "目录", 0),
            DocumentBlock("p1", "paragraph", "本项目总装机容量为200MW。", 1, section_path=["工程概况"]),
            DocumentBlock("p2", "paragraph", "总装机容量为300MW。", 2, section_path=["财务评价"]),
            DocumentBlock("p3", "paragraph", "本项目装机参数见下表。", 3, section_path=["工程特性表"]),
        ],
        tables=[
            DocumentTable(
                id="t1", order=4, caption="主要技术经济指标", section_path=["工程概况"],
                rows=[[TableCell("总装机容量", 0, 0), TableCell("MW", 0, 1), TableCell("200", 0, 2)]],
            ),
        ],
    )
    return fields, ast


def _compact(candidates):
    return [
        (c.field_code, c.source_type, c.block_id, c.table_id, c.score,
         c.meta.get("section_origin"), c.meta.get("alias_hit"))
        for c in candidates
    ]


def test_yaml_retrieval_is_identical_to_legacy_defaults():
    fields, ast = _sample()
    old = CandidateRetriever(fields)
    configured = CandidateRetriever(fields, settings=POLICY)
    assert _compact(old.retrieve(ast)) == _compact(configured.retrieve(ast))
    assert any(c.block_id == "p1" for c in configured.retrieve(ast))
    assert all(c.block_id != "p2" for c in configured.retrieve(ast))


def test_toc_filter_rules_match_legacy_behavior():
    fields, _ = _sample()
    old, configured = CandidateRetriever(fields), CandidateRetriever(fields, settings=POLICY)
    texts = [
        "目录", "目錄", "contents",
        "TOC \\o 1-3", "HYPERLINK _Toc998", "PAGEREF _Toc772",
        "第一章 项目概述", "本项目拟建总装机容量200MW。",
        "目录\n1.1 工程概况 ........ 1",
    ]
    assert [old._is_toc_like_text(s) for s in texts] == [
        configured._is_toc_like_text(s) for s in texts
    ]


def test_explicit_retrieval_weight_override_is_confined_to_retriever():
    fields, ast = _sample()
    base = CandidateRetriever(fields).retrieve(ast)
    configured_policy = {**POLICY, "paragraph_alias_bonus": 0.9}
    altered = CandidateRetriever(fields, settings=configured_policy).retrieve(ast)
    old_paragraph = next(c for c in base if c.block_id == "p1")
    new_paragraph = next(c for c in altered if c.block_id == "p1")
    assert new_paragraph.score - old_paragraph.score == 0.4 or abs(
        new_paragraph.score - old_paragraph.score - 0.4
    ) < 1e-9
    assert len(base) == len(altered)
