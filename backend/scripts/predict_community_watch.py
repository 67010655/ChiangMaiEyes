"""Frozen offline forest watch selection; target labels never read."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import hashlib
from datetime import datetime, timedelta

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
from check_priority_robustness import scores as kernel_scores
from train_community_watch_model import OUT, geometry_index, pool_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--area-km2', type=int, choices=(125, 250, 500), default=250)
    args = parser.parse_args()
    origin = datetime.fromisoformat(args.as_of)
    if origin.tzinfo is None:
        raise ValueError('Timezone required')
    origin = origin.astimezone(j.ICT)
    if origin.hour not in (8, 20) or origin.minute or origin.second or origin.microsecond:
        raise ValueError('Evaluated only at08/20ICT')
    folder = OUT / 'candidate'
    contract = j.read(folder / 'feature-contract.json')
    name = contract['model_family_key']
    grid = j.build_grid()
    features, cell, starts, counts = geometry_index(grid)
    data = j.load(origin.year, grid)
    prepared, reason = j.prepare(data, origin, grid)
    if prepared is None:
        raise ValueError(reason)
    X = prepared[0]
    eligible = data['times'] <= origin.timestamp() - 3 * 3600
    pm_date = str(origin.date() - timedelta(days=2))
    truncated = {**data, **{key: data[key][eligible] for key in ('times', 'xy', 'frp')},
                 'pm': {date: value for date, value in data['pm'].items() if date <= pm_date}}
    repeat, reason = j.prepare(truncated, origin, grid)
    assert repeat is not None, reason
    np.testing.assert_array_equal(X, repeat[0])
    pooled = pool_features(X, cell, starts, counts)
    np.testing.assert_array_equal(pooled, pool_features(repeat[0], cell, starts, counts))
    if name == 'kernel':
        values = np.maximum.reduceat(kernel_scores(data, origin, grid, [4])['4'][cell], starts)
    else:
        path = folder / 'model.joblib'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == contract['model_sha256']
        model = joblib.load(path)
        if name.startswith('forest_'):
            assert model.n_features_in_ == pooled.shape[1] == 160
            values = model.predict_proba(pooled)[:, 1]
        else:
            values = np.maximum.reduceat(model.predict_proba(X[:, contract['parent_feature_columns']])[:, 1][cell], starts)
    values /= (counts * .25) ** contract['area_power']
    order = np.lexsort((np.arange(len(features)), -values))
    lists = np.split(cell, starts[1:])
    union = np.zeros(len(grid['xy']), dtype=bool)
    used = 0
    selected = []
    for forest in order:
        cost = int((~union[lists[forest]]).sum())
        if used + cost <= args.area_km2 / .25:
            selected.append(int(forest))
            union[lists[forest]] = True
            used += cost
    assert used * .25 <= args.area_km2
    result = {'mode': contract['mode'], 'policy': contract['selected_policy_on2025'], 'as_of': origin.isoformat(),
       'valid_until': (origin + timedelta(hours=12)).isoformat(), 'target': contract['target'], 'scope': contract['scope'],
       'score_meaning': contract['score_meaning'], 'requested_area_km2': args.area_km2, 'selected_forests': len(selected),
       'union_watch_area_km2': used * .25, 'labels_read_for_prediction': False,
       'future_input_removal_feature_check': 'exact equality passed',
       'hotspot_last_eligible_acquisition': (origin - timedelta(hours=3)).isoformat(), 'pm_latest_eligible_date': pm_date,
       'forests': [{'rank': rank + 1, 'id': features[i]['properties']['id'], 'name': features[i]['properties']['name'],
                    'rank_score': float(values[i])} for rank, i in enumerate(selected)], 'production_changed': False}
    path = folder / ('forecast-' + origin.strftime('%Y%m%dT%H%M') + f'-area{args.area_km2}.json')
    j.write(path, result)
    j.write(OUT / 'verification.json', {'input_causality': 'Future hotspot rows and PM dates deleted; parent and pooled features exactly unchanged.',
       'pooled_feature_count': pooled.shape[1], 'selected_policy': contract['selected_policy_on2025'],
       'inference_forest_count': len(selected), 'union_area_within_cap': used * .25 <= args.area_km2,
       'target_labels_read_for_prediction': False, 'model_hash_checked': name != 'kernel'})
    print({'file': str(path), 'forests': len(selected), 'union_watch_area_km2': used * .25, 'policy': result['policy']})


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
