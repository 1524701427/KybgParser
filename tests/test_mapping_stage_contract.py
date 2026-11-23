"""Mapping is executed *after* secondary extraction with a safe publish boundary."""
import json
from pathlib import Path

import pytest
import yaml

import word_parser.mapping.stage as mapping_stage
from word_parser.secondary.stage import enhance_primary_result


ROOT = Path(__file__).resolve().parents[1]


def _config_root(tmp_path):
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "mapping_pipeline.yaml").write_text(
        (ROOT / "configs" / "mapping_pipeline.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return cfg


def test_mapping_yaml_is_strict_and_has_no_unknown_operator(tmp_path):
    cfg = _config_root(tmp_path)
    assert mapping_stage.load_mapping_operators(cfg) == mapping_stage.LEGACY_OPERATOR_ORDER
    file = cfg / "mapping_pipeline.yaml"
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    data["operators"] = list(reversed(data["operators"]))
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="operator order"):
        mapping_stage.load_mapping_operators(cfg)
    data["operators"] = ["unknown_operator"]
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="operator order"):
        mapping_stage.load_mapping_operators(cfg)


def _fixture(tmp_path, monkeypatch, *, fail_at=None):
    cfg = _config_root(tmp_path)
    destination = tmp_path / "final"
    destination.mkdir()
    outputs = {key: str(destination / f"case_{key}.json")
               for key in ("detail", "result", "mapped")}
    for key in ("detail", "result", "mapped"):
        initial = ({"sentinel": "old", "fieldIndex": {"hubHeight": {"value": 120}}}
                   if key == "detail" else {"sentinel": "old"})
        Path(outputs[key]).write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    original_contents = {key: Path(path).read_bytes() for key, path in outputs.items()}
    parse_result = {"result": {"sections": []}, "mapped": {},
                    "outputFiles": dict(outputs)}
    enhanced = {"sections": []}

    monkeypatch.setattr(mapping_stage, "table_value_details", lambda data: {"filePath": "case.docx", "sections": []})
    monkeypatch.setattr(mapping_stage, "final_result_with_table_values", lambda data: {"sections": [{"name": "工程概况", "fields": [], "tables": []}]})
    def initial_projection(path, config_root=None):
        detail = json.loads(Path(path).read_text(encoding="utf-8"))
        assert detail["fieldIndex"]["hubHeight"]["value"] == 120
        assert detail["tableValueExtraction"]["filePath"] == "case.docx"
        return {"${hubHeight}": 120}
    monkeypatch.setattr(mapping_stage, "mapping_from_details", initial_projection)
    events = []
    def register(name):
        def run(result, table_result, config_root):
            assert str(result["outputFiles"]["mapped"]) != outputs["mapped"]
            assert Path(result["outputFiles"]["detail"]).is_file()
            events.append(name)
            result["result"] = {"sections": [{"name": "工程概况", "fields": [], "tables": []}]}
            result["mapped"][name] = len(events)
            Path(result["outputFiles"]["detail"]).write_text(
                json.dumps({"operator": name}, ensure_ascii=False), encoding="utf-8")
            if name == fail_at:
                raise ValueError("injected mapping failure")
        return run
    monkeypatch.setattr(mapping_stage, "_operators", lambda: {
        name: register(name) for name in mapping_stage.LEGACY_OPERATOR_ORDER
    })
    return cfg, parse_result, enhanced, original_contents, events


def test_all_mapping_operators_run_in_yaml_order_and_publish_once(tmp_path, monkeypatch):
    cfg, result, enhanced, original, events = _fixture(tmp_path, monkeypatch)
    dest = result["outputFiles"].copy()
    mapping_stage.execute_final_mapping(result, enhanced, config_root=cfg)
    assert events == list(mapping_stage.LEGACY_OPERATOR_ORDER)
    assert result["outputFiles"] == dest
    assert Path(dest["detail"]).read_text(encoding="utf-8").find('"operator"') >= 0
    mapped = json.loads(Path(dest["mapped"]).read_text(encoding="utf-8"))
    assert mapped["${hubHeight}"] == 120
    assert mapped[mapping_stage.LEGACY_OPERATOR_ORDER[-1]] == len(events)
    assert not list(Path(dest["result"]).parent.glob(".kybg-final-mapping-*"))


def test_mapping_failure_keeps_prior_formal_outputs_unchanged(tmp_path, monkeypatch):
    cfg, result, enhanced, old, events = _fixture(tmp_path, monkeypatch, fail_at="align_combined_tables")
    dest = result["outputFiles"].copy()
    with pytest.raises(ValueError, match="injected mapping failure"):
        mapping_stage.execute_final_mapping(result, enhanced, config_root=cfg)
    assert result["outputFiles"] == dest
    assert events[-1] == "align_combined_tables"
    for key, path in dest.items():
        assert Path(path).read_bytes() == old[key]
    assert not list(Path(dest["result"]).parent.glob(".kybg-final-mapping-*"))


def test_secondary_write_outputs_false_is_pure_memory(tmp_path, monkeypatch):
    import word_parser.secondary.stage as secondary_stage
    result_path = tmp_path / "case_result.json"
    result_path.write_text('{"original":"untouched"}', encoding="utf-8")
    original = result_path.read_bytes()
    class FakeResolver:
        @staticmethod
        def from_config_file(config_path):
            return FakeResolver()
        def enhance_result(self, value):
            assert value == {"sections": []}
            return {"sections": [{"name": "电气", "tableFields": []}]}
    monkeypatch.setattr(secondary_stage, "TableValueResolver", FakeResolver)
    monkeypatch.setattr(secondary_stage, "final_result_with_table_values", lambda x: {"sections": []})
    monkeypatch.setattr(secondary_stage, "json_safe", lambda x: x)
    parsed = {"result": {"sections": []}, "outputFiles": {"result": str(result_path)}}
    enhanced = enhance_primary_result(parsed, "unused.yaml", write_outputs=False)
    assert enhanced["sections"][0]["name"] == "电气"
    assert result_path.read_bytes() == original
    assert not list(tmp_path.glob("*table_values*.json"))


def test_run_full_parse_reuses_factory_config_for_secondary_and_mapping(monkeypatch, tmp_path):
    import word_parser.application.workflow as workflow
    custom = tmp_path / "custom_rules"
    custom.mkdir()
    class DummyPipeline:
        exporter = type("Exporter", (), {
            "result_builder": type("Builder", (), {"config_root": custom})()
        })()
        def parse(self, file_path, defer_mapping=False):
            assert defer_mapping is True
            return {"outputFiles": {"result": str(tmp_path / "case_result.json")}}
    parser = type("Parser", (), {"pipeline": DummyPipeline()})()
    observed = {}
    def fake_enhance(data, config_path=None, config_root=None):
        observed.update(root=config_root, table=config_path)
        return {"ok": True}
    monkeypatch.setattr(workflow, "enhance_parse_result", fake_enhance)
    assert workflow.run_full_parse(parser, "case.docx") == {"ok": True}
    assert observed == {
        "root": custom,
        "table": custom / "table_field_extractors.yaml",
    }
