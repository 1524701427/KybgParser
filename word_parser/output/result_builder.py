"""组合领域规则与结果展示的兼容门面。

现有构建顺序和可变字段优先级保持不变。
"""

from __future__ import annotations

from pathlib import Path

from typing import Any

from word_parser.document.ast.document import DocumentAST

from word_parser.document.ast.evidence import Extraction, FieldEvidence, ParsedField
from word_parser.primary.domain_stage import DomainExtractionState, extract_domain_fields
from word_parser.primary.domain_dispatch import DomainOperatorSchedule
from word_parser.config.domain_regex import validate_domain_literals

from word_parser.config.loader import ConfigLoader

from word_parser.document.cover_ocr import CoverOcrExtractor, CoverOcrResult

from word_parser.primary.normalizer import Normalizer
from word_parser.primary.context_filter import CandidateContextFilter

from word_parser.document.tables import OriginalTableResolver

from word_parser.config.result_schema import ResultSchemaMixin

from word_parser.config.result_defaults import ResultDefaults

from word_parser.output.builder_support.document_support import DocumentSupportMixin

from word_parser.output.builder_support.deterministic_rules import DeterministicRulesMixin

from word_parser.output.presentation import ResultPresentationMixin

from word_parser.domains.generation import GenerationRulesMixin

from word_parser.domains.electrical import ElectricalRulesMixin

from word_parser.domains.civil import CivilRulesMixin

from word_parser.domains.wind_resource import WindResourceRulesMixin

from word_parser.domains.finance import FinanceRulesMixin

from word_parser.domains.investment import InvestmentRulesMixin

from word_parser.domains.project_overview import ProjectOverviewRulesMixin

from word_parser.domains.environment import EnvironmentRulesMixin


class ResultBuilder(
    ResultSchemaMixin,
    ResultDefaults,
    DocumentSupportMixin,
    DeterministicRulesMixin,
    ResultPresentationMixin,
    GenerationRulesMixin,
    ElectricalRulesMixin,
    CivilRulesMixin,
    WindResourceRulesMixin,
    FinanceRulesMixin,
    InvestmentRulesMixin,
    ProjectOverviewRulesMixin,
    EnvironmentRulesMixin,
):
    """通过按职责划分的模块组装相同的业务结果。"""

    def __init__(
        self,
        cover_ocr_extractor: CoverOcrExtractor | None = None,
        output_schema: dict[str, Any] | None = None,
        field_configs: dict[str, dict[str, Any]] | None = None,
        config_root: str | Path = "configs",
        domain_operator_schedule: DomainOperatorSchedule | None = None,
    ):
        self.cover_ocr_extractor = cover_ocr_extractor or CoverOcrExtractor()
        self._cover_ocr_cache: dict[str, CoverOcrResult] = {}
        self.config_root = Path(config_root)
        self.field_configs = field_configs if field_configs is not None else ConfigLoader(self.config_root).load_field_configs()
        self.normalizer = Normalizer(self.field_configs)
        self.context_filter = CandidateContextFilter(self.field_configs)
        schema = output_schema if output_schema is not None else self._load_output_schema(self.config_root)
        self._configure_output_schema(schema or {})
        self.deterministic_rules = ConfigLoader(self.config_root).load_yaml("deterministic_rules.yaml")
        self.domain_operator_schedule = domain_operator_schedule or DomainOperatorSchedule.legacy()
        self.strict_domain_literals = bool(self.deterministic_rules.get("strict_domain_literals", False))
        if self.strict_domain_literals:
            validate_domain_literals(self.deterministic_rules)
        self._merge_field_meta_from_field_configs()
        self.original_table_resolver = OriginalTableResolver(self)

    def prepare(
        self, ast: DocumentAST | None, fields: dict[str, ParsedField],
        file_path: str | None = None,
    ) -> DomainExtractionState:
        """一次抽取后执行领域专用抽取，尚不执行最终映射。"""
        return extract_domain_fields(self, ast, fields, file_path=file_path)

    def build_prepared(self, prepared: DomainExtractionState) -> dict[str, Any]:
        """仅根据已抽取的字段和领域明细组装业务结果，不再次抽值。"""
        ast, fields, details = prepared.ast, prepared.fields, prepared.details
        tables = self._build_tables(ast, details, fields)
        sections = self._build_sections(fields, tables)
        field_traces = self._build_field_traces(fields)
        return {
            "fields": self._build_fields(fields),
            "fieldTraces": field_traces,
            "parsedFields": fields,
            "extractionFields": self._build_extraction_fields(fields),
            "details": details,
            "tables": tables,
            "sections": sections,
        }

    def build(self, ast: DocumentAST | None, fields: dict[str, ParsedField], file_path: str | None = None) -> dict[str, Any]:
        """保留旧 API；内部采用『领域抽取 → 纯结果组装』两步。"""
        return self.build_prepared(self.prepare(ast, fields, file_path=file_path))

    def _apply_detail_context_constraints(self, details: dict[str, list[dict[str, Any]]]) -> None:
        """对明细行直接生成的值应用相同的工程对象规则。"""
        for rows in details.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source = (row.get("_rowSource") or {}).get("source") or {}
                text = source.get("sourceText") or source.get("text") or ""
                if not text:
                    continue
                section = source.get("sectionPath") or []
                if isinstance(section, str):
                    section = [section]
                for code, value in row.items():
                    if value is None or not (self.field_configs.get(code, {}).get("context_constraints")):
                        continue
                    proposed = Extraction(
                        field_code=code, field_name=code, raw_value=str(value), value=value,
                        unit=None, score=1.0, method="detail_row",
                        evidence=FieldEvidence(source_type="table", text=text, section_path=section),
                    )
                    accepted, _ = self.context_filter.filter([proposed])
                    if not accepted:
                        row[code] = None

    def _fill_foundation_equivalent_fields(self, fields: dict[str, ParsedField]) -> None:
        """复用已核实的基础工程量，并根据半径计算直径。"""
        equivalent_fields = {
            "windFoundationExcavationQuantity": "windFoundationEarthworkExcavation",
            "windFoundationBackfillQuantity": "windFoundationEarthworkBackfill",
        }
        for target_code, source_code in equivalent_fields.items():
            target = fields.get(target_code)
            source = fields.get(source_code)
            if (target is not None and target.value is not None) or source is None or source.value is None or source.status != "PASS":
                continue
            name, unit = self.required_field_meta[target_code]
            fields[target_code] = ParsedField(
                field_code=target_code,
                field_name=name,
                value=source.value,
                unit=unit,
                normalized_value=source.value,
                confidence=source.confidence,
                status="PASS",
                evidence=list(source.evidence),
                debug={"resolver": "equivalent_foundation_quantity", "sourceFieldCode": source_code},
            )

        target = fields.get("foundationCapDiameter")
        radius = fields.get("foundationCapBottomRadius")
        if (target is not None and target.value is not None) or radius is None or radius.status != "PASS":
            return
        if not isinstance(radius.value, (int, float)) or isinstance(radius.value, bool):
            return
        diameter = self._clean_number(float(radius.value) * 2)
        name, unit = self.required_field_meta["foundationCapDiameter"]
        evidence = [
            FieldEvidence(
                source_type=item.source_type,
                text=item.text,
                score=item.score,
                block_id=item.block_id,
                table_id=item.table_id,
                page=item.page,
                section_path=list(item.section_path),
                match_method="radius_times_two",
                meta={**item.meta, "calculation": f"{radius.value} × 2 = {diameter}"},
            )
            for item in radius.evidence
        ]
        fields["foundationCapDiameter"] = ParsedField(
            field_code="foundationCapDiameter",
            field_name=name,
            value=diameter,
            unit=unit,
            normalized_value=diameter,
            confidence=radius.confidence,
            status="PASS",
            evidence=evidence,
            debug={"resolver": "radius_times_two", "sourceFieldCode": "foundationCapBottomRadius"},
        )

    def _fill_finance_insurance_equivalent_field(self, fields: dict[str, ParsedField]) -> None:
        """把一次抽取的保险费率同步到同义的财务输出字段。"""
        target = fields.get("financeInsuranceRate")
        source = fields.get("insuranceRate")
        if (target is not None and target.value is not None) or source is None or source.value is None or source.status != "PASS":
            return
        name, unit = self.required_field_meta["financeInsuranceRate"]
        fields["financeInsuranceRate"] = ParsedField(
            field_code="financeInsuranceRate",
            field_name=name,
            value=source.value,
            unit=unit,
            normalized_value=source.value,
            confidence=source.confidence,
            status="PASS",
            evidence=list(source.evidence),
            debug={"resolver": "equivalent_finance_field", "sourceFieldCode": "insuranceRate"},
        )
