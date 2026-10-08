# Word Parser Module Layout

This package is the simplified public structure for the parser.

```text
word_parser/
  document/     Word/PDF loading, layout parsing and the unified document model
  extraction/   YAML-driven extraction, original tables, table values and OCR fallback
  output/       result.json, details.json and fields.json builders
  core/         pipeline, configuration and public service API
```

The old `parser_engine` package is still present as a compatibility layer while
the codebase migrates. New imports should use `word_parser.*`; existing imports
continue to work so business extraction logic is not changed during this
structural refactor.
