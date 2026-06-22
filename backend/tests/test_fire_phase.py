from app.fire_phase import classify_fire_phases
from app.models import Hotspot, HotspotResponse, WeatherResponse


def _weather(humidity: float, rain_today: float = 0.0) -> WeatherResponse:
    return WeatherResponse(
        wind_speed_kmh=8,
        wind_direction_deg=200,
        wind_direction_text="south",
        temperature_c=34,
        humidity_percent=humidity,
        latest_update="2026-06-23T08:00:00+07:00",
        source="test",
        rain_today_mm=rain_today,
    )


def _hotspots(*districts: str) -> HotspotResponse:
    items = [
        Hotspot(
            id=f"HS-{i}",
            latitude=18.5,
            longitude=98.4,
            district=d,
            confidence=80,
            source="test",
            detected_at="2026-06-23T07:00:00+07:00",
        )
        for i, d in enumerate(districts)
    ]
    return HotspotResponse(
        count=len(items),
        density_per_100_km2=0.1,
        latest_update="2026-06-23T07:00:00+07:00",
        source="test",
        items=items,
    )


def _phase_of(resp, district):
    return next(p for p in resp.phases if p.district == district)


def test_district_with_active_hotspot_is_during_red():
    resp = classify_fire_phases(_hotspots("แม่แจ่ม"), _weather(humidity=40))
    p = _phase_of(resp, "แม่แจ่ม")
    assert p.phase == "during"
    assert p.color == "red"
    assert p.active_hotspots == 1
    assert p.danger_score >= 0.85


def test_dry_air_high_fuel_no_fire_is_before_yellow():
    # No hotspots, very dry air, high-flammability district -> before/yellow.
    resp = classify_fire_phases(_hotspots(), _weather(humidity=20))
    p = _phase_of(resp, "แม่แจ่ม")
    assert p.phase == "before"
    assert p.color == "yellow"
    assert p.active_hotspots == 0


def test_moist_air_keeps_even_high_fuel_district_green():
    # Rainy season: max-flammability แม่แจ่ม must NOT be yellow when air is moist
    # (weather gate dominates static fuel) — avoids over-alarming.
    resp = classify_fire_phases(_hotspots(), _weather(humidity=80))
    p = _phase_of(resp, "แม่แจ่ม")
    assert p.phase == "normal"
    assert p.color == "green"


def test_humid_air_low_fuel_is_normal_green():
    # Humid air + the lowest-flammability district -> normal/green.
    resp = classify_fire_phases(_hotspots(), _weather(humidity=90, rain_today=5))
    p = _phase_of(resp, "เมืองเชียงใหม่")
    assert p.phase == "normal"
    assert p.color == "green"


def test_recent_rain_lowers_danger_below_yellow():
    dry = classify_fire_phases(_hotspots(), _weather(humidity=30, rain_today=0))
    wet = classify_fire_phases(_hotspots(), _weather(humidity=30, rain_today=10))
    assert _phase_of(wet, "ฝาง").danger_score < _phase_of(dry, "ฝาง").danger_score


def test_scores_in_range_and_sorted_desc():
    resp = classify_fire_phases(_hotspots("เชียงดาว"), _weather(humidity=35))
    scores = [p.danger_score for p in resp.phases]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert resp.source_mode == "DERIVED"
    assert any("dNBR" in n for n in resp.notes)  # after/grey honestly deferred
