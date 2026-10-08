"""Project, cover, design unit and site geology extraction rules.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

import re

from typing import Any

from parser_engine.document.ast.document import DocumentAST

from parser_engine.document.ast.evidence import ParsedField

from parser_engine.output.cover_ocr import CoverOcrResult


class ProjectOverviewRulesMixin:
    def _common_project_overview_scalar_override_values(
        self, ast: DocumentAST
    ) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        owner = self._investment_owner_company_from_blocks(ast)
        if owner is not None:
            value, evidence_text, section_path = owner
            overrides["investmentOwnerCompany"] = (
                "投资（建设）单位",
                value,
                None,
                evidence_text,
                "paragraph",
                {"resolver": "project_overview_text", "sectionPath": section_path},
            )
        address = self._project_address_from_blocks(ast)
        if address is not None:
            detail, city, county, town, evidence_text, section_path = address
            values = {
                "projectAddressCity": ("项目地址-所属市", city),
                "projectAddressCounty": ("项目地址-所属县区", county),
                "projectAddressTown": ("项目地址-所属乡镇", town),
                "projectAddressDetail": ("项目地址-详细地址", detail),
            }
            for code, (name, value) in values.items():
                if value:
                    overrides[code] = (
                        name,
                        value,
                        None,
                        evidence_text,
                        "paragraph",
                        {"resolver": "project_overview_text", "sectionPath": section_path},
                    )
        return overrides

    def _investment_owner_company_from_blocks(self, ast: DocumentAST) -> tuple[str, str, list[str]] | None:
        company_pattern = re.compile(r"(?P<value>[\u4e00-\u9fa5A-Za-z0-9（）()·]{2,60}(?:有限责任公司|股份有限公司|集团有限公司|有限公司|公司))")
        keyword_pattern = re.compile(r"(?:投资方|建设单位|项目单位)[:：\s]*[为是]?\s*(?P<value>[\u4e00-\u9fa5A-Za-z0-9（）()·]{2,60}(?:有限责任公司|股份有限公司|集团有限公司|有限公司|公司))")
        best: tuple[str, str, list[str]] | None = None
        owner_context_remaining = 0
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            section_text = " / ".join(section_path)
            if "投资方" in text and "概况" in text:
                owner_context_remaining = 8
                continue
            match = keyword_pattern.search(text)
            if match:
                return match.group("value"), match.group(0), section_path
            in_owner_section = "投资方" in section_text or "项目单位概况" in section_text or owner_context_remaining > 0
            if not in_owner_section:
                continue
            match = company_pattern.search(text)
            if owner_context_remaining > 0:
                owner_context_remaining -= 1
            if not match:
                continue
            value = match.group("value")
            if any(token in value for token in ("设计", "咨询", "勘测", "施工")):
                continue
            best = (value, match.group(0), section_path)
            break
        return best

    def _project_address_from_blocks(self, ast: DocumentAST) -> tuple[str, str | None, str | None, str | None, str, list[str]] | None:
        location_pattern = re.compile(r"(?:项目|工程|场址|拟建场区)[^。；;\n]{0,30}(?:位于|地处)\s*(?P<value>[^，。；;\n]{2,120})")
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            section_text = " / ".join(section_path)
            if not any(keyword in f"{section_text} {text}" for keyword in ("工程概况", "项目概况", "场址", "总论")):
                continue
            for match in location_pattern.finditer(text):
                detail = self._clean_text(match.group("value"))
                city, county, town = self._split_project_address(detail)
                if city and county and town:
                    return detail, city, county, town, match.group(0), section_path
        return None

    def _split_project_address(self, detail: str) -> tuple[str | None, str | None, str | None]:
        city_match = re.search(r"(?:[\u4e00-\u9fa5]{2,12}(?:省|自治区))?(?P<value>[\u4e00-\u9fa5]{2,12}市)", detail)
        city = city_match.group("value") if city_match else None
        county_pattern = r"(?:[\u4e00-\u9fa5]{2,12}(?:省|自治区))?(?:[\u4e00-\u9fa5]{2,12}市)?(?P<value>[\u4e00-\u9fa5]{1,12}(?:县|区|旗))"
        county_match = re.search(county_pattern, detail)
        county = county_match.group("value") if county_match else None
        town_pattern = r"(?:[\u4e00-\u9fa5]{2,12}(?:省|自治区))?(?:[\u4e00-\u9fa5]{2,12}市)?(?:[\u4e00-\u9fa5]{1,12}(?:县|区|旗))?(?P<value>[\u4e00-\u9fa5]{1,16}(?:镇|乡|街道|苏木))"
        town_match = re.search(town_pattern, detail)
        town = town_match.group("value") if town_match else None
        return city, county, town

    def _geology_scalar_override_values(
        self, ast: DocumentAST
    ) -> dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]]:
        overrides: dict[str, tuple[str, Any, str | None, str, str, dict[str, Any]]] = {}
        geomorphology = self._project_geomorphology_from_blocks(ast)
        if geomorphology is not None:
            value, evidence_text, section_path = geomorphology
            overrides["projectGeomorphology"] = (
                "项目地貌",
                value,
                None,
                evidence_text,
                "paragraph",
                {"resolver": "geology_text", "sectionPath": section_path},
            )
        vegetation = self._surface_vegetation_from_ast(ast)
        if vegetation is not None:
            value, evidence_text, source_type, section_path = vegetation
            overrides["surfaceVegetationType"] = (
                "地表类型",
                value,
                None,
                evidence_text,
                source_type,
                {"resolver": "geology_text", "sectionPath": section_path},
            )
        elevation = self._site_elevation_range_from_blocks(ast)
        if elevation is not None:
            value, evidence_text, section_path = elevation
            overrides["siteElevationRange"] = (
                "场区海拔高度",
                value,
                "m",
                evidence_text,
                "paragraph",
                {"resolver": "geology_text", "sectionPath": section_path},
            )
        return overrides

    def _project_geomorphology_from_blocks(self, ast: DocumentAST) -> tuple[str, str, list[str]] | None:
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            context = f"{' / '.join(section_path)} {text}"
            if not self._is_geology_or_summary_context(context):
                continue
            for sentence in self._sentences(text):
                if not any(keyword in sentence for keyword in ("地处", "主要地貌", "场区地貌")):
                    continue
                value = self._geomorphology_value_from_sentence(sentence)
                if value:
                    return value, sentence, section_path
        return None

    def _geomorphology_value_from_sentence(self, sentence: str) -> str | None:
        patterns = [
            r"(?:主要地貌|场区地貌)[:：\s为是]*(?P<value>[^，。；;]{2,80})",
            r"(?:地处|位于)(?P<value>[^。；;]{2,120}?地貌)",
        ]
        for pattern in patterns:
            match = re.search(pattern, sentence)
            if not match:
                continue
            value = self._clean_text(match.group("value"))
            value = re.sub(r"^(?:类型)?(?:为|是)", "", value).strip(" ，,。；;")
            if value:
                return value
        if "地貌" in sentence:
            return sentence.strip(" ，,。；;")
        return None

    def _surface_vegetation_from_ast(self, ast: DocumentAST) -> tuple[str, str, str, list[str]] | None:
        vegetation_terms = r"果树|旱地|荒漠|荒草|草地|灌木|乔木|林地|农田|耕地"
        explicit_vegetation_pattern = re.compile(fr"地表植被[^。；;\n]{{0,12}}?(?:为|是|：|:)?\s*(?P<value>{vegetation_terms})")
        generic_surface_pattern = re.compile(fr"地表[^。；;\n]{{0,12}}?(?:为|是|：|:)?\s*(?P<value>{vegetation_terms})")
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            context = f"{' / '.join(section_path)} {text}"
            if not self._is_geology_or_summary_context(context):
                continue
            match = explicit_vegetation_pattern.search(text)
            if match:
                return match.group("value"), match.group(0), "paragraph", section_path
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            section_path = list(table.section_path or [])
            context = f"{table.caption or ''} {' / '.join(section_path)} {self._matrix_text(matrix)}"
            if not self._is_geology_or_summary_context(context) and "地表植被" not in context:
                continue
            for row_index, row in enumerate(matrix):
                for col_index, cell in enumerate(row):
                    if "地表植被" not in cell:
                        continue
                    for value_row in matrix[row_index + 1 :]:
                        if col_index >= len(value_row):
                            continue
                        value = self._clean_text(value_row[col_index])
                        if value and value != "地表植被":
                            return value, value, "table", section_path
            match = explicit_vegetation_pattern.search(context)
            if match:
                return match.group("value"), match.group(0), "table", section_path
        generic_matches: list[tuple[str, str, str, list[str]]] = []
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            context = f"{' / '.join(section_path)} {text}"
            if not self._is_geology_or_summary_context(context):
                continue
            for match in generic_surface_pattern.finditer(text):
                generic_matches.append((match.group("value"), match.group(0), "paragraph", section_path))
        if generic_matches:
            counts: dict[str, int] = {}
            for value, *_ in generic_matches:
                counts[value] = counts.get(value, 0) + 1
            return max(generic_matches, key=lambda item: counts[item[0]])
        return None

    def _site_elevation_range_from_blocks(self, ast: DocumentAST) -> tuple[str, str, list[str]] | None:
        geology_match: tuple[str, str, list[str]] | None = None
        summary_match: tuple[str, str, list[str]] | None = None
        for block in ast.blocks:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            section_path = list(block.section_path or [])
            context = f"{' / '.join(section_path)} {text}"
            if not any(keyword in context for keyword in ("海拔高程", "海拔高度", "海拔")):
                continue
            match = self._elevation_range_from_text(text)
            if match is None:
                continue
            value, evidence_text = match
            item = (value, evidence_text, section_path)
            if self._is_geology_context(context):
                geology_match = item
                break
            if summary_match is None and self._is_summary_context(context):
                summary_match = item
        return geology_match or summary_match

    def _elevation_range_from_text(self, text: str) -> tuple[str, str] | None:
        keyword_pattern = r"(?:海拔高程|海拔高度|海拔)"
        range_pattern = r"(?P<start>[0-9]+(?:\.[0-9]+)?)\s*(?P<start_unit>m|米)?\s*(?:~|～|至|-|—)\s*(?P<end>[0-9]+(?:\.[0-9]+)?)\s*(?P<end_unit>m|米)?"
        match = re.search(fr"{keyword_pattern}[^。；;\n]{{0,30}}?{range_pattern}", text)
        if not match:
            return None
        start = match.group("start")
        end = match.group("end")
        start_unit = "m" if match.group("start_unit") in (None, "米", "m") else match.group("start_unit")
        end_unit = "m" if match.group("end_unit") in (None, "米", "m") else match.group("end_unit")
        value = f"{start}{start_unit}~{end}{end_unit}"
        return value, match.group(0)

    def _is_geology_or_summary_context(self, context: str) -> bool:
        return self._is_geology_context(context) or self._is_summary_context(context)

    def _is_geology_context(self, context: str) -> bool:
        return any(keyword in context for keyword in ("地勘章节", "工程地质", "地质", "地形地貌"))

    def _is_summary_context(self, context: str) -> bool:
        return any(keyword in context for keyword in ("综合说明", "工程概况", "项目概况", "总论"))

    def _apply_cover_text_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField]) -> None:
        cover_text = self._cover_text_before_toc(ast)
        if not cover_text:
            return
        values = {
            "projectName": self._project_name_from_cover_text(cover_text),
            "designUnit": self._design_unit_from_cover_text(cover_text),
            "designUnitQualification": self._design_unit_qualification_from_cover_text(cover_text),
        }
        for code, value in values.items():
            if value:
                name, unit = self.required_field_meta.get(code, (code, None))
                self._set_field(
                    fields,
                    code,
                    name,
                    value,
                    unit,
                    cover_text,
                    source_type="cover_text",
                    meta={"resolver": "cover_text", "sectionPath": ["封面"]},
                )

    def _cover_text_before_toc(self, ast: DocumentAST) -> str:
        lines: list[str] = []
        for block in ast.blocks[:80]:
            text = self._clean_text(block.text or "")
            if not text:
                continue
            normalized = re.sub(r"\s+", "", text)
            if normalized in {"\u76ee\u5f55", "contents", "Contents"} or re.fullmatch(r"(?:\u7b2c?[0-9\u4e00-\u9fa5]{0,4}[.\s]*)?\u76ee\u5f55", normalized):
                break
            lines.append(text)
        return "\n".join(lines)

    def _project_name_from_cover_text(self, text: str) -> str | None:
        for line in text.splitlines()[:30]:
            cleaned = self._clean_text(line)
            cleaned = re.sub(r"\s+", "", cleaned)
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\-]{4,90}(?:\u98ce\u7535|\u98ce\u529b\u53d1\u7535)[\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\-]{0,30}\u9879\u76ee)", cleaned)
            if match:
                return self._normalize_text_value(match.group(1))
        return None

    def _design_unit_from_cover_text(self, text: str) -> str | None:
        candidates: list[str] = []
        for line in text.splitlines()[:50]:
            cleaned = self._normalize_text_value(line)
            compact = re.sub(r"\s+", "", cleaned)
            if not compact or len(compact) > 90:
                continue
            if any(token in compact for token in ("\u8bc1\u4e66", "\u7b49\u7ea7", "\u76ee\u5f55", "\u53ef\u884c\u6027\u7814\u7a76\u62a5\u544a")):
                continue
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\-]{4,90}(?:\u516c\u53f8|\u8bbe\u8ba1\u9662|\u7814\u7a76\u9662|\u5de5\u7a0b\u9662|\u6709\u9650\u516c\u53f8))", compact)
            if match:
                value = self._normalize_text_value(match.group(1))
                if self._looks_like_design_unit(value):
                    candidates.append(value)
        return max(candidates, key=len) if candidates else None

    def _design_unit_qualification_from_cover_text(self, text: str) -> str | None:
        normalized = text
        normalized = re.sub(r"[\u7533\u7528\u7530][\u7ea7\u6975\u6781\u573e]", "\u7532\u7ea7", normalized)
        normalized = re.sub(r"\u7532[\u6975\u6781\u573e]", "\u7532\u7ea7", normalized)
        normalized = re.sub(r"\u4e59[\u6975\u6781\u573e]", "\u4e59\u7ea7", normalized)
        patterns = [
            r"(?:\u8bbe\u8ba1\u5355\u4f4d\u8d44\u8d28\u7b49\u7ea7|\u8bbe\u8ba1\u8d44\u8d28\u7b49\u7ea7|\u8d44\u8d28\u7b49\u7ea7|\u7b49\u7ea7)[:\uff1a\s]*([\u7532\u4e59\u4e19\u4e01]\u7ea7)",
            r"(?:\u5de5\u7a0b\u8bbe\u8ba1|\u8bbe\u8ba1)[^\n\u3002\uff1b;]{0,20}?([\u7532\u4e59\u4e19\u4e01]\u7ea7)[^\n]{0,20}?\u8bc1\u4e66",
            r"([\u7532\u4e59\u4e19\u4e01]\u7ea7)[^\n]{0,20}?(?:\u8d44\u8d28|\u8d44\u4fe1|\u8bc1\u4e66)",
        ]
        compact = re.sub(r"\s+", "", normalized)
        for source in (normalized, compact):
            for pattern in patterns:
                match = re.search(pattern, source)
                if match:
                    return match.group(1)
        return None

    def _cover_ocr_result(self, ast: DocumentAST) -> CoverOcrResult | None:
        file_path = ast.meta.get("file_path") if ast.meta else None
        if not file_path:
            return None
        if file_path not in self._cover_ocr_cache:
            self._cover_ocr_cache[file_path] = self.cover_ocr_extractor.extract(file_path, ast)
        return self._cover_ocr_cache[file_path]

    def _apply_cover_ocr_overrides(self, ast: DocumentAST, fields: dict[str, ParsedField]) -> None:
        result = self._cover_ocr_result(ast)
        if result is None:
            return
        for code in ("projectName", "designUnit", "designUnitQualification"):
            value = result.values.get(code)
            if value:
                name, unit = self.required_field_meta.get(code, (code, None))
                self._set_field(
                    fields,
                    code,
                    name,
                    value,
                    unit,
                    result.text,
                    source_type="image",
                    meta={"resolver": "cover_ocr", "sectionPath": ["封面", "资质证书"]},
                )

    def _looks_like_project_name(self, value: str) -> bool:
        cleaned = self._clean_text(value)
        if not cleaned or len(cleaned) < 6 or len(cleaned) > 90:
            return False
        bad_words = (
            "\u7bb1\u5f0f\u53d8\u7535\u7ad9",
            "\u7bb1\u53d8",
            "\u534e\u53d8",
            "\u5347\u538b\u7ad9",
            "\u57fa\u7840",
            "\u8bbe\u5907",
            "\u6750\u6599",
        )
        if any(bad in cleaned for bad in bad_words):
            return False
        return bool(re.search(r"(?:\u98ce\u7535|\u98ce\u529b\u53d1\u7535).{0,30}\u9879\u76ee", cleaned))

    def _project_name_from_file_name(self, ast: DocumentAST) -> str | None:
        stem = re.sub(r"\\.(?:docx?|pdf)$", "", ast.file_name or "", flags=re.IGNORECASE)
        stem = re.sub(r"^\\d+[.\u3001_-]?", "", stem)
        pattern = r"([\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\\-]{4,80}(?:\u98ce\u7535|\u98ce\u529b\u53d1\u7535)[\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\\-]{0,30}\u9879\u76ee)"
        match = re.search(pattern, stem)
        return self._normalize_text_value(match.group(1)) if match else None

    def _looks_like_design_unit(self, value: str) -> bool:
        cleaned = self._clean_text(value)
        if not cleaned or len(cleaned) < 4 or len(cleaned) > 90:
            return False
        bad_words = (
            "\u4e13\u9879\u8bbe\u8ba1",
            "\u786e\u5b9a",
            "\u8fdb\u884c",
            "\u7bb1\u5f0f\u53d8\u7535\u7ad9",
            "\u7bb1\u53d8",
            "\u534e\u53d8",
            "\u57fa\u7840",
            "\u8bbe\u5907",
        )
        if any(bad in cleaned for bad in bad_words):
            return False
        return bool(re.search(r"(?:\u516c\u53f8|\u8bbe\u8ba1\u9662|\u7814\u7a76\u9662|\u52d8\u6d4b\u9662|\u89c4\u5212\u9662|\u5de5\u7a0b\u9662|\u54a8\u8be2\u9662|\u96c6\u56e2|\u6709\u9650\u516c\u53f8)$", cleaned))

    def _cover_design_unit_from_blocks(self, ast: DocumentAST) -> str | None:
        for block in ast.blocks[:12]:
            text = self._clean_text(block.text)
            if not text or len(text) > 80:
                continue
            if any(keyword in text for keyword in ("可行性研究报告", "项目名称", "目录", "批准", "审核", "校核", "编写", "年月", "二〇二")):
                continue
            if any(keyword in text for keyword in ("设计研究院", "设计院", "设计公司", "有限公司", "科技工程", "工程公司")):
                return text
        return None

    def _design_unit_qualification_from_blocks(self, ast: DocumentAST, design_unit: str | None = None) -> str | None:
        del design_unit
        patterns = [
            r"(?:设计单位资质等级|设计资质等级|资质等级)[:：\s]*([^\n，。、；;]{1,40})",
            r"(?:工程设计|设计资质)[^\n，。、；;]{0,30}?([甲乙丙丁]级)",
        ]
        for pattern in patterns:
            value = self._regex_from_blocks(ast, pattern)
            if value:
                grade = re.search(r"[甲乙丙丁]级", value)
                return grade.group(0) if grade else self._normalize_text_value(value)
        return None

    def _project_name_from_ast(self, ast: DocumentAST) -> str | None:
        for block in ast.blocks[:30]:
            text = self._clean_text(block.text)
            text = re.sub(r"^项目名称[:：\s]*", "", text).strip()
            title_match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()·\-]{6,80}(?:风电|风力发电)项目)", text)
            if title_match:
                value = title_match.group(1).strip()
                if "陕西" in value:
                    value = value[value.find("陕西"):]
                value = re.sub(r"^[0-9]+[.、]\s*", "", value)
                if len(value) <= 80:
                    return value
        stem = re.sub(r"\.(?:docx?|pdf)$", "", ast.file_name, flags=re.IGNORECASE)
        stem = re.sub(r"可行性研究报告.*$", "", stem).strip()
        stem = re.sub(r"^[0-9]+[.、]\s*", "", stem)
        if "项目" in stem:
            return stem
        return None
