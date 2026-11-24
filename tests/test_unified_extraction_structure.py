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
