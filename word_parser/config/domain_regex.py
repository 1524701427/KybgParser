"""Read domain-specific literal regex policies from deterministic_rules.yaml.

The configured pattern and the Python legacy fallback are intentionally identical
until real-document parity is demonstrated. Python still performs the search,
matching, captures, arithmetic and result selection.

This function does not read files at matching time: ResultBuilder already loaded
the deterministic YAML once for the current parser instance. Domain unit-test
shims without this config continue to use their existing Python fallback.
"""
from __future__ import annotations

import re
from typing import Any


def validate_domain_literals(policy: dict[str, Any]) -> None:
    """Fail at parser startup for malformed YAML-controlled extraction rules."""
    if not isinstance(policy, dict):
        raise ValueError("deterministic_rules.yaml must be an object")
    for kind, expected in (("domain_literal_regexes", str), ("domain_literal_lists", list)):
        registry = policy.get(kind)
        if not isinstance(registry, dict):
            raise ValueError(f"deterministic_rules.yaml: {kind} must be a mapping")
        for group_name, group in registry.items():
            if not isinstance(group, dict):
                raise ValueError(f"{kind}.{group_name} must be a mapping")
            for rule_id, value in group.items():
                if not isinstance(value, expected):
                    raise ValueError(f"{kind}.{group_name}.{rule_id} has invalid value type")
                if kind == "domain_literal_regexes":
                    try:
                        re.compile(value)
                    except re.error as exc:
                        raise ValueError(f"Invalid regex at {kind}.{group_name}.{rule_id}") from exc
                elif not value or not all(isinstance(v, str) for v in value):
                    raise ValueError(f"{kind}.{group_name}.{rule_id} must contain ordered strings")


def _absent(owner: Any, module: str, rule: str, fallback: Any, kind: str) -> Any:
    if bool(getattr(owner, "strict_domain_literals", False)):
        raise KeyError(f"Required extraction rule missing: {kind}.{module}.{rule}")
    return fallback


def domain_regex(owner: Any, module: str, rule: str, fallback: str) -> str:
    config = getattr(owner, "deterministic_rules", None)
    if not isinstance(config, dict):
        return _absent(owner, module, rule, fallback, "domain_literal_regexes")
    registry = config.get("domain_literal_regexes")
    if not isinstance(registry, dict):
        return _absent(owner, module, rule, fallback, "domain_literal_regexes")
    group = registry.get(module)
    if not isinstance(group, dict):
        return _absent(owner, module, rule, fallback, "domain_literal_regexes")
    pattern = group.get(rule)
    if pattern is None:
        return _absent(owner, module, rule, fallback, "domain_literal_regexes")
    if not isinstance(pattern, str):
        raise ValueError(f"domain_literal_regexes.{module}.{rule} must be a string")
    return pattern


def domain_strings(owner: Any, module: str, rule: str, fallback: list[str]) -> list[str]:
    """Get alias/header or regex-pattern lists without changing caller algorithms.

    Return a fresh list to protect configured rules from accidental mutation.
    When the YAML section is absent, preserve the literal Python fallback.
    """
    config = getattr(owner, "deterministic_rules", None)
    if not isinstance(config, dict):
        return list(fallback)
    registry = config.get("domain_literal_lists")
    group = registry.get(module) if isinstance(registry, dict) else None
    value = group.get(rule) if isinstance(group, dict) else None
    if value is None:
        return _absent(owner, module, rule, list(fallback), "domain_literal_lists")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"domain_literal_lists.{module}.{rule} must be a list of strings")
    return list(value)
