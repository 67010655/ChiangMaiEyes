"""Offline Copernicus DSM -> UTM 47N / Horn slope -> RECOFTC polygons.

Install scripts/requirements-terrain.txt locally. Raster packages are deliberately
not production API dependencies. Source COGs and checksums stay in output/terrain.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely import transform

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
OUTPUT = ROOT / 'backend/app/data/forest-terrain-copernicus.json'
SOURCE = 'https://copernicus-dem-30m.s3.amazonaws.com'
LICENSE = 'https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf'
ATTRIBUTION = 'produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved'


def horn_slope(dem: np.ndarray, spacing_m: float = 30) -> np.ndarray:
    """Degrees; all nine finite cells required, never interpolate a missing neighbour."""
    result = np.full(dem.shape, np.nan, dtype=np.float32)
    if min(dem.shape) < 3:
        return result
    a, b, c = dem[:-2, :-2], dem[:-2, 1:-1], dem[:-2, 2:]
    d, e, f = dem[1:-1, :-2], dem[1:-1, 1:-1], dem[1:-1, 2:]
    g, h, i = dem[2:, :-2], dem[2:, 1:-1], dem[2:, 2:]
    valid = np.logical_and.reduce([np.isfinite(x) for x in (a,b,c,d,e,f,g,h,i)])
    dx = ((c+2*f+i)-(a+2*d+g))/(8*spacing_m)
    dy = ((g+2*h+i)-(a+2*b+c))/(8*spacing_m)
    slope = np.degrees(np.arctan(np.hypot(dx,dy)))
    result[1:-1,1:-1] = np.where(valid,slope,np.nan)
    return result


def summary(values: np.ndarray) -> dict | None:
    values = values[np.isfinite(values)]
    if not values.size:
        return None
    return {key:round(float(value),2) for key,value in {
        'min':np.min(values),'median':np.median(values),'mean':np.mean(values),
        'p90':np.percentile(values,90),'max':np.max(values)}.items()}


def merge_native(datasets, bounds):
    """Preserve the Copernicus PixelIsPoint source grid, including tile seams.

    Aligning to integer multiples of resolution shifts these COG origins by
    half a pixel. Snap to the first source transform instead, with a two-pixel
    interpolation halo, and merge before the one destination reprojection.
    """
    west,south,east,north=bounds
    source=datasets[0];rx,ry=source.res;cx,fy=source.transform.c,source.transform.f
    aligned=(cx+(np.floor((west-cx)/rx)-2)*rx,
             fy-(np.ceil((fy-south)/ry)+2)*ry,
             cx+(np.ceil((east-cx)/rx)+2)*rx,
             fy-(np.floor((fy-north)/ry)-2)*ry)
    return merge(datasets,bounds=aligned,nodata=np.nan,masked=True,target_aligned_pixels=False)


def download_tile(tile: tuple[int,int], cache: Path) -> dict:
    lat,lon = tile
    name = f'Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM'
    url = f'{SOURCE}/{name}/{name}.tif'
    meta_path = cache / f'{name}.json'
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf8'))
        target = cache / meta['filename']
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==meta['sha256']:
            return meta
    temporary = cache / f'{name}.part'
    digest = hashlib.sha256(); size = 0
    with httpx.stream('GET',url,timeout=120) as response:
        response.raise_for_status()
        with temporary.open('wb') as stream:
            for chunk in response.iter_bytes(1024*1024):
                digest.update(chunk);size+=len(chunk);stream.write(chunk)
        expected = response.headers.get('content-length')
        if expected and size!=int(expected):
            raise ValueError(f'Incomplete COG {name}')
        sha = digest.hexdigest()
        target = cache / f'{name}-{sha[:16]}.tif'
        temporary.replace(target)
        meta = {'tile':name,'url':url,'filename':target.name,'sha256':sha,'bytes':size,
                'etag':response.headers.get('etag'),'retrieved_at':datetime.now(timezone.utc).isoformat()}
    with rasterio.open(target) as ds:
        if ds.crs.to_epsg()!=4326 or ds.count!=1 or ds.width!=3600 or ds.height!=3600 or ds.dtypes[0]!='float32':
            raise ValueError(f'Unexpected Copernicus grid {name}')
        if not np.isclose(ds.res[0],1/3600) or not np.isclose(ds.res[1],1/3600):
            raise ValueError(f'Unexpected Copernicus spacing {name}')
        meta.update(crs=ds.crs.to_string(),resolution_degrees=list(ds.res),nodata=ds.nodata,
                    pixel_reference=ds.tags().get('AREA_OR_POINT'))
    meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print(json.dumps({'downloaded':name,'bytes':size}),flush=True)
    return meta


def forest_summary(feature, datasets, project) -> dict:
    props = feature['properties']
    fid = str(props.get('forest_id') or props.get('id') or '')
    record = {'forest_id':fid,'status':'boundary_needs_review','elevation_m':None,'slope_deg':None,
              'inside_pixels':0,'slope_valid_pixels':0,'slope_valid_fraction':None}
    geom = shape(feature['geometry'])
    if not geom.is_valid or geom.is_empty or geom.area<=0:
        return record
    projected = transform(geom,project.transform,interleaved=False)
    minx,miny,maxx,maxy = projected.bounds
    west = np.floor(minx/30)*30-90; north = np.ceil(maxy/30)*30+90
    width = int(np.ceil((maxx-west)/30))+3; height = int(np.ceil((north-miny)/30))+3
    if width*height>20_000_000:
        raise ValueError(f'Unexpectedly large forest raster {fid}')
    dst_transform = from_origin(west,north,30,30)
    source_bounds = transform_bounds('EPSG:32647','EPSG:4326',west,north-height*30,west+width*30,north,densify_pts=21)
    relevant = [ds for ds in datasets if not (ds.bounds.right<source_bounds[0] or ds.bounds.left>source_bounds[2] or ds.bounds.top<source_bounds[1] or ds.bounds.bottom>source_bounds[3])]
    if not relevant:
        record['status']='source_unavailable';return record
    mosaic,source_transform = merge_native(relevant,source_bounds)
    dem = np.full((height,width),np.nan,dtype=np.float32)
    reproject(source=mosaic[0].filled(np.nan),destination=dem,src_transform=source_transform,
              src_crs='EPSG:4326',dst_transform=dst_transform,dst_crs='EPSG:32647',
              src_nodata=np.nan,dst_nodata=np.nan,resampling=Resampling.bilinear)
    inside = geometry_mask([mapping(projected)],out_shape=dem.shape,transform=dst_transform,invert=True,all_touched=False)
    slope = horn_slope(dem)
    n = int(inside.sum()); valid = int((inside & np.isfinite(slope)).sum())
    record.update(inside_pixels=n,slope_valid_pixels=valid,slope_valid_fraction=round(valid/n,6) if n else None,
                  area_m2=round(projected.area,2),elevation_m=summary(dem[inside]),slope_deg=summary(slope[inside]),
                  source_tiles=[ds.tags().get('cme_tile') or Path(ds.name).name.split('-')[0] for ds in relevant])
    record['status']='available' if n and valid==n else 'partial' if valid else 'insufficient_resolution' if not n else 'source_unavailable'
    return record


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--limit',type=int);args=parser.parse_args()
    features = json.loads(BOUNDARIES.read_text(encoding='utf8'))['features']
    points = [p for f in features for ring in (f['geometry']['coordinates'] if f['geometry']['type']=='Polygon' else [r for poly in f['geometry']['coordinates'] for r in poly]) for p in ring]
    latitudes = range(int(np.floor(min(p[1] for p in points))),int(np.floor(max(p[1] for p in points)))+1)
    longitudes = range(int(np.floor(min(p[0] for p in points))),int(np.floor(max(p[0] for p in points)))+1)
    cache = ROOT / 'output/terrain/dem';cache.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(lambda t:download_tile(t,cache),[(lat,lon) for lat in latitudes for lon in longitudes]))
    sources.sort(key=lambda s:s['tile'])
    datasets = [rasterio.open(cache/s['filename']) for s in sources]
    project = Transformer.from_crs('EPSG:4326','EPSG:32647',always_xy=True)
    rows = []
    try:
        for feature in features[:args.limit] if args.limit else features:
            rows.append(forest_summary(feature,datasets,project))
            if len(rows)%50==0:print(json.dumps({'forests_processed':len(rows)}),flush=True)
    finally:
        for ds in datasets:ds.close()
    counts = {status:sum(r['status']==status for r in rows) for status in sorted({r['status'] for r in rows})}
    payload = {'schema_version':'cme-terrain-v1','generated_at':datetime.now(timezone.utc).isoformat(),
               'boundary_sha256':hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest(),'forest_count':len(rows),
               'dataset':'Copernicus GLO-30 Public','release':'2021 AWS mirror','surface_kind':'DSM',
               'vertical_unit':'m','vertical_reference':'EGM2008','slope_unit':'degree',
               'horizontal_crs':'EPSG:32647','grid_spacing_m':30,'slope_algorithm':'Horn 3x3',
               'resampling':'bilinear','polygon_sampling':'pixel_center_inside','counts':counts,
               'attribution':ATTRIBUTION,'license_url':LICENSE,
               'liability_notice':'หน่วยงานที่รับผิดชอบ Copernicus ไม่รับผิดชอบต่อการใช้ข้อมูล Copernicus WorldDEM-30 โครงการนี้ไม่ได้รับการรับรองจากผู้ให้ข้อมูล',
               'sources':sources,'forests':rows,
               'notes':['แบบจำลองพื้นผิวรวมต้นไม้และสิ่งปลูกสร้าง ไม่ใช่ความชันพื้นดินที่ตรวจวัดจริง',
                        'ค่าสรุปตามขอบเขตป่า ไม่ใช่ค่าความชัน ณ จุดไฟทุกจุดหรือการรับรองเส้นทางปลอดภัย',
                        'สัดส่วนที่แสดงเป็นจำนวนพิกเซลที่คำนวณความชันได้ ไม่ใช่สัดส่วนพื้นที่จริงแบบละเอียด',
                        'ป่าที่เล็กกว่ากริดอาจไม่มีพิกเซลศูนย์กลางอยู่ภายใน ไม่ขยายขอบเขตหรือเติมค่าคงที่แทน']}
    target = ROOT/'output/terrain/limited-summary.json' if args.limit else OUTPUT
    target.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf8')
    print(json.dumps({'output':str(target),'forests':len(rows),'counts':counts}),flush=True)


if __name__=='__main__':main()
