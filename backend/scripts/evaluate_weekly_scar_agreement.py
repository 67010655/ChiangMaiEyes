"""Independent-sensor weekly scar overlay, NOT a 12h spread-accuracy test.

Run with backend/.venv/Scripts/python (Rasterio environment). Inputs/outputs
stay in output/. Missing or zero-acquisition pixels are never true negatives.
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'output/burn-reference-research'
OUT = ROOT / 'output/watch-budget-20261017/scar-agreement'
RANKS = OUT.parent / 'rank-cache'
BUDGETS = (25, 50, 125, 250, 500)


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(entry):
    folder = SOURCE / 'tiles'
    path = folder / entry['url'].rsplit('/', 1)[-1]
    receipt_path = path.with_suffix('.json')
    if path.exists() and receipt_path.exists():
        receipt = read(receipt_path)
        if sha(path) == receipt['sha256'] and receipt['url'] == entry['url']:
            return {**entry, 'local': str(path), 'sha256': receipt['sha256'], 'status': 'cached'}
    for attempt in range(3):
        try:
            response = httpx.get(entry['url'], timeout=90, follow_redirects=True)
            response.raise_for_status()
            temporary = path.with_suffix('.download')
            temporary.write_bytes(response.content)
            with rasterio.open(temporary) as dataset:
                assert dataset.count == 2 and dataset.crs.to_epsg() == 32647
                assert dataset.transform.a == 20 and dataset.transform.e == -20
            temporary.replace(path)
            receipt = {'url': entry['url'], 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                       'sha256': sha(path), 'bytes': path.stat().st_size}
            write(receipt_path, receipt)
            return {**entry, 'local': str(path), 'sha256': receipt['sha256'], 'status': 'downloaded'}
        except Exception as error:
            if attempt == 2:
                return {**entry, 'status': 'failed', 'error': str(error)}
            time.sleep(attempt + 1)


def add_tile(canvas, dataset, west, north):
    transform = dataset.transform
    assert dataset.crs.to_epsg() == 32647 and transform.a == 20 and transform.e == -20
    assert transform.b == 0 and transform.d == 0
    column = (transform.c - west) / 20
    row = (north - transform.f) / 20
    assert abs(column - round(column)) < 1e-6 and abs(row - round(row)) < 1e-6
    column, row = round(column), round(row)
    left, top = max(0, column), max(0, row)
    right, bottom = min(canvas.shape[1], column + dataset.width), min(canvas.shape[0], row + dataset.height)
    if left >= right or top >= bottom:
        return 0
    bands = dataset.read(window=Window(left-column, top-row, right-left, bottom-top))
    if (bands < 0).any():
        raise ValueError('Negative codes/nodata require an explicit product mask.')
    acquisition = bands[1] > 0
    scar = bands[0] > 0
    canvas[top:bottom, left:right] |= acquisition.astype('uint8') | (scar.astype('uint8') << 1)
    return int((scar & ~acquisition).sum())


def aggregate_pixels(mask, grid):
    height, width = int(grid['height']), int(grid['width'])
    # Every500m cell is exactly25x25 source pixels on this verified UTM grid.
    return mask.reshape(height, 25, width, 25).sum(axis=(1, 3), dtype='uint16').ravel()[grid['fullindex']]


def overlay(counts, acquisitions, orders, budget):
    total = int(counts.sum()) * .0004
    selected = orders[:round(budget / .25)]
    intersection = int(counts[selected].sum()) * .0004
    observed_selected_area = int(acquisitions[selected].sum()) * .0004
    return {'selected_area_km2': len(selected) * .25,
            'acquisition_covered_selected_area_km2': observed_selected_area,
            'observed_scar_area_km2': total, 'intersection_km2': intersection,
            'observed_scar_coverage_pct': 100 * intersection / total if total else None,
            'observed_scar_overlap_dice': 2 * intersection / (len(selected) * .25 + total) if total else None,
            'observed_scar_overlap_iou': intersection / (len(selected) * .25 + total - intersection) if total else None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = SOURCE / 'b4-2026-jan-apr-manifest.json'
    manifest = read(manifest_path)
    entries = [entry for month in manifest for entry in month['files'] if entry['end_date'] <= '20260430']
    protocol = {'mode': 'offline_independent_sensor_weekly_spatial_agreement_only',
                'source': 'TamRoyPao / HII / Kasetsart University B4 Sentinel2 weekly20m burn detection counts',
                'source_description': 'https://tamroypao.hii.or.th/', 'manifest_sha256': sha(manifest_path),
                'evaluation_grid': 'Frozen500m UTM47N candidate cells. Pixel areas20m x20m, union across overlapping tiles.',
                'forecast': 'Frozen next12h candidate and2025-selected kernel baseline, at08ICT on each weekly composite start date.',
                'time_mismatch': 'Weekly scar interval includes8h before the issue and6.67days beyond the forecast. Scars may predate the issue. This does NOT estimate12h fire-spread accuracy.',
                'prior_scar_exclusion': 'Additional target excludes20m pixels detected in all earlier listed2026 composites; first detection is not a burn-date guarantee.',
                'non_detection': 'Band2 counts acquisitions, not verified cloud-free usable observations. Zero scar is not proven unburned; no true-negative or false-alarm accuracy reported.',
                'scar_reference_mask': 'Positive scar AND positive recorded acquisition in mosaic. Positive scar with zero acquisitions is excluded and counted separately.',
                'forest_quality': 'Provider has not formally assessed forest detection accuracy; canopy can obscure scars.',
                'budgets_km2': BUDGETS, 'prediction_selected_without_scar_labels': True,
                'deployment_commands_issued': 0}
    write(OUT / 'protocol.json', protocol)
    print('B4download', len(entries), 'listed files; max3 concurrent requests', flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        downloads = []
        for index, value in enumerate(pool.map(download, entries)):
            downloads.append(value)
            if index % 20 == 0:
                print('B4file', index + 1, value['status'], flush=True)
    write(OUT / 'downloads.json', downloads)
    failures = [row for row in downloads if row['status'] == 'failed']
    if failures:
        raise RuntimeError(f'{len(failures)} B4 download failures; inspect downloads.json before claiming a completed comparison.')
    grid = dict(np.load(ROOT / 'output/priority-forecast-20261017/grid.npz'))
    shape = (int(grid['height']) * 25, int(grid['width']) * 25)
    earlier = np.zeros(shape, dtype=bool)
    weeks = sorted(set(row['start_date'] for row in downloads))
    rows, skipped = [], []
    for start in weeks:
        tiles = [row for row in downloads if row['start_date'] == start]
        ends = {row['end_date'] for row in tiles}
        assert len(ends) == 1
        canvas = np.zeros(shape, dtype='uint8')
        inconsistencies = 0
        for tile in tiles:
            with rasterio.open(tile['local']) as dataset:
                inconsistencies += add_tile(canvas, dataset, float(grid['west']), float(grid['north']))
        scar = (canvas & 3) == 3
        inconsistent_pixels = int(aggregate_pixels((canvas & 3) == 2, grid).sum())
        acquisitions = aggregate_pixels((canvas & 1) > 0, grid)
        counts = aggregate_pixels(scar, grid)
        first_counts = aggregate_pixels(scar & ~earlier, grid)
        earlier |= scar
        cache = RANKS / (start + 'T08.npz')
        np.savez_compressed(OUT / (start + '-scar-counts.npz'), scar_count=counts,
                            first_observed_scar_count=first_counts, acquisition_count=acquisitions)
        if not cache.exists():
            skipped.append({'start_date': start, 'reason': 'No common2026 issue at weekly start08ICT; used only as prior-scar history.'})
            print('B4week', start, 'no forecast at issue; retained history', flush=True)
            continue
        with np.load(cache) as forecasts:
            orders = {name: forecasts[name] for name in ('candidate', 'kernel')}
        row = {'start_date': start, 'end_date': next(iter(ends)), 'listed_tiles_used': len(tiles),
               'acquisition_covered_candidate_area_km2': int(acquisitions.sum()) * .0004,
               'candidate_area_km2': len(counts) * .25,
               'scar_without_recorded_acquisition_pixels_in_clipped_tile_reads': inconsistencies,
               'excluded_scar_without_acquisition_candidate_pixels': inconsistent_pixels,
               'models': {name: {str(b): {'all_observed_scars': overlay(counts, acquisitions, order, b),
                                        'first_observed_scars': overlay(first_counts, acquisitions, order, b)}
                                 for b in BUDGETS} for name, order in orders.items()}}
        rows.append(row)
        print('B4week', start, 'reference_km2', round(int(counts.sum()) * .0004, 3), flush=True)
    assert rows, 'No completed weekly comparisons'
    pooled = {}
    for name in ('candidate', 'kernel'):
        pooled[name] = {}
        for budget in BUDGETS:
            pooled[name][str(budget)] = {}
            for target in ('all_observed_scars', 'first_observed_scars'):
                values = [row['models'][name][str(budget)][target] for row in rows]
                intersection = sum(value['intersection_km2'] for value in values)
                reference = sum(value['observed_scar_area_km2'] for value in values)
                predicted = sum(value['selected_area_km2'] for value in values)
                pooled[name][str(budget)][target] = {'intersection_km2_periods': intersection,
                    'reference_km2_periods': reference, 'selected_km2_periods': predicted,
                    'observed_scar_coverage_pct': 100 * intersection / reference if reference else None,
                    'observed_scar_overlap_dice': 2 * intersection / (predicted + reference) if reference else None,
                    'observed_scar_overlap_iou': intersection / (predicted + reference - intersection) if reference else None}
    result = {'weeks_compared': len(rows), 'listed_files_used': len(downloads), 'skipped': skipped,
              'interpretation': 'Weekly observed-scar agreement; not12h fire-spread accuracy or verified incident accuracy.',
              'pooled': pooled, 'rows': rows}
    write(OUT / 'summary.json', result)
    print(json.dumps({'weeks': len(rows), 'candidate250': pooled['candidate']['250'], 'kernel250': pooled['kernel']['250']}), flush=True)


if __name__ == '__main__':
    main()
