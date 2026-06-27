from app.config import Settings
from app.models import HotspotResponse, Pm25Response, RiskResponse, WeatherResponse
from app.services import _cache, get_summary


def test_summary_is_deterministic_even_when_gemini_key_is_configured():
    _cache.clear()
    pm25 = Pm25Response(
        current_pm25=31,
        category="ปานกลาง",
        color="orange",
        trend="stable",
        latest_update="2026-06-23T10:00:00+07:00",
        source="Air4Thai",
        stations=[],
    )
    hotspots = HotspotResponse(
        count=2,
        density_per_100_km2=0.01,
        latest_update="2026-06-23T10:10:00+07:00",
        source="GISTDA Disaster STAC VIIRS 3-day + NASA FIRMS",
        items=[],
        source_breakdown={
            "GISTDA Disaster STAC VIIRS 3-day": 1,
            "NASA FIRMS": 1,
        },
    )
    weather = WeatherResponse(
        wind_speed_kmh=8,
        wind_direction_deg=210,
        wind_direction_text="ตะวันตกเฉียงใต้",
        temperature_c=33,
        humidity_percent=52,
        latest_update="2026-06-23T10:15:00+07:00",
        source="Thai Meteorological Department AWS",
    )
    risk = RiskResponse(
        score=5,
        category="Medium",
        formula="test",
        factors={},
    )

    summary = get_summary(
        Settings(gemini_api_key="configured-but-not-used"),
        pm25,
        hotspots,
        weather,
        risk,
    )

    assert summary.source == "deterministic hourly summary"
    assert "10:15" in summary.text
    assert "31" in summary.text
    assert "GISTDA Disaster STAC VIIRS 3-day 1 จุด" in summary.text
    assert "ข้อเสนอแนะ" in summary.text
