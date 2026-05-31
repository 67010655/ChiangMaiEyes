import datetime
import logging

import httpx

from app.models import Pm25Response, Pm25Station
from app.text import repair_thai_mojibake

logger = logging.getLogger(__name__)


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


def fetch_live_pm25() -> Pm25Response:
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

        avg_pm25 = round(total_pm25 / valid_station_count, 1)
        category, color = get_pm25_category_and_color(avg_pm25)

        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        latest_update = latest_time if latest_time else now.isoformat()

        return Pm25Response(
            current_pm25=avg_pm25,
            category=category,
            color=color,
            trend="stable",
            latest_update=latest_update,
            source="Air4Thai Live API",
            stations=stations,
        )
    except Exception as exc:
        logger.error("Error fetching live PM2.5: %s", exc)
        raise exc
