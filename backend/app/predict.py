"""Fire prediction (Phase 2): forward-looking ignition risk + extended spread.

Deliberately NOT a trained ML model — this reuses the exact district-danger
formula from fire_phase.py (fuel + history + dryness) but feeds it *forecast*
humidity/rain from Open-Meteo instead of *current* conditions, so a district's
projected score is directly comparable to its live one. Spread is likewise
the same Rothermel-simplified projection already used for "during" districts,
just fed forecast wind for 48h/72h instead of only the live 6/12/24h. No
PM2.5 or hotspot-count forecast is produced: there is no real, freely
available source for either, and fabricating one would violate this
project's data-provenance rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.fire_phase import _build_spread_projection, district_base_danger, dryness_from_humidity_rain
from app.fire_spread_physics import DISTRICT_PHYSICS
from app.models import (
    DailyIgnitionForecast,
    DistrictIgnitionForecast,
    FirePhaseResponse,
    FirePredictionResponse,
    SpreadForecastExtended,
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
                "daily": "precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant",
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
    rain_list = daily.get("precipitation_sum") or []
    wind_list = daily.get("wind_speed_10m_max") or []
    wdir_list = daily.get("wind_direction_10m_dominant") or []

    out: list[dict] = []
    for i, day in enumerate(days):
        hum_values = humidity_by_day.get(day, [])
        out.append({
            "date": day,
            "humidity_pct": (sum(hum_values) / len(hum_values)) if hum_values else None,
            "rain_mm": rain_list[i] if i < len(rain_list) else None,
            "wind_kmh": wind_list[i] if i < len(wind_list) else None,
            "wind_dir_deg": wdir_list[i] if i < len(wdir_list) else None,
        })
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

    notes = (
        [
            "พยากรณ์ความเสี่ยงจุดติดไฟใช้พยากรณ์อากาศจริงจาก Open-Meteo (ความชื้น/ฝน "
            f"{_FORECAST_DAYS} วันข้างหน้า) ผ่านสูตรเดียวกับคะแนนความเสี่ยงปัจจุบัน "
            "ไม่ใช่แบบจำลอง machine learning",
            "การลามไฟ 48/72 ชม. ใช้ทิศ/ความเร็วลมพยากรณ์ระดับจังหวัด (ไม่แยกรายอำเภอ) เป็นค่าประมาณเท่านั้น",
            "ยังไม่มีแบบจำลองพยากรณ์ PM2.5 หรือจำนวนจุดความร้อนล่วงหน้าที่น่าเชื่อถือ "
            "จึงไม่แสดงในหน้านี้ เพื่อไม่ให้เข้าใจผิดว่าเป็นตัวเลขจริง",
        ]
        if forecast_days
        else ["ดึงพยากรณ์อากาศไม่สำเร็จในขณะนี้ ลองใหม่อีกครั้ง"]
    )

    return FirePredictionResponse(
        generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_mode="DERIVED",
        district_forecasts=district_forecasts,
        spread_forecast_72h=spread_forecast,
        notes=notes,
    )
