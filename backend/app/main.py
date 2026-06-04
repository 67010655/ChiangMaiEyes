from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.advisor import AdvisorUnavailable, chat_with_advisor, generate_daily_briefing
from app.config import Settings, get_settings
from app.models import (
    AdvisorBriefingRequest,
    AdvisorChatRequest,
    AdvisorResponse,
    DataStatusResponse,
    DashboardResponse,
    HistoryResponse,
    HotspotHistoryResponse,
    HotspotResponse,
    Pm25Response,
    RiskResponse,
    SummaryResponse,
    WeatherResponse,
)
from app.services import (
    calculate_risk,
    get_dashboard,
    get_data_status,
    get_history,
    get_hotspot_history,
    get_hotspots,
    get_pm25,
    get_summary,
    get_weather,
)

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


@app.get("/api/hotspots/history", response_model=HotspotHistoryResponse)
def hotspots_history(settings: Settings = Depends(get_settings)) -> HotspotHistoryResponse:
    return get_hotspot_history(settings)


@app.get("/api/history", response_model=HistoryResponse)
def history(settings: Settings = Depends(get_settings)) -> HistoryResponse:
    return get_history(settings, days=14)


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


@app.get("/api/data-status", response_model=DataStatusResponse)
def data_status(settings: Settings = Depends(get_settings)) -> DataStatusResponse:
    return get_data_status(settings)


@app.post("/api/advisor/briefing", response_model=AdvisorResponse)
def advisor_briefing(
    request: AdvisorBriefingRequest,
    settings: Settings = Depends(get_settings),
) -> AdvisorResponse:
    try:
        text = generate_daily_briefing(settings, request.dashboard)
        return AdvisorResponse(text=text, source="Groq AI")
    except AdvisorUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/advisor/chat", response_model=AdvisorResponse)
def advisor_chat(
    request: AdvisorChatRequest,
    settings: Settings = Depends(get_settings),
) -> AdvisorResponse:
    try:
        text = chat_with_advisor(settings, request.dashboard, request.history, request.user_message)
        return AdvisorResponse(text=text, source="Groq AI")
    except AdvisorUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
