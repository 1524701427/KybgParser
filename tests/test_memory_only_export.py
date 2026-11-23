"""Full four-stage parse must not expose partially written primary JSON."""
from pathlib import Path
from types import SimpleNamespace

from word_parser.output.json_exporter import JsonExporter


def test_memory_only_export_does_not_write_primary_files(tmp_path, monkeypatch):
    class Builder:
        def build_prepared(self, prepared):
            return {"sections": [{"name": "通用", "fields": [], "tables": []}]}
    exporter = JsonExporter(result_builder=Builder(), output_dir=tmp_path)
    ctx = SimpleNamespace(file_path="wind_farm.docx", result=None)
    monkeypatch.setattr(exporter, "_build_detail_json", lambda ctx, built: {
        "fieldIndex": {"installedCapacity": {"value": 200}},
        "tableIndex": {}, "filePath": "wind_farm.docx",
    })
    monkeypatch.setattr(exporter, "_build_result_json", lambda ctx: ctx.result)
    def forbidden(*args, **kwargs):
        raise AssertionError("primary interim export should never write files")
    monkeypatch.setattr(exporter, "_write_output_files", forbidden)

    result = exporter.export(ctx, defer_mapping=True, prepared=object(), memory_only=True)
    assert result["mapped"] == {}
    assert result["_primary_detail"]["fieldIndex"]["installedCapacity"]["value"] == 200
    assert result["outputFiles"]["mapped"].endswith("_mapped.json")
    assert not list(tmp_path.glob("*.json"))
