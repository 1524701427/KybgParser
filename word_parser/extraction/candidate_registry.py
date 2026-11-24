"""Shared candidate registry for the full workflow; legacy selection stays intact."""
from collections import defaultdict
from copy import deepcopy
import json

from word_parser.extraction.candidate_facts import collect_candidate_facts


def token(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def source_key(source):
    """Deduplicate only when exact physical coordinates are available."""
    table = source.get("tableId")
    row = source.get("row", source.get("rowIndex"))
    col = source.get("columnIndex", source.get("column"))
    if table and row is not None and isinstance(col, int):
        return (str(table), row, col)
    return None


class CandidateRegistry:
    def __init__(self):
        self.groups = defaultdict(list)

    @classmethod
    def from_details(cls, primary, secondary):
        registry = cls()
        for fact in collect_candidate_facts(primary, secondary):
            registry.add(fact.kind, fact.code, {
                "stage": fact.stage, "value": fact.value, "rawValue": fact.raw_value,
                "unit": fact.unit, "method": fact.method, "status": fact.status,
                "score": fact.score, "confidence": fact.confidence, "source": fact.source,
            })
        return registry

    def add(self, kind, code, candidate):
        if code:
            self.groups[(kind, str(code))].append(deepcopy(candidate))

    def report(self):
        groups = []
        for (kind, code), items in sorted(self.groups.items()):
            sources = {}
            for item in items:
                key = source_key(item.get("source") or {})
                if key is None:
                    continue
                sources.setdefault(key, set()).add(item["stage"])
            groups.append({"kind": kind, "code": code, "observations": items,
                           "physicalSourceCount": len(sources),
                           "sharedPhysicalSourceCount": sum(len(stages) > 1 for stages in sources.values())})
        return {"version": 1, "selectionPolicy": "legacy_preserved",
                "summary": {"groupCount": len(groups), "observationCount": sum(len(g["observations"]) for g in groups)},
                "groups": groups}
