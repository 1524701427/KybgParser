"""Result sections, field traces and table presentation.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

from copy import deepcopy

from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable

from parser_engine.document.ast.evidence import ParsedField


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
        self._repair_generation_summary_table(tables)
        return tables

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
