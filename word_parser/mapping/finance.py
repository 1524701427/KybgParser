"""财务相关字段的最终映射规则。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from word_parser.config.loader import ConfigLoader
from word_parser.output.presentation import ResultPresentationMixin
from word_parser.secondary.table_values.results import final_result_with_table_values

from word_parser.mapping.common import (
    _COMBINED_TABLE_DISPLAY_FIELDS,
    _TOWER_ROW_FIELDS,
    _WIND_ROW_FIELDS,
    _WIND_RECORD_FIELDS,
    _is_present,
    _flatten_values,
    _comparable,
    _values_covered,
    _combined_columns,
    _invalid_tower_metadata,
)


def _cost_years_from_split_header_table(result: dict[str, Any], row_aliases: tuple[str, ...]) -> dict[str, int | float]:
    """从年份另起一行的成本表中，按行名和年份表头恢复有证据的逐年值。"""
    recovered: dict[str, int | float] = {}
    for section in result.get("sections") or []:
        for table in section.get("tables") or []:
            if table.get("key") not in {"financeTotalCostEstimate", "financeTotalCostEstimateContinuation"}:
                continue
            rows = table.get("data") or []
            columns = [re.sub(r"\s+", "", str(cell or "")) for cell in table.get("columns") or []]
            if "项目" in columns and "合计" in columns and "建设期" not in columns and any(re.fullmatch(r"第\d+年", cell) for cell in columns):
                label_index = columns.index("项目")
                for row in rows:
                    if not isinstance(row, list) or len(row) <= label_index:
                        continue
                    label = re.sub(r"\s+", "", str(row[label_index] or ""))
                    if label not in row_aliases:
                        continue
                    for column_index, header in enumerate(columns):
                        if column_index >= len(row) or (header != "合计" and not re.fullmatch(r"第\d+年", header)):
                            continue
                        value = row[column_index]
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            recovered.setdefault(header, value)
                    break
            for index, year_row in enumerate(rows):
                if not isinstance(year_row, list):
                    continue
                years = [int(match.group(1)) for cell in year_row
                         if (match := re.fullmatch(r"第\s*(\d+)\s*年", str(cell or "").strip()))]
                if len(years) < 2 or index == 0:
                    continue
                heading = rows[index - 1]
                if not isinstance(heading, list):
                    continue
                heading_text = [re.sub(r"\s+", "", str(cell or "")) for cell in heading]
                if "项目" not in heading_text:
                    continue
                label_index = heading_text.index("项目")
                if "建设期" in heading_text and "合计" in heading_text:
                    value_start = heading_text.index("建设期") + 1
                elif "合计" in heading_text:
                    value_start = heading_text.index("合计") + 1
                else:
                    value_start = label_index + 1
                for row in rows[index + 1:]:
                    if not isinstance(row, list) or len(row) <= label_index:
                        continue
                    if any(re.fullmatch(r"第\s*\d+\s*年", str(cell or "").strip()) for cell in row):
                        break
                    label = re.sub(r"\s+", "", str(row[label_index] or ""))
                    if label not in row_aliases:
                        continue
                    for offset, year in enumerate(years):
                        cell_index = value_start + offset
                        if cell_index < len(row):
                            value = row[cell_index]
                            if isinstance(value, (int, float)) and not isinstance(value, bool):
                                recovered.setdefault(f"第{year}年", value)
                    break
    return recovered


def _price_years_from_recovered_tables(result: dict[str, Any], label: str) -> dict[str, int | float]:
    """从按年份重建的利润附表恢复二次抽取未覆盖的电价年份。"""
    recovered: dict[str, int | float] = {}
    for section in result.get("sections") or []:
        for table in section.get("tables") or []:
            if table.get("key") not in {"financeProfitDistribution", "financeProfitDistributionContinuation"}:
                continue
            columns = [re.sub(r"\s+", "", str(value or "")) for value in table.get("columns") or []]
            if "项目" not in columns or "合计" not in columns:
                continue
            label_index = columns.index("项目")
            for row in table.get("data") or []:
                if not isinstance(row, list) or len(row) <= label_index:
                    continue
                row_label = re.sub(r"\s+", "", str(row[label_index] or ""))
                if not row_label.startswith(label):
                    continue
                for index, header in enumerate(columns):
                    if re.fullmatch(r"第\d+年", header) and index < len(row):
                        value = row[index]
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            recovered.setdefault(header, value)
                break
    return recovered


def _combine_finance_cost_mappings(
    parse_result: dict[str, Any], enhanced: dict[str, Any], config_root: str | Path,
) -> None:
    """按表格列名组装 2×22 数组：第一行列名，第二行对应数值。"""
    mapped = parse_result.get("mapped")
    result = parse_result.get("result")
    if not isinstance(mapped, dict) or not isinstance(result, dict):
        return
    output_codes = ConfigLoader(config_root).load_yaml("output_schema.yaml").get("output_field_codes") or {}
    finance_sections = [section for section in result.get("sections") or [] if section.get("name") == "财务"]
    extracted_sections = [section for section in enhanced.get("sections") or [] if section.get("name") == "财务"]
    if not finance_sections or not extracted_sections:
        return
    extracted = {
        field.get("fieldCode"): field
        for section in extracted_sections for field in section.get("tableFields") or []
        if field.get("status") == "OK"
    }
    details_path = (parse_result.get("outputFiles") or {}).get("detail")
    details = json.loads(Path(details_path).read_text(encoding="utf-8")) if details_path and Path(details_path).exists() else None
    changed = False
    for kind, label, row_aliases in (
        ("MaterialCost", "材料费", ("材料费",)),
        ("RepairCost", "修理费", ("修理费", "维修费")),
    ):
        code = f"finance{kind}Schedule"
        mapped_name = output_codes.get(code)
        if not mapped_name:
            continue
        placeholder = mapped_name if str(mapped_name).startswith("${") else "${" + str(mapped_name) + "}"
        if placeholder not in mapped:
            continue
        components = (
            (f"finance{kind}Total", "financeTotalCostEstimate"),
            (f"finance{kind}Years1To13", "financeTotalCostEstimate"),
            (f"finance{kind}Years12To13Continuation", "financeTotalCostEstimateContinuation"),
            (f"finance{kind}Years14To21", "financeTotalCostEstimateContinuation"),
        )
        verified = {
            component_code: field
            for component_code, table_key in components
            if (field := extracted.get(component_code))
            and (field.get("source") or {}).get("tableKey") == table_key
            and any(alias in str((field.get("source") or {}).get("rowText") or "") for alias in row_aliases)
        }
        values = {"合计": None, **{f"第{year}年": None for year in range(1, 22)}}
        total = verified.get(f"finance{kind}Total")
        if total and isinstance(total.get("value"), (int, float)) and not isinstance(total.get("value"), bool):
            values["合计"] = total["value"]
        for suffix in ("Years1To13", "Years14To21"):
            field = verified.get(f"finance{kind}{suffix}")
            series = field.get("value") if field else None
            if not isinstance(series, dict):
                continue
            years = range(1, 14) if suffix == "Years1To13" else range(14, 22)
            for year in years:
                key = f"第{year}年"
                value = series.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values[key] = value
        continuation = verified.get(f"finance{kind}Years12To13Continuation")
        continuation_values = continuation.get("value") if continuation else None
        if isinstance(continuation_values, dict):
            for year in (12, 13):
                key = f"第{year}年"
                value = continuation_values.get(key)
                if values[key] is None and isinstance(value, (int, float)) and not isinstance(value, bool):
                    values[key] = value
        for key, value in _cost_years_from_split_header_table(result, row_aliases).items():
            if key in values and values[key] is None:
                values[key] = value
        # 先按年份键对齐，再同时导出表头和值；缺失年份仍占固定列位。
        combined = [list(values), list(values.values())] if any(value is not None for value in values.values()) else None
        mapped[placeholder] = combined
        changed = True
        for section in finance_sections:
            fields = section.setdefault("fields", [])
            target = next((field for field in fields if field.get("fieldCode") == code), None)
            if target is None:
                target = {"fieldCode": code, "name": f"{label}（合计及第1年至第21年）", "unit": "万元"}
                fields.append(target)
            target["value"] = combined
        if details is not None:
            source = {
                "sourceType": "table",
                "matchMethod": "finance_cost_series",
                "tableId": "financeTotalCostEstimate",
                "sectionPath": ["财务"],
                "meta": {
                    "row": label,
                    "valueOrder": list(values),
                    "tables": sorted({(field.get("source") or {}).get("tableKey") for field in verified.values()}),
                    "missingColumns": [key for key, value in values.items() if value is None],
                },
            } if combined is not None else None
            entry_values = {"value": combined, "unit": "万元", "status": "PASS" if combined is not None else "MISSING", "source": source}
            for key in (code, placeholder):
                entry = (details.get("fieldIndex") or {}).get(key)
                if isinstance(entry, dict):
                    entry.update(entry_values)
            for section in details.get("sections") or []:
                if section.get("name") == "财务":
                    for entry in section.get("fields") or []:
                        if entry.get("fieldCode") in {code, placeholder}:
                            entry.update(entry_values)
    if not changed:
        return
    mapped_path = (parse_result.get("outputFiles") or {}).get("mapped")
    if mapped_path:
        Path(mapped_path).write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
    result_path = (parse_result.get("outputFiles") or {}).get("result")
    if result_path:
        Path(result_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if details is not None:
        Path(details_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

def _combine_finance_price_mappings(
    parse_result: dict[str, Any], enhanced: dict[str, Any], config_root: str | Path,
) -> None:
    """将两个源表合并为按年份对齐的上网电价数组。"""
    mapped = parse_result.get("mapped")
    result = parse_result.get("result")
    if not isinstance(mapped, dict) or not isinstance(result, dict):
        return
    output_codes = ConfigLoader(config_root).load_yaml("output_schema.yaml").get("output_field_codes") or {}
    extracted = {
        field.get("fieldCode"): field
        for section in enhanced.get("sections") or []
        if section.get("name") == "财务"
        for field in section.get("tableFields") or []
        if field.get("status") == "OK"
    }
    details_path = (parse_result.get("outputFiles") or {}).get("detail")
    details = json.loads(Path(details_path).read_text(encoding="utf-8")) if details_path and Path(details_path).exists() else None
    changed = False
    for kind, label in (("WithoutTax", "上网电价（不含税）"), ("WithTax", "上网电价（含税）")):
        code = f"financeOnGridPrice{kind}Schedule"
        mapped_name = output_codes.get(code)
        if not mapped_name:
            continue
        placeholder = mapped_name if str(mapped_name).startswith("${") else "${" + str(mapped_name) + "}"
        if placeholder not in mapped:
            continue
        components = (
            (f"financeOnGridPrice{kind}Year1", "financeProfitDistribution"),
            (f"financeOnGridPrice{kind}Years2To13", "financeProfitDistribution"),
            (f"financeOnGridPrice{kind}Years14To21", "financeProfitDistributionContinuation"),
        )
        verified = {
            component_code: field
            for component_code, table_key in components
            if (field := extracted.get(component_code))
            and (field.get("source") or {}).get("tableKey") == table_key
            and (
                label in str((field.get("source") or {}).get("rowText") or "")
                or (
                    ("不含" in str((field.get("source") or {}).get("rowText") or "")) == (kind == "WithoutTax")
                    and "电价" in str((field.get("source") or {}).get("rowText") or "")
                    and ("含增值税" in str((field.get("source") or {}).get("rowText") or "") or "不含增值税" in str((field.get("source") or {}).get("rowText") or ""))
                )
            )
        }
        values = {f"第{year}年": None for year in range(1, 22)}
        first = verified.get(f"financeOnGridPrice{kind}Year1")
        if first and isinstance(first.get("value"), (int, float)) and not isinstance(first.get("value"), bool):
            values["第1年"] = first["value"]
        for suffix, years in (("Years2To13", range(2, 14)), ("Years14To21", range(14, 22))):
            field = verified.get(f"financeOnGridPrice{kind}{suffix}")
            series = field.get("value") if field else None
            if not isinstance(series, dict):
                continue
            for year in years:
                key = f"第{year}年"
                value = series.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values[key] = value
        if details is not None and any(value is None for value in values.values()):
            for year, value in _price_schedule_from_original_tables(details, kind).items():
                key = f"第{year}年"
                if key in values and values[key] is None:
                    values[key] = value
        for key, value in _price_years_from_recovered_tables(result, label).items():
            if key in values and values[key] is None:
                values[key] = value
        combined = [list(values), list(values.values())] if any(value is not None for value in values.values()) else None
        mapped[placeholder] = combined
        changed = True
        for section in result.get("sections") or []:
            if section.get("name") != "财务":
                continue
            fields = section.setdefault("fields", [])
            target = next((field for field in fields if field.get("fieldCode") == code), None)
            if target is None:
                target = {"fieldCode": code, "name": f"{label}第1年至第21年", "unit": "元/kWh"}
                fields.append(target)
            target["value"] = combined
        if details is not None:
            source = {
                "sourceType": "table",
                "matchMethod": "finance_grid_price_series",
                "tableId": "financeProfitDistribution",
                "sectionPath": ["财务"],
                "meta": {
                    "row": label,
                    "valueOrder": list(values),
                    "tables": sorted({(field.get("source") or {}).get("tableKey") for field in verified.values()}),
                    "missingColumns": [key for key, value in values.items() if value is None],
                },
            } if combined is not None else None
            entry_values = {"value": combined, "unit": "元/kWh", "status": "PASS" if combined is not None else "MISSING", "source": source}
            detail_index = details.setdefault("fieldIndex", {})
            detail_index.setdefault(code, {"fieldCode": code, "name": f"{label}第1年至第21年", "section": "财务"})
            for key in (code, placeholder):
                entry = detail_index.get(key)
                if isinstance(entry, dict):
                    entry.update(entry_values)
            for section in details.get("sections") or []:
                if section.get("name") == "财务":
                    fields = section.setdefault("fields", [])
                    if not any(entry.get("fieldCode") == code for entry in fields):
                        fields.append({"fieldCode": code, "name": f"{label}第1年至第21年"})
                    for entry in fields:
                        if entry.get("fieldCode") in {code, placeholder}:
                            entry.update(entry_values)
    if not changed:
        return
    output_files = parse_result.get("outputFiles") or {}
    if output_files.get("mapped"):
        Path(output_files["mapped"]).write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
    if details is not None:
        Path(details_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")


def _price_schedule_from_original_tables(details: dict[str, Any], kind: str) -> dict[int, float]:
    """按年份表头读取跨页利润表中的电价行，兼容“电价（含增值税）”写法。"""
    values: dict[int, float] = {}
    for table in (details.get("tableIndex") or {}).values():
        if "利润与利润分配" not in str(table.get("name") or ""):
            continue
        matrix = table.get("data") or []
        years: list[int] = []
        for row in matrix[:5]:
            candidate = [int(match.group(1)) for cell in row for match in re.finditer(r"第\s*(\d+)\s*年", str(cell))]
            if len(candidate) > len(years):
                years = candidate
        if not years:
            continue
        for row in matrix:
            label = re.sub(r"\s+", "", str(row[1] if len(row) > 1 else ""))
            if "电价" not in label:
                continue
            without_tax = "不含" in label
            with_tax = ("含税" in label or "含增值税" in label) and not without_tax
            if (kind == "WithoutTax" and not without_tax) or (kind == "WithTax" and not with_tax):
                continue
            numbers = [float(item) for item in row[2:] if isinstance(item, (int, float)) and not isinstance(item, bool) and 0 < item < 2]
            if len(numbers) == len(years):
                values.update(zip(years, numbers))
    return values

