"""Replay frozen offline selection using a labels-free initialization bundle."""
import argparse,shutil
from contextlib import contextmanager
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import run_fire_engineering_loop as loop
import fire_engineering_physics as physical
import timed_fire_growth_dense as dense

KNOWN=tuple(dict.fromkeys([*dense.KNOWN,'seeds_point']))


def bundle(case_id,destination):
    source=c.OUT/'cases'/case_id;meta=c.read(source/'case.json');folder=destination/'cases'/case_id;folder.mkdir(parents=True,exist_ok=True)
    c.write(folder/'case.json',meta)
    with np.load(source/'model-arrays.npz',allow_pickle=False) as archive:
        known={key:archive[key] for key in KNOWN}
    np.savez_compressed(folder/'initial-state.npz',**known)
    choice=c.read(c.OUT/'global-frozen-selection.json')
    minimal_point=choice['family']=='learned_or_baseline' and choice['name'].startswith(('point_no_pm__','point_pm__'))
    source_names=('single-run-weather.json',) if minimal_point else ('initial-supplement.npz','initial-supplement.json','single-run-weather.json','corner-weather.json','corner-weather.npz','corner-weather-contract.json')
    for name in source_names:
        shutil.copyfile(source/name,folder/name)
    origin=datetime.fromisoformat(meta['initial_acquisition']).astimezone(ml.j.ICT)
    cutoff=origin.date()-timedelta(days=2);first=cutoff-timedelta(days=6)
    if not (minimal_point and choice['name'].startswith('point_no_pm__')):
        dates=c.read(ml.j.OUT/f'pm-{origin.year}.json')['dates']
        c.write(destination/'context'/f'pm-{origin.year}.json',{'dates':{day:row for day,row in dates.items() if str(first)<=day<=str(cutoff)}})
    c.write(destination/'bundle-contract.json',{'case_id':case_id,'known_arrays':KNOWN,'future_optical_images_or_labels_included':False,
      'pm_latest_eligible_date':str(cutoff),'model_selection':choice,'selected_point_model_omits_unused_supplemental_inputs':minimal_point,
      'note':'Historical research replay; initial optical publication latency not simulated. Cached weather contains known single-run forecasts for desired horizon.'})
    return destination


@contextmanager
def input_root(folder):
    previous=(c.OUT,b.OUT,prep.OUT,physics.OUT,ml.OUT,ml.j.OUT)
    c.OUT=b.OUT=prep.OUT=physics.OUT=ml.OUT=folder;ml.j.OUT=folder/'context'
    try:yield
    finally:c.OUT,b.OUT,prep.OUT,physics.OUT,ml.OUT,ml.j.OUT=previous


def replay(folder,case_id):
    choice=c.read(c.OUT/'global-frozen-selection.json')
    with input_root(folder):
        meta=c.read(folder/'cases'/case_id/'case.json')
        with np.load(folder/'cases'/case_id/'initial-state.npz',allow_pickle=False) as archive:
            assert set(archive.files)==set(KNOWN)
            known={key:archive[key] for key in KNOWN}
        if choice['family']=='surface_graph':
            config=next(v for v in physical.CONFIGS if v['name']==choice['name'])
            mask=physical.predict(meta,known,config)
            mask=np.repeat(np.repeat(mask,5,axis=0),5,axis=1)
        else:mask=loop.predict(meta,{key:known[key] for key in dense.KNOWN})
    return mask,meta,choice


def forecast_domain(folder,case_id):
    with np.load(folder/'cases'/case_id/'initial-state.npz') as archive:
        swir,nir,red=archive['initial_falsecolor'];ndvi=(nir-red)/np.maximum(nir+red,1e-6)
        eligible=archive['initial_valid20']&(ndvi>=.30)&~archive['initial_scar20']&np.repeat(np.repeat(archive['burnable'],5,axis=0),5,axis=1)
        return eligible,archive['initial_valid20'],archive['initial_scar20']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case-id',required=True);parser.add_argument('--bundle-root',type=Path);parser.add_argument('--prepare-bundle',action='store_true');args=parser.parse_args()
    destination=args.bundle_root or c.OUT/'replay-selected'
    if args.prepare_bundle:bundle(args.case_id,destination)
    mask,meta,choice=replay(destination,args.case_id)
    eligible,clear,initial_scar=forecast_domain(destination,args.case_id)
    if choice['family']=='learned_or_baseline':assert not (mask&~eligible).any()
    path=destination/'prediction.npz';np.savez_compressed(path,predicted=mask,applicability20=eligible,initial_clear20=clear,known_initial_scar20=initial_scar)
    receipt={'case_id':args.case_id,'selected_family':choice['family'],'selected_name':choice['name'],'initial_time':meta['initial_acquisition'],
      'requested_valid_until':meta['final_acquisition'],'grid_crs':'EPSG:32647','bounds_utm47':meta['bounds_utm47'],'pixel_size_m':20,
      'predicted_mask_area_before_future_visibility_mask_km2':float(mask.sum()*.0004),'prediction_sha256':c.sha(path),
      'applicable_fraction':float(eligible.mean()),'outside_applicability_semantics':'Unknown/unmodeled, never an all-clear/no-fire declaration.',
      'future_images_or_target_labels_read':False,'mode':'offline_retrospective_replay','production_changed':False}
    c.write(destination/'prediction-receipt.json',receipt);print(receipt)


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
