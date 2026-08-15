#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PERSISTENT_LIVE=0
if [[ "${DATABASE_PATH:-}" == /var/data/* ]] || [[ -n "${RENDER:-}${RENDER_SERVICE_ID:-}${RENDER_EXTERNAL_URL:-}" ]]; then
  PERSISTENT_LIVE=1
fi

# The web service must never perform the full multi-era DataSF import. That workload
# can exhaust the single Render instance and take health checks down with it. The
# complete dataset is built outside the serving process and published separately.
if [[ "$PERSISTENT_LIVE" == "1" ]]; then
  export USE_LIVE_DATA="${USE_LIVE_DATA:-1}"

  LEGACY_DATABASE_PATH="${DATABASE_PATH:-/var/data/inspections.db}"
  ACTIVE_DATABASE_PATH="/var/data/active.db"
  mkdir -p /var/data

  if [[ ! -L "$ACTIVE_DATABASE_PATH" ]]; then
    rm -f "$ACTIVE_DATABASE_PATH"
    if [[ -e "$LEGACY_DATABASE_PATH" ]]; then
      ln -s "$(basename "$LEGACY_DATABASE_PATH")" "$ACTIVE_DATABASE_PATH"
    else
      ln -s inspections.db "$ACTIVE_DATABASE_PATH"
    fi
  fi

  export DATABASE_PATH="$ACTIVE_DATABASE_PATH"
  export LIVE_SYNC_ON_START="0"
  export SYNC_BACKGROUND="0"
  export COMPLETE_SYNC_BACKGROUND="0"
else
  export USE_LIVE_DATA="${USE_LIVE_DATA:-0}"
  export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
  export COMPLETE_SYNC_BACKGROUND="0"
fi

mkdir -p "$(dirname "$DATABASE_PATH")"
echo "SF Food Check startup: live_data=${USE_LIVE_DATA} database=${DATABASE_PATH} complete_sync=disabled"

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
