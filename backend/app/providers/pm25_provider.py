import datetime
import json
import logging
import math
from pathlib import Path

import httpx

from app.models import Pm25Response, Pm25Station
from app.text import repair_thai_mojibake

logger = logging.getLogger(__name__)

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



def _aqi_to_pm25(aqi: float) -> float:
    """Convert US AQI to approximate PM2.5 µg/m³ (EPA breakpoints)."""
    breakpoints = [
        (0, 50, 0.0, 12.0),
        (51, 100, 12.1, 35.4),
        (101, 150, 35.5, 55.4),
        (151, 200, 55.5, 150.4),
        (201, 300, 150.5, 250.4),
        (301, 500, 250.5, 500.4),
    ]
    for aqi_lo, aqi_hi, pm_lo, pm_hi in breakpoints:
        if aqi_lo <= aqi <= aqi_hi:
            return pm_lo + (aqi - aqi_lo) / (aqi_hi - aqi_lo) * (pm_hi - pm_lo)
    return min(500.0, aqi * 0.5)


def fetch_aqicn_stations(token: str) -> list[Pm25Station]:
    """Fetch all WAQI/AQICN stations in CM bounding box (17.5–20.5°N, 97.5–100.5°E)."""
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
        stations: list[Pm25Station] = []
        for s in data.get("data") or []:
            aqi_raw = s.get("aqi")
            if aqi_raw in (None, "-", ""):
                continue
            try:
                aqi = float(aqi_raw)
            except (ValueError, TypeError):
                continue
            if aqi < 0:
                continue
            lat = float(s.get("lat", 0))
            lon = float(s.get("lon", 0))
            if not (17.0 < lat < 21.0 and 97.0 < lon < 101.0):
                continue
            if not _is_in_cm(lat, lon):
                continue
            pm25 = round(_aqi_to_pm25(aqi), 1)
            station_info = s.get("station", {})
            district = find_district_for_point(lat, lon)
            stations.append(Pm25Station(
                id=f"AQICN-{s.get('uid', 'x')}",
                name=station_info.get("name", "AQICN"),
                district=district,
                latitude=lat,
                longitude=lon,
                pm25=pm25,
                trend="stable",
                updated_at=station_info.get("time", datetime.datetime.now().isoformat()),
            ))
        return stations
    except Exception as exc:
        logger.warning("AQICN fetch failed: %s", exc)
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


def fetch_live_pm25(aqicn_token: str | None = None) -> Pm25Response:
    url = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
    logger.info("Fetching live PM2.5 from Air4Thai: %s", url)

    try:
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()

        data = response.json()
        raw_stations = data.get("stations", [])

        stations: list[Pm25Station] = []
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

            if pm25_val < 0:
                continue

            date_str = aqi_last.get("date", "")
            time_str = aqi_last.get("time", "")
            iso_time = f"{date_str}T{time_str}:00+07:00" if date_str and time_str else datetime.datetime.now().isoformat()

            if latest_time is None or iso_time > latest_time:
                latest_time = iso_time

            district = area_en.split(",")[-2].strip() if "," in area_en else "เมืองเชียงใหม่"
            if "District" in district:
                district = district.replace("District", "").strip()

            station = Pm25Station(
                id=f"CM-{station_data.get('stationID').upper()}",
                name=repair_thai_mojibake(station_data.get("nameTH", station_data.get("nameEN", "สถานีวัดคุณภาพอากาศ"))),
                district=district,
                latitude=float(station_data.get("lat", 0.0)),
                longitude=float(station_data.get("long", 0.0)),
                pm25=pm25_val,
                trend="stable",
                updated_at=iso_time,
            )
            stations.append(station)
            total_pm25 += pm25_val
            valid_station_count += 1

        if valid_station_count == 0:
            raise Exception("No active Chiang Mai PM2.5 stations found in Air4Thai feed")

        # Merge AQICN stations when token is available
        aqicn_stations = fetch_aqicn_stations(aqicn_token or "") if aqicn_token else []
        # Dedup: skip AQICN station if Air4Thai already has one within 3 km
        import math
        def _dist_km(s1: Pm25Station, s2: Pm25Station) -> float:
            dlat = math.radians(s2.latitude - s1.latitude)
            dlon = math.radians(s2.longitude - s1.longitude)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(s1.latitude)) * math.cos(math.radians(s2.latitude)) * math.sin(dlon/2)**2
            return 2 * 6371 * math.asin(math.sqrt(a))

        merged_extra: list[Pm25Station] = []
        for aq in aqicn_stations:
            if all(_dist_km(aq, st) > 3.0 for st in stations):
                merged_extra.append(aq)

        all_stations = stations + merged_extra

        avg_pm25 = round(total_pm25 / valid_station_count, 1)
        category, color = get_pm25_category_and_color(avg_pm25)

        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        latest_update = latest_time if latest_time else now.isoformat()

        source_label = "Air4Thai PCD"
        if merged_extra:
            source_label += f" + AQICN ({len(merged_extra)} สถานีเพิ่มเติม)"

        return Pm25Response(
            current_pm25=avg_pm25,
            category=category,
            color=color,
            trend="stable",
            latest_update=latest_update,
            source=source_label,
            stations=all_stations,
        )
    except Exception as exc:
        logger.error("Error fetching live PM2.5: %s", exc)
        raise exc
