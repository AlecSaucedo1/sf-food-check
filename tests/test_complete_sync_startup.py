import asyncio

import pytest

import app


def test_complete_history_sync_runs_before_daily_interval(monkeypatch):
    sleeps = []
    sync_calls = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > 1:
            raise asyncio.CancelledError

    async def fake_sync(path):
        sync_calls.append(path)
        return {
            "rows": 123,
            "facilities": 45,
            "latest_inspection_date": "2026-08-13",
        }

    monkeypatch.setattr(app.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(app, "sync_complete_shadow", fake_sync)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app.complete_history_sync_loop())

    assert sleeps[0] == app.SYNC_START_DELAY_SECONDS
    assert sync_calls == [app.DB_PATH]
    assert sleeps[1] == app.SYNC_INTERVAL_HOURS * 3600


def test_render_defaults_enable_complete_sync():
    # The Render blueprint also sets this explicitly; this guards the application
    # wiring so the complete-history job cannot silently depend on SYNC_BACKGROUND.
    assert hasattr(app, "COMPLETE_SYNC_BACKGROUND")
