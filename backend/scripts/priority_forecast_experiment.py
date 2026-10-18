"""A separately testable next-12h *satellite detection* prioritisation task.

Train2024, select2025, test2026; fixed08/20ICT issues and3h source latency.
This predicts observations at500m support, not an exact active-fire perimeter.
"""
import argparse,hashlib,json,math,sys,time,warnings
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely import contains_xy
from pyproj import Transformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import joblib

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.forecast_terrain import dataset as terrain_dataset
from app.grid_spread import landcover_dataset
from app.providers.hotspot_provider import _province_ring
OUT=ROOT/'output/priority-forecast-20261017';OUT.mkdir(parents=True,exist_ok=True)
ICT=timezone(timedelta(hours=7));UTC=timezone.utc;RES=500.;BUDGETS=(125.,250.,500.)
projection=Transformer.from_crs(4326,32647,always_xy=True);inverse=Transformer.from_crs(32647,4326,always_xy=True)
def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,body):path.write_text(json.dumps(body,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def build_grid():
    path=OUT/'grid.npz'
    if path.exists():return dict(np.load(path))
    ring=_province_ring();polygon=Polygon(ring);xx,yy=projection.transform(*zip(*ring))
    west=math.floor(min(xx)/RES)*RES;north=math.ceil(max(yy)/RES)*RES
    width=math.ceil((max(xx)-west)/RES);height=math.ceil((north-min(yy))/RES)
    rr,cc=np.meshgrid(np.arange(height),np.arange(width),indexing='ij')
    x=west+(cc.ravel()+.5)*RES;y=north-(rr.ravel()+.5)*RES;lon,lat=inverse.transform(x,y)
    mask=contains_xy(polygon,lon,lat)
    meta,elevation=terrain_dataset();_,landcover=landcover_dataset();w=meta['width']
    col=np.floor((lon-meta['west'])/meta['step_degrees']).astype(int);row=np.floor((meta['north']-lat)/meta['step_degrees']).astype(int)
    mask&=(col>=1)&(col<w-1)&(row>=1)&(row<meta['height']-1)
    z=np.asarray(elevation);land=np.frombuffer(landcover,dtype='uint8');index=np.clip(row*w+col,0,len(z)-1)
    cls=land[index];mask&=np.isin(cls,(10,20,30,40,90,95,100))&(z[index]!=meta['nodata'])
    fullindex=np.flatnonzero(mask);row=row[mask];col=col[mask];idx=row*w+col
    dx=math.radians(meta['step_degrees'])*6371008.8*np.cos(np.radians(lat[mask]));dy=math.radians(meta['step_degrees'])*6371008.8
    east=(z[idx-w+1]+2*z[idx+1]+z[idx+w+1]-z[idx-w-1]-2*z[idx-1]-z[idx+w-1])/(8*dx)
    up=(z[idx-w-1]+2*z[idx-w]+z[idx-w+1]-z[idx+w-1]-2*z[idx+w]-z[idx+w+1])/(8*dy)
    slope=np.degrees(np.arctan(np.hypot(east,up)))
    static=np.column_stack([(lon[mask]-99),lat[mask]-19,z[idx]/1000,slope/45,*[(cls[mask]==v).astype(float) for v in (10,20,30,40)] ]).astype('float32')
    lookup=np.full(width*height,-1,dtype='int32');lookup[fullindex]=np.arange(len(fullindex))
    result={'xy':np.column_stack([x[mask],y[mask]]),'lon':lon[mask],'lat':lat[mask],'static':static,'fullindex':fullindex,
        'lookup':lookup,'width':np.array(width),'height':np.array(height),'west':np.array(west),'north':np.array(north)}
    np.savez_compressed(path,**result);print('candidate_grid_cells',len(fullindex),'area_km2',len(fullindex)*.25,flush=True);return result

def load_year(year):
    folder=ROOT/'output'/f'hindcast-{year}';rows=[p for p in read(folder/'firms-points.json') if p.get('confidence')!='l']
    rows.sort(key=lambda p:p['detected_at']);times=np.array([datetime.fromisoformat(p['detected_at']).timestamp() for p in rows]);xy=np.column_stack(projection.transform([p['longitude'] for p in rows],[p['latitude'] for p in rows]))
    frp=np.array([max(0,p.get('frp') or 0) for p in rows]);weather=read(OUT/f'gfs-weather-{year}.json')['hourly']
    wh={datetime.fromisoformat(t).replace(tzinfo=UTC).timestamp():i for i,t in enumerate(weather['time'])}
    return {'times':times,'xy':xy,'frp':frp,'weather':weather,'weather_index':wh}

def issues(year):
    first=datetime(year,1,2,8,tzinfo=ICT);end=datetime(year,5,1,tzinfo=ICT);current=first
    while current+timedelta(hours=12)<=end:
        yield current
        current+=timedelta(hours=12)

def labels(data,origin,grid):
    t=origin.timestamp();a=np.searchsorted(data['times'],t);b=np.searchsorted(data['times'],t+12*3600)
    xy=data['xy'][a:b];width=int(grid['width']);height=int(grid['height'])
    col=np.floor((xy[:,0]-float(grid['west']))/RES).astype(int);row=np.floor((float(grid['north'])-xy[:,1])/RES).astype(int)
    inrange=(col>=0)&(col<width)&(row>=0)&(row<height)
    full=np.unique(row[inrange]*width+col[inrange]);indices=grid['lookup'][full];assigned=np.unique(indices[indices>=0])
    result=np.zeros(len(grid['xy']),dtype='uint8');result[assigned]=1
    return result,{'detections':int(b-a),'target_cells_all':int(len(full)),'target_cells_in_mask':int(len(assigned)),'target_cells_outside_mask':int((indices<0).sum())}

def features(data,origin,grid,latency=3):
    t=origin.timestamp();cutoff=t-latency*3600;times=data['times'];end=np.searchsorted(times,cutoff,side='right');a=np.searchsorted(times,cutoff-24*3600);week=np.searchsorted(times,cutoff-7*24*3600);month=np.searchsorted(times,cutoff-30*24*3600)
    points=grid['xy'];n=len(points);parts=[grid['static']];bases={}
    for name,start in (('day',a),('week',week),('month',month)):
        xy=data['xy'][start:end]
        if len(xy):
            tree=cKDTree(xy);distance,index=tree.query(points,k=1,workers=1);count=tree.query_ball_point(points,1500,return_length=True,workers=1)
        else:distance=np.full(n,300000.);index=np.zeros(n,dtype=int);count=np.zeros(n)
        parts.extend([np.log1p(np.minimum(distance,300000))[:,None],np.log1p(count)[:,None]])
        bases[name]=-distance
        if name=='day':
            age=(t-times[start:end][index])/3600 if len(xy) else np.full(n,48.)
            power=data['frp'][start:end][index] if len(xy) else np.zeros(n)
            parts.extend([np.minimum(age,48)[:,None]/24,np.log1p(power)[:,None]])
            bases['recency_kernel']=np.exp(-distance/1500)*np.exp(-age/12)*(1+np.log1p(power))
    hourly=data['weather'];mapping_=data['weather_index'];weather=[]
    fields=('temperature_2m','relative_humidity_2m','precipitation','wind_speed_10m','shortwave_radiation')
    for field in fields:
        vals=[]
        for hour in range(13):
            index=mapping_.get(t+hour*3600)
            value=hourly[field+'_previous_day1'][index] if index is not None else None
            if value is None:return None,None
            vals.append(value)
        weather.extend([float(np.mean(vals)),float(np.max(vals))])
    doy=origin.timetuple().tm_yday
    temporal=[math.sin(2*math.pi*doy/366),math.cos(2*math.pi*doy/366),float(origin.hour==8)]
    parts.append(np.tile(np.array(weather+temporal,dtype='float32'),(n,1)))
    return np.column_stack(parts).astype('float32'),bases

def training(grid):
    path=OUT/'training2024.npz'
    if path.exists():d=np.load(path);return d['X'],d['y']
    data=load_year(2024);rng=np.random.default_rng(20261017);xs=[];ys=[]
    for origin in issues(2024):
        X,_=features(data,origin,grid)
        if X is None:continue
        y,meta=labels(data,origin,grid);positive=np.flatnonzero(y);negative=np.flatnonzero(y==0)
        sample=np.r_[positive,rng.choice(negative,min(1024,len(negative)),replace=False)]
        xs.append(X[sample]);ys.append(y[sample])
    X=np.vstack(xs);y=np.concatenate(ys);np.savez_compressed(path,X=X,y=y);print('training',X.shape,'positives',int(y.sum()),flush=True);return X,y

def score(score,y,meta,budget):
    k=min(len(score),round(budget/.25));order=np.lexsort((np.arange(len(score)),-np.nan_to_num(np.asarray(score,dtype='float64'),nan=-1e100)))[:k]
    return int(y[order].sum())

def evaluate(year,grid,models,latency=3):
    data=load_year(year);rows=[]
    for count,origin in enumerate(issues(year)):
        X,bases=features(data,origin,grid,latency)
        if X is None:continue
        y,meta=labels(data,origin,grid);scores={**bases,**{name:model.predict_proba(X)[:,1] for name,model in models.items()}}
        row={'issued_at':origin.isoformat(),**meta,'hits':{name:{str(b):score(values,y,meta,b) for b in BUDGETS} for name,values in scores.items()}}
        rows.append(row)
        if count%40==0:print('evaluate',year,latency,count,'targets',meta['target_cells_all'],flush=True)
    sums={'issues':len(rows),'target_cells_all':sum(r['target_cells_all'] for r in rows),'target_cells_in_mask':sum(r['target_cells_in_mask'] for r in rows),
       'detections':sum(r['detections'] for r in rows),'hits':{name:{str(b):sum(r['hits'][name][str(b)] for r in rows) for b in BUDGETS} for name in (list(rows[0]['hits']) if rows else [])}}
    return {'year':year,'latency_hours':latency,'summary':sums,'rows':rows}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sensitivity',action='store_true');args=parser.parse_args()
    grid=build_grid();protocol={'target':'At least one subsequent nominal/high-confidence VIIRS detection in a500m cell during next12h; not burned perimeter or proof of fire absence.',
      'train_year':2024,'selection_year':2025,'test_year':2026,'season':'Jan-Apr','issue_times_ict':[8,20],'source_latency_hours':3,
      'primary_alert_area_km2':250,'sensitivity_alert_area_km2':list(BUDGETS),'grid_cells':len(grid['xy']),
      'selection':'Select highest pooled target-cell coverage at250km2 on2025 only; tie preferring simpler baseline.',
      'weather':'province-point GFS stitched previous-day1 forecast for0..12h targets, available before issue by construction but not verified single runs.',
      'limits':['Satellite observation outcome only; cloud/overpass/industrial heat affect labels.','SP acquisition time plus fixed3h availability proxy; not verified as-issued NRT archive.',
                '2026 previously inspected for other models; this is retrospective cross-year validation.','500m grid and2021 land-cover mask; targets outside mask count as misses.',
                'Sampled training negatives; learned scores are rankings, not calibrated wildfire probabilities.']}
    write(OUT/'protocol.json',protocol)
    X,y=training(grid);models={
      'logistic':make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=500,class_weight='balanced',random_state=20261017)),
      'boost7':HistGradientBoostingClassifier(max_iter=60,max_leaf_nodes=7,learning_rate=.08,min_samples_leaf=30,l2_regularization=10,random_state=20261017),
      'boost15':HistGradientBoostingClassifier(max_iter=60,max_leaf_nodes=15,learning_rate=.08,min_samples_leaf=30,l2_regularization=10,random_state=20261017)}
    for name,model in models.items():
        file=OUT/(name+'.joblib')
        if file.exists():models[name]=joblib.load(file)
        else:model.fit(X,y);joblib.dump(model,file)
        print('fit',name,flush=True)
    validation_path=OUT/'validation2025.json'
    validation=read(validation_path) if validation_path.exists() else evaluate(2025,grid,models)
    write(validation_path,validation);primary='250.0';ranking=sorted(validation['summary']['hits'],key=lambda n:validation['summary']['hits'][n][primary],reverse=True)
    selected=ranking[0];strongest_baseline=max(('day','week','month','recency_kernel'),key=lambda n:validation['summary']['hits'][n][primary])
    write(OUT/'selection.json',{'selected':selected,'strongest_baseline_selected_on2025':strongest_baseline,'ranking2025':ranking})
    # Only one selected candidate proceeds to2026. No new tuning on2026 labels.
    selected_models={selected:models[selected]} if selected in models else {}
    test=evaluate(2026,grid,selected_models);write(OUT/'test2026.json',test)
    report={'protocol':protocol,'selected':selected,'strongest_baseline':strongest_baseline,'validation':validation['summary'],'test':test['summary'],'production_changed':False}
    if args.sensitivity:
        report['latency_sensitivity']={str(h):evaluate(2026,grid,selected_models,h)['summary'] for h in (0,1)}
    write(OUT/'summary.json',report);print('RESULT',json.dumps(report),flush=True)

if __name__=='__main__':main()
