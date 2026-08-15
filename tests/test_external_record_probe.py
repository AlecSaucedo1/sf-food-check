import httpx


def _get(dataset, where):
    response = httpx.get(
        f"https://data.sfgov.org/resource/{dataset}.json",
        params={"$limit": "500", "$where": where, "$order": "inspection_date DESC"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def test_external_arsicault_record_probe():
    named = _get("tvy3-wexg", "upper(dba) like '%ARSICAULT%'")
    address_current = _get("tvy3-wexg", "upper(street_address) like '%397%ARGUELLO%'")
    arg_current = _get("tvy3-wexg", "upper(street_address) like '%ARGUELLO%'")

    live_name = httpx.get(
        "https://sf-food-check.onrender.com/api/restaurants",
        params={"q": "Arsicault", "limit": "200"},
        timeout=30,
    )
    live_name.raise_for_status()
    live_address = httpx.get(
        "https://sf-food-check.onrender.com/api/restaurants",
        params={"q": "397 Arguello", "limit": "200"},
        timeout=30,
    )
    live_address.raise_for_status()

    def show(label, rows):
        print(f"\n{label}")
        for row in rows:
            print(row)

    show("CURRENT NAMED ARSICAULT", named)
    show("CURRENT 397 ARGUELLO", address_current)
    show("CURRENT ALL ARGUELLO", arg_current)
    show("LIVE SEARCH ARSICAULT", live_name.json())
    show("LIVE SEARCH 397 ARGUELLO", live_address.json())

    assert False, "diagnostic probe: inspect current Arguello identity"
