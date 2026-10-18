"""Forest-domain cell models, with2025selection before retrospective2026.

This retains the fixed250km2 cell-selection task in the forest+1km scope.
It is separate from ranking whole forests or predicting physical perimeters.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import hashlib
import json
from datetime import datetime

import joblib
import numpy as np
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
from check_priority_robustness import scores as kernel_scores

OUT = j.ROOT / 'output/community-cell-model-20261017'
CONFIGS = {'scoped_hgb_small': {'max_iter': 60, 'max_leaf_nodes': 15},
           'scoped_hgb_large': {'max_iter': 100, 'max_leaf_nodes': 31}}


def evaluate(year, grid, mask, models):
    data = j.load(year, grid)
    target_indices = np.flatnonzero(mask)
    parent = joblib.load(j.OUT / 'final-candidate/model.joblib')
    rows = []
    origins = [datetime.fromisoformat(row['issued_at']) for row in j.read(j.OUT / 'spatial-pm-comparison' / f'results-{year}.json')['rows']]
    for number, origin in enumerate(origins):
        path = OUT / f'rows-{year}' / (origin.strftime('%Y%m%dT%H') + '.json')
        if path.exists():
            rows.append(j.read(path))
            continue
        prepared, reason = j.prepare(data, origin, grid)
        if prepared is None:
            raise ValueError(reason)
        X = prepared[0][mask]
        forecasts = {name: model.predict_proba(X)[:, 1] for name, model in models.items()}
        forecasts['parent'] = parent.predict_proba(X)[:, 1]
        forecasts['kernel'] = kernel_scores(data, origin, grid, [4])['4'][mask]
        y, _ = j.labels(data, origin, grid)
        y = y[mask]
        row = {'issued_at': origin.isoformat(), 'targets': int(y.sum()), 'hits': {}}
        for name, values in forecasts.items():
            order = np.lexsort((target_indices, -values))
            row['hits'][name] = {str(b): int(y[order[:round(b / .25)]].sum()) for b in (125, 250, 500)}
        j.write(path, row)
        rows.append(row)
        if number % 40 == 0:
            print('scoped-cell', year, number + 1, '/', len(origins), flush=True)
    n = sum(row['targets'] for row in rows)
    summary = {'issues': len(rows), 'target_cell_periods': n,
       'models': {name: {str(b): {'hits': sum(row['hits'][name][str(b)] for row in rows),
                    'coverage_pct': sum(row['hits'][name][str(b)] for row in rows) / n * 100}
                 for b in (125, 250, 500)} for name in rows[0]['hits']}}
    return {'summary': summary, 'rows': rows}


def main():
    OUT.mkdir(exist_ok=True)
    for year in (2025, 2026):
        (OUT / f'rows-{year}').mkdir(exist_ok=True)
    grid = j.build_grid()
    with np.load(j.ROOT / 'output/watch-budget-20261017/scope-masks.npz') as scopes:
        mask = scopes['community_forest_plus_1km']
    with np.load(j.OUT / 'training2024.npz') as cached:
        X, y = cached['X'], cached['y']
    distance, indices = cKDTree(grid['static'][:, :2]).query(X[:, :2], workers=1)
    assert distance.max() < 1e-7
    keep = mask[indices]
    X, y = X[keep], y[keep]
    protocol = {'version': 1, 'mode': 'offline_domain_restricted_cell_model', 'train': 2024, 'choose': 2025,
       'retrospective_test': 2026, 'test_status': '2026 previously inspected; all results retrospective.',
       'scope': 'Fixed existing500m candidate-cell centres in community forest polygon union+1000m buffer.',
       'target': 'Next12h nominal/high VIIRS positive cells; not physical fire perimeter.',
       'training': 'Reuse2024full-input training rows, retain only rows in fixed community scope. All original positive rows in scope; uniform sampled negatives inherited from parent training. Scores not calibrated probabilities.',
       'training_rows': len(y), 'training_positive_rows': int(y.sum()), 'features': j.ALL_NAMES,
       'configs': CONFIGS, 'criterion': 'Best pooled2025 positive-cell coverage at250km2 among new scoped models,parent and kernel. Tie by name.',
       'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(),
       'training_sha256': hashlib.sha256((j.OUT / 'training2024.npz').read_bytes()).hexdigest(),
       'deployment_commands_issued': 0}
    prior = OUT / 'protocol.json'
    if prior.exists():
        assert j.read(prior) == json.loads(json.dumps(protocol))
    j.write(prior, protocol)
    models = {}
    for name, config in CONFIGS.items():
        path = OUT / (name + '.joblib')
        if not path.exists():
            model = HistGradientBoostingClassifier(**config, l2_regularization=.5, early_stopping=False, random_state=20261018)
            model.fit(X, y)
            joblib.dump(model, path)
        models[name] = joblib.load(path)
    validation = evaluate(2025, grid, mask, models)
    j.write(OUT / 'validation-2025.json', validation)
    ranking = sorted(validation['summary']['models'], key=lambda name: (-validation['summary']['models'][name]['250']['hits'], name))
    selection = {'selected_on2025': ranking[0], 'ranking2025': ranking, 'selection_before_scoped2026_evaluation': True,
                 'validation': validation['summary']}
    j.write(OUT / 'selection.json', selection)
    print('SCOPED SELECTION2025', selection, flush=True)
    test = evaluate(2026, grid, mask, models)
    j.write(OUT / 'test-2026.json', test)
    chosen = ranking[0]
    j.write(OUT / 'decision.json', {'selected_on2025': chosen, 'test': test['summary'],
        'production_changed': False, 'target': protocol['target']})
    print('SCOPED RESULT2026', test['summary'], flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
