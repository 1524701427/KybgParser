"""根据配置从已保留的报告表格中二次取值。"""

from word_parser.secondary.table_values.resolver import TableValueResolver, default_table_value_details_path, enhance_result_file
from word_parser.secondary.table_values.results import compact_table_value_result, final_result_with_table_values, table_value_details

__all__ = ["TableValueResolver", "compact_table_value_result", "default_table_value_details_path", "enhance_result_file", "final_result_with_table_values", "table_value_details"]
