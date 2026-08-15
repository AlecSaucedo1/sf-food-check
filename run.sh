#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Detect the persistent production data path from configuration we control. Render's
# auto-injected environment variables are not guaranteed to be present in every
# service configuration, while render.yaml explicitly sets DATABASE_PATH=/var/data/...
# and USE_LIVE_DATA=1.
PERSISTENT_LIVE=0
if [[ "${DATABASE_PATH:-}" == /var/data/* ]] || [[ -n "${RENDER:-}${RENDER_SERVICE_ID:-}${RENDER_EXTERNAL_URL:-}" ]]; then
  PERSISTENT_LIVE=1
fi

# Keep the HTTP process read-only against a stable SQLite target, while a low-priority
# background job builds the next complete data version in a separate file and
# atomically switches a symlink when finished.
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
      # A dangling relative symlink is intentional: SQLite will create the initial
      # target on first open, after which the shadow refresher publishes versions.
      ln -s inspections.db "$ACTIVE_DATABASE_PATH"
    fi
  fi

  export DATABASE_PATH="$ACTIVE_DATABASE_PATH"
  export LIVE_SYNC_ON_START="0"
  export SYNC_BACKGROUND="0"

  # Do not block web startup. The refresher covers all official DataSF eras and
  # repeats daily. `nice` prevents scoring/import work from taking CPU priority over
  # user requests; the Python runner also uses a file lock to prevent overlap.
  (
    sleep 8
    while true; do
      nice -n 10 python scripts/sync_complete_shadow.py || echo "Complete DataSF shadow sync failed; retaining last good database" >&2
      sleep 86400
    done
  ) &
else
  export USE_LIVE_DATA="${USE_LIVE_DATA:-0}"
  export DATABASE_PATH="${DATABASE_PATH:-./data/inspections.db}"
fi

mkdir -p "$(dirname "$DATABASE_PATH")"
echo "SF Food Check startup: live_data=${USE_LIVE_DATA} database=${DATABASE_PATH} shadow_sync=$([[ "$PERSISTENT_LIVE" == "1" ]] && echo enabled || echo disabled)"

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
