"""Map logical cell coordinates back to original physical cells."""
def physical_cell_source(table, row, column):
    if table is None or not isinstance(row, int) or not isinstance(column, int):
        return None
    if row < 0 or column < 0 or row >= len(table.rows):
        return None
    cells = table.rows[row]
    if not table.meta.get("recovered_view"):
        return None
    if column >= len(cells):
        return None
    return cells[column].meta.get("physical_source")


def attach_candidate_provenance(ast, extractions):
    for item in extractions:
        if not item.evidence.table_id:
            continue
        table = ast.get_table(item.evidence.table_id)
        source = physical_cell_source(table, item.debug.get("row_index"), item.debug.get("column_index"))
        if source:
            item.evidence.meta["physicalSource"] = dict(source)
