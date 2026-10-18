"""Replay the production build function, using archived GFS previous-day fields."""
import json
import sys
from pathlib import Path
from datetime import timedelta
import httpx
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from app.live_spread import build, footprint, stamp

OUT = ROOT/'output/live-spread-backtest-20261017'
OUT.mkdir(parents=True, exist_ok=True)
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')

def main():
    cases=json.loads((ROOT/'backend/app/data/dashboard-validation-2026.json').read_text(encoding='utf8'))['fire_followup']['cases']
    projection=Transformer.from_crs(4326,32647,always_xy=True).transform
    rows=[]
    for case in cases:
        start=stamp(case['as_of']); points=case['initial']
        positions=list(dict.fromkeys((p['latitude'],p['longitude']) for p in points))
        path=OUT/(case['id']+'-gfs.json')
        if path.exists(): raw=json.loads(path.read_text())
        else:
            r=httpx.get('https://previous-runs-api.open-meteo.com/v1/forecast', params={
                'latitude':','.join(str(p[0]) for p in positions),'longitude':','.join(str(p[1]) for p in positions),
                'hourly':'wind_speed_10m_previous_day1,wind_direction_10m_previous_day1',
                'models':'gfs_seamless','wind_speed_unit':'ms','timezone':'UTC',
                'start_date':str(start.date()),'end_date':str((start+timedelta(days=1)).date())},timeout=60)
            r.raise_for_status(); raw=r.json(); write(path,raw)
        raw=raw if isinstance(raw,list) else [raw]
        weather={p:{**w,'hourly':{k.removesuffix('_previous_day1'):v for k,v in w['hourly'].items()}} for p,w in zip(positions,raw)}
        result=build(points,weather,as_of=start,source_mode='retrospective_previous_day1_reconstruction',source_retrieved_at=None)
        write(OUT/(case['id']+'-forecast.json'),result)
        baseline=unary_union([Point(*projection(p['longitude'],p['latitude'])) for p in points])
        domain=Point(*projection(points[0]['longitude'],points[0]['latitude'])).buffer(5000)
        hits={0:0,375:0}; basehits={0:0,375:0}; last=0
        for p in case['later']:
            elapsed=(stamp(p['detected_at'])-start).total_seconds()/60; last=max(last,elapsed)
            forecast=unary_union([transform(projection,shape(footprint(i['point'],i['steps'],elapsed))) for i in result['inputs']])
            observed=Point(*projection(p['longitude'],p['latitude']))
            for tolerance in hits:
                hits[tolerance]+=int((forecast.buffer(tolerance) if tolerance else forecast).covers(observed))
                basehits[tolerance]+=int((baseline.buffer(tolerance) if tolerance else baseline).covers(observed))
        final=unary_union([transform(projection,shape(footprint(i['point'],i['steps'],last))) for i in result['inputs']])
        row={'case':case['id'],'initial':len(points),'used':result['used_points'],'later':len(case['later']),
             'covered':hits,'stationary_covered':basehits,
             'envelope_375m_ha':final.buffer(375).intersection(domain).area/10000,
             'stationary_375m_ha':baseline.buffer(375).intersection(domain).area/10000}
        rows.append(row); print(json.dumps(row),flush=True)
    summary={'cases':rows,'total_later':sum(r['later'] for r in rows),
             'covered':{str(t):sum(r['covered'][t] for r in rows) for t in (0,375)},
             'stationary_covered':{str(t):sum(r['stationary_covered'][t] for r in rows) for t in (0,375)},
             'envelope_375m_ha':sum(r['envelope_375m_ha'] for r in rows),
             'stationary_375m_ha':sum(r['stationary_375m_ha'] for r in rows),
             'limits':['Selected peak cases, not independent incident labels or full-season accuracy.',
                       'Previous-day1 stitched forecast fields, not verified single issue runs.',
                       'Hotspot acquisition time treated as available time; delivery lag unknown.',
                       'Positive-point coverage only; absence of a detection is not absence of fire.',
                       '375 m is a sensitivity buffer, not calibrated satellite geolocation error.',
                       'Fixed unmeasured fuel; approximately 110 m terrain fixed at each origin.']}
    write(OUT/'summary.json',summary)
    print(json.dumps(summary),flush=True)

if __name__=='__main__': main()
