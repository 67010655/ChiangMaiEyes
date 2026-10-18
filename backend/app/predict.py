"""Real forward weather and CAMS PM2.5, with an experimental air-dryness proxy.

There is no validated fire-spread model or measured fuel dataset. Do not use
former district fuel/slope constants to invent rates, distances or fire counts.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from datetime import datetime, timedelta, timezone

import httpx

from app.fire_phase import _build_spread_projection, _DISTRICT_CENTROIDS, district_base_danger, dryness_from_humidity_rain
from app.fire_spread_physics import DISTRICT_PHYSICS
from app.models import (
    DailyIgnitionForecast,
    DailyPm25Forecast,
    DistrictIgnitionForecast,
    FirePhaseResponse,
    FirePredictionResponse,
    LocationPm25Forecast,
    SpreadForecastExtended,
    WeatherForecastDay,
)

logger = logging.getLogger(__name__)

_CM_LAT, _CM_LON = 18.79, 98.99
_FORECAST_DAYS = 3
_TREND_EPSILON = 0.05
_SOURCE_CACHE: dict[str, tuple[float, object, str]] = {}
_SOURCE_LOCKS = {name: Lock() for name in ('weather', 'pm25')}


def _finite(value, *, nonnegative=False):
    if value is None or isinstance(value,bool):
        return None
    value = float(value)
    return value if math.isfinite(value) and (not nonnegative or value >= 0) else None


def _direction(value):
    value = _finite(value)
    return value % 360 if value is not None and 0 <= value <= 360 else None


def _cached_source(name, fetch):
    """Coalesce concurrent callers; cache successes 5 min, failures only 30 s.

    The retrieval timestamp belongs to the cached data, not to each page load.
    No previous successful forecast is silently substituted after expiry.
    """
    with _SOURCE_LOCKS[name]:
        cached = _SOURCE_CACHE.get(name)
        if cached and time.monotonic() < cached[0]:
            return cached[1], cached[2]
        try:
            data = fetch()
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            logger.warning('%s forecast response invalid: %s', name, exc)
            data = [] if name == 'weather' else {}
        retrieved = datetime.now(timezone.utc).isoformat()
        _SOURCE_CACHE[name] = (time.monotonic() + (300 if data else 30), data, retrieved)
        return data, retrieved


def _fetch_weather_forecast_days() -> list[dict]:
    """Real Open-Meteo forward daily forecast (keyless). Humidity has no daily
    aggregate variable (same constraint as history_provider.fetch_weather_history)
    so it's averaged from the hourly series per day. Returns [] on any
    failure so a down provider degrades gracefully rather than crashing."""
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": _CM_LAT,
                "longitude": _CM_LON,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                         "wind_speed_10m_max,wind_direction_10m_dominant",
                "hourly": "relative_humidity_2m",
                "forecast_days": _FORECAST_DAYS,
                "timezone": "Asia/Bangkok",
            },
            timeout=httpx.Timeout(8.0, connect=3.0),
        )
        response.raise_for_status()
    except Exception as ex:  # noqa: BLE001 — a down forecast provider must not crash the endpoint
        logger.warning("Weather forecast fetch failed: %s", ex)
        return []

    body = response.json()
    daily = body.get("daily", {})
    hourly = body.get("hourly", {})

    humidity_by_day: dict[str, list[float]] = {}
    for ts, rh in zip(hourly.get("time", []), hourly.get("relative_humidity_2m", [])):
        if rh is None or not math.isfinite(float(rh)) or not 0 <= float(rh) <= 100:
            continue
        humidity_by_day.setdefault(ts[:10], []).append(float(rh))

    days = daily.get("time", [])
    tmax_list = daily.get("temperature_2m_max") or []
    tmin_list = daily.get("temperature_2m_min") or []
    rain_list = daily.get("precipitation_sum") or []
    wind_list = daily.get("wind_speed_10m_max") or []
    wdir_list = daily.get("wind_direction_10m_dominant") or []

    out: list[dict] = []
    for i, day in enumerate(days):
        hum_values = humidity_by_day.get(day, [])
        out.append({
            "date": day,
            "temp_max_c": _finite(tmax_list[i]) if i < len(tmax_list) else None,
            "temp_min_c": _finite(tmin_list[i]) if i < len(tmin_list) else None,
            "humidity_pct": (sum(hum_values) / len(hum_values)) if hum_values else None,
            "rain_mm": _finite(rain_list[i],nonnegative=True) if i < len(rain_list) else None,
            "wind_kmh": _finite(wind_list[i],nonnegative=True) if i < len(wind_list) else None,
            "wind_dir_deg": _direction(wdir_list[i]) if i < len(wdir_list) else None,
        })
    return out


def _fetch_pm25_forecast_batch(locations: list[tuple[str, float, float]]) -> dict[str, list[dict]]:
    """Real PM2.5 forecast (Open-Meteo Air Quality API, CAMS model) for every
    (name, lat, lon) in `locations`, fetched in ONE batched HTTP request
    (Open-Meteo accepts comma-joined lat/lon and returns one result object
    per location, same order). Returns {} on any failure."""
    if not locations:
        return {}
    try:
        response = httpx.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": ",".join(str(lat) for _, lat, _ in locations),
                "longitude": ",".join(str(lon) for _, _, lon in locations),
                "hourly": "pm2_5",
                "forecast_days": _FORECAST_DAYS,
                "timezone": "Asia/Bangkok",
            },
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        response.raise_for_status()
    except Exception as ex:  # noqa: BLE001 — a down provider must not crash the endpoint
        logger.warning("PM2.5 forecast fetch failed: %s", ex)
        return {}

    body = response.json()
    # A single-location request returns one object, not a list — normalize.
    results = body if isinstance(body, list) else [body]

    out: dict[str, list[dict]] = {}
    for (name, _, _), result in zip(locations, results):
        hourly = (result or {}).get("hourly", {})
        by_day: dict[str, list[float]] = {}
        for ts, val in zip(hourly.get("time", []), hourly.get("pm2_5", [])):
            if val is None or not math.isfinite(float(val)) or float(val) < 0:
                continue
            by_day.setdefault(ts[:10], []).append(float(val))
        out[name] = [
            {"date": day, "pm25": round(sum(vals) / len(vals), 1)}
            for day, vals in sorted(by_day.items())
        ]
    return out


def build_fire_predictions(current_phases: FirePhaseResponse | None = None) -> FirePredictionResponse:
    # Forecasts do not depend on downloading historical incidents, polygons or
    # district winds. Fetch the two independent providers concurrently.
    pm25_locations = [('จังหวัดเชียงใหม่', _CM_LAT, _CM_LON)] + [
        (name, *_DISTRICT_CENTROIDS[name]) for name in DISTRICT_PHYSICS if name in _DISTRICT_CENTROIDS
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        weather_job = pool.submit(_cached_source, 'weather', _fetch_weather_forecast_days)
        pm_job = pool.submit(_cached_source, 'pm25', lambda: _fetch_pm25_forecast_batch(pm25_locations))
        forecast_days, weather_retrieved = weather_job.result()
        pm25_by_location, pm_retrieved = pm_job.result()
    danger_by_district_now = {p.district: p.danger_score for p in current_phases.phases} if current_phases else {}

    district_forecasts: list[DistrictIgnitionForecast] = []
    for district in DISTRICT_PHYSICS:
        daily_scores: list[DailyIgnitionForecast] = []
        for day in forecast_days:
            dryness = dryness_from_humidity_rain(day["humidity_pct"], day["rain_mm"])
            score = district_base_danger(district, dryness)
            daily_scores.append(DailyIgnitionForecast(
                date=day["date"],
                danger_score=score,
                humidity_pct=round(day["humidity_pct"], 1) if day["humidity_pct"] is not None else None,
                rain_mm=round(day["rain_mm"], 1) if day["rain_mm"] is not None else None,
            ))
        trend = "unavailable"
        if len(daily_scores) >= 2 and all(d.danger_score is not None for d in daily_scores):
            delta = daily_scores[-1].danger_score - daily_scores[0].danger_score
            trend = "rising" if delta > _TREND_EPSILON else "falling" if delta < -_TREND_EPSILON else "stable"
        district_forecasts.append(DistrictIgnitionForecast(
            district=district,
            current_danger_score=danger_by_district_now.get(district),
            daily=daily_scores,
            trend=trend,
        ))
    district_forecasts.sort(key=lambda d: -(d.daily[-1].danger_score or 0) if d.daily else 0)

    # Extended spread for districts CURRENTLY "during" — same province-level
    # wind-forecast simplification the live spread projection already falls
    # back to when a district has no per-district live reading.
    spread_forecast: list[SpreadForecastExtended] = []
    during_districts = [p for p in current_phases.phases if p.phase == "during"] if current_phases else []
    if during_districts and forecast_days:
        tomorrow = forecast_days[0]
        wind_speed = tomorrow["wind_kmh"]
        wind_dir = tomorrow["wind_dir_deg"]
        for p in during_districts if wind_speed is not None and wind_dir is not None else []:
            proj = _build_spread_projection(p.district, wind_speed, wind_dir)
            if proj is None:
                continue
            spread_forecast.append(SpreadForecastExtended(
                district=p.district,
                km_48h=round(proj.rate_kmh * 48, 1),
                km_72h=round(proj.rate_kmh * 72, 1),
                forecast_wind_kmh=round(wind_speed, 1),
                forecast_wind_dir_deg=round(wind_dir, 1),
            ))

    weather_forecast = [
        WeatherForecastDay(
            date=day["date"],
            temp_max_c=round(day["temp_max_c"], 1) if day["temp_max_c"] is not None else None,
            temp_min_c=round(day["temp_min_c"], 1) if day["temp_min_c"] is not None else None,
            humidity_pct=round(day["humidity_pct"], 1) if day["humidity_pct"] is not None else None,
            rain_mm=round(day["rain_mm"], 1) if day["rain_mm"] is not None else None,
            wind_kmh=round(day["wind_kmh"], 1) if day["wind_kmh"] is not None else None,
            wind_dir_deg=round(day["wind_dir_deg"], 1) if day["wind_dir_deg"] is not None else None,
        )
        for day in forecast_days
    ]

    # PM2.5 forecast: province centroid + every district centroid, one batched
    # request. Districts share DISTRICT_PHYSICS' keys; centroids come from
    # fire_phase's existing _DISTRICT_CENTROIDS (already used for forest
    # proximity) rather than duplicating a second coordinate table.

    # A total provider failure returns {} — leave province as None and the
    # district list empty rather than a shell of empty-daily objects, so the
    # frontend can tell "no PM2.5 forecast at all" apart from "this one
    # location's daily list happens to be empty".
    pm25_forecast_province = None
    pm25_forecast_districts: list[LocationPm25Forecast] = []
    if pm25_by_location:
        for name, lat, lon in pm25_locations:
            daily = [DailyPm25Forecast(**d) for d in pm25_by_location.get(name, [])]
            entry = LocationPm25Forecast(name=name, latitude=lat, longitude=lon, daily=daily)
            if name == "จังหวัดเชียงใหม่":
                pm25_forecast_province = entry
            else:
                pm25_forecast_districts.append(entry)
        pm25_forecast_districts.sort(
            key=lambda f: -(f.daily[-1].pm25 or 0) if f.daily and f.daily[-1].pm25 is not None else 0
        )

    notes: list[str] = []
    if forecast_days:
        notes.append(
            f"ดัชนีอากาศแห้งทดลอง {_FORECAST_DAYS} วันใช้ความชื้น/ฝนพยากรณ์จากจุดอ้างอิงเชียงใหม่ร่วมกันทุกอำเภอ "
            "ไม่ใช่โอกาสเกิดไฟ และไม่มีข้อมูลเชื้อเพลิงรายแปลง"
        )
        notes.append("ยังไม่คำนวณอัตราหรือระยะไฟลาม 48/72 ชม.: ขาดข้อมูลเชื้อเพลิงภาคสนามและแบบจำลองที่ตรวจสอบแล้ว ลมอย่างเดียวไม่ให้ระยะลาม")
    else:
        notes.append("ดึงพยากรณ์อากาศไม่สำเร็จในขณะนี้ ลองใหม่อีกครั้ง")
    if pm25_by_location:
        notes.append(
            "พยากรณ์ PM2.5 มาจาก Open-Meteo Air Quality API (แบบจำลองบรรยากาศ CAMS) "
            "เป็นค่าประมาณระดับภูมิภาค ไม่ใช่ค่าจากสถานีตรวจวัดจริงในพื้นที่ อาจคลาดเคลื่อนจากของจริงได้"
        )
    else:
        notes.append("ดึงพยากรณ์ PM2.5 ไม่สำเร็จในขณะนี้ ลองใหม่อีกครั้ง")
    notes.append(
        "ยังไม่มีแบบจำลองพยากรณ์จำนวนจุดความร้อนล่วงหน้าที่น่าเชื่อถือ (ไม่มีแหล่งข้อมูลจริงรองรับ) "
        "จึงไม่แสดงเป็นตัวเลขจำนวนจุด ดัชนีอากาศแห้งเป็นข้อมูลอากาศ ไม่ใช่ผลพยากรณ์ไฟ"
    )

    return FirePredictionResponse(
        generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_mode="DERIVED",
        source_retrieved_at={name:stamp for name,stamp,data in (
            ('weather',weather_retrieved,forecast_days),('pm25_model',pm_retrieved,pm25_by_location)) if data},
        provider_status={'weather': 'available' if forecast_days else 'unavailable',
                         'pm25_model': 'available' if pm25_by_location else 'unavailable'},
        district_forecasts=district_forecasts,
        spread_forecast_72h=spread_forecast,
        weather_forecast=weather_forecast,
        pm25_forecast_province=pm25_forecast_province,
        pm25_forecast_districts=pm25_forecast_districts,
        notes=notes,
    )
