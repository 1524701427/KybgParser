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
- ValueExtractor value/unit/noise table-header vocabularies
- CandidateResolver candidate-method weights
- Normalizer unit aliases: the same 37 entries as the existing Python dictionary

Constructor defaults remain backward compatible. The committed YAML values reproduce the old Python defaults.

## Required test gates before merging
1. python -m pytest tests/test_config_driven_parity.py -q
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
