import collections
import os
import time

import httpx


SITE = "https://sf-food-check.onrender.com"
DATASF = "https://data.sfgov.org/resource/tvy3-wexg.json"


def test_heaviest_live_restaurant_pages_respond():
    """Temporary production probe for pathological restaurant-detail payloads."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        rows = client.get(
            DATASF,
            params={
                "$select": "permit_number,dba,violation_codes,inspection_date",
                "$limit": "50000",
            },
        ).json()

        weights = collections.defaultdict(lambda: {"bytes": 0, "rows": 0, "name": ""})
        for row in rows:
            permit = str(row.get("permit_number") or "").strip()
            if not permit:
                continue
            item = weights[permit]
            item["bytes"] += len(str(row.get("violation_codes") or ""))
            item["rows"] += 1
            item["name"] = str(row.get("dba") or item["name"])

        heaviest = sorted(
            weights.items(),
            key=lambda kv: (kv[1]["bytes"] + kv[1]["rows"] * 500),
            reverse=True,
        )[:30]

        failures = []
        timings = []
        for permit, meta in heaviest:
            started = time.monotonic()
            try:
                response = client.get(f"{SITE}/api/restaurants/{permit}", timeout=12.0)
                elapsed = time.monotonic() - started
                timings.append((elapsed, permit, meta["name"], response.status_code, meta["rows"], meta["bytes"]))
                if response.status_code != 200:
                    failures.append((permit, meta["name"], response.status_code, elapsed, response.text[:200]))
            except Exception as exc:
                elapsed = time.monotonic() - started
                timings.append((elapsed, permit, meta["name"], "EXC", meta["rows"], meta["bytes"]))
                failures.append((permit, meta["name"], type(exc).__name__, elapsed, str(exc)[:200]))

        print("SLOWEST LIVE RESTAURANT DETAIL REQUESTS")
        for item in sorted(timings, reverse=True)[:15]:
            print(item)
        assert not failures, f"Live restaurant detail failures: {failures}"
