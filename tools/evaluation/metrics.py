from __future__ import annotations

import re


class FieldMetrics:
    """Field-level evaluation metrics."""

    def calculate(self, predictions: list[dict], golden: list[dict]) -> dict:
        if not golden:
            return {
                "precision": 0.0,
                "recall": 0.0,
                "exact_match": 0.0,
                "value_accuracy": 0.0,
                "unit_accuracy": 0.0,
            }

        golden_map = self._index_by_key(golden)
        prediction_map = self._index_by_key(predictions)
        matched_keys = sorted(golden_map.keys() & prediction_map.keys())

        exact_matches = 0
        value_matches = 0
        unit_matches = 0
        for key in matched_keys:
            golden_item = golden_map[key]
            prediction_item = prediction_map[key]
            if self._canonical_value(prediction_item) == self._canonical_value(golden_item):
                value_matches += 1
            if self._canonical_unit(prediction_item) == self._canonical_unit(golden_item):
                unit_matches += 1
            if (
                self._canonical_value(prediction_item) == self._canonical_value(golden_item)
                and self._canonical_unit(prediction_item) == self._canonical_unit(golden_item)
            ):
                exact_matches += 1

        precision = exact_matches / len(prediction_map) if prediction_map else 0.0
        recall = exact_matches / len(golden_map) if golden_map else 0.0
        exact_match = exact_matches / len(matched_keys) if matched_keys else 0.0
        value_accuracy = value_matches / len(matched_keys) if matched_keys else 0.0
        unit_accuracy = unit_matches / len(matched_keys) if matched_keys else 0.0
        return {
            "precision": precision,
            "recall": recall,
            "exact_match": exact_match,
            "value_accuracy": value_accuracy,
            "unit_accuracy": unit_accuracy,
        }

    def _index_by_key(self, items: list[dict]) -> dict[tuple[str | None, str | None], dict]:
        return {(item.get("file"), item.get("field_code")): item for item in items}

    def _canonical_value(self, item: dict):
        value = item.get("normalized_value", item.get("value"))
        return self._canonical_scalar(value)

    def _canonical_unit(self, item: dict):
        unit = item.get("unit")
        if unit is None:
            return None
        return str(unit).strip()

    def _canonical_scalar(self, value):
        if value is None:
            return None
        if isinstance(value, list):
            return tuple(self._canonical_scalar(item) for item in value)
        if isinstance(value, (int, float)):
            numeric = float(value)
            return int(numeric) if numeric.is_integer() else round(numeric, 10)
        text = str(value).strip()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
            numeric = float(text)
            return int(numeric) if numeric.is_integer() else round(numeric, 10)
        return text
