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

def _map_final_investment_fields(parse_result: dict[str, Any], config_root: str | Path | None = None) -> None:
    """Compatibility adapter: sync the extracted investment values to outputs."""
    from word_parser.secondary.investment_completion import load_investment_completion, calculate_investment_completion
    mapped = parse_result.get("mapped")
    if not isinstance(mapped, dict):
        return
    if config_root is None:
        config_root = Path(__file__).resolve().parents[2] / "configs"
    policy = load_investment_completion(config_root)
    mapped.update(calculate_investment_completion(mapped, policy))
    aliases = policy["result_field_aliases"]
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

