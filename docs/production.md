# Production path

## Current MVP

- Mobile-first responsive web UI and installable PWA shell.
- FastAPI application and SQLite persistence for a self-contained prototype.
- DataSF ingestion adapter for dataset `tvy3-wexg`.
- Flexible normalization layer because upstream human/API field labels can change.
- Restaurant search, status filters, recent list, nearby distance sort, approximate map view, restaurant profiles, inspection timeline, violations, comments, corrective actions, official source links.
- Verbatim-comment enrichment table plus CSV/JSON import utility.

## Live SFDPH data

Run:

```bash
python scripts/sync_datasf.py --reset --save-raw data/datasf_snapshot.json
USE_LIVE_DATA=1 uvicorn app:app --host 0.0.0.0 --port 8000
```

Use a free Socrata app token in `SOCRATA_APP_TOKEN` for higher rate limits when appropriate.

## Inspector comments

The structured open-data dataset documents inspection/suspension note fields, but current observations indicate those fields are empty. Full narrative appears in the separate MyHealthDepartment report layer. Automated retrieval of the report pages must not be treated as complete until a stable, permitted integration is verified.

Until then, backfill verified report URLs and verbatim comments using:

```bash
python scripts/import_comments.py data/comments_import_template.csv
```

The UI clearly distinguishes an unlinked narrative, demo narrative, and official report enrichment.

## Next production upgrades

1. PostgreSQL + PostGIS instead of SQLite.
2. Scheduled ingestion job (monthly source sync plus daily health check for source changes).
3. Server-side full-text/trigram search and geospatial queries.
4. Stable official-report enrichment adapter after SFDPH/MyHealthDepartment access method is confirmed.
5. Violation-code dictionary sourced from official SF documentation, then taxonomy versioning.
6. Observability: source-row counts, freshness, failed joins, duplicate permits, changed field detection.
7. CDN/caching for public reads and rate limiting for search endpoints.
8. Admin review screen for report/comment joins before publication.
9. Privacy/accessibility audit, terms/disclaimer review, and provenance page before public launch.
