"""Bounded, durable import tasks. Request handlers never download 180 days at once."""
from __future__ import annotations

import csv
import io
import math
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.environment_archive import observation, stamp, digest
from app.providers.verified_history import PRODUCTS, AVAILABILITY, FIRMS, BBOX
from app.providers.hotspot_provider import _province_ring, _point_in_ring, _nasa_detected_at, estimate_district
from app.evidence import native_confidence

UTC = timezone.utc


def task(kind, start, span, **extra):
    payload = {'utc_start': str(start), 'days': span, **extra}
    return {'task_key': kind+'/'+digest(payload), 'kind': kind, 'payload': payload}


def enqueue(store, start, end, *, requested_by=None, models=True, request_key=None):
    tasks = [task('firms_plan', start.astimezone(UTC).date(), 1)]
    if models:
        day, last = start.astimezone(UTC).date(), (end-timedelta(microseconds=1)).astimezone(UTC).date()
        while day <= last:
            span = min(5, (last-day).days+1)
            tasks.extend(task(kind, day, span) for kind in ('pm25_model','weather_model'))
            day += timedelta(days=span)
    job = {'id': str(uuid.uuid4()), 'request_key': request_key or str(uuid.uuid4()),
           'start_at': start.isoformat(), 'end_at': end.isoformat(), 'requested_by': requested_by, 'include_models': models}
    return store.call('POST','/rest/v1/rpc/cme_archive_enqueue',json={'p_job':job,'p_tasks':tasks})


def plan_firms(key, start, end, *, get=httpx.get):
    if not key:
        raise ValueError('missing_firms_key')
    r = get(AVAILABILITY+f'{key}/all',timeout=22)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    if not {'data_id','min_date','max_date'}.issubset(reader.fieldnames or []):
        raise ValueError('invalid_availability')
    availability = {}
    for x in reader:
        try:
            availability[x['data_id']] = (datetime.fromisoformat(x['min_date']).date(),datetime.fromisoformat(x['max_date']).date())
        except (KeyError,ValueError):
            continue
    tasks=[]
    last=(end-timedelta(microseconds=1)).astimezone(UTC).date()
    for sensor,sources in PRODUCTS.items():
        day=start.astimezone(UTC).date()
        pick=lambda d: next((s for s in sources if s in availability and availability[s][0]<=d<=availability[s][1]),None)
        while day<=last:
            source=pick(day);span=1
            while span<5 and day+timedelta(days=span)<=last and pick(day+timedelta(days=span))==source:
                span+=1
            t=task('firms',day,span,sensor=sensor,source=source or 'NASA FIRMS availability')
            if not source:
                t.update(status='not_available',result={**t['payload'],'status':'not_available'})
            tasks.append(t);day+=timedelta(days=span)
    return {'status':'received','source':'NASA FIRMS data availability','planned':len(tasks)},[],tasks


def firms_chunk(key, payload, start, end, *, now, get=httpx.get):
    source=payload['source'];sensor=payload['sensor'];span=int(payload['days'])
    if source not in PRODUCTS.get(sensor,()) or not 1<=span<=5 or not key:
        raise ValueError('invalid_firms_task')
    first=datetime.fromisoformat(payload['utc_start']).date()
    r=get(FIRMS+f'{key}/{source}/{BBOX}/{span}/{first}',timeout=22);r.raise_for_status()
    reader=csv.DictReader(io.StringIO(r.text))
    if not {'latitude','longitude','acq_date','acq_time'}.issubset(reader.fieldnames or []):
        raise ValueError('invalid_firms_csv')
    rows=[];invalid=0;ring=_province_ring()
    for x in reader:
        try:
            lat,lon=float(x['latitude']),float(x['longitude'])
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
                raise ValueError('coordinates')
            at=stamp(_nasa_detected_at(x['acq_date'],x['acq_time']))
            if at>now+timedelta(minutes=5) or not first<=at.astimezone(UTC).date()<first+timedelta(days=span):
                raise ValueError('time')
            if not start<=at<end or ring and not _point_in_ring(lon,lat,ring):
                continue
            frp=float(x['frp']) if x.get('frp') else None
            if frp is not None and (not math.isfinite(frp) or frp<0): raise ValueError('frp')
            satellite=x.get('satellite') or sensor
            p={'latitude':lat,'longitude':lon,'detected_at':at.isoformat(),'satellite':satellite,'source':source,
               'district':estimate_district(lat,lon),'district_method':'nearest_district_reference',
               'frp':frp,'confidence':x.get('confidence'),'source_record':x,'source_url':'https://firms.modaps.eosdis.nasa.gov/api/area/'}
            p.update(native_confidence(x.get('confidence'),'VIIRS'),confidence_source=source)
            rows.append(observation('hotspot',source,at.isoformat(),p,now.isoformat(),satellite,lat,lon))
        except (ValueError,TypeError,KeyError,OverflowError):
            invalid+=1
    return {**payload,'bbox':BBOX,'status':'partial' if invalid else 'received','invalid_rows':invalid,'received':len(rows)},rows,[]


def model_chunk(kind, payload, start, end, *, now, get=httpx.get):
    first=datetime.fromisoformat(payload['utc_start']).date();span=int(payload['days'])
    if not 1<=span<=5: raise ValueError('invalid_model_task')
    last=first+timedelta(days=span-1)
    weather=kind=='weather_model'
    fields=['temperature_2m','relative_humidity_2m','wind_speed_10m','wind_direction_10m'] if weather else ['pm2_5']
    source='Open-Meteo ERA5' if weather else 'Open-Meteo CAMS global'
    url='https://archive-api.open-meteo.com/v1/archive' if weather else 'https://air-quality-api.open-meteo.com/v1/air-quality'
    params={'latitude':18.79,'longitude':98.98,'start_date':str(first),'end_date':str(last),
            'hourly':','.join(fields),'timezone':'UTC','timeformat':'unixtime'}
    params.update({'models':'era5','wind_speed_unit':'kmh'} if weather else {'domains':'cams_global'})
    r=get(url,params=params,timeout=22);r.raise_for_status();doc=r.json()
    lat,lon=float(doc['latitude']),float(doc['longitude'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError('model_grid')
    hours=doc['hourly'];times=hours['time'];units=doc['hourly_units']
    expected={'temperature_2m':'°C','relative_humidity_2m':'%','wind_speed_10m':'km/h','wind_direction_10m':'°'} if weather else {'pm2_5':'μg/m³'}
    for f in fields:
        if len(hours[f])!=len(times) or str(units.get(f)).replace('µ','μ')!=expected[f]: raise ValueError('model_units_or_shape')
    if not times or any(not isinstance(t,(int,float)) or not math.isfinite(t) or t%3600 for t in times) or len(set(times))!=len(times):
        raise ValueError('missing_duplicate_or_unaligned_model_times')
    rows=[];missing=0
    # Missing timestamps count as gaps too; a truncated array must not pass as complete.
    by_time={t:i for i,t in enumerate(times)}
    first_at=max(start,datetime.combine(first,datetime.min.time(),UTC))
    until=min(end,datetime.combine(last+timedelta(days=1),datetime.min.time(),UTC),now)
    at=first_at.replace(minute=0,second=0,microsecond=0)
    if at<first_at: at+=timedelta(hours=1)
    expected=[]
    while at<until:
        expected.append(int(at.timestamp()));at+=timedelta(hours=1)
    for t in expected:
        at=datetime.fromtimestamp(t,UTC)
        if t not in by_time: missing+=1;continue
        i=by_time[t]
        values=[hours[f][i] for f in fields]
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
            missing+=1;continue
        if (not weather and values[0]<0) or (weather and (not 0<=values[1]<=100 or values[2]<0 or not 0<=values[3]<=360)):
            missing+=1;continue
        p={'id':f'{source}/{lat:.5f}/{lon:.5f}','measurement_kind':'model','reference_latitude':lat,'reference_longitude':lon,
           'source_url':'https://open-meteo.com/en/docs/historical-weather-api' if weather else 'https://open-meteo.com/en/docs/air-quality-api'}
        if weather:
            p.update(temperature_c=values[0],humidity_percent=values[1],wind_speed_kmh=values[2],wind_direction_deg=values[3])
        else:
            p.update(pm25=values[0],unit='µg/m³')
        # A grid reference is not assigned to a community forest as an in-forest sensor.
        rows.append(observation('weather' if weather else 'pm25',source,at.isoformat(),p,now.isoformat(),p['id']))
    return {**payload,'status':'partial' if missing else 'received','source':source,'missing_hours':missing,'received':len(rows),
            'reference_latitude':lat,'reference_longitude':lon},rows,[]


def work_one(store, *, now=None, get=httpx.get):
    fixed_now=now is not None
    token=str(uuid.uuid4());now=now or datetime.now(UTC)
    t=store.call('POST','/rest/v1/rpc/cme_archive_claim',json={'p_token':token})
    if not t:
        # Refresh a fixed recent window only after existing work drains. One
        # idempotent job per hour keeps browser requests free of upstream work.
        end=now.replace(minute=0,second=0,microsecond=0)
        enqueue(store,end-timedelta(days=2),end,models=False,request_key='refresh/'+end.isoformat())
        enqueue(store,end-timedelta(days=10),end,models=True,request_key='models-refresh/'+str(end.date()))
        return {'status':'idle'}
    try:
        start,end=stamp(t['start_at']),stamp(t['end_at'])
        if t['kind']=='firms_plan':
            result,rows,children=plan_firms(store.settings.nasa_firms_map_key,start,end,get=get)
        elif t['kind']=='firms':
            result,rows,children=firms_chunk(store.settings.nasa_firms_map_key,t['payload'],start,end,now=now,get=get)
        else:
            result,rows,children=model_chunk(t['kind'],t['payload'],start,end,now=now,get=get)
        # Record receipt after the response arrived, not before waiting on HTTP.
        received_at=(now if fixed_now else datetime.now(UTC)).isoformat()
        for row in rows: row['retrieved_at']=received_at
    except Exception as exc:
        code=f'upstream_http_{exc.response.status_code}' if isinstance(exc,httpx.HTTPStatusError) else 'upstream_request_or_format_failed'
        result,rows,children={**t['payload'],'status':'unavailable','error':code},[],[]
    store.call('POST','/rest/v1/rpc/cme_archive_finish',json={'p_id':t['id'],'p_token':token,'p_result':result,'p_rows':rows,'p_children':children})
    # No task IDs, credentials or admin diagnostics are exposed by public cron triggers.
    return {'status':'processed'}
