"""Mapping projections are decided by output_schema.yaml, not field-specific ifs."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from word_parser.mapping.projector import mapping_from_detail_json
from word_parser.mapping.wind import merge_turbulence_records


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = yaml.safe_load((ROOT / "configs" / "output_schema.yaml").read_text(encoding="utf-8"))


def _stub(transforms=None):
    codes = {
        "financeInsuranceRate": "${finance_insurance_rate}",
        "hubHeightAirDensityRange": "${hubHeightAirDensityRange}",
        "windResourceTurbulenceIntensityRecords": "${eachTierHeightTurbulenceTableList}",
    }
    return SimpleNamespace(
        output_field_codes=codes,
        field_value_fallbacks=SCHEMA["field_value_fallbacks"],
        field_value_transforms=SCHEMA["field_value_transforms"] if transforms is None else transforms,
        _required_table_keys=lambda: [],
    )


def test_schema_controls_finance_fallback_and_air_density_projection():
    detail = {"fieldIndex": {
        "financeInsuranceRate": {"value": None},
        "insuranceRate": {"value": 0.8},
        "windResourceAirDensityRecords": {"value": [
            {"tower_code": "105#", "height": 100, "value": 1.22, "source": "table"},
            {"tower_code": "106#", "height": None, "value": 1.23},
        ]},
    }}
    mapped = mapping_from_detail_json(detail, _stub())
    assert mapped["${finance_insurance_rate}"] == 0.8
    assert mapped["${hubHeightAirDensityRange}"] == [
        {"tower_code": "105#", "height": 100, "value": 1.22}
    ]


def test_yaml_transform_for_turbulence_matches_existing_python_operator():
    records = [{"tower_code": "105#", "height": 100, "value": 0.11}]
    mapped = mapping_from_detail_json(
        {"fieldIndex": {"windResourceTurbulenceIntensityRecords": {"value": records}}},
        _stub(),
    )
    assert mapped["${eachTierHeightTurbulenceTableList}"] == merge_turbulence_records(records)


def test_remove_yaml_transform_disables_only_that_projection():
    config = dict(SCHEMA["field_value_transforms"])
    config.pop("hubHeightAirDensityRange")
    detail = {"fieldIndex": {
        "windResourceAirDensityRecords": {"value": [
            {"tower_code": "105#", "height": 100, "value": 1.2}
        ]}
    }}
    mapped = mapping_from_detail_json(detail, _stub(config))
    assert mapped["${hubHeightAirDensityRange}"] is None


def test_unknown_mapping_operator_fails_instead_of_running_arbitrary_python():
    with pytest.raises(ValueError, match="unknown mapping operator"):
        mapping_from_detail_json(
            {"fieldIndex": {"windResourceTurbulenceIntensityRecords": {"value": 1}}},
            _stub({"windResourceTurbulenceIntensityRecords": {"operator": "eval"}}),
        )


def test_output_schema_has_required_registered_source_rules():
    assert SCHEMA["field_value_fallbacks"]["financeInsuranceRate"] == "insuranceRate"
    assert SCHEMA["field_value_transforms"]["hubHeightAirDensityRange"]["source_field"] == "windResourceAirDensityRecords"
    assert SCHEMA["field_value_transforms"]["windResourceTurbulenceIntensityRecords"]["operator"] == "merge_turbulence_records"
