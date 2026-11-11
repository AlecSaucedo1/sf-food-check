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
- scheduled daily source-revision checks in GitHub Actions, triggering CI-gated rebuilds only when DataSF changes

## 2. Set the Socrata token

A Socrata app token is optional. If you want to use one, set `SOCRATA_APP_TOKEN` privately in Render; never commit it to GitHub.

The application can use the public endpoint without a token, but a token is recommended for a production service.

## 3. Deploy

Apply the Blueprint. During the Docker build, `scripts/build_complete_bundle.py` fetches all three official inspection eras, deduplicates facilities across eras, builds the search index and leaderboard snapshot, and rejects incomplete data before Render switches deployments. At startup `run.sh` publishes this validated bundled database to the persistent disk before Uvicorn starts.

Production preserves the last successful database on new build failures and does not serve demo records in live mode.

### Daily automatic refresh

GitHub Actions workflow `.github/workflows/refresh_inspections.yml` checks the official current dataset's latest `data_loaded_at` timestamp every day. If newer than production's last successful sync, it runs regression tests, commits a data revision marker to `main`, and uses GitHub's `workflow_dispatch` to run CI on the bot-authored commit. This is necessary because regular `GITHUB_TOKEN` commits do not automatically start push workflows. The successful dispatched check triggers Render's **After CI Checks Pass** deployment, rebuilding all inspection eras outside the serving container.

Repository Actions must permit `GITHUB_TOKEN` to write repository contents and dispatch workflows, and automation must be allowed to push to `main`. Keep Render's Auto-Deploy setting at **After CI Checks Pass**. Inspect GitHub Actions > Refresh inspection data for failures or run it manually using **Run workflow**. If automated bot pushes are blocked by branch protection, adjust the repository automation permission or use an authorized Render deploy hook instead.

## 4. Validate the deployment

Visit these endpoints on the Render URL:

- `/api/health` — should show `ok: true`, `demo_mode: false`, a successful recent `last_sync`, and `data_freshness: current`
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
