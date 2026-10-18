"""Public replay preserves the actual target, temporal split and denominators."""
import pytest
from fastapi import HTTPException
from app import season_hindcast as module

def test_published_priority_replay_is_not_live_spread_accuracy():
    report=module.priority_validation()
    assert report['mode']=='historical_replay_only'
    assert report['protocol']['train_year']<report['protocol']['selection_year']<report['protocol']['test_year']
    assert report['protocol']['source_latency_hours']==3
    assert report['baseline']['tested_baseline_configs']==18
    assert report['community_subgroup']['community_forests']==677
    for row in report['comparison']:
        assert row['model_coverage_pct']==pytest.approx(100*row['model_hits']/row['target_cell_periods'])
        assert row['baseline_coverage_pct']==pytest.approx(100*row['baseline_hits']/row['target_cell_periods'])
        assert 0<=row['baseline_hits']<=row['target_cell_periods']
    assert len(report['examples'])==3
    assert all(e['selected_area_km2']==250 for e in report['examples'])
    assert all('geometry' in forest for e in report['examples'] for forest in e['community_watchlist'])

def test_missing_or_incompatible_replay_is_unavailable(tmp_path,monkeypatch):
    artifact=tmp_path/'priority.json';monkeypatch.setattr(module,'PRIORITY_ARTIFACT',artifact)
    for contents in (None,'{}'):
        if contents:artifact.write_text(contents,encoding='utf8')
        with pytest.raises(HTTPException) as error:module.priority_validation()
        assert error.value.status_code==503
