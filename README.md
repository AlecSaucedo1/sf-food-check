# SF Food Check

A mobile-first San Francisco restaurant health-inspection browser. The product is built around **official inspection outcomes, inspection history, violations, and inspector comments**, while keeping government records visually separate from consumer-friendly explanations.

SF Food Check is an independent project and is not affiliated with or endorsed by the City and County of San Francisco.

## Included in the MVP

- Restaurant name/address search
- Pass / Conditional Pass / Closure filters
- Recent-inspection browsing
- Nearby search using browser geolocation
- Mobile-first list and map-style views
- Restaurant detail pages and inspection timelines
- Violation codes, official descriptions, and separate plain-language categories
- Inspector-comment and corrective-action enrichment layer
- Links to official SF inspection sources
- Installable PWA shell
- FastAPI backend
- SQLite persistence for the single-instance beta
- DataSF live ingestion for dataset `tvy3-wexg`
- Raw-source retention for auditability
- Health/readiness endpoints and data-freshness telemetry
- GitHub CI
- Render Blueprint deployment

## Local development

The repository includes clearly fictional demonstration records for offline/local evaluation.

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Run with live San Francisco data

```bash
python scripts/sync_datasf.py --reset
USE_LIVE_DATA=1 python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

For production, use the included Render configuration instead of manually starting the server.

## Deploy

See [`docs/deploy-render.md`](docs/deploy-render.md).

The production configuration uses a paid Render web service with a persistent disk. On first startup the application refreshes the DataSF dataset before serving traffic. If that first refresh fails, it refuses to publish demo/empty data. Later refresh failures preserve the last successful live snapshot.

## Inspector comments

Full inspector narrative is treated as a separate enrichment source. The app never substitutes generated text for unavailable official narrative.

Verified records can be imported with:

```bash
python scripts/import_comments.py data/comments_import_template.csv
```

## Tests

```bash
pytest -q
```

or:

```bash
python -m unittest discover -s tests -v
```

See `docs/data-model.md`, `docs/product-spec.md`, and `docs/production.md` for additional architecture details.
