"""Backward (historical) trends for PM2.5 and weather from Open-Meteo.

Open-Meteo is free, keyless, and reachable from anywhere (including Vercel),
and its ``past_days`` parameter returns recent days without the multi-day delay
of the ERA5 archive. We aggregate hourly readings into daily values centred on
Chiang Mai city so the authority view can look backwards in time.
"""
import collections
import logging

import httpx

logger = logging.getLogger(__name__)

# Chiang Mai city centroid — the single point we sample historical models at.
_CM_LAT = 18.79
_CM_LON = 98.98
_TZ = "Asia/Bangkok"


def fetch_pm25_history(days: int = 14) -> list[tuple[str, float]]:
    """Daily mean PM2.5 (µg/m³) for the last ``days`` days, oldest→newest."""
    past = max(1, min(days, 92)) - 1
    try:
        response = httpx.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": _CM_LAT,
                "longitude": _CM_LON,
                "hourly": "pm2_5",
                "past_days": past,
                "forecast_days": 1,
                "timezone": _TZ,
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception as ex:  # noqa: BLE001 — history is non-critical
        logger.warning("Open-Meteo PM2.5 history fetch failed: %s", ex)
        return []

    hourly = response.json().get("hourly", {})
    buckets: dict[str, list[float]] = collections.defaultdict(list)
    for ts, value in zip(hourly.get("time", []), hourly.get("pm2_5", [])):
        if value is not None:
            buckets[ts[:10]].append(float(value))
    return [(day, round(sum(vals) / len(vals), 1)) for day, vals in sorted(buckets.items())]


def fetch_weather_history(days: int = 14) -> list[tuple[str, float, float, float, float]]:
    """Daily (date, temp_max, temp_min, wind_max, humidity_mean) for the last
    ``days`` days. Temp/wind come as daily aggregates; humidity has no daily
    variable so we average the hourly series per day (like PM2.5)."""
    past = max(1, min(days, 92)) - 1
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": _CM_LAT,
                "longitude": _CM_LON,
                "daily": "temperature_2m_max,temperature_2m_min,wind_speed_10m_max",
                "hourly": "relative_humidity_2m",
                "past_days": past,
                "forecast_days": 1,
                "timezone": _TZ,
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception as ex:  # noqa: BLE001 — history is non-critical
        logger.warning("Open-Meteo weather history fetch failed: %s", ex)
        return []

    body = response.json()
    daily = body.get("daily", {})
    hourly = body.get("hourly", {})

    humidity_by_day: dict[str, list[float]] = collections.defaultdict(list)
    for ts, rh in zip(hourly.get("time", []), hourly.get("relative_humidity_2m", [])):
        if rh is not None:
            humidity_by_day[ts[:10]].append(float(rh))

    out: list[tuple[str, float, float, float, float]] = []
    for day, tmax, tmin, wmax in zip(
        daily.get("time", []),
        daily.get("temperature_2m_max", []),
        daily.get("temperature_2m_min", []),
        daily.get("wind_speed_10m_max", []),
    ):
        if tmax is None or tmin is None:
            continue
        rh_vals = humidity_by_day.get(day, [])
        humidity = round(sum(rh_vals) / len(rh_vals)) if rh_vals else 0.0
        out.append((day, round(float(tmax), 1), round(float(tmin), 1), round(float(wmax or 0), 1), humidity))
    return out
