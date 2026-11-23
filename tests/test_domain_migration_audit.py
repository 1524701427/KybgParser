"""Prevent overclaiming that domain Python rules have all been migrated."""
from pathlib import Path
from tools.scripts.audit_domain_migration import audit, inspect_file, format_markdown


ROOT = Path(__file__).resolve().parents[1]


def test_domain_audit_covers_every_domain_python_module():
    report = audit(ROOT)
    files = sorted(p for p in (ROOT / "word_parser" / "domains").glob("*.py")
                   if p.name != "__init__.py")
    assert len(report["modules"]) == len(files)
    assert report["totals"]["module_count"] == len(files)
    assert report["totals"]["module_count"] >= 15
    assert report["totals"]["modules_with_direct_regex"] > 0
    assert report["totals"]["modules_with_yaml_hooks"] > 0
    assert "YAML" in format_markdown(report)


def test_domain_audit_distinguishes_regex_alias_and_config_hook(tmp_path):
    folder = tmp_path / "word_parser" / "domains"
    folder.mkdir(parents=True)
    source = folder / "test_domain.py"
    source.write_text(
        'import re\n'
        'class Example:\n'
        '    def x(self, text, matrix):\n'
        '        m = re.search(r"\\d+", text)\n'
        '        a = self._value_by_row_label(matrix, ["道路长度"])\n'
        '        p = self._configured_patterns({}, "road", [r"道路\\s+长度"])\n'
        '        return m, a, p\n', encoding="utf-8"
    )
    report = inspect_file(source, tmp_path)
    assert len(report["direct_regex"]) == 1
    assert len(report["alias_helper"]) == 1
    assert len(report["yaml_hook"]) == 1
    assert report["regex_like_literals"] >= 2
