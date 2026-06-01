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


class HotspotResponse(BaseModel):
    count: int
    density_per_100_km2: float
    latest_update: str
    source: str
    items: list[Hotspot]


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
    color: str
    trend: str
    latest_update: str
    source: str
    stations: list[Pm25Station]


class WeatherResponse(BaseModel):
    wind_speed_kmh: float
    wind_direction_deg: int
    wind_direction_text: str
    temperature_c: float
    humidity_percent: float
    latest_update: str
    source: str


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
