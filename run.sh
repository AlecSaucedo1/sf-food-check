#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PERSISTENT_LIVE=0
if [[ "${DATABASE_PATH:-}" == /var/data/* ]] || [[ -n "${RENDER:-}${RENDER_SERVICE_ID:-}${RENDER_EXTERNAL_URL:-}" ]]; then
  PERSISTENT_LIVE=1
fi

# The web service never performs the full multi-era DataSF import. The image build
# creates and validates a complete database before deployment. Startup only copies
# that finished file to the persistent disk, preserves any report enrichment, and
# atomically switches the active symlink before uvicorn begins accepting requests.
if [[ "$PERSISTENT_LIVE" == "1" ]]; then
  export USE_LIVE_DATA="${USE_LIVE_DATA:-1}"

  export LEGACY_DATABASE_PATH="${DATABASE_PATH:-/var/data/inspections.db}"
  export ACTIVE_DATABASE_PATH="/var/data/active.db"
  export BUNDLED_DATABASE_PATH="/app/data/complete-inspections.db"
  export LEADERBOARD_SNAPSHOT_PATH="/var/data/leaderboard_facilities.json"
  mkdir -p /var/data

  # Establish a last-good fallback before attempting publication.
  if [[ ! -L "$ACTIVE_DATABASE_PATH" ]]; then
    rm -f "$ACTIVE_DATABASE_PATH"
    if [[ -e "$LEGACY_DATABASE_PATH" ]]; then
      ln -s "$(basename "$LEGACY_DATABASE_PATH")" "$ACTIVE_DATABASE_PATH"
    else
      ln -s inspections.db "$ACTIVE_DATABASE_PATH"
    fi
  fi

  if [[ -f "$BUNDLED_DATABASE_PATH" ]]; then
    if ! python scripts/publish_bundled_db.py; then
      echo "Bundled DataSF publication failed; serving the last good persistent database" >&2
    fi
  else
    echo "Bundled DataSF database missing; serving the last good persistent database" >&2
  fi

  export DATABASE_PATH="$ACTIVE_DATABASE_PATH"
  export LIVE_SYNC_ON_START="0"
  export SYNC_BACKGROUND="0"
  export COMPLETE_SYNC_BACKGROUND="0"
  export LEADERBOARD_REFRESH_ON_START="0"
else
  export USE_LIVE_DATA="${USE_LIVE_DATA:-0}"
  export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
  export COMPLETE_SYNC_BACKGROUND="0"
fi

mkdir -p "$(dirname "$DATABASE_PATH")"
echo "SF Food Check startup: live_data=${USE_LIVE_DATA} database=${DATABASE_PATH} runtime_sync=disabled"

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
