"""Mandatory YAML and pipeline switches are enforced, not decorative."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from word_parser.application.factory import create_default_parser
from word_parser.config.loader import ConfigLoader
from word_parser.document.word.simple_docx_loader import SimpleDocxLoader
from word_parser.primary.validator import PassThroughValidator, Validator


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs"


def test_production_yaml_validator_flag_matches_original_behavior():
    pipeline = yaml.safe_load((CFG / "pipeline.yaml").read_text(encoding="utf-8-sig"))
    assert pipeline["modules"]["validator"]["enabled"] is True
    parser = create_default_parser(CFG)
    assert isinstance(parser.pipeline.validator, Validator)
    assert parser.pipeline.exporter.result_builder.strict_domain_literals is True


def test_disabling_supported_modules_selects_real_python_operators(monkeypatch):
    original = ConfigLoader.load_required_yaml
    def override(self, path):
        data = original(self, path)
        if path == "pipeline.yaml":
            data = deepcopy(data)
            data["modules"]["validator"]["enabled"] = False
            data["modules"]["aspose_loader"]["enabled"] = False
        return data
    monkeypatch.setattr(ConfigLoader, "load_required_yaml", override)
    parser = create_default_parser(CFG)
    assert isinstance(parser.pipeline.validator, PassThroughValidator)
    assert isinstance(parser.pipeline.loader.word_loader, SimpleDocxLoader)
    fields = {"x": object()}
    assert parser.pipeline.validator.validate(fields) is fields


def test_unsupported_disabled_module_fails_instead_of_being_ignored(monkeypatch):
    original = ConfigLoader.load_required_yaml
    def override(self, path):
        data = original(self, path)
        if path == "pipeline.yaml":
            data = deepcopy(data)
            data["modules"]["alias_matcher"]["enabled"] = False
        return data
    monkeypatch.setattr(ConfigLoader, "load_required_yaml", override)
    with pytest.raises(ValueError, match="alias_matcher"):
        create_default_parser(CFG)


def test_empty_or_missing_required_yaml_fails_loudly(tmp_path):
    loader = ConfigLoader(tmp_path)
    with pytest.raises(FileNotFoundError):
        loader.load_required_yaml("output_schema.yaml")
    (tmp_path / "output_schema.yaml").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="非空对象"):
        loader.load_required_yaml("output_schema.yaml")


def test_document_structure_policy_and_audit_snapshot():
    from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
    from word_parser.document.structure_parser import StructureParser
    from word_parser.document.section_detector import SectionDetector
    from word_parser.document.structure_index import build_structure_index
    policy = ConfigLoader(CFG).load_required_yaml("document_structure.yaml")
    assert not policy["heading"]["enhanced_styles"]
    ast = DocumentAST("sample.docx", blocks=[
        DocumentBlock("p1", "paragraph", "第一章 概况", 0, style=TextStyle(style_name="Heading 1")),
        DocumentBlock("tb", "table", "", 1, meta={"table_id": "t1"}),
    ], tables=[DocumentTable("t1", 1, caption="工程总概算表", rows=[
        [TableCell("项目", 0, 0, is_header=True), TableCell("数量", 0, 1, is_header=True)],
        [TableCell("设备", 1, 0)],
    ])])
    StructureParser(policy).parse(ast)
    SectionDetector(ConfigLoader(CFG).load_required_yaml("sections.yaml"), policy).detect(ast)
    before = ast.to_dict()
    snapshot = build_structure_index(ast, policy)
    assert snapshot["summary"]["physicalTableCount"] == 1
    assert snapshot["sections"][0]["id"] == "p1"
    assert snapshot["physicalTables"][0]["sectionPath"] == ["技经概算"]
    assert "RAGGED_TABLE_ROWS" in {d["code"] for d in snapshot["diagnostics"]}
    assert ast.to_dict() == before
    assert "cells" not in snapshot["physicalTables"][0]
    policy["diagnostics"]["include_text"] = True
    assert build_structure_index(ast, policy)["physicalTables"][0]["cells"][1][0]["text"] == "设备"


def test_structure_policy_controls_style_and_strict_diagnostics():
    from word_parser.document.ast.document import DocumentAST, DocumentBlock, TextStyle
    from word_parser.document.structure_parser import StructureParser
    from word_parser.document.structure_index import build_structure_index
    policy = ConfigLoader(CFG).load_required_yaml("document_structure.yaml")
    policy["heading"]["enhanced_styles"] = True
    policy["heading"]["toc_exclusion"] = True
    parser = StructureParser(policy)
    assert parser._detect_heading_level("资源分析", TextStyle(style_name="标题 2")) == 2
    assert parser._detect_heading_level("1.2 资源分析......12", TextStyle(style_name="TOC 2", bold=True)) is None
    policy["diagnostics"]["mode"] = "strict"
    broken = DocumentAST("broken.docx", blocks=[DocumentBlock("tb", "table", "", 0, meta={"table_id": "missing"})])
    with pytest.raises(ValueError, match="DANGLING_TABLE_REFERENCE"):
        build_structure_index(broken, policy)
    policy["heading"]["patterns"] = ["["]
    import re
    with pytest.raises(re.error):
        StructureParser(policy)


def test_pdf_continuation_snapshot_preserves_fragment_coordinates():
    from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
    from word_parser.document.pdf.pdf_loader import OpenDataLoaderPdfLoader
    from word_parser.document.structure_index import build_structure_index
    policy = ConfigLoader(CFG).load_required_yaml("document_structure.yaml")
    policy["diagnostics"]["include_text"] = True
    first = DocumentTable("t1", 0, page=1, caption="设备表", rows=[
        [TableCell("序号", 0, 0, is_header=True), TableCell("数量", 0, 1, is_header=True)]])
    second = DocumentTable("t2", 1, page=2, rows=[
        [TableCell("1", 0, 0), TableCell("32", 0, 1)]])
    ast = DocumentAST("sample.pdf", tables=[first, second], blocks=[
        DocumentBlock("tb1", "table", "", 0, meta={"table_id": "t1"}),
        DocumentBlock("tb2", "table", "", 1, meta={"table_id": "t2"})])
    OpenDataLoaderPdfLoader()._merge_continued_tables(ast)
    assert len(ast.tables) == 1
    assert first.to_matrix() == [["序号", "数量"], ["1", "32"]]
    snapshot = build_structure_index(ast, policy)
    assert snapshot["summary"]["physicalTableCount"] == 2
    assert snapshot["summary"]["logicalTableCount"] == 1
    assert snapshot["logicalTables"][0]["physicalTableIds"] == ["t1", "t2"]
    assert snapshot["physicalTables"][1]["cells"][0][1]["row"] == 0
    assert snapshot["physicalTables"][1]["cells"][0][1]["meta"]["source_page"] == 2


def test_docx_xml_records_declared_header_and_merge_metadata():
    from xml.etree import ElementTree as ET
    from word_parser.document.word.simple_docx_loader import SimpleDocxLoader, NAMESPACE
    xml = '<w:tbl xmlns:w="' + NAMESPACE["w"] + '"><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    table = SimpleDocxLoader()._parse_table(ET.fromstring(xml), 1, 0)
    cell = table.rows[0][0]
    assert cell.meta == {"grid_span": "2", "vertical_merge": "restart", "declared_header": True}
    assert table.to_matrix() == [["项目"]]
