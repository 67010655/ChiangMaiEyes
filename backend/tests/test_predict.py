from unittest.mock import MagicMock, patch

from app.fire_spread_physics import DISTRICT_PHYSICS
from app.models import DistrictFirePhase, FirePhaseResponse
from app.predict import build_fire_predictions


def _phases(*during_districts: str) -> FirePhaseResponse:
    phases = []
    for district in DISTRICT_PHYSICS:
        phase = "during" if district in during_districts else "normal"
        phases.append(DistrictFirePhase(
            district=district,
            phase=phase,
            color="red" if phase == "during" else "green",
            danger_score=0.9 if phase == "during" else 0.3,
            active_hotspots=1 if phase == "during" else 0,
        ))
    return FirePhaseResponse(generated_at="2026-07-08T08:00:00+07:00", phases=phases)


def _mock_forecast_response(humidity_by_day, rain=None, wind_speed=None, wind_dir=None):
    """humidity_by_day: list of per-day mean humidity (we fan each day's value
    out across 24 hourly samples, matching how the real API returns hourly
    data the code then averages per day)."""
    days = [f"2026-07-{8+i:02d}" for i in range(len(humidity_by_day))]
    hourly_time, hourly_rh = [], []
    for day, hum in zip(days, humidity_by_day):
        for h in range(24):
            hourly_time.append(f"{day}T{h:02d}:00")
            hourly_rh.append(hum)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "daily": {
            "time": days,
            "precipitation_sum": rain or [0.0] * len(days),
            "wind_speed_10m_max": wind_speed or [10.0] * len(days),
            "wind_direction_10m_dominant": wind_dir or [200.0] * len(days),
        },
        "hourly": {"time": hourly_time, "relative_humidity_2m": hourly_rh},
    }
    return mock_resp


@patch("httpx.get")
def test_predictions_cover_every_district(mock_get):
    mock_get.return_value = _mock_forecast_response([40, 35, 30])
    resp = build_fire_predictions(_phases())
    assert len(resp.district_forecasts) == len(DISTRICT_PHYSICS)
    assert all(0.0 <= f.current_danger_score <= 1.0 for f in resp.district_forecasts)
    assert all(0.0 <= d.danger_score <= 1.0 for f in resp.district_forecasts for d in f.daily)
    assert resp.source_mode == "DERIVED"


@patch("httpx.get")
def test_dropping_humidity_trend_is_rising(mock_get):
    # Humidity falling from 80% to 20% over 3 days -> dryness rising -> danger rising.
    mock_get.return_value = _mock_forecast_response([80, 50, 20])
    resp = build_fire_predictions(_phases())
    forecast = next(f for f in resp.district_forecasts if f.district == "แม่แจ่ม")
    assert forecast.trend == "rising"
    assert forecast.daily[-1].danger_score > forecast.daily[0].danger_score


@patch("httpx.get")
def test_stable_humidity_trend_is_stable(mock_get):
    mock_get.return_value = _mock_forecast_response([45, 45, 45])
    resp = build_fire_predictions(_phases())
    forecast = next(f for f in resp.district_forecasts if f.district == "แม่แจ่ม")
    assert forecast.trend == "stable"


@patch("httpx.get")
def test_spread_forecast_only_for_during_districts(mock_get):
    mock_get.return_value = _mock_forecast_response([40, 40, 40], wind_speed=[20.0, 20.0, 20.0])
    resp = build_fire_predictions(_phases("แม่แจ่ม"))
    assert len(resp.spread_forecast_72h) == 1
    sf = resp.spread_forecast_72h[0]
    assert sf.district == "แม่แจ่ม"
    assert sf.km_72h > sf.km_48h > 0


@patch("httpx.get")
def test_no_during_districts_gives_empty_spread_forecast(mock_get):
    mock_get.return_value = _mock_forecast_response([40, 40, 40])
    resp = build_fire_predictions(_phases())
    assert resp.spread_forecast_72h == []


@patch("httpx.get")
def test_forecast_provider_down_degrades_gracefully(mock_get):
    mock_get.side_effect = Exception("network error")
    resp = build_fire_predictions(_phases())
    assert len(resp.district_forecasts) == len(DISTRICT_PHYSICS)
    assert all(f.daily == [] for f in resp.district_forecasts)
    assert any("ไม่สำเร็จ" in n for n in resp.notes)
