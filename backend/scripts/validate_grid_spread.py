"""Frozen grid model: future hotspot coverage plus separate weekly scar agreement."""
import hashlib,json,math,sys,time,warnings
from datetime import datetime,timezone
from pathlib import Path
import httpx
import numpy as np
import rasterio
from rasterio.features import rasterize,shapes
from rasterio.transform import from_origin
from rasterio.warp import reproject,Resampling,transform_bounds
from pyproj import Transformer
from shapely.geometry import Point,shape,mapping,box
from shapely.ops import transform,unary_union
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.grid_spread import run,rectangles,VERSION
from app.live_spread import footprint,stamp
from optimize_spread import candidate_inputs
OUT=ROOT/'output/grid-spread-validation-20261017';OUT.mkdir(parents=True,exist_ok=True)
DATA=ROOT/'output/spread-optimization-20261017/quality-filtered'
REFERENCE=ROOT/'output/burn-reference-research'
project=Transformer.from_crs(4326,32647,always_xy=True).transform
reverse=Transformer.from_crs(32647,4326,always_xy=True).transform
warnings.filterwarnings('ignore',category=DeprecationWarning)
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def geometry_grid(result,minute):
    collection=rectangles([k for k,v in result['arrival'].items() if v<=minute],result['grid'])
    return unary_union([transform(project,shape(f['geometry'])) for f in collection['features']])
def matched_area(origins,area,domain):
    low,high=0.,10000.
    for _ in range(15):
        middle=(low+high)/2
        if origins.buffer(middle).intersection(domain).area<area:low=middle
        else:high=middle
    return origins.buffer((low+high)/2).intersection(domain)

def download(url):
    folder=REFERENCE/'tiles';folder.mkdir(exist_ok=True)
    path=folder/url.rsplit('/',1)[-1];receipt=path.with_suffix('.json')
    if not path.exists():
        for attempt in range(3):
            try:
                response=httpx.get(url,timeout=40);response.raise_for_status();path.write_bytes(response.content)
                write(receipt,{'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(response.content).hexdigest(),'bytes':len(response.content)});break
            except httpx.HTTPError:
                if attempt==2:raise
                time.sleep(3)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==read(receipt)['sha256']
    return path,read(receipt)

def reference(case,domain):
    centre=case['centre'];cx,cy=project(centre['longitude'],centre['latitude']);cx=math.floor(cx/20)*20;cy=math.floor(cy/20)*20
    affine=from_origin(cx-5000,cy+5000,20,20);burn=np.zeros((500,500),dtype=np.int16);acquisitions=np.zeros_like(burn)
    bounds=transform_bounds('EPSG:32647','EPSG:4326',cx-5000,cy-5000,cx+5000,cy+5000)
    tiles={t['tile']:t['wgs84_bounds'] for t in read(REFERENCE/'tile-metadata.json')}
    day=case['id'].replace('-','');files=[f for month in read(REFERENCE/'b4-2026-jan-apr-manifest.json') for f in month['files']
       if f['start_date']<=day<=f['end_date'] and box(*tiles[f['tile']]).intersects(box(*bounds))]
    sources=[]
    for f in files:
        path,receipt=download(f['url'])
        with rasterio.open(path) as src:
            assert src.crs.to_epsg()==32647 and src.count==2 and src.res==(20.,20.)
            for band,target in ((1,burn),(2,acquisitions)):
                layer=np.zeros_like(target)
                reproject(rasterio.band(src,band),layer,src_transform=src.transform,src_crs=src.crs,
                          dst_transform=affine,dst_crs='EPSG:32647',resampling=Resampling.nearest)
                np.maximum(target,layer,out=target)
        sources.append({**f,**receipt})
    disk=rasterize([(mapping(domain),1)],out_shape=burn.shape,transform=affine,dtype='uint8').astype(bool)
    return burn,acquisitions,disk,affine,sources

def scar_agreement(geom,burn,acquisitions,disk,affine):
    prediction=rasterize([(mapping(geom),1)],out_shape=burn.shape,transform=affine,dtype='uint8').astype(bool) if not geom.is_empty else np.zeros_like(disk)
    acquisition_support=disk&(acquisitions>0);predicted=prediction&acquisition_support;label=(burn>0)&acquisition_support
    intersection=int((predicted&label).sum());union=int((predicted|label).sum())
    return {'source_acquisition_support_fraction':float(acquisition_support.sum()/disk.sum()),
            'predicted_area_ha':float((prediction&disk).sum()*.04),'evaluated_predicted_area_ha':float(predicted.sum()*.04),
            'reference_scar_area_ha':float(label.sum()*.04),'intersection_ha':intersection*.04,
            'unconfirmed_prediction_area_ha':float((predicted&~label).sum()*.04),
            'weekly_reference_iou':intersection/union if union else None,
            'forecast_area_with_detected_scar_fraction':intersection/int(predicted.sum()) if predicted.any() else None,
            'note':'No-detection is not verified unburned. Weekly scar is not a six-hour arrival perimeter.'}

def evaluate(case):
    frozen={'moisture':8,'wind_factor':.2,'slope_factor':1};inputs=[{'point':p,'steps':steps} for p,steps in candidate_inputs(case,frozen)]
    start=stamp(case['as_of']);cx,cy=project(case['centre']['longitude'],case['centre']['latitude']);domain=Point(cx,cy).buffer(5000)
    origins=unary_union([Point(*project(p['longitude'],p['latitude'])) for p in case['initial']]);stationary=origins.buffer(375).intersection(domain)
    began=time.perf_counter();grid=run(inputs,as_of=case['as_of']);runtime=time.perf_counter()-began
    no_landcover=run(inputs,as_of=case['as_of'],use_landcover=False)
    rows={name:{'covered':0,'covered_375m':0,'equal_area_covered_375m':0,'area_ratios':[]} for name in ('current_wavelet','grid_terrain','grid_terrain_landcover')}
    bytime={}
    for p in case['later']:
        minute=(stamp(p['detected_at'])-start).total_seconds()/60;bytime.setdefault(minute,[]).append(Point(*project(p['longitude'],p['latitude'])))
    for minute,observed in bytime.items():
        geometries={'current_wavelet':unary_union([transform(project,shape(footprint(i['point'],i['steps'],minute))) for i in inputs]).intersection(domain),
           'grid_terrain':geometry_grid(no_landcover,minute).intersection(domain),'grid_terrain_landcover':geometry_grid(grid,minute).intersection(domain)}
        for name,geom in geometries.items():
            expanded=geom.buffer(375).intersection(domain);equal=matched_area(origins,expanded.area,domain)
            row=rows[name];row['covered']+=sum(geom.covers(p) for p in observed);row['covered_375m']+=sum(expanded.covers(p) for p in observed)
            row['equal_area_covered_375m']+=sum(equal.covers(p) for p in observed);row['area_ratios'].append(expanded.area/stationary.area)
    for row in rows.values():row['mean_area_ratio']=sum(row.pop('area_ratios'))/len(bytime)
    burn,acquisitions,disk,affine,sources=reference(case,domain)
    final={'current_wavelet':unary_union([transform(project,shape(footprint(i['point'],i['steps'],360))) for i in inputs]).intersection(domain),
       'grid_terrain':geometry_grid(no_landcover,360).intersection(domain),'grid_terrain_landcover':geometry_grid(grid,360).intersection(domain)}
    agreement={}
    for name,geom in final.items():
        agreement[name]=scar_agreement(geom,burn,acquisitions,disk,affine)
        agreement[name]['equal_area_baseline']=scar_agreement(matched_area(origins,geom.area,domain),burn,acquisitions,disk,affine)
    example=None
    if case['id']=='2026-03-23':
        label=(burn>0)&disk
        reference_geo=unary_union([shape(g) for g,value in shapes(label.astype('uint8'),mask=label,transform=affine) if value])
        example={'id':case['id'],'as_of':case['as_of'],'initial':case['initial'],'later':case['later'],
             'geometry':{name:mapping(transform(reverse,geom)) for name,geom in final.items()},
             'weekly_reference':mapping(transform(reverse,reference_geo)),'sources':sources}
    record={'id':case['id'],'split':'test' if case['id']>'2026-03-22' else 'development','points':len(case['later']),
       'initial':len(case['initial']),'grid_used_origins':grid['used_origins'],'grid_excluded':grid['excluded'],'truncated':grid['truncated'],
       'runtime_seconds':runtime,'models':rows,'weekly_reference':{'source_files':sources,'metrics':agreement}}
    write(OUT/(case['id']+'.json'),record)
    if example:write(OUT/'example.json',example)
    print(case['id'],len(case['later']),{k:v['covered'] for k,v in rows.items()},'reference',len(sources),flush=True)
    return record

def aggregate(cases):
    result={}
    for name in ('current_wavelet','grid_terrain','grid_terrain_landcover'):
        points=sum(c['points'] for c in cases);count=len(cases)
        block={k:sum(c['models'][name][k] for c in cases) for k in ('covered','covered_375m','equal_area_covered_375m')}
        block['mean_case_area_ratio']=sum(c['models'][name]['mean_area_ratio'] for c in cases)/count
        valid=[c['weekly_reference']['metrics'][name] for c in cases if c['weekly_reference']['source_files'] and c['weekly_reference']['metrics'][name]['source_acquisition_support_fraction']>0]
        reference_keys=('predicted_area_ha','evaluated_predicted_area_ha','reference_scar_area_ha','intersection_ha','unconfirmed_prediction_area_ha')
        block['weekly_reference']={'cases':len(valid),**{k:sum(v[k] for v in valid) for k in reference_keys},
           'equal_area_intersection_ha':sum(v['equal_area_baseline']['intersection_ha'] for v in valid)}
        result[name]=block
    return {'cases':len(cases),'points':sum(c['points'] for c in cases),'models':result}

def main():
    cases=[c for c in read(DATA/'cases.json') if c['later']];records=[]
    protocol={'model_version':VERSION,'settings':{'fuel':'FM1 unmeasured reference','moisture_pct':8,'wind_factor':.2,'max_cells':30000},
      'selection':'Reuse frozen daily-centre cases and chronological split. No tuning on weekly scars.',
      'reference':'TamRoyPao Sentinel-2 20m B4 weekly detection-count raster and acquisition-count band; independent from thermal hotspots but forest accuracy unvalidated.',
      'timing_limit':'Six-hour footprints compared with seven-day scar maps only for spatial agreement. Not arrival-time or actual burn-perimeter accuracy.',
      'absence_limit':'Band2>0 is not a cloud-free QA guarantee. Unconfirmed area is not false-positive area.',
      'landcover_limit':'2021 historical cell-centre classification; does not measure 2026 fuel or firebreaks.'}
    write(OUT/'protocol.json',protocol)
    for case in cases:
        path=OUT/(case['id']+'.json');records.append(read(path) if path.exists() else evaluate(case))
    report={'schema':'cme-grid-validation-v1','protocol':protocol,'development':aggregate([c for c in records if c['split']=='development']),
        'test':aggregate([c for c in records if c['split']=='test']),'runtime_max_seconds':max(c['runtime_seconds'] for c in records),
        'truncated_cases':sum(c['truncated'] for c in records),'cases':records}
    write(OUT/'summary.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ('cases','protocol')}),flush=True)

if __name__=='__main__':main()
