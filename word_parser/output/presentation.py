"""结果章节、字段追踪和表格展示。

兼容迁移期间，这些方法共享 ResultBuilder 状态，并保留原有规则实现和调用顺序。
"""

from __future__ import annotations

from copy import deepcopy
import re

from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentTable

from word_parser.document.ast.evidence import ParsedField


class ResultPresentationMixin:
    def _build_tables(
        self, ast: DocumentAST | None, details: dict[str, list[dict[str, Any]]], fields: dict[str, ParsedField]
    ) -> dict[str, dict[str, Any]]:
        tables: dict[str, dict[str, Any]] = {}
        for key in self._required_table_keys():
            rows = details.get(key) or []
            if rows:
                tables[key] = self._details_table(key, rows)
            else:
                tables[key] = self._empty_required_table(key)
        tables.update(self._build_schema_tables_from_fields(fields))
        if ast is not None:
            document_tables = self._build_schema_tables_from_document(ast)
            for key, table in document_tables.items():
                tables[key] = table
        air_density = self._wind_resource_air_density_table_from_fields(fields)
        if air_density is not None:
            tables["windResourceAirDensity"] = air_density
        current_turbulence = tables.get("windResourceTurbulenceIntensity")
        if current_turbulence is None or not self._table_has_extracted_value(current_turbulence):
            turbulence = self._wind_resource_turbulence_table_from_fields(fields)
            if turbulence is not None:
                tables["windResourceTurbulenceIntensity"] = turbulence
        combined = self._wind_resource_combined_table(details, tables, fields)
        if combined is not None:
            tables["windResourceCombined"] = combined
        generation_aligned = self._generation_single_turbine_aligned_table(tables)
        if generation_aligned is not None:
            tables["generationSingleTurbineAligned"] = generation_aligned
        self._repair_generation_summary_table(tables)
        return tables

    def _generation_single_turbine_aligned_table(self, tables: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """映射每行风机数据时保留空单元格的位置。"""
        source = tables.get("singleTurbineAnnualEnergy") or {}
        from_original_table = False
        if not source.get("data"):
            source = next(
                (table for key, table in tables.items()
                 if key.startswith("generationOriginalTable")
                 and table.get("data")
                 and any("标签" in str(column) or "风机编号" in str(column) for column in table.get("columns") or [])
                 and any("上网电量" in str(column) for column in table.get("columns") or [])),
                tables.get("generationSummary") or {},
            )
            from_original_table = source is not tables.get("generationSummary")
        source_columns = [re.sub(r"\s+", "", str(value)).replace("（", "(").replace("）", ")") for value in source.get("columns") or []]
        source_rows = source.get("data") or []
        if not source_columns or not source_rows:
            return None
        if not str(source_rows[0][0] or "").strip() and any(str(cell).strip() == "MWh" for cell in source_rows[0]):
            source_columns = [f"{heading}(MWh)" if index < len(source_rows[0]) and str(source_rows[0][index]).strip() == "MWh" else heading
                              for index, heading in enumerate(source_columns)]

        def find(predicate, occurrence: int = 0) -> int | None:
            matches = [index for index, heading in enumerate(source_columns) if predicate(heading)]
            return matches[occurrence] if len(matches) > occurrence else None

        indices = {
            "标签": find(lambda h: "风机编号" in h or h == "标签"),
            "X（m）": find(lambda h: re.match(r"^X(?:\(|$)", h, re.I) is not None),
            "Y（m）": find(lambda h: re.match(r"^Y(?:\(|$)", h, re.I) is not None),
            "Z（m）": find(lambda h: re.match(r"^Z(?:\(|$)", h, re.I) is not None),
            "H（m）": find(lambda h: re.match(r"^H(?:\(|$)", h, re.I) is not None),
            "理论发电量": find(lambda h: "理论发电量" in h or "理论电量" in h),
            "平均风速": find(lambda h: "风速" in h and "尾流后" not in h and "平均" in h),
            "尾流系数": find(lambda h: "尾流系数" in h or "尾流折减" in h),
            "考虑尾流效应的发电量": find(lambda h: (("考虑尾流效应" in h or "考虑尾流" in h) and "发电量" in h) or "尾流电量" in h),
            "最终上网电量": find(lambda h: "上网电量" in h or "净发电量" in h or "净电量" in h),
            "等效小时数": find(lambda h: "等效小时" in h or "利用小时" in h or "满发小时" in h),
            "尾流效应导致的平均折减率": find(lambda h: "平均折减率" in h or "尾流折减率" in h or "尾流折减" in h),
        }
        yearly = [i for i, heading in enumerate(source_columns) if "年发电量" in heading and "考虑尾流效应" not in heading]
        if indices["理论发电量"] is None and yearly:
            indices["理论发电量"] = yearly[0]
        if indices["最终上网电量"] is None and len(yearly) > 1:
            indices["最终上网电量"] = yearly[-1]
        if indices["平均风速"] is None:
            indices["平均风速"] = find(lambda h: "风速" in h and "尾流后" not in h)
        if indices["标签"] is None:
            return None

        columns = list(indices)
        energy_columns = {"理论发电量", "考虑尾流效应的发电量", "最终上网电量"}
        source_cell_sources = source.get("_cellSources") or []
        data: list[list[Any]] = []
        cell_sources: list[list[Any]] = []
        for row_number, source_row in enumerate(source_rows):
            label_index = indices["标签"]
            label = source_row[label_index] if label_index < len(source_row) else None
            if label is None or not str(label).strip():
                continue
            is_summary = bool(re.search(r"合计|总计|求和|平均", str(label)))
            row: list[Any] = []
            row_sources: list[Any] = []
            for column in columns:
                source_index = indices[column]
                value = source_row[source_index] if source_index is not None and source_index < len(source_row) else None
                if value in ("", "---", "--"):
                    value = None
                if column == "尾流效应导致的平均折减率" and isinstance(value, (int, float)) and value < 0:
                    value = abs(value)
                if column in energy_columns and value is not None and source_index is not None:
                    heading = source_columns[source_index].lower()
                    if "万kw" in heading or "万千瓦时" in heading:
                        try:
                            converted = float(str(value).replace(",", "")) * 10
                            value = int(converted) if converted.is_integer() else round(converted, 6)
                        except ValueError:
                            value = None
                    elif "mwh" not in heading and "兆瓦时" not in heading:
                        value = None  # 单位未知，不应标记为 MWh。
                if column == "尾流效应导致的平均折减率" and source_index is None and is_summary:
                    wake_index = indices["尾流系数"]
                    wake = source_row[wake_index] if wake_index is not None and wake_index < len(source_row) else None
                    if isinstance(wake, (int, float)) and wake < 0:
                        value = abs(wake)
                        source_index = wake_index
                row.append(value)
                sources = source_cell_sources[row_number] if row_number < len(source_cell_sources) else []
                row_sources.append(sources[source_index] if source_index is not None and source_index < len(sources) else None)
            data.append(row)
            cell_sources.append(row_sources)
            if from_original_table and is_summary:
                break

        if not data:
            return None
        result = {
            "key": "generationSingleTurbineAligned",
            "name": "单台风机发电量对齐表",
            "columns": columns,
            "columnKeys": columns,
            "index": list(range(len(data))),
            "data": data,
            "_trace": {"extractionType": "combined_or_project_detail", "ruleSource": "single_turbine_row_projection"},
        }
        if any(any(item is not None for item in row) for row in cell_sources):
            result["_cellSources"] = cell_sources
        return result

    def _wind_resource_combined_table(
        self,
        details: dict[str, list[dict[str, Any]]],
        tables: dict[str, dict[str, Any]],
        fields: dict[str, ParsedField],
    ) -> dict[str, Any] | None:
        """按测风塔编号对齐风资源指标，避免按数组位置对齐。"""
        source_rows = details.get("windResourceCombined") or []
        if not source_rows:
            return None

        columns = [
            "测风塔编号", "测风塔经度", "测风塔纬度", "测风周期", "该风电场的空气密度",
            "高度对应的空气密度", "10m高度空气密度", "160m高度空气密度", "各测风塔各高度空气密度",
            "轮毂高度平均风速", "轮毂高度平均风功率密度", "各测风塔轮毂高度平均风速",
            "各测风塔轮毂高度平均风功率密度", "轮毂高度处的主风向", "轮毂高度处的次风向",
            "轮毂高度处的主风能方向", "轮毂高度处的次风能方向", "最大高度处代表性湍流强度",
            "各测风塔各高度湍流强度", "综合风切变", "发电量计算是否使用",
        ]
        basic = tables.get("windResourceTowerBasic") or {}
        basic_columns = basic.get("columns") or []
        basic_rows = basic.get("data") or []
        def column_index(aliases: tuple[str, ...]) -> int | None:
            return next((i for i, name in enumerate(basic_columns) if any(alias in str(name) for alias in aliases)), None)

        tower_index = column_index(("测风塔", "塔号"))
        coordinate_index = column_index(("坐标", "经纬度"))
        period_index = column_index(("测风时段", "测风周期", "观测时段"))
        known_towers = {
            self._normalize_tower_code(str(source_row.get("测风塔编号") or ""))
            for source_row in source_rows
        }
        basic_by_tower: dict[str, tuple[str, Any]] = {}
        ambiguous_towers: set[str] = set()

        def register(tower: str, coordinates: str, period: Any) -> None:
            if tower not in known_towers or tower in ambiguous_towers:
                return
            candidate = (coordinates, period)
            previous = basic_by_tower.get(tower)
            if previous is not None and previous != candidate:
                basic_by_tower.pop(tower, None)
                ambiguous_towers.add(tower)
            else:
                basic_by_tower[tower] = candidate

        if tower_index is not None:
            for basic_row in basic_rows:
                if tower_index >= len(basic_row):
                    continue
                tower = self._normalize_tower_code(str(basic_row[tower_index] or ""))
                if tower in known_towers:
                    coordinates = str(basic_row[coordinate_index] or "") if coordinate_index is not None and coordinate_index < len(basic_row) else ""
                    period = basic_row[period_index] if period_index is not None and period_index < len(basic_row) else None
                    register(tower, coordinates, period)

        # 部分报告将基本信息表转置：每座测风塔占一列，
        # 经纬度是“地理坐标”下连续的两行。
        for column, heading in enumerate(basic_columns[1:], start=1):
            tower_match = re.search(r"[A-Za-z0-9]{2,8}#", str(heading))
            if not tower_match:
                continue
            tower = self._normalize_tower_code(tower_match.group(0))
            if tower not in known_towers:
                continue
            coordinates = ""
            period = None
            for row_number, basic_row in enumerate(basic_rows):
                label = str(basic_row[0] or "") if basic_row else ""
                if column >= len(basic_row):
                    continue
                if any(word in label for word in ("测风时段", "测风周期", "观测时段")):
                    period = basic_row[column]
                if not any(word in label for word in ("地理坐标", "经纬度", "坐标")):
                    continue
                next_row = basic_rows[row_number + 1] if row_number + 1 < len(basic_rows) else []
                if column >= len(next_row) or (next_row and str(next_row[0] or "").strip()):
                    continue
                latitude = str(basic_row[column] or "").strip()
                longitude = str(next_row[column] or "").strip()
                lat_number = re.fullmatch(r"(\d{1,2}(?:\.\d+)?)\s*[°度]?", latitude)
                lon_number = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*[°度]?", longitude)
                if lat_number and lon_number and float(lat_number.group(1)) <= 90 and float(lon_number.group(1)) <= 180:
                    coordinates = f"N{latitude} E{longitude}"
            register(tower, coordinates, period)

        record_columns = {
            "各测风塔各高度空气密度": "windResourceAirDensityRecords",
            "各测风塔轮毂高度平均风速": "hubHeightAverageWindSpeedRecords",
            "各测风塔轮毂高度平均风功率密度": "hubHeightAverageWindPowerDensityRecords",
            "各测风塔各高度湍流强度": "windResourceTurbulenceIntensityRecords",
        }
        records_by_column: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for label, field_code in record_columns.items():
            grouped: dict[str, list[dict[str, Any]]] = {}
            field = fields.get(field_code)
            for record in field.value if field is not None and isinstance(field.value, list) else []:
                if not isinstance(record, dict):
                    continue
                tower = self._normalize_tower_code(str(record.get("tower_code") or ""))
                if tower:
                    grouped.setdefault(tower, []).append(record)
            records_by_column[label] = grouped

        data: list[list[Any]] = []
        cell_sources: list[list[Any]] = []
        for source_row in source_rows:
            tower = self._normalize_tower_code(str(source_row.get("测风塔编号") or ""))
            if not tower:
                continue
            coordinates, period = basic_by_tower.get(tower, ("", None))
            latitude = re.search(r"[NS]\s*[:：]?\s*\d[^NSEW]{0,35}", coordinates, re.IGNORECASE)
            longitude = re.search(r"[EW]\s*[:：]?\s*\d[^NSEW]{0,35}", coordinates, re.IGNORECASE)
            row = dict(source_row)
            row["测风塔经度"] = longitude.group(0).strip() if longitude else row.get("测风塔经度")
            row["测风塔纬度"] = latitude.group(0).strip() if latitude else row.get("测风塔纬度")
            row["测风周期"] = period if period else row.get("测风周期")
            row["轮毂高度平均风速"] = row.get("轮毂高度平均风速m/s")
            row["轮毂高度平均风功率密度"] = row.get("轮毂高度平均风功率密度W/m²")
            for label, grouped in records_by_column.items():
                row[label] = self._wind_resource_record_display(grouped.get(tower) or [])
            # 旧版合并行在文档未说明时将该标志默认为“是”；
            # 不应把这个默认值当作文档证据。
            sources = row.get("_cellSources") or {}
            use_source = sources.get("发电量计算是否使用")
            if not use_source or (use_source.get("process") or {}).get("resolver") == "wind_resource_generation_use_default":
                row["发电量计算是否使用"] = None
            data.append([None if row.get(label) in ("---", "--", "") else row.get(label) for label in columns])
            cell_sources.append([sources.get(label) for label in columns])

        if not data:
            return None
        table = {
            "key": "windResourceCombined",
            "name": "测风塔风资源指标汇总表",
            "columns": columns,
            "columnKeys": columns,
            "index": list(range(len(data))),
            "data": data,
            "_trace": {"extractionType": "combined_or_project_detail", "ruleSource": "tower_code_join"},
        }
        if any(any(source is not None for source in row) for row in cell_sources):
            table["_cellSources"] = cell_sources
        return table

    @staticmethod
    def _wind_resource_record_display(records: list[dict[str, Any]]) -> str | None:
        """将结构化测风记录变成表格单元格可展示的文字。"""
        parts: list[str] = []
        for record in records:
            height = record.get("height")
            prefix = f"{height}m：" if height is not None else ""
            if "value" in record:
                value = record.get("value")
                if value is None:
                    continue
                unit = record.get("unit") or ""
                parts.append(f"{prefix}{value}{(' ' + unit) if unit else ''}")
            else:
                average = record.get("average_value")
                representative = record.get("representative_value")
                speed = record.get("wind_speed_segment")
                if speed is not None:
                    prefix = f"{height}m / {speed}m/s：" if height is not None else f"{speed}m/s："
                values = []
                if average is not None:
                    values.append(f"平均 {average}")
                if representative is not None:
                    values.append(f"代表性 {representative}")
                if values:
                    parts.append(prefix + "、".join(values))
        return "；".join(parts) or None

    def _wind_resource_air_density_table_from_fields(self, fields: dict[str, ParsedField]) -> dict[str, Any] | None:
        """从已抽取的逐塔记录生成空气密度参数表。"""
        field = fields.get("windResourceAirDensityRecords")
        records = field.value if field is not None and isinstance(field.value, list) else []
        data = [
            [record.get("tower_code"), record.get("height"), record.get("value")]
            for record in records
            if isinstance(record, dict) and record.get("tower_code") and record.get("value") is not None
        ]
        if not data:
            return None
        return {
            "key": "windResourceAirDensity",
            "name": "空气密度参数",
            "columns": ["测风塔编号", "高度 (m)", "空气密度 (kg/m³)"],
            "columnKeys": ["towerCode", "height", "airDensity"],
            "index": list(range(len(data))),
            "data": data,
        }

    def _wind_resource_turbulence_table_from_fields(self, fields: dict[str, ParsedField]) -> dict[str, Any] | None:
        """原文没有标准表时，用逐塔记录生成湍流强度参数表。"""
        field = fields.get("windResourceTurbulenceIntensityRecords")
        records = field.value if field is not None and isinstance(field.value, list) else []
        data = [
            [record.get("tower_code"), record.get("height"), record.get("average_value"), record.get("representative_value")]
            for record in records
            if isinstance(record, dict)
            and record.get("tower_code")
            and (record.get("average_value") is not None or record.get("representative_value") is not None)
        ]
        if not data:
            return None
        return {
            "key": "windResourceTurbulenceIntensity",
            "name": "湍流强度参数",
            "columns": ["测风塔编号", "高度 (m)", "平均湍流强度", "代表性湍流强度"],
            "columnKeys": ["towerCode", "height", "averageTurbulenceIntensity", "representativeTurbulenceIntensity"],
            "index": list(range(len(data))),
            "data": data,
        }

    def _build_schema_tables_from_fields(self, fields: dict[str, ParsedField]) -> dict[str, dict[str, Any]]:
        """把已抽到的字段值渲染成标准参数表。"""
        tables: dict[str, dict[str, Any]] = {}
        for table_key, field_codes in self.TABLE_FIELD_SOURCES.items():
            if table_key not in self.required_table_schemas:
                continue
            row: dict[str, Any] = {}
            for field_code in field_codes:
                field = fields.get(field_code)
                if field is None or field.value is None:
                    continue
                column_key = self._field_table_column_key(table_key, field_code)
                row[column_key] = field.value
                row.setdefault("_cellSources", {})[column_key] = self._field_table_cell_source(field, table_key)
            if any(value is not None for key, value in row.items() if not str(key).startswith("_")):
                tables[table_key] = self._schema_row_table(table_key, row)
        return tables

    def _field_table_column_key(self, table_key: str, field_code: str) -> str:
        """把字段 code 映射到标准表列 key。"""
        return self.FIELD_TABLE_COLUMN_MAP.get(table_key, {}).get(field_code, field_code)

    def _field_table_cell_source(self, field: ParsedField, table_key: str) -> dict[str, Any]:
        """把字段证据包装成标准表单元格来源。"""
        evidence = field.evidence[0] if field.evidence else None
        source = evidence.to_dict() if evidence is not None else {}
        return {
            "source": {
                "kind": "field_value",
                "sourceType": source.get("source_type") or source.get("sourceType"),
                "blockId": source.get("block_id") or source.get("blockId"),
                "tableId": source.get("table_id") or source.get("tableId"),
                "page": source.get("page"),
                "sectionPath": source.get("section_path") or source.get("sectionPath") or [],
                "sourceText": source.get("text"),
                "matchMethod": source.get("match_method") or source.get("matchMethod") or "field_to_schema_table",
                "description": f"字段 {field.field_code} 渲染为标准表 {table_key}。",
            },
            "process": {"resolver": "field_to_schema_table", "calculation": f"使用字段 {field.field_code} 的抽取值。"},
            "sourceDescription": f"字段 {field.field_code} 渲染为标准表 {table_key}。",
        }

    def _build_schema_tables_from_document(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        tables = self.original_table_resolver.resolve(ast)
        investment = self._investment_estimate_original_table_from_document(ast)
        if investment is not None and self._table_has_extracted_value(investment):
            tables["investmentEstimate"] = investment
        earthwork = self._earthwork_table_from_document(ast)
        if earthwork is not None and self._table_has_extracted_value(earthwork):
            tables.setdefault("earthworkBalance", earthwork)
        turbulence = self._wind_resource_turbulence_intensity_table_from_document(ast)
        if turbulence is not None and self._table_has_extracted_value(turbulence):
            tables["windResourceTurbulenceIntensity"] = turbulence
        return tables

    def _repair_generation_summary_table(self, tables: dict[str, dict[str, Any]]) -> None:
        current = tables.get("generationSummary")
        if current is not None and self._looks_like_generation_summary_table(current):
            return
        replacement = next(
            (
                table
                for key, table in tables.items()
                if key.startswith("generationOriginalTable") and self._looks_like_generation_summary_table(table)
            ),
            None,
        )
        if replacement is None:
            return
        repaired = deepcopy(replacement)
        repaired["key"] = "generationSummary"
        tables["generationSummary"] = repaired

    def _looks_like_generation_summary_table(self, table: dict[str, Any]) -> bool:
        columns_text = self._compact_text(" ".join(str(column or "") for column in table.get("columns") or []))
        rows_text = self._compact_text(" ".join(" ".join(str(cell or "") for cell in row) for row in (table.get("data") or [])[:12]))
        text = f"{columns_text} {rows_text}"
        has_project_unit_value = "项目" in columns_text and "单位" in columns_text and ("指标" in columns_text or "数值" in columns_text)
        has_generation_metrics = any(keyword in text for keyword in ("单机容量", "机组台数", "总装机容量", "综合折减系数", "年上网电量", "年利用小时"))
        return has_project_unit_value and has_generation_metrics

    def _original_table_groups_from_config(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        """兼容旧入口：原表批量导出统一交给 OriginalTableResolver。"""
        return self.original_table_resolver.resolve_groups_from_config(ast)

    def _match_original_table_title(
        self,
        ast: DocumentAST,
        table: DocumentTable,
        patterns: list[str],
        exclude_patterns: list[str] | None = None,
        include_table_text: bool = False,
    ) -> dict[str, Any] | None:
        """兼容旧入口：统一使用 OriginalTableResolver 的标题匹配链路。"""
        return self.original_table_resolver.match_title(ast, table, {}, patterns, exclude_patterns, include_table_text)

    def _original_table_title_candidates(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        """兼容旧入口：返回统一的原表标题候选。"""
        return self.original_table_resolver.title_candidates(ast, table)

    def _nearby_paragraph_title_candidates(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        """兼容旧入口：返回统一的表前标题候选。"""
        return self.original_table_resolver.nearby_title_candidates(ast, table)

    def _deduplicate_original_tables_by_source(self, tables: dict[str, dict[str, Any]]) -> None:
        """兼容旧入口：按统一源表身份去重。"""
        self.original_table_resolver.deduplicate_by_source(tables)

    def _original_table_from_config(self, ast: DocumentAST, spec: dict[str, Any]) -> dict[str, Any] | None:
        """兼容旧入口：单张原表导出统一交给 OriginalTableResolver。"""
        return self.original_table_resolver.original_table_from_config(ast, spec)

    def _repeatable_original_tables_from_config(self, ast: DocumentAST, existing_tables: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """兼容旧入口：可重复原表导出统一交给 OriginalTableResolver。"""
        return self.original_table_resolver.repeatable_tables_from_config(ast, existing_tables)

    def _original_tables_for_spec(self, ast: DocumentAST, spec: dict[str, Any]) -> list[DocumentTable]:
        """兼容旧入口：按统一章节和表题规则筛选原表候选。"""
        return self.original_table_resolver.tables_for_spec(ast, spec)

    def _original_table_section_keywords(self, spec: dict[str, Any]) -> list[str]:
        """兼容旧入口：章节关键词统一由 OriginalTableResolver 推断。"""
        return self.original_table_resolver.section_keywords(spec)

    def _schema_rows_from_horizontal_table(
        self,
        key: str,
        table: DocumentTable,
        header: list[str],
        data_rows: list[list[str]],
    ) -> list[dict[str, Any]]:
        name, header_pairs = self.required_table_schemas[key]
        del name
        rows: list[dict[str, Any]] = []
        for source_row_index, source_row in enumerate(data_rows, start=1):
            if not any(cell.strip() for cell in source_row):
                continue
            row: dict[str, Any] = {}
            for column_key, column_name in header_pairs:
                aliases = self._schema_column_aliases(key, column_key, column_name)
                index = self._find_header_index(header, aliases)
                value = None if index is None or index >= len(source_row) else self._normalize_table_cell(source_row[index])
                row[column_key] = value
                if value is not None and index is not None:
                    row.setdefault("_cellSources", {})[column_key] = self._table_cell_source(
                        table,
                        source_row_index,
                        index,
                        f"由原文横向表按标准列 {column_name} 映射抽取。",
                        resolver="schema_horizontal_table",
                    )
            rows.append(row)
        return rows

    def _schema_column_aliases(self, key: str, column_key: str, column_name: str) -> list[str]:
        aliases = [column_name]
        extra = {
            ("collectorLineTechnical", "ratedVoltage"): ["线路额定电压"],
            ("collectorLineTechnical", "circuit"): ["回路"],
            ("collectorLineTechnical", "totalLength"): ["线路总长度"],
            ("substationCivil", "voltageLevel"): ["升压站规模", "升压站电压等级"],
            ("windFoundationTechnical", "capBottomRadius"): ["基础承台底面半径"],
            ("windFoundationTechnical", "buriedDepth"): ["基础埋深"],
            ("windFoundationConstruction", "foundationType"): ["地基处理措施"],
            ("windFoundationConstruction", "pileRingCount"): ["桩圈数"],
            ("windFoundationConstruction", "pilesPerRing"): ["每圈桩数", "分布根数"],
            ("windFoundationConstruction", "c40Concrete"): ["混凝土量", "C40"],
            ("windFoundationConstruction", "rebar"): ["钢筋工程量", "钢筋制作"],
            ("boxFoundationTechnical", "c30Concrete"): ["混凝土量", "C30", "C25"],
            ("boxFoundationTechnical", "rebarQuantity"): ["钢筋工程量", "钢筋"],
            ("investmentEstimate", "dynamicInvestment"): ["单位千瓦动态投资", "单位千瓦动态投资 （元/kW）"],
            ("financingAssumptions", "workingCapitalLoanRatio"): ["流动资金贷款比例", "贷款比例"],
            ("financingAssumptions", "workingCapitalLoanInterestRate"): ["流动资金贷款利率", "贷款利率"],
            ("financialEvaluation", "windFarmGridPrice"): ["风电场上网电价", "上网电价"],
        }
        aliases.extend(extra.get((key, column_key), []))
        return aliases

    def _display_detail_rows(self, key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _split_table(self, key: str, name: str, columns: list[str], data_row: list[Any]) -> dict[str, Any]:
        return {
            "key": key,
            "name": name,
            "columns": columns,
            "index": [0],
            "data": [[self._empty_to_none(value) for value in data_row]],
        }

    def _literal_table(self, key: str, name: str, columns: list[str], data: list[list[Any]]) -> dict[str, Any]:
        return {
            "key": key,
            "name": name,
            "columns": columns,
            "columnKeys": [f"col_{index}" for index in range(len(columns))],
            "index": list(range(len(data))),
            "data": [[self._empty_to_none(value) for value in row] for row in data],
        }

    def _schema_row_table(self, key: str, row: dict[str, Any]) -> dict[str, Any]:
        return self._schema_table(key, [row])

    def _schema_table(self, key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        name, header_pairs = self.required_table_schemas.get(key, (key, []))
        if header_pairs:
            column_keys = [item[0] for item in header_pairs]
            columns = [item[1] for item in header_pairs]
        else:
            column_keys = self._row_keys(rows)
            columns = column_keys
        data = [[self._empty_to_none(row.get(column_key)) for column_key in column_keys] for row in rows]
        table = {
            "key": key,
            "name": name,
            "columns": columns,
            "columnKeys": column_keys,
            "index": list(range(len(data))),
            "data": data,
        }
        cell_sources = []
        for row in rows:
            sources = row.get("_cellSources", {}) if isinstance(row, dict) else {}
            cell_sources.append([sources.get(column_key) if isinstance(sources, dict) else None for column_key in column_keys])
        if any(any(source is not None for source in row) for row in cell_sources):
            table["_cellSources"] = cell_sources
        return table

    def _table_rows_as_dicts(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        column_keys = table.get("columnKeys") or table.get("columns") or []
        rows: list[dict[str, Any]] = []
        for data_row in table.get("data") or []:
            if not isinstance(data_row, list):
                continue
            rows.append({str(key): data_row[index] if index < len(data_row) else None for index, key in enumerate(column_keys)})
        return rows

    def _empty_required_table(self, key: str) -> dict[str, Any]:
        if key in self.required_table_schemas:
            name, header_pairs = self.required_table_schemas[key]
            return {
                "key": key,
                "name": name,
                "columns": [name for _, name in header_pairs],
                "columnKeys": [column_key for column_key, _ in header_pairs],
                "index": [0] if header_pairs else [],
                "data": [[None for _ in header_pairs]] if header_pairs else [],
            }
        meta = self.table_output_headers.get(key, {"name": key, "headers": []})
        headers = meta.get("headers", [])
        return {
            "key": key,
            "name": meta.get("name", key),
            "columns": [header.get("name") for header in headers],
            "columnKeys": [header.get("key") for header in headers],
            "index": [],
            "data": [],
        }

    def _details_table(self, key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        meta = self.table_output_headers.get(key, {"name": key, "headers": []})
        headers = meta.get("headers", [])
        name = self._detail_table_source_name(rows) or meta.get("name", key)
        if headers:
            column_keys = [header.get("key") for header in headers]
            columns = [header.get("name") for header in headers]
        else:
            column_keys = self._row_keys(rows)
            columns = column_keys
        table = {
            "key": key,
            "name": name,
            "columns": columns,
            "columnKeys": column_keys,
            "index": list(range(len(rows))),
            "data": [[self._empty_to_none(row.get(column_key)) for column_key in column_keys] for row in rows],
        }
        table_trace = next((row.get("_tableTrace") for row in rows if isinstance(row, dict) and row.get("_tableTrace")), None)
        if table_trace:
            table["_trace"] = table_trace
        cell_sources = []
        for row in rows:
            sources = row.get("_cellSources", {}) if isinstance(row, dict) else {}
            cell_sources.append([sources.get(column_key) if isinstance(sources, dict) else None for column_key in column_keys])
        if any(any(source is not None for source in source_row) for source_row in cell_sources):
            table["_cellSources"] = cell_sources
        return table

    def _detail_table_source_name(self, rows: list[dict[str, Any]]) -> str | None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            sources = row.get("_cellSources")
            if not isinstance(sources, dict):
                continue
            for source_trace in sources.values():
                if not isinstance(source_trace, dict):
                    continue
                source = source_trace.get("source") if isinstance(source_trace.get("source"), dict) else {}
                caption = self._clean_table_caption_title(source.get("caption") or "")
                if caption:
                    return caption
        return None

    def _field_value(self, fields: dict[str, ParsedField], code: str, with_unit: bool = False) -> Any:
        field = fields.get(code)
        if field is None or field.value is None:
            return None
        value = field.value
        if not with_unit or field.unit is None:
            return value
        return f"{value}{self._display_unit(field.unit)}"

    def _dash_if_none(self, value: Any) -> Any:
        return "——" if value is None else value

    def _display_unit(self, unit: str) -> str:
        return {"m2": "㎡", "m3": "m³"}.get(unit, unit)

    def _empty_to_none(self, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def _table_has_extracted_value(self, table: dict[str, Any]) -> bool:
        return any(value is not None for row in table["data"] for value in row)

    def _row_keys(self, rows: list[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if str(key).startswith("_"):
                    continue
                if key not in keys:
                    keys.append(key)
        return keys

    def _required_field_codes(self) -> list[str]:
        codes: list[str] = []
        for schema in self.required_section_schema.values():
            for code in schema.get("fields", []):
                if code not in codes:
                    codes.append(code)
        return codes

    def _build_sections(self, fields: dict[str, ParsedField], tables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        final_fields = self._build_fields(fields)
        for section_name, schema in self.required_section_schema.items():
            section_fields = [final_fields[code] for code in schema.get("fields", []) if code in final_fields]
            section_tables = [tables[key] if key in tables else self._empty_required_table(key) for key in schema.get("tables", [])]
            for key in schema.get("optional_tables", []):
                table = tables.get(key)
                if table is not None and self._table_has_extracted_value(table):
                    section_tables.append(table)
            existing_section_keys = {table.get("key") for table in section_tables}
            for prefix in schema.get("optional_table_prefixes", []):
                for key in sorted(tables):
                    if key in existing_section_keys or not key.startswith(prefix):
                        continue
                    table = tables[key]
                    if self._table_has_extracted_value(table):
                        section_tables.append(table)
                        existing_section_keys.add(key)
            sections.append({"name": section_name, "fields": section_fields, "tables": section_tables})
        return sections

    def _build_fields(self, fields: dict[str, ParsedField]) -> dict[str, Any]:
        """只导出字段值，不包含证据和调试信息。"""
        result: dict[str, Any] = {}
        for code in self._required_field_codes():
            field = fields.get(code)
            name, unit = self.required_field_meta.get(code, (code, None))
            result[code] = {
                "fieldCode": code,
                "name": field.field_name if field is not None else name,
                "value": field.value if field is not None else None,
                "unit": field.unit if field is not None and field.unit is not None else unit,
            }
        for code, field in fields.items():
            result.setdefault(
                code,
                {
                    "fieldCode": code,
                    "name": field.field_name,
                    "value": None if field is None else field.value,
                    "unit": field.unit if field is not None else None,
                },
            )
            if field is not None:
                result[code].update(
                    {
                        "name": field.field_name,
                        "value": field.value,
                        "unit": field.unit,
                    }
                )
        return result

    def _build_field_traces(self, fields: dict[str, ParsedField]) -> dict[str, dict[str, Any]]:
        traces: dict[str, dict[str, Any]] = {}
        for code in self._required_field_codes():
            traces[code] = self._trace_field(code, fields.get(code))
        for code, field in fields.items():
            traces.setdefault(code, self._trace_field(code, field))
        return traces

    def _required_table_keys(self) -> list[str]:
        keys: list[str] = []
        for schema in self.required_section_schema.values():
            for key in [*schema.get("tables", []), *schema.get("optional_tables", [])]:
                if key not in keys:
                    keys.append(key)
        return keys

    def _trace_field(self, code: str, field: ParsedField | None) -> dict[str, Any]:
        name, unit = self.required_field_meta.get(code, (code, None))
        if field is None:
            return {
                "fieldCode": code,
                "name": name,
                "value": None,
                "result": None,
                "unit": unit,
                "status": "MISSING",
                "confidence": None,
                "source": {"kind": "missing", "fieldCode": code, "description": "schema required field not extracted"},
                "evidence": [],
                "process": {},
                "messages": [],
                "debug": {},
            }
        evidence = [item.to_dict() for item in field.evidence]
        return {
            "fieldCode": code,
            "name": field.field_name or name,
            "value": field.value,
            "result": field.value,
            "unit": field.unit if field.unit is not None else unit,
            "status": field.status,
            "confidence": field.confidence,
            "source": evidence[0] if evidence else None,
            "evidence": evidence,
            "process": {key: value for key, value in (field.debug or {}).items()},
            "messages": list(field.messages),
            "debug": dict(field.debug),
        }

    def _build_extraction_fields(self, fields: dict[str, ParsedField]) -> list[dict[str, Any]]:
        """导出用户需要的“名字/结果/单位”三列结构。"""
        return [
            {
                "名字": field.field_name,
                "结果": field.value,
                "单位": field.unit,
            }
            for field in fields.values()
        ]

    def _build_details(self, ast: DocumentAST | None) -> dict[str, list[dict[str, Any]]]:
        """从解析数据表生成行级明细数组。"""
        details = {key: [] for key in self._required_table_keys()}
        for spec in self.detail_tables:
            details.setdefault(spec["key"], [])
        if ast is None:
            return details
        has_sectioned_tables = any(table.section_path for table in ast.tables)
        for table in ast.tables:
            section_text = " / ".join(table.section_path)
            for spec in self.detail_tables:
                section_keywords = spec.get("section_keywords") or []
                if section_keywords and has_sectioned_tables and not self._section_path_matches(table.section_path, section_keywords):
                    continue
                if not self._table_matches(table, section_text, spec):
                    continue
                details[spec["key"]].extend(self._rows_for_table(table, spec["columns"]))
        for key, rows in self._build_project_specific_details(ast).items():
            details[key] = rows
        for key in {"permanentLandArea", "earthworkBalance"}:
            details[key] = []
        for key, rows in self._build_land_area_details(ast).items():
            details[key] = rows
        return details

    def _build_project_specific_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {}
        for spec in self.combined_table_specs:
            details.update(self._combined_details_from_config(ast, spec))
        return details

    def _combined_details_from_config(self, ast: DocumentAST, spec: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        builder = spec.get("builder")
        if builder == "resource_details":
            return self._attach_detail_traces(self._build_resource_details(ast), spec, "resource_details")
        if builder == "collector_line_combined":
            return self._attach_detail_traces(self._build_collector_line_details(ast), spec, "collector_line_combined")
        if builder == "electrical_primary_details":
            return self._attach_detail_traces(self._build_electrical_primary_details(ast), spec, "electrical_primary_details")
        if builder == "electrical_secondary_details":
            return self._attach_detail_traces(self._build_electrical_secondary_details(ast), spec, "electrical_secondary_details")
        if builder == "substation_civil_combined":
            return self._attach_detail_traces(self._build_substation_civil_details(ast), spec, "substation_civil_combined")
        if builder == "road_parameters":
            return self._attach_detail_traces(self._build_road_parameter_details(ast), spec, "road_parameters")
        return {}

    def _attach_detail_traces(self, details: dict[str, list[dict[str, Any]]], spec: dict[str, Any], builder: str) -> dict[str, list[dict[str, Any]]]:
        trace = {
            "extractionType": "combined_or_project_detail",
            "ruleSource": "configs/output_schema.yaml",
            "builder": builder,
            "description": f"Rows produced by ResultBuilder.{builder}",
        }
        for rows in details.values():
            for row in rows:
                if isinstance(row, dict):
                    row.setdefault("_tableTrace", trace)
        return details
