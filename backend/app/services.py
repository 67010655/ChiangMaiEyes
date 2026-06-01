import json
import logging
import time
from pathlib import Path
from typing import Any, TypeVar

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
from app.text import repair_thai_mojibake_tree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple TTL cache to avoid hammering upstream APIs on every request.
# Upstream data (Air4Thai, GISTDA, Open-Meteo) updates every 1-6 hours;
# a 5-minute TTL is a good balance between freshness and rate-limit safety.
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 300  # 5 minutes

T = TypeVar("T")

_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    return value


def _set_cached(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)

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
        logger.error("Error writing cached JSON file %s: %s", filename, e)


def get_hotspots(settings: Settings) -> HotspotResponse:
    cached = _get_cached("hotspots")
    if cached is not None:
        return cached
    try:
        response = fetch_live_hotspots(settings.gistda_api_key, settings.nasa_firms_map_key)
        response = HotspotResponse(**repair_thai_mojibake_tree(response.model_dump()))
        write_json(settings.cache_dir, "hotspots.json", response.model_dump())
        _set_cached("hotspots", response)
        return response
    except Exception as e:
        logger.warning("Failed to fetch live hotspots, falling back to cached file: %s", e)
        data = read_json(settings.cache_dir, "hotspots.json")
        return HotspotResponse(**data)


def get_pm25(settings: Settings) -> Pm25Response:
    cached = _get_cached("pm25")
    if cached is not None:
        return cached
    try:
        response = fetch_live_pm25()
        response = Pm25Response(**repair_thai_mojibake_tree(response.model_dump()))
        write_json(settings.cache_dir, "pm25.json", response.model_dump())
        _set_cached("pm25", response)
        return response
    except Exception as e:
        logger.warning("Failed to fetch live PM2.5, falling back to cached file: %s", e)
        data = read_json(settings.cache_dir, "pm25.json")
        return Pm25Response(**data)


def get_weather(settings: Settings) -> WeatherResponse:
    cached = _get_cached("weather")
    if cached is not None:
        return cached
    try:
        response = fetch_live_weather()
        response = WeatherResponse(**repair_thai_mojibake_tree(response.model_dump()))
        write_json(settings.cache_dir, "weather.json", response.model_dump())
        _set_cached("weather", response)
        return response
    except Exception as e:
        logger.warning("Failed to fetch live weather, falling back to cached file: %s", e)
        data = read_json(settings.cache_dir, "weather.json")
        return WeatherResponse(**data)


def wind_pushes_smoke_to_city(wind_direction_deg: float) -> bool:
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
    return SummaryResponse(language="th", text=repair_thai_mojibake_tree(text), source="rule-based fallback")


def _gemini_text(api_key: str, model_name: str, prompt: str) -> str:
    import concurrent.futures
    import google.generativeai as genai  # type: ignore[import-not-found]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(model.generate_content, prompt)
        response = future.result(timeout=10)
    return response.text.strip()


def get_summary(settings: Settings, pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse, risk: RiskResponse) -> SummaryResponse:
    cached = _get_cached("summary")
    if cached is not None:
        return cached

    result = _compute_summary(settings, pm25, hotspots, weather, risk)
    _set_cached("summary", result)
    return result


def _compute_summary(settings: Settings, pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse, risk: RiskResponse) -> SummaryResponse:
    if not settings.gemini_api_key:
        return fallback_summary(pm25, hotspots, weather, risk)

    prompt = (
        f"สรุปสถานการณ์ฝุ่น PM2.5 และไฟป่าจังหวัดเชียงใหม่วันนี้เป็นภาษาไทย 2-3 ประโยคกระชับ โดยใช้ข้อมูลต่อไปนี้:\n"
        f"- ค่า PM2.5 เฉลี่ย {pm25.current_pm25:.0f} µg/m³ ระดับ{pm25.category}\n"
        f"- จุดความร้อน {hotspots.count} จุดในเชียงใหม่\n"
        f"- ลมพัดจากทิศ{weather.wind_direction_text} ความเร็ว {weather.wind_speed_kmh:.0f} กม./ชม.\n"
        f"- คะแนนความเสี่ยงหมอกควัน {risk.score}/10 ระดับ{risk.category}\n"
        "ตอบเป็นภาษาไทยเท่านั้น ไม่ต้องมีหัวข้อ ไม่ต้องใช้ markdown "
        "ใช้ภาษากลาง เข้าใจง่ายสำหรับประชาชนทั่วไป ไม่เกิน 3 ประโยค"
    )

    try:
        text = _gemini_text(settings.gemini_api_key, settings.gemini_model, prompt)
        return SummaryResponse(language="th", text=text, source="Gemini AI")
    except Exception as e:
        logger.warning("Gemini call failed, using fallback: %s", e)
        return fallback_summary(pm25, hotspots, weather, risk)


def get_dashboard(settings: Settings) -> DashboardResponse:
    hotspots = get_hotspots(settings)
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = get_summary(settings, pm25, hotspots, weather, risk)
    return DashboardResponse(hotspots=hotspots, pm25=pm25, weather=weather, risk=risk, summary=summary)
