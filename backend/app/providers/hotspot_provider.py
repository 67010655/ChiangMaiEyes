import csv
import datetime
import json
import logging
import math
from functools import lru_cache
from pathlib import Path
import httpx
from app.models import Hotspot, HotspotResponse

logger = logging.getLogger(__name__)

# Chiang Mai province boundary (same polygon the UI draws its mask from).
# NASA FIRMS only supports a rectangular bbox query, so its results spill into
# neighbouring provinces at the corners; RFD/GISTDA are already province-filtered
# server-side. We clip every source to this polygon so the map never shows fires
# outside Chiang Mai.
_PROVINCE_GEOJSON = Path(__file__).resolve().parent.parent.parent / "data" / "chiangmai-province.json"


@lru_cache(maxsize=1)
def _province_ring() -> tuple[tuple[float, float], ...]:
    """Outer ring of the province polygon as ((lon, lat), ...), loaded once."""
    try:
        data = json.loads(_PROVINCE_GEOJSON.read_text(encoding="utf-8"))
        ring = data["coordinates"][0]
        return tuple((float(pt[0]), float(pt[1])) for pt in ring)
    except Exception as ex:  # noqa: BLE001 — missing/invalid file must not crash a fetch
        logger.error("Could not load province boundary %s: %s", _PROVINCE_GEOJSON, ex)
        return ()


def _point_in_ring(lon: float, lat: float, ring: tuple[tuple[float, float], ...]) -> bool:
    """Ray-casting point-in-polygon test (ring points are (lon, lat))."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def filter_to_province(hotspots: list[Hotspot]) -> list[Hotspot]:
    """Drop hotspots whose coordinates fall outside the Chiang Mai boundary.

    If the boundary failed to load, pass everything through rather than wiping
    out real data.
    """
    ring = _province_ring()
    if not ring:
        return hotspots
    kept = [h for h in hotspots if _point_in_ring(h.longitude, h.latitude, ring)]
    dropped = len(hotspots) - len(kept)
    if dropped:
        logger.info("Clipped %d hotspot(s) outside Chiang Mai province", dropped)
    return kept
GISTDA_VIIRS_SOURCE = "GISTDA API Gateway VIIRS 1-day"
FOREST_FIREMAP_SOURCE = "Royal Forest Department Firemap"
FOREST_FIREMAP_URL = "https://wildfire.forest.go.th/firemap/getdb.php"
BANGKOK_TZ = datetime.timezone(datetime.timedelta(hours=7))

# Approximate district boundaries using (lat, lon) ranges for Chiang Mai.
# Ordered so more specific checks come first; the fallback covers central areas.
_DISTRICT_BOUNDS: list[tuple[str, float, float, float, float]] = [
    # (name, lat_min, lat_max, lon_min, lon_max)
    ("แม่อาย",       19.85, 20.20, 99.00, 99.40),
    ("ฝาง",          19.60, 20.05, 98.85, 99.30),
    ("เชียงดาว",     19.10, 19.70, 98.70, 99.20),
    ("แม่แตง",       18.95, 19.25, 98.70, 99.10),
    ("กัลยาณิวัฒนา", 18.85, 19.25, 98.20, 98.55),
    ("สะเมิง",       18.65, 18.95, 98.50, 98.80),
    ("แม่แจ่ม",      18.25, 18.70, 98.10, 98.55),
    ("จอมทอง",       18.25, 18.55, 98.55, 98.85),
    ("ฮอด",          17.90, 18.30, 98.45, 98.75),
    ("อมก๋อย",       17.65, 18.10, 98.15, 98.55),
    ("ดอยสะเก็ด",    18.85, 19.10, 99.10, 99.45),
    ("สันทราย",      18.90, 19.05, 98.95, 99.15),
    ("สันกำแพง",     18.70, 18.90, 99.00, 99.25),
    ("แม่ออน",       18.60, 18.85, 99.15, 99.45),
    ("แม่วาง",       18.50, 18.75, 98.65, 98.90),
    ("หางดง",        18.60, 18.82, 98.85, 99.05),
    ("สารภี",        18.68, 18.80, 98.92, 99.10),
    ("แม่ริม",       18.85, 19.00, 98.85, 99.05),
]


def estimate_district(lat: float, lon: float) -> str:
    """Approximate Chiang Mai district from coordinates using bounding boxes."""
    for name, lat_min, lat_max, lon_min, lon_max in _DISTRICT_BOUNDS:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    # Fallback for coordinates that don't match any specific box
    if lat > 19.6:
        return "ฝาง"
    if lat < 18.2:
        return "ฮอด"
    return "เมืองเชียงใหม่"

def fetch_gistda_hotspots(api_key: str) -> list[Hotspot]:
    # GISTDA API Gateway daily VIIRS hotspots GeoJSON
    url = "https://api-gateway.gistda.or.th/api/2.0/resources/features/viirs/1day"
    logger.info("Fetching hotspots from GISTDA API Gateway")
    
    response = httpx.get(url, params={"api_key": api_key}, timeout=15.0)
    response.raise_for_status()
    data = response.json()
    
    features = data.get("features", [])
    hotspots: list[Hotspot] = []
    
    idx = 1
    for f in features:
        try:
            properties = f.get("properties", {})
            # Filter specifically for Chiang Mai province
            if properties.get("pv_tn") == "เชียงใหม่":
                geometry = f.get("geometry", {})
                coords = geometry.get("coordinates", [])
                if len(coords) < 2:
                    continue
                lon = float(coords[0])
                lat = float(coords[1])
                
                # Confidence mapping
                conf_raw = str(properties.get("confidence", "nominal")).lower()
                if conf_raw in ("high", "h"):
                    confidence = 90
                elif conf_raw in ("low", "l"):
                    confidence = 50
                else:
                    confidence = 75
                
                # Format update date/time from Thai date/time
                th_date = properties.get("th_date", "")
                th_time = properties.get("th_time", "0000")
                if th_date and len(th_time) == 4:
                    detected_at = f"{th_date[:10]}T{th_time[:2]}:{th_time[2:]}:00+07:00"
                else:
                    detected_at = datetime.datetime.now().isoformat()
                
                hotspots.append(Hotspot(
                    id=f"HS-GISTDA-{idx:03d}",
                    latitude=lat,
                    longitude=lon,
                    district=properties.get("ap_tn") or estimate_district(lat, lon),
                    confidence=confidence,
                    source=GISTDA_VIIRS_SOURCE,
                    detected_at=detected_at,
                    satellite="VIIRS"
                ))
                idx += 1
        except Exception as ex:
            logger.warning("Error parsing GISTDA API Gateway hotspot feature: %s", ex)
            continue
            
    return hotspots

def format_forest_detected_at(date_value: str | None, time_value: str | int | None) -> str:
    date_part = str(date_value or "").strip()[:10]
    if not date_part:
        date_part = datetime.datetime.now(BANGKOK_TZ).date().isoformat()

    time_digits = "".join(ch for ch in str(time_value or "0000") if ch.isdigit())
    time_digits = time_digits.zfill(4)[-4:]
    return f"{date_part}T{time_digits[:2]}:{time_digits[2:]}:00+07:00"

def fetch_forest_firemap_hotspots(target_date: datetime.date | None = None) -> list[Hotspot]:
    # Royal Forest Department Firemap mirrors the public dashboard filters.
    # Query TODAY only, so our headline count matches RFD's official daily count
    # for เชียงใหม่ (what users compare against). Before today's first satellite
    # pass (≈midnight–02:00) this is naturally low, same as RFD's own dashboard.
    query_date = (target_date or datetime.datetime.now(BANGKOK_TZ).date()).isoformat()
    params = {
        "datestart": query_date,
        "dateend": query_date,
        "province": "เชียงใหม่",
        "snpp": "on",
        "noaa20": "on",
        "noaa21": "on",
        "nighttime": "on",
        "daytime": "on",
    }
    logger.info("Fetching hotspots from Royal Forest Department Firemap")

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://wildfire.forest.go.th/firemap/index.html",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    response = httpx.get(FOREST_FIREMAP_URL, params=params, headers=headers, timeout=15.0)
    response.raise_for_status()
    data = response.json()
    rows = data.get("hotspot", [])

    hotspots: list[Hotspot] = []
    for idx, row in enumerate(rows, start=1):
        try:
            lat = float(row["LAT"])
            lon = float(row["LONG"])
            landuse_type = str(row.get("TYPE") or "").strip() or None
            landuse_name = str(row.get("NAME") or "").strip() or None
            confidence = 75 if landuse_type == "OTHER" else 90

            hotspots.append(Hotspot(
                id=f"HS-RFD-{idx:03d}",
                latitude=lat,
                longitude=lon,
                district=str(row.get("AUMPER") or "").strip() or estimate_district(lat, lon),
                subdistrict=str(row.get("TUMBON") or "").strip() or None,
                landuse_type=landuse_type,
                landuse_name=landuse_name,
                satellite="SNPP/NOAA-20/NOAA-21 VIIRS",
                confidence=confidence,
                source=FOREST_FIREMAP_SOURCE,
                detected_at=format_forest_detected_at(row.get("YYMMDD"), row.get("TIME")),
            ))
        except Exception as ex:
            logger.warning("Error parsing Royal Forest Department hotspot row: %s", ex)
            continue

    return hotspots

# RFD aggregates SNPP + NOAA-20 + NOAA-21 VIIRS; query all three so NASA is
# comparable rather than undercounting (SNPP alone is often empty for a day).
NASA_VIIRS_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")


def _nasa_detected_at(acq_date: str | None, acq_time: str | int | None) -> str:
    # NASA acq_date/acq_time are UTC; convert to Bangkok so the day matches RFD.
    date_part = str(acq_date or "").strip()[:10]
    digits = "".join(ch for ch in str(acq_time or "0000") if ch.isdigit()).zfill(4)[-4:]
    try:
        dt_utc = datetime.datetime.strptime(f"{date_part} {digits}", "%Y-%m-%d %H%M").replace(
            tzinfo=datetime.timezone.utc
        )
        return dt_utc.astimezone(BANGKOK_TZ).isoformat()
    except Exception:
        fallback_date = date_part or datetime.datetime.now(BANGKOK_TZ).date().isoformat()
        return f"{fallback_date}T00:00:00+07:00"


def fetch_nasa_firms_hotspots(map_key: str) -> list[Hotspot]:
    # NASA FIRMS Area API bounding box for Chiang Mai (west, south, east, north).
    bbox = "97.25,17.35,99.68,20.28"
    hotspots: list[Hotspot] = []
    idx = 0
    for src in NASA_VIIRS_SOURCES:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{src}/{bbox}/1"
        logger.info("Fetching hotspots from NASA FIRMS %s", src)
        try:
            response = httpx.get(url, timeout=15.0)
            response.raise_for_status()
        except Exception as ex:
            logger.warning("NASA FIRMS %s fetch failed: %s", src, ex)
            continue

        reader = csv.DictReader(response.content.decode("utf-8").splitlines())
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                conf_raw = str(row.get("confidence", "n")).lower()
                confidence = 90 if conf_raw == "h" else 75 if conf_raw == "n" else 50
                idx += 1
                hotspots.append(Hotspot(
                    id=f"HS-NASA-{idx:03d}",
                    latitude=lat,
                    longitude=lon,
                    district=estimate_district(lat, lon),
                    confidence=confidence,
                    source="NASA FIRMS",
                    detected_at=_nasa_detected_at(row.get("acq_date"), row.get("acq_time")),
                    satellite=row.get("satellite") or src,
                ))
            except Exception as ex:
                logger.warning("Error parsing NASA FIRMS hotspot row: %s", ex)
                continue

    return hotspots

def fetch_hotspot_history(map_key: str, days: int = 5) -> list[tuple[str, int]]:
    """Daily in-province hotspot counts for the last ``days`` days from NASA
    VIIRS, returned oldest→newest as (YYYY-MM-DD, count) with missing days
    zero-filled. NASA is reachable from anywhere (unlike RFD), so this gives a
    consistent historical trend on both the user's machine and Vercel.
    """
    ring = _province_ring()
    bbox = "97.25,17.35,99.68,20.28"
    span = max(1, min(days, 5))  # NASA Area API day range is capped at 5
    seen: set[tuple[float, float, str]] = set()
    per_day: dict[str, int] = {}

    for src in NASA_VIIRS_SOURCES:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{src}/{bbox}/{span}"
        try:
            response = httpx.get(url, timeout=20.0)
            response.raise_for_status()
        except Exception as ex:  # noqa: BLE001 — one satellite failing is fine
            logger.warning("NASA FIRMS history %s fetch failed: %s", src, ex)
            continue
        reader = csv.DictReader(response.content.decode("utf-8").splitlines())
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                if ring and not _point_in_ring(lon, lat, ring):
                    continue
                day = _nasa_detected_at(row.get("acq_date"), row.get("acq_time"))[:10]
                key = (round(lat, 3), round(lon, 3), day)
                if key in seen:
                    continue
                seen.add(key)
                per_day[day] = per_day.get(day, 0) + 1
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue

    today = datetime.datetime.now(BANGKOK_TZ).date()
    return [
        ((today - datetime.timedelta(days=i)).isoformat(), per_day.get((today - datetime.timedelta(days=i)).isoformat(), 0))
        for i in range(span - 1, -1, -1)
    ]


def merge_hotspots(groups: list[list[Hotspot]]) -> list[Hotspot]:
    merged: list[Hotspot] = []
    seen: set[tuple[float, float, str]] = set()
    for group in groups:
        for hotspot in group:
            key = (round(hotspot.latitude, 4), round(hotspot.longitude, 4), hotspot.detected_at[:10])
            if key in seen:
                continue
            seen.add(key)
            merged.append(hotspot)
    return merged


# A VIIRS pixel is ~375 m; different sources report the same fire at slightly
# offset coordinates, so cluster detections within this radius (same day) as one.
RECONCILE_RADIUS_M = 750.0

# When several sources report the same fire, keep the richest record as the
# representative: RFD carries district/subdistrict/landuse, GISTDA next, NASA last.
_SOURCE_PRIORITY = {FOREST_FIREMAP_SOURCE: 0, GISTDA_VIIRS_SOURCE: 1, "NASA FIRMS": 2}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def reconcile_hotspots(groups: list[list[Hotspot]]) -> list[Hotspot]:
    """Cross-reference detections from multiple sources into unique hotspots.

    Detections from any source within RECONCILE_RADIUS_M on the same day are
    treated as one real fire. Each output hotspot records every source that saw
    it (``sources``/``source_count``) and takes the highest confidence reported.
    """
    clusters: list[dict] = []  # {rep: Hotspot, sources: set[str], members: list[Hotspot]}
    for group in groups:
        for hs in group:
            day = hs.detected_at[:10]
            # Only merge detections from *different* sources: each source already
            # decided its own points are distinct, so we never collapse a source's
            # own count — we only fuse the same fire seen by another source.
            best = None
            best_dist = RECONCILE_RADIUS_M
            for cluster in clusters:
                if cluster["rep"].detected_at[:10] != day:
                    continue
                if hs.source in cluster["sources"]:
                    continue
                dist = _haversine_m(
                    cluster["rep"].latitude, cluster["rep"].longitude, hs.latitude, hs.longitude
                )
                if dist <= best_dist:
                    best = cluster
                    best_dist = dist
            if best is None:
                clusters.append({"rep": hs, "sources": {hs.source}, "members": [hs]})
                continue
            best["members"].append(hs)
            best["sources"].add(hs.source)
            # Promote the representative if this source is richer (lower priority value).
            if _SOURCE_PRIORITY.get(hs.source, 99) < _SOURCE_PRIORITY.get(best["rep"].source, 99):
                best["rep"] = hs

    reconciled: list[Hotspot] = []
    for idx, cluster in enumerate(clusters, start=1):
        rep: Hotspot = cluster["rep"]
        sources = sorted(cluster["sources"], key=lambda s: _SOURCE_PRIORITY.get(s, 99))
        reconciled.append(
            rep.model_copy(
                update={
                    "id": f"HS-{idx:03d}",
                    "sources": sources,
                    "source_count": len(sources),
                    "confidence": max(m.confidence for m in cluster["members"]),
                }
            )
        )
    return reconciled

def fetch_live_hotspots(gistda_key: str | None = None, nasa_key: str | None = None) -> HotspotResponse:
    # Always query every available source so we can cross-reference them, rather
    # than stopping at the first that responds. Each source is best-effort.
    hotspot_groups: list[list[Hotspot]] = []
    sources: list[str] = []
    source_breakdown: dict[str, int] = {}
    fetch_errors: list[str] = []

    def _try(label: str, fetch) -> None:
        try:
            # Clip each source to the province boundary before counting/merging so
            # the headline count and per-source breakdown exclude fires that the
            # bbox-based sources (NASA FIRMS) pick up in neighbouring provinces.
            group = filter_to_province(fetch())
            hotspot_groups.append(group)
            sources.append(label)
            source_breakdown[label] = len(group)
            logger.info("Loaded %d hotspots from %s", len(group), label)
        except Exception as e:  # noqa: BLE001 — one source failing must not sink the rest
            fetch_errors.append(f"{label}: {e}")
            logger.error("%s fetch failed: %s", label, e)

    _try(FOREST_FIREMAP_SOURCE, fetch_forest_firemap_hotspots)
    if gistda_key:
        _try(GISTDA_VIIRS_SOURCE, lambda: fetch_gistda_hotspots(gistda_key))
    if nasa_key:
        _try("NASA FIRMS", lambda: fetch_nasa_firms_hotspots(nasa_key))

    if not hotspot_groups:
        raise Exception(f"Failed to fetch live hotspots: {'; '.join(fetch_errors)}")

    hotspots = reconcile_hotspots(hotspot_groups)
    source = " + ".join(dict.fromkeys(sources))

    if not hotspots and any(error.startswith(FOREST_FIREMAP_SOURCE) for error in fetch_errors):
        raise Exception(f"Royal Forest Department Firemap unavailable and backup sources returned no hotspots: {'; '.join(fetch_errors)}")

    count = len(hotspots)
    # Area of Chiang Mai is approximately 20,107 km2
    density = round((count / 20107.0) * 100.0, 2)

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    latest_update = now.isoformat()

    return HotspotResponse(
        count=count,
        density_per_100_km2=density,
        latest_update=latest_update,
        source=source,
        items=hotspots,
        source_breakdown=source_breakdown,
    )
