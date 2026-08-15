import asyncio

from backend.data_coverage import fetch_complete_history
from backend.normalize import normalize_row


def test_external_complete_datasf_coverage_probe():
    rows = asyncio.run(fetch_complete_history(page_size=5000, max_rows=150_000))
    normalized = [normalize_row(row) for row in rows]
    arsicault = [
        row for row in normalized
        if "ARSICAULT" in str(row.get("dba") or "").upper()
    ]
    latest_by_permit = {}
    for row in arsicault:
        permit = row["permit_number"]
        current = latest_by_permit.get(permit)
        if current is None or str(row.get("inspection_date") or "") > str(current.get("inspection_date") or ""):
            latest_by_permit[permit] = row

    print("TOTAL UNIFIED ROWS", len(rows))
    print("ARSICAULT FACILITIES")
    for permit, row in sorted(latest_by_permit.items()):
        print(permit, row.get("dba"), row.get("street_address"), row.get("inspection_date"), row.get("facility_rating_status"))

    assert len(latest_by_permit) >= 4
    assert any("397ARGUELLO" in str(row.get("street_address") or "").upper().replace(" ", "") for row in latest_by_permit.values())
