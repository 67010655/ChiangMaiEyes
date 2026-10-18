"""Choose watch-list policy on2025 with a fixed union-area budget.

This prevents a higher forest-count recall from being called an improvement
merely because selected forests are larger. No model training or deployment.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import json

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

import joint_fire_experiment as j
from train_community_watch_model import OUT, CONFIGS, geometry_index

POLICIES = [(name, power) for name in (*CONFIGS, 'cell_candidate', 'kernel') for power in (0., .5, 1.)]
BUDGETS = (125, 250, 500)


def name_for(model, power):
    return f'{model}__area_power{power:g}'


def evaluate(year):
    grid = j.build_grid()
    features, cell, starts, counts = geometry_index(grid)
    groups = np.split(cell, starts[1:])
    areas = counts * .25
    with np.load(OUT / f'features-{year}.npz') as cached:
        data = {name: cached[name] for name in cached.files}
    y = data['y']
    scores = {name: joblib.load(OUT / (name + '.joblib')).predict_proba(data['X'].reshape(-1, 160))[:, 1].reshape(y.shape) for name in CONFIGS}
    scores.update({name: data[name] for name in ('cell_candidate', 'kernel')})
    rows = []
    for issue_index, issued_at in enumerate(data['issued_at']):
        row = {'issued_at': str(issued_at), 'targets': int(y[issue_index].sum()), 'policies': {}}
        for model, power in POLICIES:
            values = scores[model][issue_index] / areas ** power
            order = np.lexsort((np.arange(len(features)), -values))
            policies = {}
            for budget in BUDGETS:
                selected = []
                union = np.zeros(len(grid['xy']), dtype=bool)
                used = 0
                cap = round(budget / .25)
                for forest in order:
                    indices = groups[forest]
                    cost = int((~union[indices]).sum())
                    if used + cost <= cap:
                        selected.append(forest)
                        union[indices] = True
                        used += cost
                policies[str(budget)] = {'hits': int(y[issue_index, selected].sum()),
                    'selected_forests': len(selected), 'union_area_km2': used * .25}
            row['policies'][name_for(model, power)] = policies
        rows.append(row)
    total = int(y.sum())
    summary = {'year': year, 'issues': len(rows), 'positive_forest_rounds': total, 'policies': {}}
    for model, power in POLICIES:
        name = name_for(model, power)
        summary['policies'][name] = {}
        for budget in BUDGETS:
            hits = sum(row['policies'][name][str(budget)]['hits'] for row in rows)
            watched = [row['policies'][name][str(budget)] for row in rows]
            summary['policies'][name][str(budget)] = {'hits': hits, 'coverage_pct': 100 * hits / total,
                  'mean_selected_forests': float(np.mean([item['selected_forests'] for item in watched])),
                  'mean_union_area_km2': float(np.mean([item['union_area_km2'] for item in watched]))}
    return {'summary': summary, 'rows': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('validation', 'test'), required=True)
    args = parser.parse_args()
    folder = OUT / 'area-budget'
    folder.mkdir(exist_ok=True)
    protocol = {'version': 1, 'criterion': 'Highest pooled2025 target forest-round coverage at250km2 union-area cap. Tie: smaller mean area then policy name.',
       'policies': [{'model': name, 'area_power': power} for name, power in POLICIES],
       'selection_algorithm': 'Order forest scores divided by individual candidate buffer area raised to area_power. Greedily add each whole forest if incremental union area fits cap; skip otherwise. Geometry only, no labels in selection.',
       'budgets_km2': BUDGETS, 'train': 2024, 'choose': 2025, 'retrospective_test': 2026,
       'test_status': '2026 has been inspected by earlier analyses. This is retrospective comparison, not a new prospective holdout.',
       'target': 'Positive forest-round from any next12h VIIRS target-cell centre in provided forest+1000m buffer. Overlaps can share detections.',
       'deployment_commands_issued': 0}
    j.write(folder / 'protocol.json', protocol)
    if args.phase == 'validation':
        result = evaluate(2025)
        j.write(folder / 'validation-2025.json', result)
        items = result['summary']['policies']
        ranking = sorted(items, key=lambda name: (-items[name]['250']['hits'], items[name]['250']['mean_union_area_km2'], name))
        j.write(folder / 'selection.json', {'selected_policy': ranking[0], 'ranking_2025': ranking, 'validation_summary': result['summary'],
                     'selection_before_this_area_budget_test': True, 'criterion': protocol['criterion']})
        print('AREA POLICY SELECTED2025', ranking[0], items[ranking[0]]['250'], flush=True)
    else:
        chosen = j.read(folder / 'selection.json')['selected_policy']
        result = evaluate(2026)
        j.write(folder / 'test-2026.json', result)
        print('AREA POLICY RESULT2026', chosen, result['summary']['policies'][chosen],
              'PARENT', result['summary']['policies']['cell_candidate__area_power0'],
              'KERNEL', result['summary']['policies']['kernel__area_power0'], flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
