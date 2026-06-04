import datetime
import logging
from typing import Any

import httpx

from app.models import WeatherResponse

logger = logging.getLogger(__name__)

TMD_AWS_URL = "https://www.tmd.go.th/api/weather/get-aws-weather-by-province?province=chiangmai"
TMD_SOURCE = "Thai Meteorological Department AWS"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _required_float(value: Any, field: str) -> float:
    parsed = _to_float(value)
    if parsed is None:
        raise ValueError(f"TMD AWS field missing: {field}")
    return parsed


def _parse_tmd_datetime(value: str | None) -> str:
    if not value:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat()

    normalized = value
    if len(value) >= 5 and value[-5] in {"+", "-"} and value[-2] != ":":
        normalized = f"{value[:-2]}:{value[-2:]}"

    return datetime.datetime.fromisoformat(normalized).isoformat()


def get_wind_direction_text(degrees: float) -> str:
    normalized = degrees % 360
    directions = [
        (-1, 10, "ทิศเหนือ"),
        (10, 30, "ทิศเหนือค่อนไปทางตะวันออก"),
        (30, 50, "ทิศตะวันออกเฉียงเหนือ"),
        (50, 70, "ทิศตะวันออกค่อนไปทางเหนือ"),
        (70, 100, "ทิศตะวันออก"),
        (100, 120, "ทิศตะวันออกค่อนไปทางใต้"),
        (120, 140, "ทิศตะวันออกเฉียงใต้"),
        (140, 160, "ทิศใต้ค่อนไปทางตะวันออก"),
        (160, 190, "ทิศใต้"),
        (190, 210, "ทิศใต้ค่อนไปทางตะวันตก"),
        (210, 230, "ทิศตะวันตกเฉียงใต้"),
        (230, 250, "ทิศตะวันตกค่อนไปทางใต้"),
        (250, 280, "ทิศตะวันตก"),
        (280, 300, "ทิศตะวันตกค่อนไปทางเหนือ"),
        (300, 320, "ทิศตะวันตกเฉียงเหนือ"),
        (320, 340, "ทิศเหนือค่อนไปทางตะวันตก"),
        (340, 360, "ทิศเหนือ"),
    ]

    for low, high, label in directions:
        if low < normalized <= high:
            return label
    return "ทิศเหนือ"


def _pick_chiangmai_station(stations: list[dict[str, Any]]) -> dict[str, Any]:
    for station in stations:
        if int(station.get("stationId", -1)) == 1:
            return station
    if stations:
        return stations[0]
    raise ValueError("TMD AWS returned no Chiang Mai station data")


def fetch_live_weather() -> WeatherResponse:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ChiangMaiEyes/1.0",
        "Referer": "https://www.tmd.go.th/weather/province/chiang-mai",
    }

    logger.info("Fetching live weather from TMD AWS: %s", TMD_AWS_URL)
    response = httpx.get(TMD_AWS_URL, headers=headers, timeout=15.0)
    response.raise_for_status()
    payload = response.json()

    stations = payload.get("data", payload)
    if not isinstance(stations, list):
        raise ValueError("TMD AWS response does not contain a station list")

    station = _pick_chiangmai_station(stations)
    wind_dir = round(_required_float(station.get("windDirection"), "windDirection"), 1)

    return WeatherResponse(
        wind_speed_kmh=_required_float(station.get("windSpeed"), "windSpeed"),
        wind_direction_deg=wind_dir,
        wind_direction_text=get_wind_direction_text(wind_dir),
        temperature_c=_required_float(station.get("temperature"), "temperature"),
        humidity_percent=_required_float(station.get("humidity"), "humidity"),
        latest_update=_parse_tmd_datetime(station.get("dateTimeUtc7")),
        source=TMD_SOURCE,
        station_name=station.get("stationNameTh") or station.get("stationNameEn"),
        station_latitude=_to_float(station.get("stationLat")),
        station_longitude=_to_float(station.get("stationLon")),
        pressure_hpa=_to_float(station.get("pressure")),
        rain_15m_mm=_to_float(station.get("precip15Mins")),
        rain_1h_mm=_to_float(station.get("precip1Hr")),
        rain_today_mm=_to_float(station.get("precipToday")),
        temperature_min_today_c=_to_float(station.get("temperatureMinToday")),
        temperature_max_today_c=_to_float(station.get("temperatureMaxToday")),
    )
