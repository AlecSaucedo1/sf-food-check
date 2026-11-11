"""Temporary external performance and freshness probe. Not part of production."""
import time
import httpx

BASE = "https://sf-food-check.onrender.com"
SOURCE = "https://data.sfgov.org/resource/tvy3-wexg.json"


def test_live_site_freshness_and_latency():
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for route in ("/api/health", "/api/restaurants?q=Arsicault", "/api/restaurants?q=Pizza", "/api/restaurants?limit=50", "/api/leaderboards?months=18", "/api/nearby?lat=37.775&lon=-122.419&radius_km=2&limit=50"):
            timings = []
            last = None
            for _ in range(2):
                t = time.perf_counter()
                r = client.get(BASE + route)
                timings.append(round((time.perf_counter()-t)*1000))
                last = r
            print("METRIC", route, last.status_code, "ms", timings, "bytes", len(last.content), flush=True)
            assert last.status_code == 200
            if route == "/api/health":
                print("LIVE_HEALTH", last.text[:1800], flush=True)
            elif route.startswith("/api/nearby"):
                print("NEARBY_COUNT", len(last.json()), flush=True)
        upstream = client.get(SOURCE, params={"$select":"count(*) as rows, max(inspection_date) as newest, max(data_loaded_at) as latest_load"})
        print("UPSTREAM", upstream.status_code, upstream.text[:1000], flush=True)
        assert upstream.status_code == 200
