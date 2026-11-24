"""Recover a provenance-preserving rectangular table view, without mutating AST.

Only explicit spans/merge markers create merged cells. Continuation is conservative:
same section, adjacent pages (or explicit continuation caption), compatible headers.
Each grid slot references an original anchor; it is not a new measurement.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy


def label(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).casefold()


def marker(value):
    value = str(value or "").casefold().split(".")[-1]
    if value in {"1", "first", "restart"}:
        return "start"
    if value in {"2", "previous", "continue"}:
        return "continue"
    return None


def _span(value):
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        return 1


def recover_grid(table, settings):
    """Expand explicit spans, preserve anchor coordinates and diagnose orphan merges."""
    grid = []
    diagnostics = []
    anchors = {}
    max_cols = settings["max_columns"]
    max_cells = settings["max_expanded_cells"]
    fragments = table.meta.get("source_fragments") or []

    def put(row, col, anchor):
        if col >= max_cols or row >= max_cells // max(1, max_cols):
            raise ValueError(f"table {table.id}: configured recovery bounds exceeded")
        while len(grid) <= row:
            grid.append([])
        while len(grid[row]) <= col:
            grid[row].append(None)
        existing = grid[row][col]
        if existing is not None and existing != anchor:
            diagnostics.append({"code": "OVERLAPPING_SPAN", "row": row, "column": col})
            return
        grid[row][col] = anchor

    def lookup(r, c):
        if r < 0 or c < 0 or r >= len(grid) or c >= len(grid[r]):
            return None
        return grid[r][c]

    for r, row in enumerate(table.rows):
        if r >= max_cells // max(1, max_cols):
            raise ValueError(f"table {table.id}: configured recovery bounds exceeded")
        if len(grid) <= r:
            grid.append([])
        c = 0
        previous = None
        for cell in row:
            h = marker(cell.meta.get("horizontal_merge"))
            v = marker(cell.meta.get("vertical_merge"))
            # XML physical cells have sequential col values; explicit grid spans
            # shift following physical cells. Native span placeholders are skipped.
            while lookup(r, c) is not None:
                c += 1
            span = max(_span(cell.col_span), _span(cell.meta.get("grid_span")))
            height = _span(cell.row_span)
            if h == "continue" and previous is not None:
                anchor = previous
            elif v == "continue" and lookup(r - 1, c) is not None:
                anchor = lookup(r - 1, c)
                if cell.text.strip() and cell.text.strip() != anchors[anchor]["text"].strip():
                    diagnostics.append({"code": "MERGE_CONTINUATION_TEXT_CONFLICT", "row": r, "column": c})
                    anchor = None
            else:
                anchor = None
            if anchor is None:
                if h == "continue" or v == "continue":
                    diagnostics.append({"code": "ORPHAN_MERGE", "row": r, "column": c})
                source_id = cell.meta.get("source_table_id", table.id)
                source_row = cell.meta.get("source_row", cell.row)
                source_page = cell.meta.get("source_page", table.page)
                source_col = cell.meta.get("source_col", cell.col)
                anchor = (r, c)
                anchors[anchor] = {
                    "text": cell.text, "row": r, "column": c,
                    "source": {"tableId": source_id, "page": source_page,
                               "row": source_row, "column": source_col},
                }
            for dr in range(height):
                for dc in range(span):
                    put(r + dr, c + dc, anchor)
            previous = anchor
            c += span
    width = max((len(row) for row in grid), default=0)
    if width * len(grid) > max_cells:
        raise ValueError(f"table {table.id}: configured recovery bounds exceeded")
    spans = {}
    for r, row in enumerate(grid):
        for c, anchor in enumerate(row):
            if anchor is not None:
                sr, sc = spans.get(anchor, (0, 0))
                spans[anchor] = (max(sr, r - anchor[0] + 1), max(sc, c - anchor[1] + 1))
    rows = []
    for r, row in enumerate(grid):
        line = []
        for c in range(width):
            anchor = row[c] if c < len(row) else None
            if anchor is None:
                line.append(None)
                continue
            record = anchors[anchor]
            height, span = spans[anchor]
            line.append({**record, "rowSpan": height, "colSpan": span,
                         "isAnchor": anchor == (r, c)})
        rows.append(line)
    declared = [r for r, row in enumerate(table.rows) if any(cell.meta.get("declared_header") is True for cell in row)]
    header_rows = []
    for r in declared:
        if r != len(header_rows):
            break
        header_rows.append(r)
    if not header_rows and table.rows and any(cell.is_header for cell in table.rows[0]):
        header_rows = [0]
    # Include rows covered by explicit header rowspans, without guessing data rows.
    for r in list(header_rows):
        for cell in rows[r]:
            if cell and cell["isAnchor"]:
                header_rows = list(range(min(len(rows), max(len(header_rows), r + cell["rowSpan"]))))
    columns = []
    for c in range(width):
        parts = []
        for r in header_rows:
            cell = rows[r][c]
            text = str(cell["text"]).strip() if cell else ""
            if text and (not parts or parts[-1] != text):
                parts.append(text)
        columns.append(" / ".join(parts))
    return {"id": table.id, "order": table.order, "page": table.page,
            "lastPage": max((f.get("page") for f in fragments if f.get("page") is not None), default=table.page),
            "caption": table.caption, "sectionPath": list(table.section_path),
            "canonicalSections": list(table.meta.get("canonical_sections") or []),
            "physicalTableIds": [f["tableId"] for f in fragments] or [table.id],
            "headerRows": header_rows, "columns": columns, "rows": rows,
            "diagnostics": diagnostics, "continuations": []}


def _caption(text, rule):
    return label(re.sub(rule["continuation_pattern"], "", str(text or "").strip()))


def _compatible(previous, current, rule, blocks):
    if not previous["rows"] or not current["rows"] or len(previous["columns"]) != len(current["columns"]):
        return False
    if not previous["sectionPath"] or previous["sectionPath"] != current["sectionPath"]:
        return False
    gap = current["order"] - previous.get("lastOrder", previous["order"])
    if gap <= 0 or gap > rule["max_order_gap"]:
        return False
    if any(previous.get("lastOrder", previous["order"]) < b.order < current["order"]
           and b.meta.get("structure_type") == "heading" for b in blocks):
        return False
    a, b = previous["lastPage"], current["page"]
    explicit = bool(re.search(rule["continuation_pattern"], str(current["caption"] or "")))
    if a is not None and b is not None:
        if not 0 < b - a <= rule["max_page_gap"]:
            return False
    elif not explicit:
        return False
    left, right = _caption(previous["caption"], rule), _caption(current["caption"], rule)
    if right and left and right != left and not (explicit and right in {"表", ""}):
        return False
    if not explicit and (not left or not right or left != right):
        return False
    headers = [label(c) for c in previous["columns"]]
    incoming = [label(c) for c in current["columns"]]
    equal = sum(bool(x) and x == y for x, y in zip(headers, incoming))
    known = {label(x) for x in rule["header_labels"]}
    recognized = sum(any(label(part) in known for part in col.split(" / ")) for col in previous["columns"])
    # A continuation with no repeated header may be joined only with explicit
    # caption and no declared header, rather than interpreting a data row as header.
    if equal >= rule["min_header_matches"] and recognized >= rule["min_header_matches"] and headers == incoming:
        return True
    return False


def recover_tables(ast, settings):
    if not settings.get("enabled", False):
        return []
    rule = settings["continuation"]
    result = []
    for table in sorted(ast.tables, key=lambda t: t.order):
        view = recover_grid(table, settings)
        if result and rule["enabled"] and _compatible(result[-1], view, rule, ast.blocks):
            previous = result[-1]
            skip = len(view["headerRows"])
            start = len(previous["rows"])
            previous["continuations"].append({"tableId": view["id"], "page": view["page"],
                                              "repeatedHeaderRows": skip, "rowStart": start})
            previous["physicalTableIds"].extend(view["physicalTableIds"])
            previous["rows"].extend(view["rows"][skip:])
            previous["diagnostics"].extend(view["diagnostics"])
            previous["lastPage"] = view["lastPage"]
            previous["lastOrder"] = view["order"]
        else:
            result.append(view)
    return result
