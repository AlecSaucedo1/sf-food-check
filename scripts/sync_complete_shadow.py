from __future__ import annotations

import os

from backend.shadow_sync import sync_complete_shadow_blocking


if __name__ == "__main__":
    db_path = os.getenv("DATABASE_PATH", "/var/data/active.db")
    result = sync_complete_shadow_blocking(db_path)
    print(
        "Complete DataSF shadow sync finished: "
        f"rows={result['rows']} facilities={result['facilities']} latest={result['latest_inspection_date']}",
        flush=True,
    )
