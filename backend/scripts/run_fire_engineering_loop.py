"""Finite earlier-year selected offline experiment, initial-only 20 m inference.

Training: 2024; selection: 2025; 2026 new cases and previously inspected
regression cases are reported separately. Years have been studied before, so
this is retrospective validation, not a pristine prospective test.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse,gc,json
from datetime import datetime
from pathlib import Path
import numpy as np
import joblib
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import timed_fire_growth_dense as dense
from fire_engineering_inputs import initial_features
from probe_native_weather_grid import fetch_historical_case_grid

MODEL_DIR=c.OUT/'models'
THRESHOLDS=(.001,.003,.01,.03,.10,.30,.50)
CONFIGS={'point_no_pm':('point_no_pm',60,15),'point_pm':('point_pm',60,15),
    'hima':('hima',60,15),'seasonal':('seasonal',60,15),'spatial':('spatial',60,15),
    'all_no_pm':('all_no_pm',60,15),'all':('all',60,15),'all_large':('all',120,31),
    'all_no_wind':('all_no_wind',60,15)}


def metas():
    return [c.read(c.OUT/'cases'/row['id']/'case.json') for row in c.read(c.OUT/'array-manifest.json')['ready']]


def weather_features(meta):
    folder=c.OUT/'cases'/meta['id'];grid=fetch_historical_case_grid(meta,folder)
    origin=datetime.fromisoformat(meta['initial_acquisition']).replace(tzinfo=None)
    finish=datetime.fromisoformat(meta['final_acquisition']).replace(tzinfo=None)
    use=np.array([origin.replace(minute=0,second=0,microsecond=0)<=datetime.fromisoformat(str(t))<=finish for t in grid['valid_time_utc']])
    assert grid['valid_forcing_mask'][use].all()
    west,south,east,north=meta['bounds_utm47'];rr,cc=np.indices((100,100));xy=np.column_stack([(west+(cc+.5)*100).ravel(),(north-(rr+.5)*100).ravel()])
    source=np.column_stack(b.PROJECT.transform(grid['longitude'],grid['latitude']));_,node=cKDTree(source).query(xy)
    speed=np.hypot(grid['u10_m_s'][use],grid['v10_m_s'][use])
    fields=[grid['u10_m_s'][use].mean(axis=0),grid['v10_m_s'][use].mean(axis=0),speed.mean(axis=0),speed.max(axis=0),
            grid['temperature_2m_c'][use].mean(axis=0),grid['relative_humidity_2m_pct'][use].mean(axis=0),grid['precipitation_mm'][use].sum(axis=0)]
    names=['grid_u_mean','grid_v_mean','grid_speed_mean','grid_speed_max','grid_temperature_mean','grid_rh_mean','grid_rain_sum']
    hotspots=np.column_stack(b.PROJECT.transform([v['longitude'] for v in meta['initial_hotspots']],[v['latitude'] for v in meta['initial_hotspots']]))
    _,nearest=cKDTree(hotspots).query(xy);delta=xy-hotspots[nearest];u=fields[0][node];v=fields[1][node];norm=np.maximum(1e-6,np.hypot(u,v))
    along=(delta[:,0]*u+delta[:,1]*v)/norm;cross=np.abs(delta[:,0]*v-delta[:,1]*u)/norm
    values=[f[node].reshape(100,100) for f in fields]+[(np.sign(along)*np.log1p(np.abs(along))).reshape(100,100),np.log1p(cross).reshape(100,100)]
    return np.stack(values),names+['grid_alongwind','grid_crosswind']


def features(meta,initial):
    X,names,eligible=dense.features(meta,initial)
    supp,receipt=initial_features(meta)
    spatial,spatial_names=weather_features(meta)
    base_names=list(names)
    def append20(values,new_names):
        nonlocal X,names
        X=np.column_stack([X,*[v.ravel() for v in values]]).astype('float32');names+=list(new_names)
    coarse=supp['coarse'];coarse_names=supp['feature_names'].tolist()
    append20([np.repeat(np.repeat(a,5,axis=0),5,axis=1) for a in coarse],coarse_names)
    append20([supp['past_ndvi_change20'],supp['past_nbr_change20']],['pixel_past_ndvi_change','pixel_past_nbr_change'])
    append20([np.repeat(np.repeat(a,5,axis=0),5,axis=1) for a in spatial],spatial_names)
    pm=[i for i,n in enumerate(names) if n.startswith('lagged_pm_')]
    wind=[i for i,n in enumerate(names) if n.startswith('wind_') or n in ('signed_log_alongwind_distance','log_crosswind_distance') or n.startswith('grid_')]
    base=list(range(len(base_names)));hima=[names.index(n) for n in coarse_names if n.startswith('hima_')]
    seasonal=[names.index(n) for n in coarse_names if not n.startswith('hima_')]+[names.index(n) for n in ('pixel_past_ndvi_change','pixel_past_nbr_change')]
    spatial_cols=[names.index(n) for n in spatial_names]
    all_cols=list(range(len(names)))
    groups={'point_pm':base,'point_no_pm':[i for i in base if i not in pm],
            'hima':base+hima,'seasonal':base+seasonal,'spatial':base+spatial_cols,
            'all':all_cols,'all_no_pm':[i for i in all_cols if i not in pm],
            'all_no_wind':[i for i in all_cols if i not in wind]}
    assert not np.isinf(X).any()
    return X,names,eligible,groups


def load(meta):
    folder=c.OUT/'cases'/meta['id']
    with np.load(folder/'model-arrays.npz') as archive:
        initial={name:archive[name] for name in dense.KNOWN}
        arrays={name:archive[name] for name in ('valid20','initial_scar20','target20','connected_target20')}
    X,names,eligible,groups=features(meta,initial)
    valid=eligible&arrays['valid20']
    return {'meta':meta,'initial':initial,'arrays':arrays,'X':X,'names':names,'groups':groups,'eligible':eligible,'valid':valid.ravel(),'y':arrays['target20'].ravel().astype('uint8')}


def baselines(case):
    X,names,eligible=case['X'],case['names'],case['eligible'];result={'no_growth':np.zeros((500,500),bool)}
    for prefix,feature in [('hotspot','log_distance_hotspot'),('scar','log_pixel_distance_scar'),('hima','hima_log_distance')]:
        d=np.expm1(X[:,names.index(feature)]).reshape(500,500)
        for radius in (100,300,1000):result[f'{prefix}_radius{radius}']=dense.clean(eligible&(d<=radius))
    return result


def pooled(rows,name):
    scores=[row['scores'][name] for row in rows]
    p,r,i=[sum(s[k] for s in scores) for k in ('predicted_growth_km2','reference_growth_km2','intersection_km2')]
    return {'pooled_dice':2*i/(p+r) if p+r else 1.,'pooled_iou':i/(p+r-i) if p+r-i else 1.,
       'macro_dice':float(np.mean([s['dice'] for s in scores])),'predicted_growth_km2':p,'reference_growth_km2':r,
       'intersection_km2':i,'reference_coverage':i/r if r else None,'prediction_precision':i/p if p else None,
       'case_count':len(scores)}


def protocol():
    return {'version':1,'scope':'Offline only; no production promotion or deployment.',
      'train':'2024 whole cases; one deterministic negative sample per case, inverse-sampling weights preserve pixel prior.',
      'select':'2025 pooled new-growth Dice, tie less predicted area then lexical name. No2026scores for model/threshold choice.',
      'test':'2026newcasebank and alreadyinspected2026regression separately; retrospective and not a pristine prospective holdout.',
      'configs':CONFIGS,'thresholds':THRESHOLDS,'baselines':'no growth, initial scar / past VIIRS / JAXA distance100/300/1000m with initial-only vegetation eligibility',
      'reference':'Existing fixed20m spectral-change algorithm and QC; exact observed2–7day image intervals, not12h arrival time.',
      'hima':'8 nominal archived snapshots at3hcadence, ending>=3hbeforeinitial. delayassumed; missing/empty unknown; FRP excluded.',
      'spatial_weather':'Same original IFS run/times,4corner nearest samples+actual model coords; no terrain downscaling. Changes sampling AND downscaling convention; not isolated wind-only.',
      'fuel':'Initial-only spectral change plus2023samecalendar-month coarse ESAseasonalprior; not measured fuel load.',
      'pm':'Lagged35T/36T daily<=initialICTdate-2; ablated under same learner/threshold budget.',
      'initial_imagery_latency':'Retrospectively initialized at acquisition; publication delay not simulated.',
      'completion':'All finite input ablations, frozen selection, year-separated evaluation, causal replay, numerical verification and report.'}


def fit_phase():
    MODEL_DIR.mkdir(exist_ok=True)
    c.write(MODEL_DIR/'protocol.json',protocol())
    train=[m for m in metas() if m['engineering_split']=='train2024'];assert len(train)>=4
    samples=[];labels=[];weights=[];rng=np.random.default_rng(20261018);train_rows=[]
    for meta in train:
        case=load(meta);positive=np.flatnonzero(case['valid']&(case['y']==1));negative=np.flatnonzero(case['valid']&(case['y']==0))
        sample=rng.choice(negative,min(15000,len(negative)),replace=False);indices=np.r_[positive,sample]
        samples.append(case['X'][indices]);labels.append(case['y'][indices]);weights.append(np.r_[np.ones(len(positive)),np.full(len(sample),len(negative)/max(1,len(sample)))])
        names,groups=case['names'],case['groups'];train_rows.append({'id':meta['id'],'positive_pixels':len(positive),'eligible_negative_pixels':len(negative),'sampled_negative_pixels':len(sample),
            'model_arrays_content_sha256':c.array_content_sha(c.OUT/'cases'/meta['id']/'model-arrays.npz')})
        print('TRAIN_CASE',meta['id'],len(positive),'positive',flush=True);del case;gc.collect()
    X=np.vstack(samples);y=np.concatenate(labels);w=np.concatenate(weights);assert len(np.unique(y))==2
    for name,(group,iterations,leaves) in CONFIGS.items():
        model=HistGradientBoostingClassifier(max_iter=iterations,max_leaf_nodes=leaves,min_samples_leaf=75,l2_regularization=2,early_stopping=False,random_state=20261018)
        model.fit(X[:,groups[group]],y,sample_weight=w);joblib.dump(model,MODEL_DIR/(name+'.joblib'));print('MODEL_FIT',name,flush=True)
    c.write(MODEL_DIR/'feature-contract.json',{'names':names,'groups':groups,'train_cases':train_rows,'known_arrays':dense.KNOWN,'protocol_sha256':c.sha(MODEL_DIR/'protocol.json')})


def evaluate(phase):
    contract=c.read(MODEL_DIR/'feature-contract.json');rows=[]
    candidates=[m for m in metas() if (m['engineering_split']=='validation2025')==(phase=='selection') and m['engineering_split']!='train2024']
    if phase=='test':
        frozen=c.read(MODEL_DIR/'frozen-selection.json')
        for name,digest in frozen['files'].items():assert c.sha(MODEL_DIR/name)==digest
    models={name:joblib.load(MODEL_DIR/(name+'.joblib')) for name in CONFIGS}
    for meta in candidates:
        case=load(meta);assert case['names']==contract['names'] and case['groups']==contract['groups']
        masks=baselines(case)
        for name,(group,_,_) in CONFIGS.items():
            values=models[name].predict_proba(case['X'][:,contract['groups'][group]])[:,1].reshape(500,500)
            for threshold in THRESHOLDS:masks[name+'__'+str(threshold)]=dense.clean(case['eligible']&(values>=threshold))
        scores={name:dense.metrics(mask,case['arrays']) for name,mask in masks.items()}
        row={'id':meta['id'],'split':meta['engineering_split'],'cohort':meta['engineering_cohort'],'horizon_hours':meta['horizon_hours'],'scores':scores}
        if phase=='test':
            chosen=c.read(MODEL_DIR/'selection.json')['selected'];mask=masks[chosen]
            row['selected_connected_growth']=dense.metrics(mask,case['arrays'],'connected_target20')
            np.savez_compressed(c.OUT/'cases'/meta['id']/'engineering-prediction.npz',predicted=mask)
        rows.append(row);c.write(MODEL_DIR/(phase+'-progress.json'),{'rows':rows})
        print('EVALUATED',phase,meta['id'],flush=True);del case,masks;gc.collect()
    summary={name:pooled(rows,name) for name in rows[0]['scores']}
    result={'rows':rows,'summary':summary}
    if phase=='selection':
        ranking=sorted(summary,key=lambda name:(-summary[name]['pooled_dice'],summary[name]['predicted_growth_km2'],name));result.update(selected=ranking[0],ranking=ranking)
        c.write(MODEL_DIR/'selection.json',result)
        files=['selection.json','protocol.json','feature-contract.json']+[name+'.joblib' for name in CONFIGS]
        c.write(MODEL_DIR/'frozen-selection.json',{'files':{name:c.sha(MODEL_DIR/name) for name in files},'2026_scores_seen_for_selection':False})
        print('SELECTED',ranking[0],summary[ranking[0]],flush=True)
    else:
        result['selected_on2025']=c.read(MODEL_DIR/'selection.json')['selected']
        result['by_split']={split:{name:pooled([r for r in rows if r['split']==split],name) for name in summary} for split in sorted({r['split'] for r in rows})}
        c.write(MODEL_DIR/'test-results.json',result)


def predict(meta,initial):
    """Inference contract only: initial arrays, cached past inputs and forecast."""
    selected=c.read(MODEL_DIR/'selection.json')['selected']
    if selected.startswith(('point_no_pm__','point_pm__')):
        name,threshold=selected.rsplit('__',1)
        X,names,eligible=dense.features(meta,initial,include_pm=name!='point_no_pm')
        contract=c.read(MODEL_DIR/'feature-contract.json');columns=contract['groups'][CONFIGS[name][0]]
        assert [names[i] for i in columns]==[contract['names'][i] for i in columns]
        model=joblib.load(MODEL_DIR/(name+'.joblib'))
        return dense.clean(eligible&(model.predict_proba(X[:,columns])[:,1].reshape(500,500)>=float(threshold)))
    X,names,eligible,groups=features(meta,initial)
    case={'X':X,'names':names,'eligible':eligible}
    if '__' not in selected:return baselines(case)[selected]
    name,threshold=selected.rsplit('__',1);group=CONFIGS[name][0]
    model=joblib.load(MODEL_DIR/(name+'.joblib'))
    return dense.clean(eligible&(model.predict_proba(X[:,groups[group]])[:,1].reshape(500,500)>=float(threshold)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('fit','selection','test'),required=True);args=parser.parse_args()
    if args.phase=='fit':fit_phase()
    else:evaluate(args.phase)


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
