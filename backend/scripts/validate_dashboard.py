"""Measure dashboard outputs with public observations; no operational writes.

Inputs acquired under output/decision-validation-20261017. Run from backend:
  .venv/Scripts/python scripts/validate_dashboard.py
The experiment keeps station agreement, retrospective prediction and satellite
positive-point coverage separate. No combined accuracy percentage is invented.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path

import httpx
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from app.validation_metrics import regression_metrics,compare_models,skill_percent

OUT=ROOT/'output/decision-validation-20261017'
PM=OUT/'pm25'
ICT=timezone(timedelta(hours=7))


def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf8')
def csv_rows(path):return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
def number(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None


def block_interval(rows,key,seed=20261017):
    groups=defaultdict(list)
    for r in rows:groups[r['time'][:10]].append(abs(r[key]-r['observed']))
    if len(groups)<2:return None
    blocks=list(groups.values());rng=np.random.default_rng(seed)
    means=[]
    for _ in range(500):
        values=[x for i in rng.integers(0,len(blocks),len(blocks)) for x in blocks[i]]
        means.append(sum(values)/len(values))
    return dict(level=.95,lower=float(np.percentile(means,2.5)),upper=float(np.percentile(means,97.5)),
                method='500 day-block bootstrap resamples; paired rows grouped by reference day',blocks=len(blocks))


def daily_model(path,end_hour=24):
    h=read(path)['hourly'];hours={datetime.fromisoformat(t):v for t,v in zip(h['time'],h['pm2_5'])}
    result={}
    for day in sorted({t.date() for t in hours}):
        start=datetime.combine(day,datetime.min.time())+timedelta(hours=end_hour-24)
        values=[hours.get(start+timedelta(hours=i)) for i in range(24)]
        result[str(day)]=sum(values)/24 if all(v is not None for v in values) else None
    return result


def daily_pm():
    rows=[];calibration={};all_observed={}
    for sid in ('35T','36T'):
        train=[r for r in csv_rows(PM/'chiangmai-air4thai-daily-2025-jan-apr.csv') if r['station_id']==sid]
        obs2026=[r for r in csv_rows(PM/'chiangmai-air4thai-daily-2026-jan-apr.csv') if r['station_id']==sid]
        m25=daily_model(PM/f'cams-{sid.lower()}-jan-apr-2025.json')
        m26=daily_model(PM/f'cams-{sid.lower()}-jan-apr-2026.json')
        errors=[number(r['pm25_ug_m3'])-m25[r['date']] for r in train if number(r['pm25_ug_m3']) is not None and m25.get(r['date']) is not None]
        bias=sum(errors)/len(errors)
        calibration[sid]=dict(training_start='2025-01-01',training_end='2025-04-30',n=len(errors),additive_bias_ug_m3=bias)
        observed={r['date']:number(r['pm25_ug_m3']) for r in obs2026};all_observed[sid]=observed
        for day,value in observed.items():
            previous=str(datetime.fromisoformat(day).date()-timedelta(days=1))
            model=m26.get(day)
            rows.append(dict(time=day,station_id=sid,observed=value,cams=model,
                             cams_bias_2025=max(0,model+bias) if model is not None else None,
                             persistence=observed.get(previous)))
    _,all_models=compare_models(rows,['cams','cams_bias_2025'])
    common,comparison=compare_models(rows,['cams','cams_bias_2025','persistence'])
    for k,v in comparison.items():v['mae_interval']=block_interval(common,k)
    by_station={sid:compare_models([r for r in rows if r['station_id']==sid],['cams','cams_bias_2025','persistence'])[1] for sid in ('35T','36T')}
    by_month={month:compare_models([r for r in rows if r['time'][5:7]==month],['cams','cams_bias_2025','persistence'])[1] for month in ('01','02','03','04')}
    sensitivity=[]
    for end in (0,7,24):
        pairs=[]
        for sid in ('35T','36T'):
            model=daily_model(PM/f'cams-{sid.lower()}-jan-apr-2026.json',end)
            pairs.extend(dict(predicted=model.get(day),observed=value) for day,value in all_observed[sid].items())
        sensitivity.append(dict(window_end_hour_ict=end,**regression_metrics(pairs)))
    return dict(status='measured_station_retrospective_agreement',unit='ug/m3',period='2026-01-01/2026-04-30',
                valid_station_days=sum(r['observed'] is not None for r in rows),expected_station_days=240,
                all_valid_pairs=all_models,matched_comparison=comparison,by_station=by_station,by_month=by_month,
                calibration=calibration,aggregation_sensitivity=sensitivity,rows=rows,
                forecast_issue_verified=False,
                meaning='CAMS archived series versus official measured daily export, not an as-issued fixed-lead forecast score',
                notes=['PCD official 24h daily PM2.5 export, preliminary QC. Exact 24h window end is not specified.',
                       'Primary aggregation is 00:00-24:00 ICT; alternate window-end assumptions are sensitivity only, not selected using best score.',
                       'Both city stations sample the same CAMS grid. They are not two independent model grids.',
                       'Bias fitted only on Jan-Apr 2025; held-out evaluation is Jan-Apr 2026. No missing observations filled with zero.',
                       'Historical station position not independently confirmed; requested coordinates are from current Air4Thai metadata.'])


def hourly_features(series,origin):
    lags=(0,1,3,6,12,24,48)
    values=[series.get(origin-timedelta(hours=h)) for h in lags]
    if any(v is None for v in values):return None
    hour=origin.hour;doy=origin.timetuple().tm_yday
    return np.array([*values,math.sin(2*math.pi*hour/24),math.cos(2*math.pi*hour/24),
                     math.sin(2*math.pi*doy/365.25),math.cos(2*math.pi*doy/365.25)],dtype=float)


def recent_pm():
    cutoff=datetime(2026,9,30,23,tzinfo=ICT);test_start=datetime(2026,10,1,tzinfo=ICT)
    test_origin_end=datetime(2026,10,15,23,tzinfo=ICT)  # equal origin cohort across 6/12/24h
    combined=defaultdict(list);stations={};latest=[]
    for sid in ('35T','36T'):
        path=PM/f'chiangmai-air4thai-{sid.lower()}-hourly-20260917-20261016.csv'
        if not path.exists():continue
        series={datetime.fromisoformat(r['datetime_as_published']).replace(tzinfo=ICT):number(r['pm25_ug_m3']) for r in csv_rows(path)}
        stations[sid]={}
        for lead in (6,12,24):
            train=[];test=[]
            for origin in sorted(series):
                x=hourly_features(series,origin);valid=origin+timedelta(hours=lead);actual=series.get(valid)
                baseline_day=series.get(valid-timedelta(hours=24))
                if x is None or actual is None or baseline_day is None:continue
                row=(origin,valid,x,actual,baseline_day)
                if valid<=cutoff:train.append(row)
                elif test_start<=origin<=test_origin_end:test.append(row)
            if len(train)<50:continue
            X=np.stack([r[2] for r in train]);y=np.array([r[3] for r in train]);mu=X.mean(axis=0);scale=X.std(axis=0);scale[scale<1e-9]=1
            X=np.column_stack([np.ones(len(X)),(X-mu)/scale]);penalty=np.eye(X.shape[1])*10;penalty[0,0]=0
            weights=np.linalg.solve(X.T@X+penalty,X.T@y)
            pairs=[]
            for origin,valid,x,actual,bday in test:
                prediction=max(0,float(np.r_[1,(x-mu)/scale]@weights))
                pairs.append(dict(time=valid.isoformat(),origin=origin.isoformat(),station_id=sid,observed=actual,
                                  ridge=prediction,persistence=series[origin],same_hour_previous_day=bday))
            matched,metrics=compare_models(pairs,['ridge','persistence','same_hour_previous_day'])
            baseline=min(metrics['persistence']['mae'],metrics['same_hour_previous_day']['mae']) if matched else None
            stations[sid][str(lead)]=dict(training_pairs=len(train),test_pairs=len(matched),metrics=metrics,
                skill_vs_best_baseline_percent=skill_percent(metrics['ridge']['mae'],baseline))
            combined[lead].extend(matched)
            end=max(series);x=hourly_features(series,end)
            if x is not None:
                chosen='same_hour_previous_day' if metrics['same_hour_previous_day']['mae']<=metrics['persistence']['mae'] else 'persistence'
                baseline_value=series.get(end+timedelta(hours=lead-24)) if chosen=='same_hour_previous_day' else series[end]
                latest.append(dict(station_id=sid,origin=end.isoformat(),valid_at=(end+timedelta(hours=lead)).isoformat(),lead_hours=lead,
                                   pm25_ug_m3=max(0,float(np.r_[1,(x-mu)/scale]@weights)),model='experimental_ridge_lags_alpha10_trained_through_20260930'))
                latest[-1].update(best_baseline_on_test=chosen,baseline_pm25_ug_m3=baseline_value,
                                  selection_basis='retrospective test comparison, not a pre-registered model selection or production change')
    results={}
    for lead,rows in combined.items():
        common,metrics=compare_models(rows,['ridge','persistence','same_hour_previous_day'])
        for k,v in metrics.items():v['mae_interval']=block_interval(common,k)
        best=min(metrics['persistence']['mae'],metrics['same_hour_previous_day']['mae'])
        results[str(lead)]=dict(metrics=metrics,skill_vs_best_baseline_percent=skill_percent(metrics['ridge']['mae'],best),rows=rows)
    return dict(status='chronological_backtest_experimental_observation_only_model',unit='ug/m3',
                training_end=cutoff.isoformat(),test_origin_start=test_start.isoformat(),test_origin_end=test_origin_end.isoformat(),
                target_end='2026-10-16T23:00:00+07:00',station_count=len(stations),by_station=stations,by_lead=results,
                latest_experimental_predictions=latest,production_model_changed=False,
                notes=['Source is Air4Thai type=hr history, not live rolling-24h AQI. Exact hour timestamp start/end convention not established.',
                       'This is a new experimental model, not the production CAMS provider. Alpha=10 and lag features fixed without selecting on test.',
                       'Train targets end Sep 30. Test origins Oct 1-15 and targets through Oct 16; same origin range across horizons.',
                       'No future observations in features; no gaps imputed. Historical delivery latency is unknown.',
                       'This recent period is outside peak burning season. Do not extrapolate these errors to March-April.'])


def wind_validation():
    path=OUT/'airport-iem-2026.csv'
    if not path.exists():return dict(status='unavailable')
    observations={};duplicates=0
    for row in csv_rows(path):
        t=datetime.fromisoformat(row['valid']).replace(tzinfo=timezone.utc)
        if t.minute!=0:continue
        speed=number(row['sknt']);direction=number(row['drct'])
        if speed is None or speed<0:continue
        key=t.astimezone(ICT).strftime('%Y-%m-%dT%H:00')
        if key in observations:duplicates+=1;continue
        observations[key]=dict(speed=speed*1852/3600,direction=direction,metar=row.get('metar'))
    forecast=read(OUT/'airport-gfs-iem-location.json');h=forecast['hourly'];results={}
    for lead in (24,48):
        suffix=f'previous_day{lead//24}';rows=[];direction_errors=[]
        for t,p,d in zip(h['time'],h[f'wind_speed_10m_{suffix}'],h[f'wind_direction_10m_{suffix}']):
            ref=observations.get(t);previous=(datetime.fromisoformat(t)-timedelta(hours=lead)).strftime('%Y-%m-%dT%H:00');past=observations.get(previous)
            if ref is None or past is None or p is None:continue
            rows.append(dict(time=t,observed=ref['speed'],gfs=p,persistence=past['speed']))
            if ref['speed']>=1 and p>=1 and ref['direction'] is not None and d is not None:
                direction_errors.append(abs((d-ref['direction']+180)%360-180))
        common,metrics=compare_models(rows,['gfs','persistence'])
        for k,v in metrics.items():v['mae_interval']=block_interval(common,k)
        results[str(lead)]=dict(metrics=metrics,skill_vs_persistence_percent=skill_percent(metrics['gfs']['mae'],metrics['persistence']['mae']),
                               direction_mae_degrees=sum(direction_errors)/len(direction_errors) if direction_errors else None,
                               direction_pairs=len(direction_errors),rows=common)
    return dict(status='forecast_vs_airport_metar_observations',station='VTCC Chiang Mai airport',
                station_latitude=18.7711,station_longitude=98.9724,unit='m/s',by_lead=results,
                forecast_requested_latitude=18.7711,forecast_requested_longitude=98.9724,
                forecast_returned_latitude=forecast['latitude'],forecast_returned_longitude=forecast['longitude'],
                duplicate_exact_hour_records_skipped=duplicates,
                sources=['https://mesonet.agron.iastate.edu/request/download.phtml','https://open-meteo.com/en/docs/previous-runs-api'],
                notes=['IEM archived routine airport METAR observations; only exact UTC hour records used, knots converted to m/s.',
                       'Missing/variable wind direction excluded from direction score; direction evaluated only when both speeds >=1 m/s.',
                       'One airport station, not forest midflame validation. Model grid, observation averaging and local exposure differ.',
                       'Current forecast request uses station location from IEM coordinates; GFS fixed leads 24h/48h, not ERA5 reference.'])


def terrain_samples(initial,sources,project):
    from rasterio.warp import reproject,Resampling,transform_bounds
    from rasterio.transform import from_origin
    from build_forest_terrain import merge_native
    output=[]
    for row in initial:
        lon,lat=row['longitude'],row['latitude'];x,y=project.transform(lon,lat)
        relevant=[(meta,ds) for meta,ds in sources if ds.bounds.left-.002<=lon<=ds.bounds.right+.002 and ds.bounds.bottom-.002<=lat<=ds.bounds.top+.002]
        patch=np.full((3,3),np.nan,dtype='float32')
        bounds=transform_bounds(32647,4326,x-45,y-45,x+45,y+45,densify_pts=21)
        mosaic,transform=merge_native([ds for _,ds in relevant],bounds)
        reproject(mosaic[0].filled(np.nan),patch,src_transform=transform,src_crs=4326,src_nodata=np.nan,
                  dst_transform=from_origin(x-45,y+45,30,30),dst_crs=32647,dst_nodata=np.nan,resampling=Resampling.bilinear)
        if not np.isfinite(patch).all():raise ValueError('Missing DEM cells at initial fire sample')
        a,b,c,d,e,f,g,h,i=map(float,patch.ravel());east=((c+2*f+i)-(a+2*d+g))/240;north=((a+2*b+c)-(g+2*h+i))/240
        slope=math.degrees(math.atan(math.hypot(east,north)));xn,yn=project.transform(lon,lat+.0001)
        upslope=(math.degrees(math.atan2(east,north))-math.degrees(math.atan2(xn-x,yn-y)))%360 if slope>1e-10 else 0
        output.append(dict(latitude=lat,longitude=lon,slope_deg=slope,upslope_to_deg=upslope,
                           elevation_m=e,sample_sha256=hashlib.sha256(patch.astype('<f4').tobytes()).hexdigest()))
    return output


def fire_followup():
    import rasterio
    from pyproj import Transformer
    from shapely.geometry import Point,shape,mapping
    from shapely import transform as coordinate_transform
    from shapely.ops import unary_union
    def project_geom(geometry,transformer):
        return coordinate_transform(geometry,transformer.transform,interleaved=False)
    from app.spread_scenario import Scenario,rate_of_spread,frame,distance_bearing
    old=read(ROOT/'output/hindcast-2026/summary.json');points=read(ROOT/'output/hindcast-2026/firms-points.json')
    for p in points:p['_time']=datetime.fromisoformat(p['detected_at'])
    project=Transformer.from_crs(4326,32647,always_xy=True);reverse=Transformer.from_crs(32647,4326,always_xy=True)
    sources=[];source_manifest=[]
    for path in sorted((ROOT/'output/terrain/dem').glob('*.json')):
        meta=read(path);tile=path.parent/meta['filename']
        if hashlib.sha256(tile.read_bytes()).hexdigest()!=meta['sha256']:
            raise ValueError('DSM tile checksum mismatch')
        ds=rasterio.open(tile);sources.append((meta,ds))
        source_manifest.append(dict(url=meta['url'],sha256=meta['sha256']))
    cases=[];agg=defaultdict(lambda:dict(covered=0,baseline_covered=0,points=0,new_points=0,new_covered=0,area_ha=0))
    for case in old['cases']:
        seed=case['seed'];first=datetime.fromisoformat(seed['detected_at']);issued=first+timedelta(minutes=5)
        nearby=[p for p in points if abs((p['_time']-first).total_seconds())<=22000 and distance_bearing(seed['latitude'],seed['longitude'],p['latitude'],p['longitude'])[0]<=5000 and p['confidence']!='l']
        initial=[p for p in nearby if first<=p['_time']<=issued]
        # The single-source control uses the exact seed from the first report.
        initial.sort(key=lambda p:(not (p['latitude']==seed['latitude'] and p['longitude']==seed['longitude'] and p['detected_at']==seed['detected_at']),p['_time']))
        later=[p for p in nearby if issued<p['_time']<=issued+timedelta(hours=6)]
        if not initial or not later:continue
        terrain=terrain_samples(initial,sources,project)
        variant=next(s for s in case['scenarios'] if s['factor']==.2 and s['moisture_pct']==8)
        req=Scenario.model_validate(variant['request'])
        stationary=unary_union([Point(*project.transform(p['longitude'],p['latitude'])) for p in initial])
        evaluation_domain=Point(*project.transform(seed['longitude'],seed['latitude'])).buffer(5000)
        last_elapsed=max((p['_time']-issued).total_seconds()/60 for p in later)
        variants={}
        for name in ('single_seed_flat','all_initial_flat','all_initial_dem'):
            starts=initial[:1] if name=='single_seed_flat' else initial
            rates=[rate_of_spread(req.fuel,req.wind,terrain[i]['slope_deg'] if name=='all_initial_dem' else 0,
                                 terrain[i]['upslope_to_deg'] if name=='all_initial_dem' else 0) for i,_ in enumerate(starts)]
            geometries={};final=None
            for elapsed in sorted({(p['_time']-issued).total_seconds()/60 for p in later}|{360.0}):
                geoms=[]
                for origin,rate in zip(starts,rates):
                    f=frame(origin['latitude'],origin['longitude'],rate,elapsed)
                    geoms.append(project_geom(shape(f['geometry']),project) if f['geometry'] else Point(*project.transform(origin['longitude'],origin['latitude'])))
                geometries[elapsed]=unary_union(geoms)
            scores=[]
            for tolerance in (0,375,750):
                base=stationary.buffer(tolerance) if tolerance else stationary
                covered=baseline_covered=new_points=new_covered=0
                for p in later:
                    point=Point(*project.transform(p['longitude'],p['latitude']));elapsed=(p['_time']-issued).total_seconds()/60
                    forecast=geometries[elapsed].buffer(tolerance) if tolerance else geometries[elapsed]
                    hit=forecast.covers(point);base_hit=base.covers(point)
                    covered+=hit;baseline_covered+=base_hit;new_points+=not base_hit;new_covered+=hit and not base_hit
                final=geometries[last_elapsed].buffer(tolerance) if tolerance else geometries[last_elapsed]
                score=dict(tolerance_m=tolerance,points=len(later),covered=int(covered),baseline_covered=int(baseline_covered),
                           coverage_percent=100*covered/len(later),baseline_coverage_percent=100*baseline_covered/len(later),
                           new_points=int(new_points),new_covered=int(new_covered),
                           new_point_coverage_percent=100*new_covered/new_points if new_points else None,
                           search_envelope_area_ha=final.intersection(evaluation_domain).area/10000,
                           unbounded_search_envelope_area_ha=final.area/10000,
                           stationary_envelope_area_ha=base.intersection(evaluation_domain).area/10000,
                           area_at_minutes=last_elapsed)
                scores.append(score)
                a=agg[(name,tolerance)]
                for k in ('covered','baseline_covered','points','new_points','new_covered'):a[k]+=score[k]
                a['area_ha']+=score['search_envelope_area_ha']
            nominal=geometries[last_elapsed]
            variants[name]=dict(scores=scores,final_geometry=mapping(project_geom(nominal,reverse)),
                                evaluation_geometry_375m=mapping(project_geom(nominal.buffer(375).intersection(evaluation_domain),reverse)),
                                effective_wind_exceeds_legacy_limit_count=sum(r['effective_wind_exceeds_legacy_limit'] for r in rates),
                                legacy_slope_clamp_omitted_count=sum(r['legacy_slope_clamp_omitted'] for r in rates))
        cases.append(dict(id=case['id'],as_of=issued.isoformat(),initial=[{k:v for k,v in p.items() if k!='_time'} for p in initial],
                          later=[{k:v for k,v in p.items() if k!='_time'} for p in later],terrain=terrain,variants=variants))
    for _,ds in sources:ds.close()
    summary=[]
    for (name,tolerance),a in agg.items():
        summary.append(dict(variant=name,tolerance_m=tolerance,**a,coverage_percent=100*a['covered']/a['points'],
                            baseline_coverage_percent=100*a['baseline_covered']/a['points'],
                            new_point_coverage_percent=100*a['new_covered']/a['new_points'] if a['new_points'] else None))
    return dict(status='satellite_followup_diagnostic',case_count=len(cases),summary=summary,cases=cases,
                terrain_provenance=dict(dataset='Copernicus GLO-30 DSM',spacing_m=30,method='Horn 3x3, bilinear UTM47N, true-north upslope',tiles=source_manifest,
                    license_url='https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf',
                    attribution='produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved'),
                accuracy_percent=None,iou=None,
                notes=['Eight peak-day windows selected with hindsight, not independently verified single-fire events.',
                       'Initial support uses ALL detections received in the first 5 acquisition minutes in the fixed 5km window.',
                       'Later observations strictly follow as_of; archived acquisition times do not establish real-time data delivery.',
                       'Nominal,375m,750m tolerances are predefined matching sensitivities, not probability/confidence radii.',
                       'No-growth baseline uses all initial points and the identical tolerance. Predicted envelope area is shown to expose growth.',
                       'Reference FM1/8% moisture and assumed wind factor .2 remain fixed. DEM sampled at observed locations, not nearby forest centroids.',
                       'Reported search area is clipped to the fixed 5km evaluation domain at the last follow-up observation, not 6h.',
                       'This measures follow-up detection coverage, not burned-area accuracy/precision/false-alarm rates; negatives/perimeters unavailable.',
                       'The earlier single-point 0.33% is not an overall accuracy score and is superseded by this initialization-aware diagnostic.'])


def main():
    print('Compute measured PM2.5 agreement and time-split forecast backtests',flush=True)
    report=dict(schema='cme-dashboard-validation-v1',generated_at=datetime.now(timezone.utc).isoformat(),
                purpose='decision_support_dashboard',overall_accuracy_percent=None,
                pm25_daily=daily_pm(),pm25_recent=recent_pm(),wind_station=wind_validation())
    print('Compute satellite follow-up coverage with correct initial support and observed-location terrain',flush=True)
    report['fire_followup']=fire_followup()
    inputs=[*sorted(PM.glob('*.csv')),*sorted(PM.glob('cams-*-jan-apr-*.json')),PM/'daily-2025.xlsx',PM/'daily-2026.xlsx',
            OUT/'airport-iem-2026.csv',OUT/'airport-gfs-iem-location.json',
            ROOT/'output/hindcast-2026/summary.json',ROOT/'output/hindcast-2026/firms-points.json']
    report['provenance']=dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        inputs=[dict(file=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                for p in inputs if p.is_file()])
    write(OUT/'summary.json',report);write(ROOT/'backend/app/data/dashboard-validation-2026.json',report)
    print(json.dumps(dict(pm25=report['pm25_daily']['matched_comparison'],recent={k:v['metrics'] for k,v in report['pm25_recent']['by_lead'].items()},
                         wind={k:v['metrics'] for k,v in report['wind_station'].get('by_lead',{}).items()},fire=report['fire_followup']['summary']),ensure_ascii=True),flush=True)


if __name__=='__main__':main()
