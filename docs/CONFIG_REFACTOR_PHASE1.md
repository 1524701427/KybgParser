# KybgParser config-driven refactor: phase 1 (compatibility first)

## Boundaries that remain unchanged
- PDF/Word parsing and cover OCR
- ResultBuilder and JsonExporter
- output_schema.yaml and existing mapped JSON structure
- domain modules, deterministic rules, and secondary table extractor
- all existing field codes and field YAML definitions

## What now comes from configs/extraction_runtime.yaml
- FieldMatcher exact alias bonus
- RapidFuzz acceptance score and minimum distance to competing fields
- minimum label length for safe fuzzy correction
- indicator discovery stop labels, column-header exclusions, scope terms, contextual value expression
- ValueExtractor value/unit/noise table-header vocabularies, summary rows, raw unit headers, material-grade exclusion pattern
- IndicatorValueParser paragraph delimiters and length limits
- CandidateResolver candidate-method weights
- Normalizer unit aliases: the same 37 entries as the existing Python dictionary

Secondary table extraction operations are now dispatched through an explicit registry, preserving existing YAML operations and the former implementations.

Constructor defaults remain backward compatible. The committed YAML values reproduce the old Python defaults.

## Configuration audit

Run `python tools/scripts/audit_extraction_config.py --config-root configs`. The audit validates YAML policy, regular expressions, numeric thresholds, and detects duplicate field codes. By default duplicate field codes remain warnings to preserve legacy behavior; `--strict-duplicates` makes them errors. This tool is read-only and does not modify field values or output.

The GitHub Actions PR workflow runs this audit and the lightweight rule/mapping comparator tests.

## Required test gates before merging
1. `python -m pytest tests/test_extraction_config_audit.py tests/test_config_driven_parity.py tests/test_mapped_parity_tool.py -q`
2. Run the complete pytest suite in the real OCR/Aspose runtime.
3. Generate old and new mapped JSON using the same real documents, runtime and configuration.
4. python tools/scripts/compare_mapped.py old_mapped.json new_mapped.json --report mapping_diff.json
5. Review every reported loss, value/type change, table change or schema change. Differences must be fixed or explicitly approved.

NOTE: Static parity tests are not evidence that every report still extracts correctly. Do not merge without real-report comparison.

## Remaining work (not yet migrated)
- shared FieldRegistry and cached DocumentIndex
- unified operator registry and validator for YAML field rules
- one-at-a-time domain matching-rule migration, with conservative legacy fallback
- convergence of primary and secondary candidate decisions, only after full business parity
- do not turn calculations or complex tabular algorithms into arbitrary YAML expressions; retain Python as tested operators

## Existing duplicate field definitions found by audit

The read-only audit found **212 effective field codes**, **0 errors**, and **2 duplicate-code warnings** on the current configuration:

- `newRoadLength`: defined in `configs/fields/civil_construction.yaml` and `configs/fields/report_required_data.yaml`
- `rebuiltRoadLength`: defined in the same two files

These are not identical definitions: `report_required_data.yaml` adds more aliases and scalar extraction rules. The current ConfigLoader deliberately retains the sorted-file, last-definition-wins behavior. Neither definition is removed or merged in this PR. Any reconciliation needs mapped-JSON and real-report parity before deployment.
