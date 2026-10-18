"""Describe frozen-model coverage versus alert area; never fit/select a model.

All scores remain offline. The 2026 season has already been inspected and is
retrospective evidence, not a new untouched holdout. Missing VIIRS detections
are not verified fire absences.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from shapely import contains_xy, make_valid, union_all
from shapely.geometry import shape
from shapely.ops import transform
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
from check_priority_robustness import scores as kernel_scores

OUT = j.ROOT / 'output/watch-budget-20261017'
BUDGETS = (5, 10, 25, 50, 125, 250, 500, 1000, 2000, 4000, 8000)
MODELS = ('candidate', 'kernel')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def community_masks(grid):
    """Grid-centre scope only; no assertion of exact polygon burned area."""
    source = j.ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
    features = j.read(source)['features']
    repaired = 0
    geometries = []
    for feature in features:
        geometry = transform(j.projection.transform, shape(feature['geometry']))
        if not geometry.is_valid:
            geometry = make_valid(geometry)
            repaired += 1
        geometries.append(geometry)
    geometry = union_all(geometries)
    x, y = grid['xy'].T
    masks = {
        'province_candidates': np.ones(len(x), dtype=bool),
        'community_forest_centres': contains_xy(geometry, x, y),
        'community_forest_plus_1km': contains_xy(geometry.buffer(1000), x, y),
    }
    return masks, {'polygon_count': len(features), 'invalid_geometries_repaired_in_memory': repaired,
                   'source_sha256': digest(source),
                   'scope_definition': '500m candidate-cell centres inside polygon union or its 1000m UTM buffer. Boundary centres excluded. A pooled scope, not a budget per forest.'}


def block_intervals(rows, scope, budget_index):
    days = {}
    for row in rows:
        item = row['scopes'][scope]
        value = days.setdefault(row['issued_at'][:10], np.zeros(3))
        value += [item['targets'], item['hits']['candidate'][budget_index], item['hits']['kernel'][budget_index]]
    matrix = np.array(list(days.values()))
    rng = np.random.default_rng(20261018)
    samples = []
    for _ in range(3000):
        starts = rng.integers(0, len(matrix), math.ceil(len(matrix) / 7))
        indices = np.concatenate([(start + np.arange(7)) % len(matrix) for start in starts])[:len(matrix)]
        totals = matrix[indices].sum(axis=0)
        if totals[0]:
            samples.append(100 * np.array([totals[1], totals[1] - totals[2]]) / totals[0])
    bounds = np.percentile(samples, [2.5, 97.5], axis=0)
    return {'coverage_pct_95': bounds[:, 0].tolist(), 'gain_pp_vs_kernel_95': bounds[:, 1].tolist()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / 'rank-cache'
    cache.mkdir(exist_ok=True)
    model_folder = j.OUT / 'final-candidate'
    spec = j.read(model_folder / 'feature-contract.json')
    assert spec['feature_pipeline'] == 'joint53'
    assert digest(model_folder / 'model.joblib') == spec['model_sha256']
    source_paths = [model_folder / 'model.joblib', model_folder / 'feature-contract.json',
                    j.OUT / 'final-common-test-rows.json', j.OLD / 'grid.npz',
                    j.ROOT / 'output/hindcast-2026/firms-points.json',
                    j.OLD / 'gfs-weather-2026.json', j.OUT / 'gfs-spatial-2026.json', j.OUT / 'pm-2026.json',
                    Path(j.__file__), Path(__file__).with_name('priority_forecast_experiment.py'),
                    Path(__file__).with_name('check_priority_robustness.py')]
    provenance = {str(p.relative_to(j.ROOT)).replace('\\', '/'): digest(p) for p in source_paths}
    fingerprint = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    previous = j.read(OUT / 'protocol.json') if (OUT / 'protocol.json').exists() else None
    if previous and previous['fingerprint'] != fingerprint:
        raise ValueError('Inputs changed; use a new output directory before reusing cached ranks.')
    grid = j.build_grid()
    masks, mask_meta = community_masks(grid)
    np.savez_compressed(OUT / 'scope-masks.npz', **masks)
    frozen_paths = list((j.ROOT / 'frontend').rglob('*')) + list((j.ROOT / 'backend/app').rglob('*'))
    frozen = {str(p.relative_to(j.ROOT)).replace('\\', '/'): digest(p) for p in frozen_paths
              if p.is_file() and 'node_modules' not in p.parts and 'dist' not in p.parts and '__pycache__' not in p.parts and '.vercel' not in p.parts}
    protocol = {'version': 1, 'mode': 'offline_frozen_model_descriptive_evaluation', 'fingerprint': fingerprint,
                'source_sha256': provenance, 'budgets_km2': BUDGETS, 'models': MODELS,
                'model_selected_on2025': spec['model_selected_on2025'],
                'target': 'Next12h nominal/high VIIRS detections in500m cells; not observed fire perimeters.',
                'issues': 'Exactly the231 common2026 issue times in final-common-test-rows.json.',
                'denominator': 'Province: all target cells, including outside candidate mask, matching FINAL_DECISION. Community scopes: only assigned target cells in each centre mask.',
                'area_80pct': 'Retrospective descriptive inversion of pooled rank counts; not a threshold selected for operational deployment.',
                'community': mask_meta, 'test_status': '2026 previously inspected, not an untouched holdout.',
                'deployment_commands_issued': 0}
    j.write(OUT / 'protocol.json', protocol)
    data = j.load(2026, grid)
    model = joblib.load(model_folder / 'model.joblib')
    rows = []
    histograms = {name: np.zeros(len(grid['xy']), dtype='int64') for name in MODELS}
    originals = j.read(j.OUT / 'final-common-test-rows.json')
    for index, original in enumerate(originals):
        origin = datetime.fromisoformat(original['issued_at'])
        path = cache / (origin.strftime('%Y%m%dT%H') + '.npz')
        if path.exists():
            with np.load(path) as saved:
                assert saved['fingerprint'].item() == fingerprint
                orders = {name: saved[name] for name in MODELS}
                y = saved['target']
        else:
            prepared, reason = j.prepare(data, origin, grid)
            if prepared is None:
                raise ValueError(reason)
            X, _, _ = prepared
            values = {'candidate': model.predict_proba(X[:, spec['feature_columns']])[:, 1],
                      'kernel': kernel_scores(data, origin, grid, [4])['4']}
            assert all(np.isfinite(v).all() for v in values.values())
            orders = {name: np.lexsort((np.arange(len(v)), -v)).astype('uint32') for name, v in values.items()}
            y, _ = j.labels(data, origin, grid)
            np.savez_compressed(path, **orders, target=y, fingerprint=fingerprint)
        assert int(y.sum()) == original['target_cells_in_mask']
        for name in MODELS:
            histograms[name] += y[orders[name]]
        scope_rows = {}
        for scope, mask in masks.items():
            denominator = original['target_cells_all'] if scope == 'province_candidates' else int(y[mask].sum())
            hits = {}
            for name in MODELS:
                scoped = orders[name][mask[orders[name]]]
                cumulative = np.r_[0, np.cumsum(y[scoped], dtype='int64')]
                hits[name] = [int(cumulative[min(len(scoped), round(area / .25))]) for area in BUDGETS]
            scope_rows[scope] = {'targets': denominator, 'hits': hits}
        assert scope_rows['province_candidates']['hits']['candidate'][5] == original['scores'][spec['model_selected_on2025']]['250.0']['hits']
        assert scope_rows['province_candidates']['hits']['kernel'][5] == original['scores']['kernel']['250.0']['hits']
        rows.append({'issued_at': origin.isoformat(), 'targets_in_mask': int(y.sum()), 'scopes': scope_rows})
        if index % 25 == 0:
            print('watch-budget', index + 1, '/', len(originals), flush=True)
    summary = {'issues': len(rows), 'model_sha256': spec['model_sha256'], 'scopes': {}}
    for scope, mask in masks.items():
        total = sum(row['scopes'][scope]['targets'] for row in rows)
        area = int(mask.sum()) * .25
        curves = []
        for bi, budget in enumerate(BUDGETS):
            hits = {name: sum(row['scopes'][scope]['hits'][name][bi] for row in rows) for name in MODELS}
            coverage = {name: 100 * value / total if total else None for name, value in hits.items()}
            curves.append({'requested_area_km2': budget, 'actual_selected_area_km2': min(budget, area), 'hits': hits,
                           'coverage_pct': coverage, 'gain_pp': coverage['candidate'] - coverage['kernel'] if total else None,
                           **block_intervals(rows, scope, bi)})
        summary['scopes'][scope] = {'candidate_area_km2': area, 'target_cell_periods': total, 'curves': curves}
    total = summary['scopes']['province_candidates']['target_cell_periods']
    summary['province_minimum_fixed_area_for_80pct_retrospective'] = {}
    for name, histogram in histograms.items():
        cumulative = np.cumsum(histogram)
        position = int(np.searchsorted(cumulative, .8 * total))
        summary['province_minimum_fixed_area_for_80pct_retrospective'][name] = ((position + 1) * .25 if position < len(cumulative) else None)
    summary['province_targets_outside_candidates'] = total - sum(row['targets_in_mask'] for row in rows)
    for month in ('01', '02', '03', '04'):
        subset = [row for row in rows if row['issued_at'][5:7] == month]
        denominator = sum(row['scopes']['province_candidates']['targets'] for row in subset)
        summary.setdefault('monthly_250km2', {})[month] = {'issues': len(subset), 'targets': denominator,
            **{name: sum(row['scopes']['province_candidates']['hits'][name][5] for row in subset) / denominator * 100 if denominator else None for name in MODELS}}
    j.write(OUT / 'rows.json', rows)
    j.write(OUT / 'summary.json', summary)
    changed = [name for name, sha in frozen.items() if not (j.ROOT / name).exists() or digest(j.ROOT / name) != sha]
    j.write(OUT / 'production-file-check.json', {'checked_files': len(frozen), 'changed': changed, 'deployment_commands_issued': 0})
    assert not changed, changed
    print(json.dumps({'issues': len(rows), 'area80': summary['province_minimum_fixed_area_for_80pct_retrospective'],
                      'province_curve': summary['scopes']['province_candidates']['curves']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
