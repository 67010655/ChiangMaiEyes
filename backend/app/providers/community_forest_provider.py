"""Community forest data — merges two sources:

The boundary shapefile received from RECOFTC is the sole source for the
community-forest count and geometries. thaicfnet activity data may enrich a
matching polygon, but never adds another forest. The converted GeoJSON is
loaded on startup; thaicfnet is cached for 24 hours.
"""
import json
import logging
import math
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


def boundary_quality(geometry):
    polygons = [geometry.get('coordinates',[])] if geometry.get('type')=='Polygon' else geometry.get('coordinates',[]) if geometry.get('type')=='MultiPolygon' else []
    invalid = not polygons
    for polygon in polygons:
        if not polygon:
            invalid = True
        for ring in polygon:
            if (len(ring)<4 or ring[0]!=ring[-1] or len({tuple(p) for p in ring[:-1]})<3
                or any(len(p)!=2 or not all(math.isfinite(v) for v in p) or not -180<=p[0]<=180 or not -90<=p[1]<=90 for p in ring)):
                invalid = True
    return ('needs_review','ขอบเขตต้นทางมีส่วนของรูปร่างไม่ครบ รักษาทะเบียนไว้และรอยืนยันกับเจ้าของข้อมูลก่อนใช้ตัดสินตำแหน่งเหตุ') if invalid else ('structural_check_passed','ผ่านการตรวจโครงสร้างพื้นฐาน ยังไม่ใช่การยืนยันขอบเขตภาคสนาม')

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
            quality,note = boundary_quality(feat.get('geometry') or {})
            forest_id = str(props.get('id') or f'cmf-{amphoe}-{len(forests)}')
            forests.append(CommunityForest(
                forest_id=forest_id,
                name=str(props.get("name") or props.get("village") or "ป่าชุมชน").strip(),
                village=str(props.get("village") or "").strip(),
                tambon=str(props.get("tambon") or "").strip(),
                amphoe=amphoe,
                latitude=float(lat),
                longitude=float(lng),
                # CGLS-derived subtypes were withdrawn after the Chiang Mai QA.
                # Keep all official boundaries, without point/subtype inference.
                forest_types=[],
                landcover_summary=None,
                fire_management_active=False,
                fire_activities=[],
                area_rai=props.get("areaRai"),
                boundary_radius_m=None,
                boundary=feat.get("geometry"),
                source="Community forest boundary shapefile received from RECOFTC",
                boundary_quality=quality, boundary_note=note,
            ))
        logger.info("Loaded %d community forest polygons from agency shapefile", len(forests))
        return forests
    except Exception as exc:
        logger.error("Failed to load official community forests GeoJSON: %s", exc)
        return []


# Load once at import time — data is static.
_official_forests: list[CommunityForest] = _load_official()


def official_community_forest_count() -> int:
    """Count the boundary records that the API can actually return."""
    return len(_official_forests)


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
    """Correct source district labels against the containing district polygon."""
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
