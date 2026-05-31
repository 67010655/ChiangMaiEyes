from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import DashboardResponse, HotspotResponse, Pm25Response, RiskResponse, SummaryResponse, WeatherResponse
from app.services import calculate_risk, get_dashboard, get_hotspots, get_pm25, get_summary, get_weather

app = FastAPI(title="ChiangMaiEyes API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hotspots", response_model=HotspotResponse)
def hotspots(settings: Settings = Depends(get_settings)) -> HotspotResponse:
    return get_hotspots(settings)


@app.get("/api/pm25", response_model=Pm25Response)
def pm25(settings: Settings = Depends(get_settings)) -> Pm25Response:
    return get_pm25(settings)


@app.get("/api/weather", response_model=WeatherResponse)
def weather(settings: Settings = Depends(get_settings)) -> WeatherResponse:
    return get_weather(settings)


@app.get("/api/risk", response_model=RiskResponse)
def risk(settings: Settings = Depends(get_settings)) -> RiskResponse:
    return calculate_risk(get_pm25(settings), get_hotspots(settings), get_weather(settings))


@app.get("/api/summary", response_model=SummaryResponse)
def summary(settings: Settings = Depends(get_settings)) -> SummaryResponse:
    dashboard = get_dashboard(settings)
    return dashboard.summary


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(settings: Settings = Depends(get_settings)) -> DashboardResponse:
    return get_dashboard(settings)
