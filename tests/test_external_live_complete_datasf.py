import time

import httpx

BASE = "https://sf-food-check.onrender.com"


def test_live_complete_datasf_contains_all_arsicault_locations():
    last_health = None
    last_rows = None
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for _ in range(30):
            health = client.get(f"{BASE}/api/health")
            health.raise_for_status()
            last_health = health.json()

            search = client.get(
                f"{BASE}/api/restaurants",
                params={"q": "Arsicault", "limit": 200},
            )
            search.raise_for_status()
            last_rows = search.json()
            addresses = {
                " ".join(str(row.get("street_address") or "").upper().split())
                for row in last_rows
            }

            if (
                last_health.get("app_version") == "0.8.1"
                and last_health.get("complete_sync_background") is True
                and len(last_rows) >= 4
                and any("397 ARGUELLO" in address for address in addresses)
            ):
                break
            time.sleep(5)
        else:
            raise AssertionError({"health": last_health, "arsicault": last_rows})

    print("LIVE HEALTH", last_health)
    print("LIVE ARSICAULT", [
        (row.get("permit_number"), row.get("street_address"), row.get("inspection_date"))
        for row in last_rows
    ])
    assert len(last_rows) >= 4
    assert any(
        "397 ARGUELLO" in " ".join(str(row.get("street_address") or "").upper().split())
        for row in last_rows
    )
