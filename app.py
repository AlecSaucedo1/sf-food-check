from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


def db():
    con = connect(DB_PATH)
    if not USE_LIVE_DATA:
        seed_demo(con, str(DEMO_PATH))
    return con


def add_consumer_risk(result: dict) -> dict:
    """Add deterministic, non-official risk summaries to inspection details."""
    for inspection in result.get("inspections", []):
        existing = inspection.get("violations") or []
        assessed = []
        if existing:
            for v in existing:
                derived = assess_violation(
                    v.get("official_description") or v.get("code"),
                    official_description=v.get("official_description"),
                    code=v.get("code"),
                )
                # Preserve any richer manually imported fields while ensuring the
                # risk fields and consumer taxonomy are consistently populated.
                assessed.append({**v, **derived})
        else:
            assessed = [assess_violation(raw) for raw in inspection.get("violation_codes", [])]

        inspection["violations"] = assessed
        inspection["risk"] = assess_inspection(
            assessed,
            status=inspection.get("facility_rating_status", ""),
            violation_count=int(inspection.get("violation_count") or len(assessed)),
        )
    if result.get("inspections"):
        result["latest_risk"] = result["inspections"][0].get("risk")
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


app = FastAPI(title="SF Food Check API", version="0.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def production_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=(), usb=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if request.url.path.startswith("/api/"):
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
    return {"ok": bool(count), "inspection_rows": count, "facility_count": facilities, "latest_inspection_date": latest, "demo_mode": not USE_LIVE_DATA, "comment_records": comments, "comment_coverage_pct": round((inspections_with_comments / count) * 100, 1) if count else 0.0, "last_sync": sync}


@app.get("/api/ready")
def ready():
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    if not count:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "No inspection data loaded"})
    return {"ok": True}


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
        "affiliation_disclaimer": "SF Food Check is an independent project and is not affiliated with or endorsed by the City and County of San Francisco.",
    }


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
