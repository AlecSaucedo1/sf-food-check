#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
mkdir -p "$(dirname "$DATABASE_PATH")"

if [[ "${USE_LIVE_DATA:-0}" == "1" && "${LIVE_SYNC_ON_START:-1}" == "1" ]]; then
  echo "Refreshing San Francisco inspection data before startup..."
  if ! python scripts/sync_datasf.py; then
    # Fail closed on a brand-new production deployment; serve stale data only if a prior
    # successful live database already exists.
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
