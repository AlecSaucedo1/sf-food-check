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

if [[ "${USE_LIVE_DATA}" == "1" && "${LIVE_SYNC_ON_START:-1}" == "1" ]]; then
  echo "Refreshing San Francisco inspection data before startup (Socrata token optional)..."
  if ! python scripts/sync_datasf.py; then
    if python - "$DATABASE_PATH" <<'PY'
import sqlite3, sys
path = sys.argv[1]
try:
    con = sqlite3.connect(path)
    count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
except Exception:
    count = 0
raise SystemExit(0 if count > 0 else 1)
PY
    then
      echo "WARNING: live refresh failed; starting with the previously stored inspection dataset."
    else
      echo "ERROR: live refresh failed and no prior live dataset exists. Refusing to publish demo/empty data."
      exit 1
    fi
  fi
fi

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
