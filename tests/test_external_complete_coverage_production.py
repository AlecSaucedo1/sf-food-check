import httpx

BASE = "https://sf-food-check.onrender.com"


def test_production_sync_diagnostic():
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        health = client.get(f"{BASE}/api/health")
        health.raise_for_status()
        search = client.get(f"{BASE}/api/restaurants", params={"q": "Arsicault", "limit": 200})
        search.raise_for_status()
        raise AssertionError({
            "health": health.json(),
            "arsicault": [
                (row.get("permit_number"), row.get("street_address"), row.get("inspection_date"))
                for row in search.json()
            ],
        })
