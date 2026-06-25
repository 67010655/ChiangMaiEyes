from app.config import get_settings
from app.services import get_dashboard


def test_dashboard_exposes_weekly_forest_league_contract():
    dashboard = get_dashboard(get_settings())

    assert dashboard.intelligence is not None
    league = dashboard.intelligence.weekly_forest_league
    assert league.week_id
    assert league.scoring_window
    assert league.ranking

    first = league.ranking[0]
    assert first.forest_id
    assert first.forest_name
    assert first.total_score >= 0
    assert first.score_breakdown.management >= 0
    assert first.score_breakdown.prevention >= 0


def test_weekly_forest_entries_explain_boundary_authority_and_verification():
    dashboard = get_dashboard(get_settings())
    entry = dashboard.intelligence.weekly_forest_league.ranking[0]

    assert entry.authority_owner
    assert entry.boundary_source
    assert entry.boundary_confidence in {"official", "estimated", "prototype"}
    assert entry.verification_status in {"verified", "review_needed", "prototype"}
    assert entry.hotspot_activity_delta_percent is not None


def test_weekly_forest_entries_include_satellite_fire_context():
    dashboard = get_dashboard(get_settings())
    entry = dashboard.intelligence.weekly_forest_league.ranking[0]

    assert entry.satellite_context is not None
    assert entry.satellite_context.source_mode in {"LIVE", "DERIVED"}
    assert entry.satellite_context.nearest_zone_id
    assert entry.satellite_context.dryness_class in {"moderate", "high", "critical"}
    assert entry.satellite_context.hotspot_pressure_7d >= 0
    assert entry.satellite_context.fire_pressure_index >= 0
