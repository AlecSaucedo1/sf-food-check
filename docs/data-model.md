# SF Food Check data model

## Design principle

The product must keep three layers distinct:

1. **Official outcome** — the SFDPH Pass / Conditional Pass / Closure result and structured inspection metadata.
2. **Official narrative** — verbatim inspector comments / corrective-action text associated with the full inspection report.
3. **Consumer interpretation** — a separate category and plain-language explanation that never replaces the official text.

## Tables

### `inspections`
One row per inspection event. The normalized primary key uses the upstream row identifier when available. Raw upstream JSON is retained in `raw_json` for audit/reprocessing.

Key fields: permit number, DBA, address, coordinates, neighborhood, inspection date/type, inspector, permit type, status, violation count/codes, source notes, source refresh timestamp.

### `report_enrichment`
One record per permit number + inspection date containing an official report URL, inspector narrative, corrective action, source label, and provenance type.

This is deliberately separate because the live DataSF note fields can be empty while the official MyHealthDepartment printable report contains narrative text.

### `violations`
Optional detail rows attached to an inspection: official code/description, normalized category, consumer explanation, risk label, and violation-level comment when supported by the source.

## Provenance rules

- Never label generated or inferred text as an inspector comment.
- Never overwrite `official_description` with a consumer rewrite.
- `comment_source=demo` must always be visibly labeled as demonstration content.
- Production official imports should use `comment_source=manual_official` or a future audited source adapter.
- Keep the official report URL whenever available.
