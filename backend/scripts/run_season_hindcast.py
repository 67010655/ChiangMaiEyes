"""Reproducible Jan-Apr 2026 diagnostic. No writes to operational archives.

FIRMS points are positive observations, not perimeters or arrival times.
All fuel, flat terrain and 10m-to-midflame factors below are declared assumptions.
Run from backend: .venv/Scripts/python scripts/run_season_hindcast.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import get_settings
from app.providers.hotspot_provider import _province_ring, _point_in_ring, province_bbox
from app.spread_scenario import Scenario, Evaluation, run_scenario, evaluate_result, distance_bearing

OUT = ROOT / 'output' / 'hindcast-2026'
RAW = OUT / 'raw'
ICT = timezone(timedelta(hours=7))
START, END = date(2026, 1, 1), date(2026, 4, 30)
FIRST = datetime(2026, 1, 1, tzinfo=ICT)
UNTIL = datetime(2026, 5, 1, tzinfo=ICT)
DOCS = {
    'firms': 'https://firms.modaps.eosdis.nasa.gov/api/area/',
    'weather': 'https://open-meteo.com/en/docs/historical-weather-api',
    'forecast': 'https://open-meteo.com/en/docs/previous-runs-api',
    'pm25': 'https://open-meteo.com/en/docs/air-quality-api',
    'pm25_catalog': 'https://data.go.th/dataset/69_18',
}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')


def download(name, url, params=None, text=False):
    path = RAW / name
    if path.exists():
        return path.read_text(encoding='utf8') if text else json.loads(path.read_text(encoding='utf8'))
    # Never persist/log a URL containing a FIRMS key, even on a failed response.
    for attempt in range(3):
        try:
            r = httpx.get(url, params=params, timeout=50, follow_redirects=True)
            r.raise_for_status()
            value = r.text if text else r.json()
            if text:
                if not r.text.startswith(('latitude,', 'data_id,')):
                    raise ValueError('Invalid CSV')
                path.write_text(value, encoding='utf8')
            else:
                write(path, value)
            return value
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise RuntimeError('Upstream failed: ' + name) from None


def firms():
    s = get_settings()
    if not s.nasa_firms_map_key:
        raise RuntimeError('NASA_FIRMS_MAP_KEY is not configured')
    base = 'https://firms.modaps.eosdis.nasa.gov/api/'
    avail = download('firms-availability.csv', base + 'data_availability/csv/' + s.nasa_firms_map_key + '/all', text=True)
    available = {r['data_id']: (date.fromisoformat(r['min_date']), date.fromisoformat(r['max_date']))
                 for r in csv.DictReader(io.StringIO(avail))}
    jobs = []
    for sensor in ('SNPP', 'NOAA20', 'NOAA21'):
        day = START - timedelta(days=1)  # preceding UTC date contains 00-07 ICT
        while day <= END:
            candidates = [f'VIIRS_{sensor}_SP', f'VIIRS_{sensor}_NRT']
            product = next((p for p in candidates if p in available and available[p][0] <= day <= available[p][1]), None)
            span = min(5, (END-day).days+1)
            if product:
                span = min(span, (available[product][1]-day).days+1)
            jobs.append((sensor, product, day, span))
            day += timedelta(days=span)
    ring, bbox = _province_ring(), province_bbox()

    def one(job):
        sensor, product, day, span = job
        meta = dict(sensor=sensor, product=product, utc_start=str(day), days=span, status='unavailable')
        rows = []
        if product:
            try:
                name = f'{product}-{day}-{span}.csv'
                body = download(name, base + f'area/csv/{s.nasa_firms_map_key}/{product}/{bbox}/{span}/{day}', text=True)
                for r in csv.DictReader(io.StringIO(body)):
                    lat, lon = float(r['latitude']), float(r['longitude'])
                    when = datetime.strptime(r['acq_date']+' '+r['acq_time'].zfill(4), '%Y-%m-%d %H%M').replace(tzinfo=timezone.utc).astimezone(ICT)
                    if FIRST <= when < UNTIL and _point_in_ring(lon, lat, ring):
                        rows.append(dict(latitude=lat, longitude=lon, detected_at=when.isoformat(),
                                         satellite=sensor, product=product, confidence=r.get('confidence'),
                                         frp=float(r['frp']) if r.get('frp') else None,
                                         scan_km=float(r['scan']) if r.get('scan') else None,
                                         track_km=float(r['track']) if r.get('track') else None))
                meta.update(status='received', in_province_count=len(rows), file=name,
                            sha256=hashlib.sha256((RAW/name).read_bytes()).hexdigest())
            except (RuntimeError, ValueError, KeyError):
                meta['error'] = 'upstream_or_csv_validation_failed'
        return meta, rows
    coverage, points = [], {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for meta, rows in pool.map(one, jobs):
            coverage.append(meta)
            for r in rows:
                points[(r['satellite'], r['latitude'], r['longitude'], r['detected_at'])] = r
    return sorted(points.values(), key=lambda r:r['detected_at']), coverage


def environment(lat=18.79, lon=98.99, suffix='city'):
    common = dict(latitude=lat, longitude=lon, start_date=str(START), end_date=str(END), timezone='Asia/Bangkok')
    era = download(f'era5-{suffix}.json', 'https://archive-api.open-meteo.com/v1/archive',
                   {**common, 'hourly':'wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m,precipitation', 'wind_speed_unit':'ms', 'models':'era5'})
    if suffix != 'city':
        return era
    cams = download('cams-city.json', 'https://air-quality-api.open-meteo.com/v1/air-quality',
                    {**common, 'hourly':'pm2_5', 'domains':'cams_global'})
    forecast = download('gfs-previous-day1-city.json', 'https://previous-runs-api.open-meteo.com/v1/forecast',
                        {**common, 'hourly':'wind_speed_10m_previous_day1,wind_direction_10m_previous_day1',
                         'wind_speed_unit':'ms', 'models':'gfs_seamless'})
    return era, cams, forecast


def complete_day(day, coverage):
    a = datetime.combine(day, datetime.min.time(), tzinfo=ICT).astimezone(timezone.utc).date()
    b = datetime.combine(day, datetime.max.time(), tzinfo=ICT).astimezone(timezone.utc).date()
    return all(any(c['sensor']==s and c['status']=='received' and date.fromisoformat(c['utc_start']) <= d < date.fromisoformat(c['utc_start'])+timedelta(days=c['days'])
                   for c in coverage) for s in ('SNPP','NOAA20','NOAA21') for d in {a,b})


def mean(values):
    v = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return sum(v)/len(v) if v else None


def pm_catalog():
    url = 'https://chiangmai.gdcatalog.go.th/dataset/f84d0596-41a3-430b-b292-dad44664d0f5/resource/b8572bb6-82dc-4af8-8760-fc04b493c4db/download/untitled-16.csv'
    path = RAW/'chiangmai-pm25-catalog.csv'
    if not path.exists():
        r=httpx.get(url,timeout=40,follow_redirects=True)
        r.raise_for_status();path.write_bytes(r.content)
    rows=list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))[1:]
    selected=[r for r in rows if len(r)>=7 and r[1]=='2569']
    numeric=0
    for r in selected:
        try:
            value=float(r[5].strip().replace('\u2212','-'))
            numeric+=int(math.isfinite(value) and value>=0)
        except ValueError:
            pass
    return dict(source=DOCS['pm25_catalog'], resource_url=url,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                rows_2026=len(selected),numeric_nonnegative_rows=numeric,
                months=sorted(set(r[2] for r in selected)),sites=len(set(r[4] for r in selected)),
                status='candidate_daily_values_not_validated_station_pairs',
                limitation='Downloaded 2026 rows cover January-February only. Publisher cites GISTDA; station IDs, QA and averaging-window end times are not established. Do not label as paired PCD measurements.')


def error_metrics(predicted, reference):
    pairs = [(p,r) for p,r in zip(predicted,reference) if p is not None and r is not None and math.isfinite(p) and math.isfinite(r)]
    errors = [p-r for p,r in pairs]
    return dict(n=len(errors), mae=mean([abs(x) for x in errors]),
                rmse=math.sqrt(mean([x*x for x in errors])) if errors else None, bias=mean(errors))


def select_cases(points, daily):
    # One seed per peak day, chosen from the first overpass in the densest
    # 0.05 degree tile of that day. Selection uses hindsight and is disclosed.
    # Later points in a fixed 5km/6h window are candidates, not proven same-fire.
    peaks = sorted([r for r in daily if r['firms_complete']], key=lambda r:r['detections'], reverse=True)[:8]
    cases = []
    for peak in peaks:
        daypoints = [r for r in points if r['detected_at'][:10]==peak['date'] and r['confidence']!='l']
        groups = defaultdict(list)
        for r in daypoints:
            groups[(math.floor(r['latitude']/.05), math.floor(r['longitude']/.05))].append(r)
        if not groups:
            continue
        group = max(groups.values(), key=len)
        seed = min(group, key=lambda r:r['detected_at'])
        start = datetime.fromisoformat(seed['detected_at'])
        observations = [dict(latitude=r['latitude'], longitude=r['longitude'], observed_at=r['detected_at'],
                             kind='firms_detection', source=r['product']+' '+r['satellite'], position_uncertainty_m=375)
                        for r in points if r['confidence']!='l' and 0 < (datetime.fromisoformat(r['detected_at'])-start).total_seconds() <= 21600
                        and distance_bearing(seed['latitude'],seed['longitude'],r['latitude'],r['longitude'])[0] <= 5000]
        if not observations:
            cases.append(dict(id=peak['date'], seed=seed, observation_count=0, status='no_later_points_within_6h_5km'))
            continue
        candidate_count = len(observations)
        observations = observations[:500]  # endpoint cap; report truncation explicitly
        era = environment(seed['latitude'],seed['longitude'], 'event-'+peak['date'])
        h = era['hourly']; hour = start.strftime('%Y-%m-%dT%H:00'); idx=h['time'].index(hour)
        speed, direction = h['wind_speed_10m'][idx], h['wind_direction_10m'][idx]
        if speed is None or direction is None:
            continue
        scenarios = []
        for factor in (.1,.2,.4):
            for moisture in (5,8,11):
                evidence = dict(basis='assumed', source='Retrospective diagnostic; not field measurements', observed_at=start.isoformat())
                request = dict(latitude=seed['latitude'],longitude=seed['longitude'],start_at=start.isoformat(),duration_minutes=360,
                               fuel=dict(load_kg_m2=.16600253963702372,depth_m=.3048,savr_per_m=11482.939632545931,
                                         moisture_pct=moisture,extinction_moisture_pct=12,evidence={**evidence,'basis':'reference','source':'USFS FM1 reference; not Chiang Mai fuel'}),
                               wind=dict(midflame_mps=speed*factor,from_deg=direction%360,evidence={**evidence,'source':f'ERA5 10m wind {speed} m/s multiplied by assumed factor {factor}; not measured midflame'}),
                               terrain=dict(mode='manual',slope_deg=0,upslope_to_deg=0,evidence={**evidence,'source':'Flat terrain assumption; no event-site DEM sampled'}))
                req=Scenario.model_validate(request); result=run_scenario(req)
                evaluation=evaluate_result(Evaluation(scenario=req,observations=observations),result,basis='retrospective_assumed_fuel_terrain_wind')
                last=result['cases'][0]['frames'][-1]
                scenarios.append(dict(factor=factor,moisture_pct=moisture,request=request,
                                      coverage_percent=evaluation['nominal_point_coverage_percent'],
                                      baseline_coverage_percent=evaluation['baseline_point_coverage_percent'],
                                      head_m_min=result['cases'][0]['rates']['head_m_min'],
                                      final_frame=last, input_sha256=result['input_sha256']))
        cases.append(dict(id=peak['date'],seed=seed,status='retrospective_assumptions',observation_count=len(observations),
                          observations=observations,era5_wind_10m_mps=speed,wind_from_deg=direction,
                          era5_sample=dict(latitude=era['latitude'],longitude=era['longitude']),scenarios=scenarios,
                          selection='Peak-day dense tile selected using hindsight; first detection is a proxy origin, not ignition',
                          candidate_count=candidate_count,truncated_at_500=candidate_count>500))
    return cases


def main():
    RAW.mkdir(parents=True,exist_ok=True)
    print('Fetching FIRMS standard processing and environmental archives',flush=True)
    points, coverage = firms()
    write(OUT/'firms-points.json',points);write(OUT/'firms-coverage.json',coverage)
    print(f'FIRMS: {len(points)} detections; {sum(c["status"]=="received" for c in coverage)}/{len(coverage)} requests',flush=True)
    era,cams,forecast = environment()
    hc,he,hf=cams['hourly'],era['hourly'],forecast['hourly']
    counts=Counter(r['detected_at'][:10] for r in points)
    daily=[]
    for n in range(120):
        day=START+timedelta(days=n);stamp=str(day);indices=[i for i,t in enumerate(he['time']) if t.startswith(stamp)]
        pm=[v for t,v in zip(hc['time'],hc['pm2_5']) if t.startswith(stamp)]
        daily.append(dict(date=stamp,detections=counts[stamp] if complete_day(day,coverage) else None,
                          observed_detections=counts[stamp],firms_complete=complete_day(day,coverage),
                          pm25_cams_mean=mean(pm),pm25_cams_hours=sum(v is not None for v in pm),
                          wind_10m_mean_mps=mean([he['wind_speed_10m'][i] for i in indices])))
    ref=dict(zip(he['time'],he['wind_speed_10m']));dirs=dict(zip(he['time'],he['wind_direction_10m']))
    ft=hf['time'];fp=hf['wind_speed_10m_previous_day1'];fd=hf['wind_direction_10m_previous_day1']
    speed_full=error_metrics(fp,[ref.get(t) for t in ft])
    previous=[ref.get((datetime.fromisoformat(t)-timedelta(days=1)).isoformat(timespec='minutes')) for t in ft]
    common=[i for i,t in enumerate(ft) if fp[i] is not None and previous[i] is not None and ref.get(t) is not None]
    speed=error_metrics([fp[i] for i in common],[ref[ft[i]] for i in common])
    persistence=error_metrics([previous[i] for i in common],[ref[ft[i]] for i in common])
    dir_errors=[abs((p-dirs[t]+180)%360-180) for t,p,rs in zip(ft,fd,fp)
                if p is not None and dirs.get(t) is not None and rs is not None and rs>=1 and ref.get(t) is not None and ref[t]>=1]
    print('Running fixed 9-scenario sensitivity grid on 8 peak-day cases',flush=True)
    cases=select_cases(points,daily)
    valid_cases=[c for c in cases if c.get('scenarios')]
    n_points=sum(c['observation_count'] for c in valid_cases)
    coverage_grid=[dict(factor=factor,moisture_pct=moisture,
                        point_count=n_points,
                        covered_count=sum(round(c['observation_count']*next(s['coverage_percent'] for s in c['scenarios'] if s['factor']==factor and s['moisture_pct']==moisture)/100) for c in valid_cases))
                   for factor in (.1,.2,.4) for moisture in (5,8,11)]
    for r in coverage_grid:
        r['coverage_percent']=100*r['covered_count']/n_points if n_points else None
    catalog=pm_catalog()
    report=dict(schema='cme-season-hindcast-v1',built_at=datetime.now(timezone.utc).isoformat(),
                start=FIRST.isoformat(),end_exclusive=UNTIL.isoformat(),timezone='Asia/Bangkok',
                scope='Chiang Mai province polygon; VIIRS SNPP, NOAA20, NOAA21; SP preferred',
                status='retrospective_diagnostic_not_validated_forecast',
                detections=len(points),complete_days=sum(r['firms_complete'] for r in daily),requested_days=120,
                source_requests=dict(received=sum(c['status']=='received' for c in coverage),total=len(coverage)),
                peak_days=sorted([r for r in daily if r['detections'] is not None],key=lambda r:r['detections'],reverse=True)[:10],
                daily=daily,cases=cases,wind=dict(reference='ERA5 reanalysis, not station observations',
                    prediction='GFS seamless previous_day1, 24h lead, city coordinate only',unit='m/s',speed=speed,
                    speed_full_window=speed_full,comparison_pairing='Forecast and persistence evaluated on the same available hours; first 24h omitted from paired comparison',
                    persistence_24h=persistence,direction_mae_degrees=mean(dir_errors),direction_n=len(dir_errors),calm_filter_mps=1),
                pm25=dict(model='CAMS global archived series; not a fixed-lead forecast',unit='ug/m3',
                          measured_pairs=0,mae=None,rmse=None,reason='No independent quality-controlled station archive has been paired'),
                fire=dict(accuracy_percent=None,iou=None,arrival_mae_minutes=None,
                          diagnostic_case_count=len(valid_cases),diagnostic_point_count=n_points,coverage_grid=coverage_grid,
                          reason='No independent perimeters/arrival times or event-site fuel measurements',
                          nominal_point_coverage_is_accuracy=False),
                pm25_catalog=catalog,
                reproducibility=dict(script='backend/scripts/run_season_hindcast.py',
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    raw_files=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(RAW.iterdir()) if p.is_file()]),
                sources=DOCS,limitations=[
                    'FIRMS counts detections, not confirmed incidents or burned area; no detections does not prove no fire.',
                    'Peak days and dense tiles selected using hindsight. This is not a blind prospective test.',
                    'Later points within 5km/6h are candidates, not verified continuation of the same fire.',
                    'First satellite detection is a proxy origin/time; true ignition is unknown.',
                    'FM1 and 5/8/11% fuel moisture, flat slope and .1/.2/.4 midflame factors are uncalibrated assumptions.',
                    '375m is nominal VIIRS resolution, not a confidence radius. Coverage uses pixel centers without buffering.',
                    'Wind is a model-versus-reanalysis comparison at the city, not midflame or station validation.',
                    'CAMS PM2.5 is a separate model, not smoke emitted from this simulated fire.',
                    'No overall fire-spread / PM2.5 accuracy percentage can be established from these data.',
                ])
    write(OUT/'summary.json',report)
    write(ROOT/'backend/app/data/season-hindcast-2026.json',report)
    print(json.dumps({'detections':report['detections'],'complete_days':report['complete_days'],'wind':report['wind'],'cases':[(c['id'],c['observation_count']) for c in cases]},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
