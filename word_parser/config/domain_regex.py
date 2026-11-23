"""Read domain-specific literal regex policies from deterministic_rules.yaml.

The configured pattern and the Python legacy fallback are intentionally identical
until real-document parity is demonstrated. Python still performs the search,
matching, captures, arithmetic and result selection.

This function does not read files at matching time: ResultBuilder already loaded
the deterministic YAML once for the current parser instance. Domain unit-test
shims without this config continue to use their existing Python fallback.
"""
from __future__ import annotations

from typing import Any


def domain_regex(owner: Any, module: str, rule: str, fallback: str) -> str:
    config = getattr(owner, "deterministic_rules", None)
    if not isinstance(config, dict):
        return fallback
    registry = config.get("domain_literal_regexes")
    if not isinstance(registry, dict):
        return fallback
    group = registry.get(module)
    if not isinstance(group, dict):
        return fallback
    pattern = group.get(rule)
    if pattern is None:
        return fallback
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
        return list(fallback)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"domain_literal_lists.{module}.{rule} must be a list of strings")
    return list(value)
