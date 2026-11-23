from types import SimpleNamespace

from word_parser.domains.wind_resource_summary import WindResourceSummaryRulesMixin
from word_parser.extraction.explicit_text_fallback import explicit_text_values


def test_explicit_overview_and_equipment_text():
    ast = SimpleNamespace(
        meta={"pdf_page_texts": [
            {"page": 1, "text": "某县甲风电场工程可行性研究报告\n某设计有限公司编制\n"
                                 "本项目建设方为某投资有限公司。\n本项目位于某省某市某县西部甲乙镇、丙丁镇一带。\n"
                                 "场区海拔为1200~1450m。新建1座110kV升压站，规模按1×100MVA设计。\n"
                                 "通过4回35kV集电线路接入。箱变容量为4400kVA。"},
        ]},
        blocks=[],
    )
    values = explicit_text_values(ast)
    assert values["projectName"][0] == "某县甲风电场工程"
    assert values["designUnit"][0] == "某设计有限公司"
    assert values["investmentOwnerCompany"][0] == "某投资有限公司"
    assert values["projectAddressTown"][0] == "甲乙镇、丙丁镇"
    assert values["siteElevationRange"][0] == "1200~1450"
    assert values["electricalPrimarySubstationVoltageLevel"][0] == 110
    assert values["circuitCount"][0] == 4
    assert values["mainTransformerRatedCapacity"][0] == 100000
    assert values["electricalPrimaryBoxTransformerCapacity"][0] == 4400


def test_flattened_tower_table_keeps_tower_values_aligned():
    pages = [
        {"page": 2, "text": "测风塔资料一览表\n0047#\n27°6′2.88″\n107°20′39.72″\n1380\n"
                            "2017.4.6~2018.7.11\n0048#\n27°2′18.0″\n107°24′36.96″\n1375\n"
                            "2017.4.6~2017.8.24\n"},
        {"page": 3, "text": "各测风塔各高度风速及风功率\n0047#\n0048#\n高度m\n风速\n风功率密度\n"
                            "105\n5.60\n163\n5.33\n138\n"},
        {"page": 4, "text": "0047#测风塔8m高度处的空气密度为1.04kg/m3。\n"
                            "0048#测风塔8m高度处的空气密度为1.05kg/m3。"},
    ]
    rows = [{"测风塔编号": "0047#"}, {"测风塔编号": "0048#"}]
    WindResourceSummaryRulesMixin()._fill_resource_rows_from_pdf_text(SimpleNamespace(meta={"pdf_page_texts": pages}), rows)
    assert rows[0]["测风塔经度"] == "107°20′39.72″"
    assert rows[1]["测风周期"] == "2017.4.6~2017.8.24"
    assert rows[0]["轮毂高度平均风速m/s"] == 5.6
    assert rows[1]["轮毂高度平均风功率密度W/m²"] == 138
    assert rows[0]["高度对应的空气密度"] == 1.04
    assert rows[1]["高度对应的空气密度"] == 1.05
    assert rows[1]["_cellSources"]["测风周期"]["source"]["page"] == 2


def test_electrical_equipment_rows_are_read_with_units():
    ast = SimpleNamespace(
        meta={"pdf_page_lines": [{"page": 5, "text": "蓄电池组\n220V/300Ah，104 节\n组\n1\n"
                                                   "UPS 逆变电源屏\n7.5kVA\n面\n1\n"}]},
        blocks=[],
    )
    values = explicit_text_values(ast)
    assert values["electricalSecondaryBatterySpec"][0] == "220V/300Ah，104 节"
    assert values["electricalSecondaryBatteryQuantity"][0] == 1
    assert values["electricalSecondaryUpsSpec"][0] == "7.5kVA"
    assert values["electricalSecondaryUpsUnit"][0] == "面"
