import httpx

BASE = "https://sf-food-check.onrender.com"


def test_complete_coverage_and_leaderboard_drilldowns_are_live():
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        health = client.get(f"{BASE}/api/health")
        health.raise_for_status()
        health_payload = health.json()

        search = client.get(
            f"{BASE}/api/restaurants",
            params={"q": "Arsicault", "limit": 200},
        )
        search.raise_for_status()
        arsicault = search.json()
        addresses = {
            " ".join(str(row.get("street_address") or "").upper().split())
            for row in arsicault
        }
        print("HEALTH", health_payload)
        print("ARSICAULT", [
            (row.get("permit_number"), row.get("street_address"), row.get("inspection_date"), row.get("facility_rating_status"))
            for row in arsicault
        ])
        assert len(arsicault) >= 4
        arguello = next(
            row for row in arsicault
            if "397 ARGUELLO" in " ".join(str(row.get("street_address") or "").upper().split())
        )
        assert str(arguello.get("permit_number") or "").startswith("H16-")

        detail = client.get(f"{BASE}/api/restaurants/{arguello['permit_number']}")
        detail.raise_for_status()
        detail_payload = detail.json()
        assert any(i.get("facility_rating_status") == "Historical" for i in detail_payload.get("inspections", []))

        leaders = client.get(
            f"{BASE}/api/leaderboards",
            params={"limit": 25, "months": 18},
        )
        leaders.raise_for_status()
        leader_payload = leaders.json()
        assert leader_payload.get("chains")
        assert leader_payload.get("neighborhoods")

        neighborhood = leader_payload["neighborhoods"][0]["name"]
        neighborhood_members = client.get(
            f"{BASE}/api/restaurants",
            params={"neighborhood": neighborhood, "limit": 200},
        )
        neighborhood_members.raise_for_status()
        assert neighborhood_members.json()

        # Arsicault is a known regression for full chain footprint: the same search
        # used by the chain drilldown must return all four inspection facilities.
        assert len(arsicault) >= 4

        js = client.get(f"{BASE}/static/leaderboards-v2.js?v=9")
        js.raise_for_status()
        assert 'data-leader-kind' in js.text
        assert 'Click to view locations' in js.text
        assert 'Click to view restaurants' in js.text
        assert 'openGroup' in js.text

        page = client.get(f"{BASE}/")
        page.raise_for_status()
        assert '/static/leaderboards-v2.js?v=9' in page.text
