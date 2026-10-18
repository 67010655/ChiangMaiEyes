"""Clip licensed CGLS-LC100 2019 at native resolution and summarize 677 forests.

Offline only: use scripts/requirements-terrain.txt. No GDAL/NumPy is needed by
the API. Downloads bounded TIFF windows via HTTP Range, not the global raster.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds, transform as window_transform
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'backend/app/data'
SOURCE = 'https://zenodo.org/records/3939050/files/PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif?download=1'
GROUPS = {
    'deciduous': {'label': 'ป่าผลัดใบ', 'codes': [113, 114, 123, 124]},
    'evergreen': {'label': 'ป่าไม่ผลัดใบ', 'codes': [111, 112, 121, 122]},
    'mixed_forest': {'label': 'ป่าผสมหลายชนิด (ยังแยกผลัดใบไม่ได้)', 'codes': [115, 125]},
    'unknown_forest': {'label': 'พื้นที่ต้นไม้ (ยังระบุชนิดป่าไม่ได้)', 'codes': [116, 126]},
    'shrub': {'label': 'ไม้พุ่ม', 'codes': [20]},
    'grass': {'label': 'ทุ่งหญ้า', 'codes': [30]},
    'crop': {'label': 'พื้นที่เกษตร', 'codes': [40]},
    'built': {'label': 'ชุมชนและสิ่งปลูกสร้าง', 'codes': [50]},
    'bare': {'label': 'พื้นที่โล่งหรือพืชเบาบาง', 'codes': [60]},
    'water': {'label': 'แหล่งน้ำ', 'codes': [80, 200]},
    'wetland': {'label': 'พื้นที่ชุ่มน้ำ', 'codes': [90]},
    'other': {'label': 'พื้นที่ชนิดอื่น', 'codes': [70, 100]},
}


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def summarize_forests(grid, transform, features):
    result = {}
    whole = Window(0, 0, grid.shape[1], grid.shape[0])
    for feature in features:
        key = feature['properties']['id']
        geometry = feature.get('geometry')
        polygon = shape(geometry)
        if not polygon.is_valid or polygon.is_empty:
            result[key] = {'status': 'invalid_boundary', 'forest_types': [], 'composition': []}
            continue
        try:
            floating = from_bounds(*polygon.bounds, transform=transform)
            col = math.floor(floating.col_off); row = math.floor(floating.row_off)
            win = Window(col, row, math.ceil(floating.col_off + floating.width) - col,
                         math.ceil(floating.row_off + floating.height) - row).intersection(whole)
        except rasterio.errors.WindowError:
            result[key] = {'status': 'outside_coverage', 'forest_types': [], 'composition': []}
            continue
        local_transform = window_transform(win, transform)
        local = grid[int(win.row_off):int(win.row_off + win.height), int(win.col_off):int(win.col_off + win.width)]
        inside = geometry_mask([geometry], out_shape=local.shape, transform=local_transform, invert=True, all_touched=False)
        valid = inside & (local != 255) & (local != 0)
        if not valid.any():
            result[key] = {'status': 'no_valid_cell_centers', 'forest_types': [], 'composition': []}
            continue
        # Longitude/latitude cells have different surface area by latitude.
        # Cosine weights avoid treating degree-square areas as equal-area units.
        latitudes = local_transform.f + (np.arange(local.shape[0]) + .5) * local_transform.e
        weights = np.broadcast_to(np.cos(np.radians(latitudes))[:, None], local.shape)
        total = float(weights[valid].sum())
        composition = []
        for group, definition in GROUPS.items():
            selected = valid & np.isin(local, definition['codes'])
            if selected.any():
                composition.append({'kind': group, 'label': definition['label'],
                    'percent': round(float(weights[selected].sum()) / total * 100, 2), 'cells': int(selected.sum())})
        composition.sort(key=lambda entry: (-entry['percent'], entry['kind']))
        result[key] = {'status': 'sampled', 'valid_cells': int(valid.sum()), 'boundary_cell_centers': int(inside.sum()),
            'forest_types': [entry['label'] for entry in composition if entry['kind'] in ('deciduous', 'evergreen', 'mixed_forest', 'unknown_forest')],
            'composition': composition}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-only', action='store_true', help='Only synchronize the public reference table')
    args = parser.parse_args()
    reference_path = DATA / 'land-context-reference.json'
    json.loads(reference_path.read_text(encoding='utf-8'))
    (ROOT / 'frontend/public/land-context-reference.json').write_bytes(reference_path.read_bytes())
    if args.reference_only:
        print('Synchronized public reference table', flush=True)
        return
    record = httpx.get('https://zenodo.org/api/records/3939050', timeout=30).raise_for_status().json()
    if record['metadata']['license']['id'] != 'cc-by-4.0':
        raise ValueError('Review publisher license before generating a derivative')
    source_file = next(f for f in record['files'] if 'Discrete-Classification-map' in f['key'])
    province_doc = json.loads((ROOT / 'frontend/public/chiangmai-province.json').read_text(encoding='utf-8'))
    province_geometries = [f['geometry'] for f in province_doc['features']] if province_doc['type'] == 'FeatureCollection' else [province_doc['geometry']] if province_doc['type'] == 'Feature' else [province_doc]
    from shapely.ops import unary_union
    bounds = unary_union([shape(g) for g in province_geometries]).bounds
    print('Reading native 100 m Chiang Mai window', bounds, flush=True)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='45', GDAL_HTTP_MAX_RETRY='3'):
        with rasterio.open(SOURCE) as src:
            if src.crs.to_epsg() != 4326 or src.count != 1 or src.dtypes[0] != 'uint8' or src.nodata != 255:
                raise ValueError('Unexpected source CRS, dtype, bands or nodata')
            floating = from_bounds(*bounds, transform=src.transform)
            col, row = math.floor(floating.col_off), math.floor(floating.row_off)
            win = Window(col, row, math.ceil(floating.col_off + floating.width) - col,
                         math.ceil(floating.row_off + floating.height) - row)
            grid = src.read(1, window=win)
            transform = window_transform(win, src.transform)
            source_transform = list(src.transform)
    inside = geometry_mask(province_geometries, out_shape=grid.shape, transform=transform, invert=True, all_touched=False)
    grid[~inside] = 255
    raw = grid.tobytes()
    (DATA / 'forest-landcover.bin.gz').write_bytes(gzip.compress(raw, mtime=0))
    metadata = {'version': 'cgls-lc100-2019-native-chiangmai-v1', 'product': 'CGLS-LC100 Collection 3 v3.0.1',
        'reference_year': 2019, 'crs': 'EPSG:4326', 'native_resolution_m': 100,
        'west': transform.c, 'north': transform.f, 'step_degrees': transform.a,
        'width': grid.shape[1], 'height': grid.shape[0], 'nodata': 255, 'unknown': 0,
        'sha256': hashlib.sha256(raw).hexdigest(), 'source_url': SOURCE, 'source_checksum': source_file['checksum'],
        'source_transform': source_transform, 'license': 'CC BY 4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'doi': '10.5281/zenodo.3939050', 'attribution': 'Buchhorn et al. (2020), Copernicus Global Land Service, Collection 3, epoch 2019. Contains modified Copernicus information [2019].',
        'method': 'Native-resolution categorical crop, no interpolation; outside Chiang Mai province cell centers set to nodata.',
        'province_boundary_sha256': hashlib.sha256((ROOT / 'frontend/public/chiangmai-province.json').read_bytes()).hexdigest(),
        'meaning': 'Historical mapped land cover, not a current forest inventory, fire perimeter or fuel-load measurement.', 'groups': GROUPS}
    dump(DATA / 'forest-landcover.json', metadata)
    forest_path = DATA / 'community-forests-chiangmai.geojson'
    features = json.loads(forest_path.read_text(encoding='utf-8'))['features']
    summaries = summarize_forests(grid, transform, features)
    dump(DATA / 'community-forest-landcover.json', {'version': metadata['version'], 'reference_year': 2019,
        'source_url': SOURCE, 'license': metadata['license'], 'grid_sha256': metadata['sha256'],
        'boundary_sha256': hashlib.sha256(forest_path.read_bytes()).hexdigest(),
        'method': 'Native cell-center samples inside valid polygons; cosine-latitude area weights; fractions of valid classified samples, not a surveyed area. No smoothing or subtype inference.',
        'forests': summaries})
    from collections import Counter
    print('Wrote', grid.shape, len(raw), 'bytes; forests:', dict(Counter(s['status'] for s in summaries.values())), flush=True)


if __name__ == '__main__':
    main()
