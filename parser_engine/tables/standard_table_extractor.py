"""需求标准表的确定性抽取工具。

本模块负责从 AST 表格中抽取标准表行数据；最终 JSON 列顺序、缺值补齐
和 details 来源说明仍由 ``ResultBuilder`` 处理。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentTable


class StandardTableExtractor:
    """从文档 AST 中抽取需求文档规定的标准表。

    新标准表应优先复用少量通用模式和配置化映射；只有通用模式无法覆盖时，
    才在这里增加轻量 hook，避免演变成每个表一个解析器。
    """

    def distribution_equipment_rows(
        self,
        ast: DocumentAST | None,
        field_value: Callable[[str, bool], Any],
    ) -> list[dict[str, Any]]:
        """构建电气一次配电装置标准表行。"""
        specs = self.distribution_equipment_specs(ast) if ast is not None else {}
        return [
            {"voltageLevel": "35kV", "equipment": "35kV接地变用变容量", "parameter": field_value("groundingTransformerCapacity35kv", True)},
            {"voltageLevel": None, "equipment": "35kV接地变兼站用变容量", "parameter": field_value("groundingStationTransformerCapacity35kv", True)},
            {"voltageLevel": "10kV", "equipment": "10kV站用变容量", "parameter": field_value("stationTransformerCapacity10kv", True)},
            {"voltageLevel": "110kV", "equipment": "断路器", "parameter": specs.get("circuitBreakerSpec") or field_value("circuitBreakerSpec", False)},
            {"voltageLevel": None, "equipment": "隔离开关", "parameter": specs.get("disconnectorSpec") or field_value("disconnectorSpec", False)},
            {"voltageLevel": None, "equipment": "电流互感器", "parameter": specs.get("currentTransformerSpec") or field_value("currentTransformerSpec", False)},
            {"voltageLevel": None, "equipment": "电压互感器", "parameter": specs.get("voltageTransformerSpec") or field_value("voltageTransformerSpec", False)},
            {"voltageLevel": "220kV", "equipment": "断路器", "parameter": None},
            {"voltageLevel": None, "equipment": "隔离开关", "parameter": None},
            {"voltageLevel": None, "equipment": "电流互感器", "parameter": None},
            {"voltageLevel": None, "equipment": "电压互感器", "parameter": None},
        ]

    def distribution_equipment_specs(self, ast: DocumentAST) -> dict[str, str]:
        """从源表中抽取 110kV 设备参数。"""
        found: dict[str, tuple[int, str]] = {}
        for table in ast.tables:
            matrix = self.table_matrix(table)
            text = self.matrix_text(matrix)
            if not any(keyword in text for keyword in ("断路器", "隔离开关", "隔离接地开关", "电流互感器", "电压互感器")):
                continue
            if not any(keyword in text for keyword in ("110kV", "126kV", "GIS", "配电装置")):
                continue
            for code, value in self.equipment_specs_from_rows(matrix).items():
                score = self.equipment_spec_score(code, value)
                if score > found.get(code, (-1, ""))[0]:
                    found[code] = (score, value)
        return {code: value for code, (_score, value) in found.items()}

    def equipment_specs_from_rows(self, matrix: list[list[str]]) -> dict[str, str]:
        """从一个表格矩阵中按高压设备段逐行抽取设备参数。"""
        specs: dict[str, str] = {}
        last_equipment_code: str | None = None
        scoped_table = any(self.row_opens_high_voltage_equipment_scope(row) for row in matrix)
        in_high_voltage_scope = not scoped_table
        for row in matrix:
            row_text = " | ".join(cell for cell in row if cell).strip()
            if not row_text:
                continue
            if scoped_table:
                if self.row_opens_high_voltage_equipment_scope(row):
                    in_high_voltage_scope = True
                    last_equipment_code = None
                    continue
                if self.row_closes_high_voltage_equipment_scope(row):
                    in_high_voltage_scope = False
                    last_equipment_code = None
                    continue
                if not in_high_voltage_scope:
                    continue
            code, value = self.equipment_spec_from_row(row)
            if code is not None and value is not None:
                if code in specs:
                    last_equipment_code = None
                    continue
                specs[code] = value
                last_equipment_code = code
                continue
            if last_equipment_code in {"currentTransformerSpec", "voltageTransformerSpec"} and self.equipment_continuation_row(row):
                continuation = self.equipment_parameter_from_row(row)
                if continuation:
                    specs[last_equipment_code] = f"{specs[last_equipment_code]} {continuation}".strip()
        return specs

    def row_opens_high_voltage_equipment_scope(self, row: list[str]) -> bool:
        """判断当前行是否开启 110kV/126kV 高压设备小段。"""
        text = " | ".join(cell for cell in row if cell).strip()
        if not re.search(r"(?:110|126)\s*kV", text, flags=re.IGNORECASE):
            return False
        return any(keyword in text for keyword in ("GIS", "配电装置", "成套设备", "主变进线间隔", "出线间隔", "间隔"))

    def row_closes_high_voltage_equipment_scope(self, row: list[str]) -> bool:
        """判断当前行是否进入低压/35kV 设备段并结束高压设备小段。"""
        text = " | ".join(cell for cell in row if cell).strip()
        if not re.search(r"(?<![0-9])(?:35|10)\s*kV", text, flags=re.IGNORECASE):
            return False
        return any(keyword in text for keyword in ("开关柜", "配电装置", "站用变", "接地变", "无功补偿", "母线", "电缆"))

    def equipment_spec_from_row(self, row: list[str]) -> tuple[str | None, str | None]:
        """从单行中识别设备类型和参数。"""
        row_text = " | ".join(cell for cell in row if cell).strip()
        mappings = [
            ("circuitBreakerSpec", ["SF6断路器", "断路器"], ["接地开关", "隔离"]),
            ("disconnectorSpec", ["三工位隔离接地开关", "三工位隔离开关", "隔离开关"], []),
            ("currentTransformerSpec", ["电流互感器"], ["间隙接地电流互感器", "中性点"]),
            ("voltageTransformerSpec", ["电压互感器", "线路电压互感器"], []),
        ]
        for code, aliases, exclusions in mappings:
            if any(exclusion in row_text for exclusion in exclusions):
                continue
            if not any(alias in row_text for alias in aliases):
                continue
            parameter = self.equipment_parameter_from_labeled_row(row, aliases)
            if parameter is None:
                continue
            parameter = self.strip_equipment_label(parameter, aliases)
            if code == "circuitBreakerSpec" and "断路器" not in row_text:
                continue
            if code == "disconnectorSpec" and "隔离" not in row_text:
                continue
            if code in {"circuitBreakerSpec", "disconnectorSpec"} and not self.looks_like_primary_equipment_parameter(parameter):
                continue
            if code in {"currentTransformerSpec", "voltageTransformerSpec"} and not re.search(r"[0-9]", parameter):
                continue
            return code, parameter
        return None, None

    def looks_like_primary_equipment_parameter(self, value: str) -> bool:
        """判断文本是否像一次设备规格参数，而不是数量或费用。"""
        if not re.search(r"[0-9]", value):
            return False
        return bool(re.search(r"kV|kA|\bA\b|/\s*[0-9]|额定|开断|耐受|SF6|GCB|TPS", value, flags=re.IGNORECASE))

    def equipment_parameter_from_labeled_row(self, row: list[str], aliases: list[str]) -> str | None:
        """从含设备标签的行中抽取标签所在单元格或其右侧参数单元格。"""
        label_index = None
        for index, cell in enumerate(row):
            if any(alias in cell for alias in aliases):
                label_index = index
                break
        if label_index is None:
            return None
        label_cell = row[label_index].strip()
        if re.search(r"[0-9]", label_cell):
            return self.normalize_equipment_parameter(label_cell)
        for cell in row[label_index + 1:]:
            cleaned = cell.strip()
            if cleaned and re.search(r"[0-9]", cleaned):
                return self.normalize_equipment_parameter(cleaned)
        return None

    def equipment_parameter_from_row(self, row: list[str]) -> str | None:
        """从续写行中抽取参数文本。"""
        nonempty = [cell.strip() for cell in row if cell and cell.strip()]
        if not nonempty:
            return None
        for cell in row[1:]:
            cleaned = cell.strip()
            if not cleaned:
                continue
            if any(keyword in cleaned for keyword in ("断路器", "隔离", "互感器")) or re.search(r"[0-9]", cleaned):
                return self.normalize_equipment_parameter(cleaned)
        return self.normalize_equipment_parameter(nonempty[-1])

    def equipment_continuation_row(self, row: list[str]) -> bool:
        """判断当前行是否是电流/电压互感器参数的续写行。"""
        text = " | ".join(cell for cell in row if cell).strip()
        if not text or any(keyword in text for keyword in ("断路器", "隔离", "电流互感器", "电压互感器", "避雷器", "开关柜", "接地开关", "架空终端", "终端", "母线", "线夹", "导线", "电缆", "套管", "汇控柜", "显示器")):
            return False
        nonempty = [cell for cell in row if cell.strip()]
        if len(nonempty) > 2:
            return False
        return bool(re.search(r"(?:VA|/|P|S|kV|A)", text, flags=re.IGNORECASE)) and bool(re.search(r"[0-9]", text))

    def strip_equipment_label(self, value: str, aliases: list[str]) -> str:
        """去掉设备名称前缀，只保留参数文本。"""
        cleaned = value.strip()
        for alias in aliases:
            cleaned = re.sub(rf"^.*?{re.escape(alias)}\s*[:：，,]?\s*", "", cleaned)
        return cleaned.strip()

    def normalize_equipment_parameter(self, value: str) -> str:
        """归一化设备参数文本中的空白、分隔符和重复量程。"""
        cleaned = self.clean_text(value)
        cleaned = re.sub(r"\s*\|\s*", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"(?<![0-9])([0-9]+)\s+\1\s*-\s*([0-9]+\s*/\s*[0-9]+\s*A)", r"\1-\2", cleaned, flags=re.IGNORECASE)
        return cleaned

    def equipment_spec_score(self, code: str, value: str) -> int:
        """为同类设备候选打分，用于跨表选择更完整的参数。"""
        score = 1
        if code == "currentTransformerSpec" and "600-1200/1A" in value:
            score += 5
        if code == "currentTransformerSpec" and "0.5/0.5" in value:
            score += 2
        if code == "voltageTransformerSpec" and "35/√" in value:
            score += 5
        if code == "voltageTransformerSpec" and "30/30/30/100VA" in value:
            score += 3
        if code == "voltageTransformerSpec" and "3P/3P" in value:
            score += 2
        if code in {"circuitBreakerSpec", "disconnectorSpec"} and "126kV" in value:
            score += 2
        return score

    def table_matrix(self, table: DocumentTable) -> list[list[str]]:
        """将 AST 表格转换为清洗后的文本矩阵。"""
        return [[self.clean_text(cell.text) for cell in row] for row in table.rows]

    def matrix_text(self, matrix: list[list[str]]) -> str:
        """将表格矩阵拼成用于锚点判断的文本。"""
        return " | ".join(cell for row in matrix for cell in row if cell)

    def clean_text(self, text: str) -> str:
        """清洗 Word 单元格文本中的控制字符和重复空白。"""
        text = text.replace("\u3000", " ")
        text = re.sub(r"[\x00-\x1f]", " ", text)
        return re.sub(r"\s+", " ", text).strip()
