"""Experimental station-only hourly prediction with frozen chronological fit."""
import json,math,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from functools import lru_cache
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import APIRouter,BackgroundTasks,Depends
from app.config import Settings,get_settings
from app.providers.pm25_provider import _air4thai_tls_context

router=APIRouter(prefix='/api/forecast',tags=['Experimental station forecasts'])
ICT=timezone(timedelta(hours=7));_lock=Lock();_cache=None

@lru_cache(maxsize=1)
def artifact():return json.loads((Path(__file__).parent/'data/pm25-station-models.json').read_text(encoding='utf8'))

def features(series,origin,lead):
    valid=origin+timedelta(hours=lead)
    required=[origin-timedelta(hours=h) for h in (0,1,3,6,12,24,48)]+[valid-timedelta(hours=24)]
    if any(t>origin or t not in series for t in required):raise ValueError('Missing causal hourly inputs')
    values=[series[t] for t in required]
    if any(not math.isfinite(v) or v<0 for v in values):raise ValueError('Invalid observation')
    return values+[math.sin(valid.hour/24*2*math.pi),math.cos(valid.hour/24*2*math.pi)]

def predict(model,x):
    if model['type']=='blend':return model['weight_now']*x[0]+(1-model['weight_now'])*x[7]
    return max(0,model['weights'][0]+sum(w*(v-m)/s for w,v,m,s in zip(model['weights'][1:],x,model['mean'],model['scale'])))

def build(station,series,now):
    # Exclude the current partial hour; do not silently backfill missing lags.
    cutoff=now.replace(minute=0,second=0,microsecond=0)-timedelta(hours=1)
    valid_times=[t for t,v in series.items() if t<=cutoff and math.isfinite(v) and v>=0]
    if not valid_times:return {'station':station,'status':'unavailable','reason':'no_completed_hour_received','forecasts':[]}
    origin=max(valid_times)
    if now-origin>timedelta(hours=6):return {'station':station,'status':'unavailable','reason':'observations_older_than_6h','forecasts':[]}
    predictions=[]
    for spec in artifact()['models']:
        if spec['station']!=station:continue
        lead=spec['lead_hours'];valid=origin+timedelta(hours=lead)
        if valid<=now:continue
        try:x=features(series,origin,lead)
        except ValueError:continue
        predictions.append({'lead_hours_from_observation':lead,'valid_at':valid.isoformat(),'pm25_ug_m3':round(predict(spec['model'],x),2),
            'selected_model':spec['selected'],'input_features':x})
    return {'station':station,'status':'experimental' if len(predictions)==3 else 'partial' if predictions else 'unavailable',
            'observation_at':origin.isoformat(),'observation_pm25_ug_m3':series[origin],'forecasts':predictions}

def fetch_station(station,now):
    r=httpx.get('https://air4thai.com/forweb/getHistoryData.php',params={'stationID':station.lower(),'param':'PM25','type':'hr',
        'sdate':str((now-timedelta(days=4)).date()),'edate':str(now.date()),'stime':'00','etime':'23'},timeout=12,verify=_air4thai_tls_context())
    r.raise_for_status();body=r.json();series={}
    for item in body.get('stations',[]):
        if item.get('stationID','').upper()!=station:continue
        for row in item.get('data',[]):
            try:
                stamp=datetime.fromisoformat(row['DATETIMEDATA']).replace(tzinfo=ICT);v=float(row['PM25'])
                if math.isfinite(v) and v>=0:series[stamp]=v
            except (KeyError,TypeError,ValueError):continue
    return series

def live():
    global _cache
    with _lock:
        if _cache and time.monotonic()<_cache[0]:return _cache[1]
        now=datetime.now(ICT)
        def station_result(station):
            try:return build(station,fetch_station(station,now),now)
            except (httpx.HTTPError,ValueError,KeyError):return {'station':station,'status':'unavailable','reason':'source_unavailable','forecasts':[]}
        with ThreadPoolExecutor(max_workers=2) as pool:stations=list(pool.map(station_result,('35T','36T')))
        result={'model_version':artifact()['version'],'issued_at':now.isoformat(),'source_retrieved_at':datetime.now(ICT).isoformat(),
            'source':'Air4Thai hourly history','stations':stations,'evaluation':artifact()['test'],
            'notes':['ทดลองเฉพาะสถานี 35T และ 36T; ไม่ใช่ค่าเฉลี่ยทั้งจังหวัดหรือแบบจำลองควันจากไฟ',
                     'ทดสอบช่วงต้นตุลาคม ยังไม่ยืนยันผลในฤดูเผา ม.ค.–เม.ย.',
                     'ระยะ 6/12/24 ชั่วโมงนับจากข้อมูลวัดล่าสุด เวลาปลายชั่วโมงของแหล่งข้อมูลยังไม่ยืนยัน',
                     'ใช้โมเดลที่เลือกด้วยข้อมูลก่อนตุลาคม ไม่มีการเติมชั่วโมงที่ขาด']}
        _cache=(time.monotonic()+(300 if any(s['forecasts'] for s in stations) else 30),result)
        return result

@router.get('/stations')
def current(background_tasks:BackgroundTasks,settings:Settings=Depends(get_settings)):
    result=live()
    if any(s['forecasts'] for s in result['stations']):
        from app.forecast_archive import collect_background
        background_tasks.add_task(collect_background,settings,result,'station')
    return result
