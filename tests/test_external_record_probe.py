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
    address_2020 = _get("5tti-66ds", "upper(business_address) like '%397%ARGUELLO%'")
    address_legacy = _get("pyih-qa8i", "upper(business_address) like '%397%ARGUELLO%'")

    live = httpx.get(
        "https://sf-food-check.onrender.com/api/restaurants",
        params={"q": "397 Arguello", "limit": "200"},
        timeout=30,
    )
    live.raise_for_status()

    def show(label, rows):
        print(f"\n{label}")
        for row in rows:
            print(row)

    show("CURRENT NAMED ARSICAULT", named)
    show("CURRENT 397 ARGUELLO", address_current)
    show("2020-2023 397 ARGUELLO", address_2020)
    show("2016-2019 397 ARGUELLO", address_legacy)
    show("LIVE SEARCH 397 ARGUELLO", live.json())

    assert False, "diagnostic probe: inspect current and historical Arguello identity"
