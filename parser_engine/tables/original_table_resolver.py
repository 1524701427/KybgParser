"""原表识别和导出 resolver。

本模块只负责“整张原表”的识别、命名、续表合并和配置 key 映射。
字段值仍然由字段抽取链路处理，避免把字段抽值和原表导出混在一起。
"""

from __future__ import annotations

import re
from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable


class OriginalTableTitleResolver:
    """章节原表标题 resolver 基类。"""

    def accepts(self, spec: dict[str, Any]) -> bool:
        """判断当前 resolver 是否适用于该原表配置。"""
        return False

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """根据章节特征给候选标题加权。"""
        return 0.0

    def title_patterns(self, spec: dict[str, Any]) -> list[str]:
        """返回该 resolver 额外兼容的表题正则。"""
        return []

    def key_patterns(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """返回该 resolver 额外兼容的稳定 key 映射规则。"""
        return []


class FinanceOriginalTableTitleResolver(OriginalTableTitleResolver):
    """财务附表标题 resolver，处理附表编号和续表差异。"""

    def accepts(self, spec: dict[str, Any]) -> bool:
        """财务原表按 key_prefix/name 判定。"""
        text = _spec_text(spec)
        return "finance" in text or "财务" in text

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """附表和财务关键词越完整，标题可信度越高。"""
        if not title:
            return 0.0
        bonus = 0.0
        if re.search(r"附表\s*(?:\d+\.)?\d+", title):
            bonus += 1.2
        if any(keyword in title for keyword in ("财务", "现金流量", "成本费用", "资产负债", "借款还本付息", "利润")):
            bonus += 0.8
        if "续" in title:
            bonus += 0.2
        return bonus


class InvestmentOriginalTableTitleResolver(OriginalTableTitleResolver):
    """技经概算原表标题 resolver。"""

    def accepts(self, spec: dict[str, Any]) -> bool:
        """技经概算原表按 key_prefix/name 判定。"""
        text = _spec_text(spec)
        return any(marker in text for marker in ("investment", "技经", "概算"))

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """概算类表题优先使用标题文本，不依赖表格正文。"""
        if not title:
            return 0.0
        if any(keyword in title for keyword in ("概算表", "工程总概算", "费用概算", "技术经济指标")):
            return 1.0
        return 0.0


class CivilOriginalTableTitleResolver(OriginalTableTitleResolver):
    """土建类原表标题 resolver。

    这里集中处理箱变基础、土石方、道路、用地等土建章节的标题弱锚点。
    """

    def accepts(self, spec: dict[str, Any]) -> bool:
        """土建类原表按 key_prefix/name 判定。"""
        text = _spec_text(spec)
        markers = ("boxFoundation", "earthwork", "road", "land", "substationCivil", "箱变", "土石方", "道路", "用地", "土建")
        return any(marker in text for marker in markers)

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """土建类标题经常不是“表 x-x”，因此对工程量、清单类短标题加权。"""
        if not title:
            return 0.0
        if any(keyword in title for keyword in ("工程量", "清单", "土石方平衡", "箱变基础", "征地", "道路")):
            return 1.0
        return 0.0


class WindResourceOriginalTableTitleResolver(OriginalTableTitleResolver):
    """风资源章节原表标题 resolver。"""

    def accepts(self, spec: dict[str, Any]) -> bool:
        """风资源原表按 key_prefix/name 判定。"""
        text = _spec_text(spec)
        return any(marker in text for marker in ("resource", "windResource", "资源", "风能", "测风塔"))

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """风资源类标题命中风切变、湍流、风向风能等关键词时提高优先级。"""
        if not title:
            return 0.0
        bonus = 0.0
        if any(keyword in title for keyword in ("风切变", "切变指数", "风向风能频率", "湍流", "平均风速", "风功率密度", "风能参数")):
            bonus += 0.8
        if re.search(r"\d+#\s*测风塔", title):
            bonus += 0.4
        return bonus

    def title_patterns(self, spec: dict[str, Any]) -> list[str]:
        """返回风资源章节代码侧兼容的原表标题规则。"""
        return [
            "\u6d4b\u98ce\u5854.*\u98ce\u901f\u5207\u53d8\u6307\u6570\u7edf\u8ba1",
            "\u98ce\u901f\u5207\u53d8\u6307\u6570(?:\u8ba1\u7b97\u6210\u679c|\u7edf\u8ba1)?\u8868",
            "\u6d4b\u98ce\u5854.*(?:\u98ce\u901f\u5207\u53d8|\u98ce\u5207\u53d8).*\u7edf\u8ba1",
            r"测风塔.*风切变指数统计",
            r"测风塔.*各高度风速切变指数统计",
            r"风切变指数(?:计算成果|统计)?表",
            r"测风塔.*(?:切变统计表|风切变指数)",
            r"测风塔.*风向风能频率统计成果表",
            r"风向风能频率统计成果表",
            r"风向.*风能.*频率统计(?:成果)?表",
            r"测风塔.*(?:平均风速|风速).*风功率密度",
            r"测风塔.*湍流(?:强度)?(?:统计结果|计算成果|比较)?表",
        ]

    def key_patterns(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """把风资源表题映射到已有的稳定 key。"""
        return [
            {
                "key": "windResourceShearStatistics",
                "patterns": [
                    "\u98ce\u901f\u5207\u53d8\u6307\u6570(?:\u8ba1\u7b97\u6210\u679c|\u7edf\u8ba1)?\u8868",
                    "\u6d4b\u98ce\u5854.*\u98ce\u901f\u5207\u53d8.*(?:\u8ba1\u7b97\u6210\u679c|\u7edf\u8ba1|\u7ed3\u679c|\u8ba1\u7b97\u7ed3\u679c)",
                    "\u6d4b\u98ce\u5854.*\u98ce\u901f\u5207\u53d8\u6307\u6570\u7edf\u8ba1",
                    r"风切变指数(?:计算成果|统计)?表",
                    r"测风塔.*风切变.*(?:计算成果|统计|结果|计算结果)",
                    r"测风塔.*各高度风速切变指数统计",
                ],
            },
            {"key": "windResourceSpeedPowerStatistics", "patterns": [r"(?:平均风速|风速).*风功率密度"]},
            {"key": "windResourceDirectionEnergyFrequency", "patterns": [r"测风塔.*风向风能频率统计成果表", r"风向风能频率统计成果表", r"风向.*风能.*频率统计(?:成果)?表"]},
            {"key": "windResourceTurbulenceComparison", "patterns": [r"湍流(?:强度)?(?:统计结果|计算成果|比较)?表"]},
        ]


class GenerationOriginalTableTitleResolver(OriginalTableTitleResolver):
    """发电量章节原表标题 resolver。

    发电量章节在不同报告里经常被挂到“风资源/总体布置”等上级章节，表题本身反而更稳定。
    这里只补代码侧的标题兼容和 key 映射，不改 output_schema.yaml 里的抽取配置。
    """

    SUMMARY_PATTERNS = [
        r"风电场\s*\d+\s*m\s*轮毂高度年上网电量估算表",
        r"风电场.*(?:发电量|年上网电量)(?:估算|计算)(?:成果)?表",
        r"风电场工程.*(?:推荐方案)?(?:发电量|年上网电量)计算(?:成果)?表",
        r"风电场发电量计算成果表",
    ]
    SINGLE_TURBINE_PATTERNS = [
        r"(?:WTG[\w-]+\s*)?方案各风电机组发电量成果表",
        r"各风电机组发电量成果表",
        r"推荐机型单机发电量统计表",
        r"单台风机年上网电量计算成果表",
    ]

    def accepts(self, spec: dict[str, Any]) -> bool:
        """发电量原表按 key_prefix/name 判定。"""
        text = _spec_text(spec)
        return "generation" in text or "发电量" in text

    def title_bonus(self, title: str, spec: dict[str, Any]) -> float:
        """发电量表题命中年上网电量、单机电量等语义时提高优先级。"""
        if not title:
            return 0.0
        bonus = 0.0
        if re.search(r"(?:发电量|年上网电量).*(?:估算|计算|成果).*表", title):
            bonus += 1.0
        if re.search(r"(?:方案|单台|单机|风电机组).*发电量.*表", title):
            bonus += 0.8
        if re.search(r"表\s*\d+(?:\.\d+)*(?:-\d+)?", title):
            bonus += 0.3
        return bonus

    def title_patterns(self, spec: dict[str, Any]) -> list[str]:
        """返回发电量章节代码侧兼容的原表标题规则。"""
        return [*self.SUMMARY_PATTERNS, *self.SINGLE_TURBINE_PATTERNS]

    def key_patterns(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """把新旧发电量表题映射到一次结果里已有的稳定 key。"""
        return [
            {"key": "generationSummary", "patterns": list(self.SUMMARY_PATTERNS)},
            {"key": "singleTurbineAnnualEnergy", "patterns": list(self.SINGLE_TURBINE_PATTERNS)},
        ]


class OriginalTableResolver:
    """从 AST 中识别配置声明的原表并生成表格输出。

    Args:
        builder: 结果构建器适配器。resolver 复用它的表格透传、单元格溯源和旧版辅助函数。
    """

    def __init__(self, builder: Any):
        self.builder = builder
        self.title_resolvers: list[OriginalTableTitleResolver] = [
            FinanceOriginalTableTitleResolver(),
            WindResourceOriginalTableTitleResolver(),
            GenerationOriginalTableTitleResolver(),
            InvestmentOriginalTableTitleResolver(),
            CivilOriginalTableTitleResolver(),
        ]

    def resolve(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        """按输出 schema 识别并导出原表。

        Args:
            ast: 已完成结构识别和章节识别的文档 AST。

        Returns:
            dict[str, dict[str, Any]]: 表 key 到表格输出对象的映射。
        """
        tables: dict[str, dict[str, Any]] = {}
        if self.builder.original_table_group_specs:
            tables.update(self._original_table_groups_from_config(ast))
            self._deduplicate_original_tables_by_source(tables)
            return tables
        if self.builder.original_table_specs:
            for spec in self.builder.original_table_specs:
                table = self._original_table_from_config(ast, spec)
                if table is not None:
                    tables[spec["key"]] = table
            for key, table in self._repeatable_original_tables_from_config(ast, tables).items():
                tables[key] = table
            self._deduplicate_original_tables_by_source(tables)
        return tables

    def resolve_groups_from_config(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        """按 original_table_groups 配置导出原表，供兼容入口复用。"""
        return self._original_table_groups_from_config(ast)

    def match_title(
        self,
        ast: DocumentAST,
        table: DocumentTable,
        spec: dict[str, Any],
        patterns: list[str],
        exclude_patterns: list[str] | None = None,
        include_table_text: bool = False,
    ) -> dict[str, Any] | None:
        """使用统一的原表题名候选链路匹配标题规则。"""
        return self._match_original_table_title(ast, table, spec, patterns, exclude_patterns, include_table_text)

    def title_candidates(self, ast: DocumentAST, table: DocumentTable, spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """返回统一清洗、加权后的原表标题候选。"""
        return self._original_table_title_candidates(ast, table, spec)

    def nearby_title_candidates(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        """返回表前附近段落补充出来的标题候选。"""
        return self._nearby_paragraph_title_candidates(ast, table)

    def deduplicate_by_source(self, tables: dict[str, dict[str, Any]]) -> None:
        """按源表身份去重原表输出。"""
        self._deduplicate_original_tables_by_source(tables)

    def original_table_from_config(self, ast: DocumentAST, spec: dict[str, Any]) -> dict[str, Any] | None:
        """按单张原表配置导出表格，兼容旧调用入口。"""
        return self._original_table_from_config(ast, spec)

    def repeatable_tables_from_config(self, ast: DocumentAST, existing_tables: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """按可重复原表配置导出表格，兼容旧调用入口。"""
        return self._repeatable_original_tables_from_config(ast, existing_tables)

    def tables_for_spec(self, ast: DocumentAST, spec: dict[str, Any]) -> list[DocumentTable]:
        """按统一章节和表题规则筛选原表候选。"""
        return self._original_tables_for_spec(ast, spec)

    def section_keywords(self, spec: dict[str, Any]) -> list[str]:
        """返回原表配置对应的章节关键词。"""
        return self._original_table_section_keywords(spec)

    def _original_table_groups_from_config(self, ast: DocumentAST) -> dict[str, dict[str, Any]]:
        """按 original_table_groups 配置批量识别原表。"""
        tables: dict[str, dict[str, Any]] = {}
        seen_sources: set[tuple[Any, ...]] = set()
        seen_captions: dict[tuple[str, str], str] = {}
        for spec in self.builder.original_table_group_specs:
            key_prefix = str(spec.get("key_prefix") or "originalTable")
            patterns = self._patterns_for_spec(spec)
            if not patterns:
                continue
            exclude_patterns = list(spec.get("exclude_patterns") or [])
            include_table_text = not bool(spec.get("title_only", True))
            counter = 1
            for table in sorted(self._original_tables_for_spec(ast, spec), key=lambda item: item.order):
                matrix = self.builder._table_matrix(table)
                if not matrix:
                    continue
                title_match = self._match_original_table_title(
                    ast,
                    table,
                    spec,
                    patterns,
                    exclude_patterns,
                    include_table_text=include_table_text,
                )
                if title_match is None:
                    continue
                caption = title_match["title"]
                matched_pattern = title_match["matchedPattern"]
                source_identity = (table.id, table.order, caption)
                if source_identity in seen_sources:
                    continue
                seen_sources.add(source_identity)
                caption_key = self._normalized_original_caption_key(caption or self._section_path_caption(table))
                existing_key = seen_captions.get((key_prefix, caption_key)) if caption_key else None
                if existing_key and existing_key in tables:
                    if self._append_original_table_continuation(
                        tables[existing_key],
                        table,
                        "grouped original table continuation configured in output_schema.yaml",
                        match_trace=title_match,
                    ):
                        continue
                preferred_key, preferred_extraction_type = self._configured_original_table_key(spec, caption, tables)
                key = preferred_key or self._grouped_original_table_key(key_prefix, counter, tables)
                header_columns, header_source = self._previous_header_fragment_for_caption(ast, table, caption)
                data_start_index = None
                if header_columns is None and title_match.get("titleSource") == "table_first_row":
                    first_row_header = self._header_after_first_title_row(table)
                    if first_row_header:
                        header_columns = first_row_header
                        data_start_index = 2
                if self._should_use_engineering_quantity_list_header(caption, matrix):
                    # 这类“工程量清单”在 Word/PDF 跨页时表头经常丢失，不能把第一条工程量误当表头。
                    header_columns = self._engineering_quantity_list_header(matrix)
                    data_start_index = 0
                extracted = self.builder._document_table_passthrough(
                    key,
                    caption or self._section_path_caption(table) or str(spec.get("name", key)),
                    table,
                    "grouped original table configured in output_schema.yaml",
                    header_columns=header_columns,
                    header_source_table=header_source,
                    data_start_index=data_start_index,
                    prefer_provided_name=bool(caption),
                )
                extracted = self._attach_table_trace(
                    extracted,
                    {**spec, "key": key},
                    preferred_extraction_type or "original_table_group",
                    matched_pattern=matched_pattern,
                    title_match=title_match,
                )
                if extracted is None:
                    continue
                if caption:
                    # loader 可能把上一张表的 caption 挂到续页表上，原表导出以本次命中的标题为准。
                    clean_caption = self._clean_table_caption_title(caption)
                    extracted["name"] = clean_caption
                    extracted.setdefault("_sourceTable", {})["caption"] = clean_caption
                self._append_adjacent_original_table_fragments(
                    ast,
                    table,
                    extracted,
                    spec,
                    patterns,
                    exclude_patterns,
                    include_table_text,
                    title_match,
                )
                tables[key] = extracted
                if preferred_key is None:
                    counter += 1
                if caption_key:
                    seen_captions[(key_prefix, caption_key)] = key
        return tables

    def _configured_original_table_key(self, spec: dict[str, Any], title: str | None, existing_tables: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
        """根据 key_patterns 把命中的表题映射成稳定表 key。"""
        text = self._clean_table_caption_title(title or "")
        if not text:
            return None, None
        for item in self._key_patterns_for_spec(spec):
            key = str(item.get("key") or "").strip()
            key_template = str(item.get("key_template") or "").strip()
            patterns = item.get("patterns") or []
            if not key and not key_template:
                continue
            for pattern in patterns:
                match = re.search(str(pattern), text, flags=re.IGNORECASE)
                if not match:
                    continue
                resolved_key = key or self._format_original_table_key_template(key_template, match)
                if resolved_key and resolved_key not in existing_tables:
                    return resolved_key, item.get("extraction_type")
        return None, None

    def _patterns_for_spec(self, spec: dict[str, Any]) -> list[str]:
        """合并配置和专用 resolver 提供的标题规则。

        output_schema.yaml 仍然是主规则来源；专用 resolver 只补不同章节里已经发现的标题变体，
        避免为了单个报告频繁改动公共抽取配置。
        """
        patterns: list[str] = [str(pattern) for pattern in spec.get("patterns") or [] if pattern]
        for resolver in self._active_title_resolvers(spec):
            patterns.extend(str(pattern) for pattern in resolver.title_patterns(spec) if pattern)
        return list(dict.fromkeys(patterns))

    def _match_patterns_for_spec(self, spec: dict[str, Any]) -> list[str]:
        """返回用于表题命中判断的完整规则集合。"""
        patterns = list(self._patterns_for_spec(spec))
        for item in self._key_patterns_for_spec(spec):
            patterns.extend(str(pattern) for pattern in item.get("patterns") or [] if pattern)
        return list(dict.fromkeys(patterns))

    def _key_patterns_for_spec(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """合并配置和专用 resolver 的稳定 key 映射规则。"""
        items: list[dict[str, Any]] = [dict(item) for item in spec.get("key_patterns") or [] if isinstance(item, dict)]
        for resolver in self._active_title_resolvers(spec):
            items.extend(dict(item) for item in resolver.key_patterns(spec) if isinstance(item, dict))
        return items

    def _active_title_resolvers(self, spec: dict[str, Any]) -> list[OriginalTableTitleResolver]:
        """返回当前原表配置适用的章节专用 resolver。"""
        return [resolver for resolver in self.title_resolvers if resolver.accepts(spec)]

    def _format_original_table_key_template(self, template: str, match: re.Match[str]) -> str:
        """用正则命名组生成动态原表 key。"""
        if not template:
            return ""
        values = {key: self._sanitize_original_table_key_part(value) for key, value in match.groupdict().items()}
        try:
            return template.format(**values)
        except KeyError:
            return ""

    def _sanitize_original_table_key_part(self, value: Any) -> str:
        """清理动态 key 片段，避免空白和中文符号进入 JSON key。"""
        text = str(value or "")
        return re.sub(r"[^0-9A-Za-z]+", "", text)

    def _match_original_table_title(
        self,
        ast: DocumentAST,
        table: DocumentTable,
        spec: dict[str, Any],
        patterns: list[str],
        exclude_patterns: list[str] | None = None,
        include_table_text: bool = False,
    ) -> dict[str, Any] | None:
        """使用多来源表题候选匹配原表标题规则。

        标题候选已经按结构层置信度排序，因此这里优先按候选走，避免“章节名”这类弱候选
        抢在真正表题前命中。章节路径默认只用于候选筛表，只有电气设备清册这类明确表名路径才兜底命中。
        """
        candidates = self._original_table_title_candidates(ast, table, spec)
        title_context = "\n".join(candidate["text"] for candidate in candidates if candidate.get("text"))
        matrix = self.builder._table_matrix(table)
        table_text = self._matrix_text(matrix)
        target_text = f"{title_context}\n{table_text[:200]}" if include_table_text else title_context
        if exclude_patterns and any(re.search(pattern, target_text, flags=re.IGNORECASE) for pattern in exclude_patterns):
            return None
        for candidate in candidates:
            if candidate.get("source") == "section_path" and not self._allow_section_path_title_match(spec):
                continue
            if self._candidate_crossed_blocking_table(ast, table, candidate):
                continue
            text = candidate.get("text") or ""
            for pattern in patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    return {
                        "title": text,
                        "matchedPattern": pattern,
                        "titleSource": candidate.get("source"),
                        "titleCandidate": candidate,
                        "titleCandidates": candidates,
                        "targetTextPreview": self._clean_text(target_text[:500]),
                    }
        for pattern in patterns:
            if include_table_text and re.search(pattern, table_text[:200], flags=re.IGNORECASE):
                fallback_title = self._first_non_section_title(candidates) or self._section_path_caption(table) or table.id
                return {
                    "title": fallback_title,
                    "matchedPattern": pattern,
                    "titleSource": "table_text",
                    "titleCandidate": {"source": "table_text", "text": self._clean_text(table_text[:200])},
                    "titleCandidates": candidates,
                    "targetTextPreview": self._clean_text(target_text[:500]),
                }
        return None

    def _allow_section_path_title_match(self, spec: dict[str, Any]) -> bool:
        """判断是否允许章节路径作为原表标题兜底。

        电气设备清册在部分 AST 中没有独立 caption，只把“主要电气一次设备/主要通信设备表”放在
        section_path 末级；这类配置允许使用章节路径命中。土建、箱变、用地等章节路径较宽，仍不允许
        直接当表题，避免把章节下无关表误抽为目标原表。
        """
        text = _spec_text(spec)
        return any(marker in text for marker in ("electricalPrimary", "electricalSecondary", "电气一次", "电气二次"))

    def _candidate_crossed_blocking_table(self, ast: DocumentAST, table: DocumentTable, candidate: dict[str, Any]) -> bool:
        """判断候选标题到目标表之间是否跨过了真正的其他表。"""
        if not candidate.get("crossedTable"):
            return False
        return not self._crossed_tables_are_same_original_fragments(ast, table, candidate)

    def _crossed_tables_are_same_original_fragments(self, ast: DocumentAST, table: DocumentTable, candidate: dict[str, Any]) -> bool:
        """允许跨过同一原表的短碎片，兼容 Word 跨页把表拆成多张表的情况。"""
        try:
            start_order = int(candidate.get("order"))
        except (TypeError, ValueError):
            return False
        crossed_tables = [item for item in ast.tables if start_order < item.order < table.order]
        if not crossed_tables:
            return False
        candidate_title = self._clean_text(candidate.get("text") or "")
        for crossed in crossed_tables:
            matrix = self.builder._table_matrix(crossed)
            if len(matrix) > 1:
                return False
            crossed_title = self._clean_text(
                crossed.caption
                or (str(crossed.meta.get("best_title") or "") if isinstance(crossed.meta, dict) else "")
                or self._caption_before_table_from_table(crossed)
            )
            if crossed_title and candidate_title and crossed_title != candidate_title:
                return False
        return True

    def _first_non_section_title(self, candidates: list[dict[str, Any]]) -> str:
        """返回第一个非章节路径的标题候选。"""
        for candidate in candidates:
            if candidate.get("source") == "section_path":
                continue
            text = self._clean_table_caption_title(candidate.get("text") or "")
            if text:
                return text
        return ""

    def _should_use_engineering_quantity_list_header(self, caption: str, matrix: list[list[str]]) -> bool:
        """判断工程量清单是否缺失表头，需要使用通用四列表头。"""
        if "工程量清单" not in self._clean_text(caption or ""):
            return False
        if not matrix:
            return False
        width = max(len(row) for row in matrix)
        if width < 4:
            return False
        first_row = matrix[0]
        if any(self._normalize_original_column_label(cell) in {"编号", "名称", "单位", "数量"} for cell in first_row):
            return False
        return True

    def _engineering_quantity_list_header(self, matrix: list[list[str]]) -> list[str]:
        """为缺表头的工程量清单补一个稳定表头。"""
        width = max(len(row) for row in matrix) if matrix else 4
        header = ["编号", "名称", "单位", "数量"]
        return header + [f"col_{index}" for index in range(4, width)]

    def _original_table_title_candidates(self, ast: DocumentAST, table: DocumentTable, spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """合并结构层表元信息和旧版上下文候选。"""
        candidates: list[dict[str, Any]] = []
        for item in (table.meta.get("title_candidates") or []) if isinstance(table.meta, dict) else []:
            if isinstance(item, dict):
                candidates.append(dict(item))
        if table.caption:
            candidates.append({"source": "caption", "text": self._clean_text(table.caption), "score": 5.0})
        caption_before = self._caption_before_table_from_table(table)
        if caption_before:
            candidates.append({"source": "caption_before", "text": self._clean_text(caption_before), "score": 4.0})
        previous_caption = self._caption_before_table(ast, table)
        if previous_caption:
            # 旧版上下文函数会从“正文+表题”混排段落中截出真正表题，优先级应高于整段文本。
            candidates.append({"source": "previous_paragraph", "text": self._clean_text(previous_caption), "score": 5.5})
        candidates.extend(self._nearby_paragraph_title_candidates(ast, table))
        section_caption = self._section_path_caption(table)
        if section_caption:
            candidates.append({"source": "section_path", "text": section_caption, "score": 1.0})
        first_row_title = self._table_first_row_title_candidate(table)
        if first_row_title:
            candidates.append({"source": "table_first_row", "text": first_row_title, "score": 3.2})
        return self._deduplicate_title_candidates(candidates, spec or {})

    def _nearby_paragraph_title_candidates(self, ast: DocumentAST, table: DocumentTable) -> list[dict[str, Any]]:
        """从表前段落补充标题候选，兼容未经过 StructureParser 的测试 AST。"""
        previous_blocks = [block for block in ast.blocks if block.order < table.order and block.type == "paragraph"]
        candidates: list[dict[str, Any]] = []
        for block in reversed(previous_blocks[-12:]):
            text = self._clean_text(block.text or "")
            if not text:
                continue
            crossed_table = any(candidate.order > block.order and candidate.order < table.order for candidate in ast.tables)
            score = 1.0
            if self._looks_like_caption_text(text):
                score += 3.0
            if block.meta.get("structure_type") in {"heading", "table_caption"}:
                score += 1.0
            candidates.append({"source": "previous_paragraph", "text": text, "score": score, "blockId": block.id, "order": block.order, "page": block.page, "crossedTable": crossed_table})
        return candidates

    def _table_first_row_title_candidate(self, table: DocumentTable) -> str:
        """从表内首行读取表题候选。"""
        matrix = self.builder._table_matrix(table)
        if not matrix:
            return ""
        first_row = [self._clean_text(cell) for cell in matrix[0] if self._clean_text(cell)]
        if len(first_row) == 1:
            return first_row[0]
        joined = self._clean_text(" ".join(first_row))
        if len(first_row) <= 3 and re.search(r"(?:^表|附表|表$|清册|工程量|统计|成果|汇总|计算|分布|湍流|风切变|概算|财务)", joined):
            return joined
        return ""

    def _header_after_first_title_row(self, table: DocumentTable) -> list[str] | None:
        """表内首行为标题时，尝试使用第二行作为表头。"""
        matrix = self.builder._table_matrix(table)
        if len(matrix) < 3:
            return None
        first_row = [self._clean_text(cell) for cell in matrix[0] if self._clean_text(cell)]
        second_row = [self._clean_text(cell) for cell in matrix[1] if self._clean_text(cell)]
        if len(first_row) != 1 or len(second_row) < 2:
            return None
        return matrix[1]

    def _first_non_empty_title(self, candidates: list[dict[str, Any]]) -> str:
        """返回第一个非空标题候选。"""
        for candidate in candidates:
            text = self._clean_table_caption_title(candidate.get("text") or "")
            if text:
                return text
        return ""

    def _normalized_original_caption_key(self, caption: str | None) -> str:
        """生成用于续表合并去重的标题 key。"""
        text = self._clean_text(caption or "")
        text = re.sub(r"\s+", "", text)
        return text

    def _previous_header_fragment_for_caption(self, ast: DocumentAST, table: DocumentTable, caption: str) -> tuple[list[str] | None, DocumentTable | None]:
        """当同名续表缺少表头时，从前一张同名表继承表头。"""
        matrix = self.builder._table_matrix(table)
        if len(matrix) < 2:
            return None, None
        caption_key = self._normalized_original_caption_key(caption)
        if not caption_key:
            return None, None
        for previous in sorted((item for item in ast.tables if item.order < table.order), key=lambda item: item.order, reverse=True):
            previous_caption = self._best_original_table_title(ast, previous)
            if self._normalized_original_caption_key(previous_caption) != caption_key:
                continue
            previous_matrix = self.builder._table_matrix(previous)
            if not previous_matrix:
                continue
            header = previous_matrix[0]
            if len(header) == len(matrix[0]) and self._row_looks_like_data_continuation(matrix[0], header):
                return header, previous
            break
        return None, None

    def _best_original_table_title(self, ast: DocumentAST, table: DocumentTable) -> str:
        """返回某张表当前可用的最佳原表标题。"""
        return self._first_non_empty_title(self._original_table_title_candidates(ast, table))

    def _row_looks_like_data_continuation(self, row: list[str], header: list[str]) -> bool:
        """判断缺表头续表的首行是否像数据行。"""
        if len(row) != len(header) or self._row_looks_like_existing_header(row, header):
            return False
        non_empty = [cell for cell in row if self._clean_text(cell)]
        if not non_empty:
            return False
        numeric_like = sum(1 for cell in non_empty if re.search(r"\d", cell))
        return numeric_like >= max(1, len(non_empty) // 2)

    def _append_original_table_continuation(self, target: dict[str, Any], table: DocumentTable, description: str, match_trace: dict[str, Any] | None = None) -> bool:
        """把同标题续表追加到已导出的原表中。"""
        if target is None:
            return False
        matrix = self.builder._table_matrix(table)
        columns = list(target.get("columns") or [])
        if not matrix or not columns:
            return False
        column_count = len(columns)
        if max(len(row) for row in matrix) != column_count:
            return False
        source_rows = self._continuation_data_rows(matrix, columns)
        if not source_rows:
            return False
        for source_row_index, row in source_rows:
            target.setdefault("data", []).append([self.builder._normalize_scalar(row[index]) if index < len(row) else None for index in range(column_count)])
            target.setdefault("_cellSources", []).append(
                [
                    self.builder._table_cell_source(table, source_row_index, column_index, description, resolver="document_table_passthrough")
                    if column_index < len(row) and row[column_index].strip()
                    else None
                    for column_index in range(column_count)
                ]
            )
        target["index"] = list(range(len(target.get("data") or [])))
        target.setdefault("_sourceTable", {}).setdefault("continuations", []).append(
            {
                "tableId": table.id,
                "order": table.order,
                "page": table.page,
                "caption": table.caption or self._caption_before_table_from_table(table),
                "sectionPath": table.section_path,
                "matchedRule": (match_trace or {}).get("matchedPattern"),
                "titleSource": (match_trace or {}).get("titleSource"),
                "matchedTitle": (match_trace or {}).get("title"),
            }
        )
        target.setdefault("_sourceTable", {})["isMerged"] = True
        target.setdefault("_trace", {})["merged"] = True
        target.setdefault("_trace", {}).setdefault("continuations", []).append(
            {
                "tableId": table.id,
                "order": table.order,
                "page": table.page,
                "matchedRule": (match_trace or {}).get("matchedPattern"),
                "titleSource": (match_trace or {}).get("titleSource"),
                "matchedTitle": (match_trace or {}).get("title"),
            }
        )
        return True

    def _append_adjacent_original_table_fragments(
        self,
        ast: DocumentAST,
        table: DocumentTable,
        target: dict[str, Any],
        spec: dict[str, Any],
        patterns: list[str],
        exclude_patterns: list[str] | None,
        include_table_text: bool,
        match_trace: dict[str, Any] | None = None,
    ) -> None:
        """合并紧邻的原表续页碎片。

        Word/PDF 抽表时，跨页表可能被切成两张 AST 表：前一张带表头和部分数据，后一张只有续行。
        这里只处理 order 紧邻、列数相同、首行不像表头的碎片，避免把后续新表误合并。
        """
        columns = list(target.get("columns") or [])
        if not columns:
            return
        next_table = next((item for item in sorted(ast.tables, key=lambda item: item.order) if item.order == table.order + 1), None)
        if next_table is None:
            return
        if self._match_original_table_title(ast, next_table, spec, patterns, exclude_patterns, include_table_text=include_table_text) is not None:
            return
        matrix = self.builder._table_matrix(next_table)
        if not matrix or max(len(row) for row in matrix) != len(columns):
            return
        if self._row_looks_like_existing_header(matrix[0], columns):
            return
        if len([cell for cell in matrix[0] if self._clean_text(cell)]) == 1:
            return
        self._append_original_table_continuation(
            target,
            next_table,
            "adjacent original table fragment continuation",
            match_trace=match_trace,
        )

    def _continuation_data_rows(self, matrix: list[list[str]], existing_columns: list[str]) -> list[tuple[int, list[str]]]:
        """过滤续表数据行。"""
        first_row_is_header = self._row_looks_like_existing_header(matrix[0], existing_columns)
        start_index = 1 if first_row_is_header else 0
        return [(source_row_index, row) for source_row_index, row in enumerate(matrix[start_index:], start=start_index) if any(cell.strip() for cell in row)]

    def _row_looks_like_existing_header(self, row: list[str], existing_columns: list[str]) -> bool:
        """判断一行是否与已有表头相同。"""
        if len(row) != len(existing_columns):
            return False
        matches = 0
        for left, right in zip(row, existing_columns):
            if self._normalize_original_column_label(left) == self._normalize_original_column_label(right):
                matches += 1
        return matches >= max(1, len(existing_columns) // 2)

    def _normalize_original_column_label(self, value: Any) -> str:
        """归一化表头文本，用于续表表头比较。"""
        text = self._clean_text(str(value or ""))
        text = re.sub(r"[\[\]（）()【】].*?[\[\]（）()【】]", "", text)
        text = re.sub(r"(?:m/s|W/m²|W/m2|kWh|MWh|MW|kW|kV|m2|㎡|%|h)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "", text)
        return text.strip().lower()

    def _grouped_original_table_key(self, key_prefix: str, counter: int, existing_tables: dict[str, dict[str, Any]]) -> str:
        """为未显式配置 key 的原表生成递增 key。"""
        key = f"{key_prefix}{counter:03d}"
        while key in existing_tables:
            counter += 1
            key = f"{key_prefix}{counter:03d}"
        return key

    def _deduplicate_original_tables_by_source(self, tables: dict[str, dict[str, Any]]) -> None:
        """按表格来源去重，优先保留更稳定的配置 key。"""
        seen: dict[tuple[Any, ...], str] = {}
        for key, table in list(tables.items()):
            source = table.get("_sourceTable") or {}
            identity = (source.get("tableId"), source.get("order"), self._clean_text(str(source.get("caption") or table.get("name") or "")))
            if not any(identity):
                continue
            existing_key = seen.get(identity)
            if existing_key is None:
                seen[identity] = key
                continue
            preferred_key = self._preferred_original_table_key(existing_key, key)
            dropped_key = key if preferred_key == existing_key else existing_key
            tables.pop(dropped_key, None)
            seen[identity] = preferred_key

    def _preferred_original_table_key(self, current_key: str, candidate_key: str) -> str:
        """在重复命中时选择更有业务含义的表 key。"""
        def score(key: str) -> int:
            if re.search(r"[A-Za-z0-9]{2,8}$", key, flags=re.IGNORECASE):
                return 3
            if re.search(r"Turbulence(?:10|15)ms[A-Za-z0-9]{2,8}$", key, flags=re.IGNORECASE):
                return 3
            return 1

        if score(candidate_key) > score(current_key):
            return candidate_key
        return current_key

    def _original_table_from_config(self, ast: DocumentAST, spec: dict[str, Any]) -> dict[str, Any] | None:
        """兼容旧版 original_tables 配置。"""
        key = spec.get("key")
        if not key:
            return None
        builder = spec.get("builder")
        if builder == "substation_civil_original":
            return self._attach_table_trace(self.builder._substation_civil_table_from_document(ast), spec, "original_table", builder=builder)
        if builder in {"road_original", "road_combined_original"}:
            return self._attach_table_trace(self.builder._road_table_from_document(ast), spec, "original_table", builder=builder)
        patterns = self._patterns_for_spec(spec)
        if patterns:
            table = self.builder._original_captioned_table_by_regex_from_document(
                ast,
                key,
                patterns,
                list(spec.get("exclude_patterns") or []),
                include_table_text=not bool(spec.get("title_only")),
                table_candidates=self._original_tables_for_spec(ast, spec),
            )
            return self._attach_table_trace(table, spec, "original_table", matched_pattern=self._matched_pattern_for_table(table, patterns))
        keywords = list(spec.get("caption_keywords") or [])
        if keywords:
            table = self.builder._original_captioned_table_from_document(ast, key, keywords, table_candidates=self._original_tables_for_spec(ast, spec))
            return self._attach_table_trace(table, spec, "original_table", matched_pattern=self._matched_keyword_for_table(table, keywords))
        return None

    def _attach_table_trace(
        self,
        table: dict[str, Any] | None,
        spec: dict[str, Any],
        extraction_type: str,
        builder: str | None = None,
        matched_pattern: str | None = None,
        title_match: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """给原表输出附加匹配追踪信息。"""
        if table is None:
            return None
        trace = {
            "extractionType": extraction_type,
            "ruleSource": "configs/output_schema.yaml",
            "configuredKey": spec.get("key") or spec.get("key_prefix"),
            "builder": builder or spec.get("builder"),
            "patterns": list(spec.get("patterns") or []),
            "excludePatterns": list(spec.get("exclude_patterns") or []),
            "captionKeywords": list(spec.get("caption_keywords") or []),
            "titleOnly": bool(spec.get("title_only")) or None,
            "matchedRule": matched_pattern,
            "matchedTitle": (title_match or {}).get("title"),
            "titleSource": (title_match or {}).get("titleSource"),
            "titleCandidates": (title_match or {}).get("titleCandidates"),
            "description": spec.get("name") or table.get("name"),
            "tablePosition": table.get("_sourceTable"),
            "merged": bool((table.get("_sourceTable") or {}).get("isMerged")),
        }
        table["_trace"] = {key: value for key, value in trace.items() if value not in (None, [], {})}
        return table

    def _matched_pattern_for_table(self, table: dict[str, Any] | None, patterns: list[str]) -> str | None:
        """根据导出表内容反查命中的正则。"""
        if table is None:
            return None
        text = self._trace_match_text(table)
        return next((pattern for pattern in patterns if re.search(pattern, text)), None)

    def _matched_keyword_for_table(self, table: dict[str, Any] | None, keywords: list[str]) -> str | None:
        """根据导出表内容反查命中的关键词。"""
        if table is None:
            return None
        text = self._trace_match_text(table)
        return next((keyword for keyword in keywords if keyword in text), None)

    def _trace_match_text(self, table: dict[str, Any]) -> str:
        """拼接用于追踪匹配的导出表文本。"""
        first_rows = table.get("data", [])[:2]
        return "\n".join([str(table.get("name", "")), " | ".join(map(str, table.get("columns", []))), str(first_rows)])

    def _repeatable_original_tables_from_config(self, ast: DocumentAST, existing_tables: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """兼容旧版 repeatable_original_tables 配置。"""
        tables: dict[str, dict[str, Any]] = {}
        existing_keys = set(existing_tables)
        existing_names = {str(table.get("name")) for table in existing_tables.values() if table.get("name")}
        for spec in self.builder.repeatable_original_table_specs:
            key_prefix = spec.get("key_prefix")
            patterns = self._patterns_for_spec(spec)
            if not key_prefix or not patterns:
                continue
            exclude_patterns = list(spec.get("exclude_patterns") or [])
            for table in self._original_tables_for_spec(ast, spec):
                matrix = self.builder._table_matrix(table)
                if len(matrix) < 2:
                    continue
                caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
                table_text = self._matrix_text(matrix)
                target_text = f"{caption}\n{table_text[:200]}"
                if exclude_patterns and any(re.search(pattern, target_text) for pattern in exclude_patterns):
                    continue
                matched_pattern = next((pattern for pattern in patterns if re.search(pattern, target_text)), None)
                if matched_pattern is None:
                    continue
                if caption and caption in existing_names:
                    continue
                key = self._repeatable_table_key(str(key_prefix), caption or table.id, tables)
                if key in existing_keys:
                    continue
                extracted = self.builder._document_table_passthrough(str(key), caption or str(spec.get("name", key)), table, "repeatable original table configured in output_schema.yaml")
                if extracted and extracted.get("data"):
                    self._attach_table_trace(extracted, spec, "repeatable_original_table", matched_pattern=matched_pattern)
                    tables[key] = extracted
                    if caption:
                        existing_names.add(caption)
        return tables

    def _repeatable_table_key(self, prefix: str, caption: str, current: dict[str, Any]) -> str:
        """为可重复原表生成基于测风塔号的 key。"""
        tower_match = re.search(r"([A-Za-z0-9]{2,8})#", caption)
        suffix = tower_match.group(1) if tower_match else "table"
        suffix = re.sub(r"[^A-Za-z0-9]+", "", suffix) or "table"
        key = f"{prefix}{suffix}"
        index = 2
        while key in current:
            key = f"{prefix}{suffix}_{index}"
            index += 1
        return key

    def _original_tables_for_spec(self, ast: DocumentAST, spec: dict[str, Any]) -> list[DocumentTable]:
        """按章节优先筛表；章节缺失时回退到全表。"""
        if self._is_finance_spec(spec):
            # 财务附表通常数量多、跨页多、章节路径也最不稳定，标题规则比章节路径更可信。
            return list(ast.tables)
        keywords = self._original_table_section_keywords(spec)
        if not keywords:
            return list(ast.tables)
        matched = [table for table in ast.tables if self.builder._section_path_matches(table.section_path, keywords)]
        hinted = [table for table in ast.tables if self._table_has_title_hint(ast, table, spec)]
        if matched or hinted:
            allowed: list[DocumentTable] = []
            seen: set[str] = set()
            for table in [*matched, *hinted]:
                if table.id in seen:
                    continue
                if table.section_path and not self.builder._section_path_matches(table.section_path, keywords):
                    if not (self._can_title_override_section_path(spec) and self._table_has_strong_title_hint(ast, table, spec)):
                        continue
                seen.add(table.id)
                allowed.append(table)
            if allowed:
                return sorted(allowed, key=lambda item: item.order)
        key_text = _spec_text(spec)
        if "boxFoundation" in key_text or "箱变基础" in key_text:
            return list(ast.tables)
        if any(table.section_path for table in ast.tables):
            return []
        return list(ast.tables)

    def _is_finance_spec(self, spec: dict[str, Any]) -> bool:
        """判断当前原表配置是否属于财务附表。"""
        text = _spec_text(spec)
        return "finance" in text or "财务" in text

    def _can_title_override_section_path(self, spec: dict[str, Any]) -> bool:
        """判断该章节是否允许强表题覆盖错误章节路径。"""
        text = _spec_text(spec)
        return any(
            marker in text
            for marker in (
                "generation",
                "发电量",
                "resource",
                "windResource",
                "资源",
                "风能",
                "测风塔",
                "investment",
                "技经",
                "概算",
                "boxFoundation",
                "earthwork",
                "road",
                "land",
                "substationCivil",
                "箱变",
                "土石方",
                "道路",
                "用地",
                "土建",
            )
        )

    def _original_table_section_keywords(self, spec: dict[str, Any]) -> list[str]:
        """从配置 key/name 推断原表所属章节关键词。"""
        explicit = spec.get("section_include") or spec.get("sections_include")
        if isinstance(explicit, str):
            return [explicit]
        if explicit:
            return [str(item) for item in explicit if item]
        sections = spec.get("sections") or {}
        if isinstance(sections, dict) and sections.get("include"):
            return [str(item) for item in sections.get("include") or [] if item]
        key_text = _spec_text(spec)
        mappings = [
            (("resource", "windResource", "资源"), ["资源章节", "风能资源", "风资源", "资源分析"]),
            (("generation", "发电量"), ["发电量章节", "风力发电机组", "发电量"]),
            (("electricalPrimary", "电气一次"), ["电气一次", "电气", "主接线"]),
            (("electricalSecondary", "电气二次"), ["电气二次", "通信", "通讯"]),
            (("collectorLine", "集电线路"), ["集电线路"]),
            (("substationCivil", "土建升压站"), ["土建升压站", "升压站", "总平面"]),
            (("windFoundation", "风机基础"), ["风机基础"]),
            (("boxFoundation", "箱变基础"), ["箱变基础"]),
            (("road", "道路"), ["道路", "施工组织", "交通运输"]),
            (("land", "用地"), ["用地", "征地"]),
            (("earthwork", "土石方"), ["土石方"]),
            (("investment", "技经", "概算"), ["技经概算", "概算", "投资"]),
            (("finance", "财务"), ["财务"]),
        ]
        for markers, keywords in mappings:
            if any(marker in key_text for marker in markers):
                return keywords
        return []

    def _deduplicate_title_candidates(self, candidates: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
        """清洗、去重并按章节 resolver 加权排序标题候选。"""
        resolvers = [resolver for resolver in self.title_resolvers if resolver.accepts(spec)]
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in candidates:
            text = self._clean_table_caption_title(candidate.get("text") or "")
            if not text:
                continue
            if not self._is_plausible_original_table_title(text, candidate, spec):
                continue
            score = float(candidate.get("score") or 0.0)
            for resolver in resolvers:
                score += resolver.title_bonus(text, spec)
            item = {**candidate, "text": text, "score": round(score, 3)}
            identity = (str(item.get("source") or ""), re.sub(r"\s+", "", text))
            existing = deduped.get(identity)
            if existing is None or float(item.get("score") or 0.0) > float(existing.get("score") or 0.0):
                deduped[identity] = item
        return sorted(deduped.values(), key=lambda item: (float(item.get("score") or 0.0), int(item.get("order") or 0)), reverse=True)

    def _is_plausible_original_table_title(self, text: str, candidate: dict[str, Any], spec: dict[str, Any]) -> bool:
        """过滤明显的正文段落，避免宽泛关键词把正文误当原表题。

        Word/PDF 结构恢复时，table.caption 有时会错挂表前较长正文。资源章节里的
        “平均风速/风功率密度”这类规则又比较宽，如果不先判断候选是否像标题，就会把正文段落
        导出成表名。这里保留短标题、编号标题、表/附表标题和表内首行标题，剔除多句长正文。
        """
        source = str(candidate.get("source") or "")
        if source == "section_path":
            return True
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return False
        sentence_marks = len(re.findall(r"[。；;！？!?]", text))
        title_like = self._looks_like_caption_text(text) or bool(
            re.match(r"^(?:附表|表)\s*[\d一二三四五六七八九十]+", text)
        )
        numbered_heading = bool(re.match(r"^\d+(?:\.\d+)*(?:-\d+)?\.?\s*\S+", text))
        narrative_prefixes = (
            "\u7531\u4ee5\u4e0a\u56fe\u8868\u53ef\u4ee5\u770b\u51fa",
            "\u7531\u4e0a\u8868\u53ef\u77e5",
            "\u7531\u4e0a\u56fe\u53ef\u77e5",
            "\u6839\u636e\u4e0b\u8868",
            "\u5982\u56fe\u6240\u793a",
            "\u53ef\u4ee5\u770b\u51fa",
            "\u53ef\u89c1",
            "\u8bf4\u660e",
        )
        if any(prefix in text for prefix in narrative_prefixes):
            return False
        title_keywords = (
            "表",
            "清单",
            "工程量",
            "概算",
            "估算",
            "汇总",
            "统计",
            "成果",
            "计算",
            "参数",
            "材料",
            "设备",
            "土石方平衡",
            "工程总征地",
            "敏感性分析",
        )
        if title_like or source == "table_first_row":
            return len(compact) <= 140 and sentence_marks <= 1
        if numbered_heading and len(compact) <= 100 and sentence_marks <= 1:
            return True
        if len(compact) <= 70 and sentence_marks == 0 and any(keyword in text for keyword in title_keywords):
            return True
        # 资源章节等正文常包含统计关键词和单位范围，但多句长段不应成为原表标题。
        if len(compact) > 100 or sentence_marks >= 2:
            return False
        if source in {"caption", "table_caption", "previous_paragraph", "caption_before", "layout_linked_caption", "layout_nearby_title", "styled_title", "nearby_title"}:
            return any(keyword in text for keyword in title_keywords)
        return True

    def _table_has_title_hint(self, ast: DocumentAST, table: DocumentTable, spec: dict[str, Any]) -> bool:
        """判断一张表是否带有足以进入候选集的标题线索。"""
        candidates = self._original_table_title_candidates(ast, table, spec)
        if not candidates:
            return False
        text = "\n".join(candidate.get("text") or "" for candidate in candidates)
        patterns = self._match_patterns_for_spec(spec)
        if any(re.search(str(pattern), text, flags=re.IGNORECASE) for pattern in patterns):
            return True
        caption_keywords = list(spec.get("caption_keywords") or [])
        if caption_keywords and any(keyword in text for keyword in caption_keywords):
            return True
        direct_hints = self._spec_title_hints(spec)
        if not direct_hints:
            return True
        compact_text = re.sub(r"\s+", "", text)
        for hint in direct_hints:
            if hint and (hint in text or re.sub(r"\s+", "", hint) in compact_text):
                return True
        return False

    def _table_has_strong_title_hint(self, ast: DocumentAST, table: DocumentTable, spec: dict[str, Any]) -> bool:
        """判断标题是否足够强，可以覆盖错误章节路径。"""
        candidates = self._original_table_title_candidates(ast, table, spec)
        patterns = self._match_patterns_for_spec(spec)
        if not patterns:
            return False
        spec_text = _spec_text(spec)
        is_resource_spec = any(marker in spec_text for marker in ("resource", "windResource", "资源", "风能", "测风塔"))
        for candidate in candidates:
            if candidate.get("crossedTable"):
                continue
            source = str(candidate.get("source") or "")
            score = float(candidate.get("score") or 0.0)
            text = candidate.get("text") or ""
            if is_resource_spec and not self._is_strong_resource_original_table_title(text):
                continue
            if source in {"caption", "caption_before", "table_caption", "table_first_row", "layout_linked_caption", "layout_nearby_title", "layout_caption"} and score >= 3.0:
                if any(re.search(str(pattern), text, flags=re.IGNORECASE) for pattern in patterns):
                    return True
        return False

    def _is_strong_resource_original_table_title(self, text: str) -> bool:
        """资源原表跨章节时必须是带塔号或明确统计类标题，避免基础表误入资源章节。"""
        title = self._clean_table_caption_title(text)
        if re.search(r"[A-Za-z0-9]{2,8}#\s*测风塔", title):
            return True
        return bool(
            re.search(
                r"测风塔.*(?:平均风速|风功率密度|风向风能频率|扇区.*(?:风向|风能)|湍流|风切变|切变统计)",
                title,
                flags=re.IGNORECASE,
            )
        )

    def _spec_title_hints(self, spec: dict[str, Any]) -> list[str]:
        """从原表配置中抽出可用于标题预筛的关键词。"""
        hints: list[str] = []
        for item in self._patterns_for_spec(spec):
            cleaned = self._regex_hint_text(str(item))
            if cleaned:
                hints.append(cleaned)
        for item in spec.get("caption_keywords") or []:
            cleaned = self._clean_text(str(item))
            if cleaned:
                hints.append(cleaned)
        for item in self._key_patterns_for_spec(spec):
            patterns = item.get("patterns") or []
            for pattern in patterns:
                cleaned = self._regex_hint_text(str(pattern))
                if cleaned:
                    hints.append(cleaned)
        return list(dict.fromkeys(hints))

    def _regex_hint_text(self, pattern: str) -> str:
        """把正则里稳定的中文片段提取成简化关键词。"""
        cleaned = re.sub(r"\\[dDsSwWtrn]", "", pattern)
        cleaned = re.sub(r"[\^$.*+?()\[\]{}|\\]", "", cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)
        return cleaned

    def _looks_like_caption_text(self, text: str) -> bool:
        """判断段落是否像表题文本。"""
        return bool(re.search(r"^(?:附表|表)\s*[\d一二三四五六七八九十]+|(?:表|清单|工程量|概算|估算|汇总|统计|成果|计算|参数|材料|设备)$", text))

    def _matrix_text(self, matrix: list[list[str]]) -> str:
        """拼接表格矩阵文本。"""
        return self.builder._matrix_text(matrix)

    def _section_path_caption(self, table: DocumentTable) -> str:
        """从章节路径生成兜底表题。"""
        return self.builder._section_path_caption(table)

    def _caption_before_table_from_table(self, table: DocumentTable) -> str:
        """读取结构层或加载器写入的表前标题。"""
        return self.builder._caption_before_table_from_table(table)

    def _caption_before_table(self, ast: DocumentAST, table: DocumentTable) -> str:
        """兼容旧版表前段落题注识别。"""
        return self.builder._caption_before_table(ast, table)

    def _clean_text(self, text: str) -> str:
        """清理控制字符和重复空白。"""
        return self.builder._clean_text(text)

    def _clean_table_caption_title(self, text: str) -> str:
        """清理串在一起的图题/表题，保留最后一个真实表题。"""
        cleaner = getattr(self.builder, "_clean_table_caption_title", None)
        if callable(cleaner):
            return cleaner(text)
        return self._clean_text(text)


def _spec_text(spec: dict[str, Any]) -> str:
    """拼接原表配置中的关键标识文本。"""
    return " ".join(str(spec.get(name) or "") for name in ("key_prefix", "key", "builder", "name"))
