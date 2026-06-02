from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services import get_data_status, write_json


def _write_snapshot(cache_dir: Path) -> None:
    write_json(
        cache_dir,
        "hotspots.json",
        {
            "count": 18,
            "density_per_100_km2": 0.09,
            "latest_update": "2026-06-03T00:19:27+07:00",
            "source": "Royal Forest Department Firemap + NASA FIRMS",
            "items": [],
            "source_breakdown": {
                "Royal Forest Department Firemap": 14,
                "NASA FIRMS": 8,
            },
        },
    )
    write_json(
        cache_dir,
        "pm25.json",
        {
            "current_pm25": 18.7,
            "category": "good",
            "color": "green",
            "trend": "stable",
            "latest_update": "2026-06-03T00:00:00+07:00",
            "source": "Air4Thai Live API",
            "stations": [],
        },
    )
    write_json(
        cache_dir,
        "weather.json",
        {
            "wind_speed_kmh": 2.9,
            "wind_direction_deg": 349,
            "wind_direction_text": "north",
            "temperature_c": 25.7,
            "humidity_percent": 90,
            "latest_update": "2026-06-03T00:43:25+07:00",
            "source": "Open-Meteo Live API",
        },
    )


def test_data_status_reports_snapshot_freshness(tmp_path: Path):
    settings = Settings(cache_dir=tmp_path)
    _write_snapshot(tmp_path)

    status = get_data_status(settings, now="2026-06-03T01:19:27+07:00")

    assert status.mode == "local-refresh-snapshot"
    assert status.latest_update == "2026-06-03T00:43:25+07:00"
    assert status.snapshot_age_minutes == 36
    assert status.hotspot_count == 18
    assert status.source_breakdown["Royal Forest Department Firemap"] == 14
    assert status.local_refresh_required is True
    assert status.vercel_fetches_rfd_directly is False


def test_data_status_endpoint_returns_snapshot_mode(tmp_path: Path):
    _write_snapshot(tmp_path)

    def override_settings() -> Settings:
        return Settings(cache_dir=tmp_path)

    from app.config import get_settings

    app.dependency_overrides[get_settings] = override_settings
    try:
        response = TestClient(app).get("/api/data-status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local-refresh-snapshot"
    assert body["hotspot_count"] == 18
    assert body["vercel_fetches_rfd_directly"] is False
