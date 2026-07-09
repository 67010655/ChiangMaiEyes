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


def _weather_response(humidity_by_day, rain=None, wind_speed=None, wind_dir=None, tmax=None, tmin=None):
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
            "temperature_2m_max": tmax or [33.0] * len(days),
            "temperature_2m_min": tmin or [22.0] * len(days),
            "precipitation_sum": rain or [0.0] * len(days),
            "wind_speed_10m_max": wind_speed or [10.0] * len(days),
            "wind_direction_10m_dominant": wind_dir or [200.0] * len(days),
        },
        "hourly": {"time": hourly_time, "relative_humidity_2m": hourly_rh},
    }
    return mock_resp


def _pm25_response(n_locations, pm25_by_day=(30.0, 35.0, 40.0)):
    """Batched Open-Meteo Air Quality response: a JSON array, one object per
    requested location, in the same order — matches what the real API sends
    for a multi-location request."""
    days = [f"2026-07-{8+i:02d}" for i in range(len(pm25_by_day))]
    hourly_time, hourly_pm = [], []
    for day, val in zip(days, pm25_by_day):
        for h in range(24):
            hourly_time.append(f"{day}T{h:02d}:00")
            hourly_pm.append(val)
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"hourly": {"time": hourly_time, "pm2_5": hourly_pm}} for _ in range(n_locations)
    ]
    return mock_resp


def _dispatch(weather_resp, pm25_resp):
    def side_effect(url, **kwargs):
        return pm25_resp if "air-quality" in url else weather_resp
    return side_effect


@patch("httpx.get")
def test_predictions_cover_every_district(mock_get):
    mock_get.side_effect = _dispatch(_weather_response([40, 35, 30]), _pm25_response(26))
    resp = build_fire_predictions(_phases())
    assert len(resp.district_forecasts) == len(DISTRICT_PHYSICS)
    assert all(0.0 <= f.current_danger_score <= 1.0 for f in resp.district_forecasts)
    assert all(0.0 <= d.danger_score <= 1.0 for f in resp.district_forecasts for d in f.daily)
    assert resp.source_mode == "DERIVED"


@patch("httpx.get")
def test_dropping_humidity_trend_is_rising(mock_get):
    # Humidity falling from 80% to 20% over 3 days -> dryness rising -> danger rising.
    mock_get.side_effect = _dispatch(_weather_response([80, 50, 20]), _pm25_response(26))
    resp = build_fire_predictions(_phases())
    forecast = next(f for f in resp.district_forecasts if f.district == "แม่แจ่ม")
    assert forecast.trend == "rising"
    assert forecast.daily[-1].danger_score > forecast.daily[0].danger_score


@patch("httpx.get")
def test_stable_humidity_trend_is_stable(mock_get):
    mock_get.side_effect = _dispatch(_weather_response([45, 45, 45]), _pm25_response(26))
    resp = build_fire_predictions(_phases())
    forecast = next(f for f in resp.district_forecasts if f.district == "แม่แจ่ม")
    assert forecast.trend == "stable"


@patch("httpx.get")
def test_spread_forecast_only_for_during_districts(mock_get):
    mock_get.side_effect = _dispatch(
        _weather_response([40, 40, 40], wind_speed=[20.0, 20.0, 20.0]), _pm25_response(26)
    )
    resp = build_fire_predictions(_phases("แม่แจ่ม"))
    assert len(resp.spread_forecast_72h) == 1
    sf = resp.spread_forecast_72h[0]
    assert sf.district == "แม่แจ่ม"
    assert sf.km_72h > sf.km_48h > 0


@patch("httpx.get")
def test_no_during_districts_gives_empty_spread_forecast(mock_get):
    mock_get.side_effect = _dispatch(_weather_response([40, 40, 40]), _pm25_response(26))
    resp = build_fire_predictions(_phases())
    assert resp.spread_forecast_72h == []


@patch("httpx.get")
def test_forecast_provider_down_degrades_gracefully(mock_get):
    mock_get.side_effect = Exception("network error")
    resp = build_fire_predictions(_phases())
    assert len(resp.district_forecasts) == len(DISTRICT_PHYSICS)
    assert all(f.daily == [] for f in resp.district_forecasts)
    assert resp.pm25_forecast_province is None
    assert resp.pm25_forecast_districts == []
    assert any("ไม่สำเร็จ" in n for n in resp.notes)


@patch("httpx.get")
def test_weather_forecast_exposes_temperature_and_wind(mock_get):
    mock_get.side_effect = _dispatch(
        _weather_response([50, 50, 50], tmax=[35.0, 36.0, 34.0], tmin=[22.0, 23.0, 21.0]),
        _pm25_response(26),
    )
    resp = build_fire_predictions(_phases())
    assert len(resp.weather_forecast) == 3
    assert resp.weather_forecast[0].temp_max_c == 35.0
    assert resp.weather_forecast[0].temp_min_c == 22.0
    assert resp.weather_forecast[0].wind_kmh is not None


@patch("httpx.get")
def test_pm25_forecast_covers_province_and_every_district(mock_get):
    mock_get.side_effect = _dispatch(
        _weather_response([40, 40, 40]), _pm25_response(1 + len(DISTRICT_PHYSICS))
    )
    resp = build_fire_predictions(_phases())
    assert resp.pm25_forecast_province is not None
    assert resp.pm25_forecast_province.name == "จังหวัดเชียงใหม่"
    assert len(resp.pm25_forecast_province.daily) == 3
    assert resp.pm25_forecast_province.daily[0].pm25 == 30.0
    assert len(resp.pm25_forecast_districts) == len(DISTRICT_PHYSICS)
    assert all(len(d.daily) == 3 for d in resp.pm25_forecast_districts)


@patch("httpx.get")
def test_pm25_forecast_down_degrades_gracefully_but_weather_still_works(mock_get):
    def side_effect(url, **kwargs):
        if "air-quality" in url:
            raise Exception("pm2.5 provider down")
        return _weather_response([40, 40, 40])
    mock_get.side_effect = side_effect
    resp = build_fire_predictions(_phases())
    assert resp.pm25_forecast_province is None
    assert resp.pm25_forecast_districts == []
    assert len(resp.district_forecasts) == len(DISTRICT_PHYSICS)  # weather-based forecast unaffected
    assert any("PM2.5" in n and "ไม่สำเร็จ" in n for n in resp.notes)
