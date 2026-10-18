"""One explicitly located DSM sample per valid forest; not a forest-wide slope.

Reuses the verified local Copernicus COGs. No runtime raster dependencies.
Each 3x3 patch is centred on a point inside the original polygon, projected
to UTM47N and bilinearly resampled at 30 m. Horn derivatives give upslope.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, transform_bounds
from pyproj import Transformer
from shapely.geometry import shape

from build_forest_terrain import BOUNDARIES, ROOT, ATTRIBUTION, LICENSE, merge_native


def main():
    project = Transformer.from_crs(4326,32647,always_xy=True)
    sources=[]; records={}
    for path in sorted((ROOT/'output/terrain/dem').glob('*.json')):
        meta=json.loads(path.read_text(encoding='utf8'))
        raster_path=path.parent/meta['filename']
        if hashlib.sha256(raster_path.read_bytes()).hexdigest()!=meta['sha256']:
            raise ValueError('Copernicus tile checksum mismatch')
        sources.append((meta,rasterio.open(raster_path)))
    for feature in json.loads(BOUNDARIES.read_text(encoding='utf8'))['features']:
        fid=feature['properties'].get('forest_id') or feature['properties']['id'];geom=shape(feature['geometry'])
        if not geom.is_valid or geom.is_empty or geom.area<=0:
            records[fid]={'status':'boundary_needs_review'};continue
        point=geom.representative_point();lon,lat=point.x,point.y;x,y=project.transform(lon,lat)
        patch=np.full((3,3),np.nan,dtype='float32')
        bounds=transform_bounds(32647,4326,x-45,y-45,x+45,y+45,densify_pts=21)
        relevant=[(meta,ds) for meta,ds in sources if ds.bounds.left-.002<=lon<=ds.bounds.right+.002 and ds.bounds.bottom-.002<=lat<=ds.bounds.top+.002]
        used=[meta['sha256'] for meta,_ in relevant]
        mosaic,source_transform=merge_native([ds for _,ds in relevant],bounds)
        reproject(mosaic[0].filled(np.nan),patch,src_transform=source_transform,src_crs='EPSG:4326',
                  src_nodata=np.nan,dst_nodata=np.nan,dst_transform=from_origin(x-45,y+45,30,30),
                  dst_crs='EPSG:32647',resampling=Resampling.bilinear)
        if not np.isfinite(patch).all():
            records[fid]={'status':'source_unavailable'};continue
        a,b,c,d,e,f,g,h,i=map(float,patch.ravel())
        dz_e=((c+2*f+i)-(a+2*d+g))/240
        dz_n=((a+2*b+c)-(g+2*h+i))/240
        slope=float(np.degrees(np.arctan(np.hypot(dz_e,dz_n))))
        # UTM grid north -> true north by projecting a small northward step.
        xn,yn=project.transform(lon,lat+.0001)
        grid_bearing=(float(np.degrees(np.arctan2(dz_e,dz_n)))+360)%360
        true_north_grid=float(np.degrees(np.arctan2(xn-x,yn-y)))
        upslope=(grid_bearing-true_north_grid)%360 if slope>1e-10 else 0.0
        records[fid]={'status':'available','latitude':lat,'longitude':lon,
                      'elevation_m':e,'slope_deg':slope,'upslope_to_deg':upslope,
                      'sample_sha256':hashlib.sha256(patch.astype('<f4').tobytes()).hexdigest(),
                      'source_tile_sha256':used}
    for _,ds in sources:ds.close()
    doc={'boundary_sha256':hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest(),
         'metadata':{'dataset':'Copernicus GLO-30 DSM','release':'2021 AWS public mirror',
          'generated_at':datetime.now(timezone.utc).isoformat(),'spacing_m':30,
          'method':'3x3 Horn / bilinear UTM47N, heading converted to true north',
          'point_method':'Shapely representative_point inside original valid boundary',
          'meaning':'A synthetic ignition location with terrain sampled at that point; not an observed fire location or the slope of the whole forest',
          'limitation':'DSM includes canopy and buildings; slope fixed across each scenario, not a spatial raster propagation',
          'attribution':ATTRIBUTION,'license_url':LICENSE,
          'liability_notice':'The organizations supplying Copernicus data do not endorse or accept liability for this derived scenario'},
         'points':records}
    target=ROOT/'backend/app/data/forest-terrain-points.json'
    target.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf8')
    print(json.dumps({'records':len(records),'available':sum(v['status']=='available' for v in records.values()),'bytes':target.stat().st_size}))


if __name__=='__main__':main()
