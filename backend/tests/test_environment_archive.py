from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

import app.environment_archive as archive
from app.config import Settings
from app.models import Hotspot, HotspotResponse, WeatherResponse
from app.providers.hotspot_provider import reconcile_hotspots
from app.providers.pm25_provider import _build_pm25_response_from_aqicn

ICT = timezone(timedelta(hours=7))


def test_window_requires_explicit_timezone_and_rejects_future():
    with pytest.raises(HTTPException) as missing_tz:
        archive.read_archive(7, "all", None, "2026-10-10T12:00:00", 0, 500, Settings())
    assert missing_tz.value.status_code == 422
    with pytest.raises(HTTPException) as future:
        archive.window(7, "2099-01-01T00:00:00+07:00")
    assert future.value.status_code == 422


def test_window_uses_exact_rolling_interval():
    end = "2026-10-10T12:00:00+07:00"
    start, until = archive.window(7, end)
    assert until == datetime(2026, 10, 10, 12, 0, tzinfo=ICT)
    assert until - start == timedelta(days=7)


def test_archive_reader_surfaces_gaps_without_filling_zero(monkeypatch):
    class Store:
        def __init__(self, settings):
            pass

        def call(self, method, path, json):
            assert path.endswith("cme_archive_read")
            assert json["p_kind"] == "hotspot"
            return {
                "total": 1,
                "rows": [{"kind": "hotspot", "payload": {"id": "one"}}],
                "daily": [{"day": "2026-10-09", "kind": "hotspot", "source": "NASA FIRMS", "samples": 1}],
                "collection": [], "first_collected": None, "last_collected": None, "recent_runs": [],
            }

    monkeypatch.setattr(archive, "CommunityStore", Store)
    result = archive.read_archive(
        days=7, kind="hotspot", forest_id=None, end="2026-10-10T12:00:00+07:00",
        offset=0, limit=500, settings=Settings(),
    )
    assert result["total"] == 1
    assert result["days_without_observations"]
    assert all("count" not in row for row in result["daily"])
    assert result["scope"] == "upstream_observations_received"


def test_observation_rejects_future_or_timezone_free_source_times():
    retrieved = "2026-10-10T10:00:00+00:00"
    with pytest.raises(ValueError):
        archive.observation("hotspot", "NASA FIRMS", "2026-10-10T10:00:00", {}, retrieved, "x")
    with pytest.raises(ValueError):
        archive.observation("hotspot", "NASA FIRMS", "2026-10-10T11:00:00+00:00", {}, retrieved, "x")


def test_collection_retains_original_evidence_when_map_reconciles_two_sources():
    time = '2026-10-10T10:00:00+00:00'
    nasa = Hotspot(id='native-nasa', latitude=19.4, longitude=99, district='Fixture',
                   confidence=75, source='NASA FIRMS', detected_at=time, satellite='N21',
                   confidence_level='nominal', confidence_raw='n', confidence_scheme='VIIRS')
    other = nasa.model_copy(update={'id': 'native-other', 'source': 'Other provider', 'satellite': 'NOAA-21'})
    hs = HotspotResponse(count=1, density_per_100_km2=0, latest_update=time,
                         source='NASA FIRMS + Other provider', items=reconcile_hotspots([[nasa], [other]]))
    weather = WeatherResponse(wind_speed_kmh=2, wind_direction_deg=0, wind_direction_text='เหนือ',
                              temperature_c=28, humidity_percent=70, latest_update=time, source='Fixture weather')
    dashboard = SimpleNamespace(hotspots=hs, pm25=_build_pm25_response_from_aqicn([]),
                                weather=weather, data_quality={})
    run, rows = archive.dashboard_batch(dashboard, now=datetime(2026, 10, 10, 11, tzinfo=timezone.utc))
    detections = [r for r in rows if r['kind'] == 'hotspot']
    assert len(detections) == 2
    assert len({r['observation_key'] for r in detections}) == 1
    assert {r['source'] for r in detections} == {'NASA FIRMS', 'Other provider'}
    assert {r['payload']['id'] for r in detections} == {'native-nasa', 'native-other'}
    assert run['sources']['pm25']['available'] is False
    assert not any(r['kind'] == 'pm25' for r in rows)
