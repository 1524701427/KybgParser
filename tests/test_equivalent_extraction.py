"""验证跨写法等价抽取，以及同页相邻表格不会串值。"""

from word_parser.application.factory import create_default_parser
from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.mapping.wind import merge_turbulence_records


def _table(table_id: str, caption: str, rows: list[list[str]], page: int = 1) -> DocumentTable:
    return DocumentTable(
        id=table_id, order=1, page=page, caption=caption,
        rows=[[TableCell(value, row_index, column_index) for column_index, value in enumerate(row)]
              for row_index, row in enumerate(rows)],
    )


def test_finance_equivalent_text_uses_pdf_page_text_and_compound_qualifier():
    builder = create_default_parser().pipeline.exporter.result_builder
    ast = DocumentAST(
        file_name="sample.pdf",
        blocks=[DocumentBlock("loan", "paragraph", "长期借款采用等额还本利息照付方式还款，还款期限约为 15 年。", 1)],
        meta={"pdf_page_texts": [{"page": 2, "text": "流动资金贷款利率为3.7%。"}]},
    )
    fields = {}

    builder._apply_finance_field_overrides(ast, fields)

    assert fields["repaymentPeriod"].value == 15
    assert fields["workingCapitalLoanInterestRate"].value == 3.7


def test_operational_roads_become_maintenance_road_only_with_explicit_statement():
    builder = create_default_parser().pipeline.exporter.result_builder
    road = "新建场内道路长约28.5km，路面宽度4.5m；扩建场内道路长约26.5km，施工结束后作为永久检修道路。"
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock("road", "paragraph", road, 1)])

    assert builder._maintenance_road_from_operational_roads(ast) == {
        "maintenanceRoadLength": 55, "maintenanceRoadPavementWidth": 4.5,
    }
    ast.blocks[0].text = road.replace("作为永久检修道路", "恢复原状")
    assert builder._maintenance_road_from_operational_roads(ast) == {}


def test_turbulence_parser_rejects_same_page_wind_speed_table():
    builder = create_default_parser().pipeline.exporter.result_builder
    speed = _table("speed", "1006#测风塔各高度平均风速", [
        ["", "80m", "70m"], ["平均值", "4.97", "4.87"],
    ])
    ast = DocumentAST(file_name="sample.pdf", tables=[speed], meta={
        "pdf_page_texts": [{"page": 1, "text": "表2-21：1006#测风塔各高度湍流强度"}],
    })
    assert builder._horizontal_turbulence_rows(ast, speed, speed.to_matrix(), speed.caption) == []

    turbulence = _table("turbulence", "1006#测风塔各高度湍流强度", [
        ["", "80m", "70m", "30m"], ["平均值", "0.19", "0.20", "0.24"],
        ["15m/s 平均值", "0.119", "0.096", ""], ["代表性湍流", "0.137", "0.147", ""],
    ])
    records = builder._horizontal_turbulence_rows(ast, turbulence, turbulence.to_matrix(), turbulence.caption)
    assert len(records) == 3
    assert {record["测风塔编号"] for record in records} == {"1006#"}
    assert [(record["高度"], record["平均湍流强度"], record["代表性湍流强度"]) for record in records] == [
        ("80m", 0.19, 0.137), ("70m", 0.20, 0.147), ("30m", 0.24, None),
    ]
    segmented = _table("turbulence_segmented", "1006#测风塔各高度湍流强度", [
        ["", "80m", "70m"],
        ["15m/s 平均值", "0.119", "0.096"],
        ["代表性湍流", "0.137", "0.147"],
    ])
    ast.tables = [turbulence, segmented]
    field_records, _ = builder._wind_resource_turbulence_records(ast, [])
    assert [(record["height"], record["average_value"], record["representative_value"]) for record in field_records] == [
        (80, 0.19, 0.137), (70, 0.20, 0.147), (30, 0.24, None),
    ]
    table = builder._wind_resource_turbulence_intensity_table_from_document(ast)
    assert table["data"] == [
        ["1006#", "80m", 0.19, 0.137],
        ["1006#", "70m", 0.20, 0.147],
        ["1006#", "30m", 0.24, None],
    ]


def test_turbulence_mapping_merges_overall_average_with_representative_value():
    records = [
        {"tower_code": "0047#", "height": 90, "height_unit": "m", "wind_speed_segment": None,
         "wind_speed_unit": None, "average_value": 0.16, "representative_value": None},
        {"tower_code": "0047#", "height": 90, "height_unit": "m", "wind_speed_segment": 15,
         "wind_speed_unit": "m/s", "average_value": 0.124, "representative_value": 0.166},
        {"tower_code": "0047#", "height": 80, "height_unit": "m", "wind_speed_segment": None,
         "wind_speed_unit": None, "average_value": 0.17, "representative_value": None},
    ]
    assert merge_turbulence_records(records) == [
        {"tower_code": "0047#", "height": 90, "height_unit": "m",
         "average_value": 0.16, "representative_value": 0.166,
         "wind_speed_segment": None, "wind_speed_unit": None},
        {"tower_code": "0047#", "height": 80, "height_unit": "m", "average_value": 0.17,
         "representative_value": None, "wind_speed_segment": None, "wind_speed_unit": None},
    ]


def test_selected_grid_scheme_overrides_candidate_station_and_binds_voltage():
    builder = create_default_parser().pipeline.exporter.result_builder
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
        "scheme", "paragraph",
        "本项目接入系统方案初步考虑为：风电场以1回110kV出线就近接入青坑110kV变电站。", 1, page=8,
    )])
    fields = {}

    builder._apply_electrical_primary_equivalents(ast, fields)

    assert fields["accessStationName"].value == "青坑110kV变电站"
    assert fields["accessibleVoltage"].value == 110
