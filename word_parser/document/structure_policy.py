"""文档结构规则加载与校验；生产工厂与独立解析器共用同一份 YAML。"""
from pathlib import Path
import re
from word_parser.config.loader import ConfigLoader


def load_structure_policy(config=None):
    if config is None:
        config = ConfigLoader(Path(__file__).resolve().parents[2] / "configs").load_required_yaml("document_structure.yaml")
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("document_structure.yaml: version must be 1")
    def strings(value, name):
        if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value):
            raise ValueError(f"document_structure.yaml: {name} must be a nonempty string list")
        return value
    def patterns(values, name):
        for value in strings(values, name):
            re.compile(value)
    heading, table, diagnostics = (config[key] for key in ("heading", "table_title", "diagnostics"))
    patterns(heading["patterns"], "heading.patterns")
    for key in ("style_contains", "additional_style_contains"):
        strings(heading[key], key)
    for key in ("style_level_pattern", "toc_style_pattern", "toc_text_pattern"):
        re.compile(heading[key])
    for key in ("numbered_max_length", "bold_max_length", "bold_level", "max_numbered_level"):
        if type(heading[key]) is not int or heading[key] <= 0:
            raise ValueError(f"document_structure.yaml: invalid {key}")
    for key in ("enhanced_styles", "toc_exclusion"):
        if type(heading[key]) is not bool:
            raise ValueError(f"document_structure.yaml: {key} must be boolean")
    for key in ("keywords", "body_hints"):
        strings(table[key], key)
    patterns(table["caption_patterns"], "table_title.caption_patterns")
    if type(table["lookback_blocks"]) is not int or table["lookback_blocks"] <= 0:
        raise ValueError("document_structure.yaml: invalid lookback_blocks")
    if type(table["minimum_score"]) not in (int, float) or table["minimum_score"] < 0:
        raise ValueError("document_structure.yaml: invalid minimum_score")
    re.compile(config["figure_caption_pattern"])
    seen = set()
    for rule in config["table_section_rules"]:
        section = rule["section"]
        if not isinstance(section, str) or not section or section in seen:
            raise ValueError("document_structure.yaml: invalid or duplicate table section")
        seen.add(section)
        patterns(rule["patterns"], section)
    if diagnostics["mode"] not in ("audit", "strict", "off") or type(diagnostics["include_text"]) is not bool:
        raise ValueError("document_structure.yaml: invalid diagnostics settings")
    recovery = config.get("table_recovery")
    if not isinstance(recovery, dict) or type(recovery.get("enabled")) is not bool:
        raise ValueError("document_structure.yaml: invalid table_recovery")
    for key in ("max_columns", "max_expanded_cells"):
        if type(recovery.get(key)) is not int or recovery[key] <= 0:
            raise ValueError(f"document_structure.yaml: invalid {key}")
    continuation = recovery["continuation"]
    if type(continuation.get("enabled")) is not bool:
        raise ValueError("document_structure.yaml: invalid continuation.enabled")
    for key in ("max_order_gap", "max_page_gap", "min_header_matches"):
        if type(continuation.get(key)) is not int or continuation[key] <= 0:
            raise ValueError(f"document_structure.yaml: invalid {key}")
    re.compile(continuation["continuation_pattern"])
    strings(continuation["header_labels"], "continuation.header_labels")
    return config
