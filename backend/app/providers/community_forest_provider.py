"""Community forest data — merges two sources:

1. Royal Forest Department community-forest boundary shapefile (converted
   from the agency's official UTM Zone 47N shapefile — 677 real Chiang Mai
   plots, WGS84 polygons, provided directly by the user's agency contact in
   2024). Primary source: real boundary polygon per plot, real area_rai,
   village/moo/tambon/amphoe.
2. thaicfnet.org public API (live, ~21 Chiang Mai records) — supplemental,
   ENRICHMENT ONLY: adds fire-management-activity detail to a matching
   official record by (name, amphoe); a thaicfnet record with no official
   match is dropped rather than added as an extra entry. This keeps the
   total forest count locked to exactly the agency's 677 — the user
   explicitly asked that every part of the app reference that one number,
   not "677 plus whatever thaicfnet happens to add today."

The RFD snapshot is loaded from disk on startup (static); thaicfnet is
fetched and cached for 24 hours.
"""
import json
import logging
import pathlib
import time
from typing import Any

import httpx

from app.models import CommunityForest
from app.providers.hotspot_provider import estimate_district

logger = logging.getLogger(__name__)

_THAICFNET_URL = "https://thaicfnet.org/api/cf/province/เชียงใหม่"
_CACHE_TTL = 86_400.0  # 24 hours

_thaicfnet_cache: tuple[float, list[dict[str, Any]]] | None = None

_OFFICIAL_GEOJSON = pathlib.Path(__file__).parent.parent / "data" / "community-forests-chiangmai.geojson"


# ---------------------------------------------------------------------------
# Official RFD shapefile (677 real Chiang Mai polygons)
# ---------------------------------------------------------------------------

def _load_official() -> list[CommunityForest]:
    """Load the converted agency shapefile (GeoJSON FeatureCollection, real
    polygon boundaries). Returns empty list on any error — this is the
    authoritative source, so a load failure should be loud in logs, not
    crash the whole /api/community-forests endpoint."""
    if not _OFFICIAL_GEOJSON.exists():
        logger.error("Official community-forests GeoJSON not found at %s", _OFFICIAL_GEOJSON)
        return []
    try:
        raw = json.loads(_OFFICIAL_GEOJSON.read_text(encoding="utf-8"))
        features = raw.get("features", [])
        forests: list[CommunityForest] = []
        for feat in features:
            props = feat.get("properties", {})
            lat, lng = props.get("lat"), props.get("lng")
            amphoe = str(props.get("amphoe") or "").strip()
            if lat is None or lng is None or not amphoe:
                continue
            forests.append(CommunityForest(
                forest_id=str(props.get("id") or f"cmf-{amphoe}-{len(forests)}"),
                name=str(props.get("name") or props.get("village") or "ป่าชุมชน").strip(),
                village=str(props.get("village") or "").strip(),
                tambon=str(props.get("tambon") or "").strip(),
                amphoe=amphoe,
                latitude=float(lat),
                longitude=float(lng),
                forest_types=[],
                fire_management_active=False,
                fire_activities=[],
                area_rai=props.get("areaRai"),
                boundary_radius_m=None,
                boundary=feat.get("geometry"),
                source="Royal Forest Department (agency shapefile, real polygon boundary)",
            ))
        logger.info("Loaded %d community forest polygons from agency shapefile", len(forests))
        return forests
    except Exception as exc:
        logger.error("Failed to load official community forests GeoJSON: %s", exc)
        return []


# Load once at import time — data is static.
_official_forests: list[CommunityForest] = _load_official()


# ---------------------------------------------------------------------------
# thaicfnet live fetch (enrichment only — see module docstring)
# ---------------------------------------------------------------------------

def _thaicfnet_key(raw: dict[str, Any]) -> tuple[str, str, list[str], bool] | None:
    """Extract (name, amphoe, fire_activities, fire_management_active) from a
    raw thaicfnet record, or None if it can't be matched to anything."""
    try:
        addresses = raw.get("addresses") or []
        addr: list = addresses[0] if addresses else []

        def _addr(idx: int) -> str:
            return str(addr[idx]).strip() if len(addr) > idx else ""

        amphoe = _addr(3)
        if not amphoe:
            return None
        name = str(raw.get("name") or "").strip() or _addr(1)
        fire_activities = [str(a).strip() for a in (raw.get("fireManagementActivityCheck") or []) if a]
        fire_management_active = bool(raw.get("fireManagementCheck") or [])
        return name, amphoe, fire_activities, fire_management_active
    except Exception as exc:
        logger.debug("Skip thaicfnet record: %s", exc)
        return None


def _fetch_thaicfnet() -> list[dict[str, Any]]:
    global _thaicfnet_cache
    if _thaicfnet_cache is not None:
        ts, records = _thaicfnet_cache
        if time.monotonic() - ts < _CACHE_TTL:
            return records
    try:
        resp = httpx.get(_THAICFNET_URL, timeout=30.0,
                         headers={"User-Agent": "ChiangMaiEyes/1.0"})
        resp.raise_for_status()
        records = resp.json()
        logger.info("Fetched %d records from thaicfnet.org", len(records))
        _thaicfnet_cache = (time.monotonic(), records)
        return records
    except Exception as exc:
        logger.warning("thaicfnet fetch failed (%s); using cached or empty", exc)
        return _thaicfnet_cache[1] if _thaicfnet_cache else []


# ---------------------------------------------------------------------------
# Merged result
# ---------------------------------------------------------------------------

def _correct_amphoe(forests: list[CommunityForest]) -> list[CommunityForest]:
    """The RFD/thaicfnet source's own amphoe label doesn't always match the
    real district polygon actually containing the point — confirmed by
    direct check, not assumed: 14 of 675 official records (~2%, previous
    point-only source) sat inside a different district's real boundary than
    their claimed amphoe. Same class of bug already fixed for hotspots —
    reuse that exact real-polygon-first helper instead of trusting the
    source label."""
    corrected = []
    for f in forests:
        real = estimate_district(f.latitude, f.longitude)
        corrected.append(f.model_copy(update={"amphoe": real}) if real and real != f.amphoe else f)
    return corrected


def fetch_community_forests() -> list[CommunityForest]:
    """677 official agency polygons, always — thaicfnet only ever enriches a
    matching record's fire-management fields, never adds to the count."""
    official = _official_forests  # already loaded

    thaicfnet_by_key: dict[tuple[str, str], tuple[list[str], bool]] = {}
    for raw in _fetch_thaicfnet():
        parsed = _thaicfnet_key(raw)
        if parsed is None:
            continue
        name, amphoe, fire_activities, fire_management_active = parsed
        thaicfnet_by_key[(name.strip(), amphoe.strip())] = (fire_activities, fire_management_active)

    enriched_count = 0
    enriched: list[CommunityForest] = []
    for f in official:
        match = thaicfnet_by_key.get((f.name.strip(), f.amphoe.strip()))
        if match:
            fire_activities, fire_management_active = match
            f = f.model_copy(update={
                "fire_activities": fire_activities,
                "fire_management_active": fire_management_active,
            })
            enriched_count += 1
        enriched.append(f)

    merged = _correct_amphoe(enriched)
    logger.info(
        "Community forests: %d official polygons (%d enriched with thaicfnet activity data)",
        len(merged), enriched_count,
    )
    return merged
