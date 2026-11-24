"""Project safely recovered tables into the shared AST before extraction."""
from copy import deepcopy
from word_parser.document.ast.document import DocumentTable, TableCell


def _project(view, original):
    headers = set(view["headerRows"])
    rows = []
    for r, row in enumerate(view["rows"]):
        line = []
        for c, item in enumerate(row):
            if not item:
                line.append(TableCell("", r, c, is_header=r in headers))
                continue
            # Do not duplicate a merged measurement in data rows.
            text = item["text"] if item["isAnchor"] or r in headers else ""
            line.append(TableCell(text, r, c, is_header=r in headers, meta={
                "physical_source": dict(item["source"]), "merge_anchor": item["isAnchor"],
                "logical_row_span": item["rowSpan"], "logical_col_span": item["colSpan"],
            }))
        rows.append(line)
    meta = deepcopy(original.meta)
    meta["recovered_view"] = True
    meta["physical_table_ids"] = list(view["physicalTableIds"])
    meta["recovered_columns"] = list(view["columns"])
    meta.pop("source_fragments", None)
    return DocumentTable(original.id, original.order, original.page, original.caption,
                         list(original.section_path), rows, meta)


def apply_recovered_tables(ast, views, mode="safe"):
    if mode != "safe":
        return {"mode": mode, "replaced": [], "fallback": []}
    originals = {table.id: table for table in ast.tables}
    replacements, removed, fallback = {}, set(), []
    for view in views:
        original = originals.get(view["id"])
        if original is None:
            continue
        if view["diagnostics"] or not view["rows"]:
            fallback.append({"tableId": original.id, "reason": "recovery_diagnostics"})
            continue
        changed = bool(view["continuations"]) or any(
            cell and (cell["rowSpan"] > 1 or cell["colSpan"] > 1)
            for row in view["rows"] for cell in row
        )
        if not changed:
            continue
        # Older positional extractors cannot safely interpret merged data
        # across multiple columns; retain the original in that case.
        if any(cell and not cell["isAnchor"] and r not in view["headerRows"]
               and cell["colSpan"] > 1 for r, row in enumerate(view["rows"]) for cell in row):
            fallback.append({"tableId": original.id, "reason": "ambiguous_data_colspan"})
            continue
        replacements[original.id] = _project(view, original)
        removed.update(tid for tid in view["physicalTableIds"] if tid in originals and tid != original.id)
    ast.tables = [replacements.get(t.id, t) for t in ast.tables if t.id not in removed]
    blocks = []
    for block in ast.blocks:
        tid = block.meta.get("table_id")
        if tid in removed:
            continue
        if tid in replacements:
            block.text = "\n".join(" | ".join(c.text for c in row) for row in replacements[tid].rows)
            block.meta["recovered_view"] = True
        blocks.append(block)
    ast.blocks = blocks
    return {"mode": mode, "replaced": list(replacements), "fallback": fallback}
