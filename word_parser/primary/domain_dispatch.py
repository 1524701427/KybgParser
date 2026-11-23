"""Named Python domain operators invoked by a YAML schedule.

The registry is deliberately allowlisted: YAML can select only known methods
and never imports arbitrary symbols or executes expressions. During legacy-order
compatibility mode, operator order cannot change field precedence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from word_parser.config.loader import ConfigLoader


LEGACY_FIELD_ORDER = (
    "land_field_overrides",
    "drop_combined_detail_only",
    "combined_detail_field_overrides",
    "wind_resource_collection_overrides",
    "road_parameter_overrides",
    "electrical_primary_table_overrides",
    "generation_field_overrides",
    "wind_foundation_table_overrides",
    "finance_field_overrides",
    "earthwork_field_overrides",
    "investment_summary_field_overrides",
    "cover_text_overrides",
    "cover_ocr_overrides",
)
LEGACY_SCALAR_ORDER = (
    "original_scalar_overrides",
    "configured_scalar_overrides",
    "project_overview_values",
    "geology_values",
    "resource_values",
    "environment_values",
    "investment_basis_values",
    "finance_curtailment_values",
    "finance_grid_price_values",
    "finance_text_values",
    "finance_capital_irr_values",
    "finance_table_values",
)


@dataclass(frozen=True)
class DomainOperatorSchedule:
    field_operators: tuple[str, ...]
    scalar_operators: tuple[str, ...]

    @classmethod
    def legacy(cls) -> "DomainOperatorSchedule":
        """Compatibility for direct legacy ResultBuilder constructors."""
        return cls(LEGACY_FIELD_ORDER, LEGACY_SCALAR_ORDER)

    @classmethod
    def from_policy(cls, policy: dict[str, Any]) -> "DomainOperatorSchedule":
        if not isinstance(policy, dict) or policy.get("version") != 1:
            raise ValueError("domain_extraction_pipeline.yaml: version must be 1")
        if policy.get("compatibility_mode") != "legacy_order":
            raise ValueError("domain_extraction_pipeline.yaml: unsupported compatibility mode")
        names = []
        for name, expected in (
            ("field_operators", LEGACY_FIELD_ORDER),
            ("scalar_operators", LEGACY_SCALAR_ORDER),
        ):
            values = policy.get(name)
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"domain_extraction_pipeline.yaml: {name} must be a list of registered names")
            if tuple(values) != expected:
                raise ValueError(
                    f"domain_extraction_pipeline.yaml: {name} must preserve the original "
                    "registered operator precedence until full-report acceptance"
                )
            names.append(tuple(values))
        return cls(*names)


def load_domain_schedule(config_root: str | Path) -> DomainOperatorSchedule:
    # Unlike the legacy lenient loader, this required stage must fail if absent.
    file = Path(config_root) / "domain_extraction_pipeline.yaml"
    if not file.is_file():
        raise FileNotFoundError(f"Required domain extraction policy missing: {file}")
    return DomainOperatorSchedule.from_policy(
        ConfigLoader(config_root).load_yaml("domain_extraction_pipeline.yaml")
    )


def apply_domain_field_operators(
    owner: Any,
    ast: Any,
    fields: dict,
    details: dict,
    *,
    configured_scalar_codes: set[str],
    combined_skip_codes: set[str],
    generation_skip_codes: set[str],
) -> None:
    """Execute approved field operators with exact original call arguments."""
    operations = {
        "land_field_overrides": lambda: owner._apply_land_field_overrides(fields, details),
        "drop_combined_detail_only": lambda: owner._drop_combined_detail_only_field_candidates(fields, skip_codes=combined_skip_codes),
        "combined_detail_field_overrides": lambda: owner._apply_combined_detail_field_overrides(fields, details, skip_codes=combined_skip_codes),
        "wind_resource_collection_overrides": lambda: owner._apply_wind_resource_collection_overrides(ast, fields, details, skip_codes=combined_skip_codes),
        "road_parameter_overrides": lambda: owner._apply_road_parameter_field_overrides(fields, details, skip_codes=combined_skip_codes),
        "electrical_primary_table_overrides": lambda: owner._apply_electrical_primary_table_field_overrides(ast, fields, skip_codes=combined_skip_codes),
        "generation_field_overrides": lambda: owner._apply_generation_field_overrides(ast, fields, skip_codes=generation_skip_codes),
        "wind_foundation_table_overrides": lambda: owner._apply_wind_foundation_table_field_overrides(ast, fields, skip_codes=combined_skip_codes),
        "finance_field_overrides": lambda: owner._apply_finance_field_overrides(ast, fields, skip_codes=configured_scalar_codes),
        "earthwork_field_overrides": lambda: owner._apply_earthwork_field_overrides(ast, fields, skip_codes=configured_scalar_codes),
        "investment_summary_field_overrides": lambda: owner._apply_investment_summary_field_overrides(ast, fields, skip_codes=configured_scalar_codes),
        "cover_text_overrides": lambda: owner._apply_cover_text_overrides(ast, fields),
        "cover_ocr_overrides": lambda: owner._apply_cover_ocr_overrides(ast, fields),
    }
    schedule = getattr(owner, "domain_operator_schedule", None) or DomainOperatorSchedule.legacy()
    for name in schedule.field_operators:
        operations[name]()


def collect_domain_scalar_overrides(
    owner: Any,
    ast: Any,
    configured_scalar_overrides: dict,
    configured_scalar_codes: set[str],
) -> dict:
    """Preserve left-to-right dictionary update priority across domain scalars."""
    operations = {
        "original_scalar_overrides": lambda: owner._extract_scalar_overrides(ast, skip_codes=configured_scalar_codes),
        "configured_scalar_overrides": lambda: configured_scalar_overrides,
        "project_overview_values": lambda: owner._common_project_overview_scalar_override_values(ast),
        "geology_values": lambda: owner._geology_scalar_override_values(ast),
        "resource_values": lambda: owner._resource_scalar_override_values(ast),
        "environment_values": lambda: owner._environmental_water_conservation_scalar_values(ast, skip_codes=configured_scalar_codes),
        "investment_basis_values": lambda: owner._investment_basis_scalar_values(ast, skip_codes=configured_scalar_codes),
        "finance_curtailment_values": lambda: owner._finance_curtailment_scalar_values(ast, skip_codes=configured_scalar_codes),
        "finance_grid_price_values": lambda: owner._finance_grid_price_scalar_values(ast, skip_codes=configured_scalar_codes),
        "finance_text_values": lambda: owner._finance_text_scalar_override_values(ast, skip_codes=configured_scalar_codes),
        "finance_capital_irr_values": lambda: owner._finance_capital_irr_scalar_values(ast, skip_codes=configured_scalar_codes),
        "finance_table_values": lambda: owner._finance_table_scalar_override_values(ast, skip_codes=configured_scalar_codes),
    }
    schedule = getattr(owner, "domain_operator_schedule", None) or DomainOperatorSchedule.legacy()
    combined: dict = {}
    for name in schedule.scalar_operators:
        combined.update(operations[name]())
    return combined
