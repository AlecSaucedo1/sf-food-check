# Deploy SF Food Check on Render

The production MVP is designed to run as one Docker web service with one persistent disk. SQLite is appropriate for this initial single-instance beta; move to Postgres before horizontal scaling.

## 1. Connect the GitHub repository

In Render, create a new Blueprint and connect the `AlecSaucedo1/sf-food-check` repository. Render reads `render.yaml` from the repository root.

The Blueprint provisions:

- Docker web service
- Starter plan
- Oregon region
- 1 GB persistent disk mounted at `/var/data`
- database at `/var/data/inspections.db`
- `/api/health` health check
- automatic deploys only after GitHub CI checks pass
- a DataSF refresh at startup and every 24 hours

## 2. Set the Socrata token

`SOCRATA_APP_TOKEN` is marked `sync: false`, so Render will ask for it during Blueprint creation. Create an application token for the DataSF/Socrata API and paste only the token value into Render. Never commit the token to GitHub.

The application can use the public endpoint without a token, but a token is recommended for a production service.

## 3. Deploy

Apply the Blueprint. On first startup, `run.sh` downloads the current DataSF inspection dataset before Uvicorn starts.

Production deliberately fails closed: if the first live sync fails and no prior live database exists, the service exits instead of showing the repository's fictional demo records. On later sync failures, the last successful live database remains available.

## 4. Validate the deployment

Visit these endpoints on the Render URL:

- `/api/health` — should show `ok: true` and `demo_mode: false`
- `/api/ready` — should return HTTP 200
- `/api/meta` — confirms the configured source and dataset ID
- `/` — opens the mobile web app

Verify several restaurants manually against the official SF inspection lookup before publicizing the site.

## 5. Inspector comments

Structured DataSF data and full inspector narratives are separate sources. The app never invents inspector comments. Until a stable official report integration is available, verified narrative/report records can be loaded through:

```bash
python scripts/import_comments.py data/comments_import_template.csv
```

Use only verbatim official narrative and retain the official report URL.

## 6. Custom domain

After the Render URL is validated, add the chosen domain under the service's Custom Domains settings and update DNS using the records Render provides.

## 7. Before meaningful traffic

Prioritize these upgrades:

1. Postgres + PostGIS for multi-instance scaling and better geospatial search.
2. Reliable official-report enrichment for inspector narratives.
3. Fuzzy/full-text search and alias handling.
4. Automated source-schema drift alerts.
5. Error monitoring and uptime monitoring.
6. Terms, privacy, methodology, accessibility, and provenance review.
