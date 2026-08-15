from __future__ import annotations

import fcntl
import os
from pathlib import Path

from backend.shadow_sync import sync_complete_shadow_blocking


if __name__ == "__main__":
    db_path = os.getenv("DATABASE_PATH", "/var/data/active.db")
    lock_path = str(Path(db_path).with_name("complete-sync.lock"))
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Complete DataSF shadow sync already running; skipping overlap.", flush=True)
            raise SystemExit(0)

        result = sync_complete_shadow_blocking(db_path)
        print(
            "Complete DataSF shadow sync finished: "
            f"rows={result['rows']} facilities={result['facilities']} latest={result['latest_inspection_date']}",
            flush=True,
        )
