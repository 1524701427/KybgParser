"""Secondary extraction: projection. Existing rule semantics are preserved."""

from __future__ import annotations

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.primitives import clean_text, first_alias, normalize_label, row_match_score, safe_search, value_at

from word_parser.extraction.table_values.results import derived_table_result, nil_table


class ProjectionOperationsMixin:
    def _extract_table_projection(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """按列投影来源表子表。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_table(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        projections = list(rule.get("columns") or [])
        selected: list[dict[str, Any]] = []
        for spec in projections:
            column_spec = spec if isinstance(spec, dict) else {"aliases": [spec]}
            result = self._select_column_frame(frame, column_spec)
            if result.get("status") == _NIL_STATUS:
                if rule.get("strict", True):
                    return nil_table(rule, result["reason"], result.get("message"), {**table_result, **result})
                selected.append({"name": first_alias(column_spec), "columnIndex": None, "sourceColumn": None})
            else:
                selected.append({"name": str(column_spec.get("name") or result.get("column") or first_alias(column_spec)), "columnIndex": result["columnIndex"], "sourceColumn": result.get("column")})
        rows: list[list[Any]] = []
        for _, row in frame.iterrows():
            rows.append([row.iloc[item["columnIndex"]] if item["columnIndex"] is not None else None for item in selected])
        return derived_table_result(rule, table, [item["name"] for item in selected], rows, {"selectedColumns": selected})

    def _extract_filter_table_projection(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """按行别名筛选来源表，再按列投影生成设备清单。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_table(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        projections = list(rule.get("columns") or [])
        selected: list[dict[str, Any]] = []
        for spec in projections:
            column_spec = spec if isinstance(spec, dict) else {"aliases": [spec]}
            result = self._select_column_frame(frame, column_spec)
            if result.get("status") == _NIL_STATUS:
                if rule.get("strict", True):
                    return nil_table(rule, result["reason"], result.get("message"), {**table_result, **result})
                selected.append({"name": first_alias(column_spec), "columnIndex": None, "sourceColumn": None})
            else:
                result = self._apply_projection_column_offset(frame, result, column_spec)
                selected.append({"name": str(column_spec.get("name") or result.get("column") or first_alias(column_spec)), "columnIndex": result["columnIndex"], "sourceColumn": result.get("column")})
        match_column_indices = self._filter_projection_match_column_indices(frame, rule, selected)
        items = [item for item in rule.get("items") or [] if isinstance(item, dict)]
        rows: list[list[Any]] = []
        matched: list[dict[str, Any]] = []
        emitted_rows: set[int] = set()
        for row_index, row in frame.iterrows():
            row_values = row.tolist()
            search_text = self._filter_projection_search_text(row_values, match_column_indices)
            if not search_text:
                continue
            match = self._best_filter_projection_item(search_text, items)
            if match is None:
                continue
            if row_index in emitted_rows and rule.get("dedupe_source_rows", True):
                continue
            emitted_rows.add(row_index)
            values = [row.iloc[item["columnIndex"]] if item["columnIndex"] is not None else None for item in selected]
            rows.append([match["name"], *values])
            matched.append({"rowIndex": int(row_index), "deviceCategory": match["name"], "matchedAlias": match["alias"], "score": match["score"], "rowText": search_text})
        if not rows:
            return nil_table(rule, "row_not_found", "未找到命中设备别名的行。", {**table_result, "itemCount": len(items)})
        return derived_table_result(
            rule,
            table,
            [str(rule.get("match_column_name") or "设备类别"), *[item["name"] for item in selected]],
            rows,
            {"selectedColumns": selected, "matchedRows": matched, "itemCount": len(items), "matchColumns": match_column_indices},
        )

    def _filter_projection_match_column_indices(self, frame: Any, rule: dict[str, Any], selected: list[dict[str, Any]]) -> list[int]:
        selector = rule.get("match_columns")
        if selector:
            indices = self._frame_column_indices(frame, selector)
            if indices:
                return indices
        selected_indices = [item["columnIndex"] for item in selected if item.get("columnIndex") is not None]
        return selected_indices or list(range(len(frame.columns)))

    def _apply_projection_column_offset(self, frame: Any, result: dict[str, Any], column_spec: dict[str, Any]) -> dict[str, Any]:
        offset = int(column_spec.get("offset") or 0)
        if not offset:
            return result
        source_patterns = [str(pattern) for pattern in column_spec.get("offset_when_source_matches") or []]
        source_column = clean_text(result.get("column"))
        if source_patterns and not any(safe_search(pattern, source_column) for pattern in source_patterns):
            return result
        shifted_index = int(result["columnIndex"]) + offset
        if shifted_index < 0 or shifted_index >= len(frame.columns):
            return result
        shifted = dict(result)
        shifted["columnIndex"] = shifted_index
        shifted["column"] = frame.columns[shifted_index]
        shifted["selector"] = f"{result.get('selector') or 'column'}_offset_{offset}"
        shifted["offsetFromColumn"] = source_column
        return shifted

    def _filter_projection_search_text(self, row_values: list[Any], indices: list[int]) -> str:
        parts = [clean_text(value_at(row_values, index)) for index in indices]
        return clean_text(" ".join(part for part in parts if part))

    def _best_filter_projection_item(self, text: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for order, item in enumerate(items):
            name = clean_text(item.get("name"))
            exclude_aliases = [clean_text(alias) for alias in item.get("exclude_aliases") or [] if clean_text(alias)]
            if exclude_aliases and self._best_matching_alias(text, exclude_aliases) is not None:
                continue
            all_aliases = [clean_text(alias) for alias in item.get("all_aliases") or [] if clean_text(alias)]
            all_results = [self._best_matching_alias(text, [alias]) for alias in all_aliases]
            if all_aliases and any(result is None for result in all_results):
                continue
            aliases = [clean_text(alias) for alias in item.get("aliases") or [] if clean_text(alias)]
            patterns = aliases or ([name] if name else [])
            alias_result = self._best_matching_alias(text, patterns) if patterns else None
            if all_aliases:
                required_results = [result for result in all_results if result is not None]
                required_alias = " && ".join(result[0] for result in required_results)
                required_score = sum(result[1] for result in required_results)
                required_length = sum(result[2] for result in required_results)
                if alias_result is None or required_score > alias_result[1]:
                    alias_result = (required_alias, required_score, required_length)
            if alias_result is None:
                continue
            alias, score, alias_length = alias_result
            candidate = {"name": name or alias, "alias": alias, "score": score, "aliasLength": alias_length, "order": order}
            if (
                best is None
                or candidate["score"] > best["score"]
                or (candidate["score"] == best["score"] and candidate["aliasLength"] > best["aliasLength"])
                or (
                    candidate["score"] == best["score"]
                    and candidate["aliasLength"] == best["aliasLength"]
                    and candidate["order"] < best["order"]
                )
            ):
                best = candidate
        return best

    def _best_matching_alias(self, text: str, aliases: list[str]) -> tuple[str, int, int] | None:
        best: tuple[str, int, int] | None = None
        for alias in aliases:
            score = row_match_score(text, [alias])
            if score <= 0:
                continue
            alias_length = len(normalize_label(alias))
            if best is None or score > best[1] or (score == best[1] and alias_length > best[2]):
                best = (alias, score, alias_length)
        return best

    def _extract_copy_table(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """复制来源表到二次抽取结果。"""
        table_result = self._locate_table(context, rule)
        if table_result.get("status") == _NIL_STATUS:
            return nil_table(rule, table_result["reason"], table_result.get("message"), table_result)
        table = table_result["table"]
        frame = self._table_frame(table)
        return derived_table_result(rule, table, table.columns, frame.values.tolist(), {"copy": True})
