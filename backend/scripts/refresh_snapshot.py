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
    get_operational_intelligence,
    get_pm25,
    get_weather,
    write_json,
)
from app.text import repair_thai_mojibake_tree

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_snapshot")


def build_hotspots(settings) -> HotspotResponse:
    # Reconcile every reachable source (RFD + GISTDA Disaster + GISTDA API
    # Gateway + NASA). From a Thai egress RFD works; key-backed sources join
    # when configured.
    logger.info("Fetching + reconciling hotspots from all sources")
    response = fetch_live_hotspots(
        settings.gistda_api_key,
        settings.nasa_firms_map_key,
        settings.gistda_disaster_api_key,
    )
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

    # --- Fetch live hotspots (best-effort) ---
    # If all sources genuinely return 0 (e.g. rainy season, no active fires),
    # we accept 0 and write it. We only abort on network/auth errors (fetch_live_hotspots
    # raises an exception in those cases). This way PM2.5 and weather in the
    # dashboardSnapshot are always refreshed even when there are no hotspots.
    try:
        hotspots = build_hotspots(settings)
        logger.info("Reconciled %d unique hotspots", hotspots.count)
    except Exception as exc:  # noqa: BLE001 — network/auth failure, not a "0 count" result
        logger.error("Hotspot fetch failed: %s", exc)
        # Fall back to the existing snapshot so PM2.5/weather can still refresh.
        existing_path = settings.cache_dir / "hotspots.json"
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                hotspots = HotspotResponse(**existing)
                logger.warning(
                    "Using existing hotspot snapshot (%d hotspots) — PM2.5/weather will still refresh.",
                    hotspots.count,
                )
            except Exception as load_exc:  # noqa: BLE001
                logger.error("Could not load existing hotspot snapshot: %s — aborting.", load_exc)
                return 1
        else:
            logger.error("No existing hotspot snapshot and live fetch failed — aborting.")
            return 1

    # --- Idempotency check for hotspots.json ---
    # Write only when the reconciled set actually changed.
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

    if hotspots_changed:
        write_json(settings.cache_dir, "hotspots.json", new_dump)

    # --- Always refresh PM2.5, weather, and the full dashboardSnapshot ---
    # These have their own update cadence and should refresh on every run
    # regardless of whether hotspots changed.
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = fallback_summary(pm25, hotspots, weather, risk)
    intelligence = get_operational_intelligence(hotspots, pm25, weather, risk)
    dashboard = DashboardResponse(
        hotspots=hotspots,
        pm25=pm25,
        weather=weather,
        risk=risk,
        summary=summary,
        intelligence=intelligence,
    )
    frontend_data = REPO_DIR / "frontend" / "src" / "data"
    write_json(frontend_data, "dashboardSnapshot.json", dashboard.model_dump())

    logger.info("Wrote dashboardSnapshot.json (hotspot_count=%d)", hotspots.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
