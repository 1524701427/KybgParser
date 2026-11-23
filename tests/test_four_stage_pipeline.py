"""Explicit four-stage execution: discovery -> primary/domain -> secondary -> mapping.

Primary domain methods must finish before serialization; prepared assembly
must never run extraction twice or mutate already selected fields.
"""
from types import SimpleNamespace

from word_parser.application.pipeline import ParserPipeline
from word_parser.document.ast.evidence import ParsedField
from word_parser.output.result_builder import ResultBuilder
from word_parser.primary.domain_stage import DomainExtractionState, extract_domain_fields


def test_domain_stage_preserves_original_method_order_and_input_fields():
    events = []
    ast = SimpleNamespace(meta={})
    original = {"installedCapacity": ParsedField(field_code="installedCapacity", field_name="装机容量", value=200)}
    class Builder:
        def _build_details(self, ast): events.append("details"); return {"tables": []}
        def _apply_detail_context_constraints(self, details): events.append("detail_constraints")
        def _apply_deterministic_overrides(self, ast, fields, details):
            events.append("domain_rules")
            fields["hubHeight"] = ParsedField(field_code="hubHeight", field_name="轮毂高度", value=120)
        def _apply_quality_filters(self, fields, ast): events.append("quality")
        def _fill_foundation_equivalent_fields(self, fields): events.append("foundation")
        def _fill_finance_insurance_equivalent_field(self, fields): events.append("finance")
    prepared = extract_domain_fields(Builder(), ast, original, file_path="test.docx")
    assert events == ["details", "detail_constraints", "domain_rules", "quality", "foundation", "finance"]
    assert "hubHeight" not in original
    assert prepared.fields["hubHeight"].value == 120
    assert prepared.ast is ast
    assert ast.meta["file_path"] == "test.docx"


def test_prepared_result_assembly_never_runs_domain_extraction(monkeypatch):
    builder = ResultBuilder.__new__(ResultBuilder)
    monkeypatch.setattr(builder, "_build_tables", lambda ast, details, fields: {"table": {"data": [[1]]}})
    monkeypatch.setattr(builder, "_build_sections", lambda fields, tables: [{"name": "工程概况", "fields": [], "tables": []}])
    monkeypatch.setattr(builder, "_build_field_traces", lambda fields: {"hubHeight": {"value": 120}})
    monkeypatch.setattr(builder, "_build_fields", lambda fields: {"hubHeight": {"value": 120}})
    monkeypatch.setattr(builder, "_build_extraction_fields", lambda fields: [])
    monkeypatch.setattr(builder, "_apply_deterministic_overrides", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("domain extraction must not run in result assembly")))
    fields = {"hubHeight": ParsedField(field_code="hubHeight", field_name="轮毂高度", value=120)}
    prepared = DomainExtractionState(ast=None, fields=fields, details={"d": []})
    result = builder.build_prepared(prepared)
    assert result["parsedFields"] is fields
    assert result["fields"]["hubHeight"]["value"] == 120
    assert result["tables"]["table"]["data"] == [[1]]


def test_pipeline_runs_domain_after_primary_before_export(monkeypatch):
    import word_parser.application.pipeline as module
    events = []
    monkeypatch.setattr(module, "read_document", lambda parser, ctx: events.append("read"))
    monkeypatch.setattr(module, "discover_indicators", lambda parser, ctx: events.append("pre") or [])
    monkeypatch.setattr(module, "extract_primary_fields", lambda parser, ctx, indicators: events.append("primary"))
    class Builder:
        def prepare(self, ast, validated, file_path=None):
            events.append("domain")
            return DomainExtractionState(ast, {}, {})
    class Exporter:
        result_builder = Builder()
        def export(self, ctx, *, defer_mapping=False, prepared=None):
            events.append("export")
            assert prepared is not None
            assert defer_mapping
            return {"mapped": {}, "result": {}}
    pipeline = ParserPipeline(
        loader=None, structure_parser=None, section_detector=None,
        candidate_retriever=None, field_matcher=None, value_extractor=None,
        funnel_pruner=None, normalizer=None, semantic_analyzer=None, resolver=None,
        validator=None, exporter=Exporter(),
    )
    assert pipeline.parse("test.docx", defer_mapping=True)["mapped"] == {}
    assert events == ["read", "pre", "primary", "domain", "export"]


def test_parser_service_exposes_explicit_full_four_stage_api(monkeypatch):
    from word_parser.application.service import ParserService
    import word_parser.application.workflow as workflow
    seen = {}
    def run(parser, path, config_root=None, table_value_config=None):
        seen.update(parser=parser, path=path, root=config_root, table=table_value_config)
        return {"stages": ["pre", "primary", "secondary", "mapping"]}
    monkeypatch.setattr(workflow, "run_full_parse", run)
    service = ParserService(pipeline=object())
    result = service.parse_full("wind_farm.docx", config_root="configs/project")
    assert result["stages"] == ["pre", "primary", "secondary", "mapping"]
    assert seen == {
        "parser": service, "path": "wind_farm.docx", "root": "configs/project", "table": None
    }
