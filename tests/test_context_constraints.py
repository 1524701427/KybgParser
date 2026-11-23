"""上下文规则确保同名标签对应正确的工程对象。"""

from word_parser.document.ast.evidence import Extraction, FieldEvidence
from word_parser.primary.context_filter import CandidateContextFilter
from word_parser.primary.candidate_resolver import CandidateResolver
from word_parser.primary.normalizer import Normalizer
from word_parser.config.loader import ConfigLoader
from word_parser.output.result_builder import ResultBuilder


def _candidate(code, value, text, section=None, score=2.0, page=1):
    return Extraction(
        field_code=code, field_name=code, raw_value=str(value), value=value,
        unit="MW", score=score, method="regex",
        evidence=FieldEvidence(source_type="paragraph", text=text, page=page,
                               section_path=section or []),
    )


def test_aliases_and_context_constraints_are_loaded_separately():
    fields = ConfigLoader("configs").load_field_configs()
    assert "升压站规划总规模" in fields["plannedCapacity"]["aliases"]
    assert "总装机容量" not in fields["plannedCapacity"]["aliases"]
    assert "升压站" in fields["plannedCapacity"]["context_constraints"]["required_context_any"]
    assert "总建设容量" in fields["installedCapacity"]["aliases"]
    assert "单机容量" in fields["installedCapacity"]["context_constraints"]["negative_context"]


def test_context_filter_uses_value_clause_and_section():
    fields = ConfigLoader("configs").load_field_configs()
    candidates = [
        _candidate("plannedCapacity", 200, "本项目总装机容量为200MW，在场内新建升压站。"),
        _candidate("plannedCapacity", 200, "规划总装机容量为200MW。", ["电气一次", "主接线"]),
        _candidate("installedCapacity", 5, "单机容量为5MW。"),
        _candidate("installedCapacity", 200, "本项目总装机规模为200MW。"),
    ]
    accepted, rejected = CandidateContextFilter(fields).filter(candidates)
    assert [item.field_code for item in accepted] == ["plannedCapacity", "installedCapacity"]
    assert [item.debug["context_rejection"] for item in rejected] == [
        "required_context_missing", "negative_context",
    ]


def test_close_conflicting_values_are_marked_for_review():
    fields = ConfigLoader("configs").load_field_configs()
    candidates = [
        _candidate("installedCapacity", 100, "总装机容量为100MW。", page=2),
        _candidate("installedCapacity", 120, "总装机容量为120MW。", page=3),
    ]
    result = CandidateResolver(fields).resolve(candidates)["installedCapacity"]
    assert result.status == "WARNING"
    assert result.debug["conflict_values"][0]["value"] in (100, 120)
    assert result.confidence <= 0.5


def test_deterministic_override_obeys_the_same_object_context():
    builder = ResultBuilder()
    fields = {}
    builder._set_field(fields, "plannedCapacity", "规划容量", 200, "MW",
                       "本项目总装机容量为200MW，在场内新建升压站。", source_type="paragraph")
    assert "plannedCapacity" not in fields
    builder._set_field(fields, "plannedCapacity", "规划容量", 200, "MW",
                       "升压站主接线规划容量为200MW。", source_type="paragraph")
    assert fields["plannedCapacity"].value == 200


def test_installed_capacity_converts_report_unit_to_mw():
    fields = ConfigLoader("configs").load_field_configs()
    item = _candidate("installedCapacity", 10, "总建设容量为10万千瓦。")
    item.unit = "万千瓦"
    normalized = Normalizer(fields).normalize_candidates([item])[0]
    assert normalized.value == 100
    assert normalized.unit == "MW"


def test_detail_row_values_obey_object_context():
    builder = ResultBuilder()
    details = {"electricalPrimaryMainConnectionCombined": [
        {"plannedCapacity": 200, "currentCapacity": 200,
         "_rowSource": {"source": {"sourceText": "本项目总装机容量为200MW，在场内新建升压站。"}}},
        {"plannedCapacity": 100, "currentCapacity": 100,
         "_rowSource": {"source": {"sourceText": "主接线规划总容量为100MW。", "sectionPath": ["电气一次"]}}},
    ]}
    builder._apply_detail_context_constraints(details)
    rows = details["electricalPrimaryMainConnectionCombined"]
    assert rows[0]["plannedCapacity"] is None
    assert rows[0]["currentCapacity"] is None
    assert rows[1]["plannedCapacity"] == 100
    assert rows[1]["currentCapacity"] == 100
