import os

import httpx

SITE = "https://sf-food-check.onrender.com"


def test_observation_release_is_live():
    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        health = client.get(SITE + "/api/health")
        assert health.status_code == 200, health.text[:300]
        h = health.json()
        assert h["app_version"] == "0.7.0"
        assert h.get("observation_model_version") == "2026.08.15.1"
        assert "observation_records" in h
        assert "observation_coverage_pct" in h

        meta = client.get(SITE + "/api/meta")
        assert meta.status_code == 200, meta.text[:300]
        m = meta.json()
        assert m.get("observation_model_version") == "2026.08.15.1"
        assert "verified official inspection report" in m.get("observation_policy", "").lower()

        for asset in ("/static/observations.js?v=7", "/static/observations.css?v=7", "/static/sw.js"):
            response = client.get(SITE + asset)
            assert response.status_code == 200, (asset, response.status_code)
        sw = client.get(SITE + "/static/sw.js").text
        assert "sf-food-check-v7" in sw
        assert "observations.js?v=7" in sw

        restaurants = client.get(SITE + "/api/restaurants?limit=1")
        assert restaurants.status_code == 200, restaurants.text[:300]
        items = restaurants.json()
        assert items
        permit = items[0]["permit_number"]
        detail = client.get(SITE + f"/api/restaurants/{permit}")
        assert detail.status_code == 200, detail.text[:300]
        d = detail.json()
        assert d.get("observation_model_version") == "2026.08.15.1"
        assert d.get("inspections")
        assert "observation_mapping" in d["inspections"][0]

        print("PRODUCTION_HEALTH", h)
        print("PRODUCTION_DETAIL_PERMIT", permit)
