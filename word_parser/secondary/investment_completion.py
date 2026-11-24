"""Configuration-driven investment completion, independent of JSON output files."""
from pathlib import Path
import re

from word_parser.config.loader import ConfigLoader


def load_investment_completion(config_root):
    policy = ConfigLoader(config_root).load_required_yaml("investment_completion.yaml")
    if policy.get("version") != 1:
        raise ValueError("investment_completion.yaml: unsupported version")
    for key in ("group_boundary_pattern", "group_total_pattern"):
        re.compile(policy[key], re.I)
    for key in ("group_values", "fill_missing_rows"):
        for patterns in policy[key].values():
            for pattern in patterns:
                re.compile(pattern, re.I)
    return policy


def placeholder(code):
    return "${" + code + "}"


def calculate_investment_completion(projected, policy):
    """Return changes only; source data and projected values are not mutated."""
    table = projected.get(placeholder(policy["table_placeholder"])) or {}
    rows, columns = table.get("data") or [], table.get("columns") or []
    label_index = next((i for i, name in enumerate(columns)
                        if policy["label_header_contains"] in str(name)), policy["legacy_label_index"])
    amount_index = next((i for i, name in enumerate(columns)
                         if policy["amount_header_contains"] in str(name)), policy["legacy_amount_index"])

    def clean(value):
        return re.sub(r"\s+", "", str(value or "")).replace("\u000b", "")

    def amount(row):
        value = row[amount_index] if len(row) > amount_index else None
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def matching_value(patterns):
        for row in rows:
            if len(row) > label_index and amount(row) is not None and any(re.search(p, clean(row[label_index]), re.I) for p in patterns):
                return amount(row)
        return None

    def group_value(patterns):
        for i, row in enumerate(rows):
            name = clean(row[label_index]) if len(row) > label_index else ""
            if not any(re.search(p, name, re.I) for p in patterns):
                continue
            if amount(row) is not None:
                return amount(row)
            for child in rows[i + 1:]:
                serial = clean(child[0]) if child else ""
                if re.fullmatch(policy["group_boundary_pattern"], serial, re.I):
                    break
                child_label = clean(child[label_index]) if len(child) > label_index else ""
                if re.fullmatch(policy["group_total_pattern"], child_label) and amount(child) is not None:
                    return amount(child)
        return None

    values = {}
    for code, patterns in policy["group_values"].items():
        value = group_value(patterns)
        if value is None and code in policy["retain_when_group_missing"]:
            value = projected.get(placeholder(code))
        values[placeholder(code)] = value
    for code, aliases in policy["value_aliases"].items():
        # Preserve the old fallback truthiness semantics, including zero.
        options = [projected.get(placeholder(alias)) for alias in aliases]
        selected = next((v for v in options[:-1] if v), options[-1] if options else None)
        values[placeholder(code)] = selected
    for code, source in policy["fill_missing_aliases"].items():
        if projected.get(placeholder(code)) is None:
            values[placeholder(code)] = projected.get(placeholder(source))
    for code, patterns in policy["fill_missing_rows"].items():
        if projected.get(placeholder(code)) is None:
            values[placeholder(code)] = matching_value(patterns)
    return values
