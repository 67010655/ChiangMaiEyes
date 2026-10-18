"""Add positive Himawari proximity evidence to frozen 12h hotspot ranking.

Finite late fusion selected on2025, then evaluated on exactly the old231
common2026origins. No retraining of the frozen53feature model; no fire-front
accuracy or calibrated probability claim.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
import numpy as np,joblib
from scipy.spatial import cKDTree
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
import joint_fire_experiment as j
import probe_himawari_fire_sources as h

OUT=c.OUT/'priority-himawari'
CHOICES={'parent':(0,1000)}
CHOICES.update({f'hima_w{weight}_r{radius}':(weight,radius) for weight in (.05,.2,.5,1.) for radius in (1000,3000,5000)})


def origins(year):
    path=j.OUT/('final-common-test-rows.json' if year==2026 else 'spatial-pm-comparison/results-2025.json')
    body=c.read(path);rows=body if isinstance(body,list) else body['rows']
    return [datetime.fromisoformat(r['issued_at']) for r in rows]


def download_origin(origin):
    stamps=[origin-timedelta(hours=hours) for hours in (3,6)]
    return [h.fetch_frame(stamp,c.OUT/'himawari-bank') for stamp in stamps]


def origin_features(origin,grid,model,spec):
    folder=OUT/f'inputs-{origin.year}';folder.mkdir(exist_ok=True)
    path=folder/(origin.strftime('%Y%m%dT%H')+'.npz');receipt=path.with_suffix('.json')
    if path.exists() and receipt.exists():return dict(np.load(path)),c.read(receipt)
    data=j.load(origin.year,grid);prepared,reason=j.prepare(data,origin,grid);assert prepared is not None,reason
    X=prepared[0];assert spec['feature_pipeline']=='joint53'
    probability=model.predict_proba(X[:,spec['feature_columns']])[:,1]
    frames=download_origin(origin)
    events=[event for _,rows in frames for event in rows if event['quality_eligible']]
    if events:
        assert all(datetime.fromisoformat(e['observation_time_utc'])<=origin-timedelta(hours=3) for e in events)
        xy=np.column_stack(j.projection.transform([e['longitude'] for e in events],[e['latitude'] for e in events]));distance,nearest=cKDTree(xy).query(grid['xy'])
        age=np.array([(origin-datetime.fromisoformat(e['observation_time_utc'])).total_seconds()/3600 for e in events])[nearest]
    else:distance=np.full(len(probability),np.inf);age=np.zeros(len(probability))
    features={'parent_score':probability,'hima_distance_m':distance,'hima_age_hours':age}
    np.savez_compressed(path,**features)
    rec={'as_of':origin.isoformat(),'frames':[r for r,_ in frames],'quality_eligible_events':len(events),'npz_sha256':c.sha(path),
         'parent_model_sha256':spec['model_sha256'],'future_labels_read_for_features':False,'missing_or_empty':'No additional evidence; fall back to parent ranking. Absence never declares no fire.'}
    c.write(receipt,rec);return features,rec


def rank_values(features,choice):
    weight,radius=CHOICES[choice];base=features['parent_score'];order=np.lexsort((np.arange(len(base)),-base))
    rank=np.empty(len(base));rank[order]=1-np.arange(len(base))/len(base)
    return rank+weight*np.exp(-features['hima_distance_m']/radius-features['hima_age_hours']/12)


def top_indices(values,count):
    # Full stable ordering gives reproducible cell-ID tie handling.
    return np.lexsort((np.arange(len(values)),-values))[:count]


def aggregate(rows,names):
    denominator=sum(row['target_cells_all'] for row in rows)
    return {name:{'hits':sum(row['scores'][name]['250.0'] for row in rows),'target_cells_all':denominator,
       'coverage_pct':100*sum(row['scores'][name]['250.0'] for row in rows)/denominator,
       'budgets':{str(area):{'hits':sum(row['scores'][name][str(area)] for row in rows),'coverage_pct':100*sum(row['scores'][name][str(area)] for row in rows)/denominator} for area in (125.,250.,500.)}} for name in names}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('prefetch','selection','test'),required=True);args=parser.parse_args();OUT.mkdir(exist_ok=True)
    protocol={'target':'Next12hVIIRS500mcells, not perimeter; identical parent common origins, budget250km2.',
      'parent':'Frozen2024trained2025selected hotspot_wind_pm large model, unmodified.',
      'choices':CHOICES,'selection':'2025pooledcoverageat250km2, tie parent then smallerweight then radius. Freeze before2026.',
      'himawari':'Two nominal UTC JAXA frames fromissue-3h/-6h; rel3/5nonvolcanic only. NoFRP because unitsunverified. Availabilitydelayassumed3h, no cloudnegativeclaims.',
      'scope':'Retrospective previouslyinspectedyears; no pristine prospective holdout; no deploy.'}
    c.write(OUT/'protocol.json',protocol)
    if args.phase=='prefetch':
        work=[t for year in (2025,2026) for t in origins(year)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for i,result in enumerate(pool.map(download_origin,work)):
                if i%40==0:print('JAXA_PREFETCH',i+1,'/',len(work),flush=True)
        return
    selected='parent' if args.phase=='selection' else c.read(OUT/'selection.json')['selected']
    if args.phase=='test':assert c.sha(OUT/'selection.json')==c.read(OUT/'frozen-selection.json')['selection_sha256']
    names=list(CHOICES) if args.phase=='selection' else list(dict.fromkeys(['parent',selected]))
    spec=c.read(j.OUT/'final-candidate/feature-contract.json');assert c.sha(j.OUT/'final-candidate/model.joblib')==spec['model_sha256']
    model=joblib.load(j.OUT/'final-candidate/model.joblib');grid=j.build_grid();year=2025 if args.phase=='selection' else 2026;data=j.load(year,grid)
    parent_rows=c.read(j.OUT/('final-common-test-rows.json' if year==2026 else 'spatial-pm-comparison/results-2025.json'))
    parent_rows=parent_rows if isinstance(parent_rows,list) else parent_rows['rows'];parents={r['issued_at']:r for r in parent_rows}
    rows=[]
    for index,origin in enumerate(origins(year)):
        features,receipt=origin_features(origin,grid,model,spec)
        y,meta=j.labels(data,origin,grid);scores={}
        for name in names:
            top=top_indices(rank_values(features,name),2000)
            scores[name]={str(area):int(y[top[:round(area/.25)]].sum()) for area in (125.,250.,500.)}
        expected=parents[origin.isoformat()]['scores'][spec['model_selected_on2025']]['250.0']['hits']
        assert scores['parent']['250.0']==expected,'Parent parity failure'
        rows.append({'issued_at':origin.isoformat(),**meta,'scores':scores,'hima_positive_events':receipt['quality_eligible_events'],
                     'retrieved_frames':sum(r['status']=='ok' for r in receipt['frames'])})
        if index%30==0:
            print('PRIORITY_EVAL',year,index+1,flush=True);c.write(OUT/(args.phase+'-progress.json'),{'rows':rows})
    summary=aggregate(rows,names);result={'rows':rows,'summary':summary,'issues':len(rows)}
    if args.phase=='selection':
        ranking=sorted(names,key=lambda name:(-summary[name]['hits'],name!='parent',CHOICES[name][0],CHOICES[name][1]));result.update(selected=ranking[0],ranking=ranking)
        c.write(OUT/'selection.json',result);c.write(OUT/'frozen-selection.json',{'selection_sha256':c.sha(OUT/'selection.json'),'2026_used_for_selection':False})
        print('PRIORITY_SELECTED',ranking[0],summary[ranking[0]],flush=True)
    else:
        result['selected_on2025']=selected
        c.write(OUT/'test-results.json',result);print('PRIORITY_FINAL',selected,summary,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
