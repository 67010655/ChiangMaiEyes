from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def _dashboard_payload() -> dict:
    return {
        "hotspots": {
            "count": 0,
            "density_per_100_km2": 0,
            "latest_update": "2026-06-04T16:00:00+07:00",
            "source": "test",
            "items": [],
            "source_breakdown": {},
        },
        "pm25": {
            "current_pm25": 12.3,
            "category": "good",
            "color": "green",
            "trend": "stable",
            "latest_update": "2026-06-04T16:00:00+07:00",
            "source": "test",
            "stations": [],
        },
        "weather": {
            "wind_speed_kmh": 4.2,
            "wind_direction_deg": 90,
            "wind_direction_text": "east",
            "temperature_c": 32,
            "humidity_percent": 55,
            "latest_update": "2026-06-04T16:00:00+07:00",
            "source": "test",
        },
        "risk": {
            "score": 2,
            "category": "Low",
            "formula": "test",
            "factors": {},
        },
        "summary": {
            "language": "th",
            "text": "test",
            "source": "test",
        },
    }


def test_advisor_briefing_returns_503_when_backend_key_missing():
    def override_settings() -> Settings:
        return Settings(groq_api_keys=None)

    app.dependency_overrides[get_settings] = override_settings
    try:
        response = TestClient(app).post(
            "/api/advisor/briefing",
            json={"dashboard": _dashboard_payload()},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "GROQ_API_KEYS" in response.json()["detail"]
