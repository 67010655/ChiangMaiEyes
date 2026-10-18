"""Reproducible conditional spread from received hotspots and hourly GFS.

Reuses the existing Rothermel rates. Time-varying homogeneous wavelets are
combined by their support directions (Minkowski sum). Terrain is sampled at
each origin, not propagated through a heterogeneous fuel/terrain grid.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from app.config import Settings, get_settings
from app.forecast_terrain import at as terrain_at, dataset
from app.spread_scenario import Fuel, Wind, rate_of_spread, destination

VERSION = 'cme-multi-origin-hourly-wavelet-v1'
MAX_POINTS = 50
FUEL = {'load_kg_m2': .16600253963702372, 'depth_m': .3048, 'savr_per_m': 11482.939632545931,
        'moisture_pct': 8, 'extinction_moisture_pct': 12}
WIND_FACTOR = .2
router = APIRouter(prefix='/api/spread', tags=['Conditional live spread'])
_lock = Lock()
_cache = None


def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None: raise ValueError('Timezone required')
    return dt.astimezone(timezone.utc)


def segments(point, weather, start, terrain):
    evidence = {'basis': 'reference', 'source': 'USFS FM1 example; unmeasured local fuel, fixed moisture 8 percent', 'observed_at': start}
    fuel = Fuel(**FUEL, evidence=evidence)
    hourly = weather['hourly']
    lookup = {stamp(t if t.endswith('Z') or '+' in t else t+'+00:00'):(s,d)
              for t,s,d in zip(hourly['time'],hourly['wind_speed_10m'],hourly['wind_direction_10m'])}
    cursor = start; end = start + timedelta(hours=6); out = []
    while cursor < end:
        hour = cursor.replace(minute=0, second=0, microsecond=0)
        stop = min(end, hour+timedelta(hours=1)); speed, direction = lookup.get(hour, (None,None))
        if speed is None or direction is None or not math.isfinite(speed) or not math.isfinite(direction) or speed < 0 or not 0 <= direction <= 360:
            raise ValueError('Missing or invalid hourly wind')
        wind = Wind(midflame_mps=speed*WIND_FACTOR, from_deg=direction % 360,
                    evidence={'basis':'assumed','source':'GFS 10 m wind multiplied by fixed experimental factor 0.2','observed_at':start})
        if terrain['slope_deg'] > 60: raise ValueError('Slope beyond engine input range')
        rates = rate_of_spread(fuel, wind, terrain['slope_deg'], terrain['upslope_to_deg'])
        out.append({'from_minute': (cursor-start).total_seconds()/60, 'to_minute':(stop-start).total_seconds()/60,
                    'wind_10m_mps':speed, 'wind_from_deg':direction, 'rates':rates})
        cursor = stop
    return out


def footprint(point, steps, minutes, vertices=48):
    """Sum ellipse support points; constant winds reproduce the original ellipse."""
    points = []
    for n in range(vertices):
        theta = 2*math.pi*n/vertices; nx,ny = math.sin(theta),math.cos(theta); x=y=0.0
        for step in steps:
            dt = max(0, min(minutes,step['to_minute'])-step['from_minute'])
            if not dt: continue
            rate=step['rates']; a=(rate['head_m_min']+rate['backing_m_min'])*dt/2
            if not a: continue
            b=a/rate['length_width_ratio']; shift=a-rate['backing_m_min']*dt
            angle=math.radians(rate['heading_to_deg'] or 0); dx,dy=math.sin(angle),math.cos(angle)
            ex,ey=dy,-dx; nd=nx*dx+ny*dy; ne=nx*ex+ny*ey
            denom=math.hypot(a*nd,b*ne)
            x+=shift*dx+(a*a*nd*dx+b*b*ne*ex)/denom
            y+=shift*dy+(a*a*nd*dy+b*b*ne*ey)/denom
        points.append(destination(point['latitude'],point['longitude'],x,y))
    return {'type':'Polygon','coordinates':[points+[points[0]]]}


def build(points, weather, *, as_of, source_mode, source_retrieved_at):
    """Pure production calculation, also invoked unchanged by the backtest."""
    inputs=[]; excluded=[]; seen=set(); eligible=[]
    for p in points:
        at=stamp(p['detected_at'])
        if not as_of-timedelta(hours=24) <= at <= as_of or p.get('confidence_level') == 'low': continue
        key=(p['latitude'],p['longitude'],at)
        if key not in seen: eligible.append(p);seen.add(key)
    eligible.sort(key=lambda p:stamp(p['detected_at']),reverse=True)
    selected=eligible[:MAX_POINTS]
    for p in selected:
        key=(p['latitude'],p['longitude'])
        try:
            terrain=terrain_at(*key)
            if terrain is None: raise ValueError('Terrain unavailable at origin')
            w=weather[key]; steps=segments(p,w,as_of,terrain)
            inputs.append({'point':p,'terrain':terrain,'steps':steps,
                           'weather_grid':{k:w.get(k) for k in ('latitude','longitude','elevation')},
                           'weather_hourly':w['hourly']})
        except (ValueError,KeyError,TypeError):
            excluded.append({'point':p,'reason':'missing_or_unsupported_terrain_or_hourly_wind'})
    frames=[]
    for hour in (3,6):
        frames.append({'hours':hour,'valid_at':(as_of+timedelta(hours=hour)).isoformat(),
            'geometry':{'type':'FeatureCollection','features':[
                {'type':'Feature','geometry':footprint(i['point'],i['steps'],hour*60),
                 'properties':{'origin_index':n,'detected_at':i['point']['detected_at']}}
                for n,i in enumerate(inputs)]}})
    meta,_=dataset()
    return {'schema':'cme-live-spread-v1','model_version':VERSION,'issued_at':as_of.isoformat(),'as_of':as_of.isoformat(),
            'status':'experimental' if inputs and not excluded and len(eligible)<=MAX_POINTS else 'partial' if inputs else 'no_usable_origins',
            'source_mode':source_mode,'source_retrieved_at':source_retrieved_at,
            'eligible_points':len(eligible),'used_points':len(inputs),'omitted_by_limit':max(0,len(eligible)-MAX_POINTS),
            'excluded':excluded,'inputs':inputs,'frames':frames,'fuel_assumption':FUEL,'wind_factor_assumption':WIND_FACTOR,
            'terrain_metadata':meta,'overall_accuracy_percent':None,
            'notes':['สมมติว่าจุดดาวเทียม 24 ชั่วโมงล่าสุดยังมีไฟ ณ เวลาเริ่ม ไม่ได้ยืนยันไฟที่ยังไหม้',
                     'เชื้อเพลิง FM1 ความชื้น 8% และตัวคูณลม 0.2 เป็นค่าทดลอง ยังไม่มีข้อมูลเชื้อเพลิงหน้างาน',
                     'ลมเปลี่ยนรายชั่วโมง; ทางลาดประมาณ 110 m อ่านที่จุดเริ่มแต่คงที่ตลอดการลามของแต่ละจุด',
                     'วงรีแต่ละชั่วโมงรวมเป็นกรอบตามเงื่อนไข ไม่รวมการดับไฟ สะเก็ดไฟ ถนน หรือเชื้อเพลิงที่เปลี่ยนตามตำแหน่ง',
                     'ใช้จุดล่าสุดไม่เกิน 50 จุดต่อรอบ จำนวนที่เว้นแสดงแยก ไม่มีคะแนนความเชื่อมั่นที่สอบเทียบแล้ว',
                     'PM2.5 ยังคงมาจาก CAMS แยกต่างหาก ไม่ใช่ควันที่คำนวณจากกรอบไฟนี้']}


def fetch_weather(points):
    if not points:return {}
    positions=list(dict.fromkeys((p['latitude'],p['longitude']) for p in points))
    response=httpx.get('https://api.open-meteo.com/v1/forecast',params={
        'latitude':','.join(str(p[0]) for p in positions),'longitude':','.join(str(p[1]) for p in positions),
        'hourly':'wind_speed_10m,wind_direction_10m','wind_speed_unit':'ms','timezone':'UTC',
        'forecast_days':2,'models':'gfs_seamless'},timeout=httpx.Timeout(18,connect=3))
    response.raise_for_status();body=response.json();body=body if isinstance(body,list) else [body]
    return dict(zip(positions,body))


def live(settings):
    global _cache
    with _lock:
        if _cache and time.monotonic() < _cache[0]:return _cache[1]
        from app.services import get_hotspots
        now=datetime.now(timezone.utc); hotspots=get_hotspots(settings)
        points=[{k:getattr(p,k) for k in ('latitude','longitude','detected_at','confidence_level','source')}
                for p in hotspots.items if now-timedelta(hours=24)<=stamp(p.detected_at)<=now and p.confidence_level!='low']
        points.sort(key=lambda p:stamp(p['detected_at']),reverse=True)
        try:weather=fetch_weather(points[:MAX_POINTS])
        except (httpx.HTTPError,ValueError):weather={}
        as_of=datetime.now(timezone.utc)
        result=build(points,weather,as_of=as_of,source_mode='live_received_inputs',
                     source_retrieved_at={'hotspots_received_at':now.isoformat(),'weather_received_at':as_of.isoformat()})
        _cache=(time.monotonic()+(300 if result['used_points'] or not points else 30),result)
        return result


@router.get('/live')
def current_spread(background_tasks: BackgroundTasks, settings: Settings=Depends(get_settings)):
    result=live(settings)
    from app.forecast_archive import collect_background
    background_tasks.add_task(collect_background,settings,result,'spread')
    return result
