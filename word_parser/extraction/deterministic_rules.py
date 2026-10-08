"""Configured scalar extraction and existing override coordination.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST

from parser_engine.document.ast.evidence import ParsedField


class DeterministicRulesMixin:
    def _deterministic_rule_section(self, name: str) -> dict[str, Any]:
        section = self.deterministic_rules.get(name) if isinstance(self.deterministic_rules, dict) else None
        return section if isinstance(section, dict) else {}

    def _configured_patterns(self, section: dict[str, Any], key: str, fallback: list[str]) -> list[str]:
        value = section.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return list(value)
        return fallback

    def _configured_field_rules(self, section_name: str, fallback: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        section = self._deterministic_rule_section(section_name)
        rules = section.get("fields")
        return rules if isinstance(rules, dict) else fallback

    def _configured_text_blocks(self, ast: DocumentAST, section_name: str, default_sections: list[str], default_keywords: list[str]) -> list[DocumentBlock]:
        section = self._deterministic_rule_section(section_name)
        section_keywords = section.get("sections") if isinstance(section.get("sections"), list) else default_sections
        matched = [
            block for block in self._body_blocks(ast)
            if self._section_path_matches(block.section_path, [str(item) for item in section_keywords])
        ]
        if matched:
            return matched
        fallback_keywords = section.get("fallback_keywords") if isinstance(section.get("fallback_keywords"), list) else default_keywords
        return [
            block for block in self._body_blocks(ast)
            if block.text and any(str(keyword) in block.text for keyword in fallback_keywords)
        ]

    def _value_from_configured_patterns(self, text: str, rule: dict[str, Any]) -> Any:
        if not isinstance(rule, dict):
            return None
        if any(keyword in text for keyword in rule.get("reject_keywords") or []):
            return None
        required_keywords = rule.get("require_keywords") or []
        if required_keywords and not all(str(keyword) in text for keyword in required_keywords):
            return None
        patterns = [str(pattern) for pattern in (rule.get("patterns") or [])]
        value_type = rule.get("value_type")
        value = self._last_configured_pattern_value(text, patterns) if rule.get("select") == "last" else self._first_configured_pattern_value(text, patterns)
        if value is None:
            return None
        if value_type == "number":
            value = self._normalize_scalar(value)
        elif rule.get("normalize") == "text":
            value = self._normalize_text_value(str(value))
        validators = rule.get("validators") if isinstance(rule.get("validators"), dict) else {}
        if isinstance(value, (int, float)):
            minimum = validators.get("min")
            maximum = validators.get("max")
            if minimum is not None and float(value) < float(minimum):
                return None
            if maximum is not None and float(value) > float(maximum):
                return None
        return value

    def _first_configured_pattern_value(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                return self._deterministic_match_value(match)
        return None

    def _last_configured_pattern_value(self, text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
            if matches:
                return self._deterministic_match_value(matches[-1])
        return None

    def _deterministic_match_value(self, match: re.Match[str]) -> Any:
        try:
            return match.group("value")
        except IndexError:
            pass
        if match.lastindex:
            return match.group(1)
        return match.group(0)

    def _apply_document_table_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField]) -> None:
        generation = self._generation_summary_row_from_document(ast)
        if generation.get("nonWakeLossFactor") is not None:
            self._set_field(fields, "nonWakeLossFactor", "\u4e0d\u8003\u8651\u5c3e\u6d41\u6548\u5e94\u7684\u6298\u51cf\u7cfb\u6570", generation["nonWakeLossFactor"], "%", "generation source tables")

    def _apply_deterministic_overrides(
        self, ast: DocumentAST, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]]
    ) -> None:
        configured_scalar_overrides = self._configured_scalar_overrides(ast)
        configured_scalar_override_codes = set(configured_scalar_overrides) - self.ROAD_PARAMETER_FIELD_CODES
        generation_skip_codes = configured_scalar_override_codes - self.GENERATION_TABLE_PREFERRED_FIELD_CODES
        table_preferred_codes = (
            self.GENERATION_TABLE_PREFERRED_FIELD_CODES
            | self.ELECTRICAL_PRIMARY_TABLE_PREFERRED_FIELD_CODES
            | self.WIND_FOUNDATION_TABLE_PREFERRED_FIELD_CODES
        )
        combined_skip_codes = configured_scalar_override_codes - table_preferred_codes
        self._apply_land_field_overrides(fields, details)
        self._drop_combined_detail_only_field_candidates(fields, skip_codes=combined_skip_codes)
        self._apply_combined_detail_field_overrides(fields, details, skip_codes=combined_skip_codes)
        self._apply_wind_resource_collection_overrides(ast, fields, details, skip_codes=combined_skip_codes)
        self._apply_road_parameter_field_overrides(fields, details, skip_codes=combined_skip_codes)
        self._apply_electrical_primary_table_field_overrides(ast, fields, skip_codes=combined_skip_codes)
        self._apply_generation_field_overrides(ast, fields, skip_codes=generation_skip_codes)
        self._apply_wind_foundation_table_field_overrides(ast, fields, skip_codes=combined_skip_codes)
        self._apply_finance_field_overrides(ast, fields, skip_codes=configured_scalar_override_codes)
        self._apply_earthwork_field_overrides(ast, fields, skip_codes=configured_scalar_override_codes)
        self._apply_investment_summary_field_overrides(ast, fields, skip_codes=configured_scalar_override_codes)
        self._apply_cover_text_overrides(ast, fields)
        self._apply_cover_ocr_overrides(ast, fields)
        overrides = self._extract_scalar_overrides(ast, skip_codes=configured_scalar_override_codes)
        overrides.update(configured_scalar_overrides)
        overrides.update(self._common_project_overview_scalar_override_values(ast))
        overrides.update(self._geology_scalar_override_values(ast))
        overrides.update(self._resource_scalar_override_values(ast))
        overrides.update(self._environmental_water_conservation_scalar_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._investment_basis_scalar_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._finance_curtailment_scalar_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._finance_grid_price_scalar_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._finance_text_scalar_override_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._finance_capital_irr_scalar_values(ast, skip_codes=configured_scalar_override_codes))
        overrides.update(self._finance_table_scalar_override_values(ast, skip_codes=configured_scalar_override_codes))
        explicit_road_table_keys = self._road_parameter_row_from_tables(ast)[1] if ast is not None else set()
        for code, override in overrides.items():
            name, value, unit, evidence_text, *rest = override
            if code in self.ROAD_PARAMETER_FIELD_CODES and fields.get(code) is not None and fields[code].value is not None:
                continue
            if (
                code in table_preferred_codes
                and fields.get(code) is not None
                and fields[code].value is not None
                and any(evidence.source_type == "table" for evidence in fields[code].evidence)
                and not self._values_equivalent(fields[code].value, value)
            ):
                continue
            if code in explicit_road_table_keys:
                continue
            if (
                code in self.GENERATION_TABLE_PREFERRED_FIELD_CODES
                and fields.get(code) is not None
                and fields[code].value is not None
                and not self._values_equivalent(fields[code].value, value)
            ):
                continue
            source_type = rest[0] if rest else "table"
            meta = rest[1] if len(rest) > 1 and isinstance(rest[1], dict) else None
            self._set_field(fields, code, name, value, unit, evidence_text, source_type=source_type, meta=meta)
        if ast is not None:
            self._clear_ambiguous_maintenance_road_length_field(fields, ast)
            self._clear_invalid_site_road_length_field(fields)

    def _drop_combined_detail_only_field_candidates(self, fields: dict[str, ParsedField], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        for code in self.COMBINED_DETAIL_ONLY_FIELD_CODES:
            if code not in skip_codes:
                fields.pop(code, None)

    def _apply_combined_detail_field_overrides(self, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]], skip_codes: set[str] | None = None) -> None:
        skip_codes = skip_codes or set()
        specs = self.combined_detail_field_specs
        for detail_key, spec in specs.items():
            rows = [row for row in details.get(detail_key, []) if isinstance(row, dict)]
            if not rows:
                continue
            for field_code, source_key in spec["fields"].items():
                if field_code in skip_codes:
                    continue
                value_rows = [row for row in rows if self._empty_to_none(row.get(source_key)) is not None]
                values = [self._empty_to_none(row.get(source_key)) for row in value_rows]
                if not values:
                    continue
                value = values if spec.get("multi") else values[0]
                name, unit = self.required_field_meta.get(field_code, (field_code, None))
                evidences = [
                    self._combined_field_evidence_from_row(row, source_key, detail_key)
                    for row in value_rows
                ]
                evidences = [evidence for evidence in evidences if evidence is not None]
                if spec.get("multi") and evidences:
                    self._set_field_with_evidence(fields, field_code, name, value, unit, evidences)
                elif evidences:
                    self._set_field_with_evidence(fields, field_code, name, value, unit, [evidences[0]])

    def _extract_scalar_overrides(self, ast: DocumentAST, skip_codes: set[str] | None = None) -> dict[str, tuple[str, Any, str | None, str]]:
        skip_codes = skip_codes or set()
        overrides: dict[str, tuple[str, Any, str | None, str]] = {}
        max_wind_speed = None if "maxWindSpeed50Year" in skip_codes else self._max_wind_speed_50_year_from_document(ast)
        if max_wind_speed is not None:
            overrides["maxWindSpeed50Year"] = (
                "50年一遇最大风速值",
                max_wind_speed,
                "m/s",
                self._field_evidence_text_for_value(ast, max_wind_speed, ["50年一遇", "最大风速"]),
                "paragraph",
                {
                    "resolver": "deterministic_max_wind_speed_50_year",
                    "sectionPath": ["资源章节"],
                },
            )
        safety_class = None if "selectedTurbineSafetyClass" in skip_codes else self._selected_turbine_safety_class_from_ast(ast)
        if safety_class is not None:
            overrides["selectedTurbineSafetyClass"] = (
                "最终宜选机型",
                safety_class,
                None,
                self._field_evidence_text_for_value(ast, safety_class, ["IEC"]),
                "paragraph",
                {"resolver": "deterministic_turbine_safety_class", "sectionPath": ["资源章节"]},
            )
        communication_power = None if "communicationPowerDesign" in skip_codes else self._communication_power_design_from_ast(ast)
        if communication_power is not None:
            overrides["communicationPowerDesign"] = (
                "通讯电源设计",
                communication_power,
                None,
                self._field_evidence_text_for_value(ast, communication_power, ["通讯", "电源"]),
                "paragraph",
                {"resolver": "deterministic_communication_power", "sectionPath": ["电气二次"]},
            )
        communication_power_unit_quantity = self._communication_power_unit_quantity_from_ast(ast)
        if communication_power_unit_quantity is not None:
            unit_value, quantity_value, evidence_text, section_path = communication_power_unit_quantity
            if "communicationPowerUnitType" not in skip_codes and unit_value is not None:
                overrides["communicationPowerUnitType"] = (
                    "通讯电源设计单位",
                    unit_value,
                    None,
                    evidence_text,
                    "table" if " | " in evidence_text else "paragraph",
                    {"resolver": "deterministic_communication_power_unit", "sectionPath": section_path},
                )
            if "communicationPowerQuantityValue" not in skip_codes and quantity_value is not None:
                overrides["communicationPowerQuantityValue"] = (
                    "通讯电源设计数量",
                    quantity_value,
                    None,
                    evidence_text,
                    "table" if " | " in evidence_text else "paragraph",
                    {"resolver": "deterministic_communication_power_quantity", "sectionPath": section_path},
                )
        communication_power_description = (
            None
            if "communicationPowerDesignDescription" in skip_codes
            else self._communication_power_design_description_from_ast(ast)
        )
        if communication_power_description is not None:
            overrides["communicationPowerDesignDescription"] = (
                "通讯电源设计描述",
                communication_power_description,
                None,
                communication_power_description,
                "paragraph",
                {"resolver": "deterministic_communication_power_description", "sectionPath": ["电气二次"]},
            )
        electrical_text_values = self._electrical_text_scalar_values(ast, skip_codes=skip_codes)
        overrides.update(electrical_text_values)
        collector_text_values = self._collector_line_text_scalar_values(ast, skip_codes=skip_codes)
        overrides.update(collector_text_values)
        road_text_values = self._road_text_scalar_values(ast, skip_codes=skip_codes)
        overrides.update(road_text_values)
        foundation_text_values = self._wind_foundation_text_scalar_values(ast, skip_codes=skip_codes)
        overrides.update(foundation_text_values)
        return overrides

    def _configured_scalar_overrides(self, ast: DocumentAST) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        for code, config in self.field_configs.items():
            rules = self._configured_scalar_rules(config)
            if not rules:
                continue
            candidate = self._best_configured_scalar_candidate(ast, code, config, rules)
            if candidate is None:
                continue
            name = str(config.get("name") or self.required_field_meta.get(code, (code, None))[0])
            unit = candidate.get("unit") or config.get("standard_unit") or self.required_field_meta.get(code, (None, None))[1]
            overrides[code] = (
                name,
                candidate["value"],
                unit,
                candidate["evidenceText"],
                candidate["sourceType"],
                candidate["meta"],
            )
        return overrides

    def _configured_scalar_field_codes(self) -> set[str]:
        return {code for code, config in self.field_configs.items() if self._configured_scalar_rules(config)}

    def _configured_scalar_rules(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        rules = config.get("scalar_rules") or []
        if isinstance(rules, list) and rules:
            return [rule for rule in rules if isinstance(rule, dict)]
        if not config.get("scalar_from_patterns"):
            return []
        patterns = config.get("patterns") or []
        if not isinstance(patterns, list) or not patterns:
            return []
        sections = config.get("sections") or {}
        return [
            {
                "name": "字段配置 patterns",
                "source_types": config.get("source_types") or ["paragraph", "table"],
                "value_type": config.get("value_type") or "string",
                "patterns": patterns,
                "section_include": sections.get("include") if isinstance(sections, dict) else [],
                "section_exclude": sections.get("exclude") if isinstance(sections, dict) else [],
                "validators": config.get("validators") or {},
                "prefer_any": config.get("prefer_any") or {},
                "penalize_any": config.get("penalize_any") or {},
            }
        ]

    def _best_configured_scalar_candidate(
        self,
        ast: DocumentAST,
        code: str,
        config: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for rule_index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            for source in self._configured_scalar_sources(ast, rule):
                source_text = source["text"]
                if not self._configured_rule_source_allowed(source, rule):
                    continue
                if self._configured_rule_rejected(source_text, rule):
                    continue
                candidates.extend(self._configured_scalar_matches(code, config, rule, rule_index, source))
        if not candidates:
            return None
        strategy = str((config.get("scalar_selection") or {}).get("strategy") or "score").lower()
        if strategy == "sum":
            return self._configured_scalar_sum_candidate(candidates)
        if strategy == "max_value":
            candidates.sort(key=lambda item: (self._numeric_sort_value(item.get("value")), item["score"], item["order"]), reverse=True)
        elif strategy == "last":
            candidates.sort(key=lambda item: (item["order"], item.get("matchStart") or 0, item["score"]), reverse=True)
        else:
            candidates.sort(key=lambda item: (item["score"], item["order"], item.get("matchStart") or 0), reverse=True)
        return candidates[0]

    def _configured_scalar_sum_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        unique: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for candidate in sorted(candidates, key=lambda item: (item.get("order") or 0, item.get("matchStart") or 0)):
            identity = self._configured_scalar_sum_identity(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            if self._numeric_sort_value(candidate.get("value")) == float("-inf"):
                continue
            unique.append(candidate)
        if not unique:
            return None
        total = self._clean_number(sum(float(candidate["value"]) for candidate in unique))
        base = dict(unique[-1])
        matched_texts = [str((candidate.get("meta") or {}).get("matchedText") or candidate.get("evidenceText")) for candidate in unique]
        matched_patterns = []
        for candidate in unique:
            pattern = (candidate.get("meta") or {}).get("matchedPattern")
            if pattern and pattern not in matched_patterns:
                matched_patterns.append(pattern)
        base["value"] = total
        base["score"] = max(float(candidate.get("score") or 0) for candidate in unique)
        base["evidenceText"] = "\n".join(matched_texts)
        base["meta"] = dict(base.get("meta") or {})
        base["meta"].update(
            {
                "aggregate": "sum",
                "matchedCount": len(unique),
                "matchedText": "\n".join(matched_texts),
                "matchedPattern": matched_patterns,
                "score": base["score"],
            }
        )
        return base

    def _configured_scalar_sum_identity(self, candidate: dict[str, Any]) -> tuple[Any, ...]:
        meta = candidate.get("meta") or {}
        dedupe_by = meta.get("dedupeBy")
        if isinstance(dedupe_by, list) and dedupe_by:
            return tuple(self._configured_scalar_identity_component(candidate, str(item)) for item in dedupe_by)
        if isinstance(dedupe_by, str) and dedupe_by:
            return tuple(self._configured_scalar_identity_component(candidate, item.strip()) for item in dedupe_by.split("+") if item.strip())
        return (candidate.get("sourceType"), meta.get("blockId"), meta.get("tableId"), candidate.get("matchStart"), meta.get("matchedText"))

    def _configured_scalar_identity_component(self, candidate: dict[str, Any], name: str) -> Any:
        meta = candidate.get("meta") or {}
        key = name.strip().lower().replace("-", "_")
        if key == "value":
            return candidate.get("value")
        if key == "unit":
            return candidate.get("unit") or meta.get("normalizedUnit") or meta.get("rawUnit")
        if key == "page":
            return meta.get("page")
        if key in {"matched_pattern", "pattern"}:
            return meta.get("matchedPattern")
        if key in {"matched_text", "text"}:
            return meta.get("matchedText")
        if key == "source_type":
            return candidate.get("sourceType")
        if key == "block_id":
            return meta.get("blockId")
        if key == "table_id":
            return meta.get("tableId")
        if key == "match_start":
            return candidate.get("matchStart")
        return meta.get(name) or candidate.get(name)

    def _configured_scalar_sources(self, ast: DocumentAST, rule: dict[str, Any]) -> list[dict[str, Any]]:
        source_types = rule.get("source_types") or rule.get("source_type") or ["paragraph", "table"]
        if isinstance(source_types, str):
            source_types = [source_types]
        sources: list[dict[str, Any]] = []
        if "paragraph" in source_types:
            for block in self._body_blocks(ast):
                text = self._clean_text(block.text or "")
                if not text:
                    continue
                sources.append(
                    {
                        "sourceType": "paragraph",
                        "text": text,
                        "order": block.order,
                        "page": block.page,
                        "blockId": block.id,
                        "tableId": None,
                        "sectionPath": self._source_section_path(
                            block.section_path,
                            (block.meta.get("canonical_sections") if isinstance(block.meta, dict) else []) or [],
                        ),
                        "inferredSections": self._inferred_source_sections(text),
                    }
                )
        if "document" in source_types:
            body_blocks = self._body_blocks(ast)
            parts = [self._clean_text(block.text or "") for block in body_blocks if block.text]
            text = "\n".join(part for part in parts if part)
            if text.strip():
                sources.append(
                    {
                        "sourceType": "document",
                        "text": text,
                        "order": max((block.order for block in body_blocks), default=0),
                        "page": None,
                        "blockId": None,
                        "tableId": None,
                        "sectionPath": [],
                        "isDocumentAggregate": True,
                    }
                )
        if "pdf_page_text" in source_types:
            page_section_paths = self._page_section_path_map(ast)
            for item in (ast.meta or {}).get("pdf_page_texts") or []:
                if not isinstance(item, dict):
                    continue
                text = self._clean_text(str(item.get("text") or ""))
                if not text or self._is_toc_like_text(text):
                    continue
                page = item.get("page")
                try:
                    page_number = int(page) if page is not None else None
                except (TypeError, ValueError):
                    page_number = None
                sources.append(
                    {
                        "sourceType": "pdf_page_text",
                        "text": text,
                        "order": page_number or 0,
                        "page": page_number,
                        "blockId": None,
                        "tableId": None,
                        "sectionPath": list(page_section_paths.get(page_number or -1) or []),
                        "inferredSections": self._inferred_source_sections(text),
                    }
                )
        if "table" in source_types:
            for table in ast.tables:
                matrix = self._table_matrix(table)
                text = self._matrix_text(matrix)
                if not text.strip():
                    continue
                caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
                evidence_text = "\n".join(part for part in [caption, text] if part)
                sources.append(
                    {
                        "sourceType": "table",
                        "text": evidence_text,
                        "order": table.order,
                        "page": table.page,
                        "blockId": None,
                        "tableId": table.id,
                        "sectionPath": self._source_section_path(
                            table.section_path,
                            (table.meta.get("canonical_sections") if isinstance(table.meta, dict) else []) or [],
                        ),
                        "inferredSections": self._inferred_source_sections(evidence_text),
                    }
                )
        return sources

    def _configured_rule_source_allowed(self, source: dict[str, Any], rule: dict[str, Any]) -> bool:
        section_text = " / ".join(source.get("sectionPath") or [])
        include_sections = rule.get("section_include") or rule.get("sections_include") or []
        exclude_sections = rule.get("section_exclude") or rule.get("sections_exclude") or []
        compact_section = self._compact_text(section_text)
        if include_sections:
            include_matched = bool(section_text) and any(str(keyword) in section_text or self._compact_text(str(keyword)) in compact_section for keyword in include_sections)
            if not include_matched:
                fallback_allowed = self._configured_section_fallback_allowed(source, rule)
                unsectioned_allowed = bool(rule.get("allow_unsectioned")) and not section_text
                if not fallback_allowed and not unsectioned_allowed and not bool(rule.get("allow_section_mismatch")):
                    return False
        if exclude_sections and any(str(keyword) in section_text or self._compact_text(str(keyword)) in compact_section for keyword in exclude_sections):
            return False
        require_any = rule.get("require_any") or []
        source_text = source.get("text", "")
        compact_source = self._compact_text(source_text)
        if require_any and not any(str(keyword) in source_text or self._compact_text(str(keyword)) in compact_source for keyword in require_any):
            return False
        return True

    def _configured_section_fallback_allowed(self, source: dict[str, Any], rule: dict[str, Any]) -> bool:
        required = rule.get("section_fallback_require_all") or rule.get("fallback_require_all") or []
        if isinstance(required, str):
            required = [required]
        if not required:
            return False
        source_text = source.get("text", "")
        compact_source = self._compact_text(source_text)
        return all(str(keyword) in source_text or self._compact_text(str(keyword)) in compact_source for keyword in required)

    def _configured_rule_rejected(self, text: str, rule: dict[str, Any]) -> bool:
        compact_text = self._compact_text(text)
        if any(str(keyword) in text or self._compact_text(str(keyword)) in compact_text for keyword in (rule.get("reject_any") or [])):
            return True
        for pattern in rule.get("reject_patterns") or []:
            if self._configured_pattern_search(str(pattern), text):
                return True
        return False

    def _configured_scalar_matches(
        self,
        code: str,
        config: dict[str, Any],
        rule: dict[str, Any],
        rule_index: int,
        source: dict[str, Any],
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for pattern_index, pattern in enumerate(rule.get("patterns") or []):
            for match in self._configured_iter_matches(str(pattern), source["text"]):
                value = self._configured_match_value(match, config, rule)
                if value in (None, ""):
                    continue
                raw_value = value
                unit = self._configured_match_unit(match, config, rule)
                raw_unit = unit
                value, unit = self._normalize_configured_value(code, value, unit)
                if not self._configured_value_allowed(value, config, rule):
                    continue
                window = self._configured_match_window(match.string, match, int(rule.get("evidence_window") or 160))
                score = self._configured_scalar_score(source, window, rule, rule_index, pattern_index)
                match_text = match.group(0)
                matches.append(
                    {
                        "value": value,
                        "unit": unit,
                        "score": score,
                        "order": source.get("order") or 0,
                        "matchStart": match.start(),
                        "sourceType": source.get("sourceType") or "paragraph",
                        "evidenceText": window or match_text,
                        "meta": {
                            "ruleSource": str(config.get("config_path") or "configs/fields/*.yaml"),
                            "configuredField": code,
                            "configuredRule": rule.get("name") or rule.get("id") or f"scalar_rules[{rule_index}]",
                            "matchedPattern": str(pattern),
                            "matchedText": match_text,
                            "dedupeBy": rule.get("dedupe_by") or rule.get("dedupeBy"),
                            "rawValue": raw_value,
                            "rawUnit": raw_unit,
                            "normalizedUnit": unit,
                            "score": score,
                            "sectionPath": source.get("sectionPath") or [],
                            "inferredSections": source.get("inferredSections") or [],
                            "blockId": source.get("blockId"),
                            "tableId": source.get("tableId"),
                            "page": source.get("page"),
                            "matchMethod": "configured_scalar_rule",
                            "resolver": "configured_scalar_rule",
                        },
                    }
                )
        return matches

    def _configured_match_value(self, match: re.Match[str], config: dict[str, Any], rule: dict[str, Any]) -> Any:
        value_group = rule.get("value_group", "value")
        raw: str | None = None
        if isinstance(value_group, int):
            raw = match.group(value_group)
        else:
            try:
                raw = match.group(str(value_group))
            except IndexError:
                raw = None
            if raw is None:
                raw = match.group(1) if match.lastindex else match.group(0)
        if raw is None:
            return None
        value_type = str(rule.get("value_type") or config.get("value_type") or "string")
        if value_type == "number":
            return self._normalize_scalar(str(raw))
        value = self._normalize_text_value(str(raw))
        if rule.get("compact"):
            value = re.sub(r"\s+", "", value)
        replacements = rule.get("replace") or []
        for item in replacements:
            if isinstance(item, dict) and "pattern" in item:
                value = re.sub(str(item["pattern"]), str(item.get("with", "")), value)
        join_patterns = rule.get("join_patterns") or []
        if join_patterns:
            parts: list[str] = [value] if value else []
            for pattern in join_patterns:
                found = re.search(str(pattern), match.string, flags=re.IGNORECASE | re.MULTILINE)
                if found:
                    part = self._normalize_text_value(found.group(1) if found.lastindex else found.group(0))
                    if part and part not in parts:
                        parts.append(part)
            if parts:
                return "\n".join(parts)
        return value

    def _configured_match_unit(self, match: re.Match[str], config: dict[str, Any], rule: dict[str, Any]) -> str | None:
        unit_group = rule.get("unit_group", "unit")
        try:
            unit = match.group(str(unit_group)) if not isinstance(unit_group, int) else match.group(unit_group)
        except IndexError:
            unit = None
        return unit or rule.get("unit") or config.get("standard_unit") or config.get("unit")

    def _normalize_configured_value(self, code: str, value: Any, unit: str | None) -> tuple[Any, str | None]:
        if code in {
            "windResourceAirDensityRecords",
            "hubHeightAverageWindSpeedRecords",
            "hubHeightAverageWindPowerDensityRecords",
            "windResourceTurbulenceIntensityRecords",
        } and isinstance(value, list):
            return value, self.normalizer._normalize_unit(unit)
        if code == "constructionPeriodYears" and isinstance(value, str) and re.fullmatch(r"\s*[0-9]+(?:\.[0-9]+)?\s*(?:年|个月|月)\s*", value):
            return self._normalize_period_value(value)
        if code == "staffSalary" and isinstance(value, (int, float)):
            return value, self.normalizer._normalize_unit(unit)
        if code in {
            "selectedTurbineSafetyClass",
            "stationTransformerCapacity10kv",
            "groundingTransformerCapacity35kv",
            "groundingStationTransformerCapacity35kv",
            "svgReactiveCompensationCapacity",
            "dcBatteryConfiguration",
            "upsPowerConfiguration",
            "foundationCapDiameter",
            "foundationColumnDiameter",
            "pileOuterDiameter",
        }:
            return self._normalize_text_value(str(value)) if value is not None else None, self.normalizer._normalize_unit(unit)
        if code not in self.field_configs:
            return value, self.normalizer._normalize_unit(unit)
        value = self.normalizer._normalize_value(code, value)
        unit = self.normalizer._normalize_unit(unit)
        return self.normalizer._convert_to_standard_unit(code, value, unit)

    def _normalize_period_value(self, value: str) -> tuple[Any, str | None]:
        """把建设期文本归一为数值和月/年单位。"""
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(年|个月|月)\s*", value)
        if not match:
            return self._normalize_text_value(value), None
        number = self._clean_number(float(match.group(1)))
        unit = "月" if match.group(2) in {"个月", "月"} else "年"
        return number, unit

    def _configured_iter_matches(self, pattern: str, text: str):
        compiled = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
        seen: set[tuple[int, int, str]] = set()
        for match in compiled.finditer(text):
            identity = (match.start(), match.end(), match.group(0))
            seen.add(identity)
            yield match
        compact_text = self._compact_text(text)
        if compact_text == text:
            return
        for match in compiled.finditer(compact_text):
            identity = (match.start(), match.end(), match.group(0))
            if identity in seen:
                continue
            yield match

    def _configured_pattern_search(self, pattern: str, text: str) -> bool:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            return True
        compact_text = self._compact_text(text)
        return compact_text != text and bool(re.search(pattern, compact_text, flags=re.IGNORECASE | re.MULTILINE))

    def _configured_value_allowed(self, value: Any, config: dict[str, Any], rule: dict[str, Any]) -> bool:
        if self._configured_value_is_field_label(value, config):
            return False
        validators = dict(config.get("validators") or {})
        validators.update(rule.get("validators") or {})
        if validators.get("allow_pattern") and not re.search(str(validators["allow_pattern"]), str(value), flags=re.IGNORECASE):
            return False
        for pattern in validators.get("reject_patterns") or []:
            if re.search(str(pattern), str(value), flags=re.IGNORECASE):
                return False
        if isinstance(value, (int, float)):
            if validators.get("min") is not None and value < float(validators["min"]):
                return False
            if validators.get("max") is not None and value > float(validators["max"]):
                return False
        return True

    def _configured_value_is_field_label(self, value: Any, config: dict[str, Any]) -> bool:
        if not isinstance(value, str):
            return False
        compact_value = re.sub(r"\s+", "", self._normalize_text_value(value))
        if not compact_value:
            return True
        labels = [config.get("name"), *(config.get("aliases") or [])]
        for label in labels:
            if not label:
                continue
            compact_label = re.sub(r"\s+", "", self._normalize_text_value(str(label)))
            if compact_label and compact_value == compact_label:
                return True
        return False

    def _configured_scalar_score(self, source: dict[str, Any], window: str, rule: dict[str, Any], rule_index: int, pattern_index: int) -> float:
        score = float(rule.get("score") or 100)
        section_text = " / ".join(source.get("sectionPath") or [])
        compact_section = self._compact_text(section_text)
        compact_window = self._compact_text(window)
        for keyword, weight in (rule.get("section_scores") or {}).items():
            if str(keyword) in section_text or self._compact_text(str(keyword)) in compact_section:
                score += float(weight)
        for keyword, weight in (rule.get("prefer_any") or {}).items():
            if str(keyword) in window or self._compact_text(str(keyword)) in compact_window:
                score += float(weight)
        for keyword, weight in (rule.get("penalize_any") or {}).items():
            if str(keyword) in window or self._compact_text(str(keyword)) in compact_window:
                score -= float(weight)
        if bool(source.get("isDocumentAggregate")):
            score -= float(rule.get("document_penalty") or 25)
        score -= rule_index * 0.01
        score -= pattern_index * 0.001
        return score

    def _compact_text(self, text: str) -> str:
        return "".join(str(text or "").split())

    def _configured_match_window(self, text: str, match: re.Match[str], size: int) -> str:
        start = max(0, match.start() - size)
        end = min(len(text), match.end() + size)
        return self._clean_text(text[start:end])

    def _numeric_sort_value(self, value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return float("-inf")

    def _apply_quality_filters(self, fields: dict[str, ParsedField], ast: DocumentAST) -> None:
        for code, field in list(fields.items()):
            if code in self.DETERMINISTIC_TEXT_FIELD_CODES and field.debug.get("resolver") in {
                "deterministic_override",
                "deterministic_turbine_safety_class",
                "deterministic_electrical_text",
                "electrical_primary_equipment_table",
                "deterministic_wind_foundation_text",
                "deterministic_finance_text",
            }:
                continue
            config = self.field_configs.get(code) or {}
            if code == "constructionPeriodYears" and field.value is not None and self._valid_construction_period(field.value, field.unit):
                continue
            if config and field.value is not None and not self._configured_value_allowed(field.value, config, {}):
                fields.pop(code, None)

        access_station = fields.get("accessStationName")
        if access_station is not None and self._looks_like_invalid_access_station_name(str(access_station.value)):
            fields.pop("accessStationName", None)
            fields.pop("accessibleVoltage", None)

        project_name = fields.get("projectName")
        if project_name is not None and not self._looks_like_project_name(str(project_name.value)):
            fields.pop("projectName", None)
        if "projectName" not in fields:
            fallback_project_name = self._project_name_from_file_name(ast)
            if fallback_project_name:
                self._set_field(fields, "projectName", "\u9879\u76ee\u540d\u79f0", fallback_project_name, None, ast.file_name, source_type="filename")

        design_unit = fields.get("designUnit")
        if design_unit is not None and not self._looks_like_design_unit(str(design_unit.value)):
            fields.pop("designUnit", None)

        selected = fields.get("selectedTurbineSafetyClass")
        if selected is not None and not self._valid_turbine_safety_class(str(selected.value)):
            fields.pop("selectedTurbineSafetyClass", None)

        wind_speed = fields.get("maxWindSpeed50Year")
        if wind_speed is not None and not self._valid_wind_speed_50_year(wind_speed.value):
            fields.pop("maxWindSpeed50Year", None)

        for code in ("independentLightningRodCount", "frameLightningRodCount"):
            field = fields.get(code)
            if field is None:
                continue
            try:
                value = float(field.value)
            except (TypeError, ValueError):
                fields.pop(code, None)
                continue
            if value < 0 or value > 10:
                fields.pop(code, None)

    def _valid_construction_period(self, value: Any, unit: str | None) -> bool:
        """允许建设期用“月”表达，避免被旧的“年”字段配置误过滤。"""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        if unit in {"月", "个月"}:
            return 0 <= number <= 120
        if unit in {"年", None}:
            return 0 <= number <= 10
        return False
