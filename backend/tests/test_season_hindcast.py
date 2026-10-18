"""Verify that a real retrospective artifact cannot masquerade as validation."""
import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.season_hindcast import season_2026
from app.spread_scenario import Evaluation, Scenario, run_scenario, evaluate_result


def test_published_hindcast_has_complete_dates_but_no_invented_accuracy():
    report=season_2026()
    assert len(report['daily'])==120
    assert len({r['date'] for r in report['daily']})==120
    assert sum(r['observed_detections'] for r in report['daily'])==report['detections']
    assert sum(r['firms_complete'] for r in report['daily'])==report['complete_days']
    assert report['fire']['accuracy_percent'] is None
    assert report['fire']['iou'] is None
    assert report['pm25']['measured_pairs']==0
    assert report['pm25']['mae'] is None
    assert report['wind']['speed']['n']==report['wind']['persistence_24h']['n']
    assert report['fire']['nominal_point_coverage_is_accuracy'] is False
    assert report['pm25_catalog']['numeric_nonnegative_rows']<=report['pm25_catalog']['rows_2026']


def test_real_peak_case_recomputes_and_only_uses_later_points():
    report=season_2026()
    row=next(c for c in report['cases'] if c.get('scenarios'))
    variant=next(s for s in row['scenarios'] if s['factor']==.2 and s['moisture_pct']==8)
    req=Scenario.model_validate(variant['request'])
    ev=Evaluation(scenario=req,observations=row['observations'])
    assert all(req.start_at<o.observed_at for o in ev.observations)
    result=run_scenario(req)
    actual=evaluate_result(ev,result,basis='test_real_artifact_recomputation')
    assert actual['nominal_point_coverage_percent']==pytest.approx(variant['coverage_percent'])
    assert actual['field_arrival_observation_count']==0
    assert actual['mean_absolute_arrival_error_minutes'] is None
    assert req.terrain.evidence.basis=='assumed'
    assert req.wind.evidence.basis=='assumed'
    assert req.fuel.evidence.basis=='reference'


def test_missing_artifact_returns_unavailable_instead_of_zero(tmp_path,monkeypatch):
    import app.season_hindcast as module
    monkeypatch.setattr(module,'ARTIFACT',tmp_path/'missing.json')
    with pytest.raises(HTTPException) as error:
        module.season_2026()
    assert error.value.status_code==503
