"""Community forest data — merges two sources:

1. Royal Forest Department KML export (bundled JSON, 675 records, 23 amphoes)
   — primary; has area_rai and estimated boundary radius.
2. thaicfnet.org public API (live, ~21 records, 6 amphoes)
   — supplemental; has fire-management activity detail.

Merged result is deduplicated by (name, amphoe).  The RFD snapshot is loaded
from disk on startup; thaicfnet is fetched and cached for 24 hours.
"""
import json
import logging
import pathlib
import time
from typing import Any

import httpx

from app.models import CommunityForest

logger = logging.getLogger(__name__)

_THAICFNET_URL = "https://thaicfnet.org/api/cf/province/เชียงใหม่"
_CACHE_TTL = 86_400.0  # 24 hours

_thaicfnet_cache: tuple[float, list[CommunityForest]] | None = None

_OFFICIAL_JSON = pathlib.Path(__file__).parent.parent / "data" / "community-forests-official.json"


# ---------------------------------------------------------------------------
# Official RFD snapshot (675 records)
# ---------------------------------------------------------------------------

def _load_official() -> list[CommunityForest]:
    """Load bundled RFD KML export. Returns empty list on any error."""
    if not _OFFICIAL_JSON.exists():
        logger.warning("Official community-forests JSON not found at %s", _OFFICIAL_JSON)
        return []
    try:
        raw = json.loads(_OFFICIAL_JSON.read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else raw.get("forests", raw.get("features", []))
        forests: list[CommunityForest] = []
        for r in records:
            props = r.get("properties", r)
            lat = props.get("lat") or props.get("latitude")
            lng = props.get("lng") or props.get("longitude")
            if not lat or not lng:
                continue
            amphoe = str(props.get("amphoe") or "").strip()
            if not amphoe:
                continue
            area = props.get("areaRai") or props.get("area_rai")
            radius = props.get("estimatedBoundaryRadiusM") or props.get("boundary_radius_m")
            forests.append(CommunityForest(
                forest_id=str(props.get("id") or f"rfd-{amphoe}-{len(forests)}"),
                name=str(props.get("name") or props.get("village") or "ป่าชุมชน").strip(),
                village=str(props.get("village") or "").strip(),
                tambon=str(props.get("tambon") or "").strip(),
                amphoe=amphoe,
                latitude=float(lat),
                longitude=float(lng),
                forest_types=[],
                fire_management_active=False,
                fire_activities=[],
                area_rai=float(area) if area is not None else None,
                boundary_radius_m=int(radius) if radius is not None else None,
                source="Royal Forest Department",
            ))
        logger.info("Loaded %d community forests from RFD official snapshot", len(forests))
        return forests
    except Exception as exc:
        logger.error("Failed to load official community forests JSON: %s", exc)
        return []


# Load once at import time — data is static.
_official_forests: list[CommunityForest] = _load_official()


# ---------------------------------------------------------------------------
# thaicfnet live fetch (supplemental)
# ---------------------------------------------------------------------------

def _parse_thaicfnet(raw: dict[str, Any]) -> CommunityForest | None:
    try:
        geo = raw.get("geo") or {}
        lat = float(geo.get("geoLat") or 0)
        lon = float(geo.get("geoLong") or 0)
        if not lat or not lon:
            return None
        addresses = raw.get("addresses") or []
        addr: list = addresses[0] if addresses else []

        def _addr(idx: int) -> str:
            return str(addr[idx]).strip() if len(addr) > idx else ""

        village = _addr(1)
        tambon = _addr(2)
        amphoe = _addr(3)
        if not amphoe:
            return None

        fire_mgmt = raw.get("fireManagementCheck") or []
        fire_activities = [str(a).strip() for a in (raw.get("fireManagementActivityCheck") or []) if a]
        record_id = str(raw.get("_id") or raw.get("id") or "")
        forest_id = f"cf-thaicfnet-{record_id}" if record_id else f"cf-{amphoe}-{village}"

        return CommunityForest(
            forest_id=forest_id,
            name=str(raw.get("name") or "").strip() or village,
            village=village,
            tambon=tambon,
            amphoe=amphoe,
            latitude=lat,
            longitude=lon,
            forest_types=[str(t).strip() for t in (raw.get("forestType") or []) if t],
            fire_management_active=bool(fire_mgmt),
            fire_activities=fire_activities,
            source="thaicfnet.org",
        )
    except Exception as exc:
        logger.debug("Skip thaicfnet record: %s", exc)
        return None


def _fetch_thaicfnet() -> list[CommunityForest]:
    global _thaicfnet_cache
    if _thaicfnet_cache is not None:
        ts, forests = _thaicfnet_cache
        if time.monotonic() - ts < _CACHE_TTL:
            return forests
    try:
        resp = httpx.get(_THAICFNET_URL, timeout=30.0,
                         headers={"User-Agent": "ChiangMaiEyes/1.0"})
        resp.raise_for_status()
        forests = [f for r in resp.json() if (f := _parse_thaicfnet(r)) is not None]
        logger.info("Fetched %d forests from thaicfnet.org", len(forests))
        _thaicfnet_cache = (time.monotonic(), forests)
        return forests
    except Exception as exc:
        logger.warning("thaicfnet fetch failed (%s); using cached or empty", exc)
        return _thaicfnet_cache[1] if _thaicfnet_cache else []


# ---------------------------------------------------------------------------
# Merged result
# ---------------------------------------------------------------------------

def fetch_community_forests() -> list[CommunityForest]:
    """Merge RFD official (primary) + thaicfnet (supplemental, live data)."""
    official = _official_forests  # already loaded

    # thaicfnet adds fire-management detail not in the RFD snapshot.
    live = _fetch_thaicfnet()

    # Dedup: keep all official records; skip thaicfnet records whose
    # (name, amphoe) already exist in official set.
    official_keys = {(f.name.strip(), f.amphoe.strip()) for f in official}
    extra = [f for f in live if (f.name.strip(), f.amphoe.strip()) not in official_keys]

    merged = official + extra
    logger.info(
        "Community forests merged: %d official + %d thaicfnet-only = %d total",
        len(official), len(extra), len(merged),
    )
    return merged
