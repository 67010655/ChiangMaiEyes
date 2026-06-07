from datetime import date, datetime

from app.weekly_forest_league import (
    CommunityForestRecord,
    FieldActivityReport,
    aggregate_weekly_rankings,
    can_accept_daily_report,
    rolling_7_day_window,
    score_daily_report,
    should_recompute_weekly_rankings,
)
from app.models import HotspotResponse, Pm25Response, RiskResponse, WeatherResponse
from app.services import get_operational_intelligence


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


def test_operational_intelligence_has_rankings_and_explainable_predictions():
    hotspots = HotspotResponse(
        count=2,
        density_per_100_km2=0.1,
        latest_update="2026-06-07T08:00:00+07:00",
        source="test",
        items=[],
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

    intelligence = get_operational_intelligence(hotspots, pm25, weather, risk)

    assert intelligence.weekly_forest_league.ranking
    assert intelligence.landuse_breakdown
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
