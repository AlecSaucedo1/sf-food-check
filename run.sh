#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Render sets RENDER/RENDER_SERVICE_ID automatically. Default a Render deployment to
# live DataSF mode even if the service was created manually rather than by Blueprint.
if [[ -n "${RENDER:-}${RENDER_SERVICE_ID:-}${RENDER_EXTERNAL_URL:-}" ]]; then
  export USE_LIVE_DATA="${USE_LIVE_DATA:-1}"
  export DATABASE_PATH="${DATABASE_PATH:-/var/data/inspections.db}"

  # IMPORTANT: the web process must remain read-only against the live SQLite file.
  # A full DataSF replacement holds a long SQLite write transaction; running it on
  # the same single-instance Render service can block health checks and trigger a
  # restart loop. Data refreshes stay disabled here until the sync path writes a
  # shadow database and atomically swaps it into place.
  export LIVE_SYNC_ON_START="0"
  export SYNC_BACKGROUND="0"
else
  export USE_LIVE_DATA="${USE_LIVE_DATA:-0}"
  export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
fi

mkdir -p "$(dirname "$DATABASE_PATH")"
echo "SF Food Check startup: live_data=${USE_LIVE_DATA} database=${DATABASE_PATH} web_sync=disabled"

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
