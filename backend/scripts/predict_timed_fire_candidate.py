"""Offline replay of the 2025-selected optical-growth candidate, initial inputs only.

Not connected to production. Input case provides acquisition-time optical state,
past hotspots, terrain, one forecast run and lagged PM; never final imagery/labels.
"""
import argparse
import json
import joblib
import numpy as np
from threadpoolctl import threadpool_limits
import timed_fire_growth_ml as ml

KNOWN = ('initial_nbr', 'initial_falsecolor', 'initial_valid20', 'initial_scar_fraction',
         'elevation_m', 'slope', 'aspect', 'landcover', 'burnable')


def predict(metadata, initial, selected=None):
    # This accepts an initial-only dictionary; accessing a future key is impossible.
    assert set(initial) == set(KNOWN)
    if selected is None:
        selected = ml.physics.read(ml.FOLDER / 'selection.json')['selected']
    X, names, groups = ml.make_features(metadata, initial)
    eligible = (X[:, names.index('initial_clear_fraction')] >= .5) & initial['burnable'].ravel()
    case = {'X': X, 'names': names, 'groups': groups, 'eligible': eligible}
    if '__threshold' not in selected:
        mask = ml.baseline_masks(case)[selected]
    else:
        name, threshold = selected.split('__threshold')
        group = ml.MODEL_CONFIGS[name][0]
        model = joblib.load(ml.FOLDER / (name+'.joblib'))
        values = model.predict_proba(X[:, groups[group]])[:, 1]
        mask = (eligible & (values >= float(threshold))).reshape(100,100)
    return mask, X


def load_initial(path):
    # NpzFile is lazy: only explicitly whitelisted members are decompressed/read.
    with np.load(path) as archive:
        return {name: archive[name] for name in KNOWN}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--family', choices=('best', 'physics', 'growth_policy', 'dense20m'), default='best')
    args = parser.parse_args()
    folder = ml.OUT / 'cases' / args.case
    meta = ml.physics.read(folder / 'case.json')
    physics_selection = ml.physics.read(ml.OUT/'spread-selection.json')
    growth_selection = ml.physics.read(ml.FOLDER/'selection.json')
    physics_name, growth_name = physics_selection['selected'], growth_selection['selected']
    family = args.family
    dense_selection_path = ml.OUT/'growth-20m/selection.json'
    dense_selection = ml.physics.read(dense_selection_path) if dense_selection_path.exists() else None
    if family == 'best':
        validation = {'physics':physics_selection['validation'][physics_name]['macro_dice'], 'growth_policy':growth_selection['validation'][growth_name]['macro_dice']}
        if dense_selection:
            validation['dense20m']=dense_selection['validation'][dense_selection['selected']]['macro_dice']
        family=max(validation,key=validation.get)
    if family == 'dense20m':
        import timed_fire_growth_dense as dense
        with np.load(folder/'model-arrays.npz') as archive:
            known={key:archive[key] for key in dense.KNOWN}
        result=dense.predict(meta,known)
    elif family == 'physics':
        keys = ('burnable', 'seeds_point', 'seeds_image', 'seeds_active', 'landcover', 'slope', 'aspect', 'elevation_m')
        with np.load(folder/'model-arrays.npz') as archive:
            known = {name: archive[name] for name in keys}
        records, horizon = ml.physics.weather_for(folder,meta)
        config = next(c for c in ml.physics.configs() if c['name']==physics_name)
        result = ml.physics.simulate(known,records,horizon,config) <= horizon
    else:
        result, _ = predict(meta, load_initial(folder/'model-arrays.npz'))
    np.savez_compressed(args.output, predicted_growth_native=result, resolution_m=20 if result.shape==(500,500) else 100, bounds_utm47=meta['bounds_utm47'])
    print(json.dumps({'case': args.case, 'family':family, 'predicted_cells': int(result.sum()), 'output': args.output}))


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
