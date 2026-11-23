"""电气二次设备和通信电源配置抽取。"""

from __future__ import annotations

from word_parser.config.domain_regex import domain_regex

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST


class ElectricalSecondaryRulesMixin:
    """电气二次设备和通信电源配置抽取，通过 ElectricalRulesMixin 组合到结果构建器。"""

    def _build_electrical_secondary_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "electricalSecondaryMainEquipment": [],
            "electricalSecondaryCommunicationEquipment": [],
        }
        for table in ast.tables:
            caption = self._clean_text(table.caption or self._caption_before_table(ast, table) or self._caption_before_table_from_table(table) or "")
            section_caption = self._clean_text(" ".join(table.section_path or []))
            target_text = f"{caption}\n{section_caption}\n{self._table_text(table)[:300]}"
            key = self._electrical_secondary_table_key(target_text)
            if key is None:
                continue
            rows = self._raw_rows_from_table(table)
            if rows:
                details[key] = rows
        return details

    def _electrical_secondary_table_key(self, text: str) -> str | None:
        for spec in self.electrical_secondary_table_key_specs:
            if self._table_key_spec_matches(spec, text):
                return str(spec.get("key"))
        return None

    def _communication_power_design_from_ast(self, ast: DocumentAST) -> str | None:
        text = "\n".join(self._clean_text(block.text or "") for block in self._body_blocks(ast) if block.text)
        table_text = "\n".join(self._table_text(table) for table in ast.tables)
        page_text = "\n".join(self._clean_text(str(page.get("text", ""))) for page in (ast.meta.get("pdf_page_texts") or []) if isinstance(page, dict))
        combined = f"{text}\n{table_text}\n{page_text}"
        patterns = [
            r"((?:本项目|本工程|升压站)[^。；;\n]{0,20}?配(?:置|备)\s*[0-9]+\s*套\s*[-－]?\s*48\s*V\s*/\s*[0-9]+\s*[×xX*]\s*[0-9]+\s*A\s*开关电源[^。；;\n]{0,80})",
            r"(\-?\s*48\s*V\s*/\s*200\s*Ah\s*\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60\s*[:\uff1a]\s*1\s*\u7ec4)",
            r"(200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60\s*1\s*\u7ec4\u53ca\s*1\s*\u5957\s*DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e)",
            r"(1\s*\u7ec4\s*200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,30}?DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e\s*1\s*\u5957)",
            r"(48\s*V\s*/\s*200\s*Ah[^\n\u3002\uff1b;]{0,30}?\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,20}?(?:1\s*\u7ec4))",
            r"(48\s*V\s*/\s*200\s*Ah[^\n\u3002\uff1b;]{0,50})",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined, flags=re.IGNORECASE)
            if match:
                return self._normalize_communication_power_design(match.group(1))
        return None

    def _communication_power_design_description_from_ast(self, ast: DocumentAST) -> str | None:
        patterns = self._communication_power_design_description_patterns()
        texts = [self._clean_text(block.text or "") for block in self._body_blocks(ast) if block.text]
        texts.extend(
            self._clean_text(str(page.get("text", "")))
            for page in (ast.meta.get("pdf_page_texts") or [])
            if isinstance(page, dict) and page.get("text")
        )
        for text in texts:
            for sentence in self._sentences(text):
                if self._communication_power_design_description_matches(sentence, patterns):
                    return self._clean_text(sentence).rstrip("。；;")
            if self._communication_power_design_description_matches(text, patterns):
                return self._clean_text(text).rstrip("。；;")
        blocks = self._body_blocks(ast)
        for index, block in enumerate(blocks):
            anchor = self._clean_text(block.text or "")
            if "通信电源" not in anchor and "通讯电源" not in anchor:
                continue
            if not re.search(domain_regex(self, "electrical_secondary", "search_001", r"(?:具体)?配(?:置|备)(?:如下|为|：|:)"), anchor):
                continue
            if not any("通信" in part or "通讯" in part for part in (block.section_path or [])):
                continue
            items = []
            for next_block in blocks[index + 1 : index + 13]:
                item = self._clean_text(next_block.text or "")
                if re.match(domain_regex(self, "electrical_secondary", "match_002", r"^\s*\d+(?:\.\d+){1,}\s*\S"), item) or "技术要求" in item:
                    break
                if re.search(domain_regex(self, "electrical_secondary", "search_003", r"(?:电源|蓄电池|电池|整流|配电)"), item) and re.search(
                    domain_regex(self, "electrical_secondary", "search_004", r"\d+(?:\.\d+)?\s*(?:V|Ah|A\b|套|组|台|面)"), item, flags=re.IGNORECASE
                ):
                    items.append(item.rstrip("。；;"))
            if items:
                return "；".join(dict.fromkeys(items))
        return None

    def _communication_power_unit_quantity_from_ast(
        self, ast: DocumentAST
    ) -> tuple[str | None, Any, str, list[str]] | None:
        table_candidates: list[tuple[int, str | None, Any, str, list[str]]] = []
        for table in ast.tables:
            matrix = self._table_matrix(table)
            header = self._header_row(matrix, ["单位", "数量"])
            if not header:
                continue
            unit_index = self._find_header_index(header, ["单位", "单 位"])
            quantity_index = self._find_header_index(header, ["数量", "数 量"])
            if unit_index is None or quantity_index is None:
                continue
            for row in matrix[matrix.index(header) + 1 :]:
                row_text = self._clean_text(" | ".join(row))
                compact = re.sub(domain_regex(self, "electrical_secondary", "sub_005", r"\s+"), "", row_text)
                score = 0
                if "通讯电池" in compact or "通信电池" in compact:
                    score = 300
                elif re.search(domain_regex(self, "electrical_secondary", "search_006", r"48V/200Ah"), compact, flags=re.IGNORECASE) and "蓄电池" in compact:
                    score = 200
                if not score:
                    continue
                unit_value = self._clean_text(row[unit_index]) if unit_index < len(row) else None
                quantity_value = self._normalize_scalar(row[quantity_index]) if quantity_index < len(row) else None
                if unit_value or quantity_value is not None:
                    table_candidates.append((score, unit_value or None, quantity_value, row_text, list(table.section_path or ["电气二次"])))
        if table_candidates:
            _, unit_value, quantity_value, evidence_text, section_path = max(table_candidates, key=lambda item: item[0])
            return unit_value, quantity_value, evidence_text, section_path

        blocks = self._configured_text_blocks(
            ast,
            "electrical_secondary",
            ["电气二次", "通信", "通讯"],
            ["通信电源", "通讯电源", "200Ah", "蓄电池"],
        )
        patterns = [
            r"([0-9]+(?:\.\d+)?)\s*(套|组|台)\s*[-－]?\s*48\s*V\s*/\s*[0-9]+\s*[×xX*]\s*[0-9]+\s*A\s*开关电源",
            r"(?:48\s*V\s*/\s*200\s*Ah|200\s*Ah)[^\n。；;]{0,50}?蓄电池[^\n。；;]{0,20}?([0-9]+(?:\.\d+)?)\s*(组|套|台)",
            r"([0-9]+(?:\.\d+)?)\s*(组|套|台)[^\n。；;]{0,20}?(?:48\s*V\s*/\s*200\s*Ah|200\s*Ah)[^\n。；;]{0,40}?蓄电池",
        ]
        text_sources = [
            (self._clean_text(block.text or ""), list(block.section_path or ["电气二次"]))
            for block in blocks
        ]
        text_sources.extend(
            (self._clean_text(str(page.get("text", ""))), ["电气二次"])
            for page in (ast.meta.get("pdf_page_texts") or [])
            if isinstance(page, dict) and page.get("text")
        )
        for text, section_path in text_sources:
            for pattern_index, pattern in enumerate(patterns):
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                if pattern_index == 0:
                    quantity, unit_value = match.group(1), match.group(2)
                else:
                    quantity, unit_value = match.group(1), match.group(2)
                return unit_value, self._normalize_scalar(quantity), text, section_path
        return None

    def _communication_power_design_description_patterns(self) -> list[str]:
        return [
            r"(?:本项目|本工程)[^。；;\n]{0,20}?配(?:置|备)\s*[0-9]+\s*套\s*[-－]?\s*48\s*V\s*/\s*[0-9]+\s*[×xX*]\s*[0-9]+\s*A\s*开关电源[^。；;\n]{0,100}?蓄电池",
            r"200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60\s*1\s*\u7ec4\u53ca\s*1\s*\u5957\s*DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e",
            r"1\s*\u7ec4\s*200\s*Ah\s*\u514d\u7ef4\u62a4\u84c4\u7535\u6c60[^\n\u3002\uff1b;]{0,30}?DC\s*/\s*DC\s*\u7535\u6e90\u8f6c\u6362\u88c5\u7f6e\s*1\s*\u5957",
        ]

    def _communication_power_design_description_matches(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _normalize_communication_power_design(self, text: str) -> str:
        value = self._normalize_text_value(text)
        value = re.sub(domain_regex(self, "electrical_secondary", "sub_007", r"\s+"), "", value)
        value = value.lstrip("-")
        if "48V/200Ah" in value and "\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60" in value:
            return re.sub(domain_regex(self, "electrical_secondary", "sub_008", r"(\u9600\u63a7\u5f0f\u5bc6\u5c01\u94c5\u9178\u84c4\u7535\u6c60)[:\uff1a,\uff0c]?(1\u7ec4)"), r"\1：\2", value)
        value = re.sub(domain_regex(self, "electrical_secondary", "sub_009", r"^1\u7ec4(200Ah\u514d\u7ef4\u62a4\u84c4\u7535\u6c60)[\uff0c,]?"), r"\g<1>" + "1\u7ec4\u53ca", value)
        value = value.replace("：", "，").replace(":", "，")
        value = re.sub(domain_regex(self, "electrical_secondary", "sub_010", r"，+"), "，", value).strip("，")
        value = re.sub(domain_regex(self, "electrical_secondary", "sub_011", r"(?<!，)(1组)$"), r"，\1", value)
        return value

    def _ups_configuration_from_blocks(self, ast: DocumentAST) -> str | None:
        for block in ast.blocks:
            found = re.search(domain_regex(self, "electrical_secondary", "search_012", r"本工程取UPS容量为([^。；;\n]+)。([^。；;\n]*双冗余方式)"), block.text)
            if found:
                return f"容量为{found.group(1).strip()}，{found.group(2).strip()}"
        return self._regex_from_blocks(ast, r"本工程取UPS容量为([^。；;\n]+)")
