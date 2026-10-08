"""基于 result.json 的表内字段二次抽取。

这个模块是主解析链路之外的旁路增强层：它只读取已经导出的 result 结构，
按独立配置抽取表内字段、投影子表或复制原表，不修改原有字段/原表抽取逻辑。
"""

from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from parser_engine.core.config_loader import ConfigLoader


__all__ = [
    "TableValueResolver",
    "compact_table_value_result",
    "default_table_value_details_path",
    "enhance_result_file",
    "final_result_with_table_values",
    "table_value_details",
]

# ``table_values`` 原先是一个包，部分业务代码直接导入
# ``parser_engine.tables.table_values.resolver``。扁平化后保留同名模块别名，
# 让旧路径与新路径指向同一份实现。
__path__ = []  # type: ignore[var-annotated]
sys.modules.setdefault(f"{__name__}.resolver", sys.modules[__name__])


_NIL_STATUS = "NIL"


@dataclass
class NormalizedTable:
    """二次抽取使用的标准化表对象。"""

    section_name: str
    table: dict[str, Any]
    columns: list[str]
    data: list[list[Any]]

    @property
    def key(self) -> str:
        """返回 result 中的表 key。"""
        return str(self.table.get("key") or "")

    @property
    def name(self) -> str:
        """返回 result 中的表名。"""
        return clean_text(self.table.get("name") or "")


class TableValueResolver:
    """从 result.json 已有表格中执行配置化二次抽取。

    支持的操作包括：
    - ``cell``：按行标签和列名取单元格。
    - ``max_row_label``：指定数值列取最大值，并返回同一行的标签列。
    - ``table_projection``：按列名投影一个子表。
    - ``filter_table_projection``：按设备/项目别名筛选行，再投影固定列生成子表。
    - ``copy_table``：把已有表复制到二次抽取结果中，作为显式需求输出。
    - ``sum_fields``：从已有字段中按 fieldCode 求和，生成派生字段。
    - ``cell_items``：复用同一张表和目标列，按 items 批量生成多个字段。
    - ``cell_series``：同一目标行按多列批量抽取，返回列名到值的映射。
    - ``cell_ratio``：从两组表内单元格取数相除，生成比率字段。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """初始化二次抽取器。"""
        self.config = config or {}
        self.rules = list(self.config.get("rules") or [])
        self._table_frame_cache: dict[int, Any] = {}

    @classmethod
    def from_config_file(cls, config_path: str | Path = "configs/table_field_extractors.yaml") -> "TableValueResolver":
        """从独立 YAML 配置创建二次抽取器。"""
        path = Path(config_path)
        if path.is_absolute():
            config_root = path.parent
            relative_path = path.name
        else:
            config_root = path.parent if str(path.parent) not in {"", "."} else "configs"
            relative_path = path.name
        return cls(ConfigLoader(config_root).load_yaml(relative_path))

    def enhance_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """返回带二次抽取内部结果的增强版 result。

        Args:
            result: 主解析链路导出的 result JSON 对象。

        Returns:
            dict[str, Any]: 深拷贝后的增强结果，原对象不会被修改。
        """
        enhanced = copy.deepcopy(result)
        context = ResultContext(enhanced)
        for rule in self._expand_rules(self.rules, context):
            operation = str(rule.get("operation") or "cell")
            if operation == "cell":
                context.add_table_field(self._extract_cell(context, rule))
            elif operation == "cell_items":
                for field in self._extract_cell_items(context, rule):
                    context.add_table_field(field)
            elif operation == "max_row_label":
                context.add_table_field(self._extract_max_row_label(context, rule))
            elif operation == "sector_max":
                context.add_table_field(self._extract_sector_max(context, rule))
            elif operation == "column_values":
                context.add_table_field(self._extract_column_values(context, rule))
            elif operation == "cell_series":
                context.add_table_field(self._extract_cell_series(context, rule))
            elif operation == "cell_ratio":
                context.add_table_field(self._extract_cell_ratio(context, rule))
            elif operation == "sum_fields":
                context.add_table_field(self._extract_sum_fields(context, rule))
            elif operation == "table_projection":
                context.add_derived_table(self._extract_table_projection(context, rule))
            elif operation == "filter_table_projection":
                context.add_derived_table(self._extract_filter_table_projection(context, rule))
            elif operation == "copy_table":
                context.add_derived_table(self._extract_copy_table(context, rule))
            else:
                context.add_table_field(nil_field(rule, "unsupported_operation", f"不支持的二次抽取操作：{operation}"))
        enhanced.setdefault("tableValueExtraction", {})["summary"] = context.summary()
        enhanced.setdefault("tableValueExtraction", {})["configVersion"] = self.config.get("version")
        return enhanced

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


class ResultContext:
    """增强过程中的 result 索引和写入适配器。"""

    def __init__(self, result: dict[str, Any]):
        """构建章节、表和字段索引。"""
        self.result = result
        self.section_index = {section.get("name"): section for section in result.get("sections") or []}
        self.table_index: list[NormalizedTable] = []
        self.field_index: dict[str, dict[str, Any]] = {}
        for section in result.get("sections") or []:
            section_name = str(section.get("name") or "")
            for table in section.get("tables") or []:
                self.table_index.append(normalize_table(section_name, table))
            for field in section.get("fields") or []:
                field_code = field.get("fieldCode") or field.get("field_code")
                if field_code:
                    self.field_index[str(field_code)] = field

    def tables(self, section_name: str | None = None) -> list[NormalizedTable]:
        """返回指定章节或全部章节的表。"""
        if not section_name:
            return list(self.table_index)
        return [table for table in self.table_index if table.section_name == section_name]

    def add_table_field(self, field: dict[str, Any]) -> None:
        """把二次抽取字段追加到所属章节。"""
        section = self._section_for(field.get("section"))
        section.setdefault("tableFields", []).append(field)

    def add_derived_table(self, table: dict[str, Any]) -> None:
        """把二次抽取表追加到所属章节。"""
        section = self._section_for(table.get("section"))
        section.setdefault("derivedTables", []).append(table)

    def summary(self) -> dict[str, Any]:
        """生成二次抽取摘要。"""
        fields = [field for section in self.result.get("sections") or [] for field in section.get("tableFields") or []]
        tables = [table for section in self.result.get("sections") or [] for table in section.get("derivedTables") or []]
        return {
            "fieldCount": len(fields),
            "fieldOkCount": sum(1 for field in fields if field.get("status") == "OK"),
            "fieldNilCount": sum(1 for field in fields if field.get("status") == _NIL_STATUS),
            "derivedTableCount": len(tables),
            "derivedTableOkCount": sum(1 for table in tables if table.get("status") == "OK"),
            "derivedTableNilCount": sum(1 for table in tables if table.get("status") == _NIL_STATUS),
        }

    def _section_for(self, section_name: Any) -> dict[str, Any]:
        """获取或创建增强结果所属章节。"""
        name = str(section_name or "二次抽取")
        section = self.section_index.get(name)
        if section is None:
            section = {"name": name, "fields": [], "tables": [], "tableFields": [], "derivedTables": []}
            self.result.setdefault("sections", []).append(section)
            self.section_index[name] = section
        return section


def enhance_result_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path = "configs/table_field_extractors.yaml",
    details_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取 result.json，写出二次抽取结果和过程明细。"""
    input_file = Path(input_path)
    result = json.loads(input_file.read_text(encoding="utf-8"))
    enhanced = TableValueResolver.from_config_file(config_path).enhance_result(result)
    if output_path is None:
        output_path = input_file
    if details_output_path is None:
        details_output_path = default_table_value_details_path(input_file)
    Path(output_path).write_text(json.dumps(json_safe(final_result_with_table_values(enhanced)), ensure_ascii=False, indent=2), encoding="utf-8")
    write_table_value_details(details_output_path, table_value_details(enhanced))
    return enhanced


def default_table_value_details_path(input_file: str | Path) -> Path:
    """根据主 result 路径生成 details 路径。"""
    path = Path(input_file)
    base = _base_result_stem(path)
    return path.with_name(f"{base}_details.json")


def _base_result_stem(path: Path) -> str:
    """剥离 result/enhanced_result 后缀，避免重复生成 enhanced_enhanced。"""
    stem = path.stem
    if stem.endswith("_enhanced_result"):
        return stem[: -len("_enhanced_result")]
    if stem.endswith("_result"):
        return stem[: -len("_result")]
    return stem


def compact_table_value_result(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成面向展示的二次抽取结果 JSON。

    输出只保留业务结果：字段使用和主解析 ``fields`` 一致的
    ``fieldCode/name/value/unit`` 结构；整表类结果只保留对原表的引用，
    完整行列命中、NIL、trace 和来源细节写入 details JSON。
    """
    results: list[dict[str, Any]] = []
    for section in enhanced.get("sections") or []:
        fields = [_compact_table_field(field) for field in section.get("tableFields") or [] if field.get("status") == "OK"]
        fields = [field for field in fields if field]
        tables = [_compact_derived_table(table) for table in section.get("derivedTables") or [] if table.get("status") == "OK"]
        tables = [table for table in tables if table]
        if not fields and not tables:
            continue
        item: dict[str, Any] = {"name": section.get("name"), "fields": fields}
        if tables:
            item["tables"] = tables
        results.append(item)
    return {
        "filePath": enhanced.get("filePath"),
        "results": results,
    }


def final_result_with_table_values(enhanced: dict[str, Any]) -> dict[str, Any]:
    """Build one final result JSON by merging secondary values into sections."""
    final = copy.deepcopy(enhanced)
    final.pop("tableValueExtraction", None)
    for section in final.get("sections") or []:
        table_fields = section.pop("tableFields", []) or []
        derived_tables = section.pop("derivedTables", []) or []
        _merge_section_fields(section, table_fields)
        _merge_section_tables(section, derived_tables)
    return final


def table_value_details(enhanced: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取过程明细 JSON。"""
    sections: list[dict[str, Any]] = []
    for section in enhanced.get("sections") or []:
        table_fields = list(section.get("tableFields") or [])
        derived_tables = list(section.get("derivedTables") or [])
        if not table_fields and not derived_tables:
            continue
        sections.append(
            {
                "name": section.get("name"),
                "tableFields": table_fields,
                "derivedTables": derived_tables,
            }
        )
    extraction = enhanced.get("tableValueExtraction") or {}
    return {
        "filePath": enhanced.get("filePath"),
        "summary": extraction.get("summary") or {},
        "configVersion": extraction.get("configVersion"),
        "sections": sections,
    }


def write_table_value_details(path: str | Path, details: dict[str, Any]) -> None:
    """把二次抽取过程写入 details JSON；若主 details 已存在则追加字段。"""
    details_path = Path(path)
    payload: dict[str, Any]
    if details_path.exists():
        try:
            payload = json.loads(details_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    if not payload.get("filePath") and details.get("filePath"):
        payload["filePath"] = details.get("filePath")
    payload["tableValueExtraction"] = details
    details_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalar values into standard JSON types."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, str | bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if value == value and value not in {float("inf"), float("-inf")} else None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return json_safe(tolist())
        except (TypeError, ValueError):
            pass
    return str(value)


_SECONDARY_NO_OVERWRITE_WHEN_PRESENT = {
    "electricalPrimaryTransformerSpec",
    "electricalPrimarySvgSpec",
    "electricalPrimarySvgUnit",
    "electricalPrimarySvgQuantity",
    "electricalPrimaryGroundingTransformerSetSpec",
    "electricalPrimaryExternalPowerTransformerSpec",
}


def _merge_section_fields(section: dict[str, Any], table_fields: list[dict[str, Any]]) -> None:
    fields = list(section.get("fields") or [])
    index = {field.get("fieldCode"): position for position, field in enumerate(fields) if isinstance(field, dict) and field.get("fieldCode")}
    for table_field in table_fields:
        if table_field.get("status") != "OK":
            continue
        field_code = table_field.get("fieldCode")
        if not field_code:
            continue
        if field_code in index:
            existing = fields[index[field_code]]
            if field_code in _SECONDARY_NO_OVERWRITE_WHEN_PRESENT and _has_present_value(existing.get("value")) and not table_field.get("valueFiltered"):
                continue
            compact = _compact_table_field(table_field, fallback_name=fields[index[field_code]].get("name"))
            fields[index[field_code]] = compact
        else:
            compact = _compact_table_field(table_field)
            index[field_code] = len(fields)
            fields.append(compact)
    section["fields"] = fields


def _has_present_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _merge_section_tables(section: dict[str, Any], derived_tables: list[dict[str, Any]]) -> None:
    tables = list(section.get("tables") or [])
    index = {
        table.get("tableCode") or table.get("key"): position
        for position, table in enumerate(tables)
        if isinstance(table, dict) and (table.get("tableCode") or table.get("key"))
    }
    for derived_table in derived_tables:
        if derived_table.get("status") != "OK":
            continue
        table_code = derived_table.get("key")
        if not table_code:
            continue
        if table_code in index:
            compact = _compact_derived_table(derived_table, fallback_name=tables[index[table_code]].get("name"))
            tables[index[table_code]] = compact
        else:
            compact = _compact_derived_table(derived_table)
            index[table_code] = len(tables)
            tables.append(compact)
    section["tables"] = tables


def _compact_table_field(field: dict[str, Any], fallback_name: str | None = None) -> dict[str, Any]:
    """把二次字段转成和主解析 fields 一致的展示结构。"""
    field_code = field.get("fieldCode")
    if not field_code:
        return {}
    return {
        "fieldCode": field_code,
        "name": field.get("fieldName") or field.get("name") or fallback_name or field_code,
        "value": field.get("value"),
        "unit": field.get("unit"),
    }


def _compact_derived_table(table: dict[str, Any], fallback_name: str | None = None) -> dict[str, Any]:
    """把二次表结果转成对原表的轻量引用。"""
    table_code = table.get("key")
    if not table_code:
        return {}
    item: dict[str, Any] = {
        "key": table_code,
        "tableCode": table_code,
        "name": table.get("name") or fallback_name or table_code,
    }
    source = table.get("source") or {}
    if source:
        item["tableRef"] = {
            "section": source.get("section"),
            "tableKey": source.get("tableKey"),
            "tableName": source.get("tableName"),
        }
    item["columns"] = list(table.get("columns") or [])
    item["data"] = list(table.get("data") or [])
    return item


def normalize_table(section_name: str, table: dict[str, Any]) -> NormalizedTable:
    """把 result 表格归一为二次抽取内部结构。"""
    columns = [clean_text(column) for column in table.get("columns") or []]
    data = [list(row) if isinstance(row, list) else [row] for row in table.get("data") or []]
    if data and row_has_year_headers(data[0]):
        width = max(len(columns), len(data[0]))
        columns = [
            clean_text(data[0][index]) or (columns[index] if index < len(columns) else f"col_{index}")
            for index in range(width)
        ]
        data = data[1:]
    # 很多原表把真正表头放在第一行，columns 只是表名/col_x；这里仅在明显情况下提升表头。
    elif data and row_looks_like_header(data[0], columns):
        columns = [clean_text(cell) or f"col_{index}" for index, cell in enumerate(data[0])]
        data = data[1:]
    columns = infer_merged_year_columns(columns)
    return NormalizedTable(section_name=section_name, table=table, columns=columns, data=data)


def infer_merged_year_columns(columns: list[str]) -> list[str]:
    """把多级财务表里被合并表头占位的“运行期”推断为第1年。"""
    normalized = [normalize_label(column) for column in columns]
    if "第1年" in normalized:
        return columns
    for index, label in enumerate(normalized):
        if label != "运行期":
            continue
        later_labels = normalized[index + 1 :]
        if any(re.fullmatch(r"第?2年", item) for item in later_labels):
            result = list(columns)
            result[index] = "第1年"
            return result
    return columns


def row_has_year_headers(row: list[Any]) -> bool:
    """判断首行是否包含横向年份表头，并保留既有项目/合计等列名。"""
    labels = [normalize_label(cell) for cell in row]
    return sum(1 for label in labels if re.fullmatch(r"第?\d+年", label)) >= 2


def row_looks_like_header(row: list[Any], columns: list[str]) -> bool:
    """判断第一行是否更像真实表头。"""
    if not row:
        return False
    normalized_columns = [normalize_label(column) for column in columns]
    if normalized_columns and not all(column.startswith("col") or column in {""} for column in normalized_columns):
        # 当前 columns 已经有较明确的表头时，不轻易替换。
        meaningful = sum(1 for column in normalized_columns if column and not column.startswith("col"))
        if meaningful >= max(2, len(normalized_columns) // 2):
            return False
    row_text = [normalize_label(cell) for cell in row]
    header_hits = sum(1 for text in row_text if text in {"序号", "项目", "项目名称", "名称", "单位", "数量", "单价", "合计", "备注", "型号规格及技术数据", "型号及规格"})
    return header_hits >= 2


def select_row(table: NormalizedTable, spec: dict[str, Any]) -> dict[str, Any]:
    """按配置选择表格行。"""
    selector_type = spec.get("type") or "label"
    if selector_type == "index":
        index = int(spec.get("index", 0))
        base = str(spec.get("index_base") or "data_rows")
        row_index = index - 1 if base == "data_rows" and index > 0 else index
        if 0 <= row_index < len(table.data):
            return {"rowIndex": row_index, "row": table.data[row_index], "selector": "index"}
        return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"行号越界：{index}"}
    patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
    search_columns = column_indices_for_selector(table, spec.get("column") or spec.get("column_aliases"))
    matches: list[dict[str, Any]] = []
    for row_index, row in enumerate(table.data):
        cells = [value_at(row, index) for index in search_columns] if search_columns else row
        text = clean_text(" ".join(str(cell or "") for cell in cells))
        if not text:
            continue
        score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
        if score > 0:
            matches.append({"rowIndex": row_index, "row": row, "score": score, "text": text})
    if not matches:
        return {"status": _NIL_STATUS, "reason": "row_not_found", "message": "未找到匹配行。"}
    matches.sort(key=lambda item: item["score"], reverse=True)
    if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
        return {"status": _NIL_STATUS, "reason": "ambiguous_row", "message": "行选择命中多个同分候选。", "candidates": matches[:5]}
    return {**matches[0], "selector": "label"}

def select_row_occurrence(table: NormalizedTable, spec: dict[str, Any], occurrence: int) -> dict[str, Any]:
    """按匹配行出现次序选择表格行。

    用于连续表被合并后多次出现同一行标签的情况，比如风切变表的多个“综合值”行。
    occurrence 从 0 开始，命中不足时返回 NIL，不回落到随机行。
    """
    patterns = [str(pattern) for pattern in spec.get("patterns") or spec.get("aliases") or []]
    exclude_patterns = [str(pattern) for pattern in spec.get("exclude_patterns") or spec.get("exclude_aliases") or []]
    search_columns = column_indices_for_selector(table, spec.get("column") or spec.get("column_aliases"))
    matches: list[dict[str, Any]] = []
    for row_index, row in enumerate(table.data):
        cells = [value_at(row, index) for index in search_columns] if search_columns else row
        text = clean_text(" ".join(str(cell or "") for cell in cells))
        if not text:
            continue
        if exclude_patterns and row_match_score(text, exclude_patterns) > 0:
            continue
        score = row_match_score(text, patterns, exact=bool(spec.get("exact")))
        if score > 0:
            matches.append({"rowIndex": row_index, "row": row, "score": score, "text": text})
    matches.sort(key=lambda item: item["rowIndex"])
    min_occurrences = max(int(spec.get("min_occurrences") or 0), 0)
    if len(matches) < min_occurrences:
        return {
            "status": _NIL_STATUS,
            "reason": "row_not_found",
            "message": f"\u5339\u914d\u884c\u4e0d\u8db3 {min_occurrences} \u4e2a\uff0c\u5b9e\u9645\u627e\u5230 {len(matches)} \u4e2a\u3002",
            "candidates": matches[:10],
        }
    if occurrence < len(matches):
        return {**matches[occurrence], "selector": "label_occurrence", "occurrence": occurrence}
    if len(matches) == 1 and occurrence > 0:
        return {**matches[0], "selector": "label_occurrence_fallback", "occurrence": 0}
    return {"status": _NIL_STATUS, "reason": "row_not_found", "message": f"\u672a\u627e\u5230\u7b2c {occurrence + 1} \u4e2a\u5339\u914d\u884c\u3002", "candidates": matches[:10]}


def select_column(table: NormalizedTable, spec: dict[str, Any]) -> dict[str, Any]:
    """按配置选择表格列。"""
    if "index" in spec:
        index = int(spec.get("index"))
        if 0 <= index < len(table.columns):
            return {"columnIndex": index, "column": table.columns[index], "selector": "index"}
        return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"列号越界：{index}"}
    aliases = [str(alias) for alias in spec.get("aliases") or spec.get("patterns") or []]
    matches: list[dict[str, Any]] = []
    for index, column in enumerate(table.columns):
        score = column_match_score(column, aliases)
        if score > 0:
            matches.append({"columnIndex": index, "column": column, "score": score})
    if not matches:
        return {"status": _NIL_STATUS, "reason": "column_not_found", "message": f"未找到匹配列：{aliases}", "columns": table.columns}
    matches.sort(key=lambda item: item["score"], reverse=True)
    if len(matches) > 1 and matches[0]["score"] == matches[1]["score"] and not spec.get("allow_ambiguous"):
        return {"status": _NIL_STATUS, "reason": "ambiguous_column", "message": "列选择命中多个同分候选。", "candidates": matches[:5]}
    return {**matches[0], "selector": "label"}


def column_indices_for_selector(table: NormalizedTable, selector: Any) -> list[int]:
    """把行选择中的列范围配置转换成列索引。"""
    if selector is None:
        return []
    specs = selector if isinstance(selector, list) else [selector]
    indices: list[int] = []
    for item in specs:
        if isinstance(item, int):
            indices.append(item)
            continue
        result = select_column(table, {"aliases": [item]})
        if result.get("status") != _NIL_STATUS:
            indices.append(result["columnIndex"])
    return indices


def field_result(rule: dict[str, Any], value: Any, table: NormalizedTable, row: dict[str, Any], column: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取字段结果。"""
    include_patterns = rule.get("include_patterns") or []
    value = filter_included_value(value, include_patterns)
    parsed_value = normalize_value(value, str(rule.get("value_type") or "auto"))
    conversion = (rule.get("column") or {}).get("conversion", rule.get("conversion"))
    if conversion == "yuan_to_wan_yuan_by_header":
        column_name = clean_text(column.get("column"))
        if "万元" not in column_name and re.search(r"(?:^|[（(])元(?:[）)]|$)", column_name):
            number = parse_number(parsed_value)
            if number is not None:
                parsed_value = normalize_number(number / 10000)
    return {
        "fieldCode": rule.get("field_code"),
        "fieldName": rule.get("field_name") or rule.get("field_code"),
        "value": parsed_value,
        "unit": rule.get("unit"),
        "status": "OK",
        "section": rule.get("section"),
        "sourceKind": "table_cell",
        "operation": rule.get("operation") or "cell",
        "valueFiltered": bool(include_patterns),
        "confidence": 1.0,
        "source": {
            "section": table.section_name,
            "tableKey": table.key,
            "tableName": table.name,
            "rowIndex": row.get("rowIndex"),
            "rowText": clean_text(" ".join(str(cell or "") for cell in row.get("row") or [])),
            "columnIndex": column.get("columnIndex"),
            "column": column.get("column"),
            "rawValue": value,
        },
    }


def filter_included_value(value: Any, include_patterns: list[Any]) -> Any:
    """Keep only configured fragments from a merged text value."""
    if not include_patterns or not isinstance(value, str):
        return value
    parts: list[str] = []
    for pattern in include_patterns:
        match = re.search(str(pattern), value, flags=re.IGNORECASE)
        if match:
            parts.append(clean_text(match.group(0)))
    return "，".join(dict.fromkeys(parts)) if parts else value


def nil_field(rule: dict[str, Any], reason: str, message: str | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 NIL 字段结果，防止低置信乱取。"""
    return {
        "fieldCode": rule.get("field_code"),
        "fieldName": rule.get("field_name") or rule.get("field_code"),
        "value": None,
        "unit": rule.get("unit"),
        "status": _NIL_STATUS,
        "section": rule.get("section"),
        "sourceKind": "table_cell",
        "operation": rule.get("operation") or "cell",
        "nilReason": reason,
        "message": message,
        "trace": simplify_trace(trace or {}),
    }


def derived_table_result(rule: dict[str, Any], table: NormalizedTable, columns: list[str], rows: list[list[Any]], trace: dict[str, Any]) -> dict[str, Any]:
    """生成二次抽取表结果。"""
    return {
        "key": rule.get("table_code") or rule.get("field_code"),
        "name": rule.get("table_name") or rule.get("field_name") or rule.get("table_code"),
        "section": rule.get("section"),
        "status": "OK",
        "operation": rule.get("operation"),
        "sourceKind": "table_projection",
        "columns": columns,
        "data": rows,
        "source": {
            "section": table.section_name,
            "tableKey": table.key,
            "tableName": table.name,
        },
        "trace": trace,
    }


def nil_table(rule: dict[str, Any], reason: str, message: str | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 NIL 表结果。"""
    return {
        "key": rule.get("table_code") or rule.get("field_code"),
        "name": rule.get("table_name") or rule.get("field_name") or rule.get("table_code"),
        "section": rule.get("section"),
        "status": _NIL_STATUS,
        "operation": rule.get("operation"),
        "nilReason": reason,
        "message": message,
        "trace": simplify_trace(trace or {}),
    }


def row_match_score(text: str, patterns: list[str], *, exact: bool = False) -> int:
    """计算行文本对行选择规则的匹配分。

    完全相等（归一化后）得分最高，避免“90m”这类标签误命中更长文本里的子串。
    """
    normalized_text = normalize_label(text)
    best = 0
    for pattern in patterns:
        normalized_pattern = normalize_label(pattern)
        if not normalized_pattern:
            continue
        numeric_score = numeric_label_match_score(text, normalized_pattern)
        if numeric_score:
            best = max(best, numeric_score)
            continue
        if normalized_text == normalized_pattern:
            best = max(best, 120)
        elif safe_search(pattern, text):
            best = max(best, 100)
        elif not exact and len(normalized_pattern) >= 3 and normalized_pattern in normalized_text:
            best = max(best, 70)
    return best


def numeric_label_match_score(text: str, normalized_pattern: str) -> int:
    """处理 90/90m 这类数字标签，避免命中 0.096 里的字符。"""
    match = re.fullmatch(r"(?P<number>\d+(?:\.\d+)?)(?:m)?", normalized_pattern)
    if not match:
        return 0
    number = re.escape(match.group("number"))
    normalized_text = clean_text(text).lower().replace("米", "m")
    if re.search(rf"(?<![\d.]){number}\s*m?(?![\d.])", normalized_text):
        return 95
    return 0


def column_match_score(column: str, aliases: list[str]) -> int:
    """计算列名对列选择规则的匹配分。

    完全相等（归一化后）得分最高，避免“测风塔”误命中“测风塔配置(m)”这类包含关系。
    """
    normalized_column = normalize_label(column)
    best = 0
    for alias in aliases:
        normalized_alias = normalize_label(alias)
        if not normalized_alias:
            continue
        if normalized_column == normalized_alias:
            best = max(best, 120)
        elif safe_search(alias, column):
            best = max(best, 100)
        elif normalized_alias in normalized_column or normalized_column in normalized_alias:
            best = max(best, 75)
    return best


def clean_text(value: Any) -> str:
    """清理空白和控制字符。"""
    text = "" if value is None else str(value)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return "" if is_placeholder_text(text) else text


def is_placeholder_text(text: str) -> bool:
    """识别表格里表示空值的占位符。"""
    compact = re.sub(r"\s+", "", text)
    return compact in {"-", "--", "—", "——", "/", "\\"}


def safe_search(pattern: str, text: str) -> bool:
    """执行正则匹配，配置不是合法正则时按普通文本处理。"""
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern in text


def extract_value_by_pattern(value: Any, rule: dict[str, Any]) -> Any:
    """按规则从单元格文本中截取目标片段，可组合多个捕获组。"""
    patterns = rule.get("value_patterns") or rule.get("value_pattern")
    if not patterns or not isinstance(value, str):
        return value
    pattern_list = patterns if isinstance(patterns, list) else [patterns]
    for pattern in pattern_list:
        try:
            match = re.search(str(pattern), value, flags=re.IGNORECASE)
        except re.error:
            match = None
        if not match:
            continue
        groups = rule.get("value_groups")
        if groups:
            parts = [clean_text(match.group(int(group))) for group in groups if match.group(int(group)) is not None]
            return str(rule.get("value_join") or "").join(parts)
        if rule.get("value_group") is not None:
            return clean_text(match.group(int(rule.get("value_group"))))
        captured = next((group for group in match.groups() if group is not None), None)
        return clean_text(captured if captured is not None else match.group(0))
    return None


def validate_cell_value(value: Any, value_type: str) -> dict[str, Any]:
    """在输出 OK 前校验单元格值，避免空值或坏数字被当成已抽取。"""
    if value is None or clean_text(value) == "":
        return {"status": _NIL_STATUS, "reason": "value_empty", "message": "目标单元格为空。"}
    if value_type == "number" and parse_number(value) is None:
        return {"status": _NIL_STATUS, "reason": "value_parse_failed", "message": "目标单元格不能解析为数值。"}
    return {"status": "OK"}


def normalize_label(value: Any) -> str:
    """归一化表头、行名，用于宽松匹配。"""
    text = clean_text(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("＃", "#").replace("－", "-").replace("×", "x")
    text = text.replace("m³", "m3").replace("㎡", "m2").replace("²", "2")
    return re.sub(r"[^0-9a-zA-Z#%\u4e00-\u9fa5]+", "", text)


def value_at(row: list[Any], index: int | None) -> Any:
    """安全读取单元格值。"""
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def normalize_value(value: Any, value_type: str) -> Any:
    """按配置转换抽取值。"""
    if value_type in {"number", "auto"}:
        number = parse_number(value)
        if number is not None:
            return normalize_number(number)
    return value


def apply_value_conversion(value: Any, conversion: Any) -> Any:
    """按规则声明做轻量单位换算。"""
    if not conversion:
        return value
    conversion_name = str(conversion)
    if conversion_name == "wan_kwh_to_mwh":
        number = parse_number(value)
        if number is None:
            return value
        return normalize_number(number * 10)
    return value


def parse_number(value: Any) -> float | None:
    """从单元格文本中解析数值。"""
    if isinstance(value, int | float):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def parse_metric_number(value: Any) -> float | None:
    """\u4e25\u683c\u89e3\u6790\u6307\u6807\u6570\u503c\uff0c\u907f\u514d\u628a\u5854\u53f7\u6216\u8868\u5934\u7f16\u53f7\u5f53\u6210\u6570\u636e\u3002"""
    if isinstance(value, int | float):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text or "#" in text or "\uff03" in text:
        return None
    normalized = text.replace("%", "").strip()
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
        return None
    return float(normalized)


def normalize_number(value: float) -> int | float:
    """把整数型浮点转回 int。"""
    return int(value) if float(value).is_integer() else value


def first_alias(spec: dict[str, Any]) -> str:
    """返回列配置中的首个别名。"""
    aliases = spec.get("aliases") or spec.get("patterns") or []
    return str(aliases[0]) if aliases else str(spec.get("name") or "")


def table_summaries(tables: list[NormalizedTable]) -> list[dict[str, Any]]:
    """生成候选表摘要，便于 NIL 审计。"""
    return [{"section": table.section_name, "key": table.key, "name": table.name, "columns": table.columns[:8]} for table in tables[:20]]


def simplify_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """裁剪 NIL trace，避免把整张表写进错误信息。"""
    simplified: dict[str, Any] = {}
    for key, value in trace.items():
        if key == "table" and isinstance(value, NormalizedTable):
            simplified[key] = {"section": value.section_name, "key": value.key, "name": value.name, "columns": value.columns[:12]}
        elif key in {"candidates", "columns", "missing", "sources", "matchMethod", "confidence", "keyTable", "expectedPatterns", "requiredColumns"}:
            simplified[key] = value
    return simplified
