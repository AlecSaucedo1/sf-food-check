"""Temporary external post-deploy canary, never merged."""
import time
import httpx

BASE = "https://sf-food-check.onrender.com"

def test_november_production_update_and_response_times():
    with httpx.Client(timeout=35, follow_redirects=True) as client:
        for attempt in range(30):
            r = client.get(BASE + "/api/health")
            if r.status_code == 200:
                health = r.json()
                if health.get("app_version") == "0.8.2" and (health.get("latest_inspection_date") or "") >= "2026-10-01":
                    break
            time.sleep(12)
        else:
            raise AssertionError({"last_health": r.text[:2000], "http_status": r.status_code})
        print("POST_HEALTH", health)
        assert health["data_freshness"] == "current"
        assert health["inspection_rows"] > 65000
        assert health["facility_count"] > 13000
        for route in (
            "/api/restaurants?limit=50",
            "/api/restaurants?q=Arsicault",
            "/api/restaurants?q=Pizza",
            "/api/nearby?lat=37.775&lon=-122.419&radius_km=2&limit=50",
            "/api/leaderboards?months=18",
        ):
            times = []
            for _ in range(2):
                t = time.perf_counter()
                response = client.get(BASE + route)
                times.append(round((time.perf_counter()-t)*1000))
            assert response.status_code == 200, (route, response.status_code)
            print("POST_METRIC", route, times, "bytes", len(response.content))
            if "Arsicault" in route:
                results = response.json()
                assert len(results) == 4
                assert sum("397 ARGUELLO" in str(x["street_address"]).upper() for x in results) == 1
        raise AssertionError("intentional metrics capture on temporary diagnostics PR")
