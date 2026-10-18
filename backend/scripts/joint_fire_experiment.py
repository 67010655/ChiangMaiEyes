"""Offline controlled ablation: hotspots, spatial wind and lagged measured PM.

No production imports for publishing, application writes, UI changes or deploys.
The observable target is later satellite detection, not a measured fire front.
"""
import hashlib,json,math,os,time
from datetime import timedelta,datetime,timezone
from pathlib import Path
import joblib,numpy as np
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from priority_forecast_experiment import ROOT,OUT as OLD,ICT,build_grid,load_year,issues,features,labels,write,read,projection
from check_priority_robustness import scores as kernel_scores

OUT=ROOT/'output/joint-fire-model-20261017';OUT.mkdir(parents=True,exist_ok=True)
VERSION='joint-input-ablation-v1'
GROUPS=('hotspot_context','hotspot_wind','hotspot_pm','hotspot_wind_pm')
CONFIGS={'small':{'max_iter':60,'max_leaf_nodes':15},'large':{'max_iter':100,'max_leaf_nodes':31}}
BASE_COLUMNS=list(range(22))+list(range(24,29)) # fixed context, omit original single-point wind
BASE_NAMES=['longitude','latitude','elevation','slope','cover10','cover20','cover30','cover40',
  'day_distance','day_count','day_age','day_frp','week_distance','week_count','month_distance','month_count',
  'temperature_mean','temperature_max','rh_mean','rh_max','rain_mean','rain_max','solar_mean','solar_max','doy_sin','doy_cos','morning_issue']
WIND_NAMES=['local_u','local_v','local_speed_mean','local_speed_max','local_u_std','local_v_std',
  'local_first_u','local_first_v','local_last_u','local_last_v','nearest_source_speed','source_to_cell_alignment',
  'signed_alongwind_distance','crosswind_distance','downwind_recent_kernel','upwind_recent_kernel']
PM_NAMES=['station35t','station36t','mean_latest','mean3days','mean7days','trend3days','trend7days','max3days','valid_stations','available_days7']
ALL_NAMES=BASE_NAMES+WIND_NAMES+PM_NAMES
COLS={GROUPS[0]:list(range(27)),GROUPS[1]:list(range(43)),GROUPS[2]:list(range(27))+list(range(43,53)),GROUPS[3]:list(range(53))}
_year_cache={}

def load(year,grid):
    if year in _year_cache:return _year_cache[year]
    data=load_year(year);met=read(OUT/f'gfs-spatial-{year}.json');pm=read(OUT/f'pm-{year}.json')
    # Assignment uses returned GFS sample coordinates; same projection as cells.
    centres=np.column_stack(projection.transform([r['longitude'] for r in met],[r['latitude'] for r in met]))
    data['wind_grid_index']=cKDTree(centres).query(grid['xy'],workers=1)[1]
    data['wind_centres']=centres;data['met']=met
    data['met_index']={datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp():i for i,t in enumerate(met[0]['hourly']['time'])}
    data['pm']=pm['dates'];_year_cache[year]=data;return data

def pm_features(data,origin,lag_days=2):
    date=origin.date()-timedelta(days=lag_days);history=[]
    for lag in range(7):
        row=data['pm'].get(str(date-timedelta(days=lag)),{})
        values=[row.get(s) for s in ('35T','36T')];good=[v for v in values if v is not None]
        history.append((values,float(np.mean(good)) if good else None,len(good)))
    latest,mean,count=history[0]
    if mean is None:return None
    three=[h[1] for h in history[:3] if h[1] is not None];seven=[h[1] for h in history if h[1] is not None]
    m3=float(np.mean(three));m7=float(np.mean(seven))
    return np.array([*[np.log1p(v) if v is not None else np.nan for v in latest],np.log1p(mean),np.log1p(m3),np.log1p(m7),
       (mean-m3)/100,(mean-m7)/100,np.log1p(max(three)),count/2,len(seven)/7],dtype='float32')

def wind_features(data,origin,grid):
    indices=[data['met_index'].get(origin.timestamp()+h*3600) for h in range(12)]
    if any(i is None for i in indices):return None
    wind=[]
    for record in data['met']:
        hourly=record['hourly'];speed=np.array([hourly['wind_speed_10m_previous_day1'][i] for i in indices],dtype=float)
        direction=np.array([hourly['wind_direction_10m_previous_day1'][i] for i in indices],dtype=float)
        if not np.isfinite(speed).all() or not np.isfinite(direction).all():return None
        radians=np.radians(direction);u=-speed*np.sin(radians);v=-speed*np.cos(radians)
        wind.append([np.mean(u),np.mean(v),np.mean(speed),np.max(speed),np.std(u),np.std(v),u[0],v[0],u[-1],v[-1]])
    values=np.array(wind);local=values[data['wind_grid_index']];t=origin.timestamp();cutoff=t-3*3600
    a=np.searchsorted(data['times'],cutoff-24*3600);b=np.searchsorted(data['times'],cutoff,side='right')
    n=len(grid['xy'])
    if a==b:return np.column_stack([local,np.zeros((n,6))]).astype('float32')
    points=data['xy'][a:b];distance,nearest=cKDTree(points).query(grid['xy'],k=min(8,b-a),workers=1)
    if distance.ndim==1:distance=distance[:,None];nearest=nearest[:,None]
    source_grid=cKDTree(data['wind_centres']).query(points,workers=1)[1];source=values[source_grid]
    delta=grid['xy'][:,None,:]-points[nearest];u=source[nearest,0];v=source[nearest,1];norm=np.hypot(u,v)
    # Direction-relative features, not wind-speed translation into flame speed.
    along=(delta[:,:,0]*u+delta[:,:,1]*v)/np.maximum(norm,1e-6)
    cross=np.abs(delta[:,:,0]*v-delta[:,:,1]*u)/np.maximum(norm,1e-6)
    cosine=np.clip(along/np.maximum(distance,1),-1,1)
    age=(t-data['times'][a:b][nearest])/3600;kernel=np.exp(-distance/1500-age/24)
    relative=np.column_stack([source[nearest[:,0],2],cosine[:,0],np.sign(along[:,0])*np.log1p(np.abs(along[:,0])),
       np.log1p(cross[:,0]),np.max(kernel*np.maximum(0,cosine),axis=1),np.max(kernel*np.maximum(0,-cosine),axis=1)])
    return np.column_stack([local,relative]).astype('float32')

def prepare(data,origin,grid,pm_lag=2):
    pm=pm_features(data,origin,pm_lag)
    if pm is None:return None,'pm_history_missing'
    old,bases=features(data,origin,grid)
    if old is None:return None,'original_weather_missing'
    wind=wind_features(data,origin,grid)
    if wind is None:return None,'spatial_wind_missing'
    X=np.column_stack([old[:,BASE_COLUMNS],wind,np.tile(pm,(len(old),1))]).astype('float32')
    assert X.shape[1]==len(ALL_NAMES)==53 and not np.isinf(X).any()
    return (X,old,bases),None

def train(grid):
    path=OUT/'training2024.npz'
    if path.exists():
        saved=np.load(path);assert saved['version'].item()==VERSION;return saved['X'],saved['y']
    data=load(2024,grid);rng=np.random.default_rng(20261017);xs=[];ys=[];kept=[];skipped=[]
    for i,origin in enumerate(issues(2024)):
        prepared,reason=prepare(data,origin,grid)
        if prepared is None:skipped.append({'issue':origin.isoformat(),'reason':reason});continue
        X,old,bases=prepared;y,meta=labels(data,origin,grid);positive=np.flatnonzero(y);negative=np.flatnonzero(y==0)
        indices=np.r_[positive,rng.choice(negative,min(1024,len(negative)),replace=False)]
        xs.append(X[indices]);ys.append(y[indices]);kept.append(origin.isoformat())
        if i%50==0:print('training features',i,flush=True)
    X=np.vstack(xs);y=np.concatenate(ys);np.savez_compressed(path,X=X,y=y,version=VERSION)
    write(OUT/'training-receipt.json',{'rows':len(y),'positive_cells':int(y.sum()),'features':ALL_NAMES,'issues':kept,'skipped':skipped})
    print('training shape',X.shape,'positives',int(y.sum()),flush=True);return X,y

def score(values,y,expansion):
    top=np.lexsort((np.arange(len(values)),-values))[:2000]
    return {str(b):{'hits':int(y[top[:int(b/.25)]].sum()),'expansion_hits':int(y[top[:int(b/.25)]][expansion[top[:int(b/.25)]]].sum())} for b in (125.,250.,500.)}

def aggregate(rows,names):
    return {'issues':len(rows),'target_cells':sum(r['target_cells_all'] for r in rows),'expansion_target_cells':sum(r['expansion_targets'] for r in rows),
      'scores':{n:{str(b):{k:sum(r['scores'][n][str(b)][k] for r in rows) for k in ('hits','expansion_hits')} for b in (125.,250.,500.)} for n in names}}

def evaluate(year,grid,models):
    data=load(year,grid);folder=OUT/f'rows-{year}';folder.mkdir(exist_ok=True);rows=[];skipped=[]
    old_model=joblib.load(OLD/'boost15.joblib')
    for i,origin in enumerate(issues(year)):
        path=folder/(origin.strftime('%Y%m%dT%H')+'.json')
        if path.exists():rows.append(read(path));continue
        prepared,reason=prepare(data,origin,grid)
        if prepared is None:skipped.append({'issue':origin.isoformat(),'reason':reason});continue
        X,old,bases=prepared;y,meta=labels(data,origin,grid)
        distance=np.expm1(old[:,8]);expansion=(distance>500)&(distance<=5000)
        predictions={name:model.predict_proba(X[:,COLS[name.split('__')[0]]])[:,1] for name,model in models.items()}
        # Matched rows, original trained model and frozen tuned kernel from2025.
        predictions.update(previous_boost15=old_model.predict_proba(old)[:,1],day=bases['day'],kernel=kernel_scores(data,origin,grid,[4])['4'])
        row={'issued_at':origin.isoformat(),**meta,'expansion_targets':int(y[expansion].sum()),
          'scores':{n:score(values,y,expansion) for n,values in predictions.items()}}
        write(path,row);rows.append(row)
        if i%40==0:print('evaluate',year,i,'targets',meta['target_cells_all'],flush=True)
    names=list(rows[0]['scores']);report={'year':year,'version':VERSION,'summary':aggregate(rows,names),'skipped':skipped,'rows':rows}
    write(OUT/f'results-{year}.json',report);return report

def select_models_by_validation(validation):
    chosen={}
    for group in GROUPS:
        names=[n for n in validation['summary']['scores'] if n.startswith(group+'__')]
        chosen[group]=max(names,key=lambda n:validation['summary']['scores'][n]['250.0']['hits'])
    winner=max(chosen.values(),key=lambda n:validation['summary']['scores'][n]['250.0']['hits'])
    return {'chosen_per_group':chosen,'selected_primary':winner,'selection_year':2025,'criterion':'Pooled coverage at250km2; only one frozen model per group goes to2026.'}

def uncertainties(rows,names):
    matrix={}
    for row in rows:
        v=matrix.setdefault(row['issued_at'][:10],np.zeros(len(names)+1));v[0]+=row['target_cells_all']
        for i,n in enumerate(names,1):v[i]+=row['scores'][n]['250.0']['hits']
    matrix=np.array(list(matrix.values()));rng=np.random.default_rng(20261017);draws=[]
    for _ in range(4000):
        starts=rng.integers(0,len(matrix),math.ceil(len(matrix)/7));idx=np.concatenate([(s+np.arange(7))%len(matrix) for s in starts])[:len(matrix)]
        draws.append(matrix[idx].sum(axis=0))
    d=np.array(draws);base=names.index('previous_boost15')+1
    return {name:list(np.percentile(100*(d[:,i+1]-d[:,base])/d[:,0],[2.5,97.5])) for i,name in enumerate(names) if name!='previous_boost15'}

def main():
    protocol={'version':VERSION,'deployment_policy':'OFFLINE ONLY. No production files, UI or deployments.',
      'groups':GROUPS,'common_context':'Same terrain, land cover, calendar and province T/RH/rain/solar; original single-point wind removed from common features.',
      'wind':'12spatial GFS previous-day1 locations; mean/variation of true-east/north vectors, direction relative to past hotspots; not terrain-resolved fire-front winds.',
      'pm':'Official35T/36T daily measured PM, latest date<=issue ICT date-2; exact publishing time/window unverified; city context only, not spatial PM map.',
      'target':'Nominal/high VIIRS detections next12h in500m grid; no claim of fire perimeter or confirmed incidents.',
      'expansion_target':'Grid-centre distance>500m and<=5km from prior24h hotspots; later detections may also be separate ignitions.',
      'train':2024,'selection':2025,'retrospective_test':2026,'hotspot_latency_hours':3,'issue_ict_hours':[8,20],
      'candidate_configs':CONFIGS,'feature_names':ALL_NAMES,'group_columns':COLS,'budgets_km2':[125,250,500],
      'training_negative_sampling':'All future-positive cells plus1024uniform negative cells per issue; scores are not calibrated probabilities.',
      'test_history':'2026 already inspected in earlier work; not an untouched independent season. No further tuning from2026.',
      'sources':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for y in (2024,2025,2026) for p in (OUT/f'pm-{y}.json',OUT/f'gfs-spatial-{y}.json',ROOT/f'output/hindcast-{y}/firms-points.json')]}
    existing=OUT/'protocol.json'
    if existing.exists():assert read(existing)==protocol,'Protocol changed; use a new experiment folder/version.'
    write(existing,protocol);grid=build_grid();X,y=train(grid);models={}
    for group in GROUPS:
        for label,config in CONFIGS.items():
            name=group+'__'+label;path=OUT/(name+'.joblib')
            if path.exists():model=joblib.load(path)
            else:
                model=HistGradientBoostingClassifier(**config,learning_rate=.08,min_samples_leaf=30,l2_regularization=10,random_state=20261017)
                model.fit(X[:,COLS[group]],y);joblib.dump(model,path)
            models[name]=model;print('fit',name,model.n_iter_,flush=True)
    validation=evaluate(2025,grid,models);selection=select_models_by_validation(validation);write(OUT/'selection.json',selection)
    print('SELECTION',json.dumps(selection),flush=True)
    test=evaluate(2026,grid,{n:models[n] for n in selection['chosen_per_group'].values()})
    monthly={m:aggregate([r for r in test['rows'] if r['issued_at'][5:7]==m],test['summary']['scores']) for m in ('01','02','03','04')}
    report={'protocol':protocol,'selection':selection,'validation':validation['summary'],'test':test['summary'],'monthly_test':monthly,
      'gain_pp_vs_previous_model_95pct_7day_block':uncertainties(test['rows'],list(test['summary']['scores'])),'production_changed':False}
    write(OUT/'summary.json',report);print('RESULT',json.dumps({k:v for k,v in report.items() if k not in ('protocol','monthly_test')}),flush=True)
if __name__=='__main__':main()
