import datetime
import logging

import httpx

from app.models import WeatherResponse

logger = logging.getLogger(__name__)


def get_wind_direction_text(degrees: int) -> str:
    directions = [
        "เหนือ",
        "ตะวันออกเฉียงเหนือ",
        "ตะวันออก",
        "ตะวันออกเฉียงใต้",
        "ใต้",
        "ตะวันตกเฉียงใต้",
        "ตะวันตก",
        "ตะวันตกเฉียงเหนือ",
    ]
    deg = (degrees + 22.5) % 360
    idx = int(deg // 45)
    return directions[idx]


def fetch_live_weather() -> WeatherResponse:
    lat = 18.8407
    lon = 98.9698
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"

    logger.info("Fetching live weather from Open-Meteo: %s", url)
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        current = data["current"]
        temp = float(current["temperature_2m"])
        humidity = float(current["relative_humidity_2m"])
        wind_speed = float(current["wind_speed_10m"])
        wind_dir = round(float(current["wind_direction_10m"]), 1)

        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

        return WeatherResponse(
            wind_speed_kmh=wind_speed,
            wind_direction_deg=wind_dir,
            wind_direction_text=get_wind_direction_text(wind_dir),
            temperature_c=temp,
            humidity_percent=humidity,
            latest_update=now.isoformat(),
            source="Open-Meteo Live API",
        )
    except Exception as exc:
        logger.error("Error fetching live weather: %s", exc)
        raise exc
