"""字段候选区域召回。"""

from __future__ import annotations
import re
from dataclasses import dataclass
from collections import defaultdict

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable
from word_parser.document.ast.evidence import Candidate
from word_parser.logger import logger


@dataclass(frozen=True)
class FieldSpec:
    """字段召回所需的预计算配置。"""

    code: str
    config: dict
    aliases: tuple[str, ...]
    table_captions: tuple[str, ...]
    table_keywords: tuple[str, ...]


@dataclass
class DocumentIndex:
    """文档召回倒排索引。"""

    paragraph_by_id: dict[str, DocumentBlock]
    table_by_id: dict[str, DocumentTable]
    table_text_by_id: dict[str, str]
    paragraph_ids_by_alias: dict[str, set[str]]
    table_ids_by_alias: dict[str, set[str]]
    paragraph_ids_by_section: dict[str, set[str]]
    table_ids_by_section: dict[str, set[str]]
    paragraph_ids_by_canonical_section: dict[str, set[str]]
    table_ids_by_canonical_section: dict[str, set[str]]
    table_ids_by_caption: dict[str, set[str]]
    has_section_context: bool


class CandidateRetriever:
    """根据字段配置从章节、段落和表格中召回候选内容。"""

    def __init__(self, field_configs: dict[str, dict], settings: dict | None = None):
        """初始化召回器。

        参数：
            field_configs: 字段配置字典。
        """
        self.field_configs = field_configs
        settings = settings or {}
        # Keep the exact legacy defaults for callers not using extraction_runtime.yaml.
        self.paragraph_alias_bonus = float(settings.get("paragraph_alias_bonus", 0.5))
        self.paragraph_hint_bonus = float(settings.get("paragraph_hint_bonus", 0.25))
        self.table_alias_bonus = float(settings.get("table_alias_bonus", 0.6))
        self.table_caption_bonus = float(settings.get("table_caption_bonus", 0.4))
        self.table_aggregate_bonus = float(settings.get("table_aggregate_bonus", 1.0))
        self.table_hint_bonus = float(settings.get("table_hint_bonus", 0.25))
        self.summary_fallback_score = float(settings.get("summary_fallback_score", 0.25))
        self.summary_section_keywords = tuple(settings.get(
            "summary_section_keywords", ("工程特性表", "综合说明")
        ))
        self.toc_markers = tuple(settings.get(
            "toc_markers", ("HYPERLINK", "PAGEREF", "TOC ", "\\o ", "_Toc")
        ))
        self.toc_headings = frozenset(settings.get("toc_headings", ("目录", "目錄", "contents")))
        self.toc_heading_prefix = str(settings.get("toc_heading_prefix", "目录"))
        self.toc_heading_max_chars = int(settings.get("toc_heading_max_chars", 120))
        self.toc_prefix_window_chars = int(settings.get("toc_prefix_window_chars", 80))

    def retrieve(self, ast: DocumentAST,
                 observation_hints: dict[str, dict[str, set[str]]] | None = None) -> list[Candidate]:
        """召回所有字段候选。

        参数：
            ast: 文档 AST。
            observation_hints: 预抽取发现的字段候选位置，只增加原文召回。

        返回：
            list[Candidate]: 候选列表。
        """
        specs = self._field_specs()
        index = self._build_document_index(ast, specs)
        candidates: list[Candidate] = []
        for spec in specs:
            source_types = spec.config.get("source_types") or ["paragraph", "table"]
            if isinstance(source_types, str):
                source_types = [source_types]
            if "paragraph" in source_types:
                candidates.extend(self._retrieve_paragraphs_for_field(
                    index, spec, (observation_hints or {}).get(spec.code, {}).get("paragraph", set())))
            if "table" in source_types:
                candidates.extend(self._retrieve_tables_for_field(
                    index, spec, (observation_hints or {}).get(spec.code, {}).get("table", set())))
        logger.info(f"候选召回器产出候选：{len(candidates)} 条")
        return candidates

    def _field_specs(self) -> list[FieldSpec]:
        """预计算字段召回配置，避免在大文档扫描中重复拆配置。"""
        specs: list[FieldSpec] = []
        for code, config in self.field_configs.items():
            specs.append(
                FieldSpec(
                    code=code,
                    config=config,
                    aliases=tuple(config.get("aliases") or []),
                    table_captions=tuple(config.get("source_priority", {}).get("table_captions", []) or []),
                    table_keywords=tuple(self._table_keywords(config)),
                )
            )
        return specs

    def _table_keywords(self, config: dict) -> list[str]:
        """从查找和聚合配置中收集仅用于表格的关键字。"""
        keywords: list[str] = []
        aggregate = config.get("table_aggregate") or {}
        keywords.extend(aggregate.get("value_headers") or [])
        keywords.extend(aggregate.get("require_any") or [])
        lookup = config.get("table_lookup") or {}
        keywords.extend(lookup.get("row_aliases") or [])
        keywords.extend(lookup.get("column_aliases") or [])
        keywords.extend(config.get("value_headers") or [])
        return list(dict.fromkeys(keyword for keyword in keywords if keyword))

    def _build_document_index(self, ast: DocumentAST, specs: list[FieldSpec]) -> DocumentIndex:
        """构建文档倒排索引，召回阶段按字段直接取候选 ID 集。"""
        aliases = sorted({alias for spec in specs for alias in [*spec.aliases, *spec.table_keywords] if alias}, key=len, reverse=True)
        section_keywords = sorted(
            {
                keyword
                for spec in specs
                for keyword in [
                    *(spec.config.get("sections", {}) or {}).get("include", []),
                    *(spec.config.get("sections", {}) or {}).get("exclude", []),
                ]
                if keyword
            },
            key=len,
            reverse=True,
        )
        caption_keywords = sorted({keyword for spec in specs for keyword in spec.table_captions if keyword}, key=len, reverse=True)

        paragraph_by_id: dict[str, DocumentBlock] = {}
        table_by_id: dict[str, DocumentTable] = {}
        table_text_by_id: dict[str, str] = {}
        paragraph_ids_by_alias: dict[str, set[str]] = defaultdict(set)
        table_ids_by_alias: dict[str, set[str]] = defaultdict(set)
        paragraph_ids_by_section: dict[str, set[str]] = defaultdict(set)
        table_ids_by_section: dict[str, set[str]] = defaultdict(set)
        paragraph_ids_by_canonical_section: dict[str, set[str]] = defaultdict(set)
        table_ids_by_canonical_section: dict[str, set[str]] = defaultdict(set)
        table_ids_by_caption: dict[str, set[str]] = defaultdict(set)
        has_section_context = False

        for block in ast.blocks:
            if block.type != "paragraph" or not block.text:
                continue
            if self._is_toc_block(block):
                continue
            paragraph_by_id[block.id] = block
            has_section_context = has_section_context or bool(block.section_path)
            self._index_text_hits(block.text, block.id, aliases, paragraph_ids_by_alias)
            self._index_text_hits(" / ".join(block.section_path), block.id, section_keywords, paragraph_ids_by_section)
            for section in block.meta.get("canonical_sections", []) or []:
                paragraph_ids_by_canonical_section[section].add(block.id)

        for table in ast.tables:
            table_by_id[table.id] = table
            has_section_context = has_section_context or bool(table.section_path)
            text = "\n".join(" | ".join(cell.text for cell in row) for row in table.rows)
            table.meta["table_text"] = text
            table_text_by_id[table.id] = text
            self._index_text_hits(text, table.id, aliases, table_ids_by_alias)
            self._index_text_hits(" / ".join(table.section_path), table.id, section_keywords, table_ids_by_section)
            for section in table.meta.get("canonical_sections", []) or []:
                table_ids_by_canonical_section[section].add(table.id)
            self._index_text_hits(table.caption or "", table.id, caption_keywords, table_ids_by_caption)

        return DocumentIndex(
            paragraph_by_id=paragraph_by_id,
            table_by_id=table_by_id,
            table_text_by_id=table_text_by_id,
            paragraph_ids_by_alias=dict(paragraph_ids_by_alias),
            table_ids_by_alias=dict(table_ids_by_alias),
            paragraph_ids_by_section=dict(paragraph_ids_by_section),
            table_ids_by_section=dict(table_ids_by_section),
            paragraph_ids_by_canonical_section=dict(paragraph_ids_by_canonical_section),
            table_ids_by_canonical_section=dict(table_ids_by_canonical_section),
            table_ids_by_caption=dict(table_ids_by_caption),
            has_section_context=has_section_context,
        )

    def _index_text_hits(self, text: str, item_id: str, keywords: list[str], output: dict[str, set[str]]) -> None:
        """把文本命中的关键词写入倒排索引。"""
        if not text:
            return
        compact_text = self._compact_text(text)
        for keyword in keywords:
            if keyword in text or self._compact_text(keyword) in compact_text:
                output[keyword].add(item_id)

    def _compact_text(self, text: str) -> str:
        return ''.join(str(text or '').split())

    def _is_toc_block(self, block: DocumentBlock) -> bool:
        meta = block.meta or {}
        if str(meta.get("structure_type") or meta.get("type") or "").lower() in {"toc", "table_of_contents"}:
            return True
        return self._is_toc_like_text(block.text or "")

    def _is_toc_like_text(self, text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return False
        compact = self._compact_text(cleaned)
        lowered = cleaned.lower()
        if any(marker.lower() in lowered for marker in self.toc_markers):
            return True
        if compact in self.toc_headings:
            return True
        if compact.startswith(self.toc_heading_prefix) and len(compact) < self.toc_heading_max_chars:
            return True
        toc_link_hits = len(re.findall(r"_Toc\d+|PAGEREF|HYPERLINK", cleaned, flags=re.IGNORECASE))
        if toc_link_hits >= 3:
            return True
        dotted_entries = len(re.findall(r"\d+(?:\.\d+)+[^\n]{0,50}(?:\.{3,}|…{2,}|\s{2,})\d+", cleaned))
        return self.toc_heading_prefix in cleaned[:self.toc_prefix_window_chars] and dotted_entries >= 2

    def _retrieve_paragraphs_for_field(self, index: DocumentIndex, spec: FieldSpec,
                                       hint_ids: set[str] | None = None) -> list[Candidate]:
        """按字段从段落倒排索引中取候选。"""
        result: list[Candidate] = []
        sections = spec.config.get("sections") or {}
        alias_ids = self._ids_for_keywords(index.paragraph_ids_by_alias, spec.aliases)
        section_ids = self._ids_for_keywords(index.paragraph_ids_by_canonical_section, sections.get("include", []))
        section_ids.update(self._ids_for_keywords(index.paragraph_ids_by_section, sections.get("include", [])))
        original_ids = section_ids | alias_ids
        candidate_ids = original_ids | ((hint_ids or set()) & index.paragraph_by_id.keys())
        blocks = sorted((index.paragraph_by_id[block_id] for block_id in candidate_ids), key=lambda item: item.order)
        for block in blocks:
            section_score = self._section_score_from_text(" / ".join(block.section_path), block.meta.get("canonical_sections", []), spec.config)
            compact_text = self._compact_text(block.text)
            alias_hit = any(alias in block.text or self._compact_text(alias) in compact_text for alias in spec.aliases)
            # 已归入其他章节时保持章节约束；无章节归属时允许别名兜底。
            if section_score < 0:
                continue
            hint_hit = block.id in (hint_ids or set()) and not alias_hit
            appendix_fallback = (
                section_score <= 0
                and bool(sections.get("include"))
                and self._is_appendix_source(block.section_path, block.text)
                and (alias_hit or hint_hit)
            )
            if section_score <= 0 and sections.get("include") and (
                block.section_path or block.meta.get("canonical_sections")
            ) and not appendix_fallback:
                continue
            if section_score <= 0 and not alias_hit and not hint_hit:
                continue
            score = section_score + (self.paragraph_alias_bonus if alias_hit else 0) + (self.paragraph_hint_bonus if hint_hit else 0)
            section_origin = self._section_origin(block.section_path, block.meta.get("canonical_sections", []), spec.config)
            result.append(
                Candidate(
                    field_code=spec.code,
                    field_name=spec.config.get("name", spec.code),
                    source_type="paragraph",
                    text=block.text,
                    score=score,
                    block_id=block.id,
                    page=block.page,
                    section_path=self._candidate_section_path(block.section_path, block.meta.get("canonical_sections", [])),
                    field_config=spec.config,
                    meta={"alias_hit": alias_hit, "section_origin": section_origin,
                          "observation_hint": hint_hit, "appendix_fallback": appendix_fallback},
                )
            )
        return result

    def _retrieve_tables_for_field(self, index: DocumentIndex, spec: FieldSpec,
                                   hint_ids: set[str] | None = None) -> list[Candidate]:
        """按字段从表格倒排索引中取候选。"""
        result: list[Candidate] = []
        sections = spec.config.get("sections") or {}
        alias_ids = self._ids_for_keywords(index.table_ids_by_alias, [*spec.aliases, *spec.table_keywords])
        caption_ids = self._ids_for_keywords(index.table_ids_by_caption, spec.table_captions)
        section_ids = self._ids_for_keywords(index.table_ids_by_canonical_section, sections.get("include", []))
        section_ids.update(self._ids_for_keywords(index.table_ids_by_section, sections.get("include", [])))
        original_ids = section_ids | alias_ids | caption_ids
        candidate_ids = original_ids | ((hint_ids or set()) & index.table_by_id.keys())
        tables = sorted((index.table_by_id[table_id] for table_id in candidate_ids), key=lambda item: item.order)
        for table in tables:
            table_text = index.table_text_by_id.get(table.id, "")
            section_score = self._section_score_from_text(" / ".join(table.section_path), table.meta.get("canonical_sections", []), spec.config)
            caption_text = table.caption or ""
            compact_caption = self._compact_text(caption_text)
            caption_hit = any(keyword in caption_text or self._compact_text(keyword) in compact_caption for keyword in spec.table_captions)
            compact_table_text = self._compact_text(table_text)
            alias_hit = any(alias in table_text or self._compact_text(alias) in compact_table_text for alias in spec.aliases)
            aggregate_hit = self._table_aggregate_hit(table_text, spec.config)
            if section_score < 0:
                continue
            hint_hit = table.id in (hint_ids or set())
            appendix_fallback = (
                section_score <= 0
                and bool(sections.get("include"))
                and (self._is_appendix_source(table.section_path, table.caption, table.meta)
                     or caption_hit)
                and (alias_hit or caption_hit or hint_hit or aggregate_hit)
            )
            if section_score <= 0 and sections.get("include") and (
                table.section_path or table.meta.get("canonical_sections")
            ) and not appendix_fallback:
                continue
            hint_only = hint_hit and not (alias_hit or caption_hit or aggregate_hit)
            if not alias_hit and not caption_hit and not aggregate_hit and not hint_only:
                continue
            score = section_score + (self.table_alias_bonus if alias_hit else 0) + (self.table_caption_bonus if caption_hit else 0) + (self.table_aggregate_bonus if aggregate_hit else 0) + (self.table_hint_bonus if hint_only else 0)
            section_origin = self._section_origin(table.section_path, table.meta.get("canonical_sections", []), spec.config)
            result.append(
                Candidate(
                    field_code=spec.code,
                    field_name=spec.config.get("name", spec.code),
                    source_type="table",
                    text=table_text,
                    score=score,
                    table_id=table.id,
                    page=table.page,
                    section_path=self._candidate_section_path(table.section_path, table.meta.get("canonical_sections", [])),
                    field_config=spec.config,
                    meta={"caption": table.caption, "alias_hit": alias_hit, "caption_hit": caption_hit,
                          "aggregate_hit": aggregate_hit, "section_origin": section_origin,
                          "observation_hint": hint_only, "appendix_fallback": appendix_fallback,
                          "table": table},
                )
            )
        return result

    def _table_aggregate_hit(self, table_text: str, config: dict) -> bool:
        """判断表格是否满足聚合抽取提示。"""
        aggregate = config.get("table_aggregate") or {}
        if not aggregate:
            return False
        value_headers = aggregate.get("value_headers") or []
        require_any = aggregate.get("require_any") or []
        compact_table_text = self._compact_text(table_text)
        if value_headers and not any(keyword in table_text or self._compact_text(keyword) in compact_table_text for keyword in value_headers):
            return False
        if require_any and not any(keyword in table_text or self._compact_text(keyword) in compact_table_text for keyword in require_any):
            return False
        reject_any = aggregate.get("reject_any") or []
        if reject_any and any(keyword in table_text or self._compact_text(keyword) in compact_table_text for keyword in reject_any):
            return False
        return True

    def _ids_for_keywords(self, index: dict[str, set[str]], keywords) -> set[str]:
        """合并多个关键词命中的文档对象 ID。"""
        ids: set[str] = set()
        for keyword in keywords or []:
            ids.update(index.get(keyword, set()))
        return ids

    @staticmethod
    def _is_appendix_source(section_path: list[str], caption: str | None = None,
                            meta: dict | None = None) -> bool:
        """识别附表或附录来源，供受章节限制的字段做跨章节候选召回。"""
        if any(re.search(r"附表|附录|附件", str(part)) for part in section_path):
            return True
        titles = [caption or ""]
        for candidate in (meta or {}).get("title_candidates") or []:
            if isinstance(candidate, dict):
                titles.append(str(candidate.get("text") or ""))
        return any(
            re.match(r"^\s*(?:附表|附录|附件)\s*[\d一二三四五六七八九十]", title)
            or re.match(r"^\s*0[1-9]\s*[^\d\s].*(?:表|清单)(?:\s*[（(].*)?$", title)
            for title in titles
        )

    def _section_score(self, section_path: list[str], config: dict) -> float:
        """计算章节匹配分。"""
        section_text = " / ".join(section_path)
        return self._section_score_from_text(section_text, [], config)

    def _section_score_from_text(self, section_text: str, canonical_sections: list[str] | tuple[str, ...], config: dict) -> float:
        """计算章节匹配分，优先使用 source_priority 中配置的章节权重。"""
        sections = config.get("sections") or {}
        canonical_text = " / ".join(canonical_sections or [])
        full_text = f"{canonical_text} / {section_text}" if canonical_text else section_text
        compact_full_text = self._compact_text(full_text)
        if any(keyword in full_text or self._compact_text(keyword) in compact_full_text for keyword in sections.get("exclude", [])):
            return -1.0
        matched = [keyword for keyword in sections.get("include", []) if keyword in full_text or self._compact_text(keyword) in compact_full_text]
        if matched:
            weights = config.get("source_priority", {}).get("sections", {}) or {}
            return max(float(weights.get(keyword, 1.0)) for keyword in matched)
        if any(keyword in full_text for keyword in self.summary_section_keywords):
            return self.summary_fallback_score
        return 0.0

    def _section_origin(self, section_path: list[str], canonical_sections, config: dict) -> str:
        score = self._section_score_from_text(" / ".join(section_path), list(canonical_sections or []), config)
        if score >= 1.0:
            return "target_section"
        if score > 0:
            return "summary_fallback"
        return "global_fallback"

    def _candidate_section_path(self, section_path: list[str], canonical_sections) -> list[str]:
        canonical = [section for section in (canonical_sections or []) if section]
        if not canonical:
            return section_path.copy()
        return [*canonical, *[section for section in section_path if section not in canonical]]
