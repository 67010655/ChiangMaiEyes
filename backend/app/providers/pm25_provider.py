import datetime
import logging

import httpx

from app.models import Pm25Response, Pm25Station
from app.text import repair_thai_mojibake

logger = logging.getLogger(__name__)


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
            pm25 = round(_aqi_to_pm25(aqi), 1)
            station_info = s.get("station", {})
            stations.append(Pm25Station(
                id=f"AQICN-{s.get('uid', 'x')}",
                name=station_info.get("name", "AQICN"),
                district="เชียงใหม่",
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
    url = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
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
