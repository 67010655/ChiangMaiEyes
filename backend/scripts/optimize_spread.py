"""Predeclared chronological search; no production parameter changes.

Initialisation uses fixed daily 02:00 ICT, the highest-FRP received point in
the preceding six hours, and at most 50 past-24h origins within 5 km. Labels
never select the centre. Acquisition time is an availability proxy only.
"""
import argparse, hashlib, json, math, sys, time, warnings
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
import httpx
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app import live_spread as engine
from app.forecast_terrain import at as terrain_at
from app.spread_scenario import Fuel,Wind,rate_of_spread
OUT=ROOT/'output/spread-optimization-20261017/quality-filtered';OUT.mkdir(exist_ok=True,parents=True)
ICT=timezone(timedelta(hours=7));project=Transformer.from_crs(4326,32647,always_xy=True).transform
warnings.filterwarnings('ignore',category=DeprecationWarning)
def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def prepare():
    points=[p for p in read(ROOT/'output/hindcast-2026/firms-points.json') if p.get('confidence')!='l']
    times=np.array([engine.stamp(p['detected_at']).timestamp() for p in points])
    xy=np.array([project(p['longitude'],p['latitude']) for p in points])
    cases=[]
    for day in range(120):
        start=datetime(2026,1,1,2,tzinfo=ICT)+timedelta(days=day); ts=start.timestamp()
        known=np.where((times<=ts)&(times>=ts-6*3600))[0]
        if not len(known):continue
        centre=max(known,key=lambda i:(points[i].get('frp') or 0,times[i],-i))
        near=np.linalg.norm(xy-xy[centre],axis=1)<=5000
        initial=np.where(near&(times<=ts)&(times>=ts-24*3600))[0]
        initial=sorted(initial,key=lambda i:times[i],reverse=True)[:50]
        later=np.where(near&(times>ts)&(times<=ts+6*3600))[0]
        cases.append({'id':str(start.date()),'as_of':start.isoformat(),'centre':points[centre],
                      'initial':[points[i] for i in initial],'later':[points[i] for i in later]})
    write(OUT/'cases.json',cases)
    manifest={'initialization':'Fixed 02:00 ICT; largest past-six-hour FRP; 5 km; past24h max50; next6h labels; low-confidence points excluded',
      'split':{'train':'2026-01-01/2026-02-28','validation':'2026-03-01/2026-03-22','test':'2026-03-23/2026-04-30'},
      'candidates':[dict(moisture=m,wind_factor=w,slope_factor=s) for m,w,s in product((5,8,11),(.1,.2,.4),(0,.5,1))],
      'objective':'Mean case coverage gain versus isotropic no-growth origins expanded to exactly the same area, at each observed time.',
      'constraint':'Mean case envelope area <=2.2 times stationary375m area, same acquisition-time evaluation points.',
      'selection':'Train constrained top five by objective; validation selects one once. Test scored after selection.',
      'known_overlap':'Eight previously inspected peak cases fall in test dates; this is expanded retrospective temporal validation, not pristine unseen test.',
      'cases':len(cases),'cases_with_followup':sum(bool(c['later']) for c in cases)}
    write(OUT/'protocol.json',manifest)
    for case in cases:
        if not case['later']:continue # unscorable positive-only cases remain in manifest
        path=OUT/(case['id']+'-gfs.json')
        if path.exists():continue
        start=engine.stamp(case['as_of']); pos=list(dict.fromkeys((p['latitude'],p['longitude']) for p in case['initial']))
        for attempt in range(3):
            try:
                r=httpx.get('https://previous-runs-api.open-meteo.com/v1/forecast',params={
                    'latitude':','.join(str(p[0]) for p in pos),'longitude':','.join(str(p[1]) for p in pos),
                    'hourly':'wind_speed_10m_previous_day1,wind_direction_10m_previous_day1','models':'gfs_seamless',
                    'wind_speed_unit':'ms','timezone':'UTC','start_date':str(start.date()),'end_date':str((start+timedelta(days=1)).date())},timeout=45)
                r.raise_for_status();write(path,r.json());time.sleep(max(1,len(pos)*.15));break
            except httpx.HTTPError as error:
                if attempt==2:raise
                pause=60 if isinstance(error,httpx.HTTPStatusError) and error.response.status_code==429 else 5
                print('provider backoff seconds',pause,flush=True);time.sleep(pause)
        print('download',case['id'],len(pos),len(case['later']),flush=True)
    print('prepared',manifest['cases'],manifest['cases_with_followup'],flush=True)

def candidate_inputs(case,config):
    raw=read(OUT/(case['id']+'-gfs.json'));raw=raw if isinstance(raw,list) else [raw]
    pos=list(dict.fromkeys((p['latitude'],p['longitude']) for p in case['initial']))
    weather={p:{**w,'hourly':{k.removesuffix('_previous_day1'):v for k,v in w['hourly'].items()}} for p,w in zip(pos,raw)}
    start=engine.stamp(case['as_of']);inputs=[]
    evidence={'basis':'assumed','source':'Predeclared retrospective candidate; not measured fuel','observed_at':start}
    fuel=Fuel(**{**engine.FUEL,'moisture_pct':config['moisture']},evidence=evidence)
    for p in case['initial']:
        key=(p['latitude'],p['longitude']);terrain=terrain_at(*key)
        if terrain is None:continue
        try:steps=engine.segments(p,weather[key],start,terrain)
        except (KeyError,ValueError):continue
        for step in steps:
            wind=Wind(midflame_mps=step['wind_10m_mps']*config['wind_factor'],from_deg=step['wind_from_deg']%360,evidence=evidence)
            step['rates']=rate_of_spread(fuel,wind,terrain['slope_deg']*config['slope_factor'],terrain['upslope_to_deg'])
        inputs.append((p,steps))
    return inputs

def evaluate(case,config):
    inputs=candidate_inputs(case,config)
    if len(inputs)!=len(case['initial']):return {'id':case['id'],'status':'incomplete_inputs'}
    start=engine.stamp(case['as_of']);centre=case['centre']
    domain=Point(*project(centre['longitude'],centre['latitude'])).buffer(5000)
    origins=unary_union([Point(*project(p['longitude'],p['latitude'])) for p in case['initial']])
    base=origins.buffer(375).intersection(domain); bytime={}
    for p in case['later']:
        minute=(engine.stamp(p['detected_at'])-start).total_seconds()/60
        bytime.setdefault(minute,[]).append(Point(*project(p['longitude'],p['latitude'])))
    hits=matched=stationary=rawhits=0; areas=[]
    for minute,observed in bytime.items():
        raw=unary_union([transform(project,shape(engine.footprint(p,steps,minute))) for p,steps in inputs]).intersection(domain)
        forecast=raw.buffer(375).intersection(domain);area=forecast.area
        low,high=0.,10000.
        for _ in range(15):
            mid=(low+high)/2
            if origins.buffer(mid).intersection(domain).area<area:low=mid
            else:high=mid
        equal=origins.buffer((low+high)/2).intersection(domain)
        hits+=sum(forecast.covers(p) for p in observed);matched+=sum(equal.covers(p) for p in observed)
        stationary+=sum(base.covers(p) for p in observed);rawhits+=sum(raw.covers(p) for p in observed)
        areas.append(area/base.area)
    total=len(case['later'])
    return {'id':case['id'],'status':'scored','points':total,'covered':hits,'equal_area_covered':matched,
            'stationary375_covered':stationary,'raw_covered':rawhits,'coverage':hits/total,
            'gain':(hits-matched)/total,'area_ratio':sum(areas)/len(areas)}

def aggregate(rows):
    rows=[r for r in rows if r['status']=='scored']
    return {'cases':len(rows),'points':sum(r['points'] for r in rows),
        **{k:sum(r[k] for r in rows) for k in ('covered','equal_area_covered','stationary375_covered','raw_covered')},
        **{k:sum(r[k] for r in rows)/len(rows) if rows else None for k in ('coverage','gain','area_ratio')}}

def search():
    cases=[c for c in read(OUT/'cases.json') if c['later']]
    protocol=read(OUT/'protocol.json');configs=protocol['candidates'];results=[]
    development=[c for c in cases if c['id']<='2026-03-22']
    for index,config in enumerate(configs):
        path=OUT/f'candidate-{index:02d}.json'
        if path.exists():row=read(path)
        else:
            scored=[evaluate(c,config) for c in development]
            row={'index':index,'config':config,'rows':scored,
                 'train':aggregate([r for r in scored if r['id']<'2026-03-01']),
                 'validation':aggregate([r for r in scored if r['id']>='2026-03-01'])}
            write(path,row)
        results.append(row);print(index,config,row['train'],row['validation'],flush=True)
    eligible=[r for r in results if r['train']['area_ratio']<=2.2]
    shortlist=sorted(eligible,key=lambda r:(r['train']['gain'],-r['train']['area_ratio']),reverse=True)[:5]
    eligible_validation=[r for r in shortlist if r['validation']['area_ratio']<=2.2]
    selected=max(eligible_validation or shortlist,key=lambda r:(r['validation']['gain'],-r['validation']['area_ratio']))
    # Persist selection before ever evaluating test candidates.
    selection={'selected_index':selected['index'],'config':selected['config'],'shortlist':[r['index'] for r in shortlist]}
    write(OUT/'selection.json',selection)
    test=[c for c in cases if c['id']>'2026-03-22'];baseline={'moisture':8,'wind_factor':.2,'slope_factor':1}
    selected_rows=[evaluate(c,selected['config']) for c in test]
    current_rows=[evaluate(c,baseline) for c in test]
    report={'protocol':protocol,'selection':selection,'development':results,'test_selected':aggregate(selected_rows),
            'test_current':aggregate(current_rows),'test_selected_rows':selected_rows,'test_current_rows':current_rows,
            'production_changed':False}
    write(OUT/'summary.json',report);print('TEST',json.dumps({k:v for k,v in report.items() if k.startswith('test_') and not k.endswith('rows')}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','search']);args=parser.parse_args()
    prepare() if args.mode=='prepare' else search()
