import httpx

BASE = "https://sf-food-check.onrender.com"


def test_complete_deduplicated_coverage_and_drilldowns_are_live():
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        health = client.get(f"{BASE}/api/health")
        health.raise_for_status()
        health_payload = health.json()

        search = client.get(f"{BASE}/api/restaurants", params={"q": "Arsicault", "limit": 200})
        search.raise_for_status()
        arsicault = search.json()
        print("HEALTH", health_payload)
        print("ARSICAULT", [
            (row.get("permit_number"), row.get("street_address"), row.get("inspection_date"), row.get("facility_rating_status"))
            for row in arsicault
        ])
        assert len(arsicault) == 4
        arguello = [
            row for row in arsicault
            if "397 ARGUELLO" in " ".join(str(row.get("street_address") or "").upper().split())
        ]
        assert len(arguello) == 1

        detail = client.get(f"{BASE}/api/restaurants/{arguello[0]['permit_number']}")
        detail.raise_for_status()
        inspections = detail.json().get("inspections", [])
        dates = [str(item.get("inspection_date") or "") for item in inspections]
        statuses = [str(item.get("facility_rating_status") or "") for item in inspections]
        print("ARGUELLO HISTORY", list(zip(dates, statuses)))
        assert any(date.startswith("2023-") for date in dates)
        assert any(date.startswith("2019-") for date in dates)
        assert "Historical" in statuses

        leaders = client.get(f"{BASE}/api/leaderboards", params={"limit": 25, "months": 18})
        leaders.raise_for_status()
        payload = leaders.json()
        assert payload.get("chains")
        assert payload.get("neighborhoods")

        neighborhood = payload["neighborhoods"][0]["name"]
        members = client.get(
            f"{BASE}/api/restaurants",
            params={"neighborhood": neighborhood, "limit": 200},
        )
        members.raise_for_status()
        assert members.json()

        js = client.get(f"{BASE}/static/leaderboards-v2.js?v=9")
        js.raise_for_status()
        assert 'data-leader-kind' in js.text
        assert 'Click to view locations' in js.text
        assert 'Click to view restaurants' in js.text
        assert 'openGroup' in js.text

        page = client.get(f"{BASE}/")
        page.raise_for_status()
        assert '/static/leaderboards-v2.js?v=9' in page.text
