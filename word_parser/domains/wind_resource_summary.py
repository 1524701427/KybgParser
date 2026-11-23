"""测风塔、风速风功率、湍流和资源汇总抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable


class WindResourceSummaryRulesMixin:
    """测风塔、风速风功率、湍流和资源汇总抽取，通过 WindResourceRulesMixin 组合到结果构建器。"""

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
        # 正文中的并列列表必须按明确的测风塔顺序关联。
        # 否则通用汇总抽取可能将同一个区域性
        # 风速或功率密度值重复赋给段落中的每座测风塔。
        for code, explicit in self._parallel_tower_speed_power_from_text(ast, tower_codes).items():
            summary = summary_by_tower.setdefault(code, {"_cellSources": {}, "directions": {}})
            for metric in ("windSpeed", "powerDensity", "height"):
                if metric in explicit:
                    summary[metric] = explicit[metric]
            summary.setdefault("_cellSources", {}).update(explicit.get("_cellSources") or {})
        shear_from_summary = self._resource_shear_from_summary(ast, tower_codes)
        shear_from_tables = self._resource_shear_from_tables(ast, tower_codes)
        for code in tower_codes:
            shear = shear_from_summary.get(code) or shear_from_tables.get(code)
            if shear is None:
                continue
            summary = summary_by_tower.setdefault(code, {"_cellSources": {}, "directions": {}})
            summary["shear"] = shear["value"]
            summary.setdefault("_cellSources", {})["综合风切变"] = shear["_source"]
        for table in self._resource_related_tables(ast):
            for turbulence_row in self._wind_resource_turbulence_rows_from_speed_table(ast, table):
                code = turbulence_row["测风塔编号"]
                if code not in tower_codes:
                    continue
                summary = summary_by_tower.setdefault(code, {"_cellSources": {}, "directions": {}})
                summary["turbulence"] = turbulence_row["代表性湍流强度"]
                summary["turbulenceHeight"] = turbulence_row["高度"]
                summary.setdefault("_cellSources", {})["最大高度处代表性湍流强度"] = (
                    turbulence_row["_cellSources"]["代表性湍流强度"]
                )
        rows: list[dict[str, Any]] = []
        for code in tower_codes:
            summary = summary_by_tower.get(code, {})
            directions = {**direction_by_tower.get(code, {}), **summary.get("directions", {})}
            generation_use_default = None
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
        self._fill_resource_rows_from_pdf_text(ast, rows)
        return rows

    def _fill_resource_rows_from_pdf_text(self, ast: DocumentAST, rows: list[dict[str, Any]]) -> None:
        """PDF 表格单元格被展平为文本行时，恢复带标签的测风塔数据。"""
        pages = [item for item in ((ast.meta or {}).get("pdf_page_lines") or (ast.meta or {}).get("pdf_page_texts") or []) if isinstance(item, dict)]
        if not pages or not rows:
            return
        by_code = {str(row.get("测风塔编号")): row for row in rows}
        def source(page: Any, evidence: str) -> dict[str, Any]:
            return {
                "source": {"kind": "document_text", "sourceType": "paragraph", "page": page,
                           "sourceText": evidence, "matchMethod": "pdf_tower_table_text"},
                "process": {"resolver": "pdf_tower_table_text"},
            }
        overview = "\n".join(str(item.get("text") or "") for item in pages if "测风塔资料一览表" in str(item.get("text") or "") or "测风时间段" in str(item.get("text") or ""))
        tower_pattern = re.compile(
            domain_regex(self, "wind_resource_summary", "compile_001", r"(?m)^\s*(?P<code>\d{4}#)\s*\n\s*(?P<lat>\d{1,2}°[^\n]{3,25})\s*\n")
            r"\s*(?P<lon>\d{2,3}°[^\n]{3,25})\s*\n\s*\d{3,4}\s*\n"
            r"\s*(?P<period>\d{4}\.\d{1,2}\.\d{1,2}\s*[~～-]\s*\d{4}\.\d{1,2}\.\d{1,2})"
        )
        for match in tower_pattern.finditer(overview):
            row = by_code.get(match.group("code"))
            if row is None:
                continue
            for key, value in (("测风塔纬度", match.group("lat")), ("测风塔经度", match.group("lon")), ("测风周期", match.group("period"))):
                if row.get(key) in (None, "", "---"):
                    row[key] = value.strip()
                    page = next((item.get("page") for item in pages if match.group("code") in str(item.get("text") or "") and match.group("period") in str(item.get("text") or "")), None)
                    row.setdefault("_cellSources", {})[key] = source(page, match.group(0))

        for item in pages:
            text = str(item.get("text") or "")
            if "各测风塔各高度风速及风功率" not in text and "测风塔订正后各高度风速及风功率" not in text:
                continue
            codes = re.findall(domain_regex(self, "wind_resource_summary", "findall_002", r"\b\d{4}#"), text[:250])
            match = re.search(r"(?m)^\s*105\s*\n" + r"\s*(\d+(?:\.\d+)?)\s*\n" * (2 * len(codes)), text) if codes else None
            if not match:
                continue
            for index, code in enumerate(codes):
                row = by_code.get(code)
                if row is None:
                    continue
                for key, value in (("轮毂高度平均风速m/s", float(match.group(index * 2 + 1))), ("轮毂高度平均风功率密度W/m²", float(match.group(index * 2 + 2)))):
                    if row.get(key) in (None, "", "---"):
                        row[key] = value
                        row.setdefault("_cellSources", {})[key] = source(item.get("page"), match.group(0))
                if row.get("_hubHeight") is None:
                    row["_hubHeight"] = 105
            break

        for item in pages:
            text = str(item.get("text") or "")
            if "空气密度" not in text:
                continue
            for match in re.finditer(domain_regex(self, "wind_resource_summary", "finditer_003", r"(?P<code>\d{4}#)\s*测风塔[^。；;]{0,100}?空气密度为\s*(?P<density>\d(?:\.\d+)?)\s*kg/m[³3]"), text):
                row = by_code.get(match.group("code"))
                if row is not None and row.get("高度对应的空气密度") in (None, "", "---"):
                    row["高度对应的空气密度"] = float(match.group("density"))
                    row.setdefault("_cellSources", {})["高度对应的空气密度"] = source(item.get("page"), match.group(0))

        # PDF 中常以一句话列出测风塔推算高度、风速和风功率，表格抽取器不会生成这一行。
        speed_power_pattern = re.compile(
            domain_regex(self, "wind_resource_summary", "compile_004", r"(?P<code>\d{3,5}#)\s*测风塔\s*(?P<height>\d{2,3})\s*m")
            r"[^。；;\n]{0,45}?高度平均风速和风功率密度分别为\s*"
            r"(?P<speed>\d+(?:\.\d+)?)\s*m/s\s*和\s*"
            r"(?P<power>\d+(?:\.\d+)?)\s*W/m[²2]"
        )
        for item in pages:
            text = str(item.get("text") or "")
            for match in speed_power_pattern.finditer(text):
                row = by_code.get(match.group("code"))
                if row is None:
                    continue
                for key, value in (
                    ("轮毂高度平均风速m/s", float(match.group("speed"))),
                    ("轮毂高度平均风功率密度W/m²", float(match.group("power"))),
                ):
                    if row.get(key) in (None, "", "---"):
                        row[key] = value
                        row.setdefault("_cellSources", {})[key] = source(item.get("page"), match.group(0))
                row["_hubHeight"] = int(match.group("height"))

        # 轮毂高度密度只归给报告明确作为推算基准的测风塔。
        density_pattern = re.compile(
            domain_regex(self, "wind_resource_summary", "compile_005", r"以\s*(?P<code>\d{3,5}#)\s*测风塔为基准[^。；;]{0,100}?")
            r"轮毂高度处的空气密度\s*为\s*(?P<density>\d+(?:\.\d+)?)\s*kg/m[³3]"
        )
        for item in pages:
            for match in density_pattern.finditer(str(item.get("text") or "")):
                row = by_code.get(match.group("code"))
                if row is None:
                    continue
                value = float(match.group("density"))
                row["高度对应的空气密度"] = value
                row.setdefault("_cellSources", {})["高度对应的空气密度"] = source(item.get("page"), match.group(0))
                height = row.get("_hubHeight")
                if isinstance(height, (int, float)):
                    row.setdefault("_heightAirDensities", {})[f"{int(height)}m"] = {
                        "value": value, "_source": source(item.get("page"), match.group(0))
                    }
                    if int(height) == 160:
                        row["160m高度空气密度"] = value

        # 测风时长不足的塔仅被提及，随后出现的全场密度不能复制为逐塔轮毂密度。
        insufficient_pattern = re.compile(
            domain_regex(self, "wind_resource_summary", "compile_006", r"(?P<codes>(?:\d{3,5}#[、，,]?\s*)+)测风塔测风时长不足")
            r"[^。]{0,80}?使用\s*(?P<reference>\d{3,5}#)\s*测风塔"
            r"[^。]{0,150}?该风电\s*场的空气密度为\s*(?P<density>\d+(?:\.\d+)?)"
        )
        for item in pages:
            for match in insufficient_pattern.finditer(str(item.get("text") or "")):
                density = float(match.group("density"))
                for code in re.findall(domain_regex(self, "wind_resource_summary", "findall_007", r"\d{3,5}#"), match.group("codes")):
                    row = by_code.get(code)
                    if row is not None and row.get("高度对应的空气密度") == density:
                        row["高度对应的空气密度"] = "---"
                        row.get("_cellSources", {}).pop("高度对应的空气密度", None)

    def _resource_shear_from_summary(self, ast: DocumentAST, tower_codes: list[str]) -> dict[str, dict[str, Any]]:
        """优先采用汇总中明确标注的综合切变指数。"""
        result: dict[str, dict[str, Any]] = {}
        pattern = re.compile(domain_regex(self, "wind_resource_summary", "compile_008", r"综合风切变指数\s*(?:为|是|取|：|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), re.I)
        for block in self._body_blocks(ast):
            if not any("小结" in str(part) for part in (block.section_path or [])):
                continue
            content = self._clean_text(block.text or "")
            match = pattern.search(content)
            if not match:
                continue
            value = self._normalize_scalar(match.group(1))
            codes = [code for code in self._tower_codes_in_text(content) if code in tower_codes] or tower_codes
            source = self._text_block_source(
                block, match.group(0), "小结综合风切变指数抽取。", resolver="wind_resource_shear_summary"
            )
            for code in codes:
                result[code] = {"value": value, "_source": source}
        return result

    def _resource_shear_from_tables(self, ast: DocumentAST, tower_codes: list[str]) -> dict[str, dict[str, Any]]:
        """将拟合或综合切变值关联到对应测风塔编号。"""
        result: dict[str, dict[str, Any]] = {}
        title_pattern = re.compile(domain_regex(self, "wind_resource_summary", "compile_009", r"风切变指数计算成果|切变统计|风切变指数统计"))
        value_labels = ("综合风切变系数", "综合风切变", "拟合值")
        known = set(tower_codes)
        for table in self._resource_related_tables(ast):
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            if not title_pattern.search(caption):
                continue
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            header_index = None
            value_column = None
            tower_column = None
            for index, row in enumerate(matrix[: min(len(matrix), 8)]):
                for column, cell in enumerate(row):
                    label = self._compact_text(cell)
                    if any(key in label for key in value_labels):
                        header_index, value_column = index, column
                    if "测风塔" in label or "塔号" in label:
                        tower_column = column
                if value_column is not None:
                    break
            if value_column is not None:
                current_tower = None
                for row_index, row in enumerate(matrix[header_index + 1 :], start=header_index + 1):
                    tower_cell = row[tower_column] if tower_column is not None and tower_column < len(row) else ""
                    candidates = self._tower_codes_in_text(tower_cell) or self._tower_codes_in_text(" ".join(row))
                    if candidates:
                        current_tower = candidates[0]
                    if not current_tower or (known and current_tower not in known):
                        continue
                    value = self._normalize_table_cell(row[value_column] if value_column < len(row) else "")
                    if value is None:
                        continue
                    result.setdefault(current_tower, {
                        "value": value,
                        "_source": self._table_cell_source(
                            table, row_index, value_column,
                            "风切变统计表按测风塔编号读取综合值或拟合值。",
                            resolver="wind_resource_shear_table",
                        ),
                    })
            # 部分报告将测风塔编号放在列中，切变标签放在行中。
            tower_columns: dict[int, str] = {}
            for row_index, row in enumerate(matrix):
                for column, cell in enumerate(row):
                    codes = self._tower_codes_in_text(cell)
                    if codes:
                        tower_columns[column] = codes[0]
                    if self._compact_text(cell) not in value_labels:
                        continue
                    row_towers = self._tower_codes_in_text(" ".join(row))
                    for value_column_index in range(column + 1, len(row)):
                        value = self._normalize_table_cell(row[value_column_index])
                        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                            continue
                        tower = tower_columns.get(value_column_index)
                        if not tower and len(row_towers) == 1:
                            tower = row_towers[0]
                        if not tower and len(known) == 1:
                            tower = next(iter(known))
                        if not tower or (known and tower not in known):
                            continue
                        result.setdefault(tower, {
                            "value": value,
                            "_source": self._table_cell_source(
                                table, row_index, value_column_index,
                                "风切变统计表按行标签和测风塔编号读取综合值或拟合值。",
                                resolver="wind_resource_shear_table",
                            ),
                        })
        return result

    def _parallel_tower_speed_power_from_text(
        self, ast: DocumentAST, tower_codes: list[str]
    ) -> dict[str, dict[str, Any]]:
        """按相同顺序读取各测风塔的风速和功率值列表。"""
        result: dict[str, dict[str, Any]] = {}
        known = set(tower_codes)
        pattern = re.compile(
            domain_regex(self, "wind_resource_summary", "compile_010", r"年平均风速分别为(?P<speeds>[^。；;\n]{0,220}?)")
            r"(?:相对应|对应)?风功率密度分别为(?P<powers>[^。；;\n]{0,220})"
        )
        for block in self._body_blocks(ast):
            text = self._clean_text(block.text or "")
            match = pattern.search(text)
            if not match:
                continue
            prefix = text[: match.start()]
            towers = [code for code in dict.fromkeys(self._tower_codes_in_text(prefix)) if code in known]
            speeds = re.findall(domain_regex(self, "wind_resource_summary", "findall_011", r"([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), match.group("speeds"), re.I)
            powers = re.findall(domain_regex(self, "wind_resource_summary", "findall_012", r"([0-9]+(?:\.[0-9]+)?)\s*W\s*/\s*m(?:2|²)"), match.group("powers"), re.I)
            if not towers or len(towers) != len(speeds) or len(towers) != len(powers):
                continue
            height_match = re.search(domain_regex(self, "wind_resource_summary", "search_013", r"([0-9]+(?:\.[0-9]+)?)\s*m\s*高度"), prefix[-80:], re.I)
            height = self._normalize_scalar(height_match.group(1)) if height_match else None
            source = self._text_block_source(
                block, match.group(0), "按原文塔号顺序对应年均风速和风功率密度。",
                resolver="wind_resource_parallel_tower_summary_text",
            )
            for tower, speed, power in zip(towers, speeds, powers):
                values: dict[str, Any] = {
                    "windSpeed": self._normalize_scalar(speed),
                    "powerDensity": self._normalize_scalar(power),
                    "_cellSources": {
                        "轮毂高度平均风速m/s": source,
                        "轮毂高度平均风功率密度W/m²": source,
                    },
                }
                if height is not None:
                    values["height"] = height
                result[tower] = values
        return result

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
                if re.search(domain_regex(self, "wind_resource_summary", "search_014", r"年\s*(?:均|平均)|平均"), text) and "风速" not in text and "风功率" not in text:
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
                match = re.search(domain_regex(self, "wind_resource_summary", "search_015", r"([0-9]+(?:\.[0-9]+)?)\s*m"), self._clean_text(cell), flags=re.IGNORECASE)
                if match:
                    columns.append((float(match.group(1)), column_index))
            if columns:
                return row_index, columns
        return 0, []

    def _wind_resource_turbulence_intensity_table_from_document(self, ast: DocumentAST) -> dict[str, Any] | None:
        rows: list[dict[str, Any]] = []
        rows_by_height: dict[tuple[Any, Any], dict[str, Any]] = {}
        for table in self._resource_related_tables(ast):
            extracted = self._wind_resource_turbulence_rows_from_table(ast, table)
            for row in extracted:
                key = (row.get("测风塔编号"), self._height_number(row.get("高度")))
                existing = rows_by_height.get(key)
                if existing is None:
                    rows_by_height[key] = row
                    rows.append(row)
                    continue
                if row.get("平均湍流强度") is not None and (
                    existing.get("平均湍流强度") is None
                    or (existing.get("风速段") is not None and row.get("风速段") is None)
                ):
                    existing["平均湍流强度"] = row["平均湍流强度"]
                    existing["风速段"] = row.get("风速段")
                if existing.get("代表性湍流强度") is None and row.get("代表性湍流强度") is not None:
                    existing["代表性湍流强度"] = row["代表性湍流强度"]
                existing.setdefault("_cellSources", {}).update(row.get("_cellSources", {}))
        if not rows:
            return None
        columns = ["测风塔编号", "高度", "平均湍流强度", "代表性湍流强度"]
        data = [[row.get(column) for column in columns] for row in rows]
        return {
            "key": "windResourceTurbulenceIntensity",
            "name": "湍流强度",
            "columns": columns,
            "columnKeys": ["towerCode", "height", "averageTurbulenceIntensity", "representativeTurbulenceIntensity"],
            "index": list(range(len(data))),
            "data": data,
            "rows": rows,
        }

    def _wind_resource_turbulence_rows_from_table(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        matrix = self._table_matrix(table)
        if len(matrix) < 2:
            return []
        caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
        horizontal_rows = self._horizontal_turbulence_rows(ast, table, matrix, caption)
        if horizontal_rows:
            return horizontal_rows
        table_text = self._table_text(table)
        combined = f"{caption}\n{table_text}"
        if "湍流" not in combined or "高度" not in combined:
            return self._wind_resource_turbulence_rows_from_speed_table(ast, table)
        header_index, columns = self._turbulence_intensity_columns(matrix)
        if columns.get("height") is None or (
            columns.get("average") is None and columns.get("representative") is None
        ):
            return self._wind_resource_turbulence_rows_from_speed_table(ast, table)
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

    def _horizontal_turbulence_rows(
        self, ast: DocumentAST, table: DocumentTable, matrix: list[list[str]], caption: str,
    ) -> list[dict[str, Any]]:
        """解析“高度为列、平均值和代表性湍流为行”的测风塔表。"""
        header_index = -1
        heights: list[tuple[int, Any]] = []
        for index, row in enumerate(matrix[:4]):
            columns = []
            for column, cell in enumerate(row[1:], start=1):
                if re.fullmatch(domain_regex(self, "wind_resource_summary", "fullmatch_016", r"\s*[0-9]+(?:\.[0-9]+)?\s*(?:m|米)\s*"), str(cell), re.I):
                    columns.append((column, self._height_cell_value(str(cell))))
            if len(columns) >= 2:
                header_index, heights = index, columns
                break
        if header_index < 0:
            return []
        page_text = next(
            (str(page.get("text", "")) for page in ast.meta.get("pdf_page_texts", [])
             if isinstance(page, dict) and page.get("page") == table.page),
            "",
        )
        title = re.search(
            domain_regex(self, "wind_resource_summary", "search_017", r"表\s*[0-9]+(?:[-－—.][0-9]+)*\s*[:：]\s*([A-Za-z0-9_-]+\s*[#＃])\s*测风塔[^。\n]{0,24}?湍流"),
            page_text,
            re.I,
        )
        tower = self._tower_code_from_text(title.group(1) if title else caption)
        if not tower:
            return []
        overall: list[str] | None = None
        segmented: list[str] | None = None
        representative: list[str] | None = None
        segment: Any = None
        row_indices: dict[str, int] = {}
        for index, row in enumerate(matrix[header_index + 1:], start=header_index + 1):
            label = self._compact_text(row[0] if row else "")
            if "代表" in label and "湍流" in label:
                representative, row_indices["representative"] = row, index
            elif "平均" in label:
                speed = re.search(domain_regex(self, "wind_resource_summary", "search_018", r"([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), label, re.I)
                if speed:
                    segmented, segment, row_indices["segmented"] = row, self._normalize_scalar(speed.group(1)), index
                else:
                    overall, row_indices["overall"] = row, index
        if overall is None and segmented is None and representative is None:
            return []
        if "湍流" not in caption and (title is None or representative is None):
            return []
        # 同页也可能有平均风速、风功率密度等高度列；湍流强度必须处于合理量纲。
        measurements = [
            self._normalize_table_cell(row[column])
            for row in (overall, segmented, representative) if row is not None
            for column, _ in heights if column < len(row)
        ]
        if any(isinstance(value, (int, float)) and not 0 <= value <= 1 for value in measurements):
            return []

        result: list[dict[str, Any]] = []
        for column, height in heights:
            def cell_value(row: list[str] | None) -> Any:
                value = self._normalize_table_cell(row[column]) if row is not None and column < len(row) else None
                return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

            average = cell_value(overall)
            at_speed = cell_value(segmented)
            representative_value = cell_value(representative)
            selected_average = average if average is not None else at_speed
            if selected_average is None and representative_value is None:
                continue
            cell_sources = {}
            if selected_average is not None:
                average_row = "overall" if average is not None else "segmented"
                cell_sources["平均湍流强度"] = self._table_cell_source(
                    table, row_indices[average_row], column, "各高度平均湍流强度。",
                    resolver="wind_resource_turbulence_horizontal_table",
                )
            if representative_value is not None:
                cell_sources["代表性湍流强度"] = self._table_cell_source(
                    table, row_indices["representative"], column, "各高度代表性湍流强度。",
                    resolver="wind_resource_turbulence_horizontal_table",
                )
            result.append({
                "测风塔编号": tower, "高度": height,
                "平均湍流强度": selected_average,
                "代表性湍流强度": representative_value,
                "风速段": segment if average is None else None,
                "_cellSources": cell_sources,
            })
        return result

    def _wind_resource_turbulence_rows_from_speed_table(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        """从逐塔风速段表提取 15m/s 处的平均值与代表性值。"""
        matrix = self._table_matrix(table)
        caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or "")
        if "湍流" not in caption or not any("风速段" in " ".join(row) and "平均湍流强度" in " ".join(row) for row in matrix[:30]):
            return []
        heights: dict[str, Any] = {}
        for block in ast.blocks:
            if not (table.order < block.order <= table.order + 12):
                continue
            text = self._clean_text(block.text or "")
            if "图" not in text or "湍流" not in text:
                continue
            tower = self._tower_code_from_text(text)
            height_match = re.search(domain_regex(self, "wind_resource_summary", "search_019", r"([0-9]+(?:\.[0-9]+)?)\s*m\s*高度"), text, flags=re.IGNORECASE)
            if tower and height_match:
                heights[tower] = self._normalize_scalar(height_match.group(1))
        rows: list[dict[str, Any]] = []
        tower: str | None = None
        average_col: int | None = None
        representative_col: int | None = None
        for row_index, row in enumerate(matrix):
            values = [self._clean_text(value) for value in row]
            if len(values) == 1:
                tower = self._tower_code_from_text(values[0])
                average_col = representative_col = None
                continue
            if any("风速段" in value for value in values):
                average_col = next((i for i, value in enumerate(values) if "平均湍流强度" in value), None)
                representative_col = next((i for i, value in enumerate(values) if "代表性湍流强度" in value), None)
                continue
            if not tower or tower not in heights or average_col is None or representative_col is None:
                continue
            if not values or not re.fullmatch(domain_regex(self, "wind_resource_summary", "fullmatch_020", r"15(?:\.0+)?"), values[0]):
                continue
            if max(average_col, representative_col) >= len(values):
                continue
            average = self._normalize_table_cell(values[average_col])
            representative = self._normalize_table_cell(values[representative_col])
            if average is None or representative is None:
                continue
            rows.append({
                "测风塔编号": tower,
                "高度": heights[tower],
                "平均湍流强度": average,
                "代表性湍流强度": representative,
                "风速段": 15,
                "_cellSources": {
                    "平均湍流强度": self._table_cell_source(
                        table, row_index, average_col, "15m/s 风速段平均湍流强度列抽取。",
                        resolver="wind_resource_turbulence_speed_table",
                    ),
                    "代表性湍流强度": self._table_cell_source(
                        table, row_index, representative_col, "15m/s 风速段代表性湍流强度列抽取。",
                        resolver="wind_resource_turbulence_speed_table",
                    ),
                },
            })
        return rows

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
        match = re.search(domain_regex(self, "wind_resource_summary", "search_021", r"([A-Za-z0-9][A-Za-z0-9_-]{0,19})\s*#"), normalized_text)
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
            domain_regex(self, "wind_resource_summary", "findall_022", r"(?:V\s*=\s*)?([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"),
            text or "",
            flags=re.IGNORECASE,
        )
        return self._normalize_scalar(matches[-1]) if matches else None

    def _height_cell_value(self, text: str) -> str | None:
        clean = self._clean_text(text)
        match = re.search(domain_regex(self, "wind_resource_summary", "search_023", r"([0-9]+(?:\.[0-9]+)?)\s*(m|米)?"), clean, flags=re.IGNORECASE)
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
            for code in re.findall(domain_regex(self, "wind_resource_summary", "findall_024", r"[A-Za-z0-9]{2,8}#"), match.group(0)):
                code = self._normalize_tower_code(code)
                if code and code not in codes:
                    codes.append(code)
        for match in re.finditer("([A-Za-z0-9#\u3001,\uff0c\\s]+)#?\\s*\u6d4b\u98ce\u5854", text):
            for code in re.findall(domain_regex(self, "wind_resource_summary", "findall_025", r"[A-Za-z0-9]{2,8}#"), match.group(1) + "#"):
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
        for match in re.finditer(domain_regex(self, "wind_resource_summary", "finditer_026", r"(?:\u53ea\u91c7\u7528|\u91c7\u7528|\u4f7f\u7528)\s*([A-Za-z0-9]{2,8}#)[^\n\u3002\uff1b;]{0,120}?(?:\u8fdb\u884c\u5206\u6790|\u7a7a\u6c14\u5bc6\u5ea6|\u5e73\u5747\u98ce\u901f|\u98ce\u529f\u7387\u5bc6\u5ea6|\u7efc\u5408\u5206\u6790)"), text):
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
        direction_match = re.search(domain_regex(self, "wind_resource_summary", "search_027", r"(?:\u4e3b\u5bfc\u98ce\u5411|\u4e3b\u98ce\u5411)(?:\u4e3a|\u548c\u4e3b\u98ce\u80fd\u65b9\u5411\u4e00\u81f4\uff0c\u4ee5)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)"), text)
        secondary_direction_match = re.search(domain_regex(self, "wind_resource_summary", "search_028", r"(?:\u6b21\u4e3b\u5bfc\u98ce\u5411|\u6b21\u4e3b\u98ce\u5411|\u6b21\u98ce\u5411)(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)"), text)
        energy_match = re.search(domain_regex(self, "wind_resource_summary", "search_029", r"\u4e3b\u98ce\u80fd\u65b9\u5411(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)"), text)
        secondary_energy_match = re.search(domain_regex(self, "wind_resource_summary", "search_030", r"(?:\u6b21\u4e3b\u5bfc\u98ce\u80fd\u65b9\u5411|\u6b21\u4e3b\u98ce\u80fd\u65b9\u5411|\u6b21\u98ce\u80fd\u65b9\u5411)(?:\u4e3a)?\s*([^。，；;]+?(?:\uff09|\))?(?:\u3001[^。，；;]+?(?:\uff09|\))?)*)\s*(?:\u6247\u533a|\uff0c|,|。|；|;)"), text)
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
        cleaned = re.split(domain_regex(self, "wind_resource_summary", "split_031", r"(?:\u98ce\u7684|\u98ce\u5411\u548c|\u98ce\u80fd\u5206\u5e03|\u5206\u5e03\u9891\u7387)"), cleaned, maxsplit=1)[0]
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
