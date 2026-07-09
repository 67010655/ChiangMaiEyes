"""Fire prediction (Phase 2): forward-looking ignition risk, extended spread,
full weather forecast, and PM2.5 forecast.

Deliberately NOT a trained ML model — ignition risk reuses the exact
district-danger formula from fire_phase.py (fuel + history + dryness) but
feeds it *forecast* humidity/rain from Open-Meteo instead of *current*
conditions, so a district's projected score is directly comparable to its
live one. Spread is likewise the same Rothermel-simplified projection
already used for "during" districts, just fed forecast wind for 48h/72h
instead of only the live 6/12/24h.

PM2.5 forecast uses Open-Meteo's Air Quality API, a real CAMS-based
atmospheric model (not fabricated) — verified to support forward
forecast_days and batched multi-location requests. No hotspot-count
forecast is produced: there is no real, freely available source for
predicting satellite-detected fire counts, and fabricating one would
violate this project's data-provenance rules. The ignition-risk score
above is the closest honest proxy and is labelled as such, not as a
hotspot-count prediction.
"""

from __future__ import annotations

import logging
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
            timeout=15.0,
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
        if rh is None:
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
            "temp_max_c": tmax_list[i] if i < len(tmax_list) else None,
            "temp_min_c": tmin_list[i] if i < len(tmin_list) else None,
            "humidity_pct": (sum(hum_values) / len(hum_values)) if hum_values else None,
            "rain_mm": rain_list[i] if i < len(rain_list) else None,
            "wind_kmh": wind_list[i] if i < len(wind_list) else None,
            "wind_dir_deg": wdir_list[i] if i < len(wdir_list) else None,
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
            timeout=20.0,
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
            if val is None:
                continue
            by_day.setdefault(ts[:10], []).append(float(val))
        out[name] = [
            {"date": day, "pm25": round(sum(vals) / len(vals), 1)}
            for day, vals in sorted(by_day.items())
        ]
    return out


def build_fire_predictions(current_phases: FirePhaseResponse) -> FirePredictionResponse:
    forecast_days = _fetch_weather_forecast_days()
    danger_by_district_now = {p.district: p.danger_score for p in current_phases.phases}

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
        trend = "stable"
        if len(daily_scores) >= 2:
            delta = daily_scores[-1].danger_score - daily_scores[0].danger_score
            trend = "rising" if delta > _TREND_EPSILON else "falling" if delta < -_TREND_EPSILON else "stable"
        district_forecasts.append(DistrictIgnitionForecast(
            district=district,
            current_danger_score=danger_by_district_now.get(district, 0.0),
            daily=daily_scores,
            trend=trend,
        ))
    district_forecasts.sort(key=lambda d: -(d.daily[-1].danger_score if d.daily else 0.0))

    # Extended spread for districts CURRENTLY "during" — same province-level
    # wind-forecast simplification the live spread projection already falls
    # back to when a district has no per-district live reading.
    spread_forecast: list[SpreadForecastExtended] = []
    during_districts = [p for p in current_phases.phases if p.phase == "during"]
    if during_districts and forecast_days:
        tomorrow = forecast_days[0]
        wind_speed = tomorrow["wind_kmh"] or 0.0
        wind_dir = tomorrow["wind_dir_deg"] or 0.0
        for p in during_districts:
            proj = _build_spread_projection(p.district, wind_speed, wind_dir)
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
    pm25_locations: list[tuple[str, float, float]] = [("จังหวัดเชียงใหม่", _CM_LAT, _CM_LON)]
    for district in DISTRICT_PHYSICS:
        centroid = _DISTRICT_CENTROIDS.get(district)
        if centroid:
            pm25_locations.append((district, centroid[0], centroid[1]))
    pm25_by_location = _fetch_pm25_forecast_batch(pm25_locations)

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
            "พยากรณ์ความเสี่ยงจุดติดไฟใช้พยากรณ์อากาศจริงจาก Open-Meteo (ความชื้น/ฝน "
            f"{_FORECAST_DAYS} วันข้างหน้า) ผ่านสูตรเดียวกับคะแนนความเสี่ยงปัจจุบัน "
            "ไม่ใช่แบบจำลอง machine learning"
        )
        notes.append("การลามไฟ 48/72 ชม. ใช้ทิศ/ความเร็วลมพยากรณ์ระดับจังหวัด (ไม่แยกรายอำเภอ) เป็นค่าประมาณเท่านั้น")
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
        "จึงไม่แสดงเป็นตัวเลขจำนวนจุด — ใช้คะแนนความเสี่ยงจุดติดไฟด้านบนเป็นตัวช่วยประเมินแทน"
    )

    return FirePredictionResponse(
        generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_mode="DERIVED",
        district_forecasts=district_forecasts,
        spread_forecast_72h=spread_forecast,
        weather_forecast=weather_forecast,
        pm25_forecast_province=pm25_forecast_province,
        pm25_forecast_districts=pm25_forecast_districts,
        notes=notes,
    )
