"""Chronological candidate selection; test labels never choose parameters."""
import csv,json,sys
from pathlib import Path
from datetime import datetime,timedelta
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
OUT=ROOT/'output/spread-optimization-20261017';OUT.mkdir(exist_ok=True,parents=True)
DATA=ROOT/'output/decision-validation-20261017'
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def bootstrap(rows):
    days=sorted({r['day'] for r in rows});blocks=[[r for r in rows if r['day']==d] for d in days]
    rng=np.random.default_rng(20261017);scores=[]
    for _ in range(2000):
        selected=[r for i in rng.integers(0,len(blocks),len(blocks)) for r in blocks[i]]
        scores.append(float(np.mean([abs(r['baseline']-r['actual'])-abs(r['selected']-r['actual']) for r in selected])))
    return {'improvement_mae_95pct_day_block_interval':np.percentile(scores,[2.5,97.5]).tolist(),'days':len(days)}

def pm():
    report={}; exported=[]
    for lead in (6,12,24):
        station_results=[];test_all=[]
        for station in ('35T','36T'):
            path=DATA/'pm25'/f'chiangmai-air4thai-{station.lower()}-hourly-20260917-20261016.csv'
            series={datetime.fromisoformat(r['datetime_as_published']):float(r['pm25_ug_m3']) for r in csv.DictReader(path.open(encoding='utf-8-sig')) if r['pm25_ug_m3']}
            rows=[]
            for origin in sorted(series):
                valid=origin+timedelta(hours=lead)
                required=[origin-timedelta(hours=h) for h in (0,1,3,6,12,24,48)]
                required+=[valid-timedelta(hours=24)]
                if valid not in series or any(t not in series for t in required):continue
                vals=[series[t] for t in required]
                if not np.isfinite(vals+[series[valid]]).all():continue
                rows.append({'origin':origin,'valid':valid,'x':vals+[np.sin(valid.hour/24*2*np.pi),np.cos(valid.hour/24*2*np.pi)],'y':series[valid]})
            train=[r for r in rows if r['valid']<datetime(2026,9,26)]
            validation=[r for r in rows if r['origin']>=datetime(2026,9,26) and r['valid']<datetime(2026,10,1)]
            test=[r for r in rows if datetime(2026,10,1)<=r['origin']<datetime(2026,10,16)]
            X=np.array([r['x'] for r in train]);Y=np.array([r['y'] for r in train]);mu=X.mean(0);sd=X.std(0);sd[sd==0]=1
            A=np.column_stack([np.ones(len(X)),(X-mu)/sd]);models={};specs={}
            for weight in (0,.25,.5,.75,1):
                models[f'blend_now_weight_{weight}']=lambda x,w=weight:w*x[0]+(1-w)*x[7]
                specs[f'blend_now_weight_{weight}']={'type':'blend','weight_now':weight}
            for alpha in (.1,1,10,100,1000):
                penalty=np.eye(A.shape[1])*alpha;penalty[0,0]=0
                weights=np.linalg.solve(A.T@A+penalty,A.T@Y)
                models[f'ridge_alpha_{alpha}']=lambda x,w=weights:max(0,float(np.r_[1,(np.array(x)-mu)/sd]@w))
                specs[f'ridge_alpha_{alpha}']={'type':'ridge','weights':weights.tolist(),'mean':mu.tolist(),'scale':sd.tolist()}
            validation_mae={name:float(np.mean([abs(fn(r['x'])-r['y']) for r in validation])) for name,fn in models.items()}
            selected=min(validation_mae,key=validation_mae.get)
            exported.append({'station':station,'lead_hours':lead,'selected':selected,'model':specs[selected]})
            baselines=['blend_now_weight_0','blend_now_weight_1'];baseline=min(baselines,key=validation_mae.get)
            testrows=[{'day':str(r['valid'].date()),'station':station,'actual':r['y'],'selected':models[selected](r['x']),
                       'baseline':models[baseline](r['x']),'now':r['x'][0],'previous_day':r['x'][7]} for r in test]
            test_all+=testrows
            station_results.append({'station':station,'train_n':len(train),'validation_n':len(validation),'test_n':len(test),
                                    'selected':selected,'baseline_selected_on_validation':baseline,'validation_mae':validation_mae})
        result={'stations':station_results,'test_pairs':len(test_all),
                'test_mae':{k:float(np.mean([abs(r[k]-r['actual']) for r in test_all])) for k in ('selected','baseline','now','previous_day')},
                **bootstrap(test_all),'rows':test_all}
        report[str(lead)]=result
    save('pm-optimization.json',{'by_lead':report,'production_changed':False,
         'limits':['Recent September/October only, not burning season.','Observation-only forecast, not calibrated CAMS smoke physics.',
                   'Historical delivery latency and hour interval convention unknown.','October data previously inspected; chronological split is not a pristine new test.']})
    (ROOT/'backend/app/data/pm25-station-models.json').write_text(json.dumps({'version':'cme-station-pm-v1',
        'trained_targets_before':'2026-09-26T00:00:00+07:00','selected_targets_before':'2026-10-01T00:00:00+07:00',
        'models':exported,'test':{k:{x:y for x,y in v.items() if x not in ('rows','stations')} for k,v in report.items()}},indent=2),encoding='utf8')
    print('PM',json.dumps({k:{x:y for x,y in v.items() if x not in ('rows','stations')} for k,v in report.items()}),flush=True)

def wind():
    original=json.loads((DATA/'summary.json').read_text(encoding='utf8'))['wind_station']['by_lead']
    results={}
    for lead,block in original.items():
        rows=block['rows'];train=[r for r in rows if r['time']<'2026-03-01'];validation=[r for r in rows if '2026-03-01'<=r['time']<'2026-03-23'];test=[r for r in rows if r['time']>='2026-03-23']
        x=np.array([r['gfs'] for r in train]);y=np.array([r['observed'] for r in train]);coef=np.linalg.lstsq(np.column_stack([np.ones(len(x)),x]),y,rcond=None)[0]
        bias=float(np.median(y-x));models={'raw':lambda r:r['gfs'],'persistence':lambda r:r['persistence'],
            'median_bias':lambda r:max(0,r['gfs']+bias),'linear':lambda r:max(0,float(coef[0]+coef[1]*r['gfs']))}
        val={k:float(np.mean([abs(fn(r)-r['observed']) for r in validation])) for k,fn in models.items()}
        selected=min(val,key=val.get);baseline=min(('raw','persistence'),key=val.get)
        paired=[{'day':r['time'][:10],'actual':r['observed'],'selected':models[selected](r),'baseline':models[baseline](r)} for r in test]
        results[lead]={'selected':selected,'coefficients':coef.tolist(),'median_bias':bias,'validation_mae':val,
            'test_n':len(test),'test_mae':{k:float(np.mean([abs(fn(r)-r['observed']) for r in test])) for k,fn in models.items()},**bootstrap(paired)}
    save('wind-optimization.json',{'by_lead':results,'production_changed':False,'limit':'Airport-specific speed correction; not validated for mountain wind, direction, or primary daily-max weather model.'})
    print('WIND',json.dumps(results),flush=True)

if __name__=='__main__':pm();wind()
