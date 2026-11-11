from datetime import datetime, timezone

import httpx
import pytest

from scripts import check_freshness


def test_revision_comparison_is_utc_aware_and_ignores_bad_future_inspection_dates():
    assert check_freshness.needs_refresh("2026-11-11T02:36:34.752", "2026-08-15T22:53:23+00:00")
    assert not check_freshness.needs_refresh("2026-11-11T02:36:34.752", "2026-11-11T12:00:00+00:00")
    assert check_freshness.needs_refresh("2026-11-11T02:36:34.752", "2026-11-11T12:00:00+00:00", force=True)
    assert check_freshness.needs_refresh("2026-11-11T02:36:34.752", None)


def test_revision_check_compares_upstream_load_time_to_live_sync(monkeypatch):
    monkeypatch.setattr(check_freshness, "BASE", "https://example.test/resource")
    monkeypatch.setattr(check_freshness, "HEALTH_URL", "https://app.test/api/health")
    def handler(request):
        if request.url.host == "example.test":
            assert "data_loaded_at" in request.url.params["$select"]
            return httpx.Response(200, json=[{"latest_load": "2026-11-11T02:36:34.752", "row_count": "23058"}])
        return httpx.Response(200, json={"last_sync": {"success": 1, "completed_at": "2026-08-15T22:53:23+00:00"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = check_freshness.check_revision(client)
    assert result["required"] is True
    assert result["source_rows"] == 23058


def test_revision_check_fails_on_partial_source(monkeypatch):
    monkeypatch.setattr(check_freshness, "BASE", "https://example.test/resource")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=[{"latest_load": "2026-11-11T02:36:34.752", "row_count": "10"}]
    ))) as client:
        with pytest.raises(RuntimeError, match="unexpectedly small"):
            check_freshness.check_revision(client)
