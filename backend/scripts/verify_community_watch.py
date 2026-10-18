"""Check packed inference without labels, causal pooling and replay parity."""
import hashlib
import sys

import numpy as np
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
import priority_forecast_experiment as p
import predict_community_watch as predictor
from train_community_watch_model import OUT, pool_features


def forbidden_labels(*args, **kwargs):
    raise AssertionError('Inference attempted to read target labels')


def main():
    X = np.tile(np.arange(53, dtype='float32'), (4, 1))
    X[:, 0] = [1, np.nan, 3, 9]
    X[:, 1] = np.nan
    pooled = pool_features(X, np.arange(4), np.array([0, 3]), np.array([3, 1]))
    assert pooled.shape == (2, 160)
    np.testing.assert_allclose(pooled[:, 0], [2, 9])
    np.testing.assert_allclose(pooled[:, 53], [1, 9])
    np.testing.assert_allclose(pooled[:, 106], [3, 9])
    assert np.isnan(pooled[:, [1, 54, 107]]).all()
    np.testing.assert_allclose(pooled[:, -1], np.log1p([.75, .25]), rtol=1e-6)
    j.labels = forbidden_labels
    p.labels = forbidden_labels
    sys.argv = ['predict_community_watch.py', '--as-of', '2026-04-15T01:00:00Z', '--area-km2', '250']
    predictor.main()
    forecast = j.read(OUT / 'candidate/forecast-20260415T0800-area250.json')
    assert forecast['as_of'] == '2026-04-15T08:00:00+07:00'
    test = j.read(OUT / 'area-budget/test-2026.json')
    row = next(item for item in test['rows'] if item['issued_at'] == forecast['as_of'])
    expected = row['policies'][forecast['policy']]['250']
    assert expected['selected_forests'] == forecast['selected_forests']
    assert expected['union_area_km2'] == forecast['union_watch_area_km2'] <= 250
    geometry = j.read(j.ROOT / 'backend/app/data/community-forests-chiangmai.geojson')['features']
    lookup = {feature['properties']['id']: i for i, feature in enumerate(geometry)}
    selected = [lookup[item['id']] for item in forecast['forests']]
    assert len(set(selected)) == len(selected)
    with np.load(OUT / 'features-2026.npz') as cache:
        index = list(cache['issued_at']).index(forecast['as_of'])
        assert int(cache['y'][index, selected].sum()) == expected['hits']
    contract = j.read(OUT / 'candidate/feature-contract.json')
    source_mismatches = [name for name, sha in contract['input_source_sha256'].items()
                         if hashlib.sha256((j.ROOT / name).read_bytes()).hexdigest() != sha]
    assert not source_mismatches
    frozen = j.read(j.OUT / 'production-files-frozen.json')
    unchanged = all(hashlib.sha256((j.ROOT / name).read_bytes()).hexdigest() == sha for name, sha in frozen.items())
    assert unchanged
    result = {**j.read(OUT / 'verification.json'), 'pooling_known_values_and_missing_data': 'passed',
       'target_label_function_blocked_during_inference': 'passed', 'UTC_to_ICT': 'passed',
       'packed_forecast_matches_test_replay': 'passed', 'forecast_forest_ids_unique': 'passed',
       'source_hashes_unchanged': len(contract['input_source_sha256']),
       'original_production_snapshot_files_unchanged': len(frozen), 'deployment_commands_issued': 0}
    j.write(OUT / 'verification.json', result)
    print(result, flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
