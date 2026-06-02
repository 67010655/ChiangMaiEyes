"""Refresh hotspot snapshots from today's RFD Firemap data.

Why this exists: the production backend (Vercel) cannot reach the Royal
Forest Department Firemap from its datacenter, so it always falls back to
the baked-in snapshot files. This script regenerates those snapshots from
a network that *can* reach RFD (e.g. a Thailand egress, or — if reachable —
a CI runner), so the deployed fallback stays fresh.

It writes:
  - backend/data/hotspots.json                 (backend fallback)
  - frontend/src/data/dashboardSnapshot.json   (UI fallback when API fails)

Safety: if the RFD fetch fails or returns zero hotspots, it writes NOTHING
and exits non-zero, so we never clobber good data with an empty result.

Run from anywhere; paths are resolved relative to the repo, and the backend
package is importable because we add backend/ to sys.path.
"""
import datetime
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.models import DashboardResponse, HotspotResponse
from app.providers.hotspot_provider import (
    BANGKOK_TZ,
    FOREST_FIREMAP_SOURCE,
    fetch_forest_firemap_hotspots,
    merge_hotspots,
)
from app.services import (
    calculate_risk,
    fallback_summary,
    get_pm25,
    get_weather,
    write_json,
)
from app.text import repair_thai_mojibake_tree

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_snapshot")


def build_hotspots() -> HotspotResponse:
    today = datetime.datetime.now(BANGKOK_TZ).date()
    logger.info("Fetching RFD Firemap hotspots for %s", today)
    forest = merge_hotspots([fetch_forest_firemap_hotspots(today)])
    count = len(forest)
    if count == 0:
        raise RuntimeError("RFD Firemap returned 0 hotspots — refusing to overwrite snapshot")

    density = round((count / 20107.0) * 100.0, 2)
    now = datetime.datetime.now(BANGKOK_TZ).isoformat()
    response = HotspotResponse(
        count=count,
        density_per_100_km2=density,
        latest_update=now,
        source=FOREST_FIREMAP_SOURCE,
        items=forest,
    )
    # Same post-processing the backend applies before caching.
    return HotspotResponse(**repair_thai_mojibake_tree(response.model_dump()))


def main() -> int:
    settings = get_settings()
    try:
        hotspots = build_hotspots()
    except Exception as exc:  # noqa: BLE001 — top-level guard, report and bail
        logger.error("Aborting without changes: %s", exc)
        return 1

    logger.info("Got %d hotspots from RFD Firemap", hotspots.count)

    # Backend fallback file.
    write_json(settings.cache_dir, "hotspots.json", hotspots.model_dump())

    # Full dashboard snapshot for the frontend; pm25/weather fall back to their
    # own cached files if their live providers are unreachable from this runner.
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = fallback_summary(pm25, hotspots, weather, risk)
    dashboard = DashboardResponse(
        hotspots=hotspots, pm25=pm25, weather=weather, risk=risk, summary=summary
    )
    frontend_data = REPO_DIR / "frontend" / "src" / "data"
    write_json(frontend_data, "dashboardSnapshot.json", dashboard.model_dump())

    logger.info("Wrote hotspots.json and dashboardSnapshot.json (count=%d)", hotspots.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
