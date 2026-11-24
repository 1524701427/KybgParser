"""预抽取结构快照：只读索引，不修改原 AST 的文本、表格或章节选值。"""
from pathlib import Path


def build_structure_index(ast, policy):
    settings = policy["diagnostics"]
    if settings["mode"] == "off":
        return None
    include_text = settings["include_text"]
    diagnostics, sections, blocks, tables = [], [], [], []
    stack = []
    table_ids = set()
    block_ids = set()

    def issue(code, object_id, severity="warning"):
        diagnostics.append({"code": code, "objectId": object_id, "severity": severity})

    for table in ast.tables:
        if table.id in table_ids:
            issue("DUPLICATE_TABLE_ID", table.id, "error")
        table_ids.add(table.id)
        widths = [len(row) for row in table.rows]
        if not widths or not any(widths):
            issue("EMPTY_TABLE", table.id)
        if len(set(widths)) > 1:
            issue("RAGGED_TABLE_ROWS", table.id)
        if not table.section_path:
            issue("UNANCHORED_TABLE", table.id)
        if not table.caption:
            issue("MISSING_TABLE_CAPTION", table.id)
        entry = {
            "id": table.id, "order": table.order, "page": table.page,
            "caption": table.caption, "sectionPath": list(table.section_path),
            "canonicalSections": list(table.meta.get("canonical_sections") or []),
            "rowWidths": widths,
            "headerRows": [i for i, row in enumerate(table.rows) if any(cell.is_header for cell in row)],
            "captionCandidates": list(table.meta.get("title_candidates") or []),
            "bbox": table.meta.get("bounding_box") or table.meta.get("layout_bbox") or table.meta.get("bbox"),
            "mergeMarkers": [
                {"row": cell.row, "column": cell.col, "horizontal": cell.meta.get("horizontal_merge"),
                 "vertical": cell.meta.get("vertical_merge")}
                for row in table.rows for cell in row
                if cell.meta.get("horizontal_merge") not in (None, "NONE", "None", "0")
                or cell.meta.get("vertical_merge") not in (None, "NONE", "None", "0")
            ],
        }
        if include_text:
            entry["cells"] = [[cell.to_dict() for cell in row] for row in table.rows]
        tables.append(entry)

    last_order = None
    referenced = set()
    for block in ast.blocks:
        if block.id in block_ids:
            issue("DUPLICATE_BLOCK_ID", block.id, "error")
        block_ids.add(block.id)
        if last_order is not None and block.order < last_order:
            issue("BLOCK_ORDER_REVERSED", block.id, "error")
        last_order = block.order
        kind = block.meta.get("structure_type", block.type)
        if kind == "heading":
            level = block.meta.get("heading_level") or 1
            while stack and stack[-1]["level"] >= level:
                stack.pop()["endBeforeOrder"] = block.order
            if level > (stack[-1]["level"] if stack else 0) + 1:
                issue("HEADING_LEVEL_GAP", block.id)
            node = {"id": block.id, "title": block.text, "level": level,
                    "parentId": stack[-1]["id"] if stack else None, "startOrder": block.order,
                    "endBeforeOrder": None, "page": block.page,
                    "sectionPath": list(block.section_path)}
            sections.append(node)
            stack.append(node)
        table_id = block.meta.get("table_id")
        if block.type == "table":
            if table_id not in table_ids:
                issue("DANGLING_TABLE_REFERENCE", block.id, "error")
            else:
                referenced.add(table_id)
        record = {
            "id": block.id, "kind": kind, "order": block.order, "page": block.page,
            "sectionId": stack[-1]["id"] if stack else None,
            "sectionPath": list(block.section_path), "tableId": table_id,
            "style": block.style.to_dict() if block.style else None,
            "bbox": block.meta.get("bounding_box") or block.meta.get("bbox"),
        }
        if include_text:
            record["text"] = block.text
        blocks.append(record)
    for table_id in sorted(table_ids - referenced):
        issue("UNREFERENCED_TABLE", table_id)
    if not blocks and not tables:
        issue("EMPTY_DOCUMENT", None, "error")
    elif not sections:
        issue("NO_HEADINGS", None)
    status = "error" if any(d["severity"] == "error" for d in diagnostics) else "warning" if diagnostics else "ok"
    if settings["mode"] == "strict" and status == "error":
        raise ValueError("Document structure error: " + ", ".join(d["code"] for d in diagnostics if d["severity"] == "error"))
    return {
        "version": 1, "format": Path(ast.file_name).suffix.lower(), "status": status,
        "summary": {"blockCount": len(blocks), "sectionCount": len(sections), "physicalTableCount": len(tables),
                    "diagnosticCount": len(diagnostics)},
        "sections": sections, "blocks": blocks, "physicalTables": tables, "diagnostics": diagnostics,
    }
