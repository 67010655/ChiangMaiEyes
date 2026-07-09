from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.advisor import (
    AdvisorUnavailable,
    chat_with_advisor,
    fallback_chat_reply,
    fallback_daily_briefing,
    generate_daily_briefing,
)
from app.config import Settings, get_settings
from app.models import (
    AdvisorBriefingRequest,
    AdvisorChatRequest,
    AdvisorResponse,
    CommunityForestsResponse,
    DataStatusResponse,
    DashboardResponse,
    FirePhaseResponse,
    FirePredictionResponse,
    HistoryResponse,
    HotspotHistoryResponse,
    HotspotResponse,
    OsmStructuresResponse,
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
    get_fire_phases,
    get_fire_predictions,
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


@app.middleware("http")
async def no_store_api_responses(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    # Every /api/ endpoint here is live/near-live data (hotspots, PM2.5, wind,
    # ...) that must never be served stale — except osm-structures, which is
    # OSM building footprints for a map bbox: effectively static, and by far
    # the most expensive endpoint per call (an Overpass round-trip). Letting
    # the browser cache it is a real speed + resource win with no honesty
    # cost, since it sets its own Cache-Control below instead of this
    # blanket no-store.
    if request.url.path.startswith("/api/") and request.url.path != "/api/osm-structures":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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
def history(
    days: Annotated[int, Query(ge=1, le=180)] = 30,
    settings: Settings = Depends(get_settings),
) -> HistoryResponse:
    return get_history(settings, days=days)


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


@app.get("/api/fire-phases", response_model=FirePhaseResponse)
def fire_phases(settings: Settings = Depends(get_settings)) -> FirePhaseResponse:
    return get_fire_phases(settings)


@app.get("/api/fire-predictions", response_model=FirePredictionResponse)
def fire_predictions(settings: Settings = Depends(get_settings)) -> FirePredictionResponse:
    return get_fire_predictions(settings)


@app.get("/api/community-forests", response_model=CommunityForestsResponse)
def community_forests() -> CommunityForestsResponse:
    from app.providers.community_forest_provider import fetch_community_forests
    import datetime

    forests = fetch_community_forests()
    return CommunityForestsResponse(
        forests=forests,
        total=len(forests),
        source="Royal Forest Department + thaicfnet.org",
        cached_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat(),
    )


@app.get("/api/osm-structures", response_model=OsmStructuresResponse)
def osm_structures(
    response: Response,
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
) -> OsmStructuresResponse:
    from app.providers.osm_structures_provider import fetch_osm_structures

    # Building footprints for a fixed bbox don't meaningfully change hour to
    # hour — cache for an hour (browser + Vercel edge) so panning back over
    # already-seen ground, or a second visit within the hour, costs nothing:
    # no Overpass round-trip, no backend CPU, no wait for the user.
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return fetch_osm_structures(south, west, north, east)


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
        return AdvisorResponse(text=text, source="Groq AI", source_mode="LIVE")
    except AdvisorUnavailable as exc:
        return AdvisorResponse(
            text=fallback_daily_briefing(request.dashboard),
            source=f"rule-based fallback ({exc})",
            source_mode="DERIVED",
        )


@app.post("/api/advisor/chat", response_model=AdvisorResponse)
def advisor_chat(
    request: AdvisorChatRequest,
    settings: Settings = Depends(get_settings),
) -> AdvisorResponse:
    try:
        text = chat_with_advisor(settings, request.dashboard, request.history, request.user_message)
        return AdvisorResponse(text=text, source="Groq AI", source_mode="LIVE")
    except AdvisorUnavailable as exc:
        return AdvisorResponse(
            text=fallback_chat_reply(request.dashboard, request.user_message),
            source=f"rule-based fallback ({exc})",
            source_mode="DERIVED",
        )
