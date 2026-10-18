"""Retrieve time-stamped Sentinel2 triplets and one-run forecast for fire hindcasts.

Independent optical reference, not verified ground truth. Retrospective initial
imagery is assumed immediately available; acquisition-to-publication delay is
reported separately. No production outputs are written.
"""
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
sys.path.append(str(Path(__file__).resolve().parents[2] / 'output/spread-deps'))
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from pyproj import Transformer
from scipy.ndimage import label
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/fire-perimeter-loop-20261017'
PROJECT = Transformer.from_crs(4326, 32647, always_xy=True)
INVERSE = Transformer.from_crs(32647, 4326, always_xy=True)
UTC = timezone.utc
ASSETS = ('scl', 'nir08', 'swir22', 'red')


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_points(year):
    points = [p for p in read(ROOT / f'output/hindcast-{year}/firms-points.json') if p.get('confidence') != 'l']
    points.sort(key=lambda p: p['detected_at'])
    times = np.array([stamp(p['detected_at']).timestamp() for p in points])
    xy = np.column_stack(PROJECT.transform([p['longitude'] for p in points], [p['latitude'] for p in points]))
    return points, times, xy


def choose_candidates():
    # Validation cases are selected solely from2025detections, before any optical
    # or model score is read.2026uses all8previously identified study centres.
    points, times, xy = source_points(2025)
    candidates = []
    for day in sorted(set(p['detected_at'][:10] for p in points if p['detected_at'][5:7] in ('03', '04'))):
        selected = np.array([i for i, p in enumerate(points) if p['detected_at'][:10] == day], dtype=int)
        if not len(selected):
            continue
        locations = xy[selected]
        counts = cKDTree(locations).query_ball_point(locations, 1500, return_length=True)
        best = int(np.argmax(counts))
        p = points[selected[best]]
        candidates.append({'id': day, 'year': 2025, 'latitude': p['latitude'], 'longitude': p['longitude'], 'initial_neighbour_count': int(counts[best])})
    validation = []
    for candidate in sorted(candidates, key=lambda p: (-p['initial_neighbour_count'], p['id'])):
        location = np.array(PROJECT.transform(candidate['longitude'], candidate['latitude']))
        if all(np.linalg.norm(location - np.array(PROJECT.transform(p['longitude'], p['latitude']))) >= 12000 for p in validation):
            validation.append(candidate)
        if len(validation) == 6:
            break
    tests = read(ROOT / 'backend/app/data/dashboard-validation-2026.json')['fire_followup']['cases']
    testing = [{'id': c['id'], 'year': 2026, 'latitude': c['initial'][0]['latitude'], 'longitude': c['initial'][0]['longitude']} for c in tests]
    return validation + testing


def catalog(candidate):
    if candidate.get('catalog_source'):
        return read(OUT / candidate['catalog_source'])
    path = OUT / 'catalogs' / ('c1-' + candidate['id'] + '.json')
    if path.exists():
        return read(path)
    date = datetime.fromisoformat(candidate.get('date', candidate['id'])).replace(tzinfo=UTC)
    params = {'collections': 'sentinel-2-c1-l2a', 'bbox': ','.join(map(str, [candidate['longitude']-.07, candidate['latitude']-.07, candidate['longitude']+.07, candidate['latitude']+.07])),
              'datetime': (date-timedelta(days=14)).isoformat() + '/' + (date+timedelta(days=12)).isoformat(), 'limit': 100}
    response = httpx.get('https://earth-search.aws.element84.com/v1/search', params=params, timeout=60)
    response.raise_for_status()
    body = response.json()
    # Earth Search may emit a next link even for a short final page.
    features = {item['id']: item for item in body.get('features', [])}
    page = body
    seen = set()
    while page.get('features'):
        link = next((link for link in page.get('links', []) if link.get('rel') == 'next'), None)
        if link is None:
            break
        if link['href'] in seen or len(seen) >= 10:
            raise ValueError('Catalog pagination repeated or exceeded bounded query limit.')
        seen.add(link['href'])
        response = httpx.get(link['href'], timeout=60)
        response.raise_for_status()
        page = response.json()
        features.update({item['id']: item for item in page.get('features', [])})
    body['features'] = list(features.values())
    body['pagination_requests'] = len(seen)
    body['links'] = [link for link in body.get('links', []) if link.get('rel') != 'next']
    write(path, body)
    return body


def crop_scene(item, bounds, folder):
    name = item['id']
    destination = folder / (name + '.npz')
    receipt = destination.with_suffix('.json')
    if destination.exists() and receipt.exists():
        assert sha(destination) == read(receipt)['sha256']
        assert read(receipt)['grid']['bounds'] == bounds, 'Cached crop extent changed; use a unique case ID.'
        return dict(np.load(destination))
    west, south, east, north = bounds
    profile = {'crs': 'EPSG:32647', 'transform': from_origin(west, north, 20, 20), 'width': 500, 'height': 500}
    arrays = {}
    metadata = {}
    for key in ASSETS:
        asset = item['assets'][key]
        with rasterio.open(asset['href']) as dataset:
            assert dataset.crs.to_epsg() == 32647
            window = from_bounds(*bounds, transform=dataset.transform)
            if min(window.col_off, window.row_off) < 0 or window.col_off + window.width > dataset.width or window.row_off + window.height > dataset.height:
                raise ValueError('Fixed10kmcase window crosses tile boundary; use another complete tile.')
            raw = dataset.read(1, window=window, out_shape=(500, 500), resampling=Resampling.nearest if key == 'scl' else Resampling.average)
            specification = asset['raster:bands'][0]
            if key == 'scl':
                arrays[key] = raw.astype('uint8')
                if np.isin(arrays[key], (4, 5)).mean() < .65:
                    raise ValueError('Initial SCL read shows less than65percentclearland; try another image triplet.')
            else:
                scale, offset = specification['scale'], specification.get('offset', 0)
                values = raw.astype('float32') * scale + offset
                values[raw == specification.get('nodata', 0)] = np.nan
                arrays[key] = values
            metadata[key] = {'href': asset['href'], 'raster_band': specification, 'native_resolution_m': list(dataset.res), 'source_crs': str(dataset.crs)}
        print('BAND_READ', folder.name, name, key, flush=True)
    arrays['valid'] = np.isin(arrays['scl'], (4, 5)) & np.isfinite(arrays['nir08']) & np.isfinite(arrays['swir22']) & np.isfinite(arrays['red'])
    arrays['valid'] &= (arrays['nir08'] > 0) & (arrays['swir22'] >= 0) & (arrays['red'] >= 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        arrays['nbr'] = (arrays['nir08'] - arrays['swir22']) / (arrays['nir08'] + arrays['swir22'])
        arrays['ndvi'] = (arrays['nir08'] - arrays['red']) / (arrays['nir08'] + arrays['red'])
    arrays['valid'] &= np.isfinite(arrays['nbr']) & np.isfinite(arrays['ndvi'])
    np.savez_compressed(destination, **arrays)
    write(receipt, {'item_id': name, 'acquisition': item['properties']['datetime'], 'catalog_created': item['properties'].get('created'),
         'processing_baseline': item['properties'].get('s2:processing_baseline'), 'assets': metadata,
         'calibration': 'Apply asset raster:bands scale and offset exactly once; do not infer calibration from boa_offset_applied boolean.',
         'grid': {'epsg': 32647, 'bounds': bounds, 'resolution_m': 20, 'shape': [500, 500]}, 'valid_fraction': float(arrays['valid'].mean()), 'sha256': sha(destination)})
    return arrays


def read_scl(item, bounds, folder):
    existing = folder / (item['id']+'.npz')
    if existing.exists():
        receipt = read(existing.with_suffix('.json'))
        assert receipt['grid']['bounds'] == bounds
        with np.load(existing) as cached:
            return cached['scl']
    path = folder / (item['id']+'-scl-only.npz')
    if path.exists():
        with np.load(path) as cached:
            np.testing.assert_array_equal(cached['bounds'], bounds)
            return cached['scl']
    with rasterio.open(item['assets']['scl']['href']) as source:
        assert source.crs.to_epsg() == 32647
        window = from_bounds(*bounds, transform=source.transform)
        if min(window.col_off, window.row_off) < 0 or window.col_off+window.width > source.width or window.row_off+window.height > source.height:
            raise ValueError('QAwindowcrossestileboundary')
        values = source.read(1, window=window, out_shape=(500, 500), resampling=Resampling.nearest)
    np.savez_compressed(path, scl=values, bounds=bounds)
    return values


def case(candidate):
    case_id = candidate['id']
    folder = OUT / 'cases' / case_id
    folder.mkdir(exist_ok=True)
    if (folder / 'case.json').exists() and read(folder / 'case.json').get('collection') == 'sentinel-2-c1-l2a':
        return read(folder / 'case.json')
    x, y = PROJECT.transform(candidate['longitude'], candidate['latitude'])
    west, north = math.floor(x / 100) * 100 - 5000, math.ceil(y / 100) * 100 + 5000
    bounds = [west, north-10000, west+10000, north]
    points, times, xy = source_points(candidate['year'])
    inside = (np.abs(xy[:, 0] - (west + 5000)) < 4500) & (np.abs(xy[:, 1] - (north - 5000)) < 4500)
    scenes = catalog(candidate)['features']
    scenes = [scene for scene in scenes if scene['properties'].get('eo:cloud_cover', 100) <= 90 and all(key in scene['assets'] for key in ASSETS)]
    scenes.sort(key=lambda scene: scene['properties']['datetime'])
    day = datetime.fromisoformat(candidate.get('date', candidate['id'])).replace(tzinfo=UTC) + timedelta(hours=4)
    combinations = []
    for start in scenes:
        if candidate.get('forced_initial_scene') and start['id'] != candidate['forced_initial_scene']:
            continue
        when = stamp(start['properties']['datetime'])
        if abs((when-day).total_seconds()) > 3 * 86400:
            continue
        eligible = inside & (times <= when.timestamp()-3*3600) & (times > when.timestamp()-27*3600)
        if not eligible.any():
            continue
        tile = start['id'].split('_')[1]
        before = [s for s in scenes if s['id'].split('_')[1] == tile and 2 <= (when-stamp(s['properties']['datetime'])).total_seconds()/86400 <= 14.1]
        after = [s for s in scenes if s['id'].split('_')[1] == tile and 1 <= (stamp(s['properties']['datetime'])-when).total_seconds()/86400 <= 7.1]
        if before and after:
            for earlier in before[-3:]:
                for later in after[:3]:
                    priority = (abs((when-day).total_seconds()),
                                (stamp(later['properties']['datetime'])-when).total_seconds(),
                                (when-stamp(earlier['properties']['datetime'])).total_seconds())
                    combinations.append((priority, start, earlier, later, np.flatnonzero(eligible)))
    combinations.sort(key=lambda item: item[0])
    rejected = []
    for _, start, before, after, indices in combinations:
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', GDAL_HTTP_TIMEOUT='60'):
                qa = [read_scl(item, bounds, folder) for item in (before, start, after)]
                usable = np.logical_and.reduce([np.isin(values, (4, 5)) for values in qa])
                if usable.mean() < .65:
                    rejected.append({'start': start['id'], 'before': before['id'], 'after': after['id'],
                        'reason': 'SCLtripletprecheckbelow65percentclearland', 'fraction': float(usable.mean())})
                    continue
                initial = crop_scene(start, bounds, folder)
                baseline = crop_scene(before, bounds, folder)
                final = crop_scene(after, bounds, folder)
            validity = baseline['valid'] & initial['valid'] & final['valid']
            if validity.mean() < .65:
                rejected.append({'start': start['id'], 'reason': 'less_than65percent_clear_land_in_all_three_images', 'fraction': float(validity.mean())})
                continue
            # Pair chosen by past hotspot availability/date/quality, never overlap score.
            origin = stamp(start['properties']['datetime'])
            end = stamp(after['properties']['datetime'])
            run = (origin-timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
            run -= timedelta(hours=run.hour % candidate.get('weather_run_interval_hours',6))
            weather_path = folder / 'single-run-weather.json'
            params = {'latitude': candidate['latitude'], 'longitude': candidate['longitude'], 'models': 'ecmwf_ifs',
                'run': run.strftime('%Y-%m-%dT%H:%M'), 'forecast_days': 9, 'wind_speed_unit': 'ms', 'timezone': 'UTC',
                'hourly': 'wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m,precipitation'}
            response = httpx.get('https://single-runs-api.open-meteo.com/v1/forecast', params=params, timeout=90)
            response.raise_for_status()
            write(weather_path, response.json())
            metadata = {'id': case_id, 'collection': 'sentinel-2-c1-l2a', 'split': 'selection2025' if candidate['year'] == 2025 else 'retrospective_test2026',
                'candidate': candidate, 'bounds_utm47': bounds, 'initial_acquisition': origin.isoformat(), 'final_acquisition': end.isoformat(),
                'horizon_hours': (end-origin).total_seconds()/3600, 'baseline_scene': before['id'], 'initial_scene': start['id'], 'final_scene': after['id'],
                'weather': {'model': 'ecmwf_ifs', 'run_init': run.isoformat(), 'assumed_model_availability_delay_hours': 6,
                    'archive_note': 'Provider describes preMay2026IFS archive as Cycle49R1hindcasts. Single initialization, not stitched future runs; not verified original as-issued distribution.',
                    'sha256': sha(weather_path), 'request': params},
                'clear_land_fraction': float(validity.mean()),
                'initial_hotspots': [points[i] for i in indices], 'excluded_triplets': rejected,
                'initialization_note': 'Retrospective initial optical image provided at acquisition time. Real image publication/processing latency is NOT simulated; catalog_created is retained.',
                'reference_note': 'Satellite-derived spectral burn-change candidate, not independently surveyed fire perimeter.'}
            write(folder / 'case.json', metadata)
            print('CASE_READY', case_id, round(metadata['horizon_hours'], 2), 'hours', len(indices), 'past_hotspots', flush=True)
            return metadata
        except Exception as error:
            rejected.append({'start': start['id'], 'reason': type(error).__name__ + ': ' + str(error)})
    failed = {'id': case_id, 'candidate': candidate, 'status': 'no_usable_triplet', 'excluded_triplets': rejected}
    write(folder / 'excluded.json', failed)
    print('CASE_EXCLUDED', case_id, rejected[-1:] or 'No time-matched triplet with past hotspots', flush=True)
    return failed


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / 'cases').mkdir(exist_ok=True)
    (OUT / 'catalogs').mkdir(exist_ok=True)
    candidates = choose_candidates()
    write(OUT / 'case-candidates.json', candidates)
    # Limit remote COG traffic; each worker reads its case sequentially.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(case, candidates))
    write(OUT / 'case-manifest.json', results)
    print('MANIFEST', {'ready': sum('initial_scene' in r for r in results), 'excluded': sum('initial_scene' not in r for r in results)}, flush=True)


if __name__ == '__main__':
    main()
