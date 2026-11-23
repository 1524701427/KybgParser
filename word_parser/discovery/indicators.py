"""发现文档中的指标，并将指标名称匹配到已配置字段。

发现流程读取通用文档抽象语法树，不修改现有字段规则，
也不重新判定已抽取字段。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from collections import Counter
import re
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentBlock
from word_parser.document.ast.evidence import Extraction, FieldEvidence
from word_parser.primary.value_extractor import ValueExtractor

try:
    import ahocorasick
except ImportError:  # 标准库兜底逻辑确保旧环境仍可使用。
    ahocorasick = None

try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = process = None


@dataclass(frozen=True)
class Indicator:
    """未通过预定义字段查询而发现的名称、数值和来源。"""

    name: str
    raw_value: str
    unit: str | None
    source_type: str
    page: int | None
    section_path: tuple[str, ...]
    block_id: str | None = None
    label_block_id: str | None = None
    table_id: str | None = None
    row: int | None = None
    column: int | None = None
    field_code: str | None = None
    suggested_field_code: str | None = None
    match_method: str | None = None
    similarity: float = 0.0
    source_text: str | None = None
    row_label: str | None = None
    observation_kind: str = "label_value"

    def to_dict(self) -> dict[str, Any]:
        """返回可用于复核的 JSON 兼容观测结果。"""
        payload = asdict(self)
        payload["section_path"] = list(self.section_path)
        return payload


class IndicatorLexicon:
    """将观测到的标签与字段名称及配置别名匹配。"""

    @property
    def rapidfuzz_available(self) -> bool:
        """报告当前进程能否执行模糊相似度匹配。"""
        return fuzz is not None and process is not None

    def __init__(self, field_configs: dict[str, dict[str, Any]], matching_config: dict | None = None):
        """构建可复用的词典索引。

        参数：
            field_configs: 已有字段定义及其别名。
        """
        self.field_configs = field_configs
        self.matching_config = matching_config or {}
        self.codes_by_label: dict[str, set[str]] = {}
        for code, config in field_configs.items():
            for label in [config.get("name"), *(config.get("aliases") or [])]:
                key = self._key(label)
                if key:
                    self.codes_by_label.setdefault(key, set()).add(code)
        self.labels = tuple(self.codes_by_label)
        self.automaton = None
        if ahocorasick is not None and self.labels:
            automaton = ahocorasick.Automaton()
            for label in self.labels:
                automaton.add_word(label, label)
            automaton.make_automaton()
            self.automaton = automaton

    @staticmethod
    def _key(value: Any) -> str:
        """仅规范化空白和常见标签标点。"""
        return "".join(str(value or "").strip().rstrip("：: ").split()).casefold()

    def match(self, name: str) -> tuple[str | None, str | None, float]:
        """返回唯一匹配字段；有歧义的标签保持未匹配。

        参数：
            name: 文档中的指标标签。

        返回：
            字段代码、匹配方式及 0～100 分的名称相似度。
        """
        code, method, score = self.match_dictionary(name)
        if method is not None:
            return code, method, score
        return self.match_similarity(name)

    def match_dictionary(self, name: str) -> tuple[str | None, str | None, float]:
        """匹配完全一致的别名，或返回包含词的复核提示。

        参数：
            name: 文档中发现的指标名称。

        返回：
            字段代码、匹配方式及词典得分。
        """
        key = self._key(name)
        # 自动机采用前缀树，同时用于精确查找和下方的
        # 包含词扫描；普通字典仍作为无依赖的兜底实现。
        label = self.automaton.get(key, None) if self.automaton is not None else key
        exact = self.codes_by_label.get(label, set()) if label == key else set()
        if len(exact) == 1:
            return next(iter(exact)), "dictionary", 100.0
        if exact:
            return None, "ambiguous", 100.0
        # 包含词典术语可用于复核，但修饰词可能改变指标含义，
        # 例如“单机”或“合计”会让自动字段归属变得不可靠。
        if self.known_label_in(key):
            return None, "dictionary_suggestion", 90.0
        return None, None, 0.0

    def match_similarity(self, name: str) -> tuple[str | None, str | None, float]:
        """可用时使用 RapidFuzz 计算名称与别名的相似度。

        参数：
            name: 文档中发现的指标名称。

        返回：
            建议的字段代码、匹配方式及相似度分数。
        """
        key = self._key(name)
        if not key or fuzz is None or process is None:
            return None, None, 0.0
        ranked = process.extract(key, self.labels, scorer=fuzz.ratio, limit=None)
        if not ranked:
            return None, None, 0.0
        label, score, _ = ranked[0]
        codes = self.codes_by_label[label]
        if len(codes) == 1:
            code = next(iter(codes))
            competing_score = max(
                (other_score for other_label, other_score, _ in ranked[1:]
                 if code not in self.codes_by_label[other_label]),
                default=0.0,
            )
            if (score >= float(self.matching_config.get("acceptance_score", 92))
                    and score - competing_score >= float(self.matching_config.get("minimum_competing_gap", 8))):
                return code, "rapidfuzz", float(score)
        return None, "suggestion", float(score)

    def known_label_in(self, text: str) -> bool:
        """无需逐字段扫描即可检查文本是否包含词典标签。"""
        key = self._key(text)
        if self.automaton is not None:
            return any(True for _ in self.automaton.iter(key))
        return any(label in key for label in self.labels)


class IndicatorValueParser:
    """使用简单状态机解析标签、单位和值之间的关系。

    数字词元识别复用 ``ValueExtractor.NUMBER_PATTERN``；此解析器
    仅判断相邻文本和单元格与该数字词元的关系。
    """

    NON_INDICATOR_LABELS = {"序号", "编号", "备注", "说明", "单位", "类别", "阶段", "项目", "指标", "名称"}
    NUMBER_CELL = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*[^\d\s]*")

    def __init__(self, settings: dict | None = None):
        settings = settings or {}
        self.NON_INDICATOR_LABELS = set(settings.get("non_indicator_labels", self.NON_INDICATOR_LABELS))
        self.column_header_exclusions = set(settings.get(
            "column_header_exclusions",
            ["数量", "数值", "指标值", "金额", "总价", "单价", "单位", "备注"],
        ))
        self.paragraph_separators = tuple(settings.get("paragraph_separators", ("：", ":", "为", "取")))
        self.label_min_length = int(settings.get("label_min_length", 2))
        self.label_max_length = int(settings.get("label_max_length", 30))
        self.paragraph_clause_max_length = int(settings.get("paragraph_clause_max_length", 180))
        self.string_value_max_length = int(settings.get("string_value_max_length", 60))
        self.NUMBER_CELL = re.compile(settings.get("number_cell_pattern", self.NUMBER_CELL.pattern))
        self.column_header_unit_pattern = re.compile(settings.get(
            "column_header_unit_pattern", r"(.+?)[（(]([^()（）]{1,16})[）)]"))
        self.paragraph_clause_pattern = re.compile(settings.get(
            "paragraph_clause_pattern", r"[。；;，\n]|,(?!\d{3}(?:\D|$))"))
        self.two_cell_text_max_length = int(settings.get("two_cell_text_max_length", 60))
        self.two_cell_value_exclusions = frozenset(settings.get(
            "two_cell_value_exclusions", ("单位", "备注", "说明")
        ))

    def parse_table_pairs(self, cells: list[str]) -> list[tuple[str, str, str | None, int]]:
        """识别同一行中并列的多组“名称、数值”，不依赖字段配置。"""
        pairs: list[tuple[str, str, str | None, int]] = []
        index = 0
        while index + 1 < len(cells):
            label = cells[index].strip().rstrip("：:").strip()
            if not self.label_allowed(label):
                index += 1
                continue
            value_index = index + 1
            unit = None
            if self._unit_token(cells[value_index]) and value_index + 1 < len(cells):
                unit = cells[value_index].strip()
                value_index += 1
            token = cells[value_index].strip()
            parsed = self.parse_number(token)
            # 并列单元格必须完整表示一个数值，避免把编号或说明当作值。
            if parsed is None or self.NUMBER_CELL.fullmatch(token) is None:
                index += 1
                continue
            value, inline_unit = parsed
            pairs.append((label, value, inline_unit or unit, value_index))
            index = value_index + 1
        return pairs

    def parse_column_headers(self, cells: list[str]) -> dict[int, tuple[str, str | None]]:
        """从横向表头提取字段名称和括号中的单位。"""
        if len(cells) < 3:
            return {}
        headers: dict[int, tuple[str, str | None]] = {}
        for index, cell in enumerate(cells[1:], start=1):
            token = cell.strip()
            match = self.column_header_unit_pattern.fullmatch(token)
            name, unit = (match.group(1).strip(), match.group(2).strip()) if match else (token, None)
            if name in self.column_header_exclusions:
                continue
            if self.label_allowed(name) and self.parse_number(name) is None:
                headers[index] = (name, unit)
        return headers if len(headers) >= 2 else {}

    def parse_table_row(self, cells: list[str]) -> tuple[str, str, str | None, int] | None:
        """从表格行读取标签、可选单位和值。

        参数：
            cells: 按原始列顺序排列的单元格文本。

        返回：
            标签、原始数值、单位和值所在列；未找到时返回 ``None``。
        """
        state = "SEEK_LABEL"
        label = ""
        unit = None
        for index, text in enumerate(cells):
            token = text.strip()
            if state == "SEEK_LABEL":
                if index >= 2:
                    return None
                label = token.rstrip("：:").strip()
                if not self.label_allowed(label):
                    continue
                state = "SEEK_UNIT_OR_VALUE"
                continue
            parsed = self.parse_number(token)
            if parsed is not None:
                value, inline_unit = parsed
                if inline_unit:
                    unit = inline_unit
                elif unit is None and index + 1 < len(cells) and self._unit_token(cells[index + 1]):
                    unit = cells[index + 1].strip()
                return label, value, unit, index
            if state == "SEEK_UNIT_OR_VALUE" and self._unit_token(token):
                unit = token
                state = "SEEK_VALUE"
        return None

    def parse_paragraph(self, text: str) -> tuple[str, str, str | None] | None:
        """读取由分隔符连接的名称和值。

        参数：
            text: 一个文档段落。

        返回：
            标签、原始数值和单位；未找到时返回 ``None``。
        """
        for separator in self.paragraph_separators:
            label, found, remainder = text.partition(separator)
            if not found or not self.label_allowed(label.strip()):
                continue
            parsed = self.parse_number(remainder.strip())
            if parsed is not None:
                return label.strip(), *parsed
        return None

    def parse_paragraph_pairs(self, text: str) -> list[tuple[str, str, str | None]]:
        """扫描段落内的多组名称和值，保留未配置字段的原文候选。"""
        pairs: list[tuple[str, str, str | None]] = []
        clauses = self.paragraph_clause_pattern.split(text)
        for clause in clauses:
            clause = clause.strip()
            if not clause or len(clause) > self.paragraph_clause_max_length:
                continue
            for separator in self.paragraph_separators:
                label, found, remainder = clause.partition(separator)
                label = label.strip()
                if not found or not self.label_allowed(label):
                    continue
                remainder = remainder.strip()
                parsed = self.parse_number(remainder)
                if parsed is not None:
                    pairs.append((label, *parsed))
                elif separator in ("：", ":") and 1 <= len(remainder) <= self.string_value_max_length:
                    pairs.append((label, remainder, None))
                break
        return pairs

    def parse_adjacent_blocks(self, label: DocumentBlock, value: DocumentBlock) -> tuple[str, str, str | None] | None:
        """将以冒号结尾的标签与附近的数值段落关联。

        参数：
            label: 可能包含标签的段落。
            value: 后续包含数值的段落。

        返回：
            页码和版面位置一致时返回标签、原始数值和单位。
        """
        name = label.text.strip().rstrip("：:").strip()
        if not label.text.rstrip().endswith(("：", ":")) or not self.label_allowed(name):
            return None
        if value.order - label.order != 1 or label.page != value.page:
            return None
        if label.section_path and value.section_path and label.section_path != value.section_path:
            return None
        if not self._nearby_bboxes(label, value):
            return None
        parsed = self.parse_number(value.text.strip())
        return (name, *parsed) if parsed is not None else None

    @staticmethod
    def parse_number(text: str) -> tuple[str, str | None] | None:
        """使用现有正则表达式解析开头的数字。"""
        normalized = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
        match = ValueExtractor.NUMBER_PATTERN.match(normalized)
        if match is None or not match.group(1):
            return None
        return match.group(1), match.group(2) or None

    def label_allowed(self, label: str) -> bool:
        """排除过短的表头，同时保留有明确名称的电压指标。"""
        text = label.strip()
        chinese_count = sum("\u4e00" <= char <= "\u9fff" for char in text)
        return bool(self.label_min_length <= len(text) <= self.label_max_length and text not in self.NON_INDICATOR_LABELS
                    and (chinese_count >= 2 or (text.isalpha() and len(text) >= 3)))

    @staticmethod
    def _unit_token(text: str) -> bool:
        token = text.strip()
        return bool(token and len(token) <= 12 and " " not in token
                    and IndicatorValueParser.parse_number(token) is None)

    @staticmethod
    def _nearby_bboxes(label: DocumentBlock, value: DocumentBlock) -> bool:
        """优先使用 PDF 几何位置；Word 文档按内容顺序处理。"""
        def box(block: DocumentBlock) -> tuple[float, float, float, float] | None:
            raw = block.meta.get("bounding_box") or block.meta.get("bbox")
            if isinstance(raw, dict):
                raw = [raw.get(key) for key in ("x0", "y0", "x1", "y1")]
            if not isinstance(raw, (list, tuple)) or len(raw) < 4:
                return None
            try:
                return tuple(float(number) for number in raw[:4])
            except (TypeError, ValueError):
                return None

        first, second = box(label), box(value)
        if first is None or second is None:
            return True
        return -5 <= second[1] - first[3] <= 50


class IndicatorDiscovery:
    """从段落和文档表格中查找简单的名称和值配对。"""

    # 外观相近的范围词可能对应不同业务字段。
    SCOPE_TERMS = (
        ("单机", "单台", "双机", "合计", "总计", "总"),
        ("规划", "实际", "设计", "运行"),
        ("接入", "送出", "集电"),
        ("一期", "二期", "本期", "远期"),
        ("平均", "最大", "最小"),
        ("年", "月", "日"),
    )
    CONTEXT_VALUE = re.compile(r"^\s*(?:为|约为|达到|达|是|取|：|:)\s*(.+)$")

    def __init__(self, field_configs: dict[str, dict[str, Any]], mode: str = "active", settings: dict | None = None, lexicon: IndicatorLexicon | None = None):
        """使用已配置的字段词典初始化指标发现器。

        参数：
            field_configs: 已有字段定义及其别名。
            mode: ``shadow`` 仅观察；``active`` 允许精确匹配兜底。
        """
        self.field_configs = field_configs
        self.mode = mode
        settings = settings or {}
        self.lexicon = lexicon if lexicon is not None else IndicatorLexicon(field_configs, matching_config=settings.get("rapidfuzz"))
        self.value_parser = IndicatorValueParser(settings)
        self.SCOPE_TERMS = tuple(tuple(group) for group in settings.get("scope_terms", self.SCOPE_TERMS))
        self.CONTEXT_VALUE = re.compile(settings.get("context_value_pattern", self.CONTEXT_VALUE.pattern))
        self.safe_fallback_min_label_length = int(
            (settings.get("rapidfuzz") or {}).get("safe_fallback_min_label_length", 8)
        )
        self.contextual_clause_pattern = re.compile(settings.get(
            "contextual_clause_pattern", r"[。；;，,\n]"))
        self.contextual_label_min_length = int(settings.get("contextual_label_min_length", 4))
        self.contextual_prefix_guard_chars = int(settings.get("contextual_prefix_guard_chars", 10))

    def discover(self, ast: DocumentAST) -> list[Indicator]:
        """按配置的各阶段发现并匹配指标。

        参数：
            ast: 包含段落和表格的已解析文档。

        返回：
            按文档顺序排列的已匹配和未匹配观测结果。
        """
        return self.match_similarity(self.match_dictionary(self.discover_raw(ast)))

    def discover_raw(self, ast: DocumentAST) -> list[Indicator]:
        """发现名称和值配对并保留来源位置。

        参数：
            ast: 包含段落和表格的已解析文档。

        返回：
            按文档顺序排列的指标；未知名称仍保留供复核。
        """
        found: list[Indicator] = []
        for table in ast.tables:
            header_cells = [cell.text.strip() for cell in table.rows[0]] if table.rows else []
            headers = self.value_parser.parse_column_headers(header_cells)
            for row_number, row in enumerate(table.rows):
                cells = [cell.text.strip() for cell in row]
                pairs = self.value_parser.parse_table_pairs(cells)
                parsed = self.value_parser.parse_table_row(cells)
                if parsed is not None and not any(
                    pair[0] == parsed[0] and pair[1] == parsed[1] and pair[3] == parsed[3]
                    for pair in pairs
                ):
                    pairs.insert(0, parsed)
                elif parsed is not None and parsed[2]:
                    pairs = [parsed if pair[0] == parsed[0] and pair[1] == parsed[1]
                             and pair[3] == parsed[3] else pair for pair in pairs]
                for label, value, unit, value_index in pairs:
                    found.append(self._indicator(label, value, unit, "table", table.page,
                                                 table.section_path, table_id=table.id,
                                                 row=row_number, column=value_index))
                if len(cells) == 2 and not pairs and self.value_parser.label_allowed(cells[0]):
                    text_value = cells[1].strip()
                    if text_value and len(text_value) <= self.value_parser.two_cell_text_max_length and text_value not in self.value_parser.two_cell_value_exclusions:
                        found.append(self._indicator(cells[0], text_value, None, "table", table.page,
                                                     table.section_path, table_id=table.id,
                                                     row=row_number, column=1))
                if not headers or row_number == 0:
                    continue
                row_label = cells[0] if cells else ""
                for column, (label, header_unit) in headers.items():
                    if column >= len(cells):
                        continue
                    parsed_value = self.value_parser.parse_number(cells[column])
                    if parsed_value is None or self.value_parser.NUMBER_CELL.fullmatch(cells[column]) is None:
                        continue
                    value, inline_unit = parsed_value
                    found.append(self._indicator(
                        label, value, inline_unit or header_unit, "table", table.page,
                        table.section_path, table_id=table.id, row=row_number,
                        column=column, row_label=row_label, observation_kind="column_header",
                        source_text=f"{header_cells[column]} | {' | '.join(cells)}",
                    ))
        paragraphs = sorted((block for block in ast.blocks if block.type == "paragraph" and block.text),
                            key=lambda block: block.order)
        for index, block in enumerate(paragraphs):
            if block.type != "paragraph" or not block.text:
                continue
            parsed_pairs = self.value_parser.parse_paragraph_pairs(block.text)
            if not parsed_pairs:
                parsed = self.value_parser.parse_paragraph(block.text)
                parsed_pairs = [parsed] if parsed is not None else []
            for label, value, unit in parsed_pairs:
                found.append(self._indicator(label, value, unit, "paragraph", block.page,
                                             block.section_path, block_id=block.id,
                                             source_text=block.text))
            parsed_keys = {(label, value, unit) for label, value, unit in parsed_pairs}
            for label, value, unit in self._contextual_values(block.text):
                if (label, value, unit) in parsed_keys:
                    continue
                found.append(self._indicator(label, value, unit, "paragraph", block.page,
                                             block.section_path, block_id=block.id,
                                             source_text=block.text))
            if index + 1 < len(paragraphs):
                next_block = paragraphs[index + 1]
                adjacent = self.value_parser.parse_adjacent_blocks(block, next_block)
                if adjacent is not None:
                    label, value, unit = adjacent
                    found.append(self._indicator(label, value, unit, "paragraph", next_block.page,
                                                 next_block.section_path or block.section_path,
                                                 block_id=next_block.id,
                                                 label_block_id=block.id))
        return found

    def _contextual_values(self, text: str) -> list[tuple[str, str, str | None]]:
        """读取语句中紧跟数值的已配置标签。"""
        found: list[tuple[str, str, str | None]] = []
        for clause in self.contextual_clause_pattern.split(text):
            if not clause or len(clause) > self.value_parser.paragraph_clause_max_length:
                continue
            key = self.lexicon._key(clause)
            if self.lexicon.automaton is not None:
                labels = {label for _, label in self.lexicon.automaton.iter(key) if len(label) >= self.contextual_label_min_length}
            else:
                labels = {label for label in self.lexicon.labels if len(label) >= self.contextual_label_min_length and label in key}
            for label in sorted(labels, key=len, reverse=True):
                # 在原始语句上匹配，以保留标点和数值偏移位置。
                compact = "".join(clause.split())
                start = compact.casefold().find(label)
                if start < 0:
                    continue
                prefix = compact[:start]
                if any(term in prefix[-self.contextual_prefix_guard_chars:] and term not in label for group in self.SCOPE_TERMS for term in group):
                    continue
                suffix = compact[start + len(label):]
                match = self.CONTEXT_VALUE.match(suffix)
                if match is None:
                    continue
                parsed = self.value_parser.parse_number(match.group(1))
                if parsed is None:
                    continue
                value, unit = parsed
                found.append((label, value, unit))
                break  # 每个语句只保留一组无歧义的标签和值。
        return found

    def match_dictionary(self, indicators: list[Indicator]) -> list[Indicator]:
        """执行精确词典匹配及包含词匹配。

        参数：
            indicators: 原始文档观测结果。

        返回：
            带有词典匹配元数据的观测结果。
        """
        return [replace(item, field_code=code, match_method=method, similarity=score)
                for item in indicators
                for code, method, score in [self.lexicon.match_dictionary(item.name)]]

    def match_similarity(self, indicators: list[Indicator]) -> list[Indicator]:
        """仅对词典未处理的名称应用 RapidFuzz。

        参数：
            indicators: 词典已匹配和未匹配的观测结果。

        返回：
            带有可选模糊匹配建议的观测结果。
        """
        result: list[Indicator] = []
        for item in indicators:
            if item.match_method not in (None, "dictionary_suggestion"):
                result.append(item)
                continue
            code, method, score = self.lexicon.match_similarity(item.name)
            if method != "rapidfuzz":
                result.append(item if item.match_method else
                              replace(item, match_method=method, similarity=score))
                continue
            # 在兜底安全检查完成前，单独保存模糊匹配字段。
            result.append(replace(item, suggested_field_code=code,
                                  match_method=method, similarity=score))
        return result

    def recall_hints(self, indicators: list[Indicator]) -> dict[str, dict[str, set[str]]]:
        """把有单位和章节支撑的名称变体转成一次抽取的原文位置提示。

        提示只负责召回候选区域，不产生字段值。最终值仍由字段抽取规则核实。
        """
        hints: dict[str, dict[str, set[str]]] = {}
        for item in indicators:
            if item.match_method not in {"dictionary_suggestion", "suggestion"}:
                continue
            source_id = item.block_id if item.source_type == "paragraph" else item.table_id
            if not source_id:
                continue
            name = self.lexicon._key(item.name)
            candidates: set[str] = set()
            if item.match_method == "dictionary_suggestion":
                labels = ((label, codes) for label, codes in self.lexicon.codes_by_label.items()
                          if len(label) >= 4 and label in name)
            elif fuzz is not None and process is not None:
                ranked = process.extract(name, self.lexicon.labels, scorer=fuzz.ratio, limit=None)
                if not ranked or ranked[0][1] < 80:
                    continue
                label = ranked[0][0]
                codes = self.lexicon.codes_by_label[label]
                if len(codes) != 1:
                    continue
                code = next(iter(codes))
                competing = max((score for other, score, _ in ranked[1:]
                                 if code not in self.lexicon.codes_by_label[other]), default=0)
                if ranked[0][1] - competing < 8:
                    continue
                labels = ((label, codes),)
            else:
                continue
            for label, codes in labels:
                if not self._scope_agrees(name, label):
                    continue
                for code in codes:
                    config = self.field_configs[code]
                    # 名称变体若缺少目标单位，不能靠相似度引导取值。
                    if config.get("standard_unit") and not item.unit:
                        continue
                    if self._unit_allowed(item.unit, config) and self._section_allowed(item.section_path, config):
                        candidates.add(code)
            if len(candidates) == 1:
                code = next(iter(candidates))
                hints.setdefault(code, {}).setdefault(item.source_type, set()).add(source_id)
        return hints

    def fallback_extractions(self, indicators: list[Indicator], existing: list[Extraction],
                             include_covered: bool = False) -> list[Extraction]:
        """把安全关联的预抽取结果转为字段候选值。

        参数：
            indicators: 独立发现的文档观测结果。
            existing: 配置的正则抽取器和表格抽取器的结果。
            include_covered: 同一字段已抽到值时仍保留预抽取候选。

        返回：
            供现有归一化器和冲突消解器处理的保守候选值。
        """
        covered = {item.field_code for item in existing}
        header_counts = Counter((item.table_id, item.name) for item in indicators
                                if item.observation_kind == "column_header")
        contextual_codes = {id(item): self._safe_containment_code(item) for item in indicators
                            if item.match_method == "dictionary_suggestion"}
        contextual_values: dict[str, set[str]] = {}
        for item in indicators:
            code = contextual_codes.get(id(item))
            if code:
                contextual_values.setdefault(code, set()).add(item.raw_value.replace(",", ""))
        exact_codes = {item.field_code for item in indicators
                       if item.match_method == "dictionary" and item.field_code}
        output: list[Extraction] = []
        for item in indicators:
            if item.observation_kind == "column_header" and item.row_label not in {
                "", "数值", "指标值", "推荐值", "取值", "合计", "总计"
            }:
                # 多实体表格中的同名列不是单值字段，例如多座测风塔的空气密度。
                continue
            if item.observation_kind == "column_header" and header_counts[item.table_id, item.name] != 1:
                continue
            exact = item.match_method == "dictionary"
            fuzzy = item.match_method == "rapidfuzz"
            contextual = item.match_method == "dictionary_suggestion"
            code = (item.field_code if exact else item.suggested_field_code if fuzzy
                    else contextual_codes.get(id(item)) if contextual else None)
            if not code or (not include_covered and code in covered) or ((fuzzy or contextual) and code in exact_codes):
                continue
            if contextual and len(contextual_values.get(code, set())) != 1:
                continue
            config = self.field_configs[code]
            value_type = config.get("value_type", "number")
            if value_type not in {"number", "string"}:
                continue
            if value_type == "number" and self.value_parser.parse_number(item.raw_value) is None:
                continue
            if not self._unit_allowed(item.unit, config):
                continue
            if fuzzy and (not item.unit or not config.get("standard_unit")):
                continue
            if fuzzy and not self._safe_fuzzy_match(item, code, config):
                continue
            evidence = FieldEvidence(
                source_type=item.source_type,
                text=item.source_text or f"{item.name} | {item.raw_value} {item.unit or ''}".strip(),
                block_id=item.block_id,
                table_id=item.table_id,
                page=item.page,
                section_path=list(item.section_path),
                match_method="indicator_discovery",
                meta={"row": item.row, "column": item.column,
                      "labelBlockId": item.label_block_id},
            )
            output.append(Extraction(
                field_code=code,
                field_name=config.get("name", code),
                raw_value=item.raw_value,
                value=item.raw_value,
                unit=item.unit,
                score=0.5 if exact else 0.4 if contextual else 0.45,
                method="indicator_discovery",
                evidence=evidence,
                debug={"discovered_name": item.name, "row_index": item.row,
                       "column_index": item.column, "name_similarity": item.similarity,
                       "name_match": "dictionary_contextual" if contextual else item.match_method},
            ))
        return output

    def _safe_containment_code(self, item: Indicator) -> str | None:
        """只接受单位明确、口径一致且归属唯一的名称包含关系。"""
        if item.match_method != "dictionary_suggestion" or not item.unit:
            return None
        name = self.lexicon._key(item.name)
        candidates: set[str] = set()
        for label, codes in self.lexicon.codes_by_label.items():
            if len(label) < 4 or label not in name:
                continue
            extra = name.replace(label, "", 1)
            # 多出的型号、等级、塔号或高度会改变目标对象，不能当作普通修饰词。
            if re.search(r"[a-z]\s*\d|\d\s*[a-z#号]", extra):
                continue
            if not self._scope_agrees(name, label):
                continue
            for code in codes:
                config = self.field_configs[code]
                if (config.get("value_type", "number") == "number"
                    and config.get("standard_unit")
                    and self._unit_allowed(item.unit, config)
                    and self._section_allowed(item.section_path, config)):
                    candidates.add(code)
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _safe_fuzzy_match(self, item: Indicator, code: str, config: dict[str, Any]) -> bool:
        """仅接受兼容章节中唯一且接近的拼写错误匹配。

        参数：
            item: 名称由 RapidFuzz 匹配的指标。
            code: 候选的已配置字段代码。
            config: 现有字段配置。

        返回：
            模糊匹配建议能否补充缺失的映射字段。
        """
        name = self.lexicon._key(item.name)
        if len(name) < self.safe_fallback_min_label_length or not self._section_allowed(item.section_path, config):
            return False
        labels = (label for label, codes in self.lexicon.codes_by_label.items() if code in codes)
        return any(self._one_edit(name, label) and self._scope_agrees(name, label)
                   for label in labels)

    @staticmethod
    def _one_edit(left: str, right: str) -> bool:
        """检查标签是否只存在一次替换、插入或删除。"""
        if abs(len(left) - len(right)) > 1:
            return False
        if len(left) == len(right):
            return sum(a != b for a, b in zip(left, right)) == 1
        shorter, longer = sorted((left, right), key=len)
        index = 0
        while index < len(shorter) and shorter[index] == longer[index]:
            index += 1
        return shorter[index:] == longer[index + 1:]

    def _scope_agrees(self, observed: str, configured: str) -> bool:
        """修正拼写错误时保持明确的对象词和阶段词不变。"""
        return all(
            {term for term in group if term in observed}
            == {term for term in group if term in configured}
            for group in self.SCOPE_TERMS
        )

    @staticmethod
    def _section_allowed(section_path: tuple[str, ...], config: dict[str, Any]) -> bool:
        """遵守排除规则；附表候选允许作为目标章节之外的补漏线索。"""
        section_text = " ".join(section_path)
        sections = config.get("sections") or {}
        excludes = sections.get("exclude") or []
        includes = sections.get("include") or []
        if any(term and term in section_text for term in excludes):
            return False
        return (not section_text or not includes
                or any(term and term in section_text for term in includes)
                or bool(re.search(r"附表|附录|附件", section_text)))

    def _indicator(self, name: str, value: str, unit: str | None, source_type: str,
                   page: int | None, section_path: list[str], **location: Any) -> Indicator:
        return Indicator(name, value, unit, source_type, page, tuple(section_path),
                         **location)

    @staticmethod
    def _unit_allowed(unit: str | None, config: dict[str, Any]) -> bool:
        expected = config.get("standard_unit")
        if not expected:
            return True
        aliases = {expected, *(config.get("unit_aliases") or [])}
        return unit in aliases
