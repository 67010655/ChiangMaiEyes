from app.models import HotspotResponse, Pm25Response, WeatherResponse
from app.services import calculate_risk, wind_pushes_smoke_to_city


def test_wind_from_west_or_northwest_pushes_smoke_toward_city():
    assert wind_pushes_smoke_to_city(260) is True
    assert wind_pushes_smoke_to_city(90) is False


def test_calculate_risk_caps_score_at_ten():
    pm25 = Pm25Response(
        current_pm25=90,
        category="อันตราย",
        color="purple",
        trend="rising",
        latest_update="2026-05-30T08:00:00+07:00",
        source="test",
        stations=[],
    )
    hotspots = HotspotResponse(
        count=500,
        density_per_100_km2=12.0,
        latest_update="2026-05-30T08:00:00+07:00",
        source="test",
        items=[],
    )
    weather = WeatherResponse(
        wind_speed_kmh=16,
        wind_direction_deg=260,
        wind_direction_text="ตะวันตก",
        temperature_c=34,
        humidity_percent=45,
        latest_update="2026-05-30T08:00:00+07:00",
        source="test",
    )

    risk = calculate_risk(pm25, hotspots, weather)

    assert risk.score == 10
    assert risk.category == "High"
