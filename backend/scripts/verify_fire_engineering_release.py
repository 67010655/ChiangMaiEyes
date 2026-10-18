"""Verify the committed offline handover without raw caches, network or API imports.

This checks inference reproducibility, not prediction accuracy on new fires.
Full historical validation is recorded separately in verification.json.
"""
import json
import sys
import tempfile
import shutil
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

import fire_engineering_common as c
import fire_research_geography as geo
import finalize_refit_fire_engineering as final
from verify_timed_fire_benchmark import fixtures


def verify():
    checks = fixtures()
    registry = c.read(c.OUT / 'MODEL_REGISTRY.json')
    assert registry['production_promoted'] is False
    for role in ('priority', 'growth'):
        entry = registry[role]
        path = c.ROOT / entry['path']
        assert c.sha(path) == entry['sha256'], role + ' weights changed'
        model = joblib.load(path)
        contract_path = entry.get('contract') if role == 'priority' else str(path.parent / 'feature-contract.json')
        contract = c.read(c.ROOT / contract_path)
        names = contract.get('feature_names')
        assert model.n_features_in_ == (len(names) if names else len(contract['feature_columns']))
    for name, digest in c.read(final.r.OUT / 'frozen-selection.json')['files'].items():
        assert c.sha(final.r.OUT / name) == digest
    for name, digest in c.read(c.OUT / 'code-sha256.json').items():
        assert c.sha(c.ROOT / 'backend/scripts' / name) == digest
    checks['frozen_models_and_selection'] = 'PASS'
    # The same loaders used during case preparation must validate both rasters.
    terrain, values = geo.terrain_dataset()
    cover, classes = geo.landcover_dataset()
    assert len(values) == len(classes) == terrain['width'] * terrain['height']
    assert len(geo._province_ring()) > 3
    checks['aligned_checksum_verified_gis'] = 'PASS'
    checks['replays'] = []
    for source in sorted((final.r.OUT / 'replay').iterdir()):
        if not source.is_dir():
            continue
        case_id = source.name
        files = {p.name for p in (source / 'cases' / case_id).iterdir()}
        assert files == {'case.json', 'initial-state.npz', 'single-run-weather.json'}
        with np.load(source / 'prediction.npz', allow_pickle=False) as archive:
            expected = {key: archive[key] for key in archive.files}
        # Replay writes only inside a temporary copy; committed evidence is immutable.
        with tempfile.TemporaryDirectory(prefix='cme-fire-replay-') as temp:
            target = Path(temp) / case_id
            shutil.copytree(source, target)
            final.replay(target, case_id)
            with np.load(target / 'prediction.npz', allow_pickle=False) as actual:
                assert set(actual.files) == set(expected)
                for key, value in expected.items():
                    np.testing.assert_array_equal(actual[key], value)
        checks['replays'].append({'case': case_id, 'all_four_arrays_exact': True, 'future_labels_in_input': False})
    assert len(checks['replays']) == 2
    assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
    checks['no_live_api_imports'] = 'PASS'
    return {'status': 'PASS', 'scope': 'committed offline inference and numerical contracts; not new accuracy validation', 'checks': checks}


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
