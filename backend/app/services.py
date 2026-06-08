import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import math
from app.fire_spread_physics import get_district_physics
from app.config import Settings
from app.models import (
    AnnualHotspotStats,
    DailyMetric,
    DataStatusResponse,
    DashboardResponse,
    DroughtZone,
    HistoryResponse,
    HotspotHistoryDay,
    HotspotHistoryResponse,
    HotspotResponse,
    LanduseBreakdownItem,
    LocalizedPrediction,
    OperationalIntelligenceResponse,
    Pm25Response,
    RiskResponse,
    SummaryResponse,
    WeeklyForestLeagueResponse,
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
from app.weekly_forest_league import (
    CommunityForestRecord,
    FieldActivityReport,
    aggregate_weekly_rankings,
    sunday_week_id,
)

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

_FOREST_RECORDS = [
    CommunityForestRecord(
        forest_id="cf-mae-chaem-001",
        forest_name="ป่าชุมชนแม่แจ่ม",
        village="บ้านแม่ปาน",
        tambon="ช่างเคิ่ง",
        amphoe="แม่แจ่ม",
        latitude=18.503,
        longitude=98.361,
    ),
    CommunityForestRecord(
        forest_id="cf-chiang-dao-001",
        forest_name="ป่าชุมชนสันเขาเชียงดาว",
        village="บ้านถ้ำ",
        tambon="เชียงดาว",
        amphoe="เชียงดาว",
        latitude=19.367,
        longitude=98.964,
    ),
    CommunityForestRecord(
        forest_id="cf-samoeng-001",
        forest_name="ป่าชุมชนสะเมิงตะวันตก",
        village="บ้านแม่สาบ",
        tambon="สะเมิงใต้",
        amphoe="สะเมิง",
        latitude=18.848,
        longitude=98.732,
    ),
]

_FIELD_REPORTS = [
    FieldActivityReport(
        report_id="rpt-001",
        forest_id="cf-mae-chaem-001",
        village_id="ban-mae-pan",
        reporter_hash="op-101",
        submitted_at=datetime.fromisoformat("2026-06-07T07:30:00+07:00"),
        patrol_count=3,
        firebreak_km=1.8,
        fuel_management_rai=28,
        water_points_checked=3,
        committee_meeting=True,
        budget_used_baht=4500,
        community_use_activity=True,
        biodiversity_note="ตรวจอัตรารอดของกล้าไม้",
        no_burn_agreement=True,
    ),
    FieldActivityReport(
        report_id="rpt-002",
        forest_id="cf-chiang-dao-001",
        village_id="ban-tham",
        reporter_hash="op-202",
        submitted_at=datetime.fromisoformat("2026-06-06T16:20:00+07:00"),
        patrol_count=2,
        firebreak_km=1.1,
        fuel_management_rai=12,
        water_points_checked=2,
        committee_meeting=True,
        budget_used_baht=2000,
        community_use_activity=False,
        biodiversity_note="ตรวจแนวไผ่แห้ง",
        no_burn_agreement=True,
    ),
    FieldActivityReport(
        report_id="rpt-003",
        forest_id="cf-samoeng-001",
        village_id="ban-mae-sap",
        reporter_hash="op-303",
        submitted_at=datetime.fromisoformat("2026-06-05T09:10:00+07:00"),
        patrol_count=1,
        firebreak_km=0.6,
        fuel_management_rai=8,
        water_points_checked=1,
        committee_meeting=False,
        budget_used_baht=0,
        community_use_activity=True,
        biodiversity_note="เชื้อเพลิงสะสมยังสูงใกล้สันเขา",
        no_burn_agreement=False,
    ),
]

_DROUGHT_ZONES = [
    DroughtZone(
        id="dry-mae-chaem",
        location_name="สันเขาฝั่งตะวันตก อ.แม่แจ่ม",
        latitude=18.501,
        longitude=98.356,
        soil_moisture_percent=18.0,
        drought_index=0.78,
        trend="drying",
        risk_level="high",
    ),
    DroughtZone(
        id="dry-chiang-dao",
        location_name="ชายป่าหินปูน อ.เชียงดาว",
        latitude=19.366,
        longitude=98.966,
        soil_moisture_percent=21.5,
        drought_index=0.69,
        trend="stable",
        risk_level="medium",
    ),
    DroughtZone(
        id="dry-samoeng",
        location_name="แนวสะสมเชื้อเพลิง อ.สะเมิง",
        latitude=18.849,
        longitude=98.73,
        soil_moisture_percent=16.2,
        drought_index=0.83,
        trend="drying",
        risk_level="critical",
    ),
]


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
        response = fetch_live_hotspots(
            settings.gistda_api_key,
            settings.nasa_firms_map_key,
            settings.gistda_disaster_api_key,
        )
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


def _landuse_breakdown(hotspots: HotspotResponse) -> list[LanduseBreakdownItem]:
    labels = {
        "NRF": "ป่าสงวนแห่งชาติ",
        "CONSERVATION": "ป่าอนุรักษ์",
        "AGRI": "พื้นที่เกษตร",
        "ALRO": "เขต ส.ป.ก.",
        "HIGHWAY": "พื้นที่ริมทางหลวง",
        "OTHER": "ชุมชนและอื่น ๆ",
    }
    counts: dict[str, int] = {}
    for item in hotspots.items:
        key = item.landuse_type or "OTHER"
        counts[key] = counts.get(key, 0) + 1

    if not counts:
        counts = {
            "NRF": 5,
            "CONSERVATION": 1,
            "AGRI": 1,
            "OTHER": 1,
        }

    total = max(1, sum(counts.values()))
    return [
        LanduseBreakdownItem(
            landuse_type=key,
            label=labels.get(key, key),
            count=count,
            percent=round((count / total) * 100, 1),
        )
        for key, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    ]


def _localized_predictions(
    hotspots: HotspotResponse,
    pm25: Pm25Response,
    weather: WeatherResponse,
    risk: RiskResponse,
) -> list[LocalizedPrediction]:
    source_hotspots = hotspots.items[:5]
    nearby_fire_count = len(source_hotspots)
    wind_to = "แนวปลายลม"
    if 180 <= weather.wind_direction_deg <= 330:
        wind_to = "หุบเขาเชียงใหม่"

    base_pm = round(pm25.current_pm25)
    smoke_severity = "critical" if base_pm >= 75 or risk.score >= 8 else "high" if base_pm >= 37 or risk.score >= 6 else "watch"
    fire_severity = "critical" if hotspots.count >= 50 else "high" if hotspots.count >= 10 else "watch"

    return [
        LocalizedPrediction(
            id="pred-smoke-mae-chaem",
            locationName="บ้านแม่ปาน อ.แม่แจ่ม",
            latitude=18.503,
            longitude=98.361,
            forecastType="dust",
            severity=smoke_severity,
            reason_for_prediction=(
                f"PM2.5 อาจเพิ่มขึ้นใกล้บ้านแม่ปานใน 12 ชั่วโมง เพราะลม "
                f"{weather.wind_speed_kmh:.1f} กม./ชม. พาควันไปทาง{wind_to} "
                f"มีจุดความร้อนใกล้เคียง {nearby_fire_count} จุด และภูมิประเทศแบบหุบเขาระบายอากาศช้า"
            ),
            lead_time_hours=12,
        ),
        LocalizedPrediction(
            id="pred-fire-samoeng",
            locationName="บ้านแม่สาบ อ.สะเมิง",
            latitude=18.849,
            longitude=98.73,
            forecastType="fire",
            severity=fire_severity,
            reason_for_prediction=(
                "ต้องเฝ้าระวังไฟลามมากขึ้น เพราะแนวเชื้อเพลิงสะเมิงมีความชื้นดินต่ำ "
                "ใบไม้แห้งสะสม และรายงานชุมชนยังพบงานจัดการเชื้อเพลิงค้างอยู่ในสัปดาห์นี้"
            ),
            lead_time_hours=24,
        ),
        LocalizedPrediction(
            id="pred-smoke-chiang-dao",
            locationName="บ้านถ้ำ อ.เชียงดาว",
            latitude=19.367,
            longitude=98.964,
            forecastType="dust",
            severity="watch" if smoke_severity == "watch" else "high",
            reason_for_prediction=(
                f"ควันอาจสะสมรอบบ้านถ้ำ เพราะทิศลม {weather.wind_direction_deg:.0f} องศา "
                "พาควันไปตามแนวสันเขา และภูมิประเทศหุบเขาหินปูนทำให้ควันกระจายช้าช่วงกลางคืน"
            ),
            lead_time_hours=12,
        ),
    ]


def get_operational_intelligence(
    hotspots: HotspotResponse,
    pm25: Pm25Response,
    weather: WeatherResponse,
    risk: RiskResponse,
) -> OperationalIntelligenceResponse:
    today = datetime.now().date()
    week_start = today - timedelta(days=(today.weekday() + 1) % 7)
    ranking = aggregate_weekly_rankings(_FOREST_RECORDS, _FIELD_REPORTS, week_start)
    this_year = max(43731, hotspots.count * 120)
    last_year = 51280
    change = round(((this_year - last_year) / last_year) * 100, 1)
    return OperationalIntelligenceResponse(
        annual_hotspot_stats=AnnualHotspotStats(
            this_year_count=this_year,
            last_year_count=last_year,
            change_percent=change,
            source="ข้อมูลจำลองแนว GISTDA/TAMFIRE สำหรับเทียบจุดความร้อนสะสมรายปี",
        ),
        drought_zones=_DROUGHT_ZONES,
        landuse_breakdown=_landuse_breakdown(hotspots),
        weekly_forest_league=WeeklyForestLeagueResponse(
            week_id=sunday_week_id(today),
            scoring_window=f"{week_start.isoformat()} to {(week_start + timedelta(days=6)).isoformat()}",
            scheduled_recompute="คำนวณใหม่ทุกวันอาทิตย์ 23:55 น. เวลาไทย และรีเฟรชรายคืนเพื่ออัปเดตคะแนนย้อนหลัง 7 วัน",
            rate_limit_rule="รับรายงานกิจกรรมภาคสนามได้ 1 ครั้งต่อป่าชุมชน/หมู่บ้าน/วัน",
            ranking=ranking,
        ),
        localizedPredictions=_localized_predictions(hotspots, pm25, weather, risk),
        source_notes=[
            "ชั้นข้อมูลรอยไหม้และความถี่การไหม้สามารถเปลี่ยนเป็น GISTDA API Gateway WMS/WMTS ได้เมื่อมี API key",
            "ข้อมูลภัยแล้งและความชื้นดินยังเป็นตัวชี้วัดจำลองแนว TAMFIRE ระหว่างรอ feed สาธารณะที่เสถียร",
            "อันดับรายสัปดาห์ใช้ 4 มิติ: การจัดการ การป้องกัน การใช้ประโยชน์ และผลลัพธ์เชิงนิเวศ",
        ],
    )


def get_dashboard(settings: Settings) -> DashboardResponse:
    hotspots = get_hotspots(settings)
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = get_summary(settings, pm25, hotspots, weather, risk)
    intelligence = get_operational_intelligence(hotspots, pm25, weather, risk)
    return DashboardResponse(
        hotspots=hotspots,
        pm25=pm25,
        weather=weather,
        risk=risk,
        summary=summary,
        intelligence=intelligence,
    )
