from app.fire_phase import classify_fire_phases
from app.models import (
    CommunityForest,
    Hotspot,
    HotspotResponse,
    SatelliteDrynessZone,
    SatelliteLayerResponse,
    WeatherResponse,
)


def _burn_layer(zone_id: str, dnbr: float, severity: str) -> SatelliteLayerResponse:
    return SatelliteLayerResponse(
        source_mode="LIVE",
        source="test",
        generated_at="2026-06-23T08:00:00+07:00",
        dataset_ids=[],
        cadence="test",
        dryness_zones=[
            SatelliteDrynessZone(
                id=zone_id,
                name=zone_id,
                latitude=18.5,
                longitude=98.4,
                radius_m=8000,
                ndvi=0.3,
                ndmi=-0.05,
                nbr=0.2,
                dryness_class="high",
                dnbr=dnbr,
                burn_severity=severity,
                updated_at="2026-06-23T08:00:00+07:00",
                source="test",
            )
        ],
        notes=[],
    )


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


def _forest(amphoe: str, lat: float, lon: float, name: str = "ป่าทดสอบ") -> CommunityForest:
    return CommunityForest(
        forest_id=f"test-{name}-{lat}-{lon}",
        name=name,
        village="",
        tambon="",
        amphoe=amphoe,
        latitude=lat,
        longitude=lon,
    )


def test_fire_phases_cover_all_25_chiang_mai_districts():
    expected = {
        "เมืองเชียงใหม่",
        "จอมทอง",
        "แม่แจ่ม",
        "เชียงดาว",
        "ดอยสะเก็ด",
        "แม่แตง",
        "แม่ริม",
        "สะเมิง",
        "ฝาง",
        "แม่อาย",
        "พร้าว",
        "สันป่าตอง",
        "สันกำแพง",
        "สันทราย",
        "หางดง",
        "ฮอด",
        "ดอยเต่า",
        "อมก๋อย",
        "สารภี",
        "เวียงแหง",
        "ไชยปราการ",
        "แม่วาง",
        "แม่ออน",
        "ดอยหล่อ",
        "กัลยาณิวัฒนา",
    }
    resp = classify_fire_phases(_hotspots("แม่วาง"), _weather(humidity=80))
    assert {p.district for p in resp.phases} == expected
    assert _phase_of(resp, "แม่วาง").active_hotspots == 1


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


def test_dnbr_burn_scar_marks_district_after_grey():
    # mae-chaem-reserve zone → แม่แจ่ม. Moderate burn severity, no active fire.
    layer = _burn_layer("mae-chaem-reserve", dnbr=0.4, severity="moderate")
    resp = classify_fire_phases(_hotspots(), _weather(humidity=30), layer)
    p = _phase_of(resp, "แม่แจ่ม")
    assert p.phase == "after"
    assert p.color == "grey"
    assert any("dNBR" in r for r in p.reasons)


def test_low_dnbr_does_not_mark_after():
    layer = _burn_layer("mae-chaem-reserve", dnbr=0.05, severity="unburned")
    resp = classify_fire_phases(_hotspots(), _weather(humidity=30), layer)
    assert _phase_of(resp, "แม่แจ่ม").phase != "after"


def test_active_fire_beats_burn_scar():
    # During (active fire) takes precedence over after (burn scar).
    layer = _burn_layer("mae-chaem-reserve", dnbr=0.5, severity="high")
    resp = classify_fire_phases(_hotspots("แม่แจ่ม"), _weather(humidity=30), layer)
    assert _phase_of(resp, "แม่แจ่ม").phase == "during"


def test_scores_in_range_and_sorted_desc():
    resp = classify_fire_phases(_hotspots("เชียงดาว"), _weather(humidity=35))
    scores = [p.danger_score for p in resp.phases]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert resp.source_mode == "DERIVED"
    assert any("dNBR" in n for n in resp.notes)  # after/grey honestly deferred


def test_forest_risk_present_for_every_community_forest():
    forests = [_forest("แม่แจ่ม", 18.5, 98.4), _forest("เชียงดาว", 19.38, 98.95)]
    resp = classify_fire_phases(_hotspots(), _weather(humidity=30), community_forests=forests)
    assert len(resp.forest_risk) == 2
    assert all(0.0 <= f.danger_score <= 1.0 for f in resp.forest_risk)


def test_forest_near_active_hotspot_scores_higher_than_far_forest_same_district():
    # Both forests are in แม่แจ่ม; one sits right on the active hotspot's
    # coordinates, the other is ~35km away — the near one must score higher.
    near = _forest("แม่แจ่ม", 18.5, 98.4, name="ใกล้ไฟ")
    far = _forest("แม่แจ่ม", 18.75, 98.6, name="ไกลไฟ")
    resp = classify_fire_phases(_hotspots("แม่แจ่ม"), _weather(humidity=40), community_forests=[near, far])
    near_risk = next(f for f in resp.forest_risk if f.name == "ใกล้ไฟ")
    far_risk = next(f for f in resp.forest_risk if f.name == "ไกลไฟ")
    assert near_risk.danger_score >= far_risk.danger_score
    assert near_risk.nearest_hotspot_km is not None
    assert far_risk.nearest_hotspot_km is not None
    assert near_risk.nearest_hotspot_km < far_risk.nearest_hotspot_km


def test_forest_risk_no_hotspots_matches_district_base_score():
    forests = [_forest("แม่แจ่ม", 18.6, 98.5)]
    resp = classify_fire_phases(_hotspots(), _weather(humidity=20), community_forests=forests)
    assert resp.forest_risk[0].nearest_hotspot_km is None
    assert resp.forest_risk[0].danger_score == _phase_of(resp, "แม่แจ่ม").danger_score
