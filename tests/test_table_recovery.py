from pathlib import Path
from word_parser.config.loader import ConfigLoader
from word_parser.document.ast.document import DocumentAST, DocumentTable, TableCell
from word_parser.document.table_recovery import recover_grid, recover_tables

SETTINGS = ConfigLoader(Path(__file__).resolve().parents[1] / "configs").load_required_yaml("document_structure.yaml")["table_recovery"]


def test_explicit_grid_span_and_vertical_merge_preserve_anchor():
    table = DocumentTable("t1", 0, rows=[
        [TableCell("名称", 0, 0, row_span=2, is_header=True),
         TableCell("费用", 0, 1, col_span=2, is_header=True)],
        [TableCell("设备", 1, 0), TableCell("安装", 1, 1)],
        [TableCell("风机", 2, 0), TableCell("0", 2, 1), TableCell("2", 2, 2)]])
    before = table.to_dict()
    view = recover_grid(table, SETTINGS)
    assert view["columns"] == ["名称", "费用 / 设备", "费用 / 安装"]
    assert view["rows"][1][0]["isAnchor"] is False
    assert view["rows"][1][0]["source"]["row"] == 0
    assert view["rows"][2][1]["text"] == "0"
    assert table.to_dict() == before


def test_xml_vertical_merge_and_grid_span():
    table = DocumentTable("t", 1, rows=[
        [TableCell("分类", 0, 0, meta={"vertical_merge": "restart"}),
         TableCell("费用", 0, 1, meta={"grid_span": "2"})],
        [TableCell("", 1, 0, meta={"vertical_merge": "continue"}),
         TableCell("设备", 1, 1), TableCell("安装", 1, 2)]])
    view = recover_grid(table, SETTINGS)
    assert view["rows"][1][0]["text"] == "分类"
    assert view["rows"][0][2]["isAnchor"] is False
    assert view["rows"][1][0]["rowSpan"] == 2


def make_table(id, order, page, caption, value):
    return DocumentTable(id, order, page, caption, ["技经概算"], rows=[
        [TableCell("项目", 0, 0, is_header=True), TableCell("数量", 0, 1, is_header=True)],
        [TableCell("设备", 1, 0), TableCell(value, 1, 1)]])


def test_repeat_header_continuation_and_distinct_caption():
    ast = DocumentAST("a.pdf", tables=[
        make_table("a", 0, 1, "设备概算表", "1"),
        make_table("b", 2, 2, "设备概算表（续）", "2"),
        make_table("c", 4, 3, "其他概算表", "3")])
    view = recover_tables(ast, SETTINGS)
    assert len(view) == 2
    assert view[0]["physicalTableIds"] == ["a", "b"]
    assert len(view[0]["rows"]) == 3
    assert view[0]["rows"][2][1]["source"] == {"tableId": "b", "page": 2, "row": 1, "column": 1}
    assert len(ast.tables) == 3
