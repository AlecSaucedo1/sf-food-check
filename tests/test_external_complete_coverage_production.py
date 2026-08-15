import time

import httpx

BASE = "https://sf-food-check.onrender.com"
OLD_SYNC = "2026-08-15T08:21:03+00:00"


def test_complete_coverage_is_live():
    last_health = None
    last_rows = None
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for _ in range(30):
            health = client.get(f"{BASE}/api/health")
            health.raise_for_status()
            last_health = health.json()
            search = client.get(f"{BASE}/api/restaurants", params={"q": "Arsicault", "limit": 200})
            search.raise_for_status()
            last_rows = search.json()
            addresses = {" ".join(str(row.get("street_address") or "").upper().split()) for row in last_rows}
            sync_started = str((last_health.get("last_sync") or {}).get("started_at") or "")
            if sync_started and sync_started != OLD_SYNC and len(last_rows) >= 4 and any("397 ARGUELLO" in a for a in addresses):
                break
            time.sleep(10)
        else:
            raise AssertionError({"health": last_health, "arsicault": last_rows})

        print("HEALTH", last_health)
        print("ARSICAULT", [(r.get("permit_number"), r.get("street_address"), r.get("inspection_date")) for r in last_rows])
        assert len(last_rows) >= 4
        assert any("397 ARGUELLO" in " ".join(str(r.get("street_address") or "").upper().split()) for r in last_rows)

        leaders = client.get(f"{BASE}/api/leaderboards", params={"limit": 25, "months": 18})
        leaders.raise_for_status()
        payload = leaders.json()
        assert payload.get("chains") is not None
        assert payload.get("neighborhoods") is not None

        js = client.get(f"{BASE}/static/leaderboards-v2.js?v=9")
        js.raise_for_status()
        assert 'data-leader-kind' in js.text
        assert 'Click to view locations' in js.text
        assert 'Click to view restaurants' in js.text
