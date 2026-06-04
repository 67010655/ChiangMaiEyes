from typing import Literal

from pydantic import BaseModel, Field


class Hotspot(BaseModel):
    id: str
    latitude: float
    longitude: float
    district: str
    subdistrict: str | None = None
    landuse_type: str | None = None
    landuse_name: str | None = None
    satellite: str | None = None
    confidence: int = Field(ge=0, le=100)
    source: str
    detected_at: str
    # Provenance after cross-source reconciliation: every source that reported
    # this (deduplicated) hotspot, and how many of them did.
    sources: list[str] = Field(default_factory=list)
    source_count: int = 1


class HotspotResponse(BaseModel):
    count: int
    density_per_100_km2: float
    latest_update: str
    source: str
    items: list[Hotspot]
    # Raw hotspot count reported by each source *before* dedup, so the UI can
    # show "RFD 12 · NASA 8 → 15 unique".
    source_breakdown: dict[str, int] = Field(default_factory=dict)


class Pm25Station(BaseModel):
    id: str
    name: str
    district: str
    latitude: float
    longitude: float
    pm25: float
    trend: str
    updated_at: str


class Pm25Response(BaseModel):
    current_pm25: float
    category: str
    color: Literal["green", "yellow", "orange", "red", "purple"]
    trend: str
    latest_update: str
    source: str
    stations: list[Pm25Station]


class WeatherResponse(BaseModel):
    wind_speed_kmh: float
    wind_direction_deg: float
    wind_direction_text: str
    temperature_c: float
    humidity_percent: float
    latest_update: str
    source: str
    station_name: str | None = None
    station_latitude: float | None = None
    station_longitude: float | None = None
    pressure_hpa: float | None = None
    rain_15m_mm: float | None = None
    rain_1h_mm: float | None = None
    rain_today_mm: float | None = None
    temperature_min_today_c: float | None = None
    temperature_max_today_c: float | None = None


class RiskResponse(BaseModel):
    score: int
    category: str
    formula: str
    factors: dict[str, float | int | str]


class SummaryResponse(BaseModel):
    language: str
    text: str
    source: str


class DashboardResponse(BaseModel):
    hotspots: HotspotResponse
    pm25: Pm25Response
    weather: WeatherResponse
    risk: RiskResponse
    summary: SummaryResponse


class DataStatusResponse(BaseModel):
    mode: Literal["local-refresh-snapshot", "live-backend"]
    latest_update: str
    snapshot_age_minutes: int
    hotspot_count: int
    source: str
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    local_refresh_required: bool
    vercel_fetches_rfd_directly: bool
    notes: list[str] = Field(default_factory=list)
