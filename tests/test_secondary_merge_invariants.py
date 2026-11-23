"""Protect original first-stage value priority during secondary reconciliation."""
from copy import deepcopy

import pytest

from word_parser.secondary.table_values.results import final_result_with_table_values


@pytest.mark.parametrize(
    "primary_value, expected_value",
    [(120, 120), (0, 0), ("", 121), (None, 121)],
)
def test_secondary_only_fills_missing_primary_value(primary_value, expected_value):
    secondary = {
        "fieldCode": "hubHeight", "fieldName": "轮毂高度",
        "status": "OK", "value": 121, "unit": "m",
        "source": {"tableKey": "t1", "rowIndex": 2, "columnIndex": 1},
    }
    enhanced = {
        "filePath": "case.docx",
        "sections": [{
            "name": "风机参数",
            "fields": [{"fieldCode": "hubHeight", "name": "轮毂高度",
                        "value": primary_value, "unit": "m"}],
            "tables": [],
            "tableFields": [secondary],
        }],
    }
    before = deepcopy(enhanced)
    final = final_result_with_table_values(enhanced)
    fields = final["sections"][0]["fields"]
    assert len(fields) == 1
    assert fields[0]["fieldCode"] == "hubHeight"
    assert fields[0]["value"] == expected_value
    assert enhanced == before  # Secondary merge is copy-on-write.


def test_nil_field_does_not_override_existing_primary_value():
    enhanced = {
        "sections": [{
            "name": "电气一次",
            "fields": [{"fieldCode": "stationTransformer", "value": "SCB18-100"}],
            "tables": [],
            "tableFields": [
                {"fieldCode": "stationTransformer", "status": "NIL", "value": None,
                 "nilReason": "row_not_found"}
            ],
        }],
    }
    final = final_result_with_table_values(enhanced)
    assert final["sections"][0]["fields"] == [
        {"fieldCode": "stationTransformer", "value": "SCB18-100"}
    ]


def test_derived_table_cannot_overwrite_existing_nonempty_primary_table():
    enhanced = {
        "sections": [{
            "name": "资源章节",
            "fields": [],
            "tables": [{"key": "windSpeeds", "columns": ["高度", "风速"], "data": [[80, 6.2]]}],
            "derivedTables": [{
                "key": "windSpeeds", "name": "备用速度表",
                "status": "OK", "columns": ["高度", "风速"], "data": [[80, 9.9]],
            }],
        }],
    }
    final = final_result_with_table_values(enhanced)
    assert final["sections"][0]["tables"][0]["data"] == [[80, 6.2]]
