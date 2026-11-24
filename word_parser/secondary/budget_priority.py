"""Budget-first scalar adoption after legacy completion, before publishing outputs.

Keep every decision and the original value; never guess units or aggregate rows.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal
import re

from word_parser.config.loader import ConfigLoader
from word_parser.document.table_recovery import label


def enrich_specs(specs, schema, loader, policy):
    """Cover schema placeholders, including currently missing and secondary-only fields."""
    section_by_code = {code: section["name"] for section in schema.get("sections", [])
                       for code in section.get("fields", [])}
    table_codes = {code for section in schema.get("sections", []) for code in section.get("tables", [])
                   if isinstance(code, str)}
    for code in schema.get("output_field_codes", {}):
        if code not in table_codes:
            specs.setdefault(code, {})
    for code, section in section_by_code.items():
        specs.setdefault(code, {})["section"] = section
    if not (policy.get("adoption") or {}).get("inherit_scalar_table_rules"):
        return
    rules = loader.load_yaml("table_field_extractors.yaml").get("rules") or []
    for rule in rules:
        code = rule.get("field_code")
        if not isinstance(code, str) or "{" in code or code not in specs:
            continue
        spec = specs[code]
        for target, source in (("name", "field_name"), ("unit", "unit"), ("value_type", "value_type"), ("section", "section")):
            if not spec.get(target) and rule.get(source):
                spec[target] = rule[source]
        row, column = rule.get("row") or {}, rule.get("column") or {}
        # Only simple row/column lookup rules: do not reuse an aggregation or
        # regex extraction as though it were an equivalent scalar.
        if (rule.get("operation", "cell") == "cell" and rule.get("value_type") == "number"
                and row.get("type") == "label" and isinstance(row.get("aliases"), list)
                and isinstance(column.get("aliases"), list) and not any(
                    rule.get(key) for key in ("value_pattern", "value_patterns", "include_patterns", "merge_following_rows", "variables", "towers")
                ) and not row.get("match") and not row.get("occurrence")):
            spec["aliases"] = list(dict.fromkeys([*(spec.get("aliases") or []), *row["aliases"]]))
            # Aliases are searched but do not become trusted automatically.
            # Column semantics are still determined by field role and unit.


def _placeholder(value):
    return value if str(value).startswith("${") else "${" + str(value) + "}"


def _numeric(value):
    from word_parser.secondary.cross_validation import number
    return number(value)


def _same(a, b, policy):
    from word_parser.secondary.cross_validation import close
    return close(a, b, policy)


def _is_missing(value):
    from word_parser.extraction.selection import has_value
    return not has_value(value)


def _json_number(value):
    n = _numeric(value)
    if n is None:
        raise ValueError("Budget candidate is not a finite number")
    return int(n) if n == n.to_integral_value() else float(n)


def _combined_targets(code, schema, result, mapped):
    """Find single-row combined display cells. Ambiguous/multi-row tables block adoption."""
    targets = []
    for key, config in (schema.get("combined_detail_field_mappings") or {}).items():
        columns = config.get("fields") or {}
        if code not in columns:
            continue
        for section in result.get("sections") or []:
            for table in section.get("tables") or []:
                if table.get("key") != key:
                    continue
                keys = table.get("columnKeys") or []
                headers = table.get("columns") or []
                target = columns[code]
                positions = [i for i, k in enumerate(keys or headers) if k in (code, target)]
                if not positions:
                    positions = [i for i, k in enumerate(headers) if k == target]
                data = table.get("data") or []
                if config.get("multi") or len(positions) != 1 or len(data) != 1 or not isinstance(data[0], list) or positions[0] >= len(data[0]):
                    return None
                targets.append((key, table, positions[0]))
    return targets


def apply_budget_priority(parse_result, details, audit, config_root):
    """Apply all independently eligible scalar values; audit-only is side-effect free."""
    from word_parser.secondary.cross_validation import load_policy
    policy = load_policy(config_root)
    if not policy or not policy["enabled"] or policy["mode"] != "prefer_budget":
        return 0
    adoption = policy["adoption"]
    schema = ConfigLoader(config_root).load_required_yaml("output_schema.yaml")
    outputs = schema.get("output_field_codes") or {}
    result, mapped = parse_result["result"], parse_result["mapped"]
    field_index = details.setdefault("fieldIndex", {})
    section_index = {s.get("name"): s for s in result.get("sections") or []}
    fields = defaultdict(list)
    for section in result.get("sections") or []:
        for field in section.get("fields") or []:
            fields[field.get("fieldCode")].append((section.get("name"), field))
    table_codes = {t.get("key") for section in result.get("sections") or [] for t in section.get("tables") or []}
    table_codes.update(c for section in schema.get("sections") or [] for c in section.get("tables") or [] if isinstance(c, str))
    transformed = set(schema.get("field_value_transforms") or {})
    transformed.update(schema.get("field_value_fallbacks") or {})
    transformed.update((schema.get("field_value_fallbacks") or {}).values())
    counts = Counter()
    for report in audit["fields"]:
        code = report["fieldCode"]
        section = report.get("section")
        matches = fields.get(code, [])
        if matches:
            section = matches[0][0]
        original_value = report.get("finalValue")
        placeholder = _placeholder(outputs[code]) if code in outputs else None
        original_mapped = mapped.get(placeholder) if placeholder else None
        decision = {"action": "not_adopted", "originalValue": deepcopy(original_value),
                    "originalMappedValue": deepcopy(original_mapped), "adoptedValue": None}
        report["adoption"] = decision

        def skip(reason):
            decision["reason"] = reason
            counts[reason] += 1

        if not placeholder or code in table_codes:
            skip("not_scalar_mapping")
            continue
        if section in adoption["excluded_sections"] or any(name in adoption["excluded_sections"] for name, _ in matches):
            skip("excluded_section")
            continue
        if not section:
            skip("section_unknown")
            continue
        if code in transformed:
            skip("dependent_mapping")
            continue
        candidates = [c for c in report["candidates"] if c.get("status") == "eligible"
                      and _numeric(c.get("value")) is not None and c.get("unit")
                      and not c.get("adoptionBlocked")
                      and (c.get("budgetSection") or not any(re.search(p, str((c.get("source") or {}).get("tableName") or ""))
                          for p in adoption.get("excluded_title_patterns", [])))]
        numeric_type = report.get("valueType") in adoption["numeric_types"]
        if not numeric_type and not report.get("unit") and _numeric(original_value) is None and _numeric(original_mapped) is None and not candidates:
            skip("not_quantitative")
            continue
        if any(not _is_missing(v) and _numeric(v) is None for v in (original_value, original_mapped)):
            skip("non_scalar_or_non_numeric_value")
            continue
        if not candidates:
            skip("no_reliable_budget_candidate")
            continue
        first = candidates[0]
        if any(not _same(first["value"], c["value"], policy) or label(first["unit"]) != label(c["unit"]) for c in candidates[1:]):
            skip("budget_tables_disagree")
            continue
        unit = first["unit"]
        if any(f.get("unit") and label(f["unit"]) != label(unit) for _, f in matches):
            # The candidates are in field standard units; don't change a display
            # with an unknown or different unit contract.
            skip("result_unit_mismatch")
            continue
        combined = _combined_targets(code, schema, result, mapped)
        if combined is None:
            skip("ambiguous_combined_table")
            continue
        if not matches and section not in section_index and not combined:
            skip("section_unavailable")
            continue
        value = _json_number(first["value"])
        same_result = not _is_missing(original_value) and _same(original_value, value, policy)
        same_mapped = not _is_missing(original_mapped) and _same(original_mapped, value, policy)
        source = {"sourceType": "table", "matchMethod": "budget_priority",
                  **deepcopy(first["source"]), "unit": unit, "rawValue": first["rawValue"]}
        decision.update(action="confirmed" if same_result and same_mapped else "filled" if _is_missing(original_value) and _is_missing(original_mapped) else "corrected",
                        reason="budget_consensus", adoptedValue=value, adoptedUnit=unit,
                        adoptedSource=source, supportingSources=[deepcopy(c["source"]) for c in candidates])
        counts[decision["action"]] += 1
        report["finalValue"], report["mappedValue"] = value, value
        report["mappedComparison"] = "consistent"
        if decision["action"] == "confirmed":
            # Mark the adopted evidence in details, while retaining exact original
            # representation if it already agrees within tolerance.
            value = original_value
            report["finalValue"], report["mappedValue"] = original_value, original_mapped
            decision["adoptedValue"] = original_value
        else:
            mapped[placeholder] = value
            if not matches and not combined:
                item = {"fieldCode": code, "name": report["fieldName"], "value": value, "unit": unit}
                section_index[section].setdefault("fields", []).append(item)
                matches = [(section, item)]
            for _, item in matches:
                item["value"] = value
                if not item.get("unit"):
                    item["unit"] = unit
        entry = field_index.setdefault(code, {"fieldCode": code, "name": report["fieldName"], "section": section})
        old_source = deepcopy(entry.get("source"))
        decision["originalSource"] = old_source
        entry.update(value=value, unit=unit, status="PASS", source=source,
                     sources=decision["supportingSources"], budgetAdoption=deepcopy(decision))
        for key in ("articleLocation", "location"):
            if key in entry:
                entry[key] = {"tableId": source.get("tableId"), "page": source.get("page"),
                              "row": source.get("row"), "column": source.get("column"),
                              "sectionPath": source.get("sectionPath")}
        api_fields = parse_result.get("fields")
        if isinstance(api_fields, dict):
            api_fields[code] = deepcopy(entry)
        for detail_section in details.get("sections") or []:
            for item in detail_section.get("fields") or []:
                if item.get("fieldCode") == code:
                    item.update(deepcopy(entry))
        if decision["action"] != "confirmed":
            for key, table, col in combined:
                table["data"][0][col] = value
                mapped_table = mapped.get(_placeholder(outputs[key])) if key in outputs else None
                if isinstance(mapped_table, dict):
                    mapped_table["data"] = deepcopy(table["data"])
                detail_table = (details.get("tableIndex") or {}).get(key)
                if isinstance(detail_table, dict):
                    detail_table["data"] = deepcopy(table["data"])
                    detail_table["sampleRows"] = deepcopy(table["data"][:1])
                    detail_table.setdefault("budgetAdoptions", {})[code] = deepcopy(decision)
                for ds in details.get("sections") or []:
                    for dt in ds.get("tables") or []:
                        if dt.get("key") == key:
                            dt["data"] = deepcopy(table["data"])
                            dt["sampleRows"] = deepcopy(table["data"][:1])
                            dt.setdefault("budgetAdoptions", {})[code] = deepcopy(decision)
    audit["summary"]["adoptionStatuses"] = dict(counts)
    audit["summary"]["adoptedFieldCount"] = counts["filled"] + counts["corrected"]
    return counts["filled"] + counts["corrected"]
