from datetime import date, datetime

from app.config import Settings
from app.weekly_forest_league import (
    CommunityForestRecord,
    FieldActivityReport,
    aggregate_weekly_rankings,
    can_accept_daily_report,
    rolling_7_day_window,
    score_daily_report,
    should_recompute_weekly_rankings,
)
from app.models import (
    Hotspot,
    HotspotHistoryDay,
    HotspotResponse,
    HistoryResponse,
    Pm25Response,
    RiskResponse,
    WeatherResponse,
)
from app.services import get_operational_intelligence


def _hotspot(idx: int, landuse_type: str) -> Hotspot:
    return Hotspot(
        id=f"HS-{idx:03d}",
        latitude=18.8,
        longitude=98.9,
        district="แม่ริม",
        landuse_type=landuse_type,
        confidence=80,
        source="test",
        detected_at="2026-06-07T08:00:00+07:00",
    )


def _report(report_id: str, submitted_at: str) -> FieldActivityReport:
    return FieldActivityReport(
        report_id=report_id,
        forest_id="cf-1",
        village_id="village-1",
        reporter_hash="operator",
        submitted_at=datetime.fromisoformat(submitted_at),
        patrol_count=2,
        firebreak_km=1.5,
        fuel_management_rai=20,
        water_points_checked=2,
        committee_meeting=True,
        budget_used_baht=3000,
        community_use_activity=True,
        biodiversity_note="seedlings and water source checked",
        no_burn_agreement=True,
    )


def test_daily_report_rate_limit_blocks_same_forest_village_day():
    existing = [_report("rpt-1", "2026-06-07T08:00:00+07:00")]

    assert (
        can_accept_daily_report(
            "cf-1",
            "village-1",
            datetime.fromisoformat("2026-06-07T16:00:00+07:00"),
            existing,
        )
        is False
    )
    assert (
        can_accept_daily_report(
            "cf-1",
            "village-1",
            datetime.fromisoformat("2026-06-08T08:00:00+07:00"),
            existing,
        )
        is True
    )


def test_scoring_uses_four_rfd_inspired_dimensions():
    score = score_daily_report(_report("rpt-1", "2026-06-07T08:00:00+07:00"))

    assert score.management > 0
    assert score.prevention > 0
    assert score.utilization > 0
    assert score.ecological_outcome > 0


def test_weekly_ranking_aggregates_and_ranks_reports():
    forests = [
        CommunityForestRecord(
            forest_id="cf-1",
            forest_name="Forest A",
            village="Village A",
            tambon="Tambon A",
            amphoe="Amphoe A",
            latitude=18.5,
            longitude=98.3,
        )
    ]
    ranking = aggregate_weekly_rankings(
        forests,
        [_report("rpt-1", "2026-06-07T08:00:00+07:00")],
        date.fromisoformat("2026-06-07"),
    )

    assert len(ranking) == 1
    assert ranking[0].rank == 1
    assert ranking[0].total_score > 0
    assert ranking[0].score_breakdown.prevention > 0
    assert "ลาดตระเวน" in ranking[0].reasons


def test_operational_intelligence_has_rankings_and_explainable_predictions(monkeypatch):
    # Deterministic, offline NASA VIIRS history so the hotspot trend is real-shaped
    # but does not hit the network: 4 days, 2 older + 5 + 6 + 7 recent.
    monkeypatch.setattr(
        "app.services.get_history",
        lambda settings, days=30: HistoryResponse(
            days=days,
            hotspots=[
                HotspotHistoryDay(date="2026-06-04", count=2),
                HotspotHistoryDay(date="2026-06-05", count=4),
                HotspotHistoryDay(date="2026-06-06", count=6),
                HotspotHistoryDay(date="2026-06-07", count=8),
            ],
            pm25=[],
            weather=[],
            sources={},
            latest_update="2026-06-07T08:00:00+07:00",
        ),
    )

    hotspots = HotspotResponse(
        count=2,
        density_per_100_km2=0.1,
        latest_update="2026-06-07T08:00:00+07:00",
        source="test",
        items=[_hotspot(1, "NRF"), _hotspot(2, "NRF"), _hotspot(3, "AGRI")],
    )
    pm25 = Pm25Response(
        current_pm25=42,
        category="moderate",
        color="orange",
        trend="rising",
        latest_update="2026-06-07T08:00:00+07:00",
        source="test",
        stations=[],
    )
    weather = WeatherResponse(
        wind_speed_kmh=15,
        wind_direction_deg=260,
        wind_direction_text="west",
        temperature_c=32,
        humidity_percent=45,
        latest_update="2026-06-07T08:00:00+07:00",
        source="test",
    )
    risk = RiskResponse(score=7, category="High", formula="test", factors={})

    intelligence = get_operational_intelligence(
        hotspots,
        pm25,
        weather,
        risk,
        Settings(allow_prototype_data=True),
    )

    assert intelligence.weekly_forest_league.ranking

    # Real NASA VIIRS trend: recent half (6+8=14) vs previous half (2+4=6) → +133.3%
    trend = intelligence.hotspot_trend
    assert trend.window_days == 4
    assert trend.recent_count == 14
    assert trend.previous_count == 6
    assert trend.change_percent == 133.3
    assert "NASA VIIRS" in trend.source

    # Real GISTDA-tagged landuse: 2× NRF + 1× AGRI, no fabricated fallback.
    breakdown = {item.landuse_type: item.count for item in intelligence.landuse_breakdown}
    assert breakdown == {"NRF": 2, "AGRI": 1}

    assert intelligence.satellite_layers is not None
    assert intelligence.satellite_layers.source_mode == "DERIVED"
    assert "COPERNICUS/S2_SR_HARMONIZED" in intelligence.satellite_layers.dataset_ids
    assert len(intelligence.satellite_layers.dryness_zones) >= 5
    assert intelligence.localizedPredictions
    assert all(p.reason_for_prediction for p in intelligence.localizedPredictions)


def test_weekly_cron_window_and_rolling_window_logic():
    sunday_rollup = datetime.fromisoformat("2026-06-07T23:56:00+07:00")
    monday = datetime.fromisoformat("2026-06-08T23:56:00+07:00")

    assert should_recompute_weekly_rankings(sunday_rollup) is True
    assert should_recompute_weekly_rankings(monday) is False
    assert rolling_7_day_window(sunday_rollup) == (
        date.fromisoformat("2026-06-01"),
        date.fromisoformat("2026-06-07"),
    )
