import time

import httpx

BASE = "https://sf-food-check.onrender.com"


def test_production_complete_coverage_and_leaderboard_assets():
    last = None
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for _ in range(18):
            health = client.get(f"{BASE}/api/health")
            health.raise_for_status()
            search = client.get(f"{BASE}/api/restaurants", params={"q": "Arsicault", "limit": 200})
            search.raise_for_status()
            rows = search.json()
            last = rows
            addresses = {" ".join(str(row.get("street_address") or "").upper().split()) for row in rows}
            if len(rows) >= 4 and any("397 ARGUELLO" in address for address in addresses):
                break
            time.sleep(10)
        else:
            raise AssertionError(f"Expanded database did not become visible. Last Arsicault rows: {last}")

        print("ARSICAULT", [(r.get("permit_number"), r.get("street_address"), r.get("inspection_date")) for r in last])
        assert len(last) >= 4
        assert any("397 ARGUELLO" in " ".join(str(r.get("street_address") or "").upper().split()) for r in last)

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

        page = client.get(f"{BASE}/")
        page.raise_for_status()
        assert '/static/leaderboards-v2.js?v=9' in page.text
