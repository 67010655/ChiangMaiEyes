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
import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.models import DashboardResponse, HotspotResponse
from app.providers.hotspot_provider import fetch_live_hotspots
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


def build_hotspots(settings) -> HotspotResponse:
    # Reconcile every reachable source (RFD + GISTDA + NASA). From a Thai egress
    # RFD works; NASA/GISTDA join when their keys are configured.
    logger.info("Fetching + reconciling hotspots from all sources")
    response = fetch_live_hotspots(settings.gistda_api_key, settings.nasa_firms_map_key)
    if response.count == 0:
        raise RuntimeError("All hotspot sources returned 0 — refusing to overwrite snapshot")
    logger.info("Source breakdown: %s → %d unique", response.source_breakdown, response.count)
    # Same post-processing the backend applies before caching.
    return HotspotResponse(**repair_thai_mojibake_tree(response.model_dump()))


def _hotspot_fingerprint(items: list[dict]) -> list[tuple]:
    """Identity of the hotspot set, ignoring volatile fields (id, timestamps)."""
    return sorted(
        (
            round(i["latitude"], 4),
            round(i["longitude"], 4),
            i.get("detected_at", "")[:10],
            i.get("confidence"),
            tuple(sorted(i.get("sources") or [])),
        )
        for i in items
    )


def main() -> int:
    settings = get_settings()
    try:
        hotspots = build_hotspots(settings)
    except Exception as exc:  # noqa: BLE001 — top-level guard, report and bail
        logger.error("Aborting without changes: %s", exc)
        return 1

    logger.info("Reconciled %d unique hotspots", hotspots.count)

    # Idempotency: keep the hotspot fallback stable when the reconciled set is
    # unchanged, but still refresh the full dashboard snapshot because weather
    # and PM2.5 have their own update cadence.
    new_dump = hotspots.model_dump()
    existing_path = settings.cache_dir / "hotspots.json"
    hotspots_changed = True
    if existing_path.exists():
        try:
            old = json.loads(existing_path.read_text(encoding="utf-8"))
            if _hotspot_fingerprint(old.get("items", [])) == _hotspot_fingerprint(new_dump["items"]):
                logger.info("Hotspots unchanged (%d) — keeping existing hotspot fallback.", hotspots.count)
                hotspots_changed = False
        except Exception as exc:  # noqa: BLE001 — comparison is best-effort
            logger.warning("Could not compare with existing snapshot: %s", exc)

    # Backend fallback file.
    if hotspots_changed:
        write_json(settings.cache_dir, "hotspots.json", new_dump)

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
