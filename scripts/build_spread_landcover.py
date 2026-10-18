"""Download bounded WorldCover COG windows onto the existing terrain grid."""
import gzip,hashlib,json,math
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling

ROOT=Path(__file__).resolve().parents[1]
def main():
    meta=json.loads((ROOT/'backend/app/data/forecast-terrain.json').read_text())
    grid=np.zeros((meta['height'],meta['width']),dtype='uint8');step=meta['step_degrees']
    transform=from_origin(meta['west'],meta['north'],step,step)
    west=meta['west'];east=west+grid.shape[1]*step;north=meta['north'];south=north-grid.shape[0]*step
    sources=[]
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='45'):
        for lat in range(math.floor(south/3)*3,math.ceil(north/3)*3,3):
            for lon in range(math.floor(west/3)*3,math.ceil(east/3)*3,3):
                name=f'ESA_WorldCover_10m_2021_v200_N{lat:02d}E{lon:03d}_Map.tif'
                url='https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/'+name
                with rasterio.open(url) as src:
                    assert src.crs.to_epsg()==4326 and src.count==1 and src.nodata==0
                    with WarpedVRT(src,crs='EPSG:4326',transform=transform,width=grid.shape[1],height=grid.shape[0],resampling=Resampling.nearest,nodata=0) as vrt:
                        layer=vrt.read(1)
                    valid=layer!=0;grid[valid]=layer[valid]
                    sources.append({'url':url,'crs':str(src.crs),'native_transform':list(src.transform),'native_shape':list(src.shape)})
                print(name,int(valid.sum()),flush=True)
    raw=grid.tobytes();output=ROOT/'backend/app/data/spread-landcover.bin.gz';output.write_bytes(gzip.compress(raw,mtime=0))
    metadata={**{k:meta[k] for k in ('west','north','step_degrees','width','height')},'version':'esa-worldcover2021-nearest-0.001deg-v1',
       'sha256':hashlib.sha256(raw).hexdigest(),'nodata':0,'sources':sources,'reference_year':2021,
       'classes':{'10':'tree','20':'shrub','30':'grass','40':'crop','50':'built-up','60':'bare/sparse','70':'snow/ice','80':'water','90':'herbaceous wetland','95':'mangroves','100':'moss/lichen'},
       'blocked_classes':[0,50,60,70,80],'method':'Nearest-neighbour categorical resampling onto the terrain grid; cell-centre class, not majority or proof of a complete barrier.',
       'meaning':'Historical land-cover mask only. It does not measure fuel loading, moisture, firebreak width or 2026 land-use changes.',
       'attribution':'© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium',
       'license':'CC BY 4.0','source_url':'https://esa-worldcover.org/en/data-access'}
    (output.parent/'spread-landcover.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
    print('bytes',output.stat().st_size,'classes',dict(zip(*[a.tolist() for a in np.unique(grid,return_counts=True)])),flush=True)

if __name__=='__main__':main()
