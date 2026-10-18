"""One predeclared input improvement: past spatial CAMS PM, fixed HGB config."""
import hashlib,json,math
from datetime import timedelta
from pathlib import Path
import joblib,numpy as np
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
import joint_fire_experiment as j

SOURCE=j.OUT;OUT=SOURCE/'spatial-pm-comparison';OUT.mkdir(parents=True,exist_ok=True)
CAMSNAMES=['cams_local_d2','cams_local_d3','cams_local3day_mean','cams_local_change','cams_spatial_anomaly','cams_nearest_hotspot_d2']
NAME='spatial_pm_hgb';CACHE={}
def load_cams(year,grid):
    if year in CACHE:return CACHE[year]
    records=j.read(SOURCE/f'cams-spatial-{year}.json');dates={}
    for location,r in enumerate(records):
        groups={}
        for when,value in zip(r['hourly']['time'],r['hourly']['pm2_5']):groups.setdefault(when[:10],[]).append(value)
        for date,values in groups.items():
            row=dates.setdefault(date,np.full(len(records),np.nan))
            if len(values)==24 and all(v is not None and math.isfinite(v) and v>=0 for v in values):row[location]=np.mean(values)
    centres=np.column_stack(j.projection.transform([r['longitude'] for r in records],[r['latitude'] for r in records]))
    out={'dates':dates,'centres':centres,'grid_index':cKDTree(centres).query(grid['xy'],workers=1)[1]};CACHE[year]=out;return out
def spatial_pm_features(data,origin,grid,cams):
    dates=[str(origin.date()-timedelta(days=d)) for d in (2,3,4)];past=[cams['dates'].get(d) for d in dates]
    if any(r is None or not np.isfinite(r).all() for r in past):return None
    latest,previous,_=past;idx=cams['grid_index'];local=latest[idx];before=previous[idx];average=np.mean(past,axis=0)[idx]
    cutoff=origin.timestamp()-3*3600;a=np.searchsorted(data['times'],cutoff-24*3600);b=np.searchsorted(data['times'],cutoff,side='right')
    if b>a:
        points=data['xy'][a:b];nearest=cKDTree(points).query(grid['xy'],workers=1)[1]
        atsource=cKDTree(cams['centres']).query(points,workers=1)[1];source_pm=latest[atsource[nearest]]
    else:source_pm=np.full(len(local),np.nan)
    return np.column_stack([np.log1p(local),np.log1p(before),np.log1p(average),(local-before)/100,
        (local-np.mean(latest))/100,np.log1p(source_pm)]).astype('float32')
def train(grid):
    path=OUT/'training2024.npz'
    if path.exists():r=np.load(path);return r['X'],r['y']
    original=np.load(SOURCE/'training2024.npz');X,y=original['X'],original['y'];receipt=j.read(SOURCE/'training-receipt.json')
    data=j.load(2024,grid);cams=load_cams(2024,grid);rng=np.random.default_rng(20261017);chunks=[];offset=0
    from datetime import datetime
    for timestamp in receipt['issues']:
        origin=datetime.fromisoformat(timestamp);label,_=j.labels(data,origin,grid);pos=np.flatnonzero(label);neg=np.flatnonzero(label==0)
        sample=np.r_[pos,rng.choice(neg,min(1024,len(neg)),replace=False)];last=offset+len(sample)
        np.testing.assert_array_equal(X[offset:last,:8],grid['static'][sample])
        np.testing.assert_array_equal(y[offset:last],label[sample])
        extra=spatial_pm_features(data,origin,grid,cams);assert extra is not None
        chunks.append(np.column_stack([X[offset:last],extra[sample]]));offset=last
    assert offset==len(X);joined=np.vstack(chunks).astype('float32');np.savez_compressed(path,X=joined,y=y)
    print('spatialPM training',joined.shape,flush=True);return joined,y
def evaluate(year,grid,model):
    data=j.load(year,grid);cams=load_cams(year,grid);reference={r['issued_at']:r for r in j.read(SOURCE/f'results-{year}.json')['rows']}
    folder=OUT/f'rows-{year}';folder.mkdir(exist_ok=True);rows=[];skips=[]
    for i,origin in enumerate(j.issues(year)):
        path=folder/(origin.strftime('%Y%m%dT%H')+'.json')
        if path.exists():rows.append(j.read(path));continue
        extra=spatial_pm_features(data,origin,grid,cams)
        if extra is None:skips.append(origin.isoformat());continue
        prepared,reason=j.prepare(data,origin,grid)
        if prepared is None:skips.append(origin.isoformat());continue
        X,old,_=prepared;y,meta=j.labels(data,origin,grid);distance=np.expm1(old[:,8]);expansion=(distance>500)&(distance<=5000)
        values=model.predict_proba(np.column_stack([X,extra]))[:,1];baseline=reference[origin.isoformat()]
        row={'issued_at':origin.isoformat(),**meta,'expansion_targets':int(y[expansion].sum()),
             'scores':{NAME:j.score(values,y,expansion),**{n:baseline['scores'][n] for n in ('hotspot_wind_pm__large','previous_boost15','kernel')}}}
        j.write(path,row);rows.append(row)
        if i%50==0:print('spatialPM evaluate',year,i,flush=True)
    report={'year':year,'summary':j.aggregate(rows,list(rows[0]['scores'])),'rows':rows,'skipped':skips}
    j.write(OUT/f'results-{year}.json',report);return report
def main():
    protocol={'change':'Add6spatial PM context features to53input joint model; HGB100iterations31leaves fixed before this test.',
      'PMsource':'CAMS global archive at12positions, daily ICT means onD-2,D-3,D-4 only; not station measurements and not verified as-issued archives.',
      'train':2024,'select':2025,'test':2026,'common_dates':'Require complete laggedCAMSdays; compare every prior candidate on identical common2025dates before selection.',
      'limit':'2026 already inspected repeatedly in prior work; retrospective comparison only, no untouched season claim.',
      'production_changed':False,'new_feature_names':CAMSNAMES,'source_sha256':{str(y):hashlib.sha256((SOURCE/f'cams-spatial-{y}.json').read_bytes()).hexdigest() for y in (2024,2025,2026)}}
    j.write(OUT/'protocol.json',protocol);grid=j.build_grid();X,y=train(grid);path=OUT/'model.joblib'
    if path.exists():model=joblib.load(path)
    else:
        model=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=31,learning_rate=.08,min_samples_leaf=30,l2_regularization=10,random_state=20261017)
        model.fit(X,y);joblib.dump(model,path)
    val=evaluate(2025,grid,model);common={r['issued_at'] for r in val['rows']};totals={NAME:val['summary']['scores'][NAME]['250.0']['hits']}
    for p in (SOURCE/'results-2025.json',SOURCE/'lightgbm-comparison/results-2025.json'):
        result=j.read(p)
        for name in result['summary']['scores']:
            totals[name]=sum(r['scores'][name]['250.0']['hits'] for r in result['rows'] if r['issued_at'] in common)
    prior=j.read(SOURCE/'selection.json')['selected_primary'];ranking=sorted(totals,key=lambda n:(totals[n],n==prior),reverse=True)
    selection={'selected_overall_on2025':ranking[0],'common_validation_issues':len(common),'target_cells':val['summary']['target_cells'],
      'all_candidate_hits2025_on_common_dates':totals,'ranking':ranking,'tie_preference':prior}
    j.write(OUT/'selection.json',selection);print('SPATIAL PM SELECTION',json.dumps(selection),flush=True)
    test=evaluate(2026,grid,model);report={'protocol':protocol,'selection':selection,'validation':val['summary'],'test':test['summary'],
      'gain_pp_vs_old_95pct':j.uncertainties(test['rows'],list(test['summary']['scores'])),'production_changed':False}
    j.write(OUT/'summary.json',report);print('SPATIAL PM RESULT',json.dumps(report),flush=True)
if __name__=='__main__':main()
