"""Secondary extraction: cells. Existing rule semantics are preserved."""

from __future__ import annotations

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.models import NormalizedTable

from word_parser.extraction.table_values.primitives import apply_value_conversion, clean_text, extract_value_by_pattern, first_alias, normalize_label, normalize_number, normalize_value, parse_metric_number, parse_number, row_match_score, safe_search, validate_cell_value, value_at

from word_parser.extraction.table_values.results import field_result, nil_field


class CellOperationsMixin:
    def _extract_cell_items(self, context: "ResultContext", rule: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract many fields from one DataFrame scan.

        The source table, label columns and value column are resolved once. Each
        row is then classified against the configured item aliases, avoiding one
        full DataFrame scan per output field.
        """
        item_rules = self._cell_item_rules(rule)
        if not item_rules:
            return []
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return [nil_field(item_rule, table_result["reason"], table_result.get("message"), table_result) for item_rule in item_rules]

        table = table_result["table"]
        frame = self._table_frame(table)
        column_spec = rule.get("column") or {}
        column_result = self._select_column_frame(frame, column_spec)
        if column_result.get("status") == _NIL_STATUS:
            trace = {**table_result, **column_result}
            return [nil_field(item_rule, column_result["reason"], column_result.get("message"), trace) for item_rule in item_rules]
        column_result = self._apply_projection_column_offset(frame, column_result, column_spec)

        row_spec = rule.get("row") or {}
        match_column_indices = self._frame_column_indices(frame, row_spec.get("column") or row_spec.get("column_aliases"))
        items = [item for item in rule.get("items") or [] if isinstance(item, dict) and item.get("field_code")]
        candidates: dict[str, list[dict[str, Any]]] = {str(item["field_code"]): [] for item in items}
        for row_index, row in frame.iterrows():
            row_values = row.tolist()
            search_text = self._filter_projection_search_text(
                row_values,
                match_column_indices or list(range(len(frame.columns))),
            )
            if not search_text:
                continue
            match = self._best_filter_projection_item(search_text, items)
            if match is None:
                continue
            item = items[int(match["order"])]
            candidates[str(item["field_code"])].append(
                {
                    "rowIndex": int(row_index),
                    "row": row_values,
                    "score": match["score"],
                    "text": search_text,
                    "selector": "cell_items_label",
                }
            )

        results: list[dict[str, Any]] = []
        for item_rule in item_rules:
            field_code = str(item_rule.get("field_code"))
            matches = sorted(candidates.get(field_code) or [], key=lambda item: item["score"], reverse=True)
            if not matches:
                results.append(nil_field(item_rule, "row_not_found", "未找到匹配行。", {**table_result, "matchColumns": match_column_indices}))
                continue
            if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not row_spec.get("allow_ambiguous"):
                results.append(nil_field(item_rule, "ambiguous_row", "行选择命中多个同分候选。", {**table_result, "candidates": matches[:5]}))
                continue
            row_result = matches[0]
            value = self._frame_value(frame, row_result["rowIndex"], column_result["columnIndex"])
            value = extract_value_by_pattern(value, item_rule)
            value_status = validate_cell_value(value, str(item_rule.get("value_type") or "auto"))
            if value_status.get("status") == _NIL_STATUS:
                results.append(nil_field(item_rule, value_status["reason"], value_status.get("message"), {**table_result, **row_result, **column_result}))
                continue
            results.append(field_result(item_rule, value, table, row_result, column_result))
        return results

    def _extract_cell(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """按行标签和列名抽取来源表单元格。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        row_result = self._select_row_for_rule(table, rule)
        if row_result.get("status") == _NIL_STATUS:
            return nil_field(rule, row_result["reason"], row_result.get("message"), {**table_result, **row_result})
        column_spec = rule.get("column") or {}
        if str(column_spec.get("type") or "label") == "row_number":
            return self._extract_row_number_cell(context, rule, table, table_result, row_result, column_spec)
        column_result = self._select_column_frame(frame, column_spec)
        if column_result.get("status") == _NIL_STATUS:
            fallback_column = self._fallback_value_column_for_labeled_row(table, row_result, column_spec)
            if fallback_column is None:
                return nil_field(rule, column_result["reason"], column_result.get("message"), {**table_result, **row_result, **column_result})
            column_result = fallback_column
        column_result = self._apply_projection_column_offset(frame, column_result, column_spec)
        value = self._merged_cell_value(frame, row_result, column_result, rule) if rule.get("merge_following_rows") else self._frame_value(frame, row_result["rowIndex"], column_result["columnIndex"])
        value = extract_value_by_pattern(value, rule)
        value_status = validate_cell_value(value, str(rule.get("value_type") or "auto"))
        if value_status.get("status") == _NIL_STATUS:
            return nil_field(rule, value_status["reason"], value_status.get("message"), {**table_result, **row_result, **column_result})
        return field_result(rule, value, table, row_result, column_result)

    def _extract_row_number_cell(self, context: "ResultContext", rule: dict[str, Any], table: NormalizedTable, table_result: dict[str, Any], row_result: dict[str, Any], column_spec: dict[str, Any]) -> dict[str, Any]:
        """从已选中的行文本里直接解析数值。

        用于“取最后一行”这类把值写在行标签里的表格（如风切变表的“综合风切变 0.258”）。
        优先在标签之后的单元格里找数字，找不到时退回整行第一个数字。
        """
        row = row_result.get("row") or []
        aliases = [str(alias) for alias in column_spec.get("aliases") or column_spec.get("patterns") or []]
        cells = [clean_text(cell) for cell in row]
        found_index = 0
        found_cell = None
        number = None
        if aliases:
            for index, cell in enumerate(cells):
                if any(alias and alias in cell for alias in aliases):
                    found_index = index
                    found_cell = cell
                    number = parse_number(cell)
                    if number is None:
                        for next_index in range(index + 1, len(cells)):
                            number = parse_number(cells[next_index])
                            if number is not None:
                                found_index = next_index
                                found_cell = cells[next_index]
                                break
                    break
        if number is None:
            for index, cell in enumerate(cells):
                number = parse_number(cell)
                if number is not None:
                    found_index = index
                    found_cell = cell
                    break
        value_status = validate_cell_value(number if number is not None else None, str(rule.get("value_type") or "auto"))
        if value_status.get("status") == _NIL_STATUS:
            return nil_field(rule, value_status["reason"], value_status.get("message"), {**table_result, **row_result, "rowCells": cells})
        column_result = {"columnIndex": found_index, "column": f"row_number:{found_index}", "score": 0, "selector": "row_number"}
        return field_result(rule, number, table, row_result, column_result)

    def _select_row_for_rule(self, table: NormalizedTable, rule: dict[str, Any]) -> dict[str, Any]:
        """为规则选择目标行。"""
        frame = self._table_frame(table)
        row_spec = rule.get("row") or {}
        if row_spec.get("match"):
            return self._select_compound_row_frame(frame, row_spec)
        if str(row_spec.get("type") or "label") in {"last", "first"}:
            return self._select_edge_row_frame(frame, row_spec)
        if "occurrence" in row_spec:
            return self._select_row_occurrence_frame(frame, row_spec, int(row_spec.get("occurrence") or 0))
        occurrence = self._repeated_row_occurrence_for_source(rule.get("source_table") or {})
        if occurrence is None:
            return self._select_row_frame(frame, row_spec)
        return self._select_row_occurrence_frame(frame, row_spec, occurrence)

    def _select_edge_row_frame(self, frame: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """选择首行或末行，用于“取最后一行”这类无行标签的规则。"""
        skip = self._row_indices_to_skip_for_edge(frame)
        candidates = [index for index in frame.index if index not in skip]
        if not candidates:
            return {"status": _NIL_STATUS, "reason": "row_not_found", "message": "没有可用于选择的表格行。"}
        if str(spec.get("type")) == "last":
            row_index = candidates[-1]
        else:
            row_index = candidates[0]
        return {"rowIndex": row_index, "row": self._frame_row(frame, row_index), "selector": "edge_row"}

    def _row_indices_to_skip_for_edge(self, frame: Any) -> set[int]:
        """跳过空行，让首/末行指向真正的数据行。"""
        skip: set[int] = set()
        for row_index, row in frame.iterrows():
            text = clean_text(" ".join(str(cell or "") for cell in row.tolist()))
            if not text:
                skip.add(row_index)
        return skip

    def _select_compound_row_frame(self, frame: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """按多列联合条件选行。

        韩家沟“平均风速、风功率密度统计表”里，塔号在第一列、风速/风功率在第二列，
        单列匹配无法唯一定位到“某塔的某指标”行，需要 ``match`` 声明多个列条件同时命中。
        """
        conditions = list(spec.get("match") or [])
        matches: list[dict[str, Any]] = []
        for row_index, row in frame.iterrows():
            ok = True
            for condition in conditions:
                column_spec = condition if isinstance(condition, dict) else {"aliases": [condition]}
                column_indices = self._frame_column_indices(frame, column_spec.get("column") or column_spec.get("column_aliases"))
                patterns = [str(pattern) for pattern in column_spec.get("patterns") or column_spec.get("aliases") or []]
                cells = row.iloc[column_indices].tolist() if column_indices else row.tolist()
                text = clean_text(" ".join(str(cell or "") for cell in cells))
                if not text and column_indices:
                    text = self._filled_down_condition_text(frame, row_index, column_indices)
                if not patterns or row_match_score(text, patterns) <= 0:
                    ok = False
                    break
            if ok:
                matches.append({"rowIndex": row_index, "row": row.tolist(), "score": 100, "text": clean_text(" ".join(str(c or "") for c in row.tolist()))})
        if not matches:
            return {"status": _NIL_STATUS, "reason": "row_not_found", "message": "未找到满足联合条件的行。"}
        matches.sort(key=lambda item: item["rowIndex"])
        if len(matches) > 1 and not spec.get("allow_ambiguous"):
            return {"status": _NIL_STATUS, "reason": "ambiguous_row", "message": "联合条件命中多行。", "candidates": matches[:5]}
        return {**matches[0], "selector": "compound_label"}

    def _filled_down_condition_text(self, frame: Any, row_index: int, column_indices: list[int]) -> str:
        """Use the nearest non-empty value above when a grouped row leaves the label cell blank."""
        values: list[str] = []
        for column_index in column_indices:
            for previous_index in range(row_index - 1, -1, -1):
                value = clean_text(str(frame.iloc[previous_index, column_index] or ""))
                if value:
                    values.append(value)
                    break
        return clean_text(" ".join(values))

    def _repeated_row_occurrence_for_source(self, source_table: dict[str, Any]) -> int | None:
        """从来源表约束里推断重复目标行的序号。

        目前只对风速切变指数连续表启用：2.5-17、2.5-18、2.5-19 分别对应
        合并表中第 1、2、3 个“综合值”行。没有表号或不是风切变表时不介入。
        """
        if not self._source_is_wind_shear(source_table):
            return None
        table_number = self._source_table_number(source_table)
        if table_number is None:
            return None
        suffix = table_number.split("-")[-1]
        if not suffix.isdigit():
            return None
        suffix_number = int(suffix)
        if 17 <= suffix_number <= 19:
            return suffix_number - 17
        return None

    def _fallback_value_column_for_labeled_row(self, table: NormalizedTable, row_result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
        """行已定位但列名缺失时，从标签行右侧寻找第一个有效值列。

        风切变综合值表常把“综合值”写在第一列，实际数值写在第二列，表头却是高度段
        ``80/70/50...``，因此配置中的“风切变/综合值”列名不会命中。这个兜底只在
        行标签明显命中且右侧存在可解析数值时生效，避免随意取其它列。
        """
        row = row_result.get("row") or []
        row_text = clean_text(" ".join(str(cell or "") for cell in row))
        aliases = [str(alias) for alias in spec.get("aliases") or spec.get("patterns") or []]
        if not aliases or not any(alias and alias in row_text for alias in aliases):
            return None
        for index in range(1, len(row)):
            value = value_at(row, index)
            if clean_text(value) and parse_number(value) is not None:
                column_name = table.columns[index] if index < len(table.columns) else f"col_{index}"
                return {"columnIndex": index, "column": column_name, "score": 0, "selector": "fallback_first_numeric_after_label"}
        return None

    def _extract_max_row_label(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """抽取数值列最大值所在行的标签值。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        value_column = self._grouped_value_column_for_max_row_label(table, rule.get("value_column") or {})
        if value_column is None:
            value_column = self._select_column_frame(frame, rule.get("value_column") or {})
        if value_column.get("status") == _NIL_STATUS:
            return nil_field(rule, value_column["reason"], value_column.get("message"), {**table_result, **value_column})
        label_column = self._select_column_frame(frame, rule.get("label_column") or {})
        if label_column.get("status") == _NIL_STATUS:
            label_column = self._fallback_label_column_for_max_row_label(table)
            if label_column is None:
                return nil_field(rule, "column_not_found", "未找到标签列。", {**table_result, **value_column})
        skip_rows = self._rows_to_skip_for_max_row_label(table, value_column, label_column)
        best_row: tuple[int, float] | None = None
        for row_index, row in frame.iterrows():
            if row_index in skip_rows:
                continue
            if self._requires_wind_direction_label(rule, table):
                label_text = clean_text(row.iloc[label_column["columnIndex"]])
                if not self._looks_like_wind_direction_label(label_text):
                    continue
            number = parse_metric_number(row.iloc[value_column["columnIndex"]])
            if number is None:
                continue
            if best_row is None or number > best_row[1]:
                best_row = (row_index, number)
        if best_row is None:
            return nil_field(rule, "value_parse_failed", "没有可用于比较的数值行。", {**table_result, **value_column})
        row_index, max_value = best_row
        value = self._frame_value(frame, row_index, label_column["columnIndex"])
        row_result = {"rowIndex": row_index, "row": self._frame_row(frame, row_index), "selector": "max_row"}
        result = field_result(rule, value, table, row_result, label_column)
        result["maxValue"] = max_value
        result["maxValueColumn"] = value_column.get("column")
        return result

    def _grouped_value_column_for_max_row_label(self, table: NormalizedTable, spec: dict[str, Any]) -> dict[str, Any] | None:
        """\u6309\u5854\u53f7\u5206\u7ec4\u8868\u5934\u5b9a\u4f4d\u98ce\u5411/\u98ce\u80fd\u9891\u7387\u5217\u3002

        \u98ce\u5411\u98ce\u80fd\u9891\u7387\u8868\u5e38\u7528\u7b2c\u4e00\u5c42\u8868\u5934\u653e\u6d4b\u98ce\u5854\u53f7\uff0c\u7b2c\u4e8c\u5c42\u8868\u5934\u653e\u201c\u98ce\u5411\u9891\u7387/\u98ce\u80fd\u9891\u7387\u201d\u3002
        \u666e\u901a\u5217\u5339\u914d\u53ea\u80fd\u547d\u4e2d\u5854\u53f7\u6240\u5728\u5217\uff0c\u8fd9\u91cc\u6839\u636e\u5206\u7ec4\u8de8\u5ea6\u4fee\u6b63\u5230\u5bf9\u5e94\u7684\u6307\u6807\u5217\u3002
        """
        if not table.columns or not table.data:
            return None
        aliases = [str(alias) for alias in spec.get("aliases") or spec.get("patterns") or []]
        alias_text = " ".join(aliases)
        tower_match = re.search(r"[A-Za-z0-9]{2,8}#", alias_text.replace("\uff03", "#"))
        if not tower_match:
            return None
        tower_code = tower_match.group(0)
        tower_codes = []
        for column in table.columns:
            for match in re.finditer(r"[A-Za-z0-9]{2,8}#", clean_text(column).replace("\uff03", "#")):
                if match.group(0) not in tower_codes:
                    tower_codes.append(match.group(0))
        if tower_code not in tower_codes or len(tower_codes) < 2:
            return None
        metric_header = self._grouped_metric_header_row(table)
        if metric_header is None:
            return None
        metric_columns = [index for index in range(1, max(len(metric_header), len(table.columns))) if clean_text(value_at(metric_header, index))]
        if len(metric_columns) < len(tower_codes):
            return None
        span = max(1, len(metric_columns) // len(tower_codes))
        position = tower_codes.index(tower_code)
        group_columns = metric_columns[position * span : position * span + span]
        if not group_columns:
            return None
        metric_aliases = self._metric_aliases_for_grouped_value_column(aliases)
        selected = None
        for alias in metric_aliases:
            selected = next((index for index in group_columns if alias in clean_text(value_at(metric_header, index))), None)
            if selected is not None:
                break
        if selected is None:
            selected = group_columns[-1] if span > 1 else group_columns[0]
        return {"columnIndex": selected, "column": f"{tower_code}{clean_text(value_at(metric_header, selected))}", "score": 110, "selector": "grouped_header"}

    def _grouped_metric_header_row(self, table: NormalizedTable) -> list[Any] | None:
        """\u5728\u524d\u51e0\u884c\u4e2d\u5bfb\u627e\u98ce\u5411/\u98ce\u80fd\u9891\u7387\u5206\u7ec4\u8868\u5934\u884c\u3002"""
        for row in table.data[:3]:
            row_text = clean_text(" ".join(str(cell or "") for cell in row))
            if "\u98ce\u5411" in row_text and ("\u98ce\u80fd\u9891\u7387" in row_text or "\u98ce\u5411\u9891\u7387" in row_text):
                return row
        return None

    def _metric_aliases_for_grouped_value_column(self, aliases: list[str]) -> list[str]:
        """\u6839\u636e\u5217\u522b\u540d\u63a8\u65ad\u5206\u7ec4\u8868\u5934\u91cc\u5e94\u8be5\u9009\u54ea\u4e2a\u6307\u6807\u5217\u3002"""
        joined = " ".join(aliases)
        if "\u98ce\u5411\u9891\u7387" in joined:
            return ["\u98ce\u5411\u9891\u7387", "\u98ce\u80fd\u9891\u7387"]
        return ["\u98ce\u80fd\u9891\u7387", "\u98ce\u5411\u9891\u7387"]

    def _fallback_label_column_for_max_row_label(self, table: NormalizedTable) -> dict[str, Any] | None:
        """在表头未显式命中时，回退到第一列作为标签列。

        这类表常把第一行留作分组表头，但标准化后列名仍然是 ``col_0``。二次抽取只关心“同一行的
        风向/综合值”等标签，因此在第一列明显是文本标签列时，可以安全回退到第一列。
        """
        if not table.columns or not table.data:
            return None
        first_column = str(table.columns[0] or "")
        first_values = [clean_text(value_at(row, 0)) for row in table.data if clean_text(value_at(row, 0))]
        if not first_values:
            return None
        if "\u98ce\u5411" in first_values[0]:
            # 风向频率表合并续表后，后半段可能出现大量数字行；只要首行明确是风向表头，第一列就是标签列。
            return {"columnIndex": 0, "column": first_column or "col_0", "score": 10, "selector": "fallback_first_column_direction_label"}
        numeric_like = sum(1 for value in first_values if parse_number(value) is not None)
        if numeric_like >= max(1, len(first_values) // 2):
            return None
        return {"columnIndex": 0, "column": first_column or "col_0", "score": 0, "selector": "fallback_first_column"}

    def _rows_to_skip_for_max_row_label(self, table: NormalizedTable, value_column: dict[str, Any], label_column: dict[str, Any]) -> set[int]:
        """识别并跳过标题行、分组表头行和空行。

        风向风能频率这类表常见双层表头，第一行是塔号，第二行是风向/风能频率。它们都不应参与
        最大值比较，否则会把 90m 风向频率这种表头文本当成数据。
        """
        skip_rows: set[int] = set()
        if not table.data:
            return skip_rows
        for row_index, row in enumerate(table.data):
            row_text = clean_text(" ".join(str(cell or "") for cell in row))
            if not row_text:
                skip_rows.add(row_index)
                continue
            if self._row_looks_like_value_header(row, value_column, label_column):
                skip_rows.add(row_index)
                continue
            value_text = clean_text(value_at(row, value_column.get("columnIndex")))
            if any(token in row_text for token in ("项目", "单位", "风向", "风能频率", "风向频率", "塔号")) and parse_number(value_text) is None:
                skip_rows.add(row_index)
                continue
            if value_text and re.search(r"[\u4e00-\u9fa5]", value_text):
                skip_rows.add(row_index)
        return skip_rows

    def _requires_wind_direction_label(self, rule: dict[str, Any], table: NormalizedTable) -> bool:
        """判断 max_row_label 是否应该限制返回值为风向标签。

        风向风能频率表被续表合并时，后半段可能是风速分布等数字行。最大值比较前先
        过滤非风向标签，可以避免把第一列的风速段数字误当成“最大值对应风向”。
        """
        text = f"{table.name} {' '.join(str(alias) for alias in (rule.get('value_column') or {}).get('aliases') or [])}"
        return "风向" in text and "风能频率" in text

    def _looks_like_wind_direction_label(self, value: Any) -> bool:
        """判断单元格值是否像风向名称。"""
        text = clean_text(value).upper().replace(" ", "")
        if not text:
            return False
        english = {"N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"}
        chinese = {"北", "北东北", "东北", "东东北", "东", "东东南", "东南", "南东南", "南", "南西南", "西南", "西西南", "西", "西西北", "西北", "北西北"}
        return text in english or clean_text(value) in chinese

    def _row_looks_like_value_header(self, row: list[Any], value_column: dict[str, Any], label_column: dict[str, Any]) -> bool:
        """判断一行是否像用于 max_row_label 的表头。"""
        value_text = clean_text(value_at(row, value_column.get("columnIndex")))
        label_text = clean_text(value_at(row, label_column.get("columnIndex")))
        if not value_text and not label_text:
            return False
        header_keywords = ("风向", "风能频率", "风向频率", "代表湍流强度", "综合值", "项目", "单位", "塔号")
        if any(keyword in value_text for keyword in header_keywords):
            return True
        if any(keyword in label_text for keyword in header_keywords):
            return True
        return False

    def _extract_column_values(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """抽取某一列的全部有效值，作为列表字段返回。

        用于“测风塔基本情况表”的【测风塔】列，把塔号列整列取出。
        """
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        column_specs = list(rule.get("columns") or [])
        if not column_specs:
            column_specs = [rule.get("column") or {}]
        column_spec: dict[str, Any] = {}
        column_result: dict[str, Any] = {"status": _NIL_STATUS, "reason": "column_not_found", "message": "未配置目标列。"}
        for candidate in column_specs:
            column_spec = candidate if isinstance(candidate, dict) else {"aliases": [candidate]}
            column_result = self._select_column_frame(frame, column_spec)
            if column_result.get("status") != _NIL_STATUS:
                break
        if column_result.get("status") == _NIL_STATUS and not rule.get("columns") and "index" not in column_spec:
            column_result = {"columnIndex": 0, "column": frame.columns[0], "selector": "first_column"}
        if column_result.get("status") == _NIL_STATUS:
            return nil_field(rule, column_result["reason"], column_result.get("message"), {**table_result, **column_result})
        column_index = column_result["columnIndex"]
        values: list[Any] = []
        value_pattern = column_spec.get("value_pattern") or rule.get("value_pattern")
        conversion = column_spec.get("conversion", rule.get("conversion"))
        dedupe = bool(rule.get("dedupe", True))
        exclude_patterns = [str(pattern) for pattern in rule.get("exclude_patterns") or []]
        for _, row in frame.iterrows():
            value = row.iloc[column_index]
            text = clean_text(value)
            if not text:
                continue
            # 跳过表头残留行（列名本身或“测风塔”这类标签）。
            if normalize_label(text) == normalize_label(column_result.get("column")):
                continue
            raw_values = [match.group(0) for match in re.finditer(str(value_pattern), text, flags=re.IGNORECASE)] if value_pattern else [text]
            for raw_value in raw_values:
                raw_text = clean_text(raw_value)
                if not raw_text:
                    continue
                if exclude_patterns and any(safe_search(pattern, raw_text) for pattern in exclude_patterns):
                    continue
                normalized = normalize_value(raw_value, str(rule.get("value_type") or "text"))
                normalized = apply_value_conversion(normalized, conversion)
                if not dedupe or normalized not in values:
                    values.append(normalized)
        return {
            "fieldCode": rule.get("field_code"),
            "fieldName": rule.get("field_name") or rule.get("field_code"),
            "value": values,
            "unit": rule.get("unit"),
            "status": "OK" if values else _NIL_STATUS,
            "section": rule.get("section"),
            "sourceKind": "table_column",
            "operation": "column_values",
            "nilReason": None if values else "value_empty",
            "message": None if values else "目标列没有可抽取的值。",
            "confidence": 1.0,
            "source": {
                "section": table.section_name,
                "tableKey": table.key,
                "tableName": table.name,
                "columnIndex": column_index,
                "column": column_result.get("column"),
            },
        }

    def _extract_cell_series(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """同一行按多个列规则批量取值，适合财务表第1年到第21年这类横向序列。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        row_result = self._select_row_for_rule(table, rule)
        if row_result.get("status") == _NIL_STATUS:
            return nil_field(rule, row_result["reason"], row_result.get("message"), {**table_result, **row_result})

        columns = list(rule.get("columns") or [])
        if not columns:
            return nil_field(rule, "column_not_found", "cell_series 未配置 columns。", table_result)

        values: dict[str, Any] = {}
        missing: list[str] = []
        selected: list[dict[str, Any]] = []
        for column_spec in columns:
            spec = column_spec if isinstance(column_spec, dict) else {"aliases": [column_spec]}
            output_name = str(spec.get("name") or first_alias(spec))
            column_result = self._select_series_column_frame(frame, spec, output_name)
            if column_result.get("status") == _NIL_STATUS:
                missing.append(output_name)
                continue
            raw_value = self._frame_value(frame, row_result["rowIndex"], column_result["columnIndex"])
            value_status = validate_cell_value(raw_value, str(rule.get("value_type") or "auto"))
            if value_status.get("status") == _NIL_STATUS:
                missing.append(output_name)
                continue
            values[output_name] = normalize_value(raw_value, str(rule.get("value_type") or "auto"))
            selected.append({"name": output_name, "columnIndex": column_result["columnIndex"], "column": column_result.get("column")})

        if missing and rule.get("strict", True):
            return nil_field(rule, "column_not_found", "部分目标列缺失或值为空。", {**table_result, **row_result, "missing": missing})
        if not values:
            return nil_field(rule, "value_empty", "目标序列没有可抽取的值。", {**table_result, **row_result, "missing": missing})
        return {
            "fieldCode": rule.get("field_code"),
            "fieldName": rule.get("field_name") or rule.get("field_code"),
            "value": values,
            "unit": rule.get("unit"),
            "status": "OK",
            "section": rule.get("section"),
            "sourceKind": "table_cells",
            "operation": "cell_series",
            "confidence": 1.0,
            "source": {
                "section": table.section_name,
                "tableKey": table.key,
                "tableName": table.name,
                "rowIndex": row_result.get("rowIndex"),
                "rowText": clean_text(" ".join(str(cell or "") for cell in row_result.get("row") or [])),
                "columns": selected,
                "missing": missing,
            },
        }

    def _select_series_column_frame(self, frame: Any, spec: dict[str, Any], output_name: str) -> dict[str, Any]:
        """年份序列优先按完整“第N年”列名匹配，避免短数字别名命中错列。"""
        normalized_name = normalize_label(output_name)
        if re.fullmatch(r"第?\d+年", normalized_name):
            exact = self._select_column_frame(frame, {"aliases": [output_name], "allow_ambiguous": spec.get("allow_ambiguous", False)})
            if exact.get("status") != _NIL_STATUS:
                return exact
        return self._select_column_frame(frame, spec)

    def _extract_cell_ratio(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """用两个表内单元格计算比率，默认输出 numerator / denominator * 100。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)

        numerator_result = self._extract_operand_cell(context, rule, table, frame, rule.get("numerator") or {})
        denominator_result = self._extract_operand_cell(context, rule, table, frame, rule.get("denominator") or {})
        missing = []
        if numerator_result.get("status") == _NIL_STATUS:
            missing.append({"operand": "numerator", **numerator_result})
        if denominator_result.get("status") == _NIL_STATUS:
            missing.append({"operand": "denominator", **denominator_result})
        if missing:
            return nil_field(rule, "source_cell_not_found", "参与比率计算的来源单元格缺失或无法转数值。", {**table_result, "missing": missing})
        denominator_value = denominator_result["value"]
        if denominator_value == 0:
            return nil_field(rule, "division_by_zero", "分母为 0，无法计算比率。", {**table_result, "missing": []})

        multiplier = float(rule.get("multiplier", 100))
        value = numerator_result["value"] / denominator_value * multiplier
        if "precision" in rule:
            value = round(value, int(rule.get("precision")))
        return {
            "fieldCode": rule.get("field_code"),
            "fieldName": rule.get("field_name") or rule.get("field_code"),
            "value": normalize_number(value),
            "unit": rule.get("unit"),
            "status": "OK",
            "section": rule.get("section"),
            "sourceKind": "derived_field",
            "operation": "cell_ratio",
            "sources": [
                {"operand": "numerator", **numerator_result["source"]},
                {"operand": "denominator", **denominator_result["source"]},
            ],
            "confidence": 1.0,
        }

    def _extract_operand_cell(self, context: "ResultContext", rule: dict[str, Any], table: NormalizedTable, frame: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """按 operand 里的 row/column 配置抽一个数值单元格。"""
        source_table = spec.get("source_table")
        if source_table:
            source_rule = {"section": rule.get("section"), "source_table": source_table}
            table_result = self._locate_table(context, source_rule)
            if table_result.get("status") == _NIL_STATUS:
                return table_result
            table = table_result["table"]
            frame = self._table_frame(table)
        row_result = self._select_row_for_rule(table, {"row": spec.get("row") or {}})
        if row_result.get("status") == _NIL_STATUS:
            return row_result
        column_result = self._select_column_frame(frame, spec.get("column") or {})
        if column_result.get("status") == _NIL_STATUS:
            fallback_column = self._fallback_value_column_for_labeled_row(table, row_result, spec.get("column") or {})
            if fallback_column is None:
                return column_result
            column_result = fallback_column
        raw_value = self._frame_value(frame, row_result["rowIndex"], column_result["columnIndex"])
        number = parse_number(raw_value)
        if number is None:
            return {"status": _NIL_STATUS, "reason": "value_parse_failed", "message": "来源单元格无法转数值。"}
        return {
            "value": number,
            "source": {
                "rowIndex": row_result.get("rowIndex"),
                "rowText": clean_text(" ".join(str(cell or "") for cell in row_result.get("row") or [])),
                "columnIndex": column_result.get("columnIndex"),
                "column": column_result.get("column"),
                "rawValue": raw_value,
            },
        }

    def _extract_sector_max(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """在分块式风向/风能分布表中，返回某测风塔指定指标最大值对应的扇区。

        韩家沟“各扇区风向和风能分布统计”表把每个测风塔排成一小块：塔号在第一列，
        第二列是“风向（%）/风功率（%）/扇区”三种行标签，数值列放在后面。这里把
        指标行里的数值按顺序铺开，再把列头 + “扇区”行里的标签按同样顺序铺开，
        取数值最大位置对应的标签。
        """
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_field(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        tower_spec = rule.get("tower") or {}
        tower_patterns = [str(pattern) for pattern in tower_spec.get("patterns") or tower_spec.get("aliases") or []]
        tower_column = self._select_column_frame(frame, rule.get("tower_column") or {"aliases": ["测风塔", "塔号"]})
        if tower_column.get("status") == _NIL_STATUS:
            tower_column = {"columnIndex": 0, "column": frame.columns[0] if len(frame.columns) else "col_0", "selector": "first_column"}
        metric_column = self._select_column_frame(frame, rule.get("metric_column") or {"aliases": ["扇区", "项目"]})
        if metric_column.get("status") == _NIL_STATUS:
            metric_column = {"columnIndex": 1, "column": frame.columns[1] if len(frame.columns) > 1 else "col_1", "selector": "second_column"}
        metric_spec = rule.get("metric") or {}
        metric_patterns = [str(pattern) for pattern in metric_spec.get("patterns") or metric_spec.get("aliases") or []]
        label_spec = rule.get("label") or {}
        label_patterns = [str(pattern) for pattern in label_spec.get("patterns") or label_spec.get("aliases") or ["扇区"]]
        value_start = int(metric_column["columnIndex"]) + 1
        value_columns = list(range(value_start, len(frame.columns)))
        if not value_columns:
            return nil_field(rule, "column_not_found", "没有可用于比较的数值列。", {**table_result, **metric_column})

        current_labels = [clean_text(frame.columns[index]) for index in value_columns]
        pairs: list[tuple[str, Any]] = []
        tower_hit = False
        in_tower_block = False
        for _, row in frame.iterrows():
            tower_cell = clean_text(row.iloc[tower_column["columnIndex"]])
            if tower_cell:
                in_tower_block = not tower_patterns or row_match_score(tower_cell, tower_patterns) > 0
                if not in_tower_block:
                    continue
                tower_hit = True
            elif not in_tower_block:
                continue
            tower_hit = True
            metric_cell = clean_text(row.iloc[metric_column["columnIndex"]])
            if row_match_score(metric_cell, label_patterns) > 0:
                current_labels = [clean_text(row.iloc[index]) for index in value_columns]
            elif metric_patterns and row_match_score(metric_cell, metric_patterns) > 0:
                pairs.extend((current_labels[offset], row.iloc[index]) for offset, index in enumerate(value_columns) if offset < len(current_labels))
        if not tower_hit:
            return nil_field(rule, "row_not_found", f"未找到测风塔行：{tower_patterns}", {**table_result, **tower_column})
        if not pairs:
            return nil_field(rule, "value_empty", "未找到指标数值行。", {**table_result, **metric_column})
        ranked: list[tuple[int, str, float]] = []
        for index, (label, value) in enumerate(pairs):
            number = parse_metric_number(value)
            if number is None:
                continue
            ranked.append((index, label, number))
        if not ranked:
            return nil_field(rule, "value_parse_failed", "指标数值无法解析。", {**table_result, **metric_column})
        ranked.sort(key=lambda item: item[2], reverse=True)
        rank = max(int(rule.get("rank") or 1), 1)
        if rank > len(ranked):
            return nil_field(rule, "rank_out_of_range", f"指标数值不足 {rank} 个。", {**table_result, **metric_column})
        best_index, label, best_value = ranked[rank - 1]
        return {
            "fieldCode": rule.get("field_code"),
            "fieldName": rule.get("field_name") or rule.get("field_code"),
            "value": normalize_value(label, str(rule.get("value_type") or "text")),
            "unit": rule.get("unit"),
            "status": "OK",
            "section": rule.get("section"),
            "sourceKind": "table_cell",
            "operation": "sector_max",
            "maxValue": best_value,
            "rank": rank,
            "rankValue": best_value,
            "confidence": 1.0,
            "source": {
                "section": table.section_name,
                "tableKey": table.key,
                "tableName": table.name,
                "towerPatterns": tower_patterns,
                "metricPatterns": metric_patterns,
                "selector": "sector_max",
                "rank": rank,
                "rankIndex": best_index,
            },
        }

    def _extract_sum_fields(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """从现有 result 字段中求和生成派生值。"""
        field_codes = list(rule.get("source_fields") or [])
        values: list[float] = []
        sources: list[dict[str, Any]] = []
        missing: list[str] = []
        for field_code in field_codes:
            field = context.field_index.get(str(field_code))
            number = parse_number((field or {}).get("value"))
            if field is None or number is None:
                missing.append(str(field_code))
                continue
            values.append(number)
            sources.append({"fieldCode": field_code, "value": field.get("value"), "unit": field.get("unit")})
        if missing:
            return nil_field(rule, "source_field_not_found", "参与计算的来源字段缺失或无法转数值。", {"missing": missing, "sources": sources})
        value = sum(values)
        return {
            "fieldCode": rule.get("field_code"),
            "fieldName": rule.get("field_name") or rule.get("field_code"),
            "value": normalize_number(value),
            "unit": rule.get("unit"),
            "status": "OK",
            "section": rule.get("section"),
            "sourceKind": "derived_field",
            "operation": "sum_fields",
            "sources": sources,
            "confidence": 1.0,
        }
