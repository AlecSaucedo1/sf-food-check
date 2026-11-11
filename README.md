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
- Complete three-era DataSF import (`pyih-qa8i`, `5tti-66ds`, `tvy3-wexg`)
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

The production configuration uses a paid Render web service with a persistent disk. The Docker image builds and validates all three DataSF eras before deployment; the web server does not perform expensive imports. The daily GitHub Actions workflow `.github/workflows/refresh_inspections.yml` compares the current DataSF `data_loaded_at` revision with production `/api/health`. Only if DataSF has changed does it commit a refresh marker and dispatch CI on that commit. With Render set to **After CI Checks Pass**, successful checks initiate a new complete Docker build; failed fetch/validation leaves the previous deployment serving. No Socrata token or Render API key is required.

Check `/api/health` for `last_sync`, `data_refreshed_at`, `data_age_days`, and `data_freshness`. DataSF is the structured inspection feed, not the full inspector-narrative report source; inspector comments remain separately sourced and require verified enrichment.

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
