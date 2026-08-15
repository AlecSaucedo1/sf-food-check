import httpx


def _get(dataset, params):
    response = httpx.get(
        f"https://data.sfgov.org/resource/{dataset}.json",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def test_external_arsicault_record_probe():
    legacy = _get("pyih-qa8i", {
        "$limit": "500",
        "$where": "upper(business_address) like '%397%ARGUELLO%' OR upper(business_name) like '%ARSICAULT%'",
        "$order": "inspection_date DESC",
    })
    historical_sample = _get("5tti-66ds", {"$limit": "3"})
    print("\n2016-2019 ARSICAULT / 397 ARGUELLO")
    for row in legacy:
        print(row)
    print("\n2020-2023 SAMPLE KEYS", sorted(historical_sample[0].keys()) if historical_sample else [])
    for row in historical_sample:
        print(row)
    assert False, "diagnostic probe: inspect historical Arsicault identity and 2020 schema"
