"""Audit every configured/observed field against the recovered raw budget tables.

Exact labels, explicit column roles, dimensional units and scope checks prevent
quantity/price and single-unit/total mixups. Never write business values.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import re
from pathlib import Path

from word_parser.config.loader import ConfigLoader
from word_parser.document.table_recovery import label
from word_parser.extraction.candidate_registry import CandidateRegistry, source_key, token


def load_policy(root):
    path = Path(root) / "cross_validation.yaml"
    if not path.is_file():
        return None  # compatibility for saved outputs and older custom configurations
    policy = ConfigLoader(root).load_required_yaml("cross_validation.yaml")
    if policy.get("version") != 1 or policy.get("mode") != "audit" or type(policy.get("enabled")) is not bool:
        raise ValueError("cross_validation.yaml: unsupported policy")
    for key in ("source_section_patterns", "source_title_patterns", "scope_exclude_patterns"):
        for pattern in policy[key]:
            re.compile(pattern)
    for rule in policy.get("field_overrides", {}).values():
        for pattern in rule.get("scope_exclude_patterns", []):
            re.compile(pattern)
    for entry in policy.get("field_role_patterns", []):
        re.compile(entry["pattern"])
        if entry["role"] not in policy["column_roles"]:
            raise ValueError("cross_validation.yaml: unknown column role")
    for pattern in policy.get("amount_column_exclude_patterns", []):
        re.compile(pattern)
    for group in policy["unit_groups"].values():
        if not isinstance(group, dict) or not group or any(Decimal(str(v)) <= 0 for v in group.values()):
            raise ValueError("cross_validation.yaml: invalid unit group")
    return policy


def present(value):
    return value is not None and value != "" and value != [] and value != {}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        val = Decimal(str(value).strip().replace(",", "").replace("，", ""))
        return val if val.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def cell_text(cell):
    return cell["text"] if cell else ""


def header_role(column, names):
    normalized = {label(v) for v in names}
    return any(label(re.sub(r"[（(][^）)]*[）)]$", "", part.strip())) in normalized or label(part) in normalized
               for part in str(column).split(" / "))


def source_tables(tables, policy):
    for table in tables:
        section = " / ".join([*table.get("sectionPath", []), *table.get("canonicalSections", [])])
        if any(re.search(p, section) for p in policy["source_section_patterns"]) or any(
            re.search(p, str(table.get("caption") or "")) for p in policy["source_title_patterns"]
        ):
            yield table


def index_rows(tables, policy):
    rows = defaultdict(list)
    for table in tables:
        headers = table["columns"]
        labels = [i for i, col in enumerate(headers) if header_role(col, policy["label_headers"])]
        units = [i for i, col in enumerate(headers) if header_role(col, policy["unit_headers"])]
        if not labels:
            continue
        for row_index, row in enumerate(table["rows"]):
            if row_index in table["headerRows"]:
                continue
            unit = cell_text(row[units[0]]) if len(units) == 1 else ""
            for col in labels:
                text = cell_text(row[col])
                if label(text):
                    rows[label(text)].append((table, row_index, row, unit, text))
    return rows


def converted(raw, source_unit, target_unit, policy):
    numeric = number(raw)
    if numeric is None:
        return None
    source, target = label(source_unit), label(target_unit)
    if not source or not target:
        return None
    if source == target:
        return numeric
    for group in policy["unit_groups"].values():
        factors = {label(key): Decimal(str(value)) for key, value in group.items()}
        if source in factors and target in factors:
            return numeric * factors[source] / factors[target]
    return None


def close(a, b, policy):
    a, b = number(a), number(b)
    if a is None or b is None:
        return False
    return abs(a - b) <= max(Decimal(str(policy["numeric_absolute_tolerance"])),
                              max(abs(a), abs(b)) * Decimal(str(policy["numeric_relative_tolerance"])))


def _selected_sources(field, detail):
    srcs = [field.get("source") or {}, *(field.get("sources") or [])]
    if detail:
        srcs.extend([detail.get("source") or {}, *(detail.get("sources") or [])])
    return [s for s in srcs if isinstance(s, dict)]


def _scope_text(table, row):
    return " / ".join([str(table.get("caption") or ""), *table.get("sectionPath", []),
                       *(cell_text(c) for c in row)])


def field_role(spec, rule, policy):
    if rule.get("role"):
        return rule["role"]
    for entry in policy.get("field_role_patterns", []):
        if re.search(entry["pattern"], str(spec.get("name") or "")):
            return entry["role"]
    return None


def amount_unit(heading, policy):
    # An explicit unit inside a heading is required. Do not use a row's
    # equipment unit or infer currency from the size of a number.
    text = str(heading)
    for unit in policy.get("amount_units", []):
        if re.search(r"[（(/\s]" + re.escape(unit) + r"(?:[）)/\s]|$)", text):
            return unit
    return None


def inherit_price_items(policy, loader):
    if not policy.get("inherit_equipment_price_items"):
        return
    items = loader.load_yaml("table_field_extractors.yaml").get("x_investment_equipment_items") or []
    overrides = policy.setdefault("field_overrides", {})
    for item in items:
        code = item.get("field_code")
        if not code or code in overrides or not item.get("aliases"):
            continue
        # Existing second-stage aliases are reused. Compound requirements and
        # alternative labels stay advisory; they never trigger overwrites.
        overrides[code] = {"labels": item["aliases"], "role": "unit_price", "unit": "万元",
                           "row_excludes": item.get("exclude_aliases") or [],
                           "trusted": not item.get("all_aliases") and len(item["aliases"]) == 1}


def field_candidates(code, spec, row_index, policy):
    rule = policy.get("field_overrides", {}).get(code, {})
    labels = rule.get("labels") or [spec.get("name"), *(spec.get("aliases") or [])]
    role = field_role(spec, rule, policy)
    allowed = rule.get("value_headers") or (policy.get("column_roles") or {}).get(role) or spec.get("value_headers") or policy["value_headers"]
    exclusions = rule.get("scope_exclude_patterns", policy["scope_exclude_patterns"])
    target_unit = rule.get("unit") or spec.get("standard_unit") or spec.get("unit")
    candidates = []
    seen = set()
    for alias in dict.fromkeys(label(x) for x in labels if x):
        for table, row_number, row, unit, row_label in row_index.get(alias, []):
            for col, heading in enumerate(table["columns"]):
                if not header_role(heading, allowed) or not row[col] or not row[col]["isAnchor"]:
                    continue
                if role in {"unit_price", "total_amount"} and any(re.search(p, heading) for p in policy.get("amount_column_exclude_patterns", [])):
                    continue
                if any(x in _scope_text(table, row) for x in rule.get("row_excludes", [])):
                    continue
                raw = cell_text(row[col])
                if not present(raw):
                    continue
                source = {**row[col]["source"], "tableName": table["caption"], "sectionPath": table["sectionPath"],
                          "rowLabel": row_label, "columnName": heading, "rawValue": raw}
                physical = source_key(source)
                identity = physical or (table["id"], row_number, col)
                if identity in seen:
                    continue
                seen.add(identity)
                actual_unit = amount_unit(heading, policy) if role in {"unit_price", "total_amount"} else unit
                value = converted(raw, actual_unit, target_unit, policy)
                if role == "specification" and number(raw) is None and not target_unit:
                    value = raw
                if any(re.search(p, _scope_text(table, row)) for p in exclusions):
                    status = "scope_mismatch"
                elif value is not None:
                    status = "eligible" if rule.get("trusted") is True else "needs_scope_confirmation"
                elif target_unit or spec.get("value_type") == "number" or number(raw) is not None:
                    status = "unit_or_type_mismatch"
                else:
                    status = "needs_scope_confirmation"
                candidates.append({"stage": "cross_validation", "value": str(value) if value is not None else raw,
                                   "rawValue": raw, "unit": target_unit, "sourceUnit": actual_unit, "columnRole": role,
                                   "method": "exact_label_and_column", "status": status, "source": source})
    return candidates


def audit_fields(fields, specifications, rows, primary, final_detail, mapped, codes, registry, policy, available):
    output = []
    for code, spec in sorted(specifications.items()):
        current = fields.get(code, {})
        name = spec.get("name") or current.get("fieldName") or current.get("name") or code
        spec = {**spec, "name": name}
        value = current.get("value")
        key = codes.get(code)
        placeholder = key if str(key).startswith("${") else "${" + str(key) + "}"
        mapping_value = mapped.get(placeholder) if key else None
        candidates = field_candidates(code, spec, rows, policy)
        for candidate in candidates:
            registry.add("field", code, candidate)
        eligible = [c for c in candidates if c["status"] == "eligible"]
        prior = (primary.get("fieldIndex") or {}).get(code) or {}
        selected = _selected_sources(current, (final_detail.get("fieldIndex") or {}).get(code))
        exact_sources = {source_key(s) for s in selected} - {None}
        if not available:
            status = "budget_tables_unavailable"
        elif not candidates:
            status = "not_found"
        elif not eligible:
            status = "scope_or_unit_unverified"
        elif len(eligible) > 1:
            status = "ambiguous"  # never add or average rows without explicit aggregation rules
        elif source_key(eligible[0]["source"]) in exact_sources:
            status = "same_source"
        elif not present(value):
            status = "missing_candidate"  # suggestion only, never auto-fill
        elif not exact_sources and not any(s.get("blockId") and s.get("sourceType") != "table_cell" for s in selected):
            status = "source_independence_unknown"
        elif number(value) is None:
            status = "scope_or_unit_unverified"
        elif close(value, eligible[0]["value"], policy):
            status = "consistent"
        else:
            status = "conflict"
        mapped_status = None
        if key and len(eligible) == 1 and status in {"consistent", "conflict"} and number(mapping_value) is not None:
            mapped_status = "consistent" if close(mapping_value, eligible[0]["value"], policy) else "conflict"
        output.append({"fieldCode": code, "fieldName": name, "primaryValue": prior.get("value"),
                       "finalValue": value, "mappedValue": mapping_value, "unit": spec.get("standard_unit") or spec.get("unit"),
                       "mappingChanged": bool(key and token(mapping_value) != token(value)), "mappedComparison": mapped_status,
                       "status": status, "candidates": candidates})
    return output


def audit_tables(result, budget):
    """Exact caption and header-aligned row comparison; ambiguous rows are not matched."""
    index = defaultdict(list)
    for view in budget:
        index[label(view["caption"])].append(view)
    reports = []
    for section in result.get("sections") or []:
        for table in section.get("tables") or []:
            candidates = index.get(label(table.get("name")), []) if table.get("name") else []
            report = {"tableCode": table.get("key"), "name": table.get("name"), "status": "not_found", "rows": []}
            if len(candidates) > 1:
                report["status"] = "ambiguous"
            elif len(candidates) == 1:
                view = candidates[0]
                report["sourceTableIds"] = view["physicalTableIds"]
                if [label(c) for c in table.get("columns") or []] != [label(c) for c in view["columns"]]:
                    report["status"] = "header_mismatch"
                else:
                    by_key = defaultdict(list)
                    for i, row in enumerate(view["rows"]):
                        if i not in view["headerRows"] and row and label(cell_text(row[0])):
                            by_key[label(cell_text(row[0]))].append(row)
                    for row in table.get("data") or []:
                        if not isinstance(row, list) or not row:
                            continue
                        matches = by_key.get(label(row[0]), [])
                        state = "not_found" if not matches else "ambiguous" if len(matches) > 1 else (
                            "consistent" if [label(c) for c in row] == [label(cell_text(c)) for c in matches[0]]
                            else "different")
                        report["rows"].append({"rowKey": row[0], "status": state,
                                               "sources": [c["source"] for c in matches[0] if c] if len(matches) == 1 else []})
                    report["status"] = "rows_compared"
            reports.append(report)
    return reports


def build_audit(parse_result, primary_detail, secondary_detail, final_detail, config_root, registry=None):
    policy = load_policy(config_root)
    if not policy or not policy["enabled"]:
        return None
    loader = ConfigLoader(config_root)
    inherit_price_items(policy, loader)
    specs = loader.load_field_configs()
    schema = loader.load_required_yaml("output_schema.yaml")
    for code, meta in (schema.get("fields") or {}).items():
        specs[code] = {**meta, **specs.get(code, {})}
    result = parse_result["result"]
    fields = {}
    for section in result.get("sections") or []:
        for field in section.get("fields") or []:
            code = field.get("fieldCode")
            if code:
                fields[code] = field
                specs.setdefault(code, {"name": field.get("fieldName") or field.get("name"), "unit": field.get("unit")})
    # Include all conditional secondary fields, including NIL, plus dynamic primary field codes.
    for source in (primary_detail.get("fieldIndex") or {}, final_detail.get("fieldIndex") or {}):
        for code, field in source.items():
            if isinstance(field, dict):
                specs.setdefault(code, {"name": field.get("name"), "unit": field.get("unit")})
    if registry is None:
        registry = CandidateRegistry.from_details(primary_detail, secondary_detail)
    for (kind, code), observations in registry.groups.items():
        if kind == "field":
            first = observations[0]
            specs.setdefault(code, {"name": code, "unit": first.get("unit")})
    recovered = parse_result.get("_recovered_tables") or []
    budget = list(source_tables(recovered, policy))
    usable_budget = [table for table in budget if table["rows"]]
    rows = index_rows(usable_budget, policy)
    fields_report = audit_fields(fields, specs, rows, primary_detail, final_detail,
                                 parse_result.get("mapped") or {}, schema.get("output_field_codes") or {},
                                 registry, policy, bool(usable_budget))
    table_report = audit_tables(result, usable_budget)
    return {"version": 1, "mode": "audit", "summary": {
        "fieldCount": len(fields_report), "budgetTableCount": len(budget),
        "unavailableBudgetTableCount": len(budget) - len(usable_budget),
        "tableCount": len(table_report), "fieldStatuses": dict(Counter(f["status"] for f in fields_report)),
        "tableStatuses": dict(Counter(t["status"] for t in table_report)),
    }, "fields": fields_report, "tables": table_report, "candidateRegistry": registry.report()}
