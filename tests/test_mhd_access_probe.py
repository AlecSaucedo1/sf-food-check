import os
import re

import httpx


BASE = "https://inspections.myhealthdepartment.com/san-francisco"


def test_probe_myhealthdepartment_access():
    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/136 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
        response = client.get(BASE + "/")
        print("MHD_STATUS", response.status_code)
        print("MHD_FINAL_URL", response.url)
        print("MHD_SERVER", response.headers.get("server"))
        text = response.text
        print("MHD_LENGTH", len(text))
        print("MHD_TITLE", re.findall(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)[:3])
        print("MHD_FORMS", re.findall(r"<form[^>]+action=[\"']([^\"']+)", text, re.I)[:20])
        print("MHD_SCRIPTS", re.findall(r"<script[^>]+src=[\"']([^\"']+)", text, re.I)[:30])
        print("MHD_LINKS", [x for x in re.findall(r"href=[\"']([^\"']+)", text, re.I) if "inspection" in x.lower()][:30])
        print("MHD_SNIPPET", re.sub(r"\s+", " ", text[:3000]))
        assert response.status_code == 200
