"""Secondary extraction: primitives. Existing rule semantics are preserved."""

from __future__ import annotations

import re

from typing import Any

from word_parser.extraction.table_values.constants import _NIL_STATUS


def json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalar values into standard JSON types."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, str | bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if value == value and value not in {float("inf"), float("-inf")} else None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return json_safe(tolist())
        except (TypeError, ValueError):
            pass
    return str(value)

def row_match_score(text: str, patterns: list[str], *, exact: bool = False) -> int:
    """计算行文本对行选择规则的匹配分。

    完全相等（归一化后）得分最高，避免“90m”这类标签误命中更长文本里的子串。
    """
    normalized_text = normalize_label(text)
    best = 0
    for pattern in patterns:
        normalized_pattern = normalize_label(pattern)
        if not normalized_pattern:
            continue
        numeric_score = numeric_label_match_score(text, normalized_pattern)
        if numeric_score:
            best = max(best, numeric_score)
            continue
        if normalized_text == normalized_pattern:
            best = max(best, 120)
        elif safe_search(pattern, text):
            best = max(best, 100)
        elif not exact and len(normalized_pattern) >= 3 and normalized_pattern in normalized_text:
            best = max(best, 70)
    return best

def numeric_label_match_score(text: str, normalized_pattern: str) -> int:
    """处理 90/90m 这类数字标签，避免命中 0.096 里的字符。"""
    match = re.fullmatch(r"(?P<number>\d+(?:\.\d+)?)(?:m)?", normalized_pattern)
    if not match:
        return 0
    number = re.escape(match.group("number"))
    normalized_text = clean_text(text).lower().replace("米", "m")
    if re.search(rf"(?<![\d.]){number}\s*m?(?![\d.])", normalized_text):
        return 95
    return 0

def column_match_score(column: str, aliases: list[str]) -> int:
    """计算列名对列选择规则的匹配分。

    完全相等（归一化后）得分最高，避免“测风塔”误命中“测风塔配置(m)”这类包含关系。
    """
    normalized_column = normalize_label(column)
    best = 0
    for alias in aliases:
        normalized_alias = normalize_label(alias)
        if not normalized_alias:
            continue
        if normalized_column == normalized_alias:
            best = max(best, 120)
        elif safe_search(alias, column):
            best = max(best, 100)
        elif normalized_alias in normalized_column or normalized_column in normalized_alias:
            best = max(best, 75)
    return best

def clean_text(value: Any) -> str:
    """清理空白和控制字符。"""
    text = "" if value is None else str(value)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return "" if is_placeholder_text(text) else text

def is_placeholder_text(text: str) -> bool:
    """识别表格里表示空值的占位符。"""
    compact = re.sub(r"\s+", "", text)
    return compact in {"-", "--", "—", "——", "/", "\\"}

def safe_search(pattern: str, text: str) -> bool:
    """执行正则匹配，配置不是合法正则时按普通文本处理。"""
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern in text

def extract_value_by_pattern(value: Any, rule: dict[str, Any]) -> Any:
    """按规则从单元格文本中截取目标片段，可组合多个捕获组。"""
    patterns = rule.get("value_patterns") or rule.get("value_pattern")
    if not patterns or not isinstance(value, str):
        return value
    pattern_list = patterns if isinstance(patterns, list) else [patterns]
    for pattern in pattern_list:
        try:
            match = re.search(str(pattern), value, flags=re.IGNORECASE)
        except re.error:
            match = None
        if not match:
            continue
        groups = rule.get("value_groups")
        if groups:
            parts = [clean_text(match.group(int(group))) for group in groups if match.group(int(group)) is not None]
            return str(rule.get("value_join") or "").join(parts)
        if rule.get("value_group") is not None:
            return clean_text(match.group(int(rule.get("value_group"))))
        captured = next((group for group in match.groups() if group is not None), None)
        return clean_text(captured if captured is not None else match.group(0))
    return None

def validate_cell_value(value: Any, value_type: str) -> dict[str, Any]:
    """在输出 OK 前校验单元格值，避免空值或坏数字被当成已抽取。"""
    if value is None or clean_text(value) == "":
        return {"status": _NIL_STATUS, "reason": "value_empty", "message": "目标单元格为空。"}
    if value_type == "number" and parse_number(value) is None:
        return {"status": _NIL_STATUS, "reason": "value_parse_failed", "message": "目标单元格不能解析为数值。"}
    return {"status": "OK"}

def normalize_label(value: Any) -> str:
    """归一化表头、行名，用于宽松匹配。"""
    text = clean_text(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("＃", "#").replace("－", "-").replace("×", "x")
    text = text.replace("m³", "m3").replace("㎡", "m2").replace("²", "2")
    return re.sub(r"[^0-9a-zA-Z#%\u4e00-\u9fa5]+", "", text)

def value_at(row: list[Any], index: int | None) -> Any:
    """安全读取单元格值。"""
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]

def normalize_value(value: Any, value_type: str) -> Any:
    """按配置转换抽取值。"""
    if value_type in {"number", "auto"}:
        number = parse_number(value)
        if number is not None:
            return normalize_number(number)
    return value

def apply_value_conversion(value: Any, conversion: Any) -> Any:
    """按规则声明做轻量单位换算。"""
    if not conversion:
        return value
    conversion_name = str(conversion)
    if conversion_name == "wan_kwh_to_mwh":
        number = parse_number(value)
        if number is None:
            return value
        return normalize_number(number * 10)
    return value

def parse_number(value: Any) -> float | None:
    """从单元格文本中解析数值。"""
    if isinstance(value, int | float):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))

def parse_metric_number(value: Any) -> float | None:
    """\u4e25\u683c\u89e3\u6790\u6307\u6807\u6570\u503c\uff0c\u907f\u514d\u628a\u5854\u53f7\u6216\u8868\u5934\u7f16\u53f7\u5f53\u6210\u6570\u636e\u3002"""
    if isinstance(value, int | float):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text or "#" in text or "\uff03" in text:
        return None
    normalized = text.replace("%", "").strip()
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
        return None
    return float(normalized)

def normalize_number(value: float) -> int | float:
    """把整数型浮点转回 int。"""
    return int(value) if float(value).is_integer() else value

def first_alias(spec: dict[str, Any]) -> str:
    """返回列配置中的首个别名。"""
    aliases = spec.get("aliases") or spec.get("patterns") or []
    return str(aliases[0]) if aliases else str(spec.get("name") or "")
