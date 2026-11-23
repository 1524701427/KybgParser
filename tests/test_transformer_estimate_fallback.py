from word_parser.mapping.equipment import _fill_transformers_from_installation_estimate


def test_transformer_estimate_rows_fill_missing_equipment_fields_without_overwriting():
    mapped = {
        "${installation_engineering_budgets_table}": {
            "columns": ["序号", "项目名称及规格", "单位", "数量"],
            "data": [
                ["", "主变压器 SZ18-100000/110 三相双绕组", "台", 2],
                ["", "35kV接地变成套装置 DKSC-800/35", "套", 1],
                ["", "35kV接地变兼站用变成套装置 DKSC-800/35-315/0.4", "台", 1],
            ],
        },
        "${main_transformer_model}": None,
        "${main_transformer_rated_capacity}": None,
        "${main_transformer_num}": None,
        "${grounding_station_transformer_model}": None,
        "${grounding_transformer_model}": "verified-from-primary-table",
    }
    fields = [{"fieldCode": "mainTransformerModel", "value": None}]
    _fill_transformers_from_installation_estimate({"mapped": mapped, "result": {"sections": [{"fields": fields}]}})
    assert mapped["${main_transformer_model}"] == "SZ18-100000/110"
    assert mapped["${main_transformer_rated_capacity}"] == 100000
    assert mapped["${main_transformer_num}"] == 2
    assert mapped["${grounding_station_transformer_model}"] == "DKSC-800/35-315/0.4"
    assert mapped["${grounding_station_transformer_capacity}"] == 800
    assert mapped["${grounding_station_transformer_quantity}"] == 1
    assert mapped["${grounding_transformer_model}"] == "verified-from-primary-table"
    assert fields[0]["value"] == "SZ18-100000/110"


def test_combined_and_standalone_grounding_transformers_keep_separate_mapping_groups():
    """兼用变和独立接地变分别写入前端已有的两组占位符。"""
    mapped = {
        "${installation_engineering_budgets_table}": {
            "columns": ["序号", "项目名称及规格", "单位", "数量"],
            "data": [
                ["", "35kV接地变兼站用变成套装置 DKSC-800/35-315/0.4", "台", 1],
                ["", "35kV接地变成套装置 DKSC-500/35", "台", 1],
            ],
        },
    }

    _fill_transformers_from_installation_estimate({"mapped": mapped, "result": {"sections": []}})

    assert mapped["${grounding_station_transformer_model}"] == "DKSC-800/35-315/0.4"
    assert mapped["${grounding_station_transformer_capacity}"] == 800
    assert mapped["${grounding_transformer_model}"] == "DKSC-500/35"
    assert mapped["${grounding_transformer_capacity}"] == 500


