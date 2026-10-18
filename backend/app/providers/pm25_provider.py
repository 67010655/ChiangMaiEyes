import datetime
import json
import logging
import math
import ssl
from functools import lru_cache
from pathlib import Path

import httpx

from app.models import AqiStation, Pm25Response, Pm25Station
from app.text import repair_thai_mojibake

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _air4thai_tls_context() -> ssl.SSLContext:
    """Complete the public issuer chain, retaining root and hostname validation.

    Air4Thai currently serves a Let's Encrypt YR1 chain. Some OpenSSL clients
    cannot build it without the cross-signed Root YR certificate. The bundled
    issuers are published by Let's Encrypt, not a leaf certificate or new root.
    Partial-chain trust is disabled so verification still reaches a trusted root.
    """
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(
        Path(__file__).resolve().parent.parent / 'data' / 'tls' / 'air4thai-issuer-chain.pem'))
    context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    return context

_DISTRICTS_GEOJSON = Path(__file__).resolve().parent.parent / "data" / "chiangmai-districts.json"
_cached_districts = None

_DISTRICT_CENTROIDS = {
    "แม่อาย":      (20.03, 99.20),
    "ฝาง":         (19.80, 99.10),
    "เชียงดาว":    (19.38, 98.95),
    "แม่แตง":      (19.10, 98.90),
    "กัลยาณิวัฒนา": (19.05, 98.35),
    "สะเมิง":      (18.80, 98.65),
    "แม่แจ่ม":     (18.50, 98.33),
    "จอมทอง":      (18.40, 98.70),
    "ฮอด":         (18.10, 98.60),
    "อมก๋อย":      (17.87, 98.35),
    "ดอยสะเก็ด":   (18.98, 99.28),
    "สันทราย":     (18.97, 99.05),
    "สันกำแพง":    (18.80, 99.12),
    "แม่ออน":      (18.73, 99.30),
    "แม่วาง":      (18.63, 98.78),
    "หางดง":       (18.70, 98.95),
    "สารภี":       (18.73, 99.01),
    "แม่ริม":      (18.92, 98.95),
    "เมืองเชียงใหม่": (18.79, 98.99),
    "ดอยเต่า":      (17.95, 98.68),
    "ดอยหล่อ":      (18.47, 98.78),
    "พร้าว":        (19.35, 99.20),
    "เวียงแหง":     (19.55, 98.63),
    "สันป่าตอง":    (18.62, 98.88),
}

def _load_districts_geojson():
    global _cached_districts
    if _cached_districts is not None:
        return _cached_districts
    try:
        with open(_DISTRICTS_GEOJSON, "r", encoding="utf-8") as f:
            _cached_districts = json.load(f)
    except Exception as e:
        logger.error("Failed to load chiangmai-districts.json: %s", e)
        _cached_districts = {"type": "FeatureCollection", "features": []}
    return _cached_districts

def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    if n == 0:
        return False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def _point_in_geometry(x: float, y: float, geom: dict) -> bool:
    g_type = geom.get("type")
    coords = geom.get("coordinates") or []
    if g_type == "Polygon":
        if not coords:
            return False
        return _point_in_polygon(x, y, coords[0])
    elif g_type == "MultiPolygon":
        for poly in coords:
            if poly and _point_in_polygon(x, y, poly[0]):
                return True
    return False

def _is_in_cm(lat: float, lon: float) -> bool:
    """Return True only if the point is inside a Chiang Mai district polygon (no centroid fallback)."""
    geojson = _load_districts_geojson()
    for feat in geojson.get("features", []):
        geom = feat.get("geometry")
        if geom and _point_in_geometry(lon, lat, geom):
            return True
    return False


def find_district_for_point(lat: float, lon: float) -> str:
    geojson = _load_districts_geojson()
    for feat in geojson.get("features", []):
        geom = feat.get("geometry")
        if geom and _point_in_geometry(lon, lat, geom):
            name = feat.get("properties", {}).get("amp_th")
            if name:
                return name
    
    # centroid fallback
    min_dist = float("inf")
    nearest_district = "เมืองเชียงใหม่"
    for name, centroid in _DISTRICT_CENTROIDS.items():
        d = (lat - centroid[0])**2 + (lon - centroid[1])**2
        if d < min_dist:
            min_dist = d
            nearest_district = name
    return nearest_district



def fetch_aqicn_stations(token: str) -> list[AqiStation]:
    """Read composite AQI. A map AQI is not a measured PM2.5 concentration."""
    if not token:
        return []
    url = (
        f"https://api.waqi.info/v2/map/bounds"
        f"?latlng=17.5,97.5,20.5,100.5&networks=all&token={token}"
    )
    try:
        r = httpx.get(url, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            return []
        stations: list[AqiStation] = []
        retrieved = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for s in data.get("data") or []:
            aqi_raw = s.get("aqi")
            if aqi_raw in (None, "-", ""):
                continue
            try:
                aqi = float(aqi_raw)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(aqi) or aqi < 0:
                continue
            try:
                lat = float(s.get("lat", 0))
                lon = float(s.get("lon", 0))
            except (TypeError,ValueError):
                continue
            if not (17.0 < lat < 21.0 and 97.0 < lon < 101.0):
                continue
            if not _is_in_cm(lat, lon):
                continue
            station_info = s.get("station", {})
            district = find_district_for_point(lat, lon)
            upstream_time = None
            try:
                parsed = datetime.datetime.fromisoformat(str(station_info.get('time', '')).replace('Z', '+00:00'))
                if parsed.tzinfo is not None:
                    upstream_time = parsed.isoformat()
            except ValueError:
                pass
            stations.append(AqiStation(
                id=f"AQICN-{s.get('uid', 'x')}",
                name=station_info.get("name", "AQICN"),
                district=district,
                latitude=lat,
                longitude=lon,
                aqi=aqi,
                updated_at=upstream_time,
                retrieved_at=retrieved,
                upstream_time_text=str(station_info['time']) if station_info.get('time') else None,
            ))
        return stations
    except Exception:
        logger.warning("AQICN request or data format failed")
        return []


def get_pm25_category_and_color(pm25: float) -> tuple[str, str]:
    if pm25 <= 15.0:
        return "ดีมาก", "green"
    if pm25 <= 25.0:
        return "ดี", "green"
    if pm25 <= 37.5:
        return "ปานกลาง", "yellow"
    if pm25 <= 75.0:
        return "เริ่มมีผลกระทบต่อสุขภาพ", "orange"
    if pm25 <= 120.0:
        return "มีผลกระทบต่อสุขภาพ", "red"
    return "อันตราย", "purple"


def normalize_cached_pm25(data):
    """Quarantine legacy AQI conversions, retaining independently measured stations."""
    result = Pm25Response(**data)
    if any(s.id.startswith('AQICN-') for s in result.stations) or (
        'AQICN' in result.source and not result.stations and result.current_pm25 is not None):
        measured = [s for s in result.stations if not s.id.startswith('AQICN-')]
        if not measured:
            missing = _build_pm25_response_from_aqicn([])
            return missing.model_copy(update={'latest_update':result.latest_update,
                'source':result.source,'note':'ข้อมูลสำรองเดิมมีค่าแปลงจาก AQI จึงไม่ใช้เป็นความเข้มข้น PM2.5'})
        value = round(sum(s.pm25 for s in measured)/len(measured),1)
        category,color = get_pm25_category_and_color(value)
        return result.model_copy(update={'stations':measured,'current_pm25':value,'category':category,'color':color})
    return result


import math as _math


def _dist_km(s1: Pm25Station, s2: Pm25Station) -> float:
    dlat = _math.radians(s2.latitude - s1.latitude)
    dlon = _math.radians(s2.longitude - s1.longitude)
    a = _math.sin(dlat / 2) ** 2 + _math.cos(_math.radians(s1.latitude)) * _math.cos(_math.radians(s2.latitude)) * _math.sin(dlon / 2) ** 2
    return 2 * 6371 * _math.asin(_math.sqrt(a))


def _build_pm25_response_from_aqicn(stations: list[AqiStation]) -> Pm25Response:
    """Explicitly missing concentration, with AQI kept in a separate collection."""
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    return Pm25Response(
        current_pm25=None,
        category='ยังไม่มีค่า PM2.5 ที่วัดได้',
        color='gray',
        trend='unknown',
        latest_update=now.isoformat(),
        source=f"AQICN ({len(stations)} สถานี — Air4Thai ไม่พร้อมใช้งาน)",
        stations=[], aqi_stations=stations,
        retrieved_at=now.isoformat(), measurement_kind='unavailable',
        note='ต้นทางสำรองมีดัชนี AQI รวม ไม่ใช่ความเข้มข้น PM2.5; ไม่แปลงดัชนีเป็น µg/m³ และไม่เก็บ AQI ในคลังย้อนหลัง',
    )


def fetch_live_pm25(aqicn_token: str | None = None) -> Pm25Response:
    url = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
    logger.info("Fetching live PM2.5 from Air4Thai: %s", url)

    air4thai_stations: list[Pm25Station] = []
    air4thai_ok = False

    try:
        response = httpx.get(url, timeout=10.0, verify=_air4thai_tls_context())
        response.raise_for_status()

        data = response.json()
        raw_stations = data.get("stations", [])

        total_pm25 = 0.0
        valid_station_count = 0
        latest_time = None

        for station_data in raw_stations:
            area_th = repair_thai_mojibake(station_data.get("areaTH", ""))
            area_en = station_data.get("areaEN", "")

            if "เชียงใหม่" not in area_th and "Chiang Mai" not in area_en and "Chiangmai" not in area_en:
                continue

            aqi_last = station_data.get("AQILast", {})
            pm25_data = aqi_last.get("PM25", {})
            pm25_val_str = pm25_data.get("value")
            if pm25_val_str is None:
                continue

            try:
                pm25_val = float(pm25_val_str)
            except ValueError:
                continue

            if not math.isfinite(pm25_val) or pm25_val < 0:
                continue

            date_str = aqi_last.get("date", "")
            time_str = aqi_last.get("time", "")
            if not date_str or not time_str:
                continue
            iso_time = datetime.datetime.fromisoformat(f'{date_str}T{time_str}').replace(
                tzinfo=datetime.timezone(datetime.timedelta(hours=7))).isoformat()

            if latest_time is None or iso_time > latest_time:
                latest_time = iso_time

            district = area_en.split(",")[-2].strip() if "," in area_en else "เมืองเชียงใหม่"
            if "District" in district:
                district = district.replace("District", "").strip()

            station = Pm25Station(
                id=f"CM-{str(station_data.get('stationID', 'unknown')).upper()}",
                name=repair_thai_mojibake(station_data.get("nameTH", station_data.get("nameEN", "สถานีวัดคุณภาพอากาศ"))),
                district=district,
                latitude=float(station_data.get("lat", 0.0)),
                longitude=float(station_data.get("long", 0.0)),
                pm25=pm25_val,
                trend="stable",
                updated_at=iso_time,
                retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            air4thai_stations.append(station)
            total_pm25 += pm25_val
            valid_station_count += 1

        if valid_station_count > 0:
            air4thai_ok = True
    except Exception:
        logger.warning("Air4Thai request or data format failed; checking AQICN separately")

    # Fetch AQICN stations (works from any IP globally)
    aqicn_stations = fetch_aqicn_stations(aqicn_token or "") if aqicn_token else []

    if not air4thai_ok:
        # Air4Thai unreachable (e.g. blocked from non-Thai IPs) — use AQICN alone
        return _build_pm25_response_from_aqicn(aqicn_stations)

    # Concentration and composite indices have different meanings and units.
    avg_pm25 = round(sum(s.pm25 for s in air4thai_stations) / len(air4thai_stations), 1)
    category, color = get_pm25_category_and_color(avg_pm25)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    latest_update = latest_time if latest_time else now.isoformat()
    source_label = "Air4Thai PCD"

    return Pm25Response(
        current_pm25=avg_pm25,
        category=category,
        color=color,
        trend="stable",
        latest_update=latest_update,
        source=source_label,
        stations=air4thai_stations, aqi_stations=aqicn_stations,
        retrieved_at=now.isoformat(),
    )
