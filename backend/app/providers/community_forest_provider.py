"""Community forest data from thaicfnet.org public API.

Fetches all community forests in Chiang Mai province and caches for 24 hours.
Field structure:
  addresses[0] = [house_num, village, tambon, amphoe, province, ...]
  geo.geoLat / geo.geoLong = GPS coordinates
  forestType = list of forest type strings
  fireManagementCheck = non-empty list means fire management plan active
  fireManagementActivityCheck = list of fire activity descriptions
"""
import logging
import time
from typing import Any

import httpx

from app.models import CommunityForest

logger = logging.getLogger(__name__)

_THAICFNET_URL = "https://thaicfnet.org/api/cf/province/เชียงใหม่"
_CACHE_TTL = 86_400.0  # 24 hours — data changes slowly

_cache: tuple[float, list[CommunityForest]] | None = None


def _parse_record(raw: dict[str, Any]) -> CommunityForest | None:
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
            return None  # can't locate without district

        forest_types = [str(t).strip() for t in (raw.get("forestType") or []) if t]
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
            forest_types=forest_types,
            fire_management_active=bool(fire_mgmt),
            fire_activities=fire_activities,
        )
    except Exception as exc:
        logger.debug("Skip community forest record (parse error): %s", exc)
        return None


def fetch_community_forests() -> list[CommunityForest]:
    global _cache

    if _cache is not None:
        ts, forests = _cache
        if time.monotonic() - ts < _CACHE_TTL:
            return forests

    logger.info("Fetching community forests from thaicfnet.org")
    try:
        response = httpx.get(
            _THAICFNET_URL,
            timeout=30.0,
            headers={"User-Agent": "ChiangMaiEyes/1.0 (fire-risk-dashboard)"},
        )
        response.raise_for_status()
        data = response.json()

        forests: list[CommunityForest] = []
        for record in data:
            parsed = _parse_record(record)
            if parsed is not None:
                forests.append(parsed)

        logger.info("Loaded %d community forests from thaicfnet.org", len(forests))
        _cache = (time.monotonic(), forests)
        return forests

    except Exception as exc:
        logger.error("Failed to fetch community forests: %s", exc)
        if _cache is not None:
            logger.warning("Returning stale community forest cache")
            return _cache[1]
        return []
