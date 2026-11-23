"""主次风向、风能方向和扇区统计抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable


class WindDirectionRulesMixin:
    """主次风向、风能方向和扇区统计抽取，通过 WindResourceRulesMixin 组合到结果构建器。"""

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
                    next_tower = re.search(domain_regex(self, "wind_resource_direction", "search_001", r"[A-Za-z0-9]{2,8}#"), text[position + len(code) : window_end])
                    if next_tower:
                        window_end = position + len(code) + next_tower.start()
                    window = text[position:window_end]
                    direction_match = re.search(domain_regex(self, "wind_resource_direction", "search_002", r"(?:主导风向|主风向)为\s*([A-Z]{1,4})"), window)
                    secondary_direction_match = re.search(domain_regex(self, "wind_resource_direction", "search_003", r"(?:次主导风向|次主风向|次风向)(?:为)?\s*([A-Z]{1,4})"), window)
                    energy_match = re.search(domain_regex(self, "wind_resource_direction", "search_004", r"(?:主导风能方向|主风能方向)为\s*([A-Z]{1,4})"), window)
                    secondary_energy_match = re.search(domain_regex(self, "wind_resource_direction", "search_005", r"(?:次主导风能方向|次主风能方向|次风能方向)(?:为)?\s*([A-Z]{1,4})"), window)
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
        page_titles: dict[int, list[str]] = {}
        for page in (ast.meta or {}).get("pdf_page_texts") or []:
            text = str(page.get("text") or "")
            titles = re.findall(domain_regex(self, "wind_resource_direction", "findall_006", r"表\s*\d+(?:[-－.]\d+)+\s*[：:]\s*([A-Za-z0-9]{2,8}#)\s*测风塔[^。\n]{0,50}风向[^。\n]{0,20}风能[^。\n]{0,30}(?:统计|分布|频率)"), text)
            if titles:
                page_titles[int(page["page"])] = list(dict.fromkeys(titles))
        frequency: dict[str, dict[str, dict[str, Any]]] = {}
        last_header: list[str] | None = None
        last_tower: str | None = None
        last_page: int | None = None
        for spec in specs:
            for table in self._original_tables_for_spec(ast, {"key_prefix": "resourceOriginalTable"}):
                caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
                page_codes = page_titles.get(table.page or -1) or []
                matrix = self._table_matrix(table)
                has_sector_header = bool(matrix and "扇区" in matrix[0][0] and any("风向" in cell for cell in matrix[0]) and any("风能" in cell for cell in matrix[0]))
                if has_sector_header and len(page_codes) == 1:
                    # PDF 表题有时被上一页标题覆盖；同页唯一的原文表题优先。
                    caption = re.sub(domain_regex(self, "wind_resource_direction", "sub_007", r"[A-Za-z0-9]{2,8}#(?=\s*测风塔)"), page_codes[0], caption, count=1)
                title_text = f"{caption}\n{self._section_path_caption(table)}"
                patterns = spec.get("patterns") or []
                if not has_sector_header and last_header and last_tower and last_page is not None and table.page in (last_page, last_page + 1):
                    if matrix and all(self._clean_direction_label(row[0]) for row in matrix if row):
                        self._collect_sector_frequency(table, matrix, last_header, last_tower, frequency, row_offset=0)
                        last_page = table.page
                        continue
                if patterns and not any(re.search(str(pattern), title_text, flags=re.IGNORECASE) for pattern in patterns):
                    continue
                tower_match = re.search(domain_regex(self, "wind_resource_direction", "search_008", r"([A-Za-z0-9]{2,8}#)\s*测风塔"), caption)
                if has_sector_header and tower_match:
                    last_tower = self._normalize_tower_code(tower_match.group(1))
                    last_header = matrix[0]
                    last_page = table.page
                    self._collect_sector_frequency(table, matrix[1:], last_header, last_tower, frequency, row_offset=1)
                    continue
                table_result = self._wind_direction_table_values(table, spec)
                for tower, values in table_result.items():
                    current = result.setdefault(tower, {})
                    current.update(values)
        for tower, targets in frequency.items():
            current = result.setdefault(tower, {})
            sources = current.setdefault("_cellSources", {})
            for main, secondary, label in (
                ("mainWindDirection", "secondaryWindDirection", "风向"),
                ("mainWindEnergyDirection", "secondaryWindEnergyDirection", "风能"),
            ):
                observations = targets.get(label, {}).get("scores", {})
                ranked = sorted(observations.items(), key=lambda item: (-item[1][0], item[0]))
                for target, item in zip((main, secondary), ranked[:2]):
                    current[target] = item[0]
                    sources[{"mainWindDirection": "轮毂高度处的主风向", "secondaryWindDirection": "轮毂高度处的次风向", "mainWindEnergyDirection": "轮毂高度处的主风能方向", "secondaryWindEnergyDirection": "轮毂高度处的次风能方向"}[target]] = item[1][1]
        return result

    def _collect_sector_frequency(self, table: DocumentTable, rows: list[list[str]], header: list[str], tower: str, frequency: dict[str, dict[str, dict[str, Any]]], row_offset: int) -> None:
        """累计逐塔扇区频率，跨页续表沿用上一页表头和塔号。"""
        if not tower or not header:
            return
        tower_data = frequency.setdefault(tower, {})
        for label in ("风向", "风能"):
            height_columns = []
            for index, heading in enumerate(header):
                match = re.search(domain_regex(self, "wind_resource_direction", "direction_dynamic_prefix", r"(\d+(?:\.\d+)?)\s*m\s*") + label, str(heading), re.I)
                if match:
                    height_columns.append((float(match.group(1)), index))
            if not height_columns:
                continue
            height, column = max(height_columns)
            metric = tower_data.setdefault(label, {"height": height, "scores": {}})
            if height > metric["height"]:
                metric.update(height=height, scores={})
            if height < metric["height"]:
                continue
            for row_index, row in enumerate(rows, start=row_offset):
                direction = self._clean_direction_label(row[0]) if row else None
                if not direction or column >= len(row):
                    continue
                value = self._numeric_sort_value(row[column])
                if value == float("-inf"):
                    continue
                previous = metric["scores"].get(direction)
                if previous is None or value > previous[0]:
                    source = self._table_cell_source(table, row_index, column, "按最高测风高度的扇区频率排序取得主次方向。", resolver="wind_resource_direction_frequency_table")
                    metric["scores"][direction] = (value, source)

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
            tower_candidates = [self._normalize_tower_code(code) for code in re.findall(domain_regex(self, "wind_resource_direction", "findall_009", r"[A-Za-z0-9]{2,8}#"), row_text)]
            if tower_index is not None and tower_index < len(row):
                tower_candidates = [self._normalize_tower_code(code) for code in re.findall(domain_regex(self, "wind_resource_direction", "findall_010", r"[A-Za-z0-9]{2,8}#"), row[tower_index])] or tower_candidates
            if tower_candidates:
                current_tower = tower_candidates[0]
            if not current_tower:
                continue
            direction = row[direction_index].strip() if direction_index < len(row) else ""
            if not re.fullmatch(domain_regex(self, "wind_resource_direction", "fullmatch_011", r"[A-Z]{1,4}"), direction):
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
            tower_candidates = [self._normalize_tower_code(code) for code in re.findall(domain_regex(self, "wind_resource_direction", "findall_012", r"[A-Za-z0-9]{2,8}#"), row_text)]
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
        match = re.search(domain_regex(self, "wind_resource_direction", "search_013", r"\b(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)\b"), text)
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
            if not re.fullmatch(domain_regex(self, "wind_resource_direction", "fullmatch_014", r"[A-Z]{1,4}"), direction):
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
