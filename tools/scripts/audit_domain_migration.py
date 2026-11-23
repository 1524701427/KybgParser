"""Inventory extraction calls in all domain Python modules (not proof of migration)."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import re

RE_METHODS = {"search", "match", "fullmatch", "findall", "finditer", "compile", "split", "sub", "subn"}
PATTERN_HELPERS = {"_first_number_after_pattern", "_last_number_after_pattern",
                   "_first_matching_number", "_first_matching_text",
                   "_original_captioned_table_by_regex_from_document"}
ALIAS_HELPERS = {"_cell_at_alias", "_find_header_index", "_value_by_row_label",
                 "_text_by_row_label", "_unit_by_row_label"}
CONFIG_HOOKS = {"_configured_patterns", "_configured_field_rules", "_deterministic_rule_section",
                "_configured_text_blocks", "_value_from_configured_patterns"}
REGEX_FEATURES = re.compile(r"\\[dDsSwWbB]|\\u[0-9a-fA-F]{4}|\(\?:|\(\?P<|\[[^]]{1,60}\]|\{\d+(?:,\d*)?\}")


def _strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [value for part in node.elts for value in _strings(part)]
    if isinstance(node, ast.Dict):
        return [value for part in node.values for value in _strings(part)]
    return []


def inspect_file(path: Path, root: Path) -> dict:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    result = {"file": str(path.relative_to(root)).replace("\\", "/"),
              "lines": len(source.splitlines()), "direct_regex": [],
              "regex_helper": [], "alias_helper": [], "yaml_hook": [],
              "regex_like_literals": 0}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            result["regex_like_literals"] += bool(REGEX_FEATURES.search(node.value))
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not isinstance(f, ast.Attribute):
            continue
        name = f.attr
        base = f.value.id if isinstance(f.value, ast.Name) else None
        entry = {"line": node.lineno, "method": name}
        if base == "re" and name in RE_METHODS and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            result["direct_regex"].append(entry)
        if name in PATTERN_HELPERS and any(REGEX_FEATURES.search(s) for arg in node.args for s in _strings(arg)):
            result["regex_helper"].append(entry)
        if name in ALIAS_HELPERS and any(re.search(r"[\u3400-\u9fff]", s) for arg in node.args for s in _strings(arg)):
            result["alias_helper"].append(entry)
        if name in CONFIG_HOOKS:
            result["yaml_hook"].append(entry)
    return result


def audit(root: Path) -> dict:
    root = root.resolve()
    domain_dir = root / "word_parser" / "domains"
    if not domain_dir.is_dir():
        raise FileNotFoundError(f"Missing domain directory: {domain_dir}")
    entries = [inspect_file(p, root) for p in sorted(domain_dir.glob("*.py"))
               if p.name != "__init__.py"]
    keys = ("direct_regex", "regex_helper", "alias_helper", "yaml_hook")
    totals = {
        "module_count": len(entries),
        "modules_with_direct_regex": sum(bool(e["direct_regex"]) for e in entries),
        "modules_with_yaml_hooks": sum(bool(e["yaml_hook"]) for e in entries),
        "regex_like_python_literals": sum(e["regex_like_literals"] for e in entries),
    }
    totals.update({key + "_calls": sum(len(e[key]) for e in entries) for key in keys})
    return {
        "version": 1,
        "scope": "word_parser/domains/*.py, excluding __init__.py",
        "interpretation": "Counts of AST call sites, not distinct business fields. Some Python regex literals are intentional YAML compatibility fallbacks. Manual review is required.",
        "totals": totals,
        "modules": entries,
    }


def format_markdown(report: dict) -> str:
    lines = [
        "# KybgParser 领域抽取规则静态审计", "",
        "扫描所有领域 Python 模块。数字为代码调用点，不等于字段或需迁移规则数。",
        "Python 中保留兼容兜底正则并不自动意味着缺少 YAML 配置。",
        "",
        "| 文件 | 直接 re 正则 | 正则辅助方法 | 字段别名辅助方法 | YAML 配置入口 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["modules"]:
        lines.append(
            f"| {Path(item['file']).name} | {len(item['direct_regex'])} | "
            f"{len(item['regex_helper'])} | {len(item['alias_helper'])} | "
            f"{len(item['yaml_hook'])} |"
        )
    lines.extend(["", "汇总统计：" + json.dumps(report["totals"], ensure_ascii=False),
                  "", "结论：只要存在未核对的直接调用点，就不能认定所有领域规则已完整迁入 YAML。",
                  "完整交付还需要同一运行环境下的真实报告新旧值与表格一致性验证。", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Static audit of domain extraction rules")
    cli.add_argument("--root", type=Path, default=Path("."))
    cli.add_argument("--json-out", type=Path)
    cli.add_argument("--markdown-out", type=Path)
    args = cli.parse_args(argv)
    report = audit(args.root)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(format_markdown(report), encoding="utf-8")
    print(json.dumps(report["totals"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
