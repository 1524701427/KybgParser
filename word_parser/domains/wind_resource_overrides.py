"""资源标量覆盖、记录合并和极端风速抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST
from word_parser.document.ast.evidence import FieldEvidence, ParsedField


class WindResourceOverrideRulesMixin:
    """资源标量覆盖、记录合并和极端风速抽取，通过 WindResourceRulesMixin 组合到结果构建器。"""

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
        pattern = re.compile(domain_regex(self, "wind_resource_overrides", "compile_001", r"风功率密度等级[^。；;\n]{0,20}?(?:为|是)?\s*(?P<value>[A-ZＡ-Ｚ]-?\s*[0-9ⅠⅡⅢⅣⅤⅥ一二三四五六]+)\s*级?"))
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
                        None,
                        fallback_value,
                        "kg/m³",
                    )
                )
                evidence = self._combined_field_evidence_from_row(row, "高度对应的空气密度", "windResourceCombined")
                if evidence is not None:
                    density_evidences.append(evidence)
            if not density_records:
                tower_codes = self._resource_tower_codes(ast)
                if len(tower_codes) == 1:
                    for table in ast.tables:
                        matrix = self._table_matrix(table)
                        if not matrix or not any("测风塔" in cell for cell in matrix[0]):
                            continue
                        tower_column = next((index for index, cell in enumerate(matrix[0]) if "测风塔" in cell), None)
                        if tower_column is None:
                            continue
                        for table_row in matrix[1:]:
                            if len(table_row) <= tower_column or "空气密度" not in table_row[0]:
                                continue
                            height_match = re.search(domain_regex(self, "wind_resource_overrides", "search_002", r"[（(]\s*(\d{2,5})\s*m\s*[）)]"), table_row[0])
                            density_match = re.fullmatch(domain_regex(self, "wind_resource_overrides", "fullmatch_003", r"\s*(\d(?:\.\d+)?)\s*"), table_row[tower_column])
                            if not height_match or not density_match:
                                continue
                            density_records.append(self._wind_resource_value_record(
                                tower_codes[0], int(height_match.group(1)), float(density_match.group(1)), "kg/m³"
                            ))
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
        records_by_height: dict[tuple[Any, Any], dict[str, Any]] = {}
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
                key = (record["tower_code"], record["height"])
                existing = records_by_height.get(key)
                if existing is None:
                    records_by_height[key] = record
                    records.append(record)
                else:
                    if record["average_value"] is not None and (
                        existing["average_value"] is None
                        or (existing["wind_speed_segment"] is not None and record["wind_speed_segment"] is None)
                    ):
                        existing["average_value"] = record["average_value"]
                        existing["wind_speed_segment"] = record["wind_speed_segment"]
                        existing["wind_speed_unit"] = record["wind_speed_unit"]
                    if existing["representative_value"] is None and record["representative_value"] is not None:
                        existing["representative_value"] = record["representative_value"]
                for source_key in ("平均湍流强度", "代表性湍流强度"):
                    if row.get(source_key) is None:
                        continue
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
        match = re.search(domain_regex(self, "wind_resource_overrides", "search_004", r"[0-9]+(?:\.[0-9]+)?"), str(value))
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
        for segment in re.split(domain_regex(self, "wind_resource_overrides", "split_005", r"[\n\u3002\uff1b;]"), combined):
            if not re.search(domain_regex(self, "wind_resource_overrides", "search_006", r"50\s*\u5e74\s*\u4e00\s*\u9047"), segment, flags=re.IGNORECASE):
                continue
            if "最大风速" not in segment:
                continue
            for keyword in re.finditer(domain_regex(self, "wind_resource_overrides", "finditer_007", r"50\s*\u5e74\s*\u4e00\s*\u9047[^\uff0c\u3001\u3002\uff1b;]{0,60}?\u6700\u5927(?:10\s*min)?(?:\u5e73\u5747)?\u98ce\u901f"), segment, flags=re.IGNORECASE):
                search_text = segment[keyword.end():keyword.end() + 90]
                match = re.search(domain_regex(self, "wind_resource_overrides", "search_008", r"(?:\u4e3a|\u503c|[:\uff1a])?\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), search_text, flags=re.IGNORECASE)
                if match is None:
                    continue
                prefix = segment[max(0, match.start() - 8):match.start()]
                if re.search(domain_regex(self, "wind_resource_overrides", "search_009", r"(?:\u5c0f\u4e8e|\u4f4e\u4e8e|\u4e0d\u5927\u4e8e|[<\u2264])\s*$"), prefix):
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
            if not re.search(domain_regex(self, "wind_resource_overrides", "search_010", r"50\s*\u5e74\s*\u4e00\s*\u9047"), text, flags=re.IGNORECASE) or "\u6700\u5927\u98ce\u901f" not in text:
                continue
            for match in re.finditer(domain_regex(self, "wind_resource_overrides", "finditer_011", r"\u63a8\u7b97(?:\u81f3|\u5230)\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), text, flags=re.IGNORECASE):
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    candidates.append((80, value))
            for match in re.finditer(domain_regex(self, "wind_resource_overrides", "finditer_012", r"\u63a8\u7b97\u81f3\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), text, flags=re.IGNORECASE):
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
            match = re.search(domain_regex(self, "wind_resource_overrides", "search_013", r"\u63a8\u7b97\u81f3\s*160\s*m\s*\u9ad8\u5ea6\u4e3a\s*([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), text, flags=re.IGNORECASE)
            if match:
                value = self._normalize_scalar(match.group(1))
                if self._valid_wind_speed_50_year(value):
                    return value
        return None

    def _max_wind_speed_50_year_multi_method_value(self, text: str) -> Any:
        all_candidates: list[Any] = []
        strong_candidates: list[Any] = []
        standard_density_candidates: list[Any] = []
        value_pattern = re.compile(domain_regex(self, "wind_resource_overrides", "compile_014", r"([0-9]+(?:\.[0-9]+)?)\s*m\s*/\s*s"), flags=re.IGNORECASE)
        for segment in re.split(domain_regex(self, "wind_resource_overrides", "split_015", r"[\n\u3002\uff1b;]"), text):
            if not re.search(domain_regex(self, "wind_resource_overrides", "search_016", r"50\s*\u5e74\s*\u4e00\s*\u9047"), segment, flags=re.IGNORECASE) or "最大风速" not in segment:
                continue
            for match in value_pattern.finditer(segment):
                value = self._normalize_scalar(match.group(1))
                if not self._valid_wind_speed_50_year(value):
                    continue
                prefix = segment[max(0, match.start() - 12):match.start()]
                if re.search(domain_regex(self, "wind_resource_overrides", "search_017", r"(?:小于|低于|不大于|不超过|[<≤])\s*$"), prefix):
                    continue
                all_candidates.append(value)
                strong_prefix = segment[max(0, match.start() - 60):match.start()]
                standard_density_prefix = segment[max(0, match.start() - 80):match.start()]
                if "标准空气密度" in standard_density_prefix and re.search(domain_regex(self, "wind_resource_overrides", "search_018", r"(?:订正到|订正至|换算成|换算至|折算到|折算至)"), standard_density_prefix):
                    standard_density_candidates.append(value)
                if re.search(domain_regex(self, "wind_resource_overrides", "search_019", r"(?:推算至|推算到|折算至|换算至|得到|取值|较大值|最终)"), strong_prefix):
                    strong_candidates.append(value)
        candidates = strong_candidates or standard_density_candidates or all_candidates
        if not candidates:
            return None
        return max(candidates, key=lambda item: float(item))

    def _max_wind_speed_50_year_segment_score(self, segment: str) -> int:
        score = 0
        if any(keyword in segment for keyword in ("初步估算", "初步判定", "判定", "选用", "安全等级")):
            score += 100
        if re.search(domain_regex(self, "wind_resource_overrides", "search_020", r"(?:\u5c0f\u4e8e|<)\s*37\.5\s*m\s*/\s*s"), segment, flags=re.IGNORECASE):
            score += 80
        if "IEC" in segment or "III" in segment or "Ⅲ" in segment:
            score += 40
        if "10min" in segment or "10 min" in segment or "平均风速" in segment:
            score -= 30
        if "介于" in segment or "～" in segment or "~" in segment:
            score -= 20
        return score
