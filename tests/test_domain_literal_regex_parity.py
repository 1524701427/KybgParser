"""Every migrated domain regex must remain *exactly* the original Python pattern.

The original literal (including implicit adjacent literal concatenation) is
kept in each domain call as a fallback. Python AST resolves that literal, so
this test compares actual runtime strings instead of source escape sequences.
"""
import ast
from pathlib import Path
import re

import pytest
import yaml

from word_parser.config.domain_regex import domain_regex, domain_strings


ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "deterministic_rules.yaml").read_text(encoding="utf-8")
)
REGISTRY = CONFIG["domain_literal_regexes"]


def _found():
    entries = {}
    for path in sorted((ROOT / "word_parser" / "domains").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not isinstance(fn, ast.Name) or fn.id != "domain_regex":
                continue
            assert len(node.args) >= 4, (path, node.lineno)
            module, key = ast.literal_eval(node.args[1]), ast.literal_eval(node.args[2])
            fallback = ast.literal_eval(node.args[3])
            assert isinstance(fallback, str)
            assert module == path.stem, (path, node.lineno)
            assert (module, key) not in entries, (path, node.lineno, key)
            entries[(module, key)] = fallback
    return entries


def test_domain_regex_configuration_covers_every_rewritten_callsite_exactly():
    discovered = _found()
    configured = {
        (module, key): pattern
        for module, patterns in REGISTRY.items() for key, pattern in patterns.items()
    }
    assert len(discovered) >= 210, "Migration should contain the four large domain categories"
    assert discovered.keys() == configured.keys(), {
        "only_python": sorted(discovered.keys() - configured.keys()),
        "only_yaml": sorted(configured.keys() - discovered.keys()),
    }
    changed = {key: (expected, configured[key]) for key, expected in discovered.items()
               if configured[key] != expected}
    assert not changed, f"YAML would change original regex semantics: {changed}"


def test_every_configured_domain_regex_compiles_with_original_python_engine():
    for (module, key), value in _found().items():
        try:
            re.compile(value)
        except re.error as exc:
            pytest.fail(f"invalid legacy regex {module}.{key}: {exc}")


def test_missing_yaml_does_not_change_legacy_domain_regex():
    class Owner:
        deterministic_rules = {}

    assert domain_regex(Owner(), "finance", "absent", r"利率\s+(\d+)") == r"利率\s+(\d+)"
    assert domain_regex(object(), "wind_resource_summary", "absent", r"\d+") == r"\d+"


def test_configured_domain_alias_lists_are_fresh_copies():
    class Owner:
        deterministic_rules = {"domain_literal_lists": {
            "finance": {"example": ["流动资金", "建设贷款"]},
        }}

    value = domain_strings(Owner(), "finance", "example", ["fallback"])
    assert value == ["流动资金", "建设贷款"]
    value.append("MUTATED")
    assert domain_strings(Owner(), "finance", "example", ["fallback"]) == [
        "流动资金", "建设贷款"
    ]
    assert domain_strings(object(), "finance", "example", ["fallback"]) == ["fallback"]


def test_ordered_domain_alias_and_pattern_lists_equal_original_python():
    """Compare actual Python list values, not lossy text/regex serializations."""
    lists = CONFIG.get("domain_literal_lists") or {}
    discovered: dict[tuple[str, str], list[str]] = {}
    for path in sorted((ROOT / "word_parser" / "domains").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "domain_strings":
                continue
            assert len(node.args) == 4, (path, node.lineno)
            module, key = ast.literal_eval(node.args[1]), ast.literal_eval(node.args[2])
            fallback = ast.literal_eval(node.args[3])
            assert isinstance(fallback, list) and all(isinstance(v, str) for v in fallback)
            assert module == path.stem, (path, node.lineno)
            assert (module, key) not in discovered
            discovered[(module, key)] = fallback
    configured = {(module, key): value for module, group in lists.items()
                  for key, value in group.items()}
    assert len(discovered) >= 110, "Expected substantial alias/header list migration"
    assert discovered.keys() == configured.keys(), {
        "only_python": sorted(discovered.keys() - configured.keys()),
        "only_yaml": sorted(configured.keys() - discovered.keys()),
    }
    assert all(configured[key] == fallback for key, fallback in discovered.items()), {
        "mismatches": [key for key, fallback in discovered.items() if configured[key] != fallback]
    }


def test_domain_policy_does_not_modify_list_order_or_original_config():
    class Owner:
        deterministic_rules = {"domain_literal_lists": {
            "civil_land": {"header_1": ["箱变基础", "升压站", "总计"]},
        }}

    ordered = domain_strings(Owner(), "civil_land", "header_1", ["fallback"])
    assert ordered == ["箱变基础", "升压站", "总计"]
    ordered.reverse()
    assert domain_strings(Owner(), "civil_land", "header_1", ["fallback"]) == [
        "箱变基础", "升压站", "总计"
    ]
