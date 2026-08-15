import httpx


def test_external_arsicault_record_probe():
    upstream = httpx.get(
        "https://data.sfgov.org/resource/tvy3-wexg.json",
        params={
            "$limit": "500",
            "$where": "upper(dba) like '%ARSICAULT%'",
            "$order": "permit_number ASC, inspection_date DESC",
        },
        timeout=30,
    )
    upstream.raise_for_status()
    upstream_rows = upstream.json()

    live = httpx.get(
        "https://sf-food-check.onrender.com/api/restaurants",
        params={"q": "Arsicault", "limit": "200"},
        timeout=30,
    )
    live.raise_for_status()
    live_rows = live.json()

    leaders = httpx.get(
        "https://sf-food-check.onrender.com/api/leaderboards",
        params={"limit": "25", "months": "18"},
        timeout=30,
    )
    leaders.raise_for_status()
    leader_rows = leaders.json()

    fields = ("permit_number", "dba", "street_address", "inspection_date", "facility_rating_status", "inspection_type")
    print("\nUPSTREAM ARSICAULT")
    for row in upstream_rows:
        print({key: row.get(key) for key in fields})
    print("UPSTREAM DISTINCT PERMITS", sorted({str(row.get("permit_number") or "") for row in upstream_rows}))
    print("\nLIVE SEARCH")
    for row in live_rows:
        print({key: row.get(key) for key in fields})
    print("LIVE DISTINCT PERMITS", sorted({str(row.get("permit_number") or "") for row in live_rows}))
    print("\nARSICAULT LEADERBOARD")
    for key in ("chains", "highest_risk_chains"):
        print(key, [row for row in leader_rows.get(key, []) if "ARSICAULT" in str(row.get("name", "")).upper()])

    assert False, "diagnostic probe: inspect logged upstream/live Arsicault rows"
