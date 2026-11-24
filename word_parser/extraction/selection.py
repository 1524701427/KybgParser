"""Shared candidate resolution helpers."""
from collections import defaultdict

def has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return any(has_value(v) for v in (value.values() if isinstance(value, dict) else value))
    return True

def group_candidates(items, code):
    groups = defaultdict(list)
    for item in items:
        groups[code(item)].append(item)
    return groups

def select_candidate(items, score):
    return max(items, key=score) if items else None

def select_secondary(existing, candidate):
    if candidate.get("status") == "OK" and not has_value((existing or {}).get("value")):
        return candidate
    return existing
