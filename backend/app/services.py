import json
import logging
from pathlib import Path

from app.config import Settings
from app.models import (
    DashboardResponse,
    HotspotResponse,
    Pm25Response,
    RiskResponse,
    SummaryResponse,
    WeatherResponse,
)
from app.providers.weather_provider import fetch_live_weather
from app.providers.pm25_provider import fetch_live_pm25
from app.providers.hotspot_provider import fetch_live_hotspots

logger = logging.getLogger(__name__)

AQI_COLORS = {
    "ดี": "green",
    "ปานกลาง": "yellow",
    "เริ่มมีผลกระทบต่อสุขภาพ": "orange",
    "มีผลกระทบต่อสุขภาพ": "red",
    "อันตราย": "purple",
}


def read_json(cache_dir: Path, filename: str) -> dict:
    with (cache_dir / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(cache_dir: Path, filename: str, data: dict) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with (cache_dir / filename).open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error writing cached JSON file {filename}: {e}")


def get_hotspots(settings: Settings) -> HotspotResponse:
    try:
        response = fetch_live_hotspots(settings.gistda_api_key, settings.nasa_firms_map_key)
        write_json(settings.cache_dir, "hotspots.json", response.model_dump())
        return response
    except Exception as e:
        logger.warning(f"Failed to fetch live hotspots, falling back to cached file: {e}")
        data = read_json(settings.cache_dir, "hotspots.json")
        return HotspotResponse(**data)


def get_pm25(settings: Settings) -> Pm25Response:
    try:
        response = fetch_live_pm25()
        write_json(settings.cache_dir, "pm25.json", response.model_dump())
        return response
    except Exception as e:
        logger.warning(f"Failed to fetch live PM2.5, falling back to cached file: {e}")
        data = read_json(settings.cache_dir, "pm25.json")
        return Pm25Response(**data)


def get_weather(settings: Settings) -> WeatherResponse:
    try:
        response = fetch_live_weather()
        write_json(settings.cache_dir, "weather.json", response.model_dump())
        return response
    except Exception as e:
        logger.warning(f"Failed to fetch live weather, falling back to cached file: {e}")
        data = read_json(settings.cache_dir, "weather.json")
        return WeatherResponse(**data)


def wind_pushes_smoke_to_city(wind_direction_deg: int) -> bool:
    # Approximation for smoke movement toward Chiang Mai city from western/northern fire areas.
    return 180 <= wind_direction_deg <= 330


def calculate_risk(pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse) -> RiskResponse:
    pm25_points = min(pm25.current_pm25 / 15, 4)
    hotspot_points = min(hotspots.count / 50, 4)
    wind_points = 2 if wind_pushes_smoke_to_city(weather.wind_direction_deg) else 0
    score = round(pm25_points + hotspot_points + wind_points)
    score = max(0, min(score, 10))

    if score <= 3:
        category = "Low"
    elif score <= 6:
        category = "Medium"
    else:
        category = "High"

    return RiskResponse(
        score=score,
        category=category,
        formula="min(10, round(min(PM2.5/15,4) + min(hotspot_count/50,4) + wind_factor))",
        factors={
            "pm25_points": round(pm25_points, 2),
            "hotspot_points": round(hotspot_points, 2),
            "wind_factor": wind_points,
            "wind_pushes_smoke_to_city": "yes" if wind_points else "no",
        },
    )


def fallback_summary(pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse, risk: RiskResponse) -> SummaryResponse:
    if risk.category == "High":
        action = "ควรลดกิจกรรมกลางแจ้งและติดตามประกาศจากหน่วยงานท้องถิ่น"
    elif risk.category == "Medium":
        action = "ประชาชนกลุ่มเสี่ยงควรระวังและตรวจสอบคุณภาพอากาศก่อนออกนอกอาคาร"
    else:
        action = "สถานการณ์โดยรวมยังอยู่ในระดับเฝ้าระวัง"

    text = (
        f"เชียงใหม่มีค่า PM2.5 เฉลี่ย {pm25.current_pm25:.0f} ไมโครกรัมต่อลูกบาศก์เมตร "
        f"อยู่ในระดับ{pm25.category} พบจุดความร้อน {hotspots.count} จุด "
        f"และลมพัดจากทิศ {weather.wind_direction_text} ด้วยความเร็ว {weather.wind_speed_kmh:.0f} กม./ชม. "
        f"คะแนนความเสี่ยงอยู่ที่ {risk.score}/10 ระดับ {risk.category} {action}"
    )
    return SummaryResponse(language="th", text=text, source="rule-based fallback")


def get_summary(settings: Settings, pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse, risk: RiskResponse) -> SummaryResponse:
    # MVP keeps a deterministic fallback so the dashboard works without paid AI usage.
    # Gemini free tier can be wired here with settings.gemini_api_key.
    return fallback_summary(pm25, hotspots, weather, risk)


def get_dashboard(settings: Settings) -> DashboardResponse:
    hotspots = get_hotspots(settings)
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = get_summary(settings, pm25, hotspots, weather, risk)
    return DashboardResponse(hotspots=hotspots, pm25=pm25, weather=weather, risk=risk, summary=summary)
