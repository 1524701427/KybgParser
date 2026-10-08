"""Secondary extraction: locator. Existing rule semantics are preserved."""

from __future__ import annotations

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.models import NormalizedTable

from word_parser.extraction.table_values.primitives import clean_text, column_match_score, normalize_label, parse_number, row_match_score, safe_search, value_at

from word_parser.extraction.table_values.results import table_summaries

from word_parser.extraction.table_values.selectors import select_column


class TableLocatorMixin:
    def _table_frame(self, table: NormalizedTable):
        """构建 pandas DataFrame 并缓存。"""
        cache_key = id(table)
        cached = self._table_frame_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("缺少 pandas 依赖") from exc
        width = len(table.columns or [])
        for row in table.data or []:
            if len(row) > width:
                width = len(row)
        columns = list(table.columns or [])
        if width > len(columns):
            columns.extend(f"col_{index}" for index in range(len(columns), width))
        rows = [self._pad_row(row, width) for row in table.data or []]
        frame = pd.DataFrame(rows, columns=columns)
        self._table_frame_cache[cache_key] = frame
        return frame

    def _pad_row(self, row: list[Any], width: int) -> list[Any]:
        """补齐行宽到 DataFrame 列数。"""
        padded = list(row[:width])
        if len(padded) < width:
            padded.extend([None] * (width - len(padded)))
        return padded

    def _frame_value(self, frame: Any, row_index: int, column_index: int | None) -> Any:
        """读取 DataFrame 单元格。"""
        if column_index is None:
            return None
        if row_index < 0 or row_index >= len(frame.index):
            return None
        if column_index < 0 or column_index >= len(frame.columns):
            return None
        return frame.iat[row_index, column_index]

    def _merged_cell_value(self, frame: Any, row_result: dict[str, Any], column_result: dict[str, Any], rule: dict[str, Any]) -> str:
        """读取本行单元格，并按配置合并后续空名称续行。"""
        row_index = int(row_result.get("rowIndex") or 0)
        column_index = int(column_result.get("columnIndex"))
        merge_config = rule.get("merge_following_rows")
        if isinstance(merge_config, dict):
            max_rows = int(merge_config.get("max_rows") or 8)
            stop_when = [str(pattern) for pattern in merge_config.get("stop_when") or []]
        else:
            max_rows = 8
            stop_when = []
        values: list[str] = []
        base_value = clean_text(self._frame_value(frame, row_index, column_index))
        if base_value:
            values.append(base_value)
        for next_row_index in range(row_index + 1, min(len(frame.index), row_index + 1 + max_rows)):
            next_row = self._frame_row(frame, next_row_index)
            row_text = clean_text(" ".join(str(cell or "") for cell in next_row))
            if not row_text:
                continue
            leading_text = clean_text(" ".join(str(value_at(next_row, index) or "") for index in range(min(column_index, len(next_row)))))
            if stop_when and any(safe_search(pattern, row_text) for pattern in stop_when):
                break
            if leading_text and parse_number(value_at(next_row, 0)) is not None:
                break
            value = clean_text(value_at(next_row, column_index))
            if value:
                values.append(value)
        return "，".join(dict.fromkeys(values))

    def _frame_row(self, frame: Any, row_index: int) -> list[Any]:
        """读取 DataFrame 某一行。"""
        return frame.iloc[row_index].tolist()

    def _select_column_frame(self, frame: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """选择 DataFrame 列。"""
        columns = list(frame.columns)
        if "index" in spec:
            index = int(spec.get("index"))
            if 0 <= index < len(columns):
                return {"columnIndex": index, "column": columns[index], "selector": "index"}
            return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"列号越界：{index}"}
        aliases = [str(alias) for alias in spec.get("aliases") or spec.get("patterns") or []]
        matches: list[dict[str, Any]] = []
        for index, column in enumerate(columns):
            if spec.get("exact") and not any(normalize_label(column) == normalize_label(alias) for alias in aliases):
                continue
            score = column_match_score(column, aliases)
            if score > 0:
                matches.append({"columnIndex": index, "column": column, "score": score})
        if not matches:
            return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"未找到匹配列：{aliases}", "columns": columns}
        if "occurrence" in spec:
            try:
                occurrence = int(spec.get("occurrence") or 0)
            except (TypeError, ValueError):
                occurrence = 0
            matches.sort(key=lambda item: item["columnIndex"])
            if 0 <= occurrence < len(matches):
                return {**matches[occurrence], "selector": "label_occurrence"}
            return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"匹配列 occurrence 越界：{occurrence}", "candidates": matches[:5]}
        matches.sort(key=lambda item: item["score"], reverse=True)
        if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
            return {"status": _NIL_STATUS, "reason": "ambiguous_column", "message": "列选择命中多个同分候选。", "candidates": matches[:5]}
        return {**matches[0], "selector": "label"}

    def _frame_column_indices(self, frame: Any, selector: Any) -> list[int]:
        """把列选择转成 DataFrame 列索引。"""
        if selector is None:
            return []
        specs = selector if isinstance(selector, list) else [selector]
        indices: list[int] = []
        for item in specs:
            if isinstance(item, int):
                indices.append(item)
                continue
            result = self._select_column_frame(frame, {"aliases": [item]})
            if result.get("status") != _NIL_STATUS:
                indices.append(result["columnIndex"])
        return indices

    def _select_row_frame(self, frame: Any, spec: dict[str, Any]) -> dict[str, Any]:
        """选择 DataFrame 行。"""
        selector_type = spec.get("type") or "label"
        if selector_type == "index":
            index = int(spec.get("index", 0))
            base = str(spec.get("index_base") or "data_rows")
            row_index = index - 1 if base == "data_rows" and index > 0 else index
            if 0 <= row_index < len(frame.index):
                return {"rowIndex": row_index, "row": self._frame_row(frame, row_index), "selector": "index"}
            return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"行号越界：{index}"}
        patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
        exclude_patterns = [str(pattern) for pattern in spec.get("exclude_patterns") or spec.get("exclude_aliases") or []]
        all_patterns = [str(pattern) for pattern in spec.get("all_patterns") or spec.get("all_aliases") or []]
        search_columns = self._frame_column_indices(frame, spec.get("column") or spec.get("column_aliases"))
        matches: list[dict[str, Any]] = []
        for row_index, row in frame.iterrows():
            cells = row.iloc[search_columns].tolist() if search_columns else row.tolist()
            text = clean_text(" ".join(str(cell or "") for cell in cells))
            if not text:
                continue
            if exclude_patterns and row_match_score(text, exclude_patterns) > 0:
                continue
            all_scores = [row_match_score(text, [pattern], exact=bool(spec.get("exact"))) for pattern in all_patterns]
            if all_patterns and any(score <= 0 for score in all_scores):
                continue
            score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
            if all_patterns:
                score = max(score, sum(all_scores))
            if score > 0:
                matches.append({"rowIndex": row_index, "row": row.tolist(), "score": score, "text": text})
        if not matches:
            return {"status": _NIL_STATUS, "reason": "row_not_found", "message": "未找到匹配行。"}
        matches.sort(key=lambda item: item["score"], reverse=True)
        if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
            return {"status": _NIL_STATUS, "reason": "ambiguous_row", "message": "行选择命中多个同分候选。", "candidates": matches[:5]}
        return {**matches[0], "selector": "label"}

    def _select_row_occurrence_frame(self, frame: Any, spec: dict[str, Any], occurrence: int) -> dict[str, Any]:
        """按出现次序选择 DataFrame 行。"""
        patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
        exclude_patterns = [str(pattern) for pattern in spec.get("exclude_patterns") or spec.get("exclude_aliases") or []]
        search_columns = self._frame_column_indices(frame, spec.get("column") or spec.get("column_aliases"))
        matches: list[dict[str, Any]] = []
        for row_index, row in frame.iterrows():
            cells = row.iloc[search_columns].tolist() if search_columns else row.tolist()
            text = clean_text(" ".join(str(cell or "") for cell in cells))
            if not text:
                continue
            if exclude_patterns and row_match_score(text, exclude_patterns) > 0:
                continue
            score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
            if score > 0:
                matches.append({"rowIndex": row_index, "row": row.tolist(), "score": score, "text": text})
        matches.sort(key=lambda item: item["rowIndex"])
        min_occurrences = max(int(spec.get("min_occurrences") or 0), 0)
        if len(matches) < min_occurrences:
            return {
                "status": _NIL_STATUS,
                "reason": "row_not_found",
                "message": f"匹配行不足 {min_occurrences} 个，实际找到 {len(matches)} 个。",
                "candidates": matches[:10],
            }
        if occurrence < len(matches):
            return {**matches[occurrence], "selector": "label_occurrence", "occurrence": occurrence}
        if len(matches) == 1 and occurrence > 0:
            return {**matches[0], "selector": "label_occurrence_fallback", "occurrence": 0}
        return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"未找到第 {occurrence + 1} 个匹配行。", "candidates": matches[:10]}

    def _locate_table(self, context: "ResultContext", rule: dict[str, Any]) -> dict[str, Any]:
        """根据配置定位来源表。"""
        source_table = rule.get("source_table") or {}
        section_name = rule.get("section") or source_table.get("section")
        key = source_table.get("key") or rule.get("source_table_key")
        candidates = context.tables(section_name)
        patterns = [str(pattern) for pattern in source_table.get("name_patterns") or []]
        has_constraints = self._source_has_constraints(source_table)
        constrained = [table for table in candidates if self._table_matches_source_constraints(table, source_table)] if has_constraints else []
        if key:
            matched = [table for table in candidates if table.key == key]
            if len(matched) == 1:
                if has_constraints and not self._table_matches_source_constraints(matched[0], source_table):
                    if len(constrained) == 1:
                        return {"table": constrained[0], "matchMethod": "content_constraint", "confidence": 0.95}
                    if len(constrained) > 1:
                        return {"status": _NIL_STATUS, "reason": "ambiguous_table", "message": "二次抽取表约束命中多张表。", "candidates": table_summaries(constrained)}
                    fallback = self._fallback_table_for_source_constraints(candidates, source_table)
                    if fallback is not None:
                        return fallback
                    return {
                        "status": _NIL_STATUS,
                        "reason": "table_constraints_mismatch",
                        "message": "表 key 命中，但表名或表内容不满足二次抽取配置约束。",
                        "keyTable": table_summaries(matched),
                        "expectedPatterns": patterns,
                        "requiredColumns": source_table.get("required_columns") or [],
                    }
                return {"table": matched[0], "matchMethod": "key", "confidence": 1.0}
            if not matched and not section_name:
                matched = [table for table in context.tables() if table.key == key]
                if len(matched) == 1:
                    if has_constraints and not self._table_matches_source_constraints(matched[0], source_table):
                        fallback = self._fallback_table_for_source_constraints(context.tables(), source_table)
                        if fallback is not None:
                            return fallback
                        return {
                            "status": _NIL_STATUS,
                            "reason": "table_constraints_mismatch",
                            "message": "表 key 命中，但表名或表内容不满足二次抽取配置约束。",
                            "keyTable": table_summaries(matched),
                            "expectedPatterns": patterns,
                            "requiredColumns": source_table.get("required_columns") or [],
                        }
                    return {"table": matched[0], "matchMethod": "key", "confidence": 1.0}
            if not matched and not source_table.get("name_patterns"):
                return {"status": _NIL_STATUS, "reason": "table_not_found", "message": f"未找到表 key：{key}"}
        if has_constraints:
            if len(constrained) == 1:
                return {"table": constrained[0], "matchMethod": "content_constraint", "confidence": 0.95}
            if len(constrained) > 1:
                original_tables = [table for table in constrained if not table.table.get("tableCode")]
                if len(original_tables) == 1:
                    return {"table": original_tables[0], "matchMethod": "content_constraint_original", "confidence": 0.95}
                return {"status": _NIL_STATUS, "reason": "ambiguous_table", "message": "二次抽取表约束命中多张表。", "candidates": table_summaries(constrained)}
            fallback = self._fallback_table_for_source_constraints(candidates, source_table)
            if fallback is not None:
                return fallback
        if key:
            return {"status": _NIL_STATUS, "reason": "table_not_found", "message": f"未找到来源表：{key}", "candidates": table_summaries(candidates)}
        return {"status": _NIL_STATUS, "reason": "table_not_found", "message": "规则没有定位到来源表。", "candidates": table_summaries(candidates)}

    def _source_has_constraints(self, source_table: dict[str, Any]) -> bool:
        """判断来源表配置是否声明了标题或内容约束。"""
        return bool(source_table.get("name_patterns") or source_table.get("required_columns") or source_table.get("required_text"))

    def _table_matches_source_constraints(self, table: NormalizedTable, source_table: dict[str, Any]) -> bool:
        """判断表是否满足二次抽取配置中的标题和内容约束。

        约束按“标题 + 列名 + 关键文本”三层组合：

        - ``name_patterns``：优先匹配表名；声明 ``name_match_content: true`` 时，
          表名不命中可回退到“列名 + 前几行”的内容匹配，兼容表题不贴在表前的报告。
        - ``required_columns``：列名必须全部命中。
        - ``required_text``：正文内容必须全部命中。
        """
        patterns = [str(pattern) for pattern in source_table.get("name_patterns") or []]
        if patterns and not self._text_matches_patterns(table.name, patterns):
            if not source_table.get("name_match_content"):
                return False
            if not self._text_matches_patterns(self._table_content_text(table, limit=6), patterns):
                return False
        for column_spec in source_table.get("required_columns") or []:
            spec = column_spec if isinstance(column_spec, dict) else {"aliases": [column_spec]}
            if select_column(table, spec).get("status") == _NIL_STATUS:
                return False
        content = self._table_content_text(table)
        for pattern in source_table.get("required_text") or []:
            if not self._text_matches_patterns(content, [str(pattern)]):
                return False
        return True

    @staticmethod
    def _table_content_text(table: NormalizedTable, limit: int | None = None) -> str:
        """把列名和数据行拼成用于内容匹配的文本。"""
        columns_text = " ".join(table.columns)
        rows = table.data if limit is None else table.data[:limit]
        rows_text = " ".join(" ".join(str(cell or "") for cell in row) for row in rows)
        return f"{table.name} {columns_text} {rows_text}"

    def _table_matches_name_patterns(self, table: NormalizedTable, patterns: list[str]) -> bool:
        """判断表名是否满足二次抽取配置中的标题约束。"""
        return self._text_matches_patterns(table.name, patterns)

    def _text_matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """判断文本是否满足任意一个标题约束。

        除了按原始正则匹配，还做一次“去空白”兜底匹配，兼容 ``表2.6-1`` 与
        ``表 2.6-1``、全角空格、塔号前后空格等排版差异。
        """
        if not patterns:
            return True
        compact_text = re.sub(r"\s+", "", text)
        for pattern in patterns:
            if safe_search(pattern, text):
                return True
            compact_pattern = re.sub(r"\\s\*", "", str(pattern))
            compact_pattern = re.sub(r"\s+", "", compact_pattern)
            if compact_pattern and compact_text and safe_search(compact_pattern, compact_text):
                return True
        return False

    def _fallback_table_for_source_constraints(self, candidates: list[NormalizedTable], source_table: dict[str, Any]) -> dict[str, Any] | None:
        """当 key 或标题错挂时，按表格结构兜底定位来源表。

        这里不放宽配置文件，而是在二次抽取层识别已经进入 result 的风切变合并表。
        只有表内出现“综合值”且形态像高度-高度段矩阵时才命中，降低误选湍流强度表的概率。
        """
        if not self._source_is_wind_shear(source_table):
            return None
        matches = [table for table in candidates if self._table_looks_like_wind_shear(table)]
        if len(matches) == 1:
            return {"table": matches[0], "matchMethod": "wind_shear_structure_fallback", "confidence": 0.82}
        if len(matches) > 1:
            return {"status": _NIL_STATUS, "reason": "ambiguous_table", "message": "风切变结构兜底命中多张表。", "candidates": table_summaries(matches)}
        return None

    def _source_is_wind_shear(self, source_table: dict[str, Any]) -> bool:
        """判断来源表约束是否指向风速切变指数表。"""
        text = " ".join(str(pattern) for pattern in source_table.get("name_patterns") or [])
        text += " " + str(source_table.get("key") or "")
        return any(keyword in text for keyword in ("风速切变", "风切变", "Shear", "shear"))

    def _source_table_number(self, source_table: dict[str, Any]) -> str | None:
        """从来源表标题正则中提取类似 2.5-17 的表号。"""
        text = " ".join(str(pattern) for pattern in source_table.get("name_patterns") or [])
        normalized = text.replace("\\s*", " ").replace("\\.", ".").replace("\\", "")
        match = re.search(r"表\s*(\d+(?:\.\d+)*-\d+)", normalized)
        if match:
            return match.group(1)
        match = re.search(r"(\d+(?:\.\d+)*-\d+)", normalized)
        return match.group(1) if match else None

    def _table_looks_like_wind_shear(self, table: NormalizedTable) -> bool:
        """判断 result 中的一张表是否像合并后的风切变指数表。"""
        columns_text = clean_text(" ".join(table.columns))
        rows_text = clean_text(" ".join(" ".join(str(cell or "") for cell in row) for row in table.data[:30]))
        text = f"{table.name} {columns_text} {rows_text}"
        if "综合值" not in text:
            return False
        if "风速段" in columns_text or "代表湍流强度" in columns_text:
            return False
        height_columns = sum(1 for column in table.columns if re.fullmatch(r"\d+(?:\.\d+)?", clean_text(column)))
        first_column_values = [clean_text(value_at(row, 0)) for row in table.data[:12]]
        height_rows = sum(1 for value in first_column_values if re.fullmatch(r"\d+(?:\.\d+)?", value))
        return "高度" in columns_text or height_columns >= 3 or height_rows >= 3
