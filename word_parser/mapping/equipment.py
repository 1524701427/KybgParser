"""设备相关字段的最终映射规则。"""

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

def _schema_output_key(config_root: str | Path, code: str) -> str:
    """Resolve a domain's output through output_schema.yaml rather than inline placeholders."""
    outputs = ConfigLoader(config_root).load_required_yaml("output_schema.yaml").get("output_field_codes") or {}
    name = outputs.get(code)
    if not isinstance(name, str) or not name:
        raise ValueError(f"output_schema.yaml: missing mapping for {code}")
    return name if name.startswith("${") else "${" + name + "}"


def _fill_transformers_from_installation_estimate(parse_result: dict[str, Any], config_root: str | Path = 'configs') -> None:
    """漏识别电气设备清单时，使用明确标注的设备行。"""
    mapped = parse_result.get("mapped")
    result = parse_result.get("result")
    if not isinstance(mapped, dict) or not isinstance(result, dict):
        return
    table = mapped.get(_schema_output_key(config_root, "investmentEquipmentInstallationCopy")) or {}
    rows = table.get("data") or []
    columns = table.get("columns") or []
    name_col = next((i for i, name in enumerate(columns) if "项目名称" in str(name)), 1)
    unit_col = next((i for i, name in enumerate(columns) if name == "单位"), 2)
    count_col = next((i for i, name in enumerate(columns) if name == "数量"), 3)
    candidates: dict[str, Any] = {}
    sources: dict[str, str] = {}

    def offer(code: str, value: Any, row_text: str) -> None:
        if value is not None and code not in candidates:
            candidates[code] = value
            sources[code] = row_text

    for row in rows:
        if not isinstance(row, list) or len(row) <= name_col:
            continue
        name = str(row[name_col] or "")
        unit = str(row[unit_col] or "").strip() if len(row) > unit_col else ""
        count = row[count_col] if len(row) > count_col else None
        model = re.search(r"\b([A-Z]{1,8}\d*[A-Z]*-\d+(?:/\d+(?:-\d+/\d+(?:\.\d+)?)?)?)\b", name, re.I)
        if not model or unit not in {"台", "套"} or not isinstance(count, (int, float)):
            continue
        spec = model.group(1)
        rating = re.search(r"-(\d+)/(\d+(?:\.\d+)?)", spec)
        if not rating:
            continue
        capacity = int(rating.group(1))
        voltage = float(rating.group(2))
        voltage = int(voltage) if voltage.is_integer() else voltage
        if re.search(r"主变压器|主变(?!进线|保护|系统)", name) and not re.search(r"系统调试|试验", name):
            offer("mainTransformerModel", spec, name)
            offer("mainTransformerRatedCapacity", capacity, name)
            offer("mainTransformerNum", int(count), name)
        elif "接地变兼站用变" in name or "站用变兼接地变" in name:
            prefix = "groundingStationTransformer"
            for suffix, value in (("Model", spec), ("Voltage", voltage), ("Capacity", capacity), ("Quantity", int(count)), ("Unit", unit)):
                offer(prefix + suffix, value, name)
        elif re.search(r"接地变(?:压器|成套装置)?", name) and "兼" not in name:
            prefix = "groundingTransformer"
            for suffix, value in (("Model", spec), ("Voltage", voltage), ("Capacity", capacity), ("Quantity", int(count)), ("Unit", unit)):
                offer(prefix + suffix, value, name)

    changed = {}
    for code, value in candidates.items():
        placeholder = _schema_output_key(config_root, code)
        if mapped.get(placeholder) is not None:
            continue
        mapped[placeholder] = value
        changed[code] = value
    if not changed:
        return
    for section in result.get("sections") or []:
        for field in section.get("fields") or []:
            if field.get("fieldCode") in changed:
                field["value"] = changed[field["fieldCode"]]
    output_files = parse_result.get("outputFiles") or {}
    for key, payload in (("mapped", mapped), ("result", result)):
        if output_files.get(key):
            Path(output_files[key]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_path = output_files.get("detail")
    if detail_path and Path(detail_path).exists():
        details = json.loads(Path(detail_path).read_text(encoding="utf-8"))
        index = details.get("fieldIndex") or {}
        for code, value in changed.items():
            for item in (index.get(code), index.get(_schema_output_key(config_root, code))):
                if isinstance(item, dict):
                    item.update(value=value, status="PASS", source={"sourceType": "table", "text": sources[code], "matchMethod": "installation_estimate_equipment_row"})
        Path(detail_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")


def _fill_station_transformers_from_equipment_table(parse_result: dict[str, Any], config_root: str | Path = 'configs') -> None:
    """将独立站用变填入现有站用变展示栏位，并保留接地变原值。"""
    mapped = parse_result.get("mapped")
    result = parse_result.get("result")
    if not isinstance(mapped, dict) or not isinstance(result, dict):
        return

    equipment_tables = (
        table
        for section in result.get("sections") or []
        for table in section.get("tables") or []
        if table.get("key") == "electricalPrimaryEquipmentMaterial"
    )
    station_rows: list[tuple[str, tuple[str, int | float, int | float, int, str, str]]] = []
    combined_equipment_present = False
    for table in equipment_tables:
        columns = [re.sub(r"\s+", "", str(column or "")) for column in table.get("columns") or []]
        name_index = next((i for i, column in enumerate(columns) if "名称" in column), 1)
        spec_index = next((i for i, column in enumerate(columns) if "型号" in column or "规格" in column), 2)
        unit_index = next((i for i, column in enumerate(columns) if column == "单位"), 3)
        quantity_index = next((i for i, column in enumerate(columns) if "数量" in column), 4)
        for row in table.get("data") or []:
            if not isinstance(row, list) or len(row) <= max(name_index, spec_index):
                continue
            name = re.sub(r"\s+", "", str(row[name_index] or ""))
            if "接地" in name and "站用变" in name:
                combined_equipment_present = True
                continue
            if ("站用变" not in name and "场用电变压器" not in name) or any(
                word in name for word in ("变柜", "保护", "测控")
            ):
                continue
            specification = str(row[spec_index] or "").strip()
            model_match = re.search(r"\b((?:SCB|S)\d{0,2}-\d{2,6}/\d{1,3}(?:\.\d+)?(?:\s*kV)?)\b", specification, re.I)
            if model_match is None:
                continue
            model = re.sub(r"\s+", "", model_match.group(1))
            rating = re.search(r"-(\d{2,6})/(\d{1,3}(?:\.\d+)?)", model)
            if rating is None:
                continue
            capacity = int(rating.group(1))
            voltage_number = float(rating.group(2))
            voltage = int(voltage_number) if voltage_number.is_integer() else voltage_number
            quantity = row[quantity_index] if len(row) > quantity_index else None
            unit = re.sub(r"\s+", "", str(row[unit_index] or "")) if len(row) > unit_index else ""
            if not isinstance(quantity, (int, float)) or unit not in {"台", "套"}:
                continue
            row_text = " | ".join((name, specification, unit, str(quantity)))
            station_rows.append((name, (model, voltage, capacity, int(quantity), unit, row_text)))

    changed: dict[str, Any] = {}
    normal_rows = [row for name, row in station_rows if "备用" not in name]
    normal_rows.sort(key=lambda row: row[1], reverse=True)
    primary = normal_rows[0] if normal_rows else None
    backup_rows = [row for name, row in station_rows if "备用" in name]
    if not backup_rows and primary:
        backup_rows = [row for row in normal_rows[1:] if row[1] < primary[1]]
    backup = backup_rows[0] if backup_rows else None
    if primary and not combined_equipment_present:
        for suffix, value in zip(("model", "voltage", "capacity", "quantity", "unit"), primary):
            placeholder = _schema_output_key(config_root, "groundingStationTransformer" + suffix.title())
            if mapped.get(placeholder) is None:
                mapped[placeholder] = value
                changed["groundingStationTransformer" + suffix.title()] = value

    if backup:
        current = mapped.get(_schema_output_key(config_root, "stationTransformerCapacity10kv"))
        if current is None or current == backup[0] or re.fullmatch(r"\s*站用变容量为\s*\d+(?:\.\d+)?\s*kVA\s*", str(current)):
            mapped[_schema_output_key(config_root, "stationTransformerCapacity10kv")] = backup[0]
            changed["stationTransformerCapacity10kv"] = backup[0]

    if not changed:
        return
    for section in result.get("sections") or []:
        for field in section.get("fields") or []:
            if field.get("fieldCode") in changed:
                field["value"] = changed[field["fieldCode"]]
    output_files = parse_result.get("outputFiles") or {}
    for key, payload in (("mapped", mapped), ("result", result)):
        if output_files.get(key):
            Path(output_files[key]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_path = output_files.get("detail")
    if detail_path and Path(detail_path).exists():
        details = json.loads(Path(detail_path).read_text(encoding="utf-8"))
        field_index = details.get("fieldIndex") or {}
        for code, value in changed.items():
            source_row = backup if code == "stationTransformerCapacity10kv" else primary
            if source_row is None:
                continue
            source = {
                "sourceType": "table", "text": source_row[5],
                "matchMethod": "station_service_equipment_row",
                "tableId": "electricalPrimaryEquipmentMaterial",
            }
            for entry in [field_index.get(code), *(
                field for section in details.get("sections") or []
                for field in section.get("fields") or [] if field.get("fieldCode") == code
            )]:
                if isinstance(entry, dict):
                    entry.update(value=value, status="PASS", source=source)
        Path(detail_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

def _map_final_investment_fields(parse_result: dict[str, Any]) -> None:
    """根据实际概算层级填充下游概算字段。"""
    import re

    mapped = parse_result.get("mapped")
    if not isinstance(mapped, dict):
        return
    table = mapped.get("${engineering_estimate_table}") or {}
    rows = table.get("data") or []
    columns = table.get("columns") or []
    label_index = next((i for i, name in enumerate(columns) if "项目名称" in str(name)), 1)
    amount_index = next((i for i, name in enumerate(columns) if "合计" in str(name)), 5)

    def clean(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "")).replace("\u000b", "")

    def amount(row: list[Any]) -> int | float | None:
        value = row[amount_index] if len(row) > amount_index else None
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def matching_value(patterns: tuple[str, ...]) -> int | float | None:
        for row in rows:
            if len(row) > label_index and amount(row) is not None and any(re.search(p, clean(row[label_index]), re.I) for p in patterns):
                return amount(row)
        return None

    def group_value(patterns: tuple[str, ...]) -> int | float | None:
        for i, row in enumerate(rows):
            label = clean(row[label_index]) if len(row) > label_index else ""
            if not any(re.search(p, label, re.I) for p in patterns):
                continue
            if amount(row) is not None:
                return amount(row)
            for child in rows[i + 1:]:
                serial = clean(child[0]) if child else ""
                if re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+", serial, re.I):
                    break
                child_label = clean(child[label_index]) if len(child) > label_index else ""
                if re.fullmatch(r"(?:工程|项目)?总投资(?:合计)?|动态投资(?:合计)?", child_label) and amount(child) is not None:
                    return amount(child)
        return None

    supporting_group_value = group_value((r"^配套费$",))
    values = {
        "delivery_project": group_value((r"(?:送出|外送|送电)(?:线路)?(?:工程|投资)",)),
        "expansion_project": group_value((r"扩建工程", r"间隔扩建")),
        "outgoing_shared_cost": group_value((r"送出分摊费", r"分摊费", r"分摊费用")),
        "supporting_cost": supporting_group_value if supporting_group_value is not None else mapped.get("${supporting_cost}"),
        "area_management_building": group_value((r"片区管理综合",)),
        "smart_wind_farm": group_value((r"智慧风场",)),
        "new_energy_sensing_equipment": group_value((r"新能源场站感知设备",)),
        "research_development_cost": group_value((r"研发",)),
        "technology_cost": group_value((r"科技",)),
        "centralized_control_platform_cost": group_value((r"平台集控费",)),
        "static_investment": mapped.get("${investment_static_partial}"),
        "dynamic_investment": mapped.get("${investment_dynamic_partial}") or mapped.get("${investment_dynamic_total}"),
        "static_investment_per_kw": mapped.get("${investment_per_kw_static_partial}") or mapped.get("${investment_per_kw_static_total}"),
        "dynamic_investment_per_kw": mapped.get("${investment_per_kw_dynamic_partial}") or mapped.get("${investment_per_kw_dynamic_total}"),
        "project_static_investment": mapped.get("${investment_static_total}"),
        "project_dynamic_investment": mapped.get("${investment_dynamic_total}"),
        "unit_kw_static_investment": mapped.get("${investment_per_kw_static_total}"),
        "unit_kw_dynamic_investment": mapped.get("${investment_per_kw_dynamic_total}"),
    }
    for code, value in values.items():
        mapped["${" + code + "}"] = value
    if mapped.get("${investment_interest_total}") is None:
        mapped["${investment_interest_total}"] = mapped.get("${investment_construction_interest_total}")
    if mapped.get("${investment_project_total}") is None:
        mapped["${investment_project_total}"] = mapped.get("${investment_dynamic_total}")
    if mapped.get("${investment_total_part_total}") is None:
        mapped["${investment_total_part_total}"] = matching_value((r"^静态投资合计$",))
    if mapped.get("${investment_outgoing_line_legacy_total}") is None:
        mapped["${investment_outgoing_line_legacy_total}"] = matching_value((r"送出.*110kV", r"110kV.*送出"))

    # 汇总字段在映射后才得到数值，同步展示结果与审计详情。
    aliases = {
        "investmentConstructionInterestGrandTotal": "investment_interest_total",
        "investmentProjectTotalCost": "investment_project_total",
        "investmentTotalPartTotal": "investment_total_part_total",
        "investment110kvOutgoingLineProjectTotal": "investment_outgoing_line_legacy_total",
        "finalDeliveryProject": "delivery_project",
        "finalDynamicInvestment": "dynamic_investment",
        "finalStaticInvestmentPerKw": "static_investment_per_kw",
        "finalDynamicInvestmentPerKw": "dynamic_investment_per_kw",
    }
    for field_code, placeholder_code in aliases.items():
        value = mapped.get("${" + placeholder_code + "}")
        if value is None:
            continue
        parsed_field = (parse_result.get("fields") or {}).get(field_code)
        if isinstance(parsed_field, dict) and parsed_field.get("value") is None:
            parsed_field["value"] = value
        for section in (parse_result.get("result") or {}).get("sections") or []:
            for field in section.get("fields") or []:
                if field.get("fieldCode") == field_code and field.get("value") is None:
                    field["value"] = value

    detail_path = (parse_result.get("outputFiles") or {}).get("detail")
    if detail_path and Path(detail_path).exists():
        details = json.loads(Path(detail_path).read_text(encoding="utf-8"))
        for field_code, placeholder_code in aliases.items():
            value = mapped.get("${" + placeholder_code + "}")
            entry = (details.get("fieldIndex") or {}).get(field_code)
            if value is None or not isinstance(entry, dict) or entry.get("value") is not None:
                continue
            entry.update({
                "value": value, "status": "PASS",
                "source": {"sourceType": "table", "text": "工程总概算表对应行或同口径汇总值", "matchMethod": "investment_equivalent_mapping", "sectionPath": ["技经概算"]},
                "rule": {"resolver": "investment_equivalent_mapping"},
            })
        Path(detail_path).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    mapped_path = (parse_result.get("outputFiles") or {}).get("mapped")
    if mapped_path:
        Path(mapped_path).write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
    result_path = (parse_result.get("outputFiles") or {}).get("result")
    if result_path and isinstance(parse_result.get("result"), dict):
        Path(result_path).write_text(json.dumps(parse_result["result"], ensure_ascii=False, indent=2), encoding="utf-8")

