"""Compact ~110 m DSM grid from verified local Copernicus tiles; offline only."""
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.providers.hotspot_provider import _province_ring
from build_forest_terrain import ATTRIBUTION, LICENSE


def main():
    ring = _province_ring(); step = .001
    west = math.floor(min(p[0] for p in ring) / step) * step - 2*step
    north = math.ceil(max(p[1] for p in ring) / step) * step + 2*step
    width = math.ceil((max(p[0] for p in ring) - west) / step) + 2
    height = math.ceil((north - min(p[1] for p in ring)) / step) + 2
    grid = np.full((height, width), -32768, dtype='<i2')
    transform = from_origin(west, north, step, step)
    sources = []
    for file in sorted((ROOT / 'output/terrain/dem').glob('*.json')):
        meta = json.loads(file.read_text(encoding='utf8')); path = file.parent / meta['filename']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta['sha256']
        with rasterio.open(path) as src:
            reproject(rasterio.band(src, 1), grid, src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=transform, dst_crs='EPSG:4326',
                      dst_nodata=-32768, init_dest_nodata=False, resampling=Resampling.average)
        sources.append({'filename': meta['filename'], 'sha256': meta['sha256']})
    raw = grid.astype('<i2').tobytes(); compressed = gzip.compress(raw, mtime=0)
    target = ROOT / 'backend/app/data/forecast-terrain.bin.gz'; target.write_bytes(compressed)
    metadata = {'version': 'copernicus-average-0.001deg-v1', 'west': west, 'north': north,
                'step_degrees': step, 'width': width, 'height': height, 'nodata': -32768,
                'sha256': hashlib.sha256(raw).hexdigest(), 'source_tiles': sources,
                'method': 'Average resampling of GLO-30 DSM to 0.001 degrees; local 3x3 Horn slope at runtime.',
                'meaning': 'Approximately 105-111 m grid, not the original 30 m resolution; includes canopy/buildings.',
                'attribution': ATTRIBUTION, 'license_url': LICENSE}
    (target.parent / 'forecast-terrain.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
    print({'shape': grid.shape, 'compressed_bytes': len(compressed), 'valid_cells': int((grid != -32768).sum())})


if __name__ == '__main__': main()
