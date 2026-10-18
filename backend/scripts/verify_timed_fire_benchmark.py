"""Numerical, time-causality and source-calibration checks for timed hindcasts."""
import json
import hashlib
from datetime import timedelta
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits

import timed_fire_spread_benchmark as b


def fixtures():
    shape = (11, 11)
    known = {'burnable': np.ones(shape, dtype=bool), 'seeds_point': np.zeros(shape, dtype=bool),
             'seeds_image': np.zeros(shape, dtype=bool), 'seeds_active': np.zeros(shape, dtype=bool),
             'elevation_m': np.zeros(shape), 'slope': np.zeros(shape), 'aspect': np.zeros(shape),
             'landcover': np.full(shape, 10)}
    known['seeds_point'][5, 5] = True
    iso = {'family': 'isotropic', 'seed': 'point', 'speed_m_min': .5}
    arrival = b.simulate(known, [], 200, iso)
    assert np.isfinite(arrival).sum() == 5
    assert arrival[5, 6] == 200 and arrival[6, 6] == np.inf
    known['burnable'][:, 6] = False
    arrival = b.simulate(known, [], 3000, iso)
    assert not np.isfinite(arrival[:, 7:]).any(), 'No propagation through a nonburnable wall'
    records = [{'start': h*60, 'wind': 3., 'from': 270., 'moisture': (.08, .08, .08)} for h in range(200)]
    config = {'family': 'pyre_graph', 'seed': 'point', 'fuel': 'mapped9', 'moisture': 'fixed8', 'scale': 1., 'wind_factor': .2}
    rates = b.Rates(known, records, config)
    head, eccentricity, direction = rates.peak(5, 5, 0)
    assert head > 0 and direction[0] > .99, 'Windfrom270mustpromotefiretowardEast'
    east = rates.travel(0, 5, 5, 5, 6, 100, (1., 0., 0.), 12000)
    west = rates.travel(0, 5, 5, 5, 4, 100, (-1., 0., 0.), 12000)
    assert east < west
    rates.base.cache_clear()
    rates.peak.cache_clear()
    class KnownRates(b.Rates):
        def peak(self, row, col, hour):
            return (1 if hour == 0 else 2), 0, (0., 1., 0.)
    rates = KnownRates(known, records, config)
    assert rates.travel(0, 5, 5, 5, 6, 100, (1., 0., 0.), 200) == 80
    fractional = [{**record, 'start': record['start']-.936833333333333} for record in records]
    rates = KnownRates(known, fractional, config)
    expected = (60-.936833333333333)+(100-(60-.936833333333333))/2
    assert abs(rates.travel(0, 5, 5, 5, 6, 100, (1., 0., 0.), 200)-expected) < 1e-10
    # Surface-area growth metrics must not count known initial scar as prediction.
    arrays = {'growth_support_fraction': np.ones((2, 2)), 'target_fraction': np.array([[1., 0], [0, 0]]),
              'initial_scar20': np.ones((10, 10), dtype=bool), 'valid20': np.ones((10, 10), dtype=bool)}
    zero = b.metrics(np.zeros((2, 2), dtype=bool), arrays)
    assert zero['dice'] == 0 and zero['cumulative_dice_including_initial'] > .8
    hit = b.metrics(np.array([[True, False], [False, False]]), arrays)
    assert hit['dice'] == 1 and hit['iou'] == 1
    return {'isotropic_known_arrivals': 'passed', 'nonburnable_barrier': 'passed',
            'wind_from270_spreads_east': 'passed', 'edge_integrates_hourly_changes': 'passed',
            'fractional_image_time_crosses_hour_boundary': 'passed',
            'growth_vs_cumulative_score_distinction': 'passed'}


def current_sources():
    folder = b.OUT / 'cases/2025-03-24'
    old_path = folder / 'S2B_47QMV_20250317_0_L2A.npz'
    new_path = folder / 'S2B_T47QMV_20250317T040533_L2A.npz'
    proof = {}
    if old_path.exists() and new_path.exists():
        with np.load(old_path) as old, np.load(new_path) as new:
            for key in ('red', 'nir08', 'swir22'):
                difference = float(np.nanmedian(new[key]-old[key]))
                assert abs(difference-.1) < 1e-5
                proof[key+'_median_difference'] = difference
    else:
        raise AssertionError('Retain both old and Collection1matched windows for calibration proof.')
    count = 0
    for path in (b.OUT / 'cases').glob('*/case.json'):
        meta = b.read(path)
        assert meta['collection'] == 'sentinel-2-c1-l2a'
        origin = b.datetime.fromisoformat(meta['initial_acquisition'])
        run = b.datetime.fromisoformat(meta['weather']['run_init'])
        assert run + b.timedelta(hours=6) <= origin
        for point in meta['initial_hotspots']:
            acquired = b.datetime.fromisoformat(point['detected_at'].replace('Z', '+00:00'))
            assert acquired + b.timedelta(hours=3) <= origin
        count += 1
    return {'old_collection_double_offset_detected_and_excluded': proof,
            'all_cases_single_run_and_past_hotspot_time_check': count}


def main():
    result = {'fixtures': fixtures(), 'sources': current_sources(), 'deployment_commands_issued': 0}
    if (b.OUT/'frozen-inputs.json').exists():
        frozen = b.verify_frozen_inputs()
        result['frozen_case_count'] = len(frozen['cases'])
    if (b.OUT/'growth-ml/test-results.json').exists():
        import predict_timed_fire_candidate as candidate
        import timed_fire_growth_ml as ml
        selection = b.read(ml.FOLDER/'selection.json')
        physics_selection = b.read(b.OUT/'spread-selection.json')
        meta = b.read(b.OUT/'cases/2026-03-27/case.json')
        folder = b.OUT/'cases'/meta['id']
        initial = candidate.load_initial(folder/'model-arrays.npz')
        predictions = np.load(folder/'growth-ml-predictions.npz')
        choices = [selection['selected']]
        choices += [next(name for name in selection['ranking'] if name.startswith(prefix+'__')) for prefix in ml.MODEL_CONFIGS]
        for name in choices:
            predicted, X = candidate.predict(meta, initial, name)
            assert np.array_equal(predicted,predictions[name]), 'Packed candidate must reproduce stored evaluation'
        # Verify against an archive containing ONLY initial fields: accessing
        # any future label/image would now fail with KeyError.
        path = b.OUT/'initial-only-replay.npz'
        np.savez_compressed(path, **initial)
        stripped = candidate.load_initial(path)
        predicted, X = candidate.predict(meta,stripped)
        assert np.array_equal(predicted,predictions[selection['selected']])
        # Alter/remove PM dates newer than the causal cutoff; features unchanged.
        original_read = b.read
        origin = ml.datetime.fromisoformat(meta['initial_acquisition']).astimezone(ml.j.ICT)
        cutoff = str(origin.date()-timedelta(days=2))
        def past_only_read(path):
            value = original_read(path)
            if path.name == 'pm-2026.json':
                value = {**value,'dates':{date:row for date,row in value['dates'].items() if date<=cutoff}}
            return value
        b.read = past_only_read
        try:
            _, filtered_X = candidate.predict(meta, stripped)
        finally:
            b.read = original_read
        assert np.array_equal(X,filtered_X,equal_nan=True)
        with np.load(folder/'model-arrays.npz') as archive:
            known = {key:archive[key] for key in ('burnable','seeds_point','seeds_image','seeds_active','landcover','slope','aspect','elevation_m')}
        records,horizon = b.weather_for(folder,meta)
        config = next(c for c in b.configs() if c['name']==physics_selection['selected'])
        arrival = b.simulate(known,records,horizon,config)
        saved = np.load(folder/'predictions'/(config['name']+'.npz'))['arrival_minutes']
        assert np.array_equal(arrival,saved)
        result['inference']={'initial_only_archive_replay':'passed','future_pm_removed_features_unchanged':'passed',
             'growth_policy_and_four_ablation_replays':'passed','physics_initial_only_replay':'passed',
             'future_labels_or_after_cloud_masks_loaded_by_predictor':False}
    if (b.OUT/'growth-20m/test-results.json').exists():
        import timed_fire_growth_dense as dense
        receipt=b.read(dense.OUT/'frozen-selection.json')
        assert receipt['selection_sha256']==hashlib.sha256((dense.OUT/'selection.json').read_bytes()).hexdigest()
        for name,digest in receipt['weights'].items():
            assert digest==hashlib.sha256((dense.OUT/(name+'.joblib')).read_bytes()).hexdigest()
        folder=b.OUT/'cases/2026-03-27'
        with np.load(folder/'model-arrays.npz') as archive:
            initial={key:archive[key] for key in dense.KNOWN}
        replay=b.OUT/'initial-only-20m-replay.npz'
        np.savez_compressed(replay,**initial)
        with np.load(replay) as archive:
            initial={key:archive[key] for key in dense.KNOWN}
        selected=b.read(dense.OUT/'selection.json')['selected']
        result20=dense.predict(b.read(folder/'case.json'),initial)
        expected=np.load(folder/'growth-20m-predictions.npz')[selected]
        assert np.array_equal(result20,expected)
        result['inference']['native20m_initial_only_replay']='passed'
    production = b.read(b.ROOT/'output/joint-fire-model-20261017/production-files-frozen.json')
    current = {path:hashlib.sha256((b.ROOT/path).read_bytes()).hexdigest() for path in production}
    assert current==production, 'Production file changed during offline experiment'
    result['production']={'unchanged_files':len(current),'hashes':current,'deployment_commands_issued':0}
    b.write(b.OUT / 'numerical-verification.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
