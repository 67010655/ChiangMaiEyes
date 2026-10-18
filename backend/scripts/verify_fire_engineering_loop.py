"""Meaningful numeric, causal replay, provenance and production-freeze checks."""
import argparse
from datetime import datetime,timedelta
import numpy as np
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import verify_timed_fire_benchmark as old_verify
import fire_engineering_physics as physical
from probe_native_weather_grid import sample_wind


def numeric():
    checks=old_verify.fixtures()
    shape=(3,3);rr,cc=np.indices(shape)
    sampled=sample_wind(c.OUT/'native-weather/chiang-mai-surface-grid.npz',18.7883+(rr-1)*.001,98.9853+(cc-1)*.001)
    u=sampled['u10_m_s'].reshape(shape);v=sampled['v10_m_s'].reshape(shape)
    known={'burnable':np.ones(shape,bool),'seeds_point':np.zeros(shape,bool),'elevation_m':np.zeros(shape),
           'slope':np.zeros(shape),'aspect':np.zeros(shape),'landcover':np.full(shape,10),'dryness_proxy':np.ones(shape)}
    known['seeds_point'][1,1]=True
    records=[{'start':i*60,'wind':0.,'from':0.,'moisture':(.08,.08,.08),'u_grid':u,'v_grid':v} for i in range(2)]
    config={**physical.CONFIGS[2],'active_hours':1}
    rates=physical.GridRates(known,records,config)
    for r,col in ((0,0),(1,1),(2,2)):
        head,ecc,direction=rates.peak(r,col,0)
        direct=physics.sf.calc_surface_fire_behavior_max(rates.base(0,8),float(np.hypot(u[r,col],v[r,col]))*.2*60,
            float((270-np.degrees(np.arctan2(v[r,col],u[r,col])))%360),0.,0.)
        assert abs(head-direct.max_spread_rate)<1e-12 and np.isfinite(head)
        np.testing.assert_allclose(direction,direct.max_spread_direction)
    arrival=physics.simulate(known,records,60,config,rates_class=physical.GridRates)
    assert arrival[1,1]==0 and np.isfinite(arrival).sum()>=1
    rates.peak.cache_clear();rates.base.cache_clear()
    checks['actual_native_grib_to_spatial_surface_rate_and_graph']='passed; current field numerical smoke only, not historical skill'
    return checks


def frozen_production():
    expected=c.read(c.ROOT/'output/joint-fire-model-20261017/production-files-frozen.json')
    actual={name:c.sha(c.ROOT/name) for name in expected};assert actual==expected
    old=c.read(c.OLD/'frozen-inputs.json')
    for name,digest in old['files'].items():assert c.sha(c.ROOT/name)==digest,'Changed old frozen source '+name
    return {'production_files_unchanged':actual,'old_frozen_input_count':len(old['files']),'deployment_commands_issued':0}


def full():
    import run_fire_engineering_loop as loop
    import predict_fire_engineering as inference
    metas=loop.metas();receipt=[]
    for meta in metas:
        folder=c.OUT/'cases'/meta['id'];origin=datetime.fromisoformat(meta['initial_acquisition']);run=datetime.fromisoformat(meta['weather']['run_init'])
        assert run+timedelta(hours=6)<=origin
        assert all(datetime.fromisoformat(p['detected_at'].replace('Z','+00:00'))<=origin-timedelta(hours=3) for p in meta['initial_hotspots'])
        supplementary=c.read(folder/'initial-supplement.json')
        assert supplementary['esa_prior_year']<origin.year
        assert all(datetime.fromisoformat(r['nominal_observation_time_utc'])<=origin-timedelta(hours=3) for r in supplementary['himawari_frames'])
        assert c.sha(folder/'initial-supplement.npz')==supplementary['npz_sha256']
        grid=c.read(folder/'corner-weather-contract.json');assert grid['original_valid_times_exact_match'] and grid['case_horizon_all_finite']
        if meta['engineering_split']=='train2024':assert origin.year==2024
        elif meta['engineering_split']=='validation2025':assert origin.year==2025
        else:assert origin.year==2026
        receipt.append({'id':meta['id'],'split':meta['engineering_split'],'corner_points':grid['unique_grid_point_count']})
    frozen=c.read(loop.MODEL_DIR/'frozen-selection.json')
    for name,digest in frozen['files'].items():assert c.sha(loop.MODEL_DIR/name)==digest
    for row in c.read(loop.MODEL_DIR/'feature-contract.json')['train_cases']:
        assert row['model_arrays_content_sha256']==c.array_content_sha(c.OUT/'cases'/row['id']/'model-arrays.npz')
    choice=c.read(c.OUT/'global-frozen-selection.json')
    assert choice['ml_selection_sha256']==c.sha(loop.MODEL_DIR/'selection.json')
    assert choice['physics_selection_sha256']==c.sha(physical.OUT/'selection.json')
    # Only copied initial-state fields and past weather/satellite summaries exist
    # in this separate input tree; no final imagery/label archive is available.
    test=next(meta for meta in metas if meta['engineering_split']=='test2026_new_cases')
    destination=c.OUT/'replay-selected';inference.bundle(test['id'],destination)
    mask,_,_=inference.replay(destination,test['id'])
    folder=c.OUT/'cases'/test['id']
    if choice['family']=='surface_graph':
        stored=np.load(folder/(choice['name']+'-field-prediction.npz'))['predicted'];stored=np.repeat(np.repeat(stored,5,axis=0),5,axis=1)
    else:stored=np.load(folder/'engineering-prediction.npz')['predicted']
    np.testing.assert_array_equal(mask,stored)
    input_names=[p.name for p in (destination/'cases'/test['id']).iterdir()]
    assert 'model-arrays.npz' not in input_names and not any(name.startswith('S2') for name in input_names)
    # Poison future PM dates in the isolated context and prove identical replay.
    cutoff=datetime.fromisoformat(test['initial_acquisition']).astimezone(ml.j.ICT).date()-timedelta(days=2)
    # Verify the PM-consuming feature branch separately even when the selected
    # model correctly omits PM and runs with no context directory at all.
    audit_root=c.OUT/'verification-pm-branch';path=audit_root/f'pm-{cutoff.year}.json'
    source=c.read(ml.j.OUT/f'pm-{cutoff.year}.json')['dates'];first=cutoff-timedelta(days=6)
    pm={'dates':{day:row for day,row in source.items() if str(first)<=day<=str(cutoff)}};c.write(path,pm)
    with np.load(destination/'cases'/test['id']/'initial-state.npz') as archive:initial={key:archive[key] for key in loop.dense.KNOWN}
    previous_pm=ml.j.OUT
    try:
        ml.j.OUT=audit_root;before_features,_,_=ml.make_features(test,initial)
        pm['dates'][str(cutoff+timedelta(days=1))]={'35T':99999999,'36T':99999999};c.write(path,pm)
        after_features,_,_=ml.make_features(test,initial);np.testing.assert_array_equal(before_features,after_features)
    finally:ml.j.OUT=previous_pm
    again,_,_=inference.replay(destination,test['id']);np.testing.assert_array_equal(mask,again)
    eligible,clear,initial_scar=inference.forecast_domain(destination,test['id'])
    if choice['family']=='learned_or_baseline':assert not (mask&~eligible).any()
    np.savez_compressed(destination/'prediction.npz',predicted=mask,applicability20=eligible,initial_clear20=clear,known_initial_scar20=initial_scar)
    return {'case_temporal_contracts':receipt,'frozen_model_selection':'passed','labels_free_replay_case':test['id'],
      'replay_exact_prediction_parity':'passed','future_pm_poisoning_invariance':'passed on the full PM-consuming feature branch','replay_input_files':input_names,
      'initial_state_allowlist':inference.KNOWN}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--numeric-only',action='store_true');args=parser.parse_args()
    result={'status':'PASS','numeric':numeric(),'frozen':frozen_production()}
    if not args.numeric_only:result['full']=full()
    c.write(c.OUT/('numerical-verification.json' if args.numeric_only else 'verification.json'),result);print(result)


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
