import os
from collections import Counter

import httpx

BASE = "https://sf-food-check.onrender.com"


def test_recalibrated_production_release():
    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        health = client.get(BASE + "/api/health")
        assert health.status_code == 200, health.text[:500]
        h = health.json()
        print("HEALTH", {k: h.get(k) for k in ("app_version", "risk_model_version", "facility_count", "inspection_rows")})
        assert h.get("app_version") == "0.8.0"
        assert h.get("risk_model_version") == "2026.08.15.4"

        prime = client.get(BASE + "/api/restaurants/18531")
        assert prime.status_code == 200, prime.text[:500]
        p = prime.json()
        print("PRIME", p.get("dba"), p.get("latest_risk"))
        assert p.get("latest_risk", {}).get("risk_score") == 53
        assert p.get("latest_risk", {}).get("risk_score", 100) < 100

        listings = client.get(BASE + "/api/restaurants?limit=30")
        assert listings.status_code == 200, listings.text[:500]
        items = listings.json()
        scores = []
        failures = []
        for item in items[:30]:
            permit = item.get("permit_number")
            try:
                response = client.get(BASE + "/api/restaurants/" + str(permit))
                if response.status_code != 200:
                    failures.append((permit, response.status_code))
                    continue
                score = int(response.json().get("latest_risk", {}).get("risk_score") or 0)
                scores.append(score)
            except Exception as exc:
                failures.append((permit, type(exc).__name__))
        print("SAMPLE_SCORES", scores)
        print("SAMPLE_FAILURES", failures)
        assert not failures
        assert scores
        assert max(scores) <= 98
        assert 100 not in scores
        bands = Counter(
            "0-19" if s < 20 else "20-44" if s < 45 else "45-69" if s < 70 else "70-89" if s < 90 else "90+"
            for s in scores
        )
        print("SCORE_BANDS", dict(bands))

        leader = client.get(BASE + "/api/leaderboards?limit=10&months=18")
        assert leader.status_code == 200, leader.text[:500]
        data = leader.json()
        for key in ("chains", "neighborhoods", "highest_risk_chains", "highest_risk_neighborhoods"):
            assert data.get(key), key
        assert data["chains"][0]["average_risk"] <= data["chains"][-1]["average_risk"]
        assert data["neighborhoods"][0]["average_risk"] <= data["neighborhoods"][-1]["average_risk"]
        assert data["highest_risk_chains"][0]["average_risk"] >= data["highest_risk_chains"][-1]["average_risk"]
        assert data["highest_risk_neighborhoods"][0]["average_risk"] >= data["highest_risk_neighborhoods"][-1]["average_risk"]
        print("BEST_CHAINS", [(x["name"], x["average_risk"]) for x in data["chains"][:5]])
        print("RISK_CHAINS", [(x["name"], x["average_risk"]) for x in data["highest_risk_chains"][:5]])
        print("BEST_NEIGHBORHOODS", [(x["name"], x["average_risk"]) for x in data["neighborhoods"][:5]])
        print("RISK_NEIGHBORHOODS", [(x["name"], x["average_risk"]) for x in data["highest_risk_neighborhoods"][:5]])
