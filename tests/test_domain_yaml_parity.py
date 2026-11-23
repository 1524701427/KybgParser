"""Project and civil-road domain rule YAML parity without Aspose/OCR.

The checks invoke the original domain methods, not duplicate parsing algorithms.
They assert that YAML inputs reproduce the unchanged Python fallback rules.
"""
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
import yaml

from word_parser.domains.project_overview import ProjectOverviewRulesMixin
from word_parser.domains.civil_roads import CivilRoadRulesMixin


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = yaml.safe_load((ROOT / "configs" / "deterministic_rules.yaml").read_text(encoding="utf-8"))


class ProjectShim(ProjectOverviewRulesMixin):
    def __init__(self, section):
        self.section = section

    def _deterministic_rule_section(self, name):
        assert name == "project_overview"
        return self.section

    def _clean_text(self, text):
        return text.strip()


class RoadShim(CivilRoadRulesMixin):
    def __init__(self, section):
        self.section = section

    def _deterministic_rule_section(self, name):
        assert name == "civil_roads"
        return self.section

    def _clean_text(self, text):
        return text.strip()

    def _configured_patterns(self, section, key, fallback):
        return section.get(key, fallback)

    def _first_number_after_pattern(self, text, pattern):
        match = re.search(pattern, text, re.I)
        return float(match.group(1)) if match else None

    def _last_number_after_pattern(self, text, pattern):
        matches = list(re.finditer(pattern, text, re.I))
        return float(matches[-1].group(1)) if matches else None

    def _original_captioned_table_by_regex_from_document(self, ast, key, patterns, include_table_text=True):
        return {"key": key, "patterns": patterns, "includeTableText": include_table_text}


@pytest.mark.parametrize("texts", [
    ["建设单位：陕西华电能源有限责任公司"],
    ["本项目投资方为华电新能源有限公司，场址位于陕西省延安市吴起县"],
    ["本工程位于陕西省榆林市靖边县宁条梁镇，工程概况如下。"],
    ["投资方概况", "项目单位：榆林能源股份有限公司"],
    ["项目名称：陕西某风电场"],
])
def test_project_overview_yaml_matches_original_fallback(texts):
    ast = SimpleNamespace(blocks=[
        SimpleNamespace(text=text, section_path=["工程概况"])
        for text in texts
    ])
    old, updated = ProjectShim({}), ProjectShim(SETTINGS["project_overview"])
    assert updated._investment_owner_company_from_blocks(ast) == old._investment_owner_company_from_blocks(ast)
    assert updated._project_address_from_blocks(ast) == old._project_address_from_blocks(ast)


@pytest.mark.parametrize("texts", [
    ["本项目进站道路3.2km，场内道路5.1km，新建道路4.5km，改建道路0.6km。"],
    ["进站道路路基宽8m，进站道路路面宽6m。路基设计宽度为8m。"],
    ["检修道路路基5m路面宽4.5m。"],
    ["基础混凝土C40和风机叶片型号资料，不包含道路参数。"],
])
def test_road_patterns_match_original_fallback(texts):
    ast = SimpleNamespace(blocks=[
        SimpleNamespace(text=text, section_path=["道路"])
        for text in texts
    ])
    old, updated = RoadShim({}), RoadShim(SETTINGS["civil_roads"])
    assert updated._road_combined_row_from_document(ast) == old._road_combined_row_from_document(ast)
    assert updated._road_original_table_from_document(ast) == old._road_original_table_from_document(ast)


def test_existing_project_and_road_patterns_compile_in_yaml():
    project = SETTINGS["project_overview"]
    for key in ("company_pattern", "owner_keyword_pattern", "project_location_pattern"):
        assert isinstance(project[key], str)
        re.compile(project[key])
    road = SETTINGS["civil_roads"]
    assert len(road["caption_patterns"]) == 3
    assert len(road["combined_text_patterns"]) == 9
    for rule in [*road["caption_patterns"], *road["combined_text_patterns"].values()]:
        re.compile(rule)


def test_yaml_rules_change_only_the_intended_field():
    text = "本项目新建道路5km，改建道路3km。"
    ast = SimpleNamespace(blocks=[SimpleNamespace(text=text, section_path=["道路"])])
    rule = SETTINGS["civil_roads"].copy()
    rule["combined_text_patterns"] = dict(rule["combined_text_patterns"])
    rule["combined_text_patterns"]["newRoadLength"] = r"根本不存在的标签(\d+)km"
    original = RoadShim(SETTINGS["civil_roads"])._road_combined_row_from_document(ast)
    altered = RoadShim(rule)._road_combined_row_from_document(ast)
    assert original is not None and altered is not None
    assert original["newRoadLength"] == 5.0
    assert altered["newRoadLength"] is None
    assert altered["rebuiltRoadLength"] == original["rebuiltRoadLength"] == 3.0
