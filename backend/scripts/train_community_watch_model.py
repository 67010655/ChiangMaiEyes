"""Offline forest-level candidate: train2024, choose2025, describe2026.

The target is future satellite detections around a community forest, not a fire
perimeter. This experiment does not replace the frozen province model.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import hashlib
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from shapely import STRtree, make_valid, points
from shapely.geometry import shape
from shapely.ops import transform
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
from check_priority_robustness import scores as kernel_scores

OUT = j.ROOT / 'output/community-model-20261017'
COUNTS = (10, 20, 50, 100, 200)
CONFIGS = {'forest_hgb_small': {'max_iter': 60, 'max_leaf_nodes': 15},
           'forest_hgb_large': {'max_iter': 100, 'max_leaf_nodes': 31}}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_index(grid):
    source = j.ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
    features = j.read(source)['features']
    geometries = [make_valid(transform(j.projection.transform, shape(feature['geometry']))).buffer(1000) for feature in features]
    cell, forest = STRtree(geometries).query(points(grid['xy']), predicate='within')
    order = np.lexsort((cell, forest))
    cell, forest = cell[order], forest[order]
    ids, starts = np.unique(forest, return_index=True)
    assert len(ids) == len(features)
    counts = np.diff(np.r_[starts, len(cell)])
    return features, cell, starts, counts


def pool_features(X, cell, starts, counts):
    values = X[cell]
    valid = np.isfinite(values)
    n = np.add.reduceat(valid.astype('int32'), starts)
    means = np.add.reduceat(np.where(valid, values, 0), starts) / np.maximum(n, 1)
    minimum = np.minimum.reduceat(np.where(valid, values, np.inf), starts)
    maximum = np.maximum.reduceat(np.where(valid, values, -np.inf), starts)
    means[n == 0] = np.nan
    minimum[n == 0] = np.nan
    maximum[n == 0] = np.nan
    return np.column_stack([means, minimum, maximum, np.log1p(counts * .25)]).astype('float32')


def prepare_year(year, grid, index, cell_model, columns):
    features, cell, starts, counts = index
    path = OUT / f'features-{year}.npz'
    if path.exists():
        return dict(np.load(path))
    data = j.load(year, grid)
    Xs, ys, issues, cell_scores, kernels, skipped = [], [], [], [], [], []
    if year in (2025, 2026):
        times = [row['issued_at'] for row in j.read(j.OUT / 'spatial-pm-comparison' / f'results-{year}.json')['rows']]
        origins = [datetime.fromisoformat(value) for value in times]
    else:
        origins = list(j.issues(year))
    for number, origin in enumerate(origins):
        prepared, reason = j.prepare(data, origin, grid)
        if prepared is None:
            skipped.append({'issue': origin.isoformat(), 'reason': reason})
            continue
        X, _, _ = prepared
        Xs.append(pool_features(X, cell, starts, counts))
        y, _ = j.labels(data, origin, grid)
        ys.append(np.logical_or.reduceat(y[cell].astype(bool), starts).astype('uint8'))
        # Comparing frozen parent model and kernel with the same forest scope.
        if year != 2024:
            parent = cell_model.predict_proba(X[:, columns])[:, 1]
            baseline = kernel_scores(data, origin, grid, [4])['4']
            cell_scores.append(np.maximum.reduceat(parent[cell], starts))
            kernels.append(np.maximum.reduceat(baseline[cell], starts))
        issues.append(origin.isoformat())
        if number % 35 == 0:
            print('forest-features', year, number + 1, '/', len(origins), flush=True)
    result = {'X': np.stack(Xs), 'y': np.stack(ys), 'issued_at': np.array(issues)}
    if year != 2024:
        result.update(cell_candidate=np.stack(cell_scores), kernel=np.stack(kernels))
    np.savez_compressed(path, **result)
    j.write(OUT / f'features-{year}.receipt.json', {'issues': len(issues), 'shape': result['X'].shape,
         'positive_forest_rounds': int(result['y'].sum()), 'skipped': skipped, 'sha256': sha(path)})
    return result


def evaluate(dataset, models, index):
    _, cell, starts, _ = index
    lists = np.split(cell, starts[1:])
    y = dataset['y']
    forecasts = {name: model.predict_proba(dataset['X'].reshape(-1, dataset['X'].shape[-1]))[:, 1].reshape(y.shape)
                 for name, model in models.items()}
    forecasts.update({name: dataset[name] for name in ('cell_candidate', 'kernel')})
    rows = []
    for issue_index, issued_at in enumerate(dataset['issued_at']):
        row = {'issued_at': str(issued_at), 'targets': int(y[issue_index].sum()), 'models': {}}
        for name, values in forecasts.items():
            assert np.isfinite(values[issue_index]).all()
            order = np.lexsort((np.arange(y.shape[1]), -values[issue_index]))
            row['models'][name] = {str(n): {'hits': int(y[issue_index, order[:n]].sum()),
                  'union_area_km2': len(np.unique(np.concatenate([lists[i] for i in order[:n]]))) * .25}
                  for n in COUNTS}
        rows.append(row)
    total = int(y.sum())
    summary = {'issues': len(rows), 'positive_forest_rounds': total, 'models': {}}
    for name in forecasts:
        summary['models'][name] = {}
        for n in COUNTS:
            hits = sum(row['models'][name][str(n)]['hits'] for row in rows)
            summary['models'][name][str(n)] = {'hits': hits, 'coverage_pct': hits / total * 100,
                 'mean_union_area_km2': float(np.mean([row['models'][name][str(n)]['union_area_km2'] for row in rows]))}
    return {'summary': summary, 'rows': rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    grid = j.build_grid()
    index = geometry_index(grid)
    contract = j.read(j.OUT / 'final-candidate/feature-contract.json')
    assert contract['feature_pipeline'] == 'joint53'
    parent = joblib.load(j.OUT / 'final-candidate/model.joblib')
    source_paths = [j.OUT / 'final-candidate/model.joblib', j.OUT / 'final-candidate/feature-contract.json',
         j.OLD / 'grid.npz', j.ROOT / 'backend/app/data/community-forests-chiangmai.geojson',
         Path(__file__), Path(j.__file__), Path(__file__).with_name('priority_forecast_experiment.py'),
         Path(__file__).with_name('check_priority_robustness.py')]
    for year in (2024, 2025, 2026):
        source_paths.extend([j.OUT / f'pm-{year}.json', j.OUT / f'gfs-spatial-{year}.json',
                            j.OLD / f'gfs-weather-{year}.json', j.ROOT / f'output/hindcast-{year}/firms-points.json'])
    source_paths.extend([j.OUT / 'spatial-pm-comparison' / f'results-{year}.json' for year in (2025, 2026)])
    sources = {str(path.relative_to(j.ROOT)).replace('\\', '/'): sha(path) for path in source_paths}
    protocol = {'version': 1, 'mode': 'offline_forest_level_model_comparison', 'train': 2024, 'choose': 2025,
        'retrospective_test': 2026, 'test_status': 'Already inspected at cell level. Not an untouched prospective season.',
        'scope': '677 supplied forest polygons buffered1000m;500m candidate-cell centre membership.',
        'target': 'Any next12h nominal/high VIIRS detection-cell centre in forest buffer. Overlapping forests can share detections; not distinct verified incidents.',
        'features': [f'{pool}__{name}' for pool in ('mean', 'minimum', 'maximum') for name in j.ALL_NAMES] + ['log1p_candidate_buffer_area_km2'],
        'hotspot_delay_hours': 3, 'pm_latest_eligible_date_lag_days': 2,
        'configs': CONFIGS, 'selection': 'Highest pooled2025 coverage among top50 forest lists. Tie: smaller mean watched area, then name. All four comparators eligible.',
        'comparison': 'Same forest count; also report union watch area. Not an equal-area or verified false-alarm benchmark.',
        'source_sha256': sources, 'parent_model_sha256': contract['model_sha256'], 'deployment_commands_issued': 0}
    old = OUT / 'protocol.json'
    if old.exists():
        assert j.read(old) == json.loads(json.dumps(protocol)), 'Protocol or inputs changed; start a new experiment directory.'
    j.write(old, protocol)
    train = prepare_year(2024, grid, index, parent, contract['feature_columns'])
    models = {}
    for name, config in CONFIGS.items():
        path = OUT / (name + '.joblib')
        if path.exists():
            model = joblib.load(path)
        else:
            model = HistGradientBoostingClassifier(**config, l2_regularization=.5, early_stopping=False, random_state=20261018)
            model.fit(train['X'].reshape(-1, train['X'].shape[-1]), train['y'].ravel())
            joblib.dump(model, path)
        models[name] = model
        print('forest-trained', name, flush=True)
    validation = prepare_year(2025, grid, index, parent, contract['feature_columns'])
    val_path = OUT / 'validation-2025.json'
    val = j.read(val_path) if val_path.exists() else evaluate(validation, models, index)
    j.write(val_path, val)
    ranked = sorted(val['summary']['models'], key=lambda name: (-val['summary']['models'][name]['50']['hits'],
                      val['summary']['models'][name]['50']['mean_union_area_km2'], name))
    selection = {'selected': ranked[0], 'criterion': protocol['selection'], 'ranking_2025': ranked,
                 'validation2025': val['summary'], 'selected_before_this_experiment_test2026': True}
    j.write(OUT / 'selection.json', selection)
    print('FOREST SELECTION2025', json.dumps(selection), flush=True)
    test = prepare_year(2026, grid, index, parent, contract['feature_columns'])
    result = evaluate(test, models, index)
    j.write(OUT / 'test-2026.json', result)
    j.write(OUT / 'decision.json', {'selected_on2025': ranked[0], 'test': result['summary'],
              'changes_to_parent_or_production': False, 'not_fire_spread_accuracy': True})
    print('FOREST RESULT2026', json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
