"""Time-dependent raster graph using pinned upstream Pyretechnics surface rates.

This is NOT the complete ELMFIRE level-set solver. It compares mapped-fuel,
moisture and wind hypotheses against proper baselines on observed image times.
Initial imagery is retrospective; the reference is optical change, not surveys.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import bisect
import hashlib
import heapq
import json
import math
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'output/reference-tools/pyretechnics')]
from pyretechnics import fuel_models as fm, surface_fire as sf
from fire_research_moisture import equilibria, advance

OUT = ROOT / 'output/fire-perimeter-loop-20261017'
NEIGHBOURS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def verify_frozen_inputs():
    frozen = read(OUT / 'frozen-inputs.json')
    for name, digest in frozen['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, 'Changed frozen source: '+name
    for name, digest in frozen['selection_files'].items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest() == digest, 'Changed frozen selection: '+name
    assert {r['id'] for r in read(OUT/'array-manifest.json')['ready']} == {r['id'] for r in frozen['cases']}
    return frozen


def configs():
    result = [{'name': 'no_growth', 'family': 'stationary', 'seed': 'image'}]
    for seed in ('point', 'image'):
        for speed in (.2, .5, 1.):
            result.append({'name': f'isotropic_{seed}_{speed:g}', 'family': 'isotropic', 'seed': seed, 'speed_m_min': speed})
        for fuel, moisture in (('uniform1', 'fixed8'), ('mapped9', 'fixed8'), ('mapped9', 'dynamic'), ('mapped8', 'dynamic')):
            for scale in (.25, 1.):
                result.append({'name': f'pyre_{fuel}_{moisture}_{seed}_s{scale:g}', 'family': 'pyre_graph',
                    'fuel': fuel, 'moisture': moisture, 'seed': seed, 'scale': scale, 'wind_factor': .2})
    for seed in ('image', 'active'):
        for active_hours in (6, 24):
            result.append({'name': f'pyre_mapped9_dynamic_{seed}_active{active_hours}', 'family': 'pyre_graph',
                'fuel': 'mapped9', 'moisture': 'dynamic', 'seed': seed, 'scale': .25, 'wind_factor': .2,
                'active_hours': active_hours})
    return result


def weather_for(folder, meta):
    raw = read(folder / 'single-run-weather.json')['hourly']
    origin = datetime.fromisoformat(meta['initial_acquisition'])
    end = datetime.fromisoformat(meta['final_acquisition'])
    state = (.08, .10, .12)
    records = []
    for i, value in enumerate(raw['time']):
        when = datetime.fromisoformat(value).replace(tzinfo=origin.tzinfo)
        fields = [raw[key][i] for key in ('wind_speed_10m', 'wind_direction_10m', 'temperature_2m', 'relative_humidity_2m', 'precipitation')]
        if any(v is None or not math.isfinite(v) for v in fields):
            if origin-timedelta(hours=1) <= when <= end:
                raise ValueError('Missing single-run forecast field inside evaluated interval')
            continue
        dry, wet = equilibria(fields[2], fields[3])
        state = advance(state, dry, wet, fields[4])
        if origin.replace(minute=0, second=0, microsecond=0) <= when <= end:
            records.append({'start': (when-origin).total_seconds()/60, 'wind': fields[0], 'from': fields[1],
                            'moisture': state, 'temperature': fields[2], 'rain_mm': fields[4]})
    horizon = (end-origin).total_seconds()/60
    assert records and records[0]['start'] <= 0 and records[-1]['start'] + 60 >= horizon
    run = datetime.fromisoformat(meta['weather']['run_init'])
    assert run + timedelta(hours=6) <= origin
    return records, horizon


class Rates:
    def __init__(self, arrays, records, config):
        self.arrays, self.records, self.config = arrays, records, config
        self.starts = [record['start'] for record in records]

    @lru_cache(maxsize=100000)
    def base(self, hour, fuel):
        moisture = self.records[hour]['moisture'] if self.config.get('moisture') == 'dynamic' else (.08, .08, .08)
        model = fm.moisturize(fm.get_fuel_model(fuel), (*moisture, 0., .5, .8))
        return sf.calc_surface_fire_behavior_no_wind_no_slope(model)

    @lru_cache(maxsize=100000)
    def peak(self, row, col, hour):
        cover = int(self.arrays['landcover'][row, col])
        mapping = self.config['fuel']
        fuel = 1 if mapping == 'uniform1' else {10: 8 if mapping == 'mapped8' else 9, 20: 5}.get(cover, 1)
        weather = self.records[hour]
        value = sf.calc_surface_fire_behavior_max(self.base(hour, fuel),
            weather['wind'] * self.config['wind_factor'] * 60, weather['from'],
            float(self.arrays['slope'][row, col]), float(self.arrays['aspect'][row, col]))
        return value.max_spread_rate, value.eccentricity, value.max_spread_direction

    def travel(self, elapsed, row, col, nr, nc, distance3d, unit3d, horizon):
        if self.config['family'] == 'isotropic':
            return elapsed + distance3d / self.config['speed_m_min']
        remaining = distance3d
        cursor = elapsed
        while cursor < horizon:
            hour = bisect.bisect_right(self.starts, cursor) - 1
            if hour < 0 or hour >= len(self.records):
                return math.inf
            # Use the exact next stored boundary: start+60 can differ by one
            # floating-point ULP and otherwise leave cursor stuck in this hour.
            stop = min(self.starts[hour+1] if hour+1 < len(self.starts) else self.starts[hour]+60, horizon)
            if stop <= cursor:
                raise ValueError('Weather interval cannot advance')
            head, eccentricity, direction = self.peak(row, col, hour)
            cosine = sum(a*b for a, b in zip(unit3d, direction))
            speed = head * (1-eccentricity) / max(1e-9, 1-eccentricity*cosine) * self.config['scale']
            if speed > 0:
                capacity = (stop-cursor)*speed
                if capacity >= remaining:
                    return cursor + remaining/speed
                remaining -= capacity
            cursor = stop
        return math.inf


def simulate(known, records, horizon, config, rates_class=None):
    # Only these initial/terrain arrays enter propagation, never target masks.
    allowed = known['burnable']
    seeds = known['seeds_' + config['seed']]
    arrival = np.full(allowed.shape, np.inf, dtype='float64')
    if config['family'] == 'stationary':
        return arrival
    arrival[seeds] = 0
    horizon = min(horizon, config.get('active_hours', math.inf)*60)
    queue = [(0., int(r), int(c)) for r, c in zip(*np.where(seeds))]
    heapq.heapify(queue)
    rates = (rates_class or Rates)(known, records, config)
    height, width = allowed.shape
    elevation = known['elevation_m']
    while queue:
        elapsed, row, col = heapq.heappop(queue)
        if elapsed != arrival[row, col] or elapsed > horizon:
            continue
        for dr, dc in NEIGHBOURS:
            nr, nc = row+dr, col+dc
            if not (0 <= nr < height and 0 <= nc < width) or not allowed[nr, nc]:
                continue
            if arrival[nr, nc] <= elapsed:
                continue
            if dr and dc and (not allowed[nr, col] or not allowed[row, nc]):
                continue
            delta_z = float(elevation[nr, nc]-elevation[row, col])
            length = math.sqrt((dr*100)**2 + (dc*100)**2 + delta_z**2)
            unit = (dc*100/length, -dr*100/length, delta_z/length)
            reached = rates.travel(elapsed, row, col, nr, nc, length, unit, horizon)
            if reached <= horizon and reached < arrival[nr, nc]:
                arrival[nr, nc] = reached
                heapq.heappush(queue, (reached, nr, nc))
    # Break bound-method LRU references promptly between runs.
    rates.base.cache_clear()
    rates.peak.cache_clear()
    return arrival


def metrics(predicted, arrays, target_key='target_fraction'):
    support = arrays['growth_support_fraction']
    target = arrays[target_key]
    p = float((predicted * support).sum() * .01)
    r = float(target.sum() * .01)
    intersection = float((predicted * target).sum() * .01)
    union = p+r-intersection
    dice = 2*intersection/(p+r) if p+r else 1.
    iou = intersection/union if union else 1.
    initial_known = float((arrays['initial_scar20'] & arrays['valid20']).sum() * .0004)
    cumulative_dice = 2*(initial_known+intersection)/(2*initial_known+p+r) if 2*initial_known+p+r else 1.
    return {'predicted_growth_km2': p, 'reference_growth_km2': r, 'intersection_km2': intersection,
            'dice': dice, 'iou': iou, 'reference_coverage': intersection/r if r else None,
            'known_initial_scar_km2': initial_known, 'cumulative_dice_including_initial': cumulative_dice,
            'unmatched_prediction_km2': p-intersection, 'missed_reference_km2': r-intersection}


def boundary_metrics(predicted, arrays):
    upsampled = np.repeat(np.repeat(predicted, 5, axis=0), 5, axis=1)
    pred = upsampled & arrays['valid20'] & ~arrays['initial_scar20']
    reference = arrays['target20']
    a = pred & ~binary_erosion(pred)
    b = reference & ~binary_erosion(reference)
    if not a.any() or not b.any():
        return {'symmetric_boundary_mean_m': None, 'symmetric_boundary_p95_m': None}
    da, db = distance_transform_edt(~a)*20, distance_transform_edt(~b)*20
    distances = np.r_[da[b], db[a]]
    return {'symmetric_boundary_mean_m': float(distances.mean()), 'symmetric_boundary_p95_m': float(np.percentile(distances, 95))}


def known_arrays(arrays):
    return {key: arrays[key] for key in ('burnable', 'seeds_point', 'seeds_image', 'seeds_active', 'landcover', 'slope', 'aspect', 'elevation_m')}


def evaluate_case(metadata, candidates):
    folder = OUT / 'cases' / metadata['id']
    arrays = dict(np.load(folder / 'model-arrays.npz'))
    known = known_arrays(arrays)
    records, horizon = weather_for(folder, metadata)
    rows = {}
    cache = folder / 'predictions'
    cache.mkdir(exist_ok=True)
    for config in candidates:
        path = cache / (config['name'] + '.npz')
        signature = hashlib.sha256(json.dumps({'solver_version': 2, 'config': config, 'weather': records, 'horizon': horizon}, sort_keys=True).encode())
        for key, value in sorted(known.items()):
            if key == 'seeds_active' and config['seed'] != 'active':
                continue
            signature.update(key.encode()+value.tobytes())
        fingerprint = signature.hexdigest()
        arrival = None
        if path.exists():
            with np.load(path) as saved:
                if saved['known_input_sha256'].item() == fingerprint:
                    arrival = saved['arrival_minutes']
        if arrival is None:
            arrival = simulate(known, records, horizon, config)
            np.savez_compressed(path, arrival_minutes=arrival, known_input_sha256=fingerprint)
        predicted = arrival <= horizon
        rows[config['name']] = {**metrics(predicted, arrays), **boundary_metrics(predicted, arrays),
             'connected_growth': metrics(predicted, arrays, 'connected_target_fraction'),
             'low_reference_threshold': metrics(predicted, arrays, 'target_low_fraction'),
             'high_reference_threshold': metrics(predicted, arrays, 'target_high_fraction'),
             'forecast_reaches_domain_edge': bool(predicted[0].any() or predicted[-1].any() or predicted[:, 0].any() or predicted[:, -1].any())}
        print('SCORE', metadata['id'], config['name'], 'Dice', round(rows[config['name']]['dice'], 4), flush=True)
    return {'id': metadata['id'], 'horizon_hours': horizon/60, 'split': metadata['split'], 'scores': rows}


def aggregate(rows):
    result = {}
    for name in rows[0]['scores']:
        values = [row['scores'][name] for row in rows]
        p = sum(v['predicted_growth_km2'] for v in values)
        r = sum(v['reference_growth_km2'] for v in values)
        i = sum(v['intersection_km2'] for v in values)
        result[name] = {'case_count': len(values), 'macro_dice': float(np.mean([v['dice'] for v in values])),
           'pooled_dice': 2*i/(p+r) if p+r else 1, 'pooled_iou': i/(p+r-i) if p+r-i else 1,
           'predicted_growth_km2': p, 'reference_growth_km2': r, 'intersection_km2': i,
           'empty_reference_cases': sum(v['reference_growth_km2'] == 0 for v in values),
           'domain_edge_cases': sum(v['forecast_reaches_domain_edge'] for v in values)}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('selection', 'test'), required=True)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    if args.phase == 'test' and not args.pilot:
        assert (OUT / 'spread-selection.json').exists(), 'Freeze2025selection before evaluating2026.'
        verify_frozen_inputs()
    if not args.pilot:
        assert (OUT / 'case-manifest.json').exists(), 'Finish all candidate retrievals before final selection.'
    manifest = read(OUT / 'array-manifest.json')['ready']
    split = 'selection2025' if args.phase == 'selection' else 'retrospective_test2026'
    selected = [read(OUT / 'cases' / row['id'] / 'case.json') for row in manifest if row['split'] == split]
    assert selected
    if args.pilot:
        selected = selected[:1]
    candidates = configs()
    protocol = {'mode': 'offline_initial_image_conditioned_fire_growth', 'configs': candidates,
       'physics': read(ROOT / 'output/reference-tools/pyretechnics/SOURCE.json'),
       'solver': 'Own100m8-neighbourtime-dependentFIFOgraph; upstreamPyretechnicsRothermelsurface rates and3Ddirectionalellipse. NOTfullELMFIRElevelset,crownfire,spottingorsuppression.',
       'criterion': 'Highest meancaseDicefornewgrowthonly on2025opticalchange reference. Tie: smaller predicted area then name. Empty-referenceDice1onlyifno predicted growth; otherwise0.',
       'forcing': 'FixedsingleIFSinitialization6hprior; WRFXmoisture starts8/10/12percent at run start and evolveswithT/RH/rain. Live moisture50/80percent, reference assumptions.',
       'fuel': 'UniformFM1orWorldCovertree->FM9orFM8,shrub->FM5,otherburnable->FM1; unmeasuredThai fuels.',
       'initial_seed': 'PastVIIRSpointcells or connectedopticalscar nearpastVIIRS; compare both andselecton2025.',
       'scores': 'Fractional20mreference area versus100mforecast on jointlyclearland excludingknown initialscar. Opticalchange agreement, not independently surveyed physical accuracy.',
       'deployment_commands_issued': 0}
    write(OUT / 'spread-model-protocol.json', protocol)
    rows = [evaluate_case(meta, candidates) for meta in selected]
    summary = aggregate(rows)
    suffix = '-pilot' if args.pilot else ''
    write(OUT / (args.phase+suffix+'-results.json'), {'summary': summary, 'rows': rows})
    if args.phase == 'selection' and not args.pilot:
        ranking = sorted(summary, key=lambda name: (-summary[name]['macro_dice'], summary[name]['predicted_growth_km2'], name))
        write(OUT / 'spread-selection.json', {'selected': ranking[0], 'ranking': ranking, 'validation': summary,
                    'chosen_before_timed2026_test': True, 'criterion': protocol['criterion']})
        print('SELECTED', ranking[0], summary[ranking[0]], flush=True)
    elif args.phase == 'test' and not args.pilot:
        chosen = read(OUT / 'spread-selection.json')['selected']
        print('TEST_SELECTED', chosen, summary[chosen], flush=True)


if __name__ == '__main__':
    main()
