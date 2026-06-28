from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import HistoryResponse
from app.services import _cache, get_history


def setup_function():
    _cache.clear()


def test_get_history_cache_is_keyed_by_days(monkeypatch):
    calls: list[int] = []

    def fake_hotspot_history(_key: str, days: int):
        calls.append(days)
        return [(f"2026-06-{day:02d}", day) for day in range(1, days + 1)]

    monkeypatch.setattr("app.services.fetch_hotspot_history", fake_hotspot_history)
    monkeypatch.setattr("app.services.fetch_pm25_history", lambda days: [(f"2026-06-{day:02d}", 10.0) for day in range(1, days + 1)])
    monkeypatch.setattr(
        "app.services.fetch_weather_history",
        lambda days: [(f"2026-06-{day:02d}", 34.0, 24.0, 7.0, 60.0) for day in range(1, days + 1)],
    )

    settings = Settings(cache_dir=".", nasa_firms_map_key="nasa")

    seven = get_history(settings, days=7)
    thirty = get_history(settings, days=30)

    assert seven.days == 7
    assert len(seven.hotspots) == 7
    assert thirty.days == 30
    assert len(thirty.hotspots) == 30
    assert calls == [7, 30]


def test_history_route_accepts_days_query_and_validates_bounds(monkeypatch):
    def fake_get_history(_settings: Settings, days: int = 30):
        return HistoryResponse(days=days, hotspots=[], pm25=[], weather=[], sources={}, latest_update="2026-06-28T14:00:00+07:00")

    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=".")
    monkeypatch.setattr("app.main.get_history", fake_get_history)
    client = TestClient(app)
    try:
        ok = client.get("/api/history?days=7")
        low = client.get("/api/history?days=0")
        high = client.get("/api/history?days=181")
    finally:
        app.dependency_overrides.clear()

    assert ok.status_code == 200
    assert ok.json()["days"] == 7
    assert low.status_code == 422
    assert high.status_code == 422


def test_history_uses_real_archive_for_district_and_hourly_when_available(monkeypatch):
    monkeypatch.setattr("app.services.fetch_pm25_history", lambda days: [])
    monkeypatch.setattr("app.services.fetch_weather_history", lambda days: [])
    monkeypatch.setattr(
        "app.services._read_optional_snapshot_json",
        lambda _settings, filename: {
            "metadata": {
                "season_label": "2569",
                "build_date": "2026-06-28T14:00:00+07:00",
                "source": "test archive",
            },
            "seasons": {
                "2569": [
                    {
                        "date": "2026-06-27",
                        "count": 2,
                        "districts": {"แม่แจ่ม": 2},
                        "hour_histogram": [0, 1, 1, *([0] * 21)],
                    },
                    {
                        "date": "2026-06-28",
                        "count": 1,
                        "districts": {"แม่วาง": 1},
                        "hour_histogram": [1, *([0] * 23)],
                    },
                ]
            },
        }
        if filename == "season_history.json"
        else None,
    )

    history = get_history(Settings(cache_dir="."), days=2)

    assert [day.count for day in history.hotspots] == [2, 1]
    assert history.by_district[0].districts == {"แม่แจ่ม": 2}
    assert history.by_district[1].districts == {"แม่วาง": 1}
    assert sum(history.hour_histogram) == 3
    assert history.data_quality["history_archive"].source_mode == "SNAPSHOT"


def test_history_does_not_mix_partial_archive_with_longer_live_window(monkeypatch):
    monkeypatch.setattr("app.services.fetch_hotspot_history", lambda _key, days: [(f"2026-06-{day:02d}", day) for day in range(1, days + 1)])
    monkeypatch.setattr("app.services.fetch_pm25_history", lambda days: [])
    monkeypatch.setattr("app.services.fetch_weather_history", lambda days: [])
    monkeypatch.setattr(
        "app.services._read_optional_snapshot_json",
        lambda _settings, filename: {
            "metadata": {"season_label": "2569", "build_date": "2026-06-28T14:00:00+07:00"},
            "seasons": {
                "2569": [
                    {"date": "2026-06-28", "count": 0, "districts": {}, "hour_histogram": [0] * 24}
                ]
            },
        }
        if filename == "season_history.json"
        else None,
    )

    history = get_history(Settings(cache_dir=".", nasa_firms_map_key="nasa"), days=30)

    assert len(history.hotspots) == 30
    assert history.by_district == []
    assert history.hour_histogram == []


def test_history_archive_is_unavailable_without_real_archive(monkeypatch):
    monkeypatch.setattr("app.services.fetch_pm25_history", lambda days: [])
    monkeypatch.setattr("app.services.fetch_weather_history", lambda days: [])
    monkeypatch.setattr("app.services._read_optional_snapshot_json", lambda _settings, _filename: None)

    history = get_history(Settings(cache_dir="."))

    assert history.by_district == []
    assert history.hour_histogram == []
    assert history.data_quality["history_archive"].source_mode == "UNAVAILABLE"
