"""Secondary extraction: expansion. Existing rule semantics are preserved."""

from __future__ import annotations

import copy

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS

from word_parser.extraction.table_values.primitives import clean_text, safe_search


class RuleExpansionMixin:
    @staticmethod
    def _cell_item_rules(rule: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand one shared cell rule into per-item field rules.

        Items without ``field_code`` are intentionally ignored so the same alias
        catalogue can also serve a filtered table projection.
        """
        expanded: list[dict[str, Any]] = []
        for item in rule.get("items") or []:
            if not isinstance(item, dict) or not item.get("field_code"):
                continue
            item_rule = copy.deepcopy(rule)
            item_rule.pop("items", None)
            item_rule["operation"] = "cell_items"
            item_rule["field_code"] = item.get("field_code")
            item_rule["field_name"] = item.get("field_name") or item.get("name") or item.get("field_code")
            if "unit" in item:
                item_rule["unit"] = item.get("unit")

            row = copy.deepcopy(rule.get("row") or {})
            row.setdefault("type", "label")
            for key in ("aliases", "all_aliases", "exclude_aliases", "patterns", "exact"):
                if key in item:
                    row[key] = copy.deepcopy(item[key])
            item_rule["row"] = row
            expanded.append(item_rule)
        return expanded

    def _expand_rules(self, rules: list[dict[str, Any]], context: "ResultContext" | None = None) -> list[dict[str, Any]]:
        """按模板变量展开规则，避免为塔号、高度、年份等维度重复写规则。

        ``towers`` 是兼容旧配置的快捷变量，会生成 ``{tower}``、``{tower_clean}``、
        ``{tower_index}`` 和 ``{tower_ordinal}``。新配置可以声明 ``variables``，
        每个变量会生成 ``{变量名}``、``{变量名_clean}``、``{变量名_index}`` 和
        ``{变量名_ordinal}``。多个变量按笛卡尔积展开。
        """
        expanded: list[dict[str, Any]] = []
        for rule in rules:
            partials: list[tuple[dict[str, Any], dict[str, str]]] = [(copy.deepcopy(rule), {})]
            towers = rule.get("towers")
            if towers:
                next_partials: list[tuple[dict[str, Any], dict[str, str]]] = []
                for partial_rule, values in partials:
                    tower_values = self._tower_values(context, partial_rule, towers)
                    for index, tower in enumerate(tower_values):
                        tower_text = self._normalize_tower_code(tower)
                        if not tower_text:
                            continue
                        rendered_values = {**values, **self._template_values_for("tower", tower_text, index)}
                        next_partials.append((self._render_rule_template(partial_rule, rendered_values), rendered_values))
                partials = next_partials
            variables = rule.get("variables") or {}
            variable_items = variables.items() if isinstance(variables, dict) else ((item.get("name"), item) for item in variables if isinstance(item, dict))
            for name, spec in variable_items:
                variable_name = clean_text(name)
                if not variable_name:
                    continue
                next_partials = []
                for partial_rule, values in partials:
                    rendered_spec = self._render_rule_template(spec, values)
                    for index, value in enumerate(self._variable_values(context, partial_rule, rendered_spec)):
                        text = clean_text(value)
                        if not text:
                            continue
                        rendered_values = {**values, **self._template_values_for(variable_name, text, index)}
                        next_partials.append((self._render_rule_template(partial_rule, rendered_values), rendered_values))
                partials = next_partials
            if not partials:
                # 动态发现不到变量值时跳过该条规则，避免把占位符原样输出成字段。
                continue
            for rendered, _ in partials:
                rendered.pop("towers", None)
                rendered.pop("variables", None)
                expanded.append(rendered)
        return expanded

    def _tower_values(self, context: "ResultContext" | None, rule: dict[str, Any], towers: Any) -> list[Any]:
        """解析旧版 ``towers`` 快捷配置。"""
        if isinstance(towers, dict):
            return self._discover_towers(context, rule, towers) if context is not None else []
        if isinstance(towers, str):
            return [towers]
        return list(towers or [])

    def _variable_values(self, context: "ResultContext" | None, rule: dict[str, Any], spec: Any) -> list[str]:
        """解析 ``variables`` 中的静态或动态变量值。"""
        if isinstance(spec, list):
            return [clean_text(value) for value in spec if clean_text(value)]
        if isinstance(spec, str):
            return [clean_text(spec)] if clean_text(spec) else []
        if not isinstance(spec, dict):
            return []
        if "values" in spec:
            return [clean_text(value) for value in spec.get("values") or [] if clean_text(value)]
        source = spec.get("from_table")
        if source and context is not None:
            return self._discover_values_from_table(context, rule, source)
        return []

    def _discover_values_from_table(self, context: "ResultContext", rule: dict[str, Any], source: dict[str, Any]) -> list[str]:
        """按配置从来源表列或表内容中发现通用变量值。"""
        source_rule = {
            "section": source.get("section") or rule.get("section"),
            "source_table": source.get("source_table") or source,
        }
        table_result = self._locate_table(context, source_rule)
        if table_result.get("status") == _NIL_STATUS:
            return []
        table = table_result["table"]
        frame = self._table_frame(table)
        values: list[Any] = []
        column_spec = source.get("column")
        if column_spec:
            column_result = self._select_column_frame(frame, column_spec)
            if column_result.get("status") != _NIL_STATUS:
                values = frame.iloc[:, column_result["columnIndex"]].tolist()
        if not values:
            values = frame.to_numpy().flatten().tolist()
        pattern = source.get("value_pattern")
        excludes = [str(item) for item in source.get("exclude_patterns") or []]
        discovered: list[str] = []
        for value in values:
            text = clean_text(value)
            if not text:
                continue
            candidates = [match.group(0) for match in re.finditer(str(pattern), text, flags=re.IGNORECASE)] if pattern else [text]
            for candidate in candidates:
                candidate = clean_text(candidate)
                if not candidate:
                    continue
                if excludes and any(safe_search(pattern, candidate) for pattern in excludes):
                    continue
                if candidate not in discovered:
                    discovered.append(candidate)
        limit = source.get("limit")
        if limit is not None:
            discovered = discovered[: int(limit)]
        return discovered

    @staticmethod
    def _template_values_for(name: str, value: Any, index: int) -> dict[str, str]:
        """生成单个模板变量的替换字典。"""
        text = clean_text(value)
        clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "", text)
        return {
            name: text,
            f"{name}_clean": clean,
            f"{name}_index": str(index),
            f"{name}_ordinal": str(index + 1),
        }

    def _discover_towers(self, context: "ResultContext" | None, rule: dict[str, Any], spec: dict[str, Any]) -> list[str]:
        """按配置从 result 中的表格动态发现测风塔号。"""
        if context is None:
            return []
        source = spec.get("from_table") or spec
        source_rule = {
            "section": source.get("section") or rule.get("section"),
            "source_table": source.get("source_table") or source,
        }
        table_result = self._locate_table(context, source_rule)
        if table_result.get("status") == _NIL_STATUS:
            # 指定来源表（如“测风塔基本情况表”）没找到时，回退到扫描整个章节里的塔号，
            # 兼容不同报告把塔号放在不同表、或表题命名不一致的情况。
            return self._discover_towers_from_section(context, source)
        table = table_result["table"]
        frame = self._table_frame(table)
        column_spec = source.get("column") or {"aliases": ["测风塔", "测风塔编号", "塔号"]}
        column_result = self._select_column_frame(frame, column_spec)
        values: list[Any] = []
        if column_result.get("status") == _NIL_STATUS:
            scan_rows = min(len(frame.index), int(source.get("scan_rows", len(frame.index) or 0)))
            for row_index in range(scan_rows):
                values.extend(frame.iloc[row_index].tolist())
        else:
            values = frame.iloc[:, column_result["columnIndex"]].tolist()
        values.extend(list(table.columns))
        pattern = str(source.get("value_pattern") or r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]")
        excludes = [str(item) for item in source.get("exclude_patterns") or []]
        towers: list[str] = []
        for value in values:
            text = clean_text(value).replace("＃", "#")
            if not text:
                continue
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                tower = self._normalize_tower_code(match.group(0))
                if not tower:
                    continue
                if excludes and any(safe_search(pattern, tower) for pattern in excludes):
                    continue
                if tower not in towers:
                    towers.append(tower)
        limit = source.get("limit")
        if limit is not None:
            towers = towers[: int(limit)]
        return towers

    def _discover_towers_from_section(self, context: "ResultContext", source: dict[str, Any]) -> list[str]:
        """扫描目标章节全部表格，按 ``value_pattern`` 汇总塔号。

        这是 ``from_table`` 定位失败时的兜底：不同报告的测风塔编号可能散落在
        “基本情况表”以外的风能参数、风切变、湍流等表里，这里按同一正则统一发现。
        """
        section_name = source.get("section")
        pattern = str(source.get("value_pattern") or r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]")
        excludes = [str(item) for item in source.get("exclude_patterns") or []]
        towers: list[str] = []
        for table in context.tables(section_name):
            frame = self._table_frame(table)
            values = [*list(table.columns), *list(frame.to_numpy().flatten())]
            for value in values:
                text = clean_text(value).replace("＃", "#")
                if not text:
                    continue
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    tower = self._normalize_tower_code(match.group(0))
                    if not tower:
                        continue
                    if excludes and any(safe_search(pattern, tower) for pattern in excludes):
                        continue
                    if tower not in towers:
                        towers.append(tower)
        limit = source.get("limit")
        if limit is not None:
            towers = towers[: int(limit)]
        return towers

    @staticmethod
    def _normalize_tower_code(value: Any) -> str:
        """把 ``0821＃``、``0821 #`` 等形式统一成 ``0821#``。"""
        text = clean_text(value).replace("＃", "#")
        match = re.search(r"([A-Za-z0-9][A-Za-z0-9_-]{0,19})\s*#", text)
        if match:
            return f"{match.group(1)}#"
        return text

    @staticmethod
    def _render_rule_template(rule: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
        """递归渲染规则模板里的 ``{tower}`` / ``{tower_clean}`` 占位符。"""

        def render(value: Any) -> Any:
            if isinstance(value, str):
                text = value
                for key, replacement in values.items():
                    text = text.replace("{" + key + "}", replacement)
                return text
            if isinstance(value, list):
                return [render(item) for item in value]
            if isinstance(value, dict):
                return {key: render(item) for key, item in value.items()}
            return value

        return render(copy.deepcopy(rule))
