"""Position-based terrain lookup without raster packages in production."""
import array
import gzip
import hashlib
import json
import math
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def dataset():
    root = Path(__file__).parent / 'data'
    meta = json.loads((root / 'forecast-terrain.json').read_text(encoding='utf8'))
    raw = gzip.decompress((root / 'forecast-terrain.bin.gz').read_bytes())
    if len(raw) != 2*meta['width']*meta['height'] or hashlib.sha256(raw).hexdigest() != meta['sha256']:
        raise ValueError('Forecast terrain checksum mismatch')
    values = array.array('h'); values.frombytes(raw)
    if sys.byteorder != 'little': values.byteswap()
    return meta, values


def at(latitude, longitude):
    meta, values = dataset(); step = meta['step_degrees']; w = meta['width']; h = meta['height']
    col = math.floor((longitude - meta['west']) / step)
    row = math.floor((meta['north'] - latitude) / step)
    if not (1 <= col < w-1 and 1 <= row < h-1): return None
    patch = [values[(row+dy)*w+col+dx] for dy in (-1,0,1) for dx in (-1,0,1)]
    if meta['nodata'] in patch: return None
    a,b,c,d,e,f,g,h_,i = patch
    dy = math.radians(step)*6371008.8; dx = dy*math.cos(math.radians(latitude))
    east = (c+2*f+i-a-2*d-g)/(8*dx); north = (a+2*b+c-g-2*h_-i)/(8*dy)
    slope = math.degrees(math.atan(math.hypot(east, north)))
    return {'slope_deg': slope, 'upslope_to_deg': math.degrees(math.atan2(east, north)) % 360 if slope else 0,
            'elevation_m': e, 'grid_latitude': meta['north']-(row+.5)*step,
            'grid_longitude': meta['west']+(col+.5)*step, 'grid_spacing_m': [dx,dy],
            'dataset_sha256': meta['sha256'], 'method': meta['method']}
