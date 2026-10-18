"""Learn time-matched optical growth from initial-only conditions.

Case-blocked leave-one-case-out2025selection; frozen2026comparison. This
predicts new visible burn candidates over the observed2-7dayimage interval,
not a validated12hfront or verified fire-arrival time. All work is offline.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
import timed_fire_spread_benchmark as physics

OUT = physics.OUT
FOLDER = OUT / 'growth-ml'
THRESHOLDS = (.03, .07, .15, .30, .50)
MODEL_CONFIGS = {'full_small': ('full', 60, 15), 'full_large': ('full', 100, 31),
                 'without_pm': ('without_pm', 60, 15), 'without_wind_pm': ('without_wind_pm', 60, 15)}


def aggregate_initial(image, validity):
    a = np.where(validity, image, np.nan).reshape(100, 5, 100, 5)
    with np.errstate(invalid='ignore'):
        count = np.isfinite(a).sum(axis=(1, 3))
        mean = np.nansum(a, axis=(1, 3))/np.maximum(count, 1)
        second = np.nansum(a*a, axis=(1, 3))/np.maximum(count, 1)
        std = np.sqrt(np.maximum(0, second-mean*mean))
    mean[count == 0] = np.nan
    std[count == 0] = np.nan
    return mean, std


def make_features(metadata, initial, include_pm=True):
    """This function has no reference labels, final image, or future observations."""
    folder = OUT / 'cases' / metadata['id']
    rows, cols = np.indices((100, 100))
    west, south, east, north = metadata['bounds_utm47']
    xy = np.column_stack([west+(cols.ravel()+.5)*100, north-(rows.ravel()+.5)*100])
    points = metadata['initial_hotspots']
    source_xy = np.column_stack(j.projection.transform([p['longitude'] for p in points], [p['latitude'] for p in points]))
    distance, nearest = cKDTree(source_xy).query(xy, workers=1)
    origin = datetime.fromisoformat(metadata['initial_acquisition'])
    age = np.array([(origin-datetime.fromisoformat(p['detected_at'].replace('Z', '+00:00'))).total_seconds()/3600 for p in points])
    assert (age >= 3).all()
    power = np.array([max(0., p.get('frp') or 0.) for p in points])
    count = cKDTree(source_xy).query_ball_point(xy, 1000, return_length=True)
    scar = initial['initial_scar_fraction'] >= .12
    scar_distance = distance_transform_edt(~scar)*100 if scar.any() else np.full((100, 100), 20000.)
    inside_distance = distance_transform_edt(scar)*100
    basic = [initial['elevation_m']/1000, initial['slope'], np.sin(np.radians(initial['aspect'])), np.cos(np.radians(initial['aspect'])),
             *[(initial['landcover'] == c).astype(float) for c in (10, 20, 30, 40)],
             np.log1p(distance).reshape(100, 100), age[nearest].reshape(100, 100)/24,
             np.log1p(power[nearest]).reshape(100, 100), np.log1p(count).reshape(100, 100),
             initial['initial_scar_fraction'], np.log1p(scar_distance), np.log1p(inside_distance)]
    names = ['elevation_km', 'slope', 'aspect_sin', 'aspect_cos', 'forest', 'shrub', 'grass', 'crop',
             'log_distance_hotspot', 'age_hotspot_days', 'log_frp', 'log_hotspots_1km',
             'initial_scar_fraction', 'log_distance_initial_scar', 'log_distance_inside_scar']
    validity = initial['initial_valid20']
    for name, image in [('nbr', initial['initial_nbr']), ('ndvi', (initial['initial_falsecolor'][1]-initial['initial_falsecolor'][2])/
                      np.maximum(initial['initial_falsecolor'][1]+initial['initial_falsecolor'][2], 1e-6)),
                        ('swir', initial['initial_falsecolor'][0]), ('nir', initial['initial_falsecolor'][1]), ('red', initial['initial_falsecolor'][2])]:
        mean, std = aggregate_initial(image, validity)
        basic.extend([mean, std])
        names.extend(['initial_'+name+'_mean', 'initial_'+name+'_std'])
    basic.extend([np.full((100, 100), metadata['horizon_hours']/24), validity.reshape(100, 5, 100, 5).mean(axis=(1, 3))])
    names.extend(['forecast_days', 'initial_clear_fraction'])
    context_count = len(names)
    weather, horizon = physics.weather_for(folder, metadata)
    speed = np.array([w['wind'] for w in weather])
    direction = np.radians([w['from'] for w in weather])
    u, v = float(np.mean(-speed*np.sin(direction))), float(np.mean(-speed*np.cos(direction)))
    norm = max(1e-6, np.hypot(u, v))
    delta = xy-source_xy[nearest]
    along = (delta[:, 0]*u+delta[:, 1]*v)/norm
    cross = np.abs(delta[:, 0]*v-delta[:, 1]*u)/norm
    weather_values = [u, v, speed.mean(), speed.max(), np.mean([w['temperature'] for w in weather]),
                      np.mean([w['moisture'][0] for w in weather]), sum(w['rain_mm'] for w in weather)]
    basic.extend([np.full((100, 100), value) for value in weather_values])
    names.extend(['wind_u', 'wind_v', 'wind_mean', 'wind_max', 'temperature_mean', 'estimated_moisture_mean', 'forecast_rain_sum'])
    basic.extend([np.sign(along).reshape(100, 100)*np.log1p(np.abs(along)).reshape(100, 100), np.log1p(cross).reshape(100, 100)])
    names.extend(['signed_log_alongwind_distance', 'log_crosswind_distance'])
    wind_end = len(names)
    if include_pm:
        dates = physics.read(j.OUT / f'pm-{origin.year}.json')['dates']
        pm = j.pm_features({'pm': dates}, origin.astimezone(j.ICT))
        if pm is None:
            raise ValueError('Missing causally lagged PM station values')
    else:
        # Keep the feature schema stable while permitting a selected ablation
        # to run without fetching inputs its tree never uses.
        pm = np.full(len(j.PM_NAMES),np.nan,dtype='float32')
    basic.extend([np.full((100, 100), value) for value in pm])
    names.extend(['lagged_pm_'+name for name in j.PM_NAMES])
    X = np.column_stack([np.asarray(a).ravel() for a in basic]).astype('float32')
    assert X.shape[1] == len(names) and not np.isinf(X).any()
    groups = {'full': list(range(len(names))), 'without_pm': list(range(wind_end)), 'without_wind_pm': list(range(context_count))}
    return X, names, groups


def load_case(metadata):
    folder = OUT / 'cases' / metadata['id']
    arrays = dict(np.load(folder / 'model-arrays.npz'))
    known_names = ('initial_nbr', 'initial_falsecolor', 'initial_valid20', 'initial_scar_fraction', 'elevation_m', 'slope', 'aspect', 'landcover')
    initial = {name: arrays[name] for name in known_names}
    X, names, groups = make_features(metadata, initial)
    eligible = (X[:, names.index('initial_clear_fraction')] >= .5) & arrays['burnable'].ravel()
    label_valid = arrays['growth_support_fraction'].ravel() >= .8
    return {'metadata': metadata, 'arrays': arrays, 'known': initial, 'X': X, 'names': names, 'groups': groups,
            'eligible': eligible, 'train_valid': eligible & label_valid, 'y': (arrays['target_fraction'].ravel() > 0).astype('uint8')}


def new_model(iterations, leaves):
    return HistGradientBoostingClassifier(max_iter=iterations, max_leaf_nodes=leaves, l2_regularization=2,
           min_samples_leaf=30, early_stopping=False, random_state=20261018)


def baseline_masks(case):
    X, names = case['X'], case['names']
    distance = np.expm1(X[:, names.index('log_distance_hotspot')])
    scar_distance = np.expm1(X[:, names.index('log_distance_initial_scar')])
    vegetation = X[:, names.index('initial_ndvi_mean')] >= .3
    result = {}
    for radius in (100, 250, 500, 1000):
        result['hotspot_fuel_radius'+str(radius)] = (case['eligible'] & vegetation & (distance <= radius)).reshape(100, 100)
        result['scar_fuel_radius'+str(radius)] = (case['eligible'] & vegetation & (scar_distance <= radius)).reshape(100, 100)
    return result


def candidate_name(model, threshold):
    return model+'__threshold'+str(threshold)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('selection', 'test'), required=True)
    args = parser.parse_args()
    FOLDER.mkdir(exist_ok=True)
    assert (OUT / 'case-manifest.json').exists() and (OUT / 'extra-validation-manifest.json').exists(), 'Finish initial-only case discovery before final model selection.'
    if args.phase == 'test':
        assert (FOLDER / 'selection.json').exists()
        physics.verify_frozen_inputs()
    metadata = [physics.read(OUT / 'cases' / item['id'] / 'case.json') for item in physics.read(OUT / 'array-manifest.json')['ready']]
    training = [load_case(item) for item in metadata if item['split'] == 'selection2025']
    assert len(training) >= 4, 'Acquire at least4spatiallyseparate2025case groups before leave-case-out selection.'
    protocol = {'mode': 'offline_time_matched_optical_growth_learning', 'target': 'New visible burn-candidate pixels over exactimageinterval; detached new ignitions included. Not validated12hfirefront.',
      'training': '2025cases;leave-one-entire-case-out predictions select configuration andthreshold. Fitall2025casesonlyafterselection.',
      'test': '2026case-studyimages, already inspected forreference quality butnotusedtofitmodel/selectthreshold. Retrospective, not prospective season.',
      'features': training[0]['names'], 'groups': training[0]['groups'], 'configs': MODEL_CONFIGS, 'thresholds': THRESHOLDS,
      'criterion': 'Meanheldout-caseDiceonfractional20mnew-scarreference; tie smaller predicted growth area then name. Baselines eligible towin.',
      'initial_only': 'No finalimage/reference/aftercloudmask in features or forecasteligibility. Futurecloudmask used onlyaslabel/evaluationvisibility.',
      'pm': 'Observed35T/36TdailyPMdates<=initialICTdate-2. Citycontext, notlocalfirefrontPMorweather.',
      'deployment_commands_issued': 0}
    physics.write(FOLDER / 'protocol.json', protocol)
    if args.phase == 'selection':
        rows = []
        for held_index, held in enumerate(training):
            remaining = [case for i, case in enumerate(training) if i != held_index]
            X = np.vstack([case['X'][case['train_valid']] for case in remaining])
            y = np.concatenate([case['y'][case['train_valid']] for case in remaining])
            scores = {name: physics.metrics(mask, held['arrays']) for name, mask in baseline_masks(held).items()}
            for name, (group, iterations, leaves) in MODEL_CONFIGS.items():
                columns = held['groups'][group]
                model = new_model(iterations, leaves).fit(X[:, columns], y)
                values = model.predict_proba(held['X'][:, columns])[:, 1]
                for threshold in THRESHOLDS:
                    mask = (held['eligible'] & (values >= threshold)).reshape(100, 100)
                    scores[candidate_name(name, threshold)] = physics.metrics(mask, held['arrays'])
            rows.append({'id': held['metadata']['id'], 'scores': scores})
            print('GROWTH_LOCO_FOLD', held['metadata']['id'], 'done', flush=True)
        summary = {name: {'macro_dice': float(np.mean([row['scores'][name]['dice'] for row in rows])),
                          'predicted_growth_km2': sum(row['scores'][name]['predicted_growth_km2'] for row in rows)} for name in rows[0]['scores']}
        ranking = sorted(summary, key=lambda name: (-summary[name]['macro_dice'], summary[name]['predicted_growth_km2'], name))
        physics.write(FOLDER / 'selection.json', {'selected': ranking[0], 'ranking': ranking, 'validation': summary, 'folds': rows, 'chosen_before_2026_model_evaluation': True})
        # Save each ablation to report full-input value on identical2026cases.
        X = np.vstack([case['X'][case['train_valid']] for case in training])
        y = np.concatenate([case['y'][case['train_valid']] for case in training])
        for name, (group, iterations, leaves) in MODEL_CONFIGS.items():
            model = new_model(iterations, leaves).fit(X[:, training[0]['groups'][group]], y)
            joblib.dump(model, FOLDER / (name+'.joblib'))
        print('GROWTH_SELECTED2025', ranking[0], summary[ranking[0]], flush=True)
    else:
        selection = physics.read(FOLDER / 'selection.json')
        chosen = selection['selected']
        rows = []
        for meta in metadata:
            if meta['split'] != 'retrospective_test2026':
                continue
            case = load_case(meta)
            candidates = baseline_masks(case)
            probabilities = {}
            for name, (group, _, _) in MODEL_CONFIGS.items():
                model = joblib.load(FOLDER / (name+'.joblib'))
                values = model.predict_proba(case['X'][:, case['groups'][group]])[:, 1]
                probabilities[name] = values.reshape(100, 100)
                for threshold in THRESHOLDS:
                    candidates[candidate_name(name, threshold)] = (case['eligible'] & (values >= threshold)).reshape(100, 100)
            scores = {name: {**physics.metrics(mask, case['arrays']), **physics.boundary_metrics(mask, case['arrays']),
                       'connected_growth': physics.metrics(mask, case['arrays'], 'connected_target_fraction'),
                       'low_reference_threshold': physics.metrics(mask, case['arrays'], 'target_low_fraction'),
                       'high_reference_threshold': physics.metrics(mask, case['arrays'], 'target_high_fraction')} for name, mask in candidates.items()}
            rows.append({'id': meta['id'], 'cohort': meta['candidate'].get('cohort', 'original_case_studies'), 'horizon_hours': meta['horizon_hours'], 'scores': scores})
            np.savez_compressed(OUT / 'cases' / meta['id'] / 'growth-ml-predictions.npz', **candidates, **{'probability_'+name: v for name, v in probabilities.items()})
            print('GROWTH_TEST', meta['id'], chosen, round(scores[chosen]['dice'], 4), flush=True)
        # Include allresults for transparency; never reselect usingtest scores.
        summary = {}
        for name in rows[0]['scores']:
            values = [row['scores'][name] for row in rows]
            p, r, i = [sum(value[key] for value in values) for key in ('predicted_growth_km2', 'reference_growth_km2', 'intersection_km2')]
            summary[name] = {'macro_dice': float(np.mean([value['dice'] for value in values])),
               'pooled_dice': 2*i/(p+r) if p+r else 1., 'pooled_iou': i/(p+r-i) if p+r-i else 1.,
               'predicted_growth_km2': p, 'reference_growth_km2': r, 'intersection_km2': i}
        physics.write(FOLDER / 'test-results.json', {'selected_on2025': chosen, 'summary': summary, 'rows': rows})
        print('GROWTH_FINAL_SELECTED', chosen, summary[chosen], flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
