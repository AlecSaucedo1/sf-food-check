#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Render sets RENDER/RENDER_SERVICE_ID automatically. Default a Render deployment to
# live DataSF mode even if the service was created manually rather than by Blueprint.
if [[ -n "${RENDER:-}${RENDER_SERVICE_ID:-}${RENDER_EXTERNAL_URL:-}" ]]; then
  export USE_LIVE_DATA="${USE_LIVE_DATA:-1}"
  export LIVE_SYNC_ON_START="${LIVE_SYNC_ON_START:-1}"
  export SYNC_BACKGROUND="${SYNC_BACKGROUND:-1}"
  export SYNC_INTERVAL_HOURS="${SYNC_INTERVAL_HOURS:-24}"
  export DATABASE_PATH="${DATABASE_PATH:-/var/data/inspections.db}"
else
  export USE_LIVE_DATA="${USE_LIVE_DATA:-0}"
  export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
fi

mkdir -p "$(dirname "$DATABASE_PATH")"
echo "SF Food Check startup: live_data=${USE_LIVE_DATA} database=${DATABASE_PATH}"

# Do not make web startup depend on a full DataSF refresh. Render's persistent disk
# retains the last good snapshot, and sync_service replaces inspection data plus the
# leaderboard snapshot atomically. The refresh can therefore run after uvicorn starts
# without exposing a partially written dataset.
if [[ "${USE_LIVE_DATA}" == "1" && "${LIVE_SYNC_ON_START:-1}" == "1" ]]; then
  echo "Starting San Francisco inspection refresh in the background (Socrata token optional)..."
  (
    if python scripts/sync_datasf.py; then
      echo "Initial DataSF refresh completed."
    else
      echo "WARNING: initial DataSF refresh failed; continuing with the last persisted dataset if available."
    fi
  ) &
fi

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
