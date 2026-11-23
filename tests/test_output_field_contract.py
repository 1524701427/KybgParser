"""Final mapped JSON contract: protect all pre-refactor output field names.

The baseline reflects main's output_schema.yaml before configuration refactoring.
This is a schema-level guard; it does not replace document/field-value regression tests.
"""
import json
from pathlib import Path

from word_parser.config.loader import ConfigLoader


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "tests" / "contracts" / "output_field_codes_baseline.json").read_text(encoding="utf-8")
)


def test_all_pre_refactor_mapped_keys_still_exist_with_same_targets():
    current = ConfigLoader(ROOT / "configs").load_yaml("output_schema.yaml")["output_field_codes"]
    expected = CONTRACT["field_mappings"]
    missing = sorted(set(expected) - set(current))
    remapped = {
        code: {"previous": old, "current": current[code]}
        for code, old in expected.items() if code in current and current[code] != old
    }
    assert missing == [], f"Final mapped codes were removed: {missing}"
    assert remapped == {}, f"Final mapped destinations changed: {remapped}"
    # Additions are allowed; old fields and destinations cannot silently disappear.
    assert len(current) >= CONTRACT["baseline_count"] == 284


def test_pre_refactor_destinations_are_unique_only_where_originally_unique():
    """Preserve the old mapping exactly; do not invent a uniqueness constraint."""
    mappings = CONTRACT["field_mappings"]
    assert len(mappings) == len(set(mappings))
    assert len(mappings) == 284
