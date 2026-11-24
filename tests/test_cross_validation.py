from pathlib import Path
from copy import deepcopy
from word_parser.config.loader import ConfigLoader
from word_parser.document.ast.document import DocumentTable, TableCell
from word_parser.document.table_recovery import recover_grid
from word_parser.secondary.cross_validation import build_audit, converted, load_policy
from word_parser.extraction.candidate_registry import CandidateRegistry

ROOT = Path(__file__).resolve().parents[1] / "configs"


def test_unit_dimension_conversion():
    policy = load_policy(ROOT)
    assert converted("2000", "m", "km", policy) == 2
    assert converted("32", "台", "套", policy) is None
    assert converted("0", "m", "km", policy) == 0


def test_all_fields_audited_raw_table_with_no_business_table_and_no_overwrite():
    settings = ConfigLoader(ROOT).load_required_yaml("document_structure.yaml")["table_recovery"]
    table = DocumentTable("budget", 1, caption="设备及安装工程概算表", section_path=["技经概算"], rows=[
        [TableCell(v, 0, i, is_header=True) for i, v in enumerate(["名称", "单位", "数量", "单价"])],
        [TableCell(v, 1, i) for i, v in enumerate(["风力发电机组", "台", "32", "500"])]])
    primary = {"fieldIndex": {"turbineCount": {"value": 30, "source": {"tableId": "design", "row": 1, "column": 2}}},
               "extractionCandidates": []}
    result = {"result": {"sections": [{"name": "工程概况", "fields": [
        {"fieldCode": "turbineCount", "value": 30, "unit": "台"}], "tables": []}]},
        "mapped": {}, "_recovered_tables": [recover_grid(table, settings)]}
    before = deepcopy(result)
    report = build_audit(result, primary, {"sections": []}, primary, ROOT)
    by_code = {f["fieldCode"]: f for f in report["fields"]}
    assert len(by_code) >= len(ConfigLoader(ROOT).load_field_configs())
    assert by_code["turbineCount"]["status"] == "conflict"
    assert by_code["turbineCount"]["candidates"][0]["value"] == "32"
    assert len(by_code["turbineCount"]["candidates"]) == 1
    assert by_code["turbineCount"]["candidates"][0]["source"]["tableId"] == "budget"
    assert result == before
    primary["fieldIndex"]["turbineCount"]["source"] = {"tableId": "budget", "row": 1, "column": 2}
    report = build_audit(result, primary, {"sections": []}, primary, ROOT)
    assert next(f for f in report["fields"] if f["fieldCode"] == "turbineCount")["status"] == "same_source"


def test_shared_candidate_registry_keeps_observations_and_deduplicates_sources():
    r = CandidateRegistry()
    for stage in ("primary", "secondary_field", "cross_validation"):
        r.add("field", "x", {"stage": stage, "value": 0, "source": {"tableId": "t", "row": 1, "column": 2}})
    group = r.report()["groups"][0]
    assert len(group["observations"]) == 3
    assert group["physicalSourceCount"] == 1
    assert group["sharedPhysicalSourceCount"] == 1
