from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.leaderboards import build_leaderboards
from backend.store import connect, latest_sync_run, list_restaurants, nearby, restaurant_detail, seed_demo
from backend.sync_service import sync_once
from backend.taxonomy import assess_inspection, assess_violation

ROOT = Path(__file__).resolve().parent
ON_RENDER = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_URL"))
DEFAULT_DB_PATH = "/var/data/inspections.db" if ON_RENDER else str(ROOT / "data" / "inspections.db")
DB_PATH = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
DEMO_PATH = ROOT / "data" / "demo.json"
USE_LIVE_DATA = os.getenv("USE_LIVE_DATA", "1" if ON_RENDER else "0") == "1"
SYNC_BACKGROUND = os.getenv("SYNC_BACKGROUND", "1" if ON_RENDER else "0") == "1"
SYNC_INTERVAL_HOURS = max(1.0, float(os.getenv("SYNC_INTERVAL_HOURS", "24")))
APP_VERSION = "0.6.0"
RISK_MODEL_VERSION = "2026.08.14.3"


def db():
    con = connect(DB_PATH)
    if not USE_LIVE_DATA:
        seed_demo(con, str(DEMO_PATH))
    return con


def _violation_key(item: dict) -> tuple[str, str]:
    code = str(item.get("code") or "").strip().lower()
    desc = " ".join(str(item.get("official_description") or "").lower().split())
    return code, desc


def add_consumer_risk(result: dict) -> dict:
    """Add deterministic, non-official risk summaries to inspection details.

    Manually imported violation records are retained, then supplemented by violation
    fields recovered from the raw DataSF inspection row. This allows the live site to
    use DataSF's actual descriptions instead of treating every item as a bare code.
    """
    for inspection in result.get("inspections", []):
        candidates: list[dict] = []
        candidates.extend(inspection.get("violations") or [])
        candidates.extend(inspection.pop("source_violations", []) or [])

        assessed: list[dict] = []
        code_index: dict[str, int] = {}
        desc_seen: set[str] = set()
        for item in candidates:
            derived = assess_violation(
                item.get("official_description") or item.get("code"),
                official_description=item.get("official_description"),
                code=item.get("code"),
                official_risk_category=item.get("official_risk_category") or item.get("risk_level"),
                source_field=item.get("source_field"),
            )
            code, desc = _violation_key(derived)
            if code and code in code_index:
                existing = assessed[code_index[code]]
                if not existing.get("official_description") and derived.get("official_description"):
                    assessed[code_index[code]] = {**existing, **derived}
                continue
            if not code and desc and desc in desc_seen:
                continue
            if code:
                code_index[code] = len(assessed)
            if desc:
                desc_seen.add(desc)
            assessed.append(derived)

        published_count = int(inspection.get("violation_count") or 0)
        display_count = len(assessed) if assessed else published_count
        inspection["violations"] = assessed
        inspection["display_violation_count"] = display_count
        inspection["mapping"] = {
            "mapped_count": sum(1 for v in assessed if v.get("official_description")),
            "published_count": published_count,
            "source_fields": inspection.pop("source_violation_fields", []),
        }
        inspection["risk"] = assess_inspection(
            assessed,
            status=inspection.get("facility_rating_status", ""),
            violation_count=published_count or display_count,
        )
        inspection["risk"]["model_version"] = RISK_MODEL_VERSION

    if result.get("inspections"):
        result["latest_risk"] = result["inspections"][0].get("risk")
    result["app_version"] = APP_VERSION
    result["risk_model_version"] = RISK_MODEL_VERSION
    return result


async def periodic_sync() -> None:
    while True:
        await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)
        try:
            await sync_once(DB_PATH)
        except Exception as exc:
            print(f"Background DataSF sync failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if USE_LIVE_DATA and SYNC_BACKGROUND:
        task = asyncio.create_task(periodic_sync())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="SF Food Check API", version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def production_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=(), usb=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if request.url.path == "/static/sw.js":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    elif request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "public, max-age=60, stale-while-revalidate=300")
    elif request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    return response


@app.get("/api/health")
def health():
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
        latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]
        comments = con.execute("SELECT COUNT(*) FROM report_enrichment WHERE COALESCE(inspector_comments,'') <> ''").fetchone()[0]
        inspections_with_comments = con.execute("""SELECT COUNT(*) FROM inspections i
            WHERE EXISTS (
              SELECT 1 FROM report_enrichment r
              WHERE r.permit_number=i.permit_number AND r.inspection_date=i.inspection_date
                AND COALESCE(r.inspector_comments,'') <> ''
            )""").fetchone()[0]
        sync = latest_sync_run(con)
    return {"ok": bool(count), "app_version": APP_VERSION, "risk_model_version": RISK_MODEL_VERSION, "inspection_rows": count, "facility_count": facilities, "latest_inspection_date": latest, "demo_mode": not USE_LIVE_DATA, "comment_records": comments, "comment_coverage_pct": round((inspections_with_comments / count) * 100, 1) if count else 0.0, "last_sync": sync}


@app.get("/api/ready")
def ready():
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    if not count:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "No inspection data loaded"})
    return {"ok": True, "app_version": APP_VERSION}


@app.get("/api/meta")
def meta():
    with db() as con:
        neighborhoods = [r[0] for r in con.execute("SELECT DISTINCT analysis_neighborhood FROM inspections WHERE analysis_neighborhood<>'' ORDER BY 1")]
    return {
        "city": "San Francisco",
        "official_statuses": ["Pass", "Conditional Pass", "Closure"],
        "neighborhoods": neighborhoods,
        "data_source": "San Francisco Department of Public Health / DataSF",
        "dataset_id": "tvy3-wexg",
        "dataset_url": "https://data.sfgov.org/d/tvy3-wexg",
        "report_lookup_url": "https://inspections.myhealthdepartment.com/san-francisco",
        "comment_policy": "Inspector comments are displayed verbatim only when linked to an official report enrichment record.",
        "risk_methodology": "Foodborne Illness Risk Index is an independent relative severity indicator based on how directly a published finding can contribute to contamination, pathogen growth, or pathogen survival. It is not a probability and not an official SFDPH score.",
        "risk_model_version": RISK_MODEL_VERSION,
        "affiliation_disclaimer": "SF Food Check is an independent project and is not affiliated with or endorsed by the City and County of San Francisco.",
    }


@app.get("/api/leaderboards")
def leaderboards(
    limit: int = Query(10, ge=1, le=25),
    months: int = Query(18, ge=6, le=36),
):
    with db() as con:
        return build_leaderboards(
            con,
            model_version=RISK_MODEL_VERSION,
            months=months,
            minimum_chain_locations=3,
            minimum_neighborhood_restaurants=25,
            limit=limit,
        )


@app.get("/api/restaurants")
def restaurants(q: str = "", status: str = "", neighborhood: str = "", limit: int = Query(50, ge=1, le=200)):
    with db() as con:
        return list_restaurants(con, q=q, status=status, neighborhood=neighborhood, limit=limit)


@app.get("/api/restaurants/{permit_number}")
def restaurant(permit_number: str):
    with db() as con:
        result = restaurant_detail(con, permit_number)
    if not result:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return add_consumer_risk(result)


@app.get("/api/nearby")
def restaurants_nearby(lat: float, lon: float, radius_km: float = Query(2.0, ge=0.1, le=20), limit: int = Query(50, ge=1, le=200)):
    with db() as con:
        return nearby(con, lat, lon, radius_km=radius_km, limit=limit)


@app.get("/robots.txt")
def robots():
    return FileResponse(ROOT / "static" / "robots.txt", media_type="text/plain")


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/{path:path}")
def spa_fallback(path: str):
    if path.startswith("api/") or path.startswith("static/"):
        raise HTTPException(status_code=404)
    return FileResponse(ROOT / "static" / "index.html")
