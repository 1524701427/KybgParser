"""Compatibility imports for secondary extraction; implementation is in word_parser."""

import sys

from word_parser.extraction.table_values.constants import (
    _NIL_STATUS,
)
from word_parser.extraction.table_values.models import (
    NormalizedTable,
)
from word_parser.extraction.table_values.primitives import (
    apply_value_conversion,
    clean_text,
    column_match_score,
    extract_value_by_pattern,
    first_alias,
    is_placeholder_text,
    json_safe,
    normalize_label,
    normalize_number,
    normalize_value,
    numeric_label_match_score,
    parse_metric_number,
    parse_number,
    row_match_score,
    safe_search,
    validate_cell_value,
    value_at,
)
from word_parser.extraction.table_values.results import (
    derived_table_result,
    field_result,
    filter_included_value,
    nil_field,
    nil_table,
    simplify_trace,
    table_summaries,
)
from word_parser.extraction.table_values.selectors import (
    column_indices_for_selector,
    infer_merged_year_columns,
    normalize_table,
    row_has_year_headers,
    row_looks_like_header,
    select_column,
    select_row,
    select_row_occurrence,
)
from word_parser.extraction.table_values.context import (
    ResultContext,
)
from word_parser.extraction.table_values.presentation import (
    _SECONDARY_NO_OVERWRITE_WHEN_PRESENT,
    _compact_derived_table,
    _compact_table_field,
    _has_present_value,
    _merge_section_fields,
    _merge_section_tables,
    compact_table_value_result,
    final_result_with_table_values,
    table_value_details,
)
from word_parser.extraction.table_values.files import (
    _base_result_stem,
    default_table_value_details_path,
    enhance_result_file,
    write_table_value_details,
)
from word_parser.extraction.table_values.resolver import (
    TableValueResolver,
)

__all__ = ["TableValueResolver", "compact_table_value_result", "default_table_value_details_path", "enhance_result_file", "final_result_with_table_values", "table_value_details"]

# Preserve the historical package import without creating a second implementation.
__path__ = []
sys.modules.setdefault(f"{__name__}.resolver", sys.modules[__name__])
