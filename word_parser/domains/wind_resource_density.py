"""代表年用途和不同高度空气密度抽取。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentBlock


class WindDensityRulesMixin:
    """代表年用途和不同高度空气密度抽取，通过 WindResourceRulesMixin 组合到结果构建器。"""

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
            # 仅出现测风塔编号不能证明其参与发电量计算。
            return {}
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
        blocks = list(self._body_blocks(ast))
        page_texts = (ast.meta or {}).get("pdf_page_lines") or (ast.meta or {}).get("pdf_page_texts") or []
        for index, item in enumerate(page_texts):
            if not isinstance(item, dict) or "空气密度" not in str(item.get("text") or ""):
                continue
            blocks.append(DocumentBlock(
                id=f"pdf_density_page_{index}", type="paragraph", order=index,
                text=str(item["text"]), page=item.get("page"), section_path=[],
            ))
        for block in blocks:
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
                        r"(?P<height>[0-9]+(?:\.[0-9]+)?)\s*m\s*高度(?:处)?的?空气密度(?:为)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*kg\s*/?\s*m",
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
