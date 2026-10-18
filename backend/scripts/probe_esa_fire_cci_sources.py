"""Small, read-only public-source availability probe; no application integration."""
from pathlib import Path
import hashlib
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output' / 'source-review-20261018' / 'esa-fire'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.append(str(ROOT / 'output' / 'spread-deps'))
import numpy as np
import rasterio
from rasterio.windows import from_bounds

def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()

base = 'https://data.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN'
grid_listing = json.loads(get(base + '/grid/v1.1/2024?json'))
year_listing = json.loads(get(base + '/pixel/v1.1/uncompressed?json'))
entry = next(x for x in grid_listing['items'] if x['name'].startswith('20240301'))
data = get(entry['download'])
assert len(data) == entry['size'], 'Catalog size mismatch'
assert hashlib.md5(data).hexdigest() == entry['md5'], 'Catalog checksum mismatch'
path = OUT / entry['name']
path.write_bytes(data)
with rasterio.open(path) as src:
    tags, subdatasets = src.tags(), src.subdatasets
variables = {}
for variable in ['burned_area', 'standard_error', 'fraction_of_burnable_area', 'fraction_of_observed_area']:
    with rasterio.open(f'NETCDF:"{path}":{variable}') as src:
        window = from_bounds(98.5, 18.0, 99.5, 19.0, src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=window, masked=True)
        variables[variable] = {'shape':list(src.shape),'crs':str(src.crs),'transform':list(src.transform),
                              'bounds':list(src.bounds),'nodata':src.nodata,'tags':src.tags(1),
                              'example_box_98_5_18_0_99_5_19_0':arr.filled(float('nan')).tolist()}
summary = {'source_listing':base+'/grid/v1.1/2024?json','pixel_year_listing':base+'/pixel/v1.1/uncompressed?json',
           'available_pixel_years':[x['name'] for x in year_listing['items'] if x['type']=='dir'],
           'entry':entry,'download_bytes':len(data),'md5':hashlib.md5(data).hexdigest(),
           'sha256':hashlib.sha256(data).hexdigest(),'netcdf_tags':tags,'subdatasets':subdatasets,'variables':variables,
           'scope_note':'Example is a 1-degree box around Chiang Mai, not the administrative province polygon.'}
modis_url = 'https://data.ceda.ac.uk/neodc/esacci/fire/data/burned_area/MODIS/pixel/v5.1/compressed?json'
summary['modis_pixel_year_listing'] = modis_url
summary['available_modis_pixel_years'] = [x['name'] for x in json.loads(get(modis_url))['items'] if x['name'].isdigit()]
(OUT/'probe.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
print(json.dumps({'download_bytes':len(data),'catalog_md5_verified':entry.get('md5')==summary['md5'],
                  'years':summary['available_pixel_years'],'variables':{k:v['example_box_98_5_18_0_99_5_19_0'] for k,v in variables.items()}},ensure_ascii=False))
