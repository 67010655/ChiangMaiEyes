"""Source regression, physical limits, geometry, and evidence semantics.

FM1 values trace to pinned official-core runtime via the external regression
workflow documented in docs/research/2026-10-15-spread-model-and-validation.md.
These verify numerical implementation, not Chiang Mai field accuracy.
"""
import copy
import math
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.spread_scenario import (
    Evidence, Fuel, Wind, Scenario, Evaluation, run_scenario, evaluate,
    rate_of_spread, terrain_point, point_dataset, destination, distance_bearing,
)

EVIDENCE = {'basis':'reference','source':'USFS Anderson FM1; synthetic regression only',
            'observed_at':'2020-01-01T00:00:00Z'}


def payload():
    return {'latitude':18.79,'longitude':98.99,'start_at':'2020-01-01T00:00:00Z','duration_minutes':180,
            'fuel':{'load_kg_m2':.16600253963702372,'depth_m':.3048,'savr_per_m':11482.939632545931,
                    'moisture_pct':5,'extinction_moisture_pct':12,'evidence':EVIDENCE},
            'wind':{'midflame_mps':0,'from_deg':0,'evidence':EVIDENCE},
            'terrain':{'mode':'manual','slope_deg':0,'upslope_to_deg':0,'evidence':EVIDENCE}}


@pytest.mark.parametrize('wind,slope,chains_per_hour',[
    (0,0,4.4262698923571939),
    (0,math.degrees(math.atan(.3)),20.817222076028628),
    (.508,0,8.834274755440232),
    (.508,math.degrees(math.atan(.3)),21.399596624626479),
])
def test_fm1_official_runtime_regression(wind,slope,chains_per_hour):
    p=payload();p['wind'].update(midflame_mps=wind,from_deg=270);r=Scenario(**p)
    result=rate_of_spread(r.fuel,r.wind,slope,0)
    assert result['head_m_min'] == pytest.approx(chains_per_hour*20.1168/60,rel=1e-10)


def test_vector_and_wind_from_semantics():
    p=payload();p['wind'].update(midflame_mps=.508,from_deg=270);r=Scenario(**p)
    result=rate_of_spread(r.fuel,r.wind,math.degrees(math.atan(.3)),0)
    assert result['heading_to_deg'] == pytest.approx(15.0523735027703)
    assert result['length_width_ratio'] == pytest.approx(1.2012136371759516)
    assert rate_of_spread(r.fuel,r.wind,0,0)['heading_to_deg'] == pytest.approx(90)
    calm=r.wind.model_copy(update={'midflame_mps':0})
    assert rate_of_spread(r.fuel,calm,0,0)['heading_to_deg'] is None


def test_extinction_is_model_zero_while_missing_inputs_are_rejected():
    p=payload();p['fuel']['moisture_pct']=12
    result=run_scenario(Scenario(**p))
    assert result['cases'][0]['rates']['head_m_min']==0
    assert all(f['geometry'] is None for f in result['cases'][0]['frames'])
    del p['fuel']['load_kg_m2']
    with pytest.raises(ValidationError):Scenario(**p)


@pytest.mark.parametrize('path,value',[
    (('fuel','load_kg_m2'),float('nan')), (('wind','midflame_mps'),float('inf')),
    (('fuel','depth_m'),0), (('fuel','savr_per_m'),1), (('wind','from_deg'),360),
    (('terrain','slope_deg'),61), (('fuel','effective_mineral_pct'),50),
])
def test_input_units_and_bounds(path,value):
    p=payload();p[path[0]][path[1]]=value
    with pytest.raises(ValidationError):Scenario(**p)


def test_evidence_and_time_cannot_be_omitted_or_backdated_by_output_fields():
    p=payload();p['start_at']='2020-01-01T00:00:00'
    with pytest.raises(ValidationError):Scenario(**p)
    p=payload();p['fuel']['evidence']={**EVIDENCE,'observed_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    with pytest.raises(ValidationError):Scenario(**p)
    p=payload();p['issued_at']='2020-01-01T00:00:00Z'
    with pytest.raises(ValidationError):Scenario(**p)


def test_geometry_time_area_baseline_and_input_digest():
    r=Scenario(**payload());a=run_scenario(r);b=run_scenario(r)
    assert a['input_sha256']==b['input_sha256']
    frames=a['cases'][0]['frames']
    assert frames[1]['scenario_area_ha']==pytest.approx(4*frames[0]['scenario_area_ha'])
    assert frames[-1]['head_distance_m']==pytest.approx(a['cases'][0]['rates']['head_m_min']*180)
    for f in frames:
        coords=f['geometry']['coordinates'][0]
        assert len(coords)==73 and coords[0]==coords[-1]
        assert all(98<lon<100 and 17<lat<21 for lon,lat in coords)
    assert frames==a['baseline']['frames']
    assert not a['operational_alerts_enabled']


def test_sensitivity_is_not_probability_and_does_not_modify_central_fuel():
    p=payload();p['moisture_range_pct']=(2,10);result=run_scenario(Scenario(**p))
    central,drier,wetter=result['cases']
    assert drier['rates']['head_m_min']>central['rates']['head_m_min']>wetter['rates']['head_m_min']
    assert result['inputs']['request']['fuel']['moisture_pct']==5
    assert any('ช่วงความเชื่อมั่น' in x for x in result['limitations'])
    p['moisture_range_pct']=(6,10)
    with pytest.raises(ValidationError):Scenario(**p)


def test_legacy_wind_limit_is_explicit_and_does_not_change_heading():
    r=Scenario(**payload());wind=r.wind.model_copy(update={'midflame_mps':15})
    a=rate_of_spread(r.fuel,wind,0,0);b=rate_of_spread(r.fuel,wind,0,0,cap=True)
    assert a['effective_wind_exceeds_legacy_limit'] and not a['legacy_wind_limit_applied']
    assert b['legacy_wind_limit_applied'] and b['head_m_min']<a['head_m_min']
    assert a['heading_to_deg']==b['heading_to_deg']


def test_real_copernicus_points_and_quarantined_boundary():
    data=point_dataset()
    assert len(data['points'])==677
    assert sum(r['status']=='available' for r in data['points'].values())==676
    row=terrain_point('cmf-th-2522')['point']
    assert 0<=row['slope_deg']<=90 and 0<=row['upslope_to_deg']<360
    assert len(row['sample_sha256'])==64
    with pytest.raises(HTTPException) as error:terrain_point('cmf-th-3192')
    assert error.value.status_code==422
    p=payload();p.update(forest_id='cmf-th-2522',latitude=None,longitude=None)
    p['terrain']={'mode':'copernicus_forest_point'}
    result=run_scenario(Scenario(**p))
    assert result['inputs']['ignition']['latitude']==row['latitude']
    assert result['inputs']['terrain']['slope_deg']==row['slope_deg']
    p['latitude']=18.8
    with pytest.raises(ValidationError):Scenario(**p)


def test_evaluation_excludes_firms_from_arrival_errors_and_deduplicates():
    p=payload();r=run_scenario(Scenario(**p));rate=r['cases'][0]['rates']['head_m_min']
    lon,lat=destination(18.79,98.99,0,rate*60)
    obs={'latitude':lat,'longitude':lon,'kind':'firms_detection','observed_at':'2020-01-01T01:00:00Z','source':'NASA FIRMS test fixture'}
    same_instant={**obs,'observed_at':'2020-01-01T08:00:00+07:00'}
    req=Evaluation(scenario=p,observations=[obs,same_instant])
    result=evaluate(req)
    assert result['duplicate_count']==1 and result['unique_observation_count']==1
    assert result['field_arrival_sample_count']==0
    assert result['median_absolute_arrival_error_minutes'] is None
    obs={**obs,'kind':'field_arrival'}
    result=evaluate(Evaluation(scenario=p,observations=[obs]))
    assert result['median_absolute_arrival_error_minutes']==pytest.approx(0,abs=.01)
    assert result['mean_absolute_arrival_error_minutes']==pytest.approx(0,abs=.01)
    assert result['status']=='retrospective_diagnostic_not_blind_validation'
    assert not any(k in result for k in ('accuracy','precision','iou'))


def test_no_truth_before_start_or_beyond_horizon():
    obs={'latitude':18.79,'longitude':98.99,'kind':'firms_detection','source':'NASA FIRMS',
         'observed_at':'2020-01-01T00:00:00Z'}
    with pytest.raises(ValidationError):Evaluation(scenario=payload(),observations=[obs])
    obs['observed_at']='2020-01-01T04:00:00Z'
    with pytest.raises(ValidationError):Evaluation(scenario=payload(),observations=[obs])


def test_forward_inverse_geodesic_agree():
    lon,lat=destination(18.79,98.99,1000,1000)
    distance,bearing=distance_bearing(18.79,98.99,lat,lon)
    assert distance==pytest.approx(math.sqrt(2)*1000,abs=.01)
    assert bearing==pytest.approx(45,abs=.001)


def test_numerical_domain_and_material_provenance_are_explicit():
    p=payload();p['fuel']['load_kg_m2']=5e-324
    with pytest.raises(ValidationError):Scenario(**p)
    p=payload();p['fuel']['particle_density_kg_m3']=600
    with pytest.raises(ValidationError):Scenario(**p)
    p['fuel'].update(material_basis='user_specified',material_source='Published sample XYZ, density measured separately')
    result=run_scenario(Scenario(**p))
    assert result['inputs']['fuel_material_provenance']['basis']=='user_specified'
    p=payload();p['fuel']['evidence']={**EVIDENCE,'basis':'measured'}
    result=run_scenario(Scenario(**p))
    assert result['inputs']['fuel_material_provenance']['basis']=='behave_reference'


def test_published_slope_variant_does_not_claim_universal_behave_parity():
    p=payload();p['fuel'].update(load_kg_m2=.01,depth_m=.1,savr_per_m=2000)
    p['terrain']['slope_deg']=60
    result=run_scenario(Scenario(**p))
    assert result['cases'][0]['rates']['legacy_slope_clamp_omitted']
    assert 'unclipped' in result['inputs']['slope_factor_variant']
    assert any('ไม่อ้างว่าตรง Behave ทุกเงื่อนไข' in s for s in result['limitations'])


def test_snapshot_evaluation_keeps_original_terrain_when_live_source_changes(monkeypatch):
    from app.spread_scenario import SnapshotEvaluation, evaluate_snapshot
    p = payload(); p.pop('latitude'); p.pop('longitude')
    p.update(forest_id='cmf-th-2869', terrain={'mode':'copernicus_forest_point'})
    snapshot = run_scenario(Scenario(**p))
    monkeypatch.setattr('app.spread_scenario.resolve_terrain', lambda _: (_ for _ in ()).throw(AssertionError('must not resolve current terrain')))
    point = dict(snapshot['inputs']['ignition'], kind='field_arrival', observed_at='2020-01-01T00:30:00Z', source='synthetic test point')
    out = evaluate_snapshot(SnapshotEvaluation(snapshot=snapshot, observations=[point]))
    assert out['input_sha256'] == snapshot['input_sha256']
    assert out['scenario_issued_at'] == snapshot['issued_at']
    assert out['evaluation_basis'] == 'submitted_snapshot_equations_checked'
    assert out['observations'][0]['arrival_error_minutes'] == -30
    assert out['status'] == 'retrospective_diagnostic_not_blind_validation'


@pytest.mark.parametrize('mutation', ['rate', 'version', 'time', 'origin', 'missing', 'nan'])
def test_snapshot_rejects_inconsistent_or_malformed_artifact(mutation):
    from app.spread_scenario import SnapshotEvaluation, evaluate_snapshot
    snapshot = run_scenario(Scenario(**payload()))
    if mutation == 'rate': snapshot['cases'][0]['rates']['head_m_min'] *= 2
    if mutation == 'version': snapshot['model_version'] = 'unsupported'
    if mutation == 'time': snapshot['issued_at'] = 12
    if mutation == 'origin': snapshot['inputs']['ignition']['latitude'] = 18
    if mutation == 'missing': snapshot['cases'] = []
    if mutation == 'nan': snapshot['cases'][0]['rates']['eccentricity'] = float('nan')
    point = {'latitude':18.79, 'longitude':98.99, 'kind':'firms_detection', 'observed_at':'2020-01-01T00:30:00Z', 'source':'synthetic test point'}
    with pytest.raises((HTTPException, ValidationError)):
        evaluate_snapshot(SnapshotEvaluation(snapshot=snapshot, observations=[point]))


def test_snapshot_json_round_trip_and_beyond_horizon_are_explicit():
    import json
    from app.spread_scenario import SnapshotEvaluation, evaluate_snapshot
    snapshot = json.loads(json.dumps(run_scenario(Scenario(**payload()))))
    lon, lat = destination(18.79,98.99,10000,0)
    points = [dict(latitude=lat, longitude=lon, kind=k, observed_at='2020-01-01T01:00:00Z', source='synthetic point only') for k in ('field_arrival','firms_detection')]
    out = evaluate_snapshot(SnapshotEvaluation(snapshot=snapshot, observations=points))
    assert out['field_arrival_sample_count'] == 1
    assert out['observations'][0]['model_arrival_within_horizon'] is False
    assert out['observations'][0]['arrival_error_minutes'] > 0
    assert out['observations'][1]['arrival_error_minutes'] is None
    assert out['observations'][0]['latitude'] == lat
