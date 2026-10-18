"""Download an indexed current ECMWF numeric surface field, retaining provenance.

Research adapter only. Native *published* GRIB grid is retained, not downscaled.
No fire labels or production services are read. Run with .venv-research Python.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import importlib.metadata
import json
from pathlib import Path
import re
from urllib.parse import urljoin

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/fire-engineering-20261018/native-weather'
PORTAL = 'https://data.ecmwf.int/forecasts/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(v for k, v in attrs if k == 'href' and v)


def get(url, path=None, headers=None):
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        r = client.get(url, headers=headers or {})
        r.raise_for_status()
        body = r.content
        receipt = {'url': url, 'status': r.status_code, 'headers': dict(r.headers),
                   'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                   'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
    if path:
        path.write_bytes(body)
    return body, receipt


def listed(url, label, pattern):
    body, receipt = get(url, OUT / f'listing-{label}.html')
    p = Links()
    p.feed(body.decode())
    matches = sorted({urljoin(url, x) for x in p.links if re.search(pattern, x)})
    write(OUT / f'listing-{label}-receipt.json', receipt)
    if not matches:
        raise RuntimeError(f'No actual listing link matching {pattern} in {url}')
    return matches


def decode(grib_path, bbox):
    import eccodes as ec
    fields = {}
    metas = []
    with grib_path.open('rb') as f:
        while (gid := ec.codes_grib_new_from_file(f)) is not None:
            try:
                meta = {}
                for key in ['shortName', 'name', 'units', 'typeOfLevel', 'level', 'dataDate',
                            'dataTime', 'validityDate', 'validityTime', 'stepRange', 'stepType',
                            'gridType', 'Ni', 'Nj', 'iDirectionIncrementInDegrees',
                            'jDirectionIncrementInDegrees', 'shapeOfTheEarth',
                            'latitudeOfFirstGridPointInDegrees', 'longitudeOfFirstGridPointInDegrees',
                            'latitudeOfLastGridPointInDegrees', 'longitudeOfLastGridPointInDegrees']:
                    try:
                        meta[key] = ec.codes_get(gid, key)
                    except ec.CodesInternalError:
                        pass
                lat = ec.codes_get_array(gid, 'latitudes')
                lon = (ec.codes_get_array(gid, 'longitudes') + 180) % 360 - 180
                val = ec.codes_get_values(gid)
                mask = (lon >= bbox[0]) & (lon <= bbox[2]) & (lat >= bbox[1]) & (lat <= bbox[3])
                ls, xs = np.unique(lat[mask])[::-1], np.unique(lon[mask])
                expected = len(ls) * len(xs)
                assert mask.sum() == expected and expected > 0, 'Regional grid must be complete rectangle'
                rows = np.searchsorted(-ls, -lat[mask])
                cols = np.searchsorted(xs, lon[mask])
                values = np.full((len(ls), len(xs)), np.nan)
                values[rows, cols] = val[mask]
                assert np.isfinite(values).all()
                fields[meta['shortName']] = values.astype('float32')
                meta['regional_shape'] = list(values.shape)
                meta['regional_min'] = float(values.min())
                meta['regional_max'] = float(values.max())
                metas.append(meta)
            finally:
                ec.codes_release(gid)
    assert '10u' in fields and '10v' in fields
    return fields, ls, xs, metas


def historical_probe():
    """Sample one fixed historical run per year, retaining returned grid centres.

    This is an API point-sampling proof, not an export of the native O1280 GRIB.
    """
    rows = []
    for year in [2024, 2025, 2026]:
        params = {'latitude': '18.7,18.7,18.9,18.9', 'longitude': '98.9,99.1,98.9,99.1',
                  'models': 'ecmwf_ifs', 'run': f'{year}-03-24T00:00',
                  'hourly': 'wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m,precipitation',
                  'forecast_days': 1, 'timezone': 'UTC', 'wind_speed_unit': 'ms',
                  'cell_selection': 'nearest', 'elevation': 'nan,nan,nan,nan'}
        url = str(httpx.URL('https://single-runs-api.open-meteo.com/v1/forecast', params=params))
        path = OUT / f'historical-{year}-samples.json'
        body, receipt = get(url, path)
        data = json.loads(body)
        assert isinstance(data, list) and len(data) == 4
        receipt['request'] = params
        write(OUT / f'historical-{year}-receipt.json', receipt)
        row = {'year': year, 'run': params['run'], 'requested_latitude': params['latitude'],
               'requested_longitude': params['longitude'], 'response_locations': [],
               'sha256': sha(path), 'api_status': receipt['status']}
        for cell in data:
            assert cell['hourly']['time'][0] == f'{year}-03-24T00:00'
            speed = np.asarray(cell['hourly']['wind_speed_10m'], dtype=float)
            assert np.isfinite(speed).all()
            row['response_locations'].append({'latitude': cell['latitude'], 'longitude': cell['longitude'],
                'elevation': cell.get('elevation'), 'samples': len(speed),
                'wind_speed_min_m_s': float(speed.min()), 'wind_speed_max_m_s': float(speed.max())})
        speeds = np.asarray([x['hourly']['wind_speed_10m'] for x in data], dtype=float).T
        directions = np.radians(np.asarray([x['hourly']['wind_direction_10m'] for x in data], dtype=float).T)
        history_path = OUT / f'historical-{year}-point-forcing.npz'
        np.savez_compressed(history_path,
            latitude=np.asarray([x['latitude'] for x in data]),
            longitude=np.asarray([x['longitude'] for x in data]),
            valid_time_utc=np.asarray(data[0]['hourly']['time'], dtype='U16'),
            u10_m_s=(-speeds*np.sin(directions)).astype('float32'),
            v10_m_s=(-speeds*np.cos(directions)).astype('float32'),
            temperature_2m_c=np.asarray([x['hourly']['temperature_2m'] for x in data], dtype='float32').T,
            relative_humidity_2m_pct=np.asarray([x['hourly']['relative_humidity_2m'] for x in data], dtype='float32').T,
            precipitation_mm=np.asarray([x['hourly']['precipitation'] for x in data], dtype='float32').T)
        row['forcing_npz'] = {'path': str(history_path.relative_to(ROOT)), 'sha256': sha(history_path),
            'shape': list(speeds.shape), 'convention': 'time x returned grid point; not a regular raster',
            'precipitation': 'Provider hourly precipitation amount mm; historical API product, unlike raw run-accumulated GRIB tp'}
        rows.append(row)
        print(f'HISTORICAL {year} PASS 4 locations', flush=True)
    write(OUT / 'historical-sampling-contract.json', {'status': 'PASS', 'runs': rows,
        'interpretation': 'Open-Meteo nearest sampling of IFS HRES O1280 archive, elevation downscaling disabled. Not original native GRIB export.',
        'historical_run_provenance': 'Provider documents March14 2024-May12 2026 archive as IFS Cycle49R1 hindcasts, not proven original as-issued forecasts.',
        'sources': ['https://open-meteo.com/en/docs/single-runs-api', 'https://open-meteo.com/en/docs']} )


def fetch_historical_case_grid(meta, folder):
    """Fetch/cache four case-corner samples from the EXACT original weather run.

    folder is a research cache directory. Original hourly time contract is read
    from meta['weather_source_path'] when supplied, otherwise from
    folder/'single-run-weather.json' when present. Returned array dictionaries
    use time x UNIQUE returned grid point, preserving actual model coordinates.
    No fire labels are accessed. This is archive API sampling, not native GRIB.
    """
    from pyproj import Transformer
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    params = dict(meta['weather']['request'])
    original_run = params['run']
    init = datetime.fromisoformat(original_run).replace(tzinfo=timezone.utc)
    known = datetime.fromisoformat(meta['initial_acquisition']).astimezone(timezone.utc)
    delay = meta['weather'].get('assumed_model_availability_delay_hours', 6)
    assert init + timedelta(hours=delay) <= known, 'Run availability must precede initial image'
    assert params.get('models') == 'ecmwf_ifs' and params.get('timezone', 'UTC') == 'UTC'
    assert params.get('wind_speed_unit') == 'ms'
    source = Path(meta.get('weather_source_path', folder / 'single-run-weather.json'))
    old = json.loads(source.read_text(encoding='utf8')) if source.exists() else None
    if old is not None:
        times = old['hourly']['time']
        expected_source_sha = sha(source)
    else:
        assert 'forecast_days' in params, 'Need original time contract or forecast_days'
        times = [(init + timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M')
                 for i in range(int(params['forecast_days'])*24)]
        expected_source_sha = None
    west, south, east, north = meta['bounds_utm47']
    transform = Transformer.from_crs('EPSG:32647', 'EPSG:4326', always_xy=True)
    longitude, latitude = transform.transform([west, east, west, east], [south, south, north, north])
    params.update(latitude=','.join(f'{x:.7f}' for x in latitude),
                  longitude=','.join(f'{x:.7f}' for x in longitude),
                  cell_selection='nearest', elevation='nan,nan,nan,nan',
                  hourly='wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m,precipitation')
    signature = hashlib.sha256(json.dumps({'request': params, 'times': times,
        'bounds_utm47': meta['bounds_utm47'], 'initial_acquisition': meta['initial_acquisition'],
        'final_acquisition': meta['final_acquisition'], 'delay': delay,
        'source_point_weather_sha256': expected_source_sha}, sort_keys=True).encode()).hexdigest()
    raw_path, rec_path = folder/'corner-weather.json', folder/'corner-weather-receipt.json'
    contract_path, npz_path = folder/'corner-weather-contract.json', folder/'corner-weather.npz'
    cached = json.loads(contract_path.read_text(encoding='utf8')) if contract_path.exists() else None
    if (cached and cached.get('request_signature') == signature and raw_path.exists() and npz_path.exists()
            and sha(raw_path) == cached['raw_sha256'] and sha(npz_path) == cached['npz_sha256']):
        with np.load(npz_path, allow_pickle=False) as data:
            result = {k: data[k] for k in data.files}
        result['receipt'] = cached
        return result
    url = str(httpx.URL('https://single-runs-api.open-meteo.com/v1/forecast', params=params))
    body, rec = get(url, raw_path)
    data = json.loads(body)
    assert isinstance(data, list) and len(data) == 4
    unique, mapping = [], []
    for row in data:
        assert row['hourly']['time'] == times, 'Spatial forcing must retain exact original valid times'
        assert row['hourly_units']['wind_speed_10m'] == 'm/s'
        assert row['hourly_units']['temperature_2m'] == '°C'
        assert row['hourly_units']['relative_humidity_2m'] == '%'
        assert row['hourly_units']['precipitation'] == 'mm'
        key = (row['latitude'], row['longitude'])
        match = next((i for i, other in enumerate(unique) if (other['latitude'], other['longitude']) == key), None)
        if match is None:
            match = len(unique)
            unique.append(row)
        else:
            assert row['hourly'] == unique[match]['hourly'], 'Duplicate grid point returned different weather'
        mapping.append(match)
    speed = np.asarray([x['hourly']['wind_speed_10m'] for x in unique], dtype=float).T
    direction = np.radians(np.asarray([x['hourly']['wind_direction_10m'] for x in unique], dtype=float).T)
    arrays = {'latitude': np.asarray([x['latitude'] for x in unique]),
        'longitude': np.asarray([x['longitude'] for x in unique]),
        'valid_time_utc': np.asarray(times, dtype='U16'),
        'u10_m_s': (-speed*np.sin(direction)).astype('float32'),
        'v10_m_s': (-speed*np.cos(direction)).astype('float32'),
        'temperature_2m_c': np.asarray([x['hourly']['temperature_2m'] for x in unique], dtype='float32').T,
        'relative_humidity_2m_pct': np.asarray([x['hourly']['relative_humidity_2m'] for x in unique], dtype='float32').T,
        'precipitation_mm': np.asarray([x['hourly']['precipitation'] for x in unique], dtype='float32').T}
    all_finite = np.ones((len(times), len(unique)), dtype=bool)
    end = datetime.fromisoformat(meta['final_acquisition']).astimezone(timezone.utc)
    assert datetime.fromisoformat(times[-1]).replace(tzinfo=timezone.utc) >= end.replace(minute=0, second=0, microsecond=0)
    required = np.asarray([datetime.fromisoformat(x).replace(tzinfo=timezone.utc) <= end for x in times])
    for key in ['u10_m_s', 'v10_m_s', 'temperature_2m_c', 'relative_humidity_2m_pct', 'precipitation_mm']:
        finite = np.isfinite(arrays[key])
        variable_required = required.copy()
        # First rain interval would precede initialization; provider correctly
        # reports null there. Retain missing value, do not invent zero rainfall.
        if key == 'precipitation_mm' and times[0] == init.strftime('%Y-%m-%dT%H:%M'):
            variable_required[0] = False
        assert finite[variable_required].all(), f'{key}: missing forcing values within case horizon'
        assert arrays[key].shape == (len(times), len(unique))
        all_finite &= finite
    arrays['valid_forcing_mask'] = all_finite
    np.savez_compressed(npz_path, **arrays)
    rec['request'] = params
    write(rec_path, rec)
    contract = {'case_id': meta['id'], 'request_signature': signature, 'run_init_utc': init.isoformat(),
        'availability_delay_hours': delay, 'initial_acquisition': meta['initial_acquisition'],
        'raw_sha256': sha(raw_path), 'npz_sha256': sha(npz_path),
        'source_point_weather_sha256': expected_source_sha,
        'original_valid_times_exact_match': True, 'hour_count': len(times),
        'fully_available_hour_count': int(all_finite.all(axis=1).sum()),
        'case_horizon_all_finite': True,
        'missing_value_policy': 'Preserve API nulls (first initialization rain interval and forecast tail) as NaN plus valid_forcing_mask; no zero filling or extension beyond forecast availability',
        'requested_corner_latitude': list(latitude), 'requested_corner_longitude': list(longitude),
        'returned_points': [{'latitude': x['latitude'], 'longitude': x['longitude'], 'elevation': x.get('elevation')} for x in unique],
        'corner_to_unique_point': mapping, 'unique_grid_point_count': len(unique),
        'all_corners_same_grid_point': len(unique) == 1,
        'array_convention': 'time x unique returned grid point; irregular points, not rectangular native raster',
        'point_sampling': 'nearest with elevation downscaling disabled; distinct returned points do not imply terrain-resolving winds',
        'historical_provenance': meta['weather'].get('archive_note', 'IFS49R1 hindcast archive before May12 2026; not confirmed original as-issued'),
        'rain_units': 'mm per API hourly interval, not raw GRIB run-accumulated tp',
        'source': 'https://single-runs-api.open-meteo.com/v1/forecast',
        'request': params, 'receipt_path': str(rec_path), 'npz_path': str(npz_path)}
    write(contract_path, contract)
    arrays['receipt'] = contract
    return arrays


def sample_wind(npz_path, latitude, longitude):
    """Bilinear u/v sampling, no spatial extrapolation or angle interpolation.

    Numerical interpolation creates no extra environmental resolution. Return
    eastward/northward components, speed and meteorological FROM direction.
    """
    from scipy.interpolate import RegularGridInterpolator
    with np.load(npz_path, allow_pickle=False) as arrays:
        lat, lon = arrays['latitude'][::-1], arrays['longitude']
        point = np.column_stack(np.broadcast_arrays(np.asarray(latitude).ravel(), np.asarray(longitude).ravel()))
        u = RegularGridInterpolator((lat, lon), arrays['10u'][::-1], bounds_error=True)(point)
        v = RegularGridInterpolator((lat, lon), arrays['10v'][::-1], bounds_error=True)(point)
    return {'u10_m_s': u, 'v10_m_s': v, 'speed_m_s': np.hypot(u, v),
            'from_direction_deg': (270 - np.degrees(np.arctan2(v, u))) % 360}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bbox', nargs=4, type=float, default=[98, 17, 100, 20.5], metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    ap.add_argument('--step', type=int, default=6)
    ap.add_argument('--decode-only', action='store_true')
    ap.add_argument('--historical-probe', action='store_true')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.historical_probe:
        historical_probe()
        return
    receipt_path = OUT / 'download-receipt.json'
    grib_path = OUT / 'surface-selected.grib2'
    if not args.decode_only:
        day_url = listed(PORTAL, 'root', r'/\d{8}/?$')[-1]
        hour_url = listed(day_url, 'day', r'/\d{2}z/?$')[-1]
        # Explicitly select the demonstrated regular published grid, not inferred native 9 km.
        ifs_url = next(x for x in listed(hour_url, 'hour', r'/ifs/?$') if x.endswith('/ifs/'))
        grid_url = next(x for x in listed(ifs_url, 'ifs', r'/0p25/?$') if x.endswith('/0p25/'))
        stream_url = next(x for x in listed(grid_url, 'grid', r'/oper/?$') if x.endswith('/oper/'))
        indexes = listed(stream_url, 'stream', rf'-{args.step}h-oper-fc\.index$')
        index_url = indexes[0]
        data_url = index_url.removesuffix('.index') + '.grib2'
        body, index_receipt = get(index_url, OUT / 'surface.index')
        rows = [json.loads(x) for x in body.decode().splitlines() if x.strip()]
        selected = [x for x in rows if x.get('param') in ['10u', '10v', '2t', '2d', 'tp'] and x.get('type') == 'fc']
        assert {'10u', '10v'}.issubset({x['param'] for x in selected})
        assert len(selected) <= 5
        range_receipts = []
        with grib_path.open('wb') as out:
            for row in selected:
                start, size = row['_offset'], row['_length']
                assert size < 20_000_000
                header = {'Range': f'bytes={start}-{start+size-1}'}
                body, rec = get(data_url, headers=header)
                assert rec['status'] == 206 and len(body) == size, 'Server must honor exact byte range'
                assert body[:4] == b'GRIB' and body[-4:] == b'7777'
                out.write(body)
                rec['requested_headers'] = header
                rec['index_row'] = row
                range_receipts.append(rec)
                print(f"DOWNLOADED {row['param']} {size} bytes", flush=True)
        receipt = {'index': index_receipt, 'ranges': range_receipts, 'grib_sha256': sha(grib_path),
                   'grib_bytes': grib_path.stat().st_size, 'source': 'ECMWF IFS Open Data',
                   'purpose': 'Current published-grid numeric forcing adapter; not historical skill gain'}
        write(receipt_path, receipt)
    receipt = json.loads(receipt_path.read_text(encoding='utf8'))
    assert sha(grib_path) == receipt['grib_sha256']
    fields, lat, lon, metas = decode(grib_path, args.bbox)
    u, v = fields['10u'], fields['10v']
    fields['wind_speed_10m_m_s'] = np.hypot(u, v)
    fields['wind_from_direction_10m_deg'] = (270 - np.degrees(np.arctan2(v, u))) % 360
    if '2t' in fields:
        fields['temperature_2m_c'] = fields['2t'] - 273.15
    if '2d' in fields and '2t' in fields:
        t, td = fields['temperature_2m_c'], fields['2d'] - 273.15
        fields['relative_humidity_2m_pct'] = np.clip(100*np.exp(17.625*td/(243.04+td) - 17.625*t/(243.04+t)), 0, 100)
    init = datetime.strptime(f"{metas[0]['dataDate']}{metas[0]['dataTime']:04d}", '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
    valid = datetime.strptime(f"{metas[0]['validityDate']}{metas[0]['validityTime']:04d}", '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
    npz = OUT / 'chiang-mai-surface-grid.npz'
    np.savez_compressed(npz, latitude=lat, longitude=lon, **fields)
    summary = {'source': receipt['source'], 'run_init_utc': init.isoformat(), 'valid_time_utc': valid.isoformat(),
               'forecast_lead_hours': (valid-init).total_seconds()/3600,
               'retrieved_utc': receipt['ranges'][-1]['retrieved_utc'], 'bbox_wsen': args.bbox,
               'actual_grid_bbox_wsen': [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
               'coordinate_reference': 'Geographic latitude/longitude degrees; ECMWF spherical Earth specified in GRIB shapeOfTheEarth',
               'grid_axis_convention': 'latitude north to south, longitude west to east; coordinate arrays are cell centres',
               'grib': {'path': str(grib_path.relative_to(ROOT)), 'sha256': sha(grib_path), 'bytes': grib_path.stat().st_size},
               'npz': {'path': str(npz.relative_to(ROOT)), 'sha256': sha(npz), 'shape': list(u.shape), 'keys': list(fields)},
               'fields': metas, 'packages': {x: importlib.metadata.version(x) for x in ['ecmwf-opendata', 'eccodes', 'numpy']},
               'limitations': ['One current forecast step only; not an hourly forcing series or a validation result.',
                              '0.25 degree is the published field spacing, not 9 km, 1 km, or terrain-downscaled wind.',
                              '10 m wind is above model surface; not flame-height or resolved forest-valley wind.',
                              'tp is run-accumulated precipitation in metres; do not treat as one-hour rain.',
                              'Derived RH uses Magnus approximation, not an independently measured humidity field.',
                              'No historical forecast improvement claimed from current fields.']}
    write(OUT / 'grid-contract.json', summary)
    # Independent GDAL metadata check; this Rasterio build lacks libaec, so its
    # GRIB data decoder cannot unpack template 5.42. Do not claim two decoders.
    import sys
    sys.path.append(str(ROOT / 'output/spread-deps'))
    import rasterio
    errors = {}
    with rasterio.open(grib_path) as src:
        assert src.width == 1440 and src.height == 721
        assert np.isclose(src.transform.a, .25) and np.isclose(src.transform.e, -.25)
        for i in range(1, src.count+1):
            key = {'UGRD': '10u', 'VGRD': '10v'}.get(src.tags(i).get('GRIB_ELEMENT'))
            if key:
                assert src.tags(i)['GRIB_UNIT'] == '[m/s]'
                assert datetime.fromtimestamp(int(src.tags(i)['GRIB_REF_TIME']), timezone.utc) == init
                assert datetime.fromtimestamp(int(src.tags(i)['GRIB_VALID_TIME']), timezone.utc) == valid
                errors[key] = 'unit/grid/time metadata match'
    assert set(errors) == {'10u', '10v'}
    import eccodes as ec
    nearest_errors = {}
    with grib_path.open('rb') as f:
        while (gid := ec.codes_grib_new_from_file(f)) is not None:
            try:
                key = ec.codes_get(gid, 'shortName')
                if key in ['10u', '10v']:
                    nearest = ec.codes_grib_find_nearest(gid, 18.7883, 98.9853)[0]
                    r = np.flatnonzero(np.isclose(lat, nearest['lat']))[0]
                    c = np.flatnonzero(np.isclose(lon, nearest['lon']))[0]
                    error = abs(float(fields[key][r, c])-nearest['value'])
                    assert error < 1e-5
                    nearest_errors[key] = error
            finally:
                ec.codes_release(gid)
    assert set(nearest_errors) == {'10u', '10v'}
    for key, angle in [('eastward', 270), ('northward', 180), ('westward', 90), ('southward', 0)]:
        uv = {'eastward': (1, 0), 'northward': (0, 1), 'westward': (-1, 0), 'southward': (0, -1)}[key]
        assert np.isclose((270 - np.degrees(np.arctan2(uv[1], uv[0]))) % 360, angle)
    sample = sample_wind(npz, [18.7883], [98.9853])
    write(OUT / 'numerical-verification.json', {'status': 'PASS', 'independent_gdal_metadata': errors,
        'eccodes_nearest_vs_extracted_node_max_error_m_s': nearest_errors,
        'independent_data_decoder': 'Not available: Rasterio GDAL lacks libaec for GRIB data template 5.42; eccodes 2.50 successfully decodes actual values.',
        'cardinal_from_direction_fixtures': 'PASS', 'chiang_mai_centre_sample': {k: v.tolist() for k, v in sample.items()},
        'sample_method': 'bilinear interpolate u/v at 18.7883N,98.9853E; no wind-direction averaging; no extrapolation',
        'npz_sha256': sha(npz), 'grib_sha256': sha(grib_path)})
    print(json.dumps({'status': 'PASS', 'run': summary['run_init_utc'], 'valid': summary['valid_time_utc'],
                      'shape': list(u.shape), 'fields': list(fields), 'grib_bytes': grib_path.stat().st_size}))


if __name__ == '__main__':
    main()
