from pathlib import Path
from word_parser.config.loader import ConfigLoader
from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.document.table_projection import apply_recovered_tables
from word_parser.document.table_recovery import recover_tables

ROOT = Path(__file__).resolve().parents[1] / "configs"


def test_recovered_table_replaces_original_without_duplicate_measurements():
    ast = DocumentAST("a.docx", tables=[DocumentTable("t", 0, rows=[
        [TableCell("项目", 0, 0, is_header=True), TableCell("数量", 0, 1, is_header=True)],
        [TableCell("设备", 1, 0), TableCell("5", 1, 1, row_span=2)],
        [TableCell("其他", 2, 0)]])],
        blocks=[DocumentBlock("tb", "table", "", 0, meta={"table_id": "t"})])
    cfg = ConfigLoader(ROOT).load_required_yaml("document_structure.yaml")["table_recovery"]
    views = recover_tables(ast, cfg)
    summary = apply_recovered_tables(ast, views)
    assert summary["replaced"] == ["t"]
    assert ast.tables[0].to_matrix() == [["项目", "数量"], ["设备", "5"], ["其他", ""]]
    assert ast.tables[0].rows[2][1].meta["physical_source"]["row"] == 1
    assert ast.get_table("t") is ast.tables[0]


def test_shared_selection_and_unit_factors():
    from word_parser.extraction.selection import select_secondary, select_candidate
    from word_parser.primary.normalizer import Normalizer
    primary = {"value": 0}
    secondary = {"status": "OK", "value": 2}
    assert select_secondary(primary, secondary) is primary
    assert select_secondary({"value": None}, secondary) is secondary
    assert select_candidate(["a", "b"], lambda item: 1) == "a"
    normalizer = Normalizer()
    assert normalizer._convert_value(1000, "m", "km") == 1
    assert normalizer._convert_value(2, "km", "m") == 2000
    assert normalizer._convert_value(3, "台", "套") is None


def test_physical_source_identity_after_projection():
    from word_parser.extraction.candidate_registry import source_key
    assert source_key({"tableId": "logical", "row": 3, "column": 2,
                       "physicalSource": {"tableId": "page2", "row": 0, "column": 2}}) == ("page2", 0, 2)


def test_budget_price_role_does_not_confuse_quantity_or_total():
    from word_parser.document.table_recovery import recover_grid
    from word_parser.secondary.cross_validation import load_policy, inherit_price_items, index_rows, field_candidates
    policy = load_policy(ROOT)
    inherit_price_items(policy, ConfigLoader(ROOT))
    table = DocumentTable("t", 0, caption="设备及安装工程概算表", section_path=["技经概算"], rows=[
        [TableCell(v, 0, i, is_header=True) for i, v in enumerate(["项目名称", "单位", "数量", "设备单价（元）", "合价（万元）"])],
        [TableCell(v, 1, i) for i, v in enumerate(["风电机组", "台", "32", "2000000", "6400"])],
    ])
    settings = ConfigLoader(ROOT).load_required_yaml("document_structure.yaml")["table_recovery"]
    rows = index_rows([recover_grid(table, settings)], policy)
    candidates = field_candidates("windTurbineUnitPrice", {"name": "风机单价", "unit": "万元"}, rows, policy)
    assert len(candidates) == 1
    assert candidates[0]["value"] == "200"
    assert candidates[0]["columnRole"] == "unit_price"
    assert candidates[0]["sourceUnit"] == "元"


def test_investment_calculation_is_pure_and_preserves_legacy_values():
    from copy import deepcopy
    from word_parser.secondary.investment_completion import load_investment_completion, calculate_investment_completion, placeholder
    policy = load_investment_completion(ROOT)
    initial = {
        placeholder("engineering_estimate_table"): {"columns": ["序号", "项目名称", "合计"],
            "data": [["Ⅰ", "送出线路工程", 100], ["Ⅱ", "配套费", None], ["1", "项目总投资", 30]]},
        placeholder("investment_dynamic_partial"): 0,
        placeholder("investment_dynamic_total"): 200,
    }
    original = deepcopy(initial)
    changes = calculate_investment_completion(initial, policy)
    assert changes[placeholder("delivery_project")] == 100
    assert changes[placeholder("supporting_cost")] == 30
    assert changes[placeholder("dynamic_investment")] == 200
    assert initial == original
