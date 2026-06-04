import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import math
from app.fire_spread_physics import get_district_physics
from app.config import Settings
from app.models import (
    DailyMetric,
    DataStatusResponse,
    DashboardResponse,
    HistoryResponse,
    HotspotHistoryDay,
    HotspotHistoryResponse,
    HotspotResponse,
    Pm25Response,
    RiskResponse,
    SummaryResponse,
    WeatherHistoryDay,
    WeatherResponse,
)
from app.providers.weather_provider import fetch_live_weather
from app.providers.pm25_provider import fetch_live_pm25
from app.providers.history_provider import fetch_pm25_history, fetch_weather_history
from app.providers.hotspot_provider import (
    FOREST_FIREMAP_SOURCE,
    fetch_hotspot_history,
    fetch_live_hotspots,
)
from app.text import repair_thai_mojibake_tree

logger = logging.getLogger(__name__)

# Snapshot files baked into the deployment. Always readable (even on a
# read-only serverless FS), so they are the last-resort source when neither
# live providers nor a writable cache can supply data.
_BUNDLED_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Simple TTL cache to avoid hammering upstream APIs on every request.
# Upstream data (Air4Thai, GISTDA, TMD AWS) updates every 1-6 hours;
# a 5-minute TTL is a good balance between freshness and rate-limit safety.
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 300  # 5 minutes
# Historical series are immutable except for "today", so cache them far longer
# to avoid re-running the heavy multi-request NASA chain every 5 minutes.
_HISTORY_TTL_SECONDS = 1800  # 30 minutes

T = TypeVar("T")

_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str, ttl: float = _CACHE_TTL_SECONDS) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > ttl:
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


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_data_status(settings: Settings, now: str | None = None) -> DataStatusResponse:
    hotspots = read_json(settings.cache_dir, "hotspots.json")
    pm25 = read_json(settings.cache_dir, "pm25.json")
    weather = read_json(settings.cache_dir, "weather.json")
    latest_update = max(
        hotspots["latest_update"],
        pm25["latest_update"],
        weather["latest_update"],
        key=_parse_datetime,
    )
    current_time = _parse_datetime(now) if now else datetime.now(tz=_parse_datetime(latest_update).tzinfo)
    age_seconds = max(0, (current_time - _parse_datetime(latest_update)).total_seconds())

    return DataStatusResponse(
        mode="local-refresh-snapshot",
        latest_update=latest_update,
        snapshot_age_minutes=round(age_seconds / 60),
        hotspot_count=hotspots["count"],
        source=hotspots["source"],
        source_breakdown=hotspots.get("source_breakdown", {}),
        local_refresh_required=True,
        vercel_fetches_rfd_directly=False,
        notes=[
            "RFD blocks non-Thai infrastructure, so this deployment serves the latest local refresh snapshot.",
            "The Windows startup launcher and hourly task refresh data from this PC, then push changed snapshots to Vercel.",
        ],
    )


def _serve_hotspot_snapshot(settings: Settings) -> HotspotResponse:
    """Serve the most recent hotspot snapshot, preferring a writable cache
    (refreshed from Thailand) and falling back to the bundled deploy file so a
    read-only or empty /tmp can never turn this into a 500."""
    for directory in (settings.cache_dir, _BUNDLED_DATA_DIR):
        try:
            snapshot = HotspotResponse(**read_json(directory, "hotspots.json"))
            _set_cached("hotspots", snapshot)
            return snapshot
        except Exception as exc:  # noqa: BLE001 — try the next location
            logger.debug("Hotspot snapshot unavailable in %s: %s", directory, exc)
    raise RuntimeError("No hotspot snapshot available")


def get_hotspots(settings: Settings) -> HotspotResponse:
    cached = _get_cached("hotspots")
    if cached is not None:
        return cached
    try:
        response = fetch_live_hotspots(settings.gistda_api_key, settings.nasa_firms_map_key)
        response = HotspotResponse(**repair_thai_mojibake_tree(response.model_dump()))
        # RFD (Royal Forest Department) is the authoritative, full-coverage source.
        # Infrastructure it blocks (e.g. Vercel's datacenter) only gets partial live
        # data from NASA/GISTDA, which under-counts. When RFD didn't contribute,
        # serve the Thailand-refreshed snapshot — it still carries RFD's complete
        # in-province picture — instead of the thin live result.
        if FOREST_FIREMAP_SOURCE not in (response.source_breakdown or {}):
            logger.info(
                "RFD absent from live hotspots — serving snapshot instead of partial live data"
            )
            return _serve_hotspot_snapshot(settings)
        write_json(settings.cache_dir, "hotspots.json", response.model_dump())
        _set_cached("hotspots", response)
        return response
    except Exception as e:
        logger.warning("Failed to fetch live hotspots, falling back to snapshot: %s", e)
        return _serve_hotspot_snapshot(settings)


def get_hotspot_history(settings: Settings) -> HotspotHistoryResponse:
    """7-day in-province hotspot trend from NASA VIIRS for the authority view.
    Best-effort: returns an empty series rather than erroring if NASA is
    unreachable or no key is configured."""
    cached = _get_cached("hotspot_history")
    if cached is not None:
        return cached

    days: list[HotspotHistoryDay] = []
    if settings.nasa_firms_map_key:
        try:
            raw = fetch_hotspot_history(settings.nasa_firms_map_key, 5)
            days = [HotspotHistoryDay(date=d, count=c) for d, c in raw]
        except Exception as e:  # noqa: BLE001 — history is non-critical
            logger.warning("Failed to fetch hotspot history: %s", e)

    response = HotspotHistoryResponse(
        days=days,
        source="NASA VIIRS (SNPP/NOAA-20/NOAA-21)",
        latest_update=datetime.now().isoformat(),
    )
    # Only cache a real series, so a transient NASA failure is retried next call.
    if days:
        _set_cached("hotspot_history", response)
    return response


def get_history(settings: Settings, days: int = 30) -> HistoryResponse:
    """Combined backward trends (hotspots · PM2.5 · weather) for the authority
    view. Every series is best-effort, so one failing provider never sinks the
    others or errors the request."""
    cached = _get_cached("history", ttl=_HISTORY_TTL_SECONDS)
    if cached is not None:
        return cached

    hotspots: list[HotspotHistoryDay] = []
    if settings.nasa_firms_map_key:
        try:
            hotspots = [HotspotHistoryDay(date=d, count=c) for d, c in fetch_hotspot_history(settings.nasa_firms_map_key, days)]
        except Exception as e:  # noqa: BLE001
            logger.warning("Hotspot history failed: %s", e)

    try:
        pm25 = [DailyMetric(date=d, value=v) for d, v in fetch_pm25_history(days)]
    except Exception as e:  # noqa: BLE001
        logger.warning("PM2.5 history failed: %s", e)
        pm25 = []

    try:
        weather = [
            WeatherHistoryDay(date=d, temp_max=hi, temp_min=lo, wind_max=wind, humidity=hum)
            for d, hi, lo, wind, hum in fetch_weather_history(days)
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("Weather history failed: %s", e)
        weather = []

    response = HistoryResponse(
        days=days,
        hotspots=hotspots,
        pm25=pm25,
        weather=weather,
        sources={
            "hotspots": "NASA VIIRS (SNPP/NOAA-20/NOAA-21)",
            "pm25": "Open-Meteo Air Quality",
            "weather": "Open-Meteo (ECMWF/GFS)",
        },
        latest_update=datetime.now().isoformat(),
    )
    # Cache only when we actually got something, so transient failures retry.
    if hotspots or pm25 or weather:
        _set_cached("history", response)
    return response


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
    # 1. Base PM2.5 points (max 3 points)
    pm25_points = min(pm25.current_pm25 / 20.0, 3.0)
    
    # 2. Hotspot points (max 3 points)
    hotspot_points = min(hotspots.count / 40.0, 3.0)
    
    # 3. Wind and physical spread factor (max 4 points)
    wind_speed = weather.wind_speed_kmh
    wind_direction = weather.wind_direction_deg
    
    total_flammability = 0.0
    total_slope_factor = 0.0
    total_history_factor = 0.0
    
    if hotspots.items:
        for h in hotspots.items:
            phys = get_district_physics(h.district)
            total_flammability += phys["fuel_flammability"]
            # Slope factor increases Rate of Spread exponentially
            # ROS_slope = e^(0.0693 * slope) -> normalized slope multiplier
            slope = phys["slope_deg"]
            slope_factor = math.exp(0.0693 * slope) / 4.0 # normalized around 20 deg slope (~1.0)
            total_slope_factor += slope_factor
            total_history_factor += phys["history_multiplier"]
            
        avg_flammability = total_flammability / len(hotspots.items)
        avg_slope_factor = total_slope_factor / len(hotspots.items)
        avg_history_factor = total_history_factor / len(hotspots.items)
    else:
        avg_flammability = 1.2
        avg_slope_factor = 1.0
        avg_history_factor = 1.2
        
    # Rate of Spread (ROS) index based on wind speed, slope, flammability, history
    # Let's normalize wind_speed (5 kmh -> multiplier of 1.0)
    wind_multiplier = 1.0 + (wind_speed / 15.0)
    
    # Wind direction risk
    pushes = wind_pushes_smoke_to_city(wind_direction)
    wind_direction_mult = 1.4 if pushes else 0.8
    
    # Combined Spread Danger Index (SDI)
    spread_danger = avg_flammability * avg_slope_factor * avg_history_factor * wind_multiplier * wind_direction_mult
    
    # Map to spread points (0 to 4)
    spread_points = min(spread_danger * 1.25, 4.0)
    
    # Calculate score (out of 10)
    score = round(pm25_points + hotspot_points + spread_points)
    score = max(0, min(score, 10))
    
    if score <= 3:
        category = "Low"
    elif score <= 6:
        category = "Medium"
    else:
        category = "High"
        
    formula = "min(10, round(PM2.5_pts(3) + Hotspot_pts(3) + Spread_pts(4))) where Spread = Flammability * Slope * History * Wind"
    
    return RiskResponse(
        score=score,
        category=category,
        formula=formula,
        factors={
            "pm25_points": round(pm25_points, 2),
            "hotspot_points": round(hotspot_points, 2),
            "spread_points": round(spread_points, 2),
            "avg_flammability": round(avg_flammability, 2),
            "avg_slope_factor": round(avg_slope_factor, 2),
            "avg_history_factor": round(avg_history_factor, 2),
            "wind_speed_kmh": wind_speed,
            "wind_pushes_smoke_to_city": "yes" if pushes else "no",
        }
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
