"""Wind tower, direction, turbulence, density and resource extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import FieldEvidence, ParsedField


class WindResourceRulesMixin:
    def _build_resource_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details = {
            "windResourceTowerBasic": [],
            "windResourceShearStatistics": [],
            "windResourceSpeedPowerStatistics": [],
            "windResourceSectorDistribution": [],
            "windResourceTurbulenceComparison": [],
            "windResourceCombined": [],
        }
        resource_tables = self._original_tables_for_spec(ast, {"key_prefix": "resourceOriginalTable"})
        for table in resource_tables:
            caption = self._clean_table_caption_title(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            if not caption:
                continue
            key = self._resource_table_key(caption)
            if key is None:
                continue
            rows = self._raw_rows_from_table(table)
            if not rows:
                continue
            details[key] = rows
        details["windResourceCombined"] = self._wind_resource_combined_rows(ast)
        return details

    def _wind_resource_combined_rows(self, ast: DocumentAST) -> list[dict[str, Any]]:
        tower_code_sources = self._resource_tower_code_sources(ast)
        wind_farm_density_by_tower = self._wind_farm_air_density_by_tower_from_resource_text(ast)
        density_by_tower = self._air_density_by_tower_from_resource_text(ast)
        height_density_by_tower = self._height_air_density_by_tower_from_resource_text(ast)
        table_density_by_tower = self._air_density_by_tower_from_resource_tables(ast)
        if table_density_by_tower:
            density_by_tower = {**density_by_tower, **table_density_by_tower}
        direction_by_tower = self._wind_direction_by_tower_from_resource_text(ast)
        table_direction_by_tower = self._wind_direction_by_tower_from_resource_tables(ast)
        if table_direction_by_tower:
            direction_by_tower = {**direction_by_tower, **table_direction_by_tower}
        use_by_tower = self._generation_use_by_tower_from_resource_text(ast)
        base_tower_codes = self._resource_tower_codes(ast)
        text_tower_codes = self._resource_tower_codes_from_text(ast)
        summary_text_tower_codes = self._resource_summary_explicit_tower_codes(ast, text_tower_codes)
        candidate_tower_codes = self._merge_tower_codes(base_tower_codes, summary_text_tower_codes, list(wind_farm_density_by_tower), list(density_by_tower), list(direction_by_tower), list(use_by_tower))
        summary_by_tower = self._resource_summary_by_tower_from_text(ast, candidate_tower_codes)
        table_summary_by_tower = self._resource_summary_by_tower_from_tables(ast, candidate_tower_codes)
        if table_summary_by_tower:
            summary_by_tower = self._merge_resource_summary_by_tower(summary_by_tower, table_summary_by_tower)
        summary_tower_codes = self._resource_summary_tower_codes(summary_by_tower, candidate_tower_codes)
        preferred_tower_codes = self._resource_preferred_tower_codes_from_text(ast, candidate_tower_codes)
        if summary_tower_codes:
            tower_codes = summary_tower_codes
            summary_by_tower = self._merge_resource_summary_by_tower(
                self._resource_summary_by_tower_from_text(ast, tower_codes),
                self._resource_summary_by_tower_from_tables(ast, tower_codes),
            )
        elif preferred_tower_codes:
            tower_codes = preferred_tower_codes
            summary_by_tower = self._merge_resource_summary_by_tower(
                self._resource_summary_by_tower_from_text(ast, tower_codes),
                self._resource_summary_by_tower_from_tables(ast, tower_codes),
            )
        elif base_tower_codes:
            tower_codes = base_tower_codes
        else:
            tower_codes = self._merge_tower_codes(text_tower_codes, list(density_by_tower), list(direction_by_tower), list(use_by_tower))
            summary_by_tower = self._merge_resource_summary_by_tower(
                self._resource_summary_by_tower_from_text(ast, tower_codes),
                self._resource_summary_by_tower_from_tables(ast, tower_codes),
            )
        summary_tower_code_set = set(summary_tower_codes)
        rows: list[dict[str, Any]] = []
        for code in tower_codes:
            summary = summary_by_tower.get(code, {})
            directions = {**direction_by_tower.get(code, {}), **summary.get("directions", {})}
            generation_use_default = "是" if not use_by_tower or code in summary_tower_code_set else "否"
            row = {
                "\u6d4b\u98ce\u5854\u7f16\u53f7": code,
                "\u8be5\u98ce\u7535\u573a\u7684\u7a7a\u6c14\u5bc6\u5ea6": self._resource_value(wind_farm_density_by_tower.get(code), "---"),
                "\u9ad8\u5ea6\u5bf9\u5e94\u7684\u7a7a\u6c14\u5bc6\u5ea6": self._resource_value(density_by_tower.get(code), self._resource_value(summary.get("airDensity"), "---")),
                "10m\u9ad8\u5ea6\u7a7a\u6c14\u5bc6\u5ea6": self._resource_value((height_density_by_tower.get(code) or {}).get("10m"), "---"),
                "160m\u9ad8\u5ea6\u7a7a\u6c14\u5bc6\u5ea6": self._resource_value((height_density_by_tower.get(code) or {}).get("160m"), "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u901fm/s": self._resource_value(summary.get("windSpeed"), "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u529f\u7387\u5bc6\u5ea6W/m\u00b2": self._resource_value(summary.get("powerDensity"), "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u5411": directions.get("mainWindDirection", "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u5411": directions.get("secondaryWindDirection", "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u80fd\u65b9\u5411": directions.get("mainWindEnergyDirection", "---"),
                "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u80fd\u65b9\u5411": directions.get("secondaryWindEnergyDirection", "---"),
                "\u6700\u5927\u9ad8\u5ea6\u5904\u4ee3\u8868\u6027\u6e4d\u6d41\u5f3a\u5ea6": self._resource_value(summary.get("turbulence"), "---"),
                "\u7efc\u5408\u98ce\u5207\u53d8": self._resource_value(summary.get("shear"), "---"),
                "\u53d1\u7535\u91cf\u8ba1\u7b97\u662f\u5426\u4f7f\u7528": self._resource_value(use_by_tower.get(code), generation_use_default),
                "_hubHeight": self._resource_value(summary.get("height"), None),
                "_turbulenceHeight": self._resource_value(summary.get("turbulenceHeight"), None),
                "_heightAirDensities": height_density_by_tower.get(code) or {},
            }
            row_sources: dict[str, Any] = {}
            if code in tower_code_sources:
                row_sources["\u6d4b\u98ce\u5854\u7f16\u53f7"] = tower_code_sources[code]
            wind_farm_density_source = self._resource_source(wind_farm_density_by_tower.get(code))
            if wind_farm_density_source:
                row_sources["\u8be5\u98ce\u7535\u573a\u7684\u7a7a\u6c14\u5bc6\u5ea6"] = wind_farm_density_source
            density_source = self._resource_source(density_by_tower.get(code))
            if density_source:
                row_sources["\u9ad8\u5ea6\u5bf9\u5e94\u7684\u7a7a\u6c14\u5bc6\u5ea6"] = density_source
            density_10m_source = self._resource_source((height_density_by_tower.get(code) or {}).get("10m"))
            if density_10m_source:
                row_sources["10m\u9ad8\u5ea6\u7a7a\u6c14\u5bc6\u5ea6"] = density_10m_source
            density_160m_source = self._resource_source((height_density_by_tower.get(code) or {}).get("160m"))
            if density_160m_source:
                row_sources["160m\u9ad8\u5ea6\u7a7a\u6c14\u5bc6\u5ea6"] = density_160m_source
            summary_sources = summary.get("_cellSources")
            if isinstance(summary_sources, dict):
                row_sources.update(summary_sources)
            cell_sources = directions.get("_cellSources") if isinstance(directions, dict) else None
            if isinstance(cell_sources, dict):
                row_sources.update(cell_sources)
            use_source = self._resource_source(use_by_tower.get(code))
            if use_source:
                row_sources["\u53d1\u7535\u91cf\u8ba1\u7b97\u662f\u5426\u4f7f\u7528"] = use_source
            elif use_by_tower and tower_code_sources.get(code):
                row_sources["\u53d1\u7535\u91cf\u8ba1\u7b97\u662f\u5426\u4f7f\u7528"] = tower_code_sources[code]
            if row_sources:
                row["_cellSources"] = row_sources
            if tower_code_sources.get(code):
                row["_rowSource"] = tower_code_sources[code]
            rows.append(row)
        return rows

    def _resource_summary_tower_codes(self, summary_by_tower: dict[str, dict[str, Any]], tower_codes: list[str]) -> list[str]:
        result: list[str] = []
        for code in tower_codes:
            summary = summary_by_tower.get(code) or {}
            if any(summary.get(key) is not None for key in ("windSpeed", "powerDensity")):
                result.append(code)
        return result

    def _merge_resource_summary_by_tower(self, *groups: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for group in groups:
            for tower, values in (group or {}).items():
                current = merged.setdefault(tower, {"_cellSources": {}, "directions": {}})
                for key, value in values.items():
                    if key == "_cellSources" and isinstance(value, dict):
                        current.setdefault("_cellSources", {}).update(value)
                    elif key == "directions" and isinstance(value, dict):
                        current.setdefault("directions", {}).update({k: v for k, v in value.items() if k not in current.get("directions", {})})
                    elif key not in current or current.get(key) is None:
                        current[key] = value
        return merged

    def _resource_summary_by_tower_from_tables(self, ast: DocumentAST, tower_codes: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        known_codes = set(tower_codes)
        for table in self._resource_related_tables(ast):
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._table_text(table)
            combined = f"{caption}\n{table_text}"
            if "测风塔" not in combined:
                continue
            if "平均风速" in combined and "风功率" in combined:
                self._merge_resource_summary_by_tower_in_place(result, self._resource_speed_power_summary_from_table(table, known_codes))
            if "湍流" in combined and "高度" in combined:
                self._merge_resource_summary_by_tower_in_place(result, self._resource_turbulence_summary_from_table(table, known_codes))
        return result

    def _merge_resource_summary_by_tower_in_place(self, target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]) -> None:
        merged = self._merge_resource_summary_by_tower(target, source)
        target.clear()
        target.update(merged)

    def _resource_related_tables(self, ast: DocumentAST) -> list[DocumentTable]:
        tables: list[DocumentTable] = []
        seen: set[int] = set()
        for table in [*self._original_tables_for_spec(ast, {"key_prefix": "resourceOriginalTable"}), *ast.tables]:
            identity = id(table)
            if identity in seen:
                continue
            seen.add(identity)
            tables.append(table)
        return tables

    def _resource_speed_power_summary_from_table(self, table: DocumentTable, known_codes: set[str]) -> dict[str, dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return {}
        annual_column = self._resource_annual_average_column(matrix)
        if annual_column is None:
            return {}
        result: dict[str, dict[str, Any]] = {}
        current_tower: str | None = None
        table_height = self._resource_summary_height_from_text(table.caption or "")
        for row_index, row in enumerate(matrix):
            row_text = self._clean_text(" ".join(row))
            tower_candidates = self._tower_codes_in_text(row_text)
            tower_candidates = [code for code in tower_candidates if code and (not known_codes or code in known_codes)]
            if tower_candidates:
                current_tower = tower_candidates[0]
            if not current_tower:
                continue
            value = self._normalize_table_cell(row[annual_column] if annual_column < len(row) else "")
            if value is None:
                value = self._last_numeric_cell_value(row)
            if value is None:
                continue
            metric = self._resource_speed_power_metric_from_row(row)
            if metric is None:
                continue
            label = "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u901fm/s" if metric == "windSpeed" else "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u529f\u7387\u5bc6\u5ea6W/m\u00b2"
            current = result.setdefault(current_tower, {"_cellSources": {}, "directions": {}})
            current[metric] = value
            row_height = self._resource_summary_height_from_text(row_text)
            if current.get("height") is None and (row_height is not None or table_height is not None):
                current["height"] = row_height if row_height is not None else table_height
            current["_cellSources"][label] = self._table_cell_source(
                table,
                row_index,
                annual_column,
                "资源章节平均风速/风功率密度统计表年均列抽取。",
                resolver="wind_resource_speed_power_table",
            )
        return result

    def _resource_annual_average_column(self, matrix: list[list[str]]) -> int | None:
        for row in matrix[: min(len(matrix), 5)]:
            for index, cell in enumerate(row):
                text = self._clean_text(cell)
                if re.search(r"年\s*(?:均|平均)|平均", text) and "风速" not in text and "风功率" not in text:
                    return index
        return None

    def _resource_speed_power_metric_from_row(self, row: list[str]) -> str | None:
        row_text = self._clean_text(" ".join(row))
        if "风功率" in row_text:
            return "powerDensity"
        if "风速" in row_text:
            return "windSpeed"
        return None

    def _resource_turbulence_summary_from_table(self, table: DocumentTable, known_codes: set[str]) -> dict[str, dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return {}
        header_index, height_columns = self._resource_turbulence_height_columns(matrix)
        if not height_columns:
            return {}
        target_height, target_column = max(height_columns, key=lambda item: item[0])
        result: dict[str, dict[str, Any]] = {}
        for row_index, row in enumerate(matrix[header_index + 1 :], start=header_index + 1):
            row_text = self._clean_text(" ".join(row))
            tower_candidates = self._tower_codes_in_text(row_text)
            tower_candidates = [code for code in tower_candidates if code and (not known_codes or code in known_codes)]
            if not tower_candidates:
                continue
            value = self._normalize_table_cell(row[target_column] if target_column < len(row) else "")
            if value is None:
                continue
            tower = tower_candidates[0]
            current = result.setdefault(tower, {"_cellSources": {}, "directions": {}})
            current["turbulence"] = value
            current["turbulenceHeight"] = self._clean_number(target_height)
            current["_cellSources"]["\u6700\u5927\u9ad8\u5ea6\u5904\u4ee3\u8868\u6027\u6e4d\u6d41\u5f3a\u5ea6"] = self._table_cell_source(
                table,
                row_index,
                target_column,
                f"资源章节湍流强度比较表最高高度 {self._clean_number(target_height)}m 抽取。",
                resolver="wind_resource_turbulence_table",
            )
        return result

    def _resource_turbulence_height_columns(self, matrix: list[list[str]]) -> tuple[int, list[tuple[float, int]]]:
        for row_index, row in enumerate(matrix[: min(len(matrix), 6)]):
            columns: list[tuple[float, int]] = []
            for column_index, cell in enumerate(row):
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*m", self._clean_text(cell), flags=re.IGNORECASE)
                if match:
                    columns.append((float(match.group(1)), column_index))
            if columns:
                return row_index, columns
        return 0, []

    def _wind_resource_turbulence_intensity_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        rows: list[dict[str, Any]] = []
        for table in self._resource_related_tables(ast):
            extracted = self._wind_resource_turbulence_rows_from_table(ast, table)
            if extracted:
                rows.extend(extracted)
        if not rows:
            return None
        columns = ["测风塔编号", "高度", "平均湍流强度", "代表性湍流强度"]
        data = [[row.get(column) for column in columns] for row in rows]
        return {
            "key": "windResourceTurbulenceIntensity",
            "name": "湍流强度",
            "columns": columns,
            "data": data,
            "rows": rows,
        }

    def _wind_resource_turbulence_rows_from_table(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return []
        caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
        table_text = self._table_text(table)
        combined = f"{caption}\n{table_text}"
        if "湍流" not in combined or "高度" not in combined:
            return []
        header_index, columns = self._turbulence_intensity_columns(matrix)
        if columns.get("height") is None or (
            columns.get("average") is None and columns.get("representative") is None
        ):
            return []
        tower_from_caption = self._tower_code_from_text(caption)
        wind_speed_segment = self._turbulence_wind_speed_segment(combined)
        result: list[dict[str, Any]] = []
        for row_index, row in enumerate(matrix[header_index + 1 :], start=header_index + 1):
            tower = self._tower_code_from_text(" ".join(row)) or tower_from_caption
            if not tower:
                continue
            height_text = row[columns["height"]] if columns["height"] < len(row) else ""
            height = self._height_cell_value(height_text)
            if height is None:
                continue
            average = self._normalize_table_cell(row[columns["average"]]) if columns.get("average") is not None and columns["average"] < len(row) else None
            representative = self._normalize_table_cell(row[columns["representative"]]) if columns.get("representative") is not None and columns["representative"] < len(row) else None
            if average is None and representative is None:
                continue
            cell_sources: dict[str, Any] = {
                "高度": self._table_cell_source(
                    table,
                    row_index,
                    columns["height"],
                    "资源章节湍流强度表高度列抽取。",
                    resolver="wind_resource_turbulence_intensity_table",
                )
            }
            if average is not None:
                cell_sources["平均湍流强度"] = self._table_cell_source(
                    table,
                    row_index,
                    columns["average"],
                    "资源章节湍流强度表平均湍流强度列抽取。",
                    resolver="wind_resource_turbulence_intensity_table",
                )
            if representative is not None:
                cell_sources["代表性湍流强度"] = self._table_cell_source(
                    table,
                    row_index,
                    columns["representative"],
                    "资源章节湍流强度表代表性湍流强度列抽取。",
                    resolver="wind_resource_turbulence_intensity_table",
                )
            result.append(
                {
                    "测风塔编号": tower,
                    "高度": height,
                    "平均湍流强度": average,
                    "代表性湍流强度": representative,
                    "风速段": wind_speed_segment,
                    "_cellSources": cell_sources,
                }
            )
        return result

    def _turbulence_intensity_columns(self, matrix: list[list[str]]) -> tuple[int, dict[str, int]]:
        best: tuple[int, dict[str, int]] = (0, {})
        for row_index, row in enumerate(matrix[: min(len(matrix), 8)]):
            columns: dict[str, int] = {}
            for column_index, cell in enumerate(row):
                text = self._compact_text(cell)
                if not text:
                    continue
                if "高度" in text or "测风高度" in text:
                    columns.setdefault("height", column_index)
                if "平均" in text and "湍流" in text:
                    columns.setdefault("average", column_index)
                if ("代表" in text or "代表性" in text) and "湍流" in text:
                    columns.setdefault("representative", column_index)
            if columns.get("height") is not None and (columns.get("average") is not None or columns.get("representative") is not None):
                return row_index, columns
            if len(columns) > len(best[1]):
                best = (row_index, columns)
        return best

    def _tower_code_from_text(self, text: str) -> str | None:
        normalized_text = (text or "").replace("＃", "#")
        match = re.search(r"([A-Za-z0-9][A-Za-z0-9_-]{0,19})\s*#", normalized_text)
        if not match:
            return None
        return self._normalize_tower_code(f"{match.group(1)}#")

    def _tower_code_matches(self, text: str) -> list[re.Match[str]]:
        """返回文本中的全部测风塔编号匹配，兼容字母、数字、横线和全角井号。"""
        return list(re.finditer(self.WIND_TOWER_CODE_PATTERN, text or "", flags=re.IGNORECASE))

    def _tower_codes_in_text(self, text: str) -> list[str]:
        """按出现顺序提取并去重测风塔编号。"""
        codes: list[str] = []
        for match in self._tower_code_matches(text):
            code = self._normalize_tower_code(match.group(0))
            if code and code not in codes:
                codes.append(code)
        return codes

    def _turbulence_wind_speed_segment(self, text: str) -> Any:
        """提取湍流统计对应的风速段，不限定为10m/s或15m/s。"""
        matches = re.findall(
            r"(?:V\s*=\s*)?([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s",
            text or "",
            flags=re.IGNORECASE,
        )
        return self._normalize_scalar(matches[-1]) if matches else None

    def _height_cell_value(self, text: str) -> str | None:
        clean = self._clean_text(text)
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(m|米)?", clean, flags=re.IGNORECASE)
        if not match:
            return None
        number = self._clean_number(match.group(1))
        unit = "m" if (match.group(2) or "").lower() in ("", "m") or match.group(2) == "米" else match.group(2)
        return f"{number}{unit}"

    def _resource_summary_explicit_tower_codes(self, ast: DocumentAST, tower_codes: list[str]) -> list[str]:
        result: list[str] = []
        known_codes = set(tower_codes)
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if "#" not in text or not self._resource_summary_values_from_text(text):
                continue
            for code in self._tower_codes_in_text(text):
                if code and (not known_codes or code in known_codes) and code not in result:
                    result.append(code)
        return result

    def _resource_preferred_tower_codes_from_text(self, ast: DocumentAST, tower_codes: list[str]) -> list[str]:
        known_codes = set(tower_codes)
        result: list[str] = []
        patterns = self._configured_patterns(
            self._deterministic_rule_section("resource"),
            "preferred_tower_patterns",
            [
                r"本期风电场内设有一座\s*([A-Za-z0-9]{2,8}#)\s*测风塔",
                r"目前已有测风塔数据为[^\n。；;]{0,40}?([A-Za-z0-9]{2,8}#)\s*测风塔",
                r"本期[^\n。；;]{0,80}?([A-Za-z0-9]{2,8}#)\s*测风塔",
            ],
        )
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if "测风塔" not in text or "#" not in text:
                continue
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    code = self._normalize_tower_code(str(self._deterministic_match_value(match)))
                    if code and (not known_codes or code in known_codes) and code not in result:
                        result.append(code)
        return result

    def _resource_value(self, item: Any, default: Any = None) -> Any:
        if isinstance(item, dict) and "value" in item:
            return item.get("value")
        return default if item is None else item

    def _resource_source(self, item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict) and isinstance(item.get("_source"), dict):
            return item["_source"]
        return None

    def _merge_tower_codes(self, *groups: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for group in groups:
            for code in group:
                if code and code not in seen:
                    seen.add(code)
                    result.append(code)
        return result

    def _resource_tower_codes(self, ast: DocumentAST) -> list[str]:
        seen: set[str] = set()
        codes: list[str] = []
        resource_tables = self._original_tables_for_spec(ast, {"key_prefix": "resourceOriginalTable"})
        for table in resource_tables:
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._table_text(table)
            if "测风塔" not in caption or "基本情况" not in caption:
                continue
            for code in self._tower_codes_in_text(table_text):
                if code not in seen:
                    seen.add(code)
                    codes.append(code)
            if codes:
                return codes
        for table in ast.tables:
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._table_text(table)
            if not ("2.4.1-1" in caption or "\u6d4b\u98ce\u5854" in caption or "\u6d4b\u98ce\u5854" in table_text):
                continue
            for code in self._tower_codes_in_text(table_text):
                if code not in seen:
                    seen.add(code)
                    codes.append(code)
        return codes

    def _resource_tower_codes_from_text(self, ast: DocumentAST) -> list[str]:
        text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        codes: list[str] = []
        for segment in re.split("[\n\u3002\uff1b;]", text):
            if any(keyword in segment for keyword in ("编号", "测风塔", "雷达测风")) and ("#" in segment or "＃" in segment):
                for code in self._tower_codes_in_text(segment):
                    if code and code not in codes:
                        codes.append(code)
        for match in re.finditer("(?:\u6d4b\u98ce\u5854\u7f16\u53f7|\u96f7\u8fbe\u6d4b\u98ce\u7f16\u53f7|\u6d4b\u98ce\u7f16\u53f7)[^\n\u3002\uff1b;]{0,80}", text):
            for code in re.findall(r"[A-Za-z0-9]{2,8}#", match.group(0)):
                code = self._normalize_tower_code(code)
                if code and code not in codes:
                    codes.append(code)
        for match in re.finditer("([A-Za-z0-9#\u3001,\uff0c\\s]+)#?\\s*\u6d4b\u98ce\u5854", text):
            for code in re.findall(r"[A-Za-z0-9]{2,8}#", match.group(1) + "#"):
                code = self._normalize_tower_code(code)
                if code and code not in codes:
                    codes.append(code)
        for pattern in [
            "(?:\u6d4b\u98ce\u5854\u7f16\u53f7|\u6d4b\u98ce\u5854\u7f16\u53f7\u4e3a|\u96f7\u8fbe\u6d4b\u98ce\u7f16\u53f7|\u6d4b\u98ce\u7f16\u53f7)\\s*(?:\u4e3a)?\\s*([A-Za-z0-9]{2,8}#)",
            "([A-Za-z0-9]{2,8}#)\\s*\u6d4b\u98ce\u5854",
        ]:
            for match in re.finditer(pattern, text):
                code = self._normalize_tower_code(match.group(1))
                if code and code not in codes:
                    codes.append(code)
        return codes

    def _resource_summary_by_tower_from_text(self, ast: DocumentAST, tower_codes: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not tower_codes:
            return result
        summary_keywords = ("风功率密度", "主风向", "主风能", "主导风向", "湍流强度", "风切变", "空气密度")
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not text or not any(keyword in text for keyword in summary_keywords):
                continue
            target_windows = self._resource_summary_target_windows(text, tower_codes)
            if not target_windows:
                continue
            for tower, value_text in target_windows.items():
                values = self._resource_summary_values_from_text(value_text)
                if not values:
                    continue
                current = result.setdefault(tower, {"_cellSources": {}, "directions": {}})
                for key, label in {
                    "airDensity": "\u9ad8\u5ea6\u5bf9\u5e94\u7684\u7a7a\u6c14\u5bc6\u5ea6",
                    "windSpeed": "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u901fm/s",
                    "powerDensity": "\u8f6e\u6bc2\u9ad8\u5ea6\u5e73\u5747\u98ce\u529f\u7387\u5bc6\u5ea6W/m\u00b2",
                    "turbulence": "\u6700\u5927\u9ad8\u5ea6\u5904\u4ee3\u8868\u6027\u6e4d\u6d41\u5f3a\u5ea6",
                    "shear": "\u7efc\u5408\u98ce\u5207\u53d8",
                }.items():
                    if key in values and key not in current:
                        current[key] = values[key]
                        current["_cellSources"][label] = self._text_block_source(
                            block,
                            text,
                            "资源章节综合评价正文抽取。",
                            resolver="wind_resource_summary_text",
                        )
                height = values.get("height")
                if height is not None and current.get("height") is None:
                    current["height"] = height
                directions = values.get("directions")
                if isinstance(directions, dict):
                    for direction_key, direction_value in directions.items():
                        if direction_key.startswith("_") or direction_key in current["directions"]:
                            continue
                        current["directions"][direction_key] = direction_value
                        label_by_direction_key = {
                            "mainWindDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u5411",
                            "secondaryWindDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u5411",
                            "mainWindEnergyDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u80fd\u65b9\u5411",
                            "secondaryWindEnergyDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u80fd\u65b9\u5411",
                        }
                        label = label_by_direction_key.get(direction_key)
                        if label is None:
                            continue
                        current["_cellSources"][label] = self._text_block_source(
                            block,
                            text,
                            "资源章节综合评价主风向/主风能方向正文抽取。",
                            resolver="wind_resource_summary_text",
                        )
        return result

    def _resource_summary_target_windows(self, text: str, tower_codes: list[str]) -> dict[str, str]:
        block_towers = self._tower_codes_in_text(text)
        block_towers = [code for code in dict.fromkeys(block_towers) if code in tower_codes]
        if len(block_towers) <= 1:
            target_towers = block_towers or (tower_codes if len(tower_codes) == 1 else [])
            return {tower: text for tower in target_towers}
        windows: dict[str, str] = {}
        selected = self._resource_summary_target_towers(text, tower_codes)
        if selected:
            return {tower: text for tower in selected}
        for occurrence in self._tower_code_matches(text):
            code = self._normalize_tower_code(occurrence.group(0))
            if code not in tower_codes or code in windows:
                continue
            window_end = occurrence.start() + 260
            next_tower = re.search(self.WIND_TOWER_CODE_PATTERN, text[occurrence.end() : window_end])
            if next_tower:
                window_end = occurrence.end() + next_tower.start()
            window = text[occurrence.start() : window_end]
            if self._resource_summary_values_from_text(window):
                windows[code] = window
        return windows

    def _resource_summary_target_towers(self, text: str, tower_codes: list[str]) -> list[str]:
        block_towers = self._tower_codes_in_text(text)
        block_towers = [code for code in dict.fromkeys(block_towers) if code in tower_codes]
        if len(block_towers) <= 1:
            return block_towers or (tower_codes if len(tower_codes) == 1 else [])
        selected: list[str] = []
        for match in re.finditer(r"(?:\u53ea\u91c7\u7528|\u91c7\u7528|\u4f7f\u7528)\s*([A-Za-z0-9]{2,8}#)[^\n\u3002\uff1b;]{0,120}?(?:\u8fdb\u884c\u5206\u6790|\u7a7a\u6c14\u5bc6\u5ea6|\u5e73\u5747\u98ce\u901f|\u98ce\u529f\u7387\u5bc6\u5ea6|\u7efc\u5408\u5206\u6790)", text):
            code = self._normalize_tower_code(match.group(1))
            if code in tower_codes and code not in selected:
                selected.append(code)
        if selected:
            return selected
        for occurrence in self._tower_code_matches(text):
            code = self._normalize_tower_code(occurrence.group(0))
            if code not in tower_codes or code in selected:
                continue
            window_end = occurrence.start() + 220
            next_tower = re.search(self.WIND_TOWER_CODE_PATTERN, text[occurrence.end() : window_end])
            if next_tower:
                window_end = occurrence.end() + next_tower.start()
            window = text[occurrence.start() : window_end]
            if self._resource_summary_values_from_text(window):
                selected.append(code)
        return selected

    def _resource_summary_values_from_text(self, text: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        resource_rules = self._deterministic_rule_section("resource")
        summary_rules = resource_rules.get("summary_fields") if isinstance(resource_rules.get("summary_fields"), dict) else {}
        fallback_rules = self._default_resource_summary_field_rules()
        for key, fallback_rule in fallback_rules.items():
            rule = summary_rules.get(key) if isinstance(summary_rules.get(key), dict) else fallback_rule
            value = self._value_from_configured_patterns(text, rule)
            if value is not None:
                values[key] = value
        height = self._resource_summary_height_from_text(text)
        if height is not None:
            values["height"] = height
        directions = self._resource_summary_directions_from_text(text)
        if directions:
            values["directions"] = directions
        return values

    def _resource_summary_height_from_text(self, text: str) -> Any:
        """提取平均风速、风功率密度或湍流指标对应的实际高度。"""
        patterns = [
            r"([0-9]+(?:\.[0-9]+)?)\s*m\s*(?:轮毂)?高度[^\n。；;]{0,80}?(?:年?平均风速|年?平均风功率密度|代表性?湍流强度)",
            r"(?:年?平均风速|年?平均风功率密度|代表性?湍流强度)[^\n。；;]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*m\s*(?:轮毂)?高度",
        ]
        for pattern in patterns:
            match = re.search(pattern, text or "", flags=re.IGNORECASE)
            if match:
                return self._normalize_scalar(match.group(1))
        return None

    def _default_resource_summary_field_rules(self) -> dict[str, dict[str, Any]]:
        return {
            "airDensity": {
                "value_type": "number",
                "select": "last",
                "patterns": [
                    r"\u7a7a\u6c14\u5bc6\u5ea6(?:\u6761\u4ef6\u4e0b)?(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:kg|km)\s*/?\s*m",
                    r"\u7a7a\u6c14\u5bc6\u5ea6\s*([0-9]+(?:\.[0-9]+)?)\s*(?:kg|km)\s*/?\s*m",
                ],
                "validators": {"min": 0.8, "max": 1.4},
            },
            "windSpeed": {
                "value_type": "number",
                "select": "last",
                "require_keywords": ["风功率密度"],
                "patterns": [
                    r"(?:\u8f6e\u6bc2\u9ad8\u5ea6|[0-9]+\s*m\s*\u9ad8\u5ea6)[^\n\u3002\uff1b;]{0,40}?\u5e74?\u5e73\u5747\u98ce\u901f(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s",
                    r"\u5e74?\u5e73\u5747\u98ce\u901f(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s",
                ],
            },
            "powerDensity": {
                "value_type": "number",
                "select": "last",
                "patterns": [
                    r"\u5e74?\u5e73\u5747\u98ce\u529f\u7387\u5bc6\u5ea6(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)\s*W\s*/?\s*m",
                    r"\u98ce\u529f\u7387\u5bc6\u5ea6(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)\s*W\s*/?\s*m",
                ],
            },
            "turbulence": {
                "value_type": "number",
                "select": "last",
                "reject_keywords": ["折减"],
                "patterns": [
                    r"\u6e4d\u6d41\u5f3a\u5ea6(?!\s*\u5728\s*[0-9]+(?:\.[0-9]+)?\s*[~\uff5e\uff5e\u301c-])(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)",
                    r"\u4ee3\u8868\u6027\u6e4d\u6d41\u5f3a\u5ea6[^\n\u3002\uff1b;]{0,20}?([0-9]+(?:\.[0-9]+)?)",
                ],
                "validators": {"min": 0, "max": 1},
            },
            "shear": {
                "value_type": "number",
                "select": "last",
                "patterns": [
                    r"\u7efc\u5408\u98ce\u5207\u53d8(?:\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)",
                    r"\u98ce\u5207\u53d8\u6307\u6570(?:\u53d6|\u4e3a)?\s*([0-9]+(?:\.[0-9]+)?)",
                ],
                "validators": {"min": 0, "max": 1},
            },
        }

    def _last_number_match(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                value = matches[-1][0] if isinstance(matches[-1], tuple) else matches[-1]
                return self._normalize_scalar(value)
        return None

    def _resource_summary_directions_from_text(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        direction_match = re.search(r"(?:\u4e3b\u5bfc\u98ce\u5411|\u4e3b\u98ce\u5411)(?:\u4e3a|\u548c\u4e3b\u98ce\u80fd\u65b9\u5411\u4e00\u81f4\uff0c\u4ee5)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)", text)
        secondary_direction_match = re.search(r"(?:\u6b21\u4e3b\u5bfc\u98ce\u5411|\u6b21\u4e3b\u98ce\u5411|\u6b21\u98ce\u5411)(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)", text)
        energy_match = re.search(r"\u4e3b\u98ce\u80fd\u65b9\u5411(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)", text)
        secondary_energy_match = re.search(r"(?:\u6b21\u4e3b\u5bfc\u98ce\u80fd\u65b9\u5411|\u6b21\u4e3b\u98ce\u80fd\u65b9\u5411|\u6b21\u98ce\u80fd\u65b9\u5411)(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)", text)
        if direction_match:
            result["mainWindDirection"] = self._clean_direction_text(direction_match.group(1))
        if secondary_direction_match:
            result["secondaryWindDirection"] = self._clean_direction_text(secondary_direction_match.group(1))
        if energy_match:
            energy = self._clean_direction_text(energy_match.group(1))
            if energy not in {"一致", "\u4e00\u81f4"}:
                result["mainWindEnergyDirection"] = energy
        if secondary_energy_match:
            energy = self._clean_direction_text(secondary_energy_match.group(1))
            if energy not in {"一致", "\u4e00\u81f4"}:
                result["secondaryWindEnergyDirection"] = energy
        if result.get("mainWindDirection") and not result.get("mainWindEnergyDirection") and "主风向和主风能方向一致" in text:
            result["mainWindEnergyDirection"] = result["mainWindDirection"]
        return {key: value for key, value in result.items() if value}

    def _clean_direction_text(self, text: str) -> str:
        cleaned = self._clean_text(text)
        cleaned = cleaned.strip(" ，,、及和")
        cleaned = re.split(r"(?:\u98ce\u7684|\u98ce\u5411\u548c|\u98ce\u80fd\u5206\u5e03|\u5206\u5e03\u9891\u7387)", cleaned, maxsplit=1)[0]
        cleaned = cleaned.strip(" ，,、及和")
        return cleaned

    def _resource_tower_code_sources(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for table in ast.tables:
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            table_text = self._table_text(table)
            if not ("测风塔" in caption or "测风塔" in table_text or "雷达测风" in table_text):
                continue
            matrix = self._table_matrix(table)
            for row_index, row in enumerate(matrix):
                for column_index, cell in enumerate(row):
                    for normalized in self._tower_codes_in_text(cell):
                        if normalized and normalized not in sources:
                            sources[normalized] = self._table_cell_source(
                                table,
                                row_index,
                                column_index,
                                "资源章节原文表格测风塔编号来源。",
                                resolver="wind_resource_tower_code_table",
                            )
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text or "#" not in text:
                continue
            if not any(keyword in text for keyword in ("测风塔编号", "雷达测风编号", "测风编号", "测风塔")):
                continue
            for normalized in self._tower_codes_in_text(text):
                if normalized and normalized not in sources:
                    sources[normalized] = self._text_block_source(
                        block,
                        text,
                        "资源章节正文测风塔编号来源。",
                        resolver="wind_resource_tower_code_text",
                    )
        return sources

    def _wind_direction_by_tower_from_resource_text(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            for code in set(self._tower_codes_in_text(text)):
                direction_match = None
                secondary_direction_match = None
                energy_match = None
                secondary_energy_match = None
                matched_window = ""
                for occurrence in re.finditer(re.escape(code), text):
                    position = occurrence.start()
                    window_end = position + 600
                    next_tower = re.search(r"[A-Za-z0-9]{2,8}#", text[position + len(code) : window_end])
                    if next_tower:
                        window_end = position + len(code) + next_tower.start()
                    window = text[position:window_end]
                    direction_match = re.search(r"(?:主导风向|主风向)为\s*([A-Z]{1,4})", window)
                    secondary_direction_match = re.search(r"(?:次主导风向|次主风向|次风向)(?:为)?\s*([A-Z]{1,4})", window)
                    energy_match = re.search(r"(?:主导风能方向|主风能方向)为\s*([A-Z]{1,4})", window)
                    secondary_energy_match = re.search(r"(?:次主导风能方向|次主风能方向|次风能方向)(?:为)?\s*([A-Z]{1,4})", window)
                    if direction_match or secondary_direction_match or energy_match or secondary_energy_match:
                        matched_window = window
                        break
                if direction_match or secondary_direction_match or energy_match or secondary_energy_match:
                    source_trace = self._text_block_source(
                        block,
                        matched_window,
                        "资源章节正文测风塔主风向/主风能方向抽取。",
                        resolver="wind_resource_direction_text",
                    )
                    cell_sources: dict[str, Any] = {}
                    if direction_match:
                        cell_sources["\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u5411"] = source_trace
                    if secondary_direction_match:
                        cell_sources["\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u5411"] = source_trace
                    if energy_match:
                        cell_sources["\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u80fd\u65b9\u5411"] = source_trace
                    if secondary_energy_match:
                        cell_sources["\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u6b21\u98ce\u80fd\u65b9\u5411"] = source_trace
                    result[self._normalize_tower_code(code)] = {
                        "mainWindDirection": direction_match.group(1) if direction_match else "---",
                        "secondaryWindDirection": secondary_direction_match.group(1) if secondary_direction_match else "---",
                        "mainWindEnergyDirection": energy_match.group(1) if energy_match else "---",
                        "secondaryWindEnergyDirection": secondary_energy_match.group(1) if secondary_energy_match else "---",
                        "_cellSources": cell_sources,
                    }
        return result

    def _wind_direction_by_tower_from_resource_tables(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        specs = self.wind_resource_direction_table_specs or []
        if not specs:
            return result
        for spec in specs:
            for table in self._original_tables_for_spec(ast, {"key_prefix": "resourceOriginalTable"}):
                caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
                title_text = f"{caption}\n{self._section_path_caption(table)}"
                patterns = spec.get("patterns") or []
                if patterns and not any(re.search(str(pattern), title_text, flags=re.IGNORECASE) for pattern in patterns):
                    continue
                table_result = self._wind_direction_table_values(table, spec)
                for tower, values in table_result.items():
                    current = result.setdefault(tower, {})
                    current.update(values)
        return result

    def _wind_direction_table_values(self, table: DocumentTable, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return {}
        sector_rows = self._wind_direction_sector_rows_values(table, matrix, spec)
        if sector_rows:
            return sector_rows
        header_index = self._configured_header_row_index(matrix, spec)
        grouped = self._wind_direction_grouped_header_values(table, matrix, spec, header_index)
        if grouped:
            return grouped
        header = matrix[header_index]
        data_rows = list(enumerate(matrix[header_index + 1 :], start=header_index + 1))
        direction_aliases = spec.get("direction_column_aliases") or ["风向", "扇区", "方位"]
        tower_aliases = spec.get("tower_column_aliases") or ["塔号", "测风塔", "编号"]
        direction_index = self._find_header_index(header, direction_aliases)
        tower_index = self._find_header_index(header, tower_aliases)
        metric_specs = spec.get("metrics") or []
        if direction_index is None:
            direction_index = 0
        metric_indexes = [
            (metric, self._find_header_index(header, metric.get("column_aliases") or []))
            for metric in metric_specs
            if isinstance(metric, dict)
        ]
        if not metric_indexes:
            return {}
        best: dict[str, dict[str, tuple[float, str, int, int]]] = {}
        current_tower: str | None = None
        for row_index, row in data_rows:
            row_text = " | ".join(row)
            tower_candidates = [self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", row_text)]
            if tower_index is not None and tower_index < len(row):
                tower_candidates = [self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", row[tower_index])] or tower_candidates
            if tower_candidates:
                current_tower = tower_candidates[0]
            if not current_tower:
                continue
            direction = row[direction_index].strip() if direction_index < len(row) else ""
            if not re.fullmatch(r"[A-Z]{1,4}", direction):
                continue
            for metric, column_index in metric_indexes:
                if column_index is None or column_index >= len(row):
                    continue
                value = self._numeric_sort_value(row[column_index])
                if value == float("-inf"):
                    continue
                target = str(metric.get("target") or "")
                if target not in {"mainWindDirection", "mainWindEnergyDirection"}:
                    continue
                tower_best = best.setdefault(current_tower, {})
                if value > tower_best.get(target, (float("-inf"), "", -1, -1))[0]:
                    tower_best[target] = (value, direction, row_index, column_index)
        return self._wind_direction_best_to_result(table, best)

    def _wind_direction_sector_rows_values(self, table: DocumentTable, matrix: list[list[str]], spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
        metric_specs = [metric for metric in (spec.get("metrics") or []) if isinstance(metric, dict)]
        if not metric_specs:
            return {}
        best: dict[str, dict[str, tuple[float, str, int, int]]] = {}
        current_tower: str | None = None
        current_labels: list[tuple[int, str]] = []
        for row_index, row in enumerate(matrix):
            row_text = self._clean_text(" ".join(row))
            tower_candidates = [self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", row_text)]
            tower_candidates = [code for code in tower_candidates if code]
            if tower_candidates:
                current_tower = tower_candidates[0]
                current_labels = []
            if not current_tower:
                continue
            label_index = self._sector_row_label_index(row)
            if label_index is None:
                continue
            label_cell = self._clean_text(row[label_index])
            if "扇区" in label_cell:
                labels = self._sector_labels_from_row(row, label_index + 1)
                if labels:
                    current_labels = labels
                continue
            target = self._wind_direction_metric_target_from_label(label_cell, metric_specs)
            if target is None or not current_labels:
                continue
            tower_best = best.setdefault(current_tower, {})
            for column_index, direction in current_labels:
                if column_index >= len(row):
                    continue
                value = self._numeric_sort_value(row[column_index])
                if value == float("-inf"):
                    continue
                if value > tower_best.get(target, (float("-inf"), "", -1, -1))[0]:
                    tower_best[target] = (value, direction, row_index, column_index)
        return self._wind_direction_best_to_result(table, best)

    def _sector_row_label_index(self, row: list[str]) -> int | None:
        for index, cell in enumerate(row[: min(len(row), 4)]):
            text = self._clean_text(cell)
            if any(keyword in text for keyword in ("扇区", "风向", "风速", "风功率", "风能")):
                return index
        return None

    def _sector_labels_from_row(self, row: list[str], start: int) -> list[tuple[int, str]]:
        labels: list[tuple[int, str]] = []
        for column_index in range(start, len(row)):
            label = self._clean_direction_label(row[column_index])
            if label:
                labels.append((column_index, label))
        return labels

    def _clean_direction_label(self, value: Any) -> str | None:
        text = self._clean_text(str(value or "")).upper()
        match = re.search(r"\b(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)\b", text)
        return match.group(1) if match else None

    def _wind_direction_metric_target_from_label(self, label: str, metric_specs: list[dict[str, Any]]) -> str | None:
        if "风功率" in label or "风能" in label:
            wanted = "mainWindEnergyDirection"
        elif "风向" in label or "风速" in label:
            wanted = "mainWindDirection"
        else:
            return None
        targets = {str(metric.get("target") or "") for metric in metric_specs}
        return wanted if wanted in targets else None

    def _wind_direction_grouped_header_values(
        self,
        table: DocumentTable,
        matrix: list[list[str]],
        spec: dict[str, Any],
        header_index: int,
    ) -> dict[str, dict[str, Any]]:
        grouped_spec = spec.get("grouped_header") or {}
        if not bool(grouped_spec.get("enabled")):
            return {}
        if header_index >= len(matrix) - 1:
            return {}
        tower_pattern = str(grouped_spec.get("tower_pattern") or r"[A-Za-z0-9]{2,8}#")
        tower_header_index = header_index
        tower_header = matrix[tower_header_index]
        tower_codes = [self._normalize_tower_code(match.group(0)) for cell in tower_header for match in re.finditer(tower_pattern, cell)]
        if len(tower_codes) < 2 and header_index > 0:
            previous_header = matrix[header_index - 1]
            previous_codes = [self._normalize_tower_code(match.group(0)) for cell in previous_header for match in re.finditer(tower_pattern, cell)]
            if len(previous_codes) >= 2:
                tower_header_index = header_index - 1
                tower_codes = previous_codes
        tower_codes = list(dict.fromkeys(code for code in tower_codes if code))
        if len(tower_codes) < 2:
            return {}
        try:
            metric_header_index = tower_header_index + int(grouped_spec.get("metric_header_row_offset", 1))
        except (TypeError, ValueError):
            metric_header_index = tower_header_index + 1
        if metric_header_index >= len(matrix):
            return {}
        metric_header = matrix[metric_header_index]
        direction_aliases = grouped_spec.get("direction_column_aliases") or spec.get("direction_column_aliases") or ["风向", "扇区", "方位"]
        direction_index = self._find_header_index(metric_header, direction_aliases)
        if direction_index is None:
            direction_index = 0
        metric_columns = [index for index, value in enumerate(metric_header) if index != direction_index and str(value).strip()]
        if not metric_columns or len(metric_columns) < len(tower_codes):
            return {}
        span = max(1, len(metric_columns) // len(tower_codes))
        if len(metric_columns) % len(tower_codes) != 0:
            return {}
        metric_specs = [metric for metric in (spec.get("metrics") or []) if isinstance(metric, dict)]
        if not metric_specs:
            return {}
        tower_metric_indexes: dict[str, list[tuple[dict[str, Any], int]]] = {}
        for tower_index, tower in enumerate(tower_codes):
            columns = metric_columns[tower_index * span : (tower_index + 1) * span]
            for metric in metric_specs:
                aliases = metric.get("column_aliases") or []
                column_index = next(
                    (
                        column
                        for column in columns
                        if any(str(alias) in str(metric_header[column]) for alias in aliases if alias)
                    ),
                    None,
                )
                if column_index is not None:
                    tower_metric_indexes.setdefault(tower, []).append((metric, column_index))
        if not tower_metric_indexes:
            return {}
        best: dict[str, dict[str, tuple[float, str, int, int]]] = {}
        for row_index, row in enumerate(matrix[metric_header_index + 1 :], start=metric_header_index + 1):
            direction = row[direction_index].strip() if direction_index < len(row) else ""
            if not re.fullmatch(r"[A-Z]{1,4}", direction):
                continue
            for tower, metric_indexes in tower_metric_indexes.items():
                tower_best = best.setdefault(tower, {})
                for metric, column_index in metric_indexes:
                    if column_index >= len(row):
                        continue
                    value = self._numeric_sort_value(row[column_index])
                    if value == float("-inf"):
                        continue
                    target = str(metric.get("target") or "")
                    if target not in {"mainWindDirection", "mainWindEnergyDirection"}:
                        continue
                    if value > tower_best.get(target, (float("-inf"), "", -1, -1))[0]:
                        tower_best[target] = (value, direction, row_index, column_index)
        return self._wind_direction_best_to_result(table, best)

    def _wind_direction_best_to_result(self, table: DocumentTable, best: dict[str, dict[str, tuple[float, str, int, int]]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        label_by_target = {
            "mainWindDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u5411",
            "mainWindEnergyDirection": "\u8f6e\u6bc2\u9ad8\u5ea6\u5904\u7684\u4e3b\u98ce\u80fd\u65b9\u5411",
        }
        for tower, values in best.items():
            row: dict[str, Any] = {"_cellSources": {}}
            for target, (_value, direction, row_index, column_index) in values.items():
                row[target] = direction
                label = label_by_target.get(target)
                if label:
                    row["_cellSources"][label] = self._table_cell_source(
                        table,
                        row_index,
                        column_index,
                        "按配置的风向/风能频率表最大值抽取主方向。",
                        resolver="wind_resource_direction_frequency_table",
                    )
            result[tower] = row
        return result

    def _generation_use_by_tower_from_resource_text(self, ast: DocumentAST) -> dict[str, Any]:
        text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        selected: set[str] = set()
        selected_sources: dict[str, dict[str, Any]] = {}
        for match in re.finditer(r"(?:选用|使用|采用)\s*([A-Za-z0-9]{2,8}#)[^\n。；;]{0,80}?(?:发电量评估|发电量计算|依据)", text):
            code = self._normalize_tower_code(match.group(1))
            selected.add(code)
            source_block = self._block_containing_text(ast, match.group(0))
            if source_block:
                selected_sources[code] = self._text_block_source(
                    source_block,
                    match.group(0),
                    "资源章节正文发电量计算采用测风塔判断。",
                    resolver="wind_resource_generation_use_text",
                )
        for match in re.finditer(r"(?:根据|采用|使用|只采用)\s*([A-Za-z0-9]{2,8}#)[^\n。；;]{0,160}?(?:推算各风能要素|风能要素|综合分析)", text):
            code = self._normalize_tower_code(match.group(1))
            selected.add(code)
            source_block = self._block_containing_text(ast, match.group(0))
            if source_block:
                selected_sources[code] = self._text_block_source(
                    source_block,
                    match.group(0),
                    "资源章节正文发电量计算采用测风塔判断。",
                    resolver="wind_resource_generation_use_text",
                )
        if not selected:
            towers = self._resource_tower_codes(ast) or self._merge_tower_codes([self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", text)])
            source_block = next((block for block in ast.blocks if block.text and any(code in block.text for code in towers)), None)
            if not towers or source_block is None:
                return {code: "是" for code in towers}
            source = self._text_block_source(
                source_block,
                self._clean_text(source_block.text or ""),
                "资源章节未出现排除测风塔的发电量计算说明，已知测风塔默认用于组合字段。",
                resolver="wind_resource_generation_use_default",
            )
            return {code: {"value": "是", "_source": source} for code in towers}
        known_towers = self._resource_tower_codes(ast)
        towers = known_towers or self._merge_tower_codes([self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", text)])
        fallback_source = next(iter(selected_sources.values()), None)
        return {
            code: {
                "value": "是" if code in selected else "否",
                "_source": selected_sources.get(code) or fallback_source,
            }
            for code in towers
        }

    def _air_density_by_tower_from_resource_text(self, ast: DocumentAST) -> dict[str, Any]:
        blocks_text = "\n".join(self._clean_text(block.text or "") for block in ast.blocks if block.text)
        result: dict[str, Any] = {}
        selected_density_towers: set[str] = set()
        for match in re.finditer("(?:\u53ea\u91c7\u7528|\u91c7\u7528|\u6839\u636e|\u4f7f\u7528)\\s*([A-Za-z0-9]{2,8}#)[^\n\u3002\uff1b;]{0,120}?(?:\u8fdb\u884c\u5206\u6790|\u7a7a\u6c14\u5bc6\u5ea6\u8ba1\u7b97)", blocks_text):
            code = self._normalize_tower_code(match.group(1))
            if code:
                selected_density_towers.add(code)
        for code in set(re.findall(r"[A-Za-z0-9]{2,8}#", blocks_text)):
            normalized_code = self._normalize_tower_code(code)
            if selected_density_towers and normalized_code not in selected_density_towers:
                continue
            context_match = re.search(re.escape(code) + r"[^\n。；;]{0,80}?(?:空气密度计算|空气密度)", blocks_text)
            if context_match:
                window = blocks_text[context_match.start() : context_match.start() + 500]
                density_matches = re.findall(r"(?:推算至|轮毂高度|[0-9]+m\s*高度)[^\n。；;]{0,60}?空气密度为\s*([0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m", window, flags=re.IGNORECASE)
                if density_matches and normalized_code:
                    source_block = self._block_containing_text(ast, context_match.group(0))
                    result[normalized_code] = {
                        "value": self._normalize_scalar(density_matches[-1]),
                        "_source": self._text_block_source(
                            source_block,
                            window,
                            "资源章节正文空气密度抽取。",
                            resolver="wind_resource_air_density_text",
                        ) if source_block else None,
                    }
        if result:
            return result
        if selected_density_towers:
            for segment in re.split(r"[\n\u3002\uff1b;]", blocks_text):
                if "空气密度" not in segment or not any(code in segment for code in selected_density_towers):
                    continue
                densities = self._air_density_values_from_text(segment)
                if not densities:
                    continue
                source_block = self._block_containing_text(ast, segment)
                for code in selected_density_towers:
                    if code not in segment:
                        continue
                    result[code] = {
                        "value": densities[-1],
                        "_source": self._text_block_source(
                            source_block,
                            segment,
                            "资源章节正文指定测风塔空气密度抽取。",
                            resolver="wind_resource_air_density_text",
                        ) if source_block else None,
                    }
            if result:
                return result
        for segment in re.split(r"[\n\u3002\uff1b;]", blocks_text):
            if "空气密度" not in segment or "分别为" not in segment:
                match = re.search(r"([A-Za-z0-9]{2,8}#)[^\n。；;]{0,120}?空气密度[^\n。；;]{0,30}?为\s*([0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m", segment, flags=re.IGNORECASE)
                if match:
                    source_block = self._block_containing_text(ast, segment)
                    result[self._normalize_tower_code(match.group(1))] = {
                        "value": self._normalize_scalar(match.group(2)),
                        "_source": self._text_block_source(
                            source_block,
                            segment,
                            "资源章节正文空气密度抽取。",
                            resolver="wind_resource_air_density_text",
                        ) if source_block else None,
                    }
                continue
            before, after = segment.split("分别为", 1)
            towers = self._tower_codes_near_air_density_list(before)
            densities = self._air_density_values_from_text(after)
            for code, density in zip(towers, densities):
                source_block = self._block_containing_text(ast, segment)
                result[code] = {
                    "value": density,
                    "_source": self._text_block_source(
                        source_block,
                        segment,
                        "资源章节正文空气密度列表抽取。",
                        resolver="wind_resource_air_density_text",
                    ) if source_block else None,
                }
        if result:
            return result
        density_match = re.search(r"\u7a7a\u6c14\u5bc6\u5ea6[^\n\u3002]{0,30}?\u5206\u522b\u4e3a([^\n\u3002]+)", blocks_text)
        if density_match:
            before = blocks_text[max(0, density_match.start() - 500): density_match.start()]
            towers = self._tower_codes_near_air_density_list(before)
            densities = self._air_density_values_from_text(density_match.group(1))
            for code, density in zip(towers, densities):
                source_block = self._block_containing_text(ast, density_match.group(0))
                result[code] = {
                    "value": density,
                    "_source": self._text_block_source(
                        source_block,
                        density_match.group(0),
                        "资源章节正文空气密度列表抽取。",
                        resolver="wind_resource_air_density_text",
                    ) if source_block else None,
                }
        return result

    def _wind_farm_air_density_by_tower_from_resource_text(self, ast: DocumentAST) -> dict[str, Any]:
        result: dict[str, Any] = {}
        all_tower_codes = self._resource_tower_codes(ast) or self._resource_tower_codes_from_text(ast)
        patterns = [
            r"(?:该|本)(?:风电场|项目)(?:区域)?的?空气密度(?:采用|为|是|计算得到)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m",
            r"(?:风电场|项目)(?:区域)?空气密度(?:采用|为|是|计算得到)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m",
            r"计算得到(?:该|本)?(?:风电场|项目)(?:区域)?的?空气密度(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m",
        ]
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if "空气密度" not in text or "轮毂高度" in text and not re.search(r"(?:该|本)(?:风电场|项目)|风电场区域|项目区域", text):
                continue
            for match in self._wind_farm_air_density_matches(text, patterns):
                tower_codes = self._tower_codes_for_wind_farm_density_text(text, match.start(), all_tower_codes)
                if not tower_codes:
                    continue
                source = self._text_block_source(
                    block,
                    text,
                    "资源章节正文该风电场空气密度抽取。",
                    resolver="wind_farm_air_density_text",
                )
                value = self._normalize_scalar(match.group("value"))
                for code in tower_codes:
                    result.setdefault(code, {"value": value, "_source": source})
        return result

    def _wind_farm_air_density_matches(self, text: str, patterns: list[str]) -> list[re.Match[str]]:
        matches: list[re.Match[str]] = []
        for pattern in patterns:
            matches.extend(re.finditer(pattern, text, flags=re.IGNORECASE))
        return sorted(matches, key=lambda item: item.start())

    def _tower_codes_for_wind_farm_density_text(self, text: str, position: int, all_tower_codes: list[str]) -> list[str]:
        before = text[max(0, position - 220): position]
        preferred_codes = self._preferred_tower_codes_near_wind_farm_density_text(before, all_tower_codes)
        if preferred_codes:
            return preferred_codes
        codes = [self._normalize_tower_code(code) for code in re.findall(r"[A-Za-z0-9]{2,8}#", before)]
        codes = [code for code in dict.fromkeys(codes) if code]
        if codes:
            return [codes[-1]]
        known_codes = [code for code in dict.fromkeys(self._normalize_tower_code(code) for code in all_tower_codes) if code]
        return known_codes if len(known_codes) == 1 else []

    def _preferred_tower_codes_near_wind_farm_density_text(self, text: str, all_tower_codes: list[str]) -> list[str]:
        known_codes = {code for code in (self._normalize_tower_code(code) for code in all_tower_codes) if code}
        patterns = [
            r"(?:使用|采用|选用)\s*([A-Za-z0-9]{2,8}#)\s*测风塔",
            r"以\s*([A-Za-z0-9]{2,8}#)\s*测风塔(?:为(?:基准|代表)|进行(?:分析|空气密度计算)|作为)",
            r"([A-Za-z0-9]{2,8}#)\s*测风塔[^#\n。；;]{0,30}?(?:作为|用于|进行)[^#\n。；;]{0,20}?(?:分析|空气密度计算|发电量评估|依据|基准)",
        ]
        matches: list[tuple[int, str]] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                code = self._normalize_tower_code(str(self._deterministic_match_value(match)))
                if code and (not known_codes or code in known_codes):
                    matches.append((match.start(), code))
        if not matches:
            return []
        return [matches[-1][1]]

    def _height_air_density_by_tower_from_resource_text(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "").replace("＃", "#")
            if "空气密度" not in text:
                continue
            tower_codes = [
                self._normalize_tower_code(code)
                for code in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]", text)
            ]
            tower_codes = [code for code in dict.fromkeys(tower_codes) if code]
            if not tower_codes:
                continue
            for tower in tower_codes:
                for occurrence in re.finditer(re.escape(tower), text):
                    window_end = occurrence.start() + 520
                    next_tower = re.search(
                        r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]",
                        text[occurrence.end() : window_end],
                    )
                    if next_tower:
                        window_end = occurrence.end() + next_tower.start()
                    window = text[occurrence.start() : window_end]
                    for density_match in re.finditer(
                        r"(?P<height>[0-9]+(?:\.[0-9]+)?)\s*m\s*高度空气密度(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m",
                        window,
                        flags=re.IGNORECASE,
                    ):
                        height_key = f"{density_match.group('height')}m"
                        result.setdefault(tower, {})[height_key] = {
                            "value": self._normalize_scalar(density_match.group("value")),
                            "_source": self._text_block_source(
                                block,
                                window,
                                "资源章节正文指定高度空气密度抽取。",
                                resolver="wind_resource_height_air_density_text",
                            ),
                        }
        return result

    def _tower_codes_near_air_density_list(self, text: str) -> list[str]:
        candidates = re.findall(r"((?:[A-Za-z0-9]{2,8}#[\u3001,，\s]*)+)[^#\n\u3002\uff1b;]{0,40}?\u6d4b\u98ce\u5854", text)
        source = candidates[-1] if candidates else text[-180:]
        codes: list[str] = []
        for code in re.findall(r"[A-Za-z0-9]{2,8}#", source):
            normalized = self._normalize_tower_code(code)
            if normalized and normalized not in codes:
                codes.append(normalized)
        return codes

    def _air_density_by_tower_from_resource_tables(self, ast: DocumentAST) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            header_text = " ".join(matrix[0])
            table_text = self._matrix_text(matrix)
            if "测风塔编号" not in table_text or "空气密度" not in table_text:
                continue
            for row in matrix[1:]:
                if len(row) < 2:
                    continue
                code_match = re.search(r"[A-Za-z0-9][A-Za-z0-9_-]{0,19}\s*[#＃]", row[0])
                if code_match is None:
                    continue
                code = self._normalize_tower_code(code_match.group(0))
                value = self._air_density_value_from_cell(row[1])
                result[code] = {
                    "value": value if value is not None else "---",
                    "_source": self._table_cell_source(
                        table,
                        matrix.index(row),
                        1,
                        "资源章节空气密度表格抽取。",
                        resolver="wind_resource_air_density_table",
                    ),
                }
            if result:
                return result
        return result

    def _air_density_value_from_cell(self, text: str) -> Any:
        cleaned = self._clean_text(str(text))
        if not cleaned or cleaned in {"---", "--", "??", "/"} or "??" in cleaned:
            return None
        matches = re.findall(r"(?:90\s*[:?])?([01](?:\.\d+)?)", cleaned)
        for value in matches:
            number = self._normalize_scalar(value)
            try:
                if 0.8 <= float(number) <= 1.4:
                    return number
            except (TypeError, ValueError):
                continue
        return None

    def _air_density_values_from_text(self, text: str) -> list[Any]:
        values = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m(?:[\u00b3\uff13\^]?3)?", text, flags=re.IGNORECASE)
        if not values:
            cleaned = re.sub(r"kg\s*/?\s*m(?:[\u00b3\uff13\^]?3)?", " ", text, flags=re.IGNORECASE)
            values = re.findall(r"\d+\.\d+", cleaned)
        return [self._normalize_scalar(value) for value in values]

    def _resource_table_key(self, caption: str) -> str | None:
        for spec in self.resource_table_key_specs:
            if self._table_key_spec_matches(spec, caption):
                return str(spec.get("key"))
        return None

    def _resource_scalar_override_values(
        self, ast: DocumentAST
    ) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        grade = self._wind_power_density_grade_from_blocks(ast)
        if grade is not None:
            value, evidence_text, section_path = grade
            overrides["windPowerDensityGrade"] = (
                "风功率密度等级",
                value,
                "级",
                evidence_text,
                "paragraph",
                {"resolver": "wind_resource_text", "sectionPath": section_path},
            )
        return overrides

    def _wind_power_density_grade_from_blocks(self, ast: DocumentAST) -> tuple[str, str, list[str]] | None:
        pattern = re.compile(r"风功率密度等级[^。；;\n]{0,20}?(?:为|是)?\s*(?P<value>[A-ZＡ-Ｚ]-?\s*[0-9ⅠⅡⅢⅣⅤⅥ一二三四五六]+)\s*级?")
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            if not text or "风功率密度等级" not in text:
                continue
            context = f"{' / '.join(block.section_path or [])} {text}"
            if not any(keyword in context for keyword in ("资源章节", "风资源", "风能资源", "综合分析", "小结")):
                continue
            match = pattern.search(text)
            if match:
                value = match.group("value").replace(" ", "").replace("－", "-").replace("—", "-")
                return value, match.group(0), list(block.section_path or [])
        return None

    def _apply_wind_resource_collection_overrides(
        self,
        ast: DocumentAST,
        fields: dict[str, ParsedField],
        details: dict[str, list[dict[str, Any]]],
        skip_codes: set[str] | None = None,
    ) -> None:
        """把风资源指标整理成携带塔号、高度、数值和单位的通用记录。"""
        skip_codes = skip_codes or set()
        rows = [row for row in details.get("windResourceCombined", []) if isinstance(row, dict)]
        tower_codes = [row.get("测风塔编号") for row in rows if row.get("测风塔编号")]
        if tower_codes:
            tower_evidences = [
                evidence
                for row in rows
                if (evidence := self._combined_field_evidence_from_row(row, "测风塔编号", "windResourceCombined")) is not None
            ]
            name, unit = self.required_field_meta.get("windResourceTowerCodes", ("测风塔编号", None))
            if tower_evidences:
                self._set_field_with_evidence(fields, "windResourceTowerCodes", name, tower_codes, unit, tower_evidences)
            else:
                self._set_field(
                    fields,
                    "windResourceTowerCodes",
                    name,
                    tower_codes,
                    unit,
                    "资源章节动态测风塔编号。",
                    source_type="paragraph",
                    meta={"resolver": "wind_resource_tower_codes"},
                )

        metric_specs = (
            ("hubHeightAverageWindSpeedRecords", "轮毂高度平均风速m/s", "m/s"),
            ("hubHeightAverageWindPowerDensityRecords", "轮毂高度平均风功率密度W/m²", "W/m²"),
        )
        for field_code, source_key, unit in metric_specs:
            if field_code in skip_codes:
                continue
            records: list[dict[str, Any]] = []
            evidences: list[FieldEvidence] = []
            for row in rows:
                value = self._empty_to_none(row.get(source_key))
                if not self._wind_resource_record_value_present(value):
                    continue
                records.append(
                    self._wind_resource_value_record(
                        row.get("测风塔编号"),
                        row.get("_hubHeight"),
                        value,
                        unit,
                    )
                )
                evidence = self._combined_field_evidence_from_row(row, source_key, "windResourceCombined")
                if evidence is not None:
                    evidences.append(evidence)
            self._set_wind_resource_collection_field(fields, field_code, records, unit, evidences)

        if "windResourceAirDensityRecords" not in skip_codes:
            density_records: list[dict[str, Any]] = []
            density_evidences: list[FieldEvidence] = []
            for row in rows:
                tower_code = row.get("测风塔编号")
                height_densities = row.get("_heightAirDensities") or {}
                for height_key, density_item in height_densities.items():
                    value = self._empty_to_none(self._resource_value(density_item, None))
                    if not self._wind_resource_record_value_present(value):
                        continue
                    density_records.append(
                        self._wind_resource_value_record(
                            tower_code,
                            self._height_number(height_key),
                            value,
                            "kg/m³",
                        )
                    )
                    source = self._resource_source(density_item)
                    if source:
                        evidence = self._combined_field_evidence_from_row(
                            {"_rowSource": source},
                            "高度对应的空气密度",
                            "windResourceCombined",
                        )
                        if evidence is not None:
                            density_evidences.append(evidence)
                if height_densities:
                    continue
                fallback_value = self._empty_to_none(row.get("高度对应的空气密度"))
                if not self._wind_resource_record_value_present(fallback_value):
                    continue
                density_records.append(
                    self._wind_resource_value_record(
                        tower_code,
                        row.get("_hubHeight"),
                        fallback_value,
                        "kg/m³",
                    )
                )
                evidence = self._combined_field_evidence_from_row(row, "高度对应的空气密度", "windResourceCombined")
                if evidence is not None:
                    density_evidences.append(evidence)
            self._set_wind_resource_collection_field(
                fields,
                "windResourceAirDensityRecords",
                density_records,
                "kg/m³",
                density_evidences,
            )

        if "windResourceTurbulenceIntensityRecords" not in skip_codes:
            turbulence_records, turbulence_evidences = self._wind_resource_turbulence_records(ast, rows)
            self._set_wind_resource_collection_field(
                fields,
                "windResourceTurbulenceIntensityRecords",
                turbulence_records,
                None,
                turbulence_evidences,
            )

    def _wind_resource_value_record(
        self,
        tower_code: Any,
        height: Any,
        value: Any,
        unit: str,
    ) -> dict[str, Any]:
        """构建统一的风资源数值记录。"""
        return {
            "tower_code": self._normalize_tower_code(str(tower_code or "")) or None,
            "height": self._height_number(height),
            "height_unit": "m",
            "value": value,
            "unit": unit,
        }

    def _wind_resource_turbulence_records(
        self,
        ast: DocumentAST,
        combined_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[FieldEvidence]]:
        """抽取各测风塔、各高度的平均和代表性湍流强度。"""
        records: list[dict[str, Any]] = []
        evidences: list[FieldEvidence] = []
        seen: set[tuple[Any, ...]] = set()
        for table in self._resource_related_tables(ast):
            for row in self._wind_resource_turbulence_rows_from_table(ast, table):
                record = {
                    "tower_code": self._normalize_tower_code(str(row.get("测风塔编号") or "")) or None,
                    "height": self._height_number(row.get("高度")),
                    "height_unit": "m",
                    "wind_speed_segment": row.get("风速段"),
                    "wind_speed_unit": "m/s" if row.get("风速段") is not None else None,
                    "average_value": row.get("平均湍流强度"),
                    "representative_value": row.get("代表性湍流强度"),
                }
                identity = tuple(record.values())
                if identity in seen:
                    continue
                seen.add(identity)
                records.append(record)
                source_key = "代表性湍流强度" if row.get("代表性湍流强度") is not None else "平均湍流强度"
                evidence = self._combined_field_evidence_from_row(row, source_key, "windResourceTurbulenceIntensity")
                if evidence is not None:
                    evidences.append(evidence)
        if records:
            return records, evidences
        for row in combined_rows:
            value = self._empty_to_none(row.get("最大高度处代表性湍流强度"))
            if not self._wind_resource_record_value_present(value):
                continue
            records.append(
                {
                    "tower_code": self._normalize_tower_code(str(row.get("测风塔编号") or "")) or None,
                    "height": self._height_number(row.get("_turbulenceHeight") or row.get("_hubHeight")),
                    "height_unit": "m",
                    "wind_speed_segment": None,
                    "wind_speed_unit": None,
                    "average_value": None,
                    "representative_value": value,
                }
            )
            evidence = self._combined_field_evidence_from_row(
                row,
                "最大高度处代表性湍流强度",
                "windResourceCombined",
            )
            if evidence is not None:
                evidences.append(evidence)
        return records, evidences

    def _wind_resource_record_value_present(self, value: Any) -> bool:
        """判断风资源记录是否包含真实值，过滤对齐用占位符。"""
        return value is not None and str(value).strip() not in {"", "---", "--", "/", "无", "未提及"}

    def _set_wind_resource_collection_field(
        self,
        fields: dict[str, ParsedField],
        field_code: str,
        records: list[dict[str, Any]],
        unit: str | None,
        evidences: list[FieldEvidence],
    ) -> None:
        """仅在存在有效记录时写入风资源集合字段。"""
        if not records:
            fields.pop(field_code, None)
            return
        name, configured_unit = self.required_field_meta.get(field_code, (field_code, unit))
        final_unit = unit if unit is not None else configured_unit
        if evidences:
            self._set_field_with_evidence(fields, field_code, name, records, final_unit, evidences)
        else:
            self._set_field(
                fields,
                field_code,
                name,
                records,
                final_unit,
                "风资源正文/表格通用集合抽取。",
                source_type="table",
                meta={"resolver": "wind_resource_collection"},
            )

    def _height_number(self, value: Any) -> Any:
        """把“120m”“120 米”等高度统一为数值。"""
        if value is None:
            return None
        match = re.search(r"[0-9]+(?:\.[0-9]+)?", str(value))
        return self._normalize_scalar(match.group(0)) if match else None

    def _valid_wind_speed_50_year(self, value: Any) -> bool:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return 15 <= number <= 60

    def _valid_avg_wind_speed(self, value: Any) -> bool:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return 2 <= number <= 12

    def _max_wind_speed_50_year_from_document(self, ast: DocumentAST) -> Any:
        text = "\n".join(self._clean_text(block.text) for block in ast.blocks if block.text)
        table_text = "\n".join(self._table_text(table) for table in ast.tables)
        combined = f"{text}\n{table_text}"
        final_projection_value = self._max_wind_speed_50_year_projection_from_blocks(ast)
        if final_projection_value is not None:
            return final_projection_value
        multi_method_value = self._max_wind_speed_50_year_multi_method_value(combined)
        if multi_method_value is not None:
            return multi_method_value
        projection_value = self._resource_max_wind_speed_projection_value(ast)
        if projection_value is not None:
            return projection_value
        candidates: list[tuple[int, int, Any]] = []
        for segment in re.split(r"[\n\u3002\uff1b;]", combined):
            if not re.search(r"50\s*\u5e74\s*\u4e00\s*\u9047", segment, flags=re.IGNORECASE):
                continue
            if "最大风速" not in segment:
                continue
            for keyword in re.finditer(r"50\s*\u5e74\s*\u4e00\s*\u9047[^\uff0c\u3001\u3002\uff1b;]{0,60}?\u6700\u5927(?:10\s*min)?(?:\u5e73\u5747)?\u98ce\u901f", segment, flags=re.IGNORECASE):
                search_text = segment[keyword.end():keyword.end() + 90]
                match = re.search(r"(?:\u4e3a|\u503c|[:\uff1a])?\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s", search_text, flags=re.IGNORECASE)
                if match is None:
                    continue
                prefix = segment[max(0, match.start() - 8):match.start()]
                if re.search(r"(?:\u5c0f\u4e8e|\u4f4e\u4e8e|\u4e0d\u5927\u4e8e|[<\u2264])\s*$", prefix):
                    continue
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    score = self._max_wind_speed_50_year_segment_score(segment)
                    candidates.append((score, keyword.start(), value))
        if candidates:
            return sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)[0][2]
        patterns = [
            r"50\s*\u5e74\s*\u4e00\s*\u9047[^\n\uff0c\u3002\uff1b;]{0,40}?(?:\u6700\u5927)?\u98ce\u901f(?:\u503c)?[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*m/s",
            r"(?:\u6700\u5927\u98ce\u901f\u503c|\u6700\u5927\u98ce\u901f)[^\n\uff0c\u3002\uff1b;]{0,20}?50\s*\u5e74\s*\u4e00\s*\u9047[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*m/s",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, combined, flags=re.IGNORECASE):
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    return value
        return None

    def _max_wind_speed_50_year_projection_from_blocks(self, ast: DocumentAST) -> Any:
        candidates: list[tuple[int, Any]] = []
        for block in self._blocks_in_sections(ast, ["\u98ce\u80fd\u8d44\u6e90", "\u8d44\u6e90\u7ae0\u8282", "\u8d44\u6e90"]):
            text = self._clean_text(block.text or "")
            if not re.search(r"50\s*\u5e74\s*\u4e00\s*\u9047", text, flags=re.IGNORECASE) or "\u6700\u5927\u98ce\u901f" not in text:
                continue
            for match in re.finditer(r"\u63a8\u7b97(?:\u81f3|\u5230)\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s", text, flags=re.IGNORECASE):
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    candidates.append((80, value))
            for match in re.finditer(r"\u63a8\u7b97\u81f3\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s", text, flags=re.IGNORECASE):
                value = self._normalize_scalar(match.group(1))
                if not self._valid_wind_speed_50_year(value):
                    continue
                score = 20
                if "\u516c\u5f0f\u8ba1\u7b97" in text or "\u6362\u7b97\u6210\u6807\u51c6\u7a7a\u6c14\u5bc6\u5ea6" in text:
                    score += 30
                if "\u5b9e\u6d4b\u6700\u5927\u98ce\u901f\u7edf\u8ba1" in text:
                    score -= 20
                candidates.append((score, value))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], float(item[1])), reverse=True)
        return candidates[0][1]

    def _resource_max_wind_speed_projection_value(self, ast: DocumentAST) -> Any:
        for block in self._blocks_in_sections(ast, ["\u98ce\u80fd\u8d44\u6e90", "\u8d44\u6e90\u7ae0\u8282", "\u8d44\u6e90"]):
            text = self._clean_text(block.text or "")
            if "\u5b9e\u6d4b\u6700\u5927\u98ce\u901f" not in text or "\u63a8\u7b97\u81f3" not in text:
                continue
            match = re.search(r"\u63a8\u7b97\u81f3\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s", text, flags=re.IGNORECASE)
            if match:
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    return value
        return None

    def _max_wind_speed_50_year_multi_method_value(self, text: str) -> Any:
        all_candidates: list[Any] = []
        strong_candidates: list[Any] = []
        standard_density_candidates: list[Any] = []
        value_pattern = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s", flags=re.IGNORECASE)
        for segment in re.split(r"[\n\u3002\uff1b;]", text):
            if not re.search(r"50\s*\u5e74\s*\u4e00\s*\u9047", segment, flags=re.IGNORECASE) or "最大风速" not in segment:
                continue
            for match in value_pattern.finditer(segment):
                value = self._normalize_scalar(match.group(1))
                if not self._valid_wind_speed_50_year(value):
                    continue
                prefix = segment[max(0, match.start() - 12):match.start()]
                if re.search(r"(?:小于|低于|不大于|不超过|[<≤])\s*$", prefix):
                    continue
                all_candidates.append(value)
                strong_prefix = segment[max(0, match.start() - 60):match.start()]
                standard_density_prefix = segment[max(0, match.start() - 80):match.start()]
                if "标准空气密度" in standard_density_prefix and re.search(r"(?:订正到|订正至|换算成|换算至|折算到|折算至)", standard_density_prefix):
                    standard_density_candidates.append(value)
                if re.search(r"(?:推算至|推算到|折算至|换算至|得到|取值|较大值|最终)", strong_prefix):
                    strong_candidates.append(value)
        candidates = strong_candidates or standard_density_candidates or all_candidates
        if not candidates:
            return None
        return max(candidates, key=lambda item: float(item))

    def _max_wind_speed_50_year_segment_score(self, segment: str) -> int:
        score = 0
        if any(keyword in segment for keyword in ("初步估算", "初步判定", "判定", "选用", "安全等级")):
            score += 100
        if re.search(r"(?:\u5c0f\u4e8e|<)\s*37\.5\s*m\s*/\s*s", segment, flags=re.IGNORECASE):
            score += 80
        if "IEC" in segment or "III" in segment or "Ⅲ" in segment:
            score += 40
        if "10min" in segment or "10 min" in segment or "平均风速" in segment:
            score -= 30
        if "介于" in segment or "～" in segment or "~" in segment:
            score -= 20
        return score
