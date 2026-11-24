from copy import deepcopy
from pathlib import Path

from word_parser.config.loader import ConfigLoader
from word_parser.document.ast.document import DocumentTable, TableCell
from word_parser.document.table_recovery import recover_grid
from word_parser.secondary.cross_validation import build_audit
from word_parser.secondary.budget_priority import apply_budget_priority

ROOT = Path(__file__).resolve().parents[1] / "configs"
SETTINGS = ConfigLoader(ROOT).load_required_yaml("document_structure.yaml")["table_recovery"]
SCHEMA = ConfigLoader(ROOT).load_required_yaml("output_schema.yaml")
CODES = SCHEMA["output_field_codes"]


def key(code):
    return "${" + CODES[code] + "}"


def table(id, name, unit, value):
    return recover_grid(DocumentTable(id, 0, caption="设备及安装工程概算表", section_path=["技经概算"], rows=[
        [TableCell(v, 0, i, is_header=True) for i, v in enumerate(["项目名称", "单位", "数量"])],
        [TableCell(v, 1, i) for i, v in enumerate([name, unit, str(value)])]]), SETTINGS)


def run(tables, old=30):
    fields = [{"fieldCode": "turbineCount", "name": "风机台数", "unit": "台", "value": old}]
    result = {"result": {"sections": [{"name": "发电量章节", "fields": fields}]},
              "mapped": {key("turbineCount"): old}, "_recovered_tables": tables, "fields": {}}
    detail = {"fieldIndex": {"turbineCount": {"value": old, "source": {"tableId": "design", "row": 1, "column": 2}}}}
    audit = build_audit(result, deepcopy(detail), {"sections": []}, detail, ROOT)
    changed = apply_budget_priority(result, detail, audit, ROOT)
    report = next(f for f in audit["fields"] if f["fieldCode"] == "turbineCount")
    return result, detail, report, changed


def test_multiple_budget_tables_agree_and_replace():
    result, detail, report, changed = run([table("a", "风力发电机组", "台", 32), table("b", "风机", "台", 32)])
    assert changed == 1
    assert result["mapped"][key("turbineCount")] == 32
    assert result["result"]["sections"][0]["fields"][0]["value"] == 32
    assert detail["fieldIndex"]["turbineCount"]["source"]["tableId"] == "a"
    assert report["adoption"]["originalValue"] == 30
    assert len(report["adoption"]["supportingSources"]) == 2


def test_conflict_between_budget_tables_is_not_guessed():
    result, detail, report, changed = run([table("a", "风机", "台", 32), table("b", "风机", "台", 36)])
    assert changed == 0
    assert report["adoption"]["reason"] == "budget_tables_disagree"
    assert result["mapped"][key("turbineCount")] == 30


def test_fill_missing_and_keep_zero():
    result, detail, report, changed = run([table("a", "风机", "台", 0)], old=None)
    assert changed == 1
    assert report["adoption"]["action"] == "filled"
    assert result["mapped"][key("turbineCount")] == 0


def test_excluded_resource_section():
    result = {"result": {"sections": [{"name": "资源章节", "fields": [{"fieldCode": "turbineCount", "unit": "台", "value": 30}]}]},
              "mapped": {key("turbineCount"): 30}, "_recovered_tables": [table("a", "风机", "台", 32)]}
    detail = {"fieldIndex": {}}
    audit = build_audit(result, detail, {"sections": []}, detail, ROOT)
    assert apply_budget_priority(result, detail, audit, ROOT) == 0
    assert next(f for f in audit["fields"] if f["fieldCode"] == "turbineCount")["adoption"]["reason"] == "excluded_section"
