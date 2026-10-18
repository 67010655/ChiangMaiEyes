"""Measured artifacts must retain correct cohorts, timing, units and meanings."""
from datetime import datetime,timedelta

import pytest
from fastapi import HTTPException

from app.season_hindcast import decision_validation
from app.validation_metrics import regression_metrics,compare_models,skill_percent


def test_matching_never_fills_missing_or_compares_different_days():
    rows=[dict(observed=10,a=11,b=None),dict(observed=20,a=22,b=18),dict(observed=None,a=0,b=0)]
    matched,metrics=compare_models(rows,['a','b'])
    assert len(matched)==1
    assert metrics['a']['n']==metrics['b']['n']==1
    assert metrics['a']['mae']==metrics['b']['mae']==2
    assert regression_metrics([{'predicted':True,'observed':2}])['n']==0
    assert skill_percent(1,2)==50
    assert skill_percent(2,1)==-100
    assert skill_percent(0,0) is None


def test_daily_station_reference_counts_and_metrics_recompute():
    report=decision_validation(include_rows=True);pm=report['pm25_daily']
    assert pm['valid_station_days']==239
    assert pm['expected_station_days']==240
    assert sum(r['observed'] is None for r in pm['rows'])==1
    actual=regression_metrics([{'predicted':r['cams'],'observed':r['observed']} for r in pm['rows']])
    assert actual['mae']==pytest.approx(pm['all_valid_pairs']['cams']['mae'])
    assert len({m['n'] for m in pm['matched_comparison'].values()})==1
    assert all(c['training_end']<'2026-01-01' for c in pm['calibration'].values())
    assert pm['forecast_issue_verified'] is False
    assert pm['status']=='measured_station_retrospective_agreement'


def test_temporal_forecasts_only_use_training_targets_before_test():
    report=decision_validation(include_rows=True);recent=report['pm25_recent']
    cutoff=datetime.fromisoformat(recent['training_end'])
    for lead,item in recent['by_lead'].items():
        for row in item['rows']:
            origin=datetime.fromisoformat(row['origin']);valid=datetime.fromisoformat(row['time'])
            assert origin>cutoff
            assert valid-origin==timedelta(hours=int(lead))
        assert len({m['n'] for m in item['metrics'].values()})==1
    assert recent['production_model_changed'] is False


def test_actual_wind_reference_and_compact_api_keep_same_scores():
    compact=decision_validation();full=decision_validation(include_rows=True)
    assert compact['wind_station']['status']=='forecast_vs_airport_metar_observations'
    for lead,item in full['wind_station']['by_lead'].items():
        actual=regression_metrics([dict(predicted=r['gfs'],observed=r['observed']) for r in item['rows']])
        assert actual['mae']==pytest.approx(item['metrics']['gfs']['mae'])
        assert 'rows' not in compact['wind_station']['by_lead'][lead]
        assert item['metrics']==compact['wind_station']['by_lead'][lead]['metrics']


def test_initial_support_diagnostic_has_no_future_seed_or_false_accuracy():
    fire=decision_validation()['fire_followup']
    assert fire['accuracy_percent'] is None and fire['iou'] is None
    assert fire['case_count']==8
    for row in fire['cases']:
        issued=datetime.fromisoformat(row['as_of'])
        assert all(datetime.fromisoformat(p['detected_at'])<=issued for p in row['initial'])
        assert all(issued<datetime.fromisoformat(p['detected_at'])<=issued+timedelta(hours=6) for p in row['later'])
        assert len(row['terrain'])==len(row['initial'])
        for name,variant in row['variants'].items():
            for score in variant['scores']:
                assert 0<=score['covered']<=score['points']
                assert score['new_covered']<=score['new_points']
                assert score['search_envelope_area_ha']<=score['unbounded_search_envelope_area_ha']+1e-6
                if name.startswith('all_initial'):
                    assert score['covered']>=score['baseline_covered']
    nominal=next(s for s in fire['summary'] if s['variant']=='all_initial_dem' and s['tolerance_m']==375)
    assert nominal['points']==305
    assert nominal['covered']==174
    assert nominal['baseline_covered']==131


def test_missing_validation_is_unavailable_not_perfect_or_zero(tmp_path,monkeypatch):
    import app.season_hindcast as module
    monkeypatch.setattr(module,'VALIDATION_ARTIFACT',tmp_path/'missing.json')
    with pytest.raises(HTTPException) as error:module.decision_validation()
    assert error.value.status_code==503
