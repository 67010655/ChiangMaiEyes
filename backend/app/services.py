import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeVar

import httpx
import math
from app.fire_spread_physics import get_district_physics
from app.config import Settings, get_settings
from app.models import (
    HotspotTrendStats,
    DailyMetric,
    FieldReportResult,
    FieldReportSubmission,
    FirePhaseResponse,
    DataQualityMetadata,
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
    SatelliteLayerResponse,
    SummaryResponse,
    SourceMode,
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
from app.providers.earth_engine_provider import load_satellite_layers
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
# User-facing values should refresh within the decision-support window, without
# hammering free upstream APIs on every frontend poll.
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 900  # 15 minutes
_REMOTE_SNAPSHOT_TTL_SECONDS = 30
# Historical series are immutable except for "today", so cache them far longer
# to avoid re-running the heavy multi-request NASA chain every 5 minutes.
_HISTORY_TTL_SECONDS = 1800  # 30 minutes
_HOURLY_DECISION_CADENCE_MINUTES = 60
_SATELLITE_HOTSPOT_EXPECTED_LAG_MINUTES = 300
_SATELLITE_HOTSPOT_STALE_AFTER_MINUTES = 360
_LIVE_SENSOR_STALE_AFTER_MINUTES = 180

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


def _read_optional_json(cache_dir: Path, filename: str) -> dict[str, Any] | None:
    for directory in (cache_dir, _BUNDLED_DATA_DIR):
        try:
            return read_json(directory, filename)
        except Exception:
            continue
    return None


def _snapshot_path(filename: str) -> str:
    if filename == "dashboardSnapshot.json":
        return f"frontend/src/data/{filename}"
    return f"backend/data/{filename}"


def _read_remote_snapshot(settings: Settings, filename: str) -> dict[str, Any] | None:
    if not settings.remote_snapshot_base_url:
        return None

    cache_buster = int(time.time() // _REMOTE_SNAPSHOT_TTL_SECONDS)
    cache_key = f"remote_snapshot:{settings.remote_snapshot_base_url}:{filename}:{cache_buster}"
    cached = _get_cached(cache_key, ttl=_REMOTE_SNAPSHOT_TTL_SECONDS)
    if cached is not None:
        return cached

    url = f"{settings.remote_snapshot_base_url.rstrip('/')}/{_snapshot_path(filename)}?v={cache_buster}"
    try:
        response = httpx.get(
            url,
            timeout=8,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        response.raise_for_status()
        data = response.json()
        _set_cached(cache_key, data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Remote snapshot unavailable for %s: %s", filename, exc)
        return None


def _read_snapshot_json(settings: Settings, filename: str) -> dict[str, Any]:
    remote = _read_remote_snapshot(settings, filename)
    if remote is not None:
        return remote

    try:
        return read_json(settings.cache_dir, filename)
    except Exception:
        pass

    return read_json(_BUNDLED_DATA_DIR, filename)


def _read_optional_snapshot_json(settings: Settings, filename: str) -> dict[str, Any] | None:
    try:
        return _read_snapshot_json(settings, filename)
    except Exception:
        return None


def _official_community_forest_summary() -> dict[str, Any] | None:
    try:
        return read_json(_BUNDLED_DATA_DIR, "community-forests-official.json").get("summary")
    except Exception:
        return None


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _age_minutes(current_time: datetime, updated_at: str) -> int:
    age_seconds = max(0, (current_time - _parse_datetime(updated_at)).total_seconds())
    return round(age_seconds / 60)


def _data_quality(
    *,
    label: str,
    source: str,
    source_mode: SourceMode,
    latest_update: str | None,
    checked_at: str,
    age_minutes: int | None,
    confidence: float,
    stale_after_minutes: int,
    note: str,
    update_cadence_minutes: int | None = None,
    expected_observation_lag_minutes: int | None = None,
    decision_use: str | None = None,
) -> DataQualityMetadata:
    return DataQualityMetadata(
        label=label,
        source=source,
        source_mode=source_mode,
        latest_update=latest_update,
        checked_at=checked_at,
        age_minutes=age_minutes,
        update_cadence_minutes=update_cadence_minutes,
        expected_observation_lag_minutes=expected_observation_lag_minutes,
        confidence=confidence,
        is_stale=age_minutes is not None and age_minutes > stale_after_minutes,
        note=note,
        decision_use=decision_use,
    )


def _build_data_quality(
    hotspots: HotspotResponse,
    pm25: Pm25Response,
    weather: WeatherResponse,
    *,
    settings: Settings | None = None,
    checked_at: str | None = None,
) -> dict[str, DataQualityMetadata]:
    current_time = _parse_datetime(checked_at) if checked_at else datetime.now(tz=_parse_datetime(hotspots.latest_update).tzinfo)
    checked_at = checked_at or current_time.isoformat()
    hotspot_age = _age_minutes(current_time, hotspots.latest_update)
    pm25_age = _age_minutes(current_time, pm25.latest_update)
    weather_age = _age_minutes(current_time, weather.latest_update)
    has_rfd = FOREST_FIREMAP_SOURCE in (hotspots.source_breakdown or {}) or "Royal Forest" in hotspots.source
    hotspot_stale_after = (
        _LIVE_SENSOR_STALE_AFTER_MINUTES
        if has_rfd
        else _SATELLITE_HOTSPOT_STALE_AFTER_MINUTES
    )
    hotspot_source_mode = (
        "UNAVAILABLE"
        if hotspot_age > hotspot_stale_after
        else "SNAPSHOT" if has_rfd else "LIVE"
    )
    satellite_layers_configured = bool(
        settings
        and (
            (settings.copernicus_client_id and settings.copernicus_client_secret)
            or settings.satellite_layers_file
            or settings.earth_engine_enabled
        )
    )
    field_reports_configured = bool(
        settings and settings.supabase_url and settings.supabase_service_role_key
    )
    official_community_summary = _official_community_forest_summary()
    official_community_count = (
        int(official_community_summary.get("recordCount", 0))
        if isinstance(official_community_summary, dict)
        else 0
    )
    satellite_source_mode: SourceMode = "DERIVED" if satellite_layers_configured else "UNAVAILABLE"
    satellite_confidence = 0.62 if satellite_layers_configured else 0.3
    # This entry describes the community-forest POINTS. Official RFD KML points
    # are a static download → SNAPSHOT (matches the "RFD KML" source label and
    # takes priority); only fall back to LIVE submitted field reports otherwise.
    community_source_mode: SourceMode = (
        "SNAPSHOT"
        if official_community_count > 0
        else "LIVE"
        if field_reports_configured
        else "UNAVAILABLE"
    )

    return {
        "hotspots": _data_quality(
            label="Hotspot",
            source=hotspots.source,
            source_mode=hotspot_source_mode,
            latest_update=hotspots.latest_update,
            checked_at=checked_at,
            age_minutes=hotspot_age,
            confidence=0.9 if not hotspot_age > hotspot_stale_after else 0.35,
            stale_after_minutes=hotspot_stale_after,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            expected_observation_lag_minutes=(
                None if has_rfd else _SATELLITE_HOTSPOT_EXPECTED_LAG_MINUTES
            ),
            note=(
                "Authoritative RFD-backed data delivered via the Thailand refresh snapshot "
                "(RFD blocks some serverless infrastructure), not a live request — trust the snapshot age."
                if has_rfd
                else (
                    "Cloud-fetched NASA/GISTDA satellite hotspot feed. Satellite detections can lag field reality "
                    "by about 4-5 hours, so use timestamps and local confirmation before dispatch decisions."
                )
            ),
            decision_use="Hourly decision-support signal; not proof that fire is still active at this minute.",
        ),
        "pm25": _data_quality(
            label="PM2.5",
            source=pm25.source,
            source_mode="LIVE" if not pm25_age > _LIVE_SENSOR_STALE_AFTER_MINUTES else "UNAVAILABLE",
            latest_update=pm25.latest_update,
            checked_at=checked_at,
            age_minutes=pm25_age,
            confidence=0.92 if not pm25_age > _LIVE_SENSOR_STALE_AFTER_MINUTES else 0.4,
            stale_after_minutes=_LIVE_SENSOR_STALE_AFTER_MINUTES,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            note="Station reading from configured air-quality provider.",
            decision_use="Use for current smoke/health situation and trend monitoring.",
        ),
        "weather": _data_quality(
            label="Wind and weather",
            source=weather.source,
            source_mode="LIVE" if not weather_age > _LIVE_SENSOR_STALE_AFTER_MINUTES else "UNAVAILABLE",
            latest_update=weather.latest_update,
            checked_at=checked_at,
            age_minutes=weather_age,
            confidence=0.9 if not weather_age > _LIVE_SENSOR_STALE_AFTER_MINUTES else 0.4,
            stale_after_minutes=_LIVE_SENSOR_STALE_AFTER_MINUTES,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            note="Weather station reading used for wind direction and smoke movement.",
            decision_use="Use for hourly wind/smoke movement decisions.",
        ),
        "risk": _data_quality(
            label="Risk score",
            source="ChiangMaiEyes deterministic formula",
            source_mode="DERIVED",
            latest_update=max(hotspots.latest_update, pm25.latest_update, weather.latest_update, key=_parse_datetime),
            checked_at=checked_at,
            age_minutes=max(hotspot_age, pm25_age, weather_age),
            confidence=0.72,
            stale_after_minutes=_SATELLITE_HOTSPOT_STALE_AFTER_MINUTES,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            note="Calculated from PM2.5, hotspot count, wind, and fire-spread factors. It is not an official warning.",
            decision_use="Use to prioritize review areas; confirm with field/local context before operational action.",
        ),
        "summary": _data_quality(
            label="Situation summary",
            source="ChiangMaiEyes deterministic hourly summary",
            source_mode="DERIVED",
            latest_update=max(hotspots.latest_update, pm25.latest_update, weather.latest_update, key=_parse_datetime),
            checked_at=checked_at,
            age_minutes=max(hotspot_age, pm25_age, weather_age),
            confidence=0.82,
            stale_after_minutes=_SATELLITE_HOTSPOT_STALE_AFTER_MINUTES,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            note="Rule-based operator briefing generated from PM2.5, hotspot, wind, and risk inputs. No Gen AI call.",
            decision_use="Use as a concise hourly briefing for decision meetings and local coordination.",
        ),
        "ndvi": _data_quality(
            label="NDVI",
            source="Sentinel-2 NDVI/NDMI/NBR (Copernicus Data Space; seeded until configured)",
            source_mode=satellite_source_mode,
            latest_update=None,
            checked_at=checked_at,
            age_minutes=None,
            confidence=satellite_confidence,
            stale_after_minutes=0,
            update_cadence_minutes=1440 if satellite_layers_configured else None,
            expected_observation_lag_minutes=1440 if satellite_layers_configured else None,
            note="Zonal dryness indices require Copernicus Data Space, Earth Engine, or a verified export file. Prototype seed values are disabled.",
            decision_use="Use for prevention planning only after real Sentinel/CDSE export is configured.",
        ),
        "fire_zones": _data_quality(
            label="Fire management zones",
            source="Not configured",
            source_mode="UNAVAILABLE",
            latest_update=None,
            checked_at=checked_at,
            age_minutes=None,
            confidence=0.0,
            stale_after_minutes=0,
            note="No verified fire-management vector layer is configured. Prototype boundaries are disabled.",
            decision_use="Import verified shapefile/GeoJSON layers before using this for decisions.",
        ),
        "community_forests": _data_quality(
            label="Community forest points",
            source=(
                "Royal Forest Department community forest coordinates KML"
                if official_community_count > 0
                else "Supabase field reports"
                if field_reports_configured
                else "Not configured"
            ),
            source_mode=community_source_mode,
            latest_update=None,
            checked_at=checked_at,
            age_minutes=None,
            confidence=0.72 if official_community_count > 0 else 0.0,
            stale_after_minutes=0,
            note=(
                f"Official RFD point coordinates loaded for {official_community_count} Chiang Mai community forests; official polygon boundaries are not included."
                if official_community_count > 0
                else "Ranking uses verified submitted field reports."
                if field_reports_configured
                else "No verified community forest reporting database is configured. Seed rankings are disabled."
            ),
            decision_use=(
                "Use for locating official RFD community forest point records; request polygon boundaries before area analysis."
                if official_community_count > 0
                else "Use as submitted-report evidence for participating forests."
                if field_reports_configured
                else "Connect Supabase/PostGIS and verified community forest records before using this layer."
            ),
        ),
        "predictions": _data_quality(
            label="Localized predictions",
            source="Rule-based estimate from dashboard inputs",
            source_mode="DERIVED",
            latest_update=max(hotspots.latest_update, pm25.latest_update, weather.latest_update, key=_parse_datetime),
            checked_at=checked_at,
            age_minutes=max(hotspot_age, pm25_age, weather_age),
            confidence=0.55,
            stale_after_minutes=_SATELLITE_HOTSPOT_STALE_AFTER_MINUTES,
            update_cadence_minutes=_HOURLY_DECISION_CADENCE_MINUTES,
            note="Derived estimate for situational review, not an official forecast.",
            decision_use="Use as a review prompt, not an official forecast or dispatch instruction.",
        ),
    }


def get_data_status(settings: Settings, now: str | None = None) -> DataStatusResponse:
    local_refresh_required = settings.hotspot_include_rfd
    hotspots = _serve_hotspot_snapshot(settings) if local_refresh_required else get_hotspots(settings)
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    latest_update = max(
        hotspots.latest_update,
        pm25.latest_update,
        weather.latest_update,
        key=_parse_datetime,
    )
    current_time = _parse_datetime(now) if now else datetime.now(tz=_parse_datetime(latest_update).tzinfo)
    checked_at = current_time.isoformat()
    refresh_status = _read_optional_snapshot_json(settings, "refresh_status.json") if local_refresh_required else None
    refresh_checked_at = refresh_status.get("checked_at") if refresh_status else None

    return DataStatusResponse(
        mode="local-refresh-snapshot" if local_refresh_required else "live-backend",
        latest_update=latest_update,
        snapshot_age_minutes=_age_minutes(current_time, latest_update),
        refresh_checked_at=refresh_checked_at,
        refresh_age_minutes=(
            _age_minutes(current_time, refresh_checked_at) if isinstance(refresh_checked_at, str) else None
        ),
        refresh_status=refresh_status.get("status") if refresh_status else None,
        hotspot_latest_update=hotspots.latest_update,
        hotspot_age_minutes=_age_minutes(current_time, hotspots.latest_update),
        pm25_latest_update=pm25.latest_update,
        pm25_age_minutes=_age_minutes(current_time, pm25.latest_update),
        weather_latest_update=weather.latest_update,
        weather_age_minutes=_age_minutes(current_time, weather.latest_update),
        hotspot_count=hotspots.count,
        source=hotspots.source,
        source_breakdown=hotspots.source_breakdown,
        local_refresh_required=local_refresh_required,
        vercel_fetches_rfd_directly=False,
        data_quality=_build_data_quality(hotspots, pm25, weather, settings=settings, checked_at=checked_at),
        notes=(
            [
                "Hotspots use NASA/GISTDA cloud-friendly satellite feeds so production does not require the local Thailand refresh PC.",
                "Satellite hotspot detections can lag field reality by about 4-5 hours; use them for hourly decision support with local confirmation.",
                "RFD Firemap is disabled by default because it blocks some serverless infrastructure.",
                "Backend responses are cached briefly to protect free upstream APIs while keeping the dashboard current enough for hourly decisions.",
            ]
            if not local_refresh_required
            else [
                "Hotspots use the latest Thailand refresh snapshot because RFD blocks some serverless infrastructure.",
                "PM2.5 and wind/weather are fetched live by the backend when upstream providers are reachable.",
                "The hourly Windows refresh task publishes refresh_status.json so the UI/API can show when the worker actually checked sources.",
            ]
        ),
    )


def _serve_hotspot_snapshot(settings: Settings) -> HotspotResponse:
    """Serve the newest Thailand-refreshed snapshot without requiring redeploys."""
    snapshot = HotspotResponse(**_read_snapshot_json(settings, "hotspots.json"))
    _set_cached("hotspots", snapshot)
    return snapshot


def get_hotspots(settings: Settings) -> HotspotResponse:
    cached = _get_cached("hotspots")
    if cached is not None:
        return cached
    try:
        response = fetch_live_hotspots(
            settings.gistda_api_key,
            settings.nasa_firms_map_key,
            settings.gistda_disaster_api_key,
            include_forest_firemap=settings.hotspot_include_rfd,
        )
        response = HotspotResponse(**repair_thai_mojibake_tree(response.model_dump()))
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
        data = _read_snapshot_json(settings, "pm25.json")
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
        data = _read_snapshot_json(settings, "weather.json")
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
    return deterministic_hourly_summary(pm25, hotspots, weather, risk)


def _risk_action(risk: RiskResponse, hotspots: HotspotResponse, pm25: Pm25Response) -> str:
    if risk.category == "High":
        return (
            "ข้อเสนอแนะ: ให้ศูนย์สั่งการตรวจสอบพื้นที่จุดความร้อนกับหน่วยพื้นที่ทันที "
            "เตรียมชุดลาดตระเวน/ดับไฟ และสื่อสารเตือนกลุ่มเสี่ยงเรื่องฝุ่น"
        )
    if risk.category == "Medium":
        return (
            "ข้อเสนอแนะ: ให้เจ้าหน้าที่ติดตามจุดความร้อนซ้ำในรอบถัดไป "
            "ตรวจแนวลมที่อาจพาควันเข้าพื้นที่ชุมชน และเตรียมมาตรการลดการเผา"
        )
    if hotspots.count > 0 or pm25.current_pm25 >= 25:
        return (
            "ข้อเสนอแนะ: ยังควรเฝ้าระวังเชิงพื้นที่ โดยเฉพาะอำเภอที่มีจุดความร้อน "
            "และตรวจแนวโน้ม PM2.5 ก่อนตัดสินใจกิจกรรมกลางแจ้ง"
        )
    return "ข้อเสนอแนะ: สถานการณ์เหมาะกับการเฝ้าระวังตามปกติและเตรียมพร้อมข้อมูลสำหรับรอบถัดไป"


def _risk_meaning(risk: RiskResponse) -> str:
    if risk.category == "High":
        return "ระดับสูง ต้องให้ความสำคัญกับการสั่งการภาคสนาม"
    if risk.category == "Medium":
        return "ระดับปานกลาง ต้องติดตามการเปลี่ยนแปลงของลม จุดความร้อน และฝุ่น"
    return "ระดับต่ำถึงเฝ้าระวัง เหมาะกับการติดตามสถานการณ์ตามรอบ"


def _source_summary(hotspots: HotspotResponse) -> str:
    if not hotspots.source_breakdown:
        return hotspots.source
    parts = [f"{source} {count} จุด" for source, count in hotspots.source_breakdown.items()]
    return " · ".join(parts)


def deterministic_hourly_summary(
    pm25: Pm25Response,
    hotspots: HotspotResponse,
    weather: WeatherResponse,
    risk: RiskResponse,
) -> SummaryResponse:
    """Rule-based operator summary. No Gen AI calls by design."""

    updated = max(
        pm25.latest_update,
        hotspots.latest_update,
        weather.latest_update,
        key=_parse_datetime,
    )
    updated_label = _parse_datetime(updated).strftime("%H:%M")
    source_text = _source_summary(hotspots)
    wind_towards = "ทิศปลายลมควรดูประกอบบนแผนที่"
    if isinstance(weather.wind_direction_deg, (int, float)):
        wind_towards = f"ลมมาจาก {weather.wind_direction_text} ความเร็ว {weather.wind_speed_kmh:.0f} กม./ชม."

    text = (
        f"สรุปสถานการณ์รอบ {updated_label} น.: PM2.5 เฉลี่ย {pm25.current_pm25:.0f} µg/m³ "
        f"อยู่ในระดับ {pm25.category}; พบจุดความร้อนในเชียงใหม่ {hotspots.count} จุด "
        f"จากแหล่งข้อมูล {source_text}. "
        f"{wind_towards}; คะแนนความเสี่ยงหมอกควัน {risk.score}/10 ({_risk_meaning(risk)}). "
        f"{_risk_action(risk, hotspots, pm25)}."
    )
    return SummaryResponse(language="th", text=repair_thai_mojibake_tree(text), source="deterministic hourly summary")


def get_summary(settings: Settings, pm25: Pm25Response, hotspots: HotspotResponse, weather: WeatherResponse, risk: RiskResponse) -> SummaryResponse:
    cached = _get_cached("summary")
    if cached is not None:
        return cached

    result = deterministic_hourly_summary(pm25, hotspots, weather, risk)
    _set_cached("summary", result)
    return result


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

    # No fabricated fallback: with zero hotspots there is genuinely nothing to
    # break down, so return an empty list and let the UI say "no active fire".
    if not counts:
        return []

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


def get_satellite_layers(settings: Settings, now: str | None = None) -> SatelliteLayerResponse:
    return load_satellite_layers(settings, now=now)


def get_fire_phases(settings: Settings) -> "FirePhaseResponse":
    from app.fire_phase import classify_fire_phases

    return classify_fire_phases(
        get_hotspots(settings),
        get_weather(settings),
        get_satellite_layers(settings),
    )


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


def _load_field_reports(settings: Settings) -> tuple[list[FieldActivityReport], SourceMode]:
    """Real submitted reports from Supabase when configured, else the seed demo
    set. Returns the reports and the provenance mode for the league response."""
    from app.providers.field_report_store import fetch_field_reports, supabase_enabled

    if supabase_enabled(settings):
        try:
            reports = fetch_field_reports(settings)
            return reports, "LIVE"
        except Exception as exc:  # noqa: BLE001 — never error the dashboard on a store hiccup
            logger.warning("Supabase field reports unavailable, using seed: %s", exc)
    if settings.allow_prototype_data:
        return list(_FIELD_REPORTS), "PROTOTYPE"
    return [], "UNAVAILABLE"


def submit_field_report(settings: Settings, submission: "FieldReportSubmission") -> "FieldReportResult":
    """Validate + persist a community field report, enforcing the daily limit.

    In demo mode (no Supabase) nothing is stored — we say so plainly rather than
    pretending the report was saved."""
    from uuid import uuid4

    import httpx

    from app.providers.field_report_store import (
        insert_field_report,
        report_exists_today,
        supabase_enabled,
    )

    if not supabase_enabled(settings):
        return FieldReportResult(
            accepted=False,
            stored=False,
            message="โหมดสาธิต: ยังไม่ได้เชื่อมฐานข้อมูล รายงานจึงยังไม่ถูกบันทึก",
            source_mode="UNAVAILABLE",
        )

    # Only registered community forests may submit — blocks arbitrary forest_id
    # injection that would bloat the store (junk rows never reach the league,
    # which filters to known forests, but must not be storable in the first place).
    known_forest_ids = {record.forest_id for record in _FOREST_RECORDS}
    if submission.forest_id not in known_forest_ids:
        return FieldReportResult(
            accepted=False,
            stored=False,
            message="ไม่พบรหัสป่าชุมชนนี้ในทะเบียน — ส่งรายงานได้เฉพาะป่าชุมชนที่ลงทะเบียนไว้",
            source_mode="LIVE",
        )

    rate_limited = FieldReportResult(
        accepted=False,
        stored=False,
        message="วันนี้ป่าชุมชน/หมู่บ้านนี้ส่งรายงานแล้ว (จำกัด 1 ครั้งต่อวัน)",
        source_mode="LIVE",
    )

    submitted_at = datetime.now(tz=timezone(timedelta(hours=7)))
    if report_exists_today(settings, submission.forest_id, submission.village_id, submitted_at.date()):
        return rate_limited

    report = FieldActivityReport(
        report_id=f"rpt-{uuid4().hex[:12]}",
        submitted_at=submitted_at,
        **submission.model_dump(),
    )
    try:
        insert_field_report(settings, report)
    except httpx.HTTPStatusError as exc:
        # DB unique index is the authoritative rate-limit; a 409 means another
        # report for this forest/village landed today between our check and insert.
        if exc.response.status_code == 409:
            return rate_limited
        raise
    return FieldReportResult(
        accepted=True,
        stored=True,
        message="บันทึกรายงานภาคสนามเรียบร้อย ขอบคุณที่ช่วยกันดูแลป่า",
        source_mode="LIVE",
    )


def _hotspot_trend(settings: Settings, hotspots: HotspotResponse, window_days: int = 30) -> HotspotTrendStats:
    """Real in-province cumulative from NASA VIIRS daily counts, split recent vs
    previous half so the change is computed, never invented. Falls back to the
    current snapshot count (clearly labelled) when no history is available."""
    series: list[HotspotHistoryDay] = []
    try:
        series = get_history(settings, days=window_days).hotspots
    except Exception as exc:  # noqa: BLE001 — trend is non-critical
        logger.warning("Hotspot trend history unavailable: %s", exc)

    if series:
        counts = [day.count for day in series]
        half = len(counts) // 2
        previous_count = sum(counts[:half])
        recent_count = sum(counts[half:])
        change = (
            round(((recent_count - previous_count) / previous_count) * 100, 1)
            if previous_count
            else 0.0
        )
        return HotspotTrendStats(
            window_days=len(counts),
            recent_count=recent_count,
            previous_count=previous_count,
            change_percent=change,
            source="NASA VIIRS (SNPP/NOAA-20/NOAA-21) จุดความร้อนรายวันในจังหวัด",
        )

    # No history (no NASA key / unreachable): show only the current snapshot count.
    return HotspotTrendStats(
        window_days=0,
        recent_count=hotspots.count,
        previous_count=0,
        change_percent=0.0,
        source="จำนวนปัจจุบันจาก snapshot (ยังไม่มีประวัติย้อนหลังจาก NASA VIIRS)",
    )


def get_operational_intelligence(
    hotspots: HotspotResponse,
    pm25: Pm25Response,
    weather: WeatherResponse,
    risk: RiskResponse,
    settings: Settings | None = None,
) -> OperationalIntelligenceResponse:
    settings = settings or get_settings()
    field_reports, league_mode = _load_field_reports(settings)
    today = datetime.now().date()
    week_start = today - timedelta(days=(today.weekday() + 1) % 7)
    ranking = aggregate_weekly_rankings(_FOREST_RECORDS, field_reports, week_start)
    ranking_week_start = week_start
    if not ranking and field_reports:
        latest_report_day = max(report.submitted_at.date() for report in field_reports)
        ranking_week_start = latest_report_day - timedelta(days=(latest_report_day.weekday() + 1) % 7)
        ranking = aggregate_weekly_rankings(_FOREST_RECORDS, field_reports, ranking_week_start)
    prototype_enabled = settings.allow_prototype_data
    return OperationalIntelligenceResponse(
        hotspot_trend=_hotspot_trend(settings, hotspots),
        drought_zones=_DROUGHT_ZONES if prototype_enabled else [],
        satellite_layers=get_satellite_layers(settings or get_settings()),
        landuse_breakdown=_landuse_breakdown(hotspots),
        weekly_forest_league=WeeklyForestLeagueResponse(
            week_id=sunday_week_id(ranking_week_start),
            scoring_window=f"{ranking_week_start.isoformat()} to {(ranking_week_start + timedelta(days=6)).isoformat()}",
            scheduled_recompute="คำนวณใหม่ทุกวันอาทิตย์ 23:55 น. เวลาไทย และรีเฟรชรายคืนเพื่ออัปเดตคะแนนย้อนหลัง 7 วัน",
            rate_limit_rule="รับรายงานกิจกรรมภาคสนามได้ 1 ครั้งต่อป่าชุมชน/หมู่บ้าน/วัน",
            ranking=ranking,
            source_mode=league_mode,
        ),
        localizedPredictions=(
            _localized_predictions(hotspots, pm25, weather, risk)
            if prototype_enabled
            else []
        ),
        source_notes=(
            [
                "Prototype intelligence layers are disabled. Only live, derived-from-live, or configured verified data is returned.",
                "Community forest boundaries, fire-management zones, and field-report rankings require verified database/vector imports before use.",
            ]
            if not prototype_enabled
            else [
            "ชั้นข้อมูลรอยไหม้และความถี่การไหม้สามารถเปลี่ยนเป็น GISTDA API Gateway WMS/WMTS ได้เมื่อมี API key",
            "ข้อมูลภัยแล้งและความชื้นดินยังเป็นตัวชี้วัดจำลองแนว TAMFIRE ระหว่างรอ feed สาธารณะที่เสถียร",
            "อันดับรายสัปดาห์ใช้ 4 มิติ: การจัดการ การป้องกัน การใช้ประโยชน์ และผลลัพธ์เชิงนิเวศ",
            ]
        ),
    )


def get_dashboard(settings: Settings) -> DashboardResponse:
    hotspots = get_hotspots(settings)
    pm25 = get_pm25(settings)
    weather = get_weather(settings)
    risk = calculate_risk(pm25, hotspots, weather)
    summary = get_summary(settings, pm25, hotspots, weather, risk)
    intelligence = get_operational_intelligence(hotspots, pm25, weather, risk, settings)
    data_quality = _build_data_quality(hotspots, pm25, weather, settings=settings)
    return DashboardResponse(
        hotspots=hotspots,
        pm25=pm25,
        weather=weather,
        risk=risk,
        summary=summary,
        intelligence=intelligence,
        data_quality=data_quality,
    )
