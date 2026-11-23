"""YAML is authoritative for primary domain matching and named operators."""
from pathlib import Path

import pytest
import yaml

from word_parser.config.domain_regex import (
    domain_regex, domain_strings, validate_domain_literals,
)
from word_parser.primary.domain_dispatch import (
    DomainOperatorSchedule, LEGACY_FIELD_ORDER, LEGACY_SCALAR_ORDER,
    apply_domain_field_operators, collect_domain_scalar_overrides,
    load_domain_schedule,
)


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs"
DETERMINISTIC = yaml.safe_load((CFG / "deterministic_rules.yaml").read_text(encoding="utf-8"))


def test_full_parser_domain_yaml_is_strict_and_valid():
    assert DETERMINISTIC["strict_domain_literals"] is True
    validate_domain_literals(DETERMINISTIC)
    schedule = load_domain_schedule(CFG)
    assert schedule.field_operators == LEGACY_FIELD_ORDER
    assert schedule.scalar_operators == LEGACY_SCALAR_ORDER


def test_missing_or_bad_yaml_field_fails_when_strict():
    class Owner:
        strict_domain_literals = True
        deterministic_rules = DETERMINISTIC

    with pytest.raises(KeyError, match="finance.missing"):
        domain_regex(Owner(), "finance", "missing", r"\d+")
    with pytest.raises(KeyError, match="finance.missing"):
        domain_strings(Owner(), "finance", "missing", ["测试"])
    class MissingConfig:
        strict_domain_literals = True
        deterministic_rules = {}

    with pytest.raises(KeyError, match="domain_literal_regexes"):
        domain_regex(MissingConfig(), "finance", "search_001", r"\d+")


def test_real_yaml_values_override_python_fallback_when_strict():
    class Owner:
        strict_domain_literals = True
        deterministic_rules = DETERMINISTIC
    pattern = DETERMINISTIC["domain_literal_regexes"]["finance"]["search_001"]
    assert domain_regex(Owner(), "finance", "search_001", "NOT_A_VALID_ORIGINAL") == pattern
    aliases = DETERMINISTIC["domain_literal_lists"]["finance"]["list_001"]
    assert domain_strings(Owner(), "finance", "list_001", ["WRONG"]) == aliases


def test_invalid_regex_and_bad_alias_array_fail_validation():
    invalid = {
        "domain_literal_regexes": {"wind": {"bad": "("}},
        "domain_literal_lists": {"finance": {"a": ["合计"]}},
    }
    with pytest.raises(ValueError, match="Invalid regex"):
        validate_domain_literals(invalid)
    invalid["domain_literal_regexes"]["wind"]["bad"] = r"\d+"
    invalid["domain_literal_lists"]["finance"]["a"] = [1]
    with pytest.raises(ValueError, match="ordered strings"):
        validate_domain_literals(invalid)


def test_domain_schedule_rejects_unknown_or_reordered_operators(tmp_path):
    policy = yaml.safe_load((CFG / "domain_extraction_pipeline.yaml").read_text(encoding="utf-8"))
    wrong = {**policy, "field_operators": policy["field_operators"][:-1]}
    with pytest.raises(ValueError, match="field_operators"):
        DomainOperatorSchedule.from_policy(wrong)
    wrong = {**policy, "scalar_operators": ["eval_untrusted_code"]}
    with pytest.raises(ValueError, match="scalar_operators"):
        DomainOperatorSchedule.from_policy(wrong)
    with pytest.raises(FileNotFoundError):
        load_domain_schedule(tmp_path)


def test_registered_python_domain_methods_keep_original_business_order():
    events = []

    class Owner:
        domain_operator_schedule = DomainOperatorSchedule.from_policy(
            yaml.safe_load((CFG / "domain_extraction_pipeline.yaml").read_text(encoding="utf-8"))
        )

        def __getattr__(self, name):
            def handle(*args, **kwargs):
                events.append((name, args, kwargs))
                return {name: name}
            return handle

    owner = Owner()
    fields, details = {}, {}
    ast = object()
    apply_domain_field_operators(
        owner, ast, fields, details,
        configured_scalar_codes={"amount"},
        combined_skip_codes={"discard"},
        generation_skip_codes={"generation"},
    )
    assert len(events) == len(LEGACY_FIELD_ORDER)
    assert [name for name, _, _ in events] == [
        "_apply_land_field_overrides",
        "_drop_combined_detail_only_field_candidates",
        "_apply_combined_detail_field_overrides",
        "_apply_wind_resource_collection_overrides",
        "_apply_road_parameter_field_overrides",
        "_apply_electrical_primary_table_field_overrides",
        "_apply_generation_field_overrides",
        "_apply_wind_foundation_table_field_overrides",
        "_apply_finance_field_overrides",
        "_apply_earthwork_field_overrides",
        "_apply_investment_summary_field_overrides",
        "_apply_cover_text_overrides",
        "_apply_cover_ocr_overrides",
    ]
    events.clear()
    output = collect_domain_scalar_overrides(owner, ast, {"configured": "yes"}, {"amount"})
    assert len(events) == len(LEGACY_SCALAR_ORDER) - 1
    assert output["configured"] == "yes"
    assert output["_finance_table_scalar_override_values"] == "_finance_table_scalar_override_values"
    assert events[0][0] == "_extract_scalar_overrides"
    assert events[-1][0] == "_finance_table_scalar_override_values"
