"""Check raster alignment/overlap arithmetic and the completed frozen replay."""
import json
from pathlib import Path

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from evaluate_weekly_scar_agreement import add_tile, aggregate_pixels, overlay

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/watch-budget-20261017'


def check_rasters():
    grid = {'width': 2, 'height': 2, 'fullindex': np.arange(4)}
    canvas = np.zeros((50, 50), dtype='uint8')
    bands = np.zeros((2, 25, 25), dtype='int16')
    bands[1] = 1
    bands[0, :2, :3] = 1
    bands[0, 24, 24] = 1
    bands[1, 24, 24] = 0  # Contradictory provider codes must not enter reference.
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', height=25, width=25, count=2, dtype='int16',
                         crs='EPSG:32647', transform=from_origin(500, 1000, 20, 20)) as dataset:
            dataset.write(bands)
            assert add_tile(canvas, dataset, 0, 1000) == 1
            before = canvas.copy()
            add_tile(canvas, dataset, 0, 1000)
            np.testing.assert_array_equal(before, canvas)  # Overlap must not double-count.
    counts = aggregate_pixels((canvas & 3) == 3, grid)
    acquisitions = aggregate_pixels((canvas & 1) > 0, grid)
    np.testing.assert_array_equal(counts, [0, 6, 0, 0])  # Upper-right, not transposed/flipped.
    np.testing.assert_array_equal(acquisitions, [0, 624, 0, 0])
    assert ((canvas & 3) == 2).sum() == 1
    hit = overlay(counts, acquisitions, np.array([1, 0, 2, 3]), .25)
    miss = overlay(counts, acquisitions, np.array([0, 1, 2, 3]), .25)
    assert hit['observed_scar_coverage_pct'] == 100 and miss['intersection_km2'] == 0
    assert abs(hit['intersection_km2'] - .0024) < 1e-12
    assert miss['acquisition_covered_selected_area_km2'] == 0
    # Zero acquisition is kept as missing evidence, not counted as correct unburned.
    empty = overlay(np.zeros(4, dtype='uint16'), acquisitions, np.arange(4), .25)
    assert empty['observed_scar_coverage_pct'] is None
    return {'20m_to500m_orientation': 'passed', 'overlapping_tile_union': 'passed',
            'known_pixel_area': 'passed', 'zero_scar_undefined_coverage': 'passed',
            'unobserved_selected_area_preserved': 'passed',
            'scar_without_acquisition_excluded': 'passed'}


def check_replay():
    summary = json.loads((OUT / 'summary.json').read_text(encoding='utf8'))
    original = json.loads((ROOT / 'output/joint-fire-model-20261017/FINAL_DECISION.json').read_text(encoding='utf8'))
    province = summary['scopes']['province_candidates']
    at250 = next(row for row in province['curves'] if row['requested_area_km2'] == 250)
    assert summary['issues'] == original['common_test_issues'] == 231
    assert province['target_cell_periods'] == original['common_test_target_cells'] == 19372
    assert at250['hits']['candidate'] == 6988 and at250['hits']['kernel'] == 5510
    assert abs(at250['coverage_pct']['candidate'] - original['selected_test_coverage_pct']) < 1e-10
    for scope in summary['scopes'].values():
        for name in ('candidate', 'kernel'):
            hits = [row['hits'][name] for row in scope['curves']]
            assert all(a <= b for a, b in zip(hits, hits[1:]))
            assert all(value <= scope['target_cell_periods'] for value in hits)
    production = json.loads((OUT / 'production-file-check.json').read_text(encoding='utf8'))
    assert production['changed'] == [] and production['deployment_commands_issued'] == 0
    return {'original231_issue_result_reproduced': 'passed', 'monotone_area_coverage': 'passed',
            'unchanged_production_files': production['checked_files']}


if __name__ == '__main__':
    result = {'raster_fixtures': check_rasters(), 'frozen_replay': check_replay()}
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))
