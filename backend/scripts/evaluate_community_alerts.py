"""Translate frozen cell ranks into a descriptive top-N forest watch list.

No model fitting. A positive forest-round means at least one future VIIRS cell
centre in that forest's1000m buffer; overlapping forests can share the same
detection. These are not verified independent incidents or calibrated alerts.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely import STRtree, make_valid, points
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/watch-budget-20261017'
COUNTS = (10, 20, 50, 100, 200)


def main():
    source = ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
    features = json.loads(source.read_text(encoding='utf8'))['features']
    grid = dict(np.load(ROOT / 'output/priority-forecast-20261017/grid.npz'))
    projection = Transformer.from_crs(4326, 32647, always_xy=True)
    geometries = [make_valid(transform(projection.transform, shape(feature['geometry']))).buffer(1000) for feature in features]
    tree = STRtree(geometries)
    cells, forests = tree.query(points(grid['xy']), predicate='within')
    order = np.lexsort((cells, forests))
    cells, forests = cells[order], forests[order]
    ids, starts = np.unique(forests, return_index=True)
    assert len(ids) == len(features), 'A forest lacks candidate cells; handle explicitly before comparing all forests.'
    lists = np.split(cells, starts[1:])
    rows = []
    affected = np.zeros(len(features), dtype='int64')
    captured = {name: {str(count): np.zeros(len(features), dtype='int64') for count in COUNTS} for name in ('candidate', 'kernel')}
    for path in sorted((OUT / 'rank-cache').glob('*.npz')):
        with np.load(path) as cache:
            target = np.logical_or.reduceat(cache['target'][cells].astype(bool), starts)
            affected += target
            entry = {'issue': path.stem, 'positive_forest_rounds': int(target.sum()), 'models': {}}
            for name in ('candidate', 'kernel'):
                ranks = np.empty(len(grid['xy']), dtype='uint32')
                ranks[cache[name]] = np.arange(len(ranks))
                forest_best_rank = np.minimum.reduceat(ranks[cells], starts)
                forest_order = np.lexsort((np.arange(len(features)), forest_best_rank))
                values = {}
                for count in COUNTS:
                    selected = forest_order[:count]
                    captured[name][str(count)][selected] += target[selected]
                    values[str(count)] = {'captured_positive_forest_rounds': int(target[selected].sum()),
                                          'union_watch_area_km2': len(np.unique(np.concatenate([lists[i] for i in selected]))) * .25}
                entry['models'][name] = values
            rows.append(entry)
    total = int(affected.sum())
    summary = {'forest_count': len(features), 'issues': len(rows), 'unique_forests_with_future_detections': int((affected > 0).sum()),
               'positive_forest_rounds': total, 'curves': []}
    for count in COUNTS:
        values = {}
        for name in ('candidate', 'kernel'):
            hits = sum(row['models'][name][str(count)]['captured_positive_forest_rounds'] for row in rows)
            values[name] = {'captured_positive_forest_rounds': hits, 'coverage_pct': 100 * hits / total,
                            'mean_union_watch_area_km2': float(np.mean([row['models'][name][str(count)]['union_watch_area_km2'] for row in rows])),
                            'positive_forest_rounds_per_selected_forest_round_pct': 100 * hits / (count * len(rows)),
                            'warning': 'The last ratio is satellite detection frequency, not verified alarm precision.'}
        summary['curves'].append({'selected_forests_per_issue': count, 'models': values})
    protocol = {'mode': 'offline_descriptive_forest_ranking', 'model_sha256': json.loads((OUT / 'summary.json').read_text())['model_sha256'],
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'scope': 'Each provided forest polygon buffered1000m in EPSG32647.500m candidate-cell centre membership.',
                'score': 'Best (lowest) frozen province cell rank inside each forest buffer; ties broken by source feature index.',
                'target': 'Any next12h nominal/high VIIRS detection-cell centre inside forest buffer. No new training labels enter ranking.',
                'selection': 'Top-N values are descriptive scenarios, not tuned on2026 or approved operational thresholds.',
                'overlap_policy': 'A detection can label multiple overlapping forest buffers. Positive forest-rounds are not distinct incidents.',
                'comparison': 'Equal number of forests selected; footprint areas differ and are reported. Not an equal-area comparison.',
                'absence': 'No satellite detection does not establish absence of fire. No true false-alarm rate reported.',
                'deployment_commands_issued': 0}
    payload = {'protocol': protocol, 'summary': summary, 'rows': rows,
               'forest_diagnostics': [{'id': feature['properties']['id'], 'name': feature['properties']['name'],
                    'positive_forest_rounds': int(affected[i]),
                    'captured_at_top50': {name: int(captured[name]['50'][i]) for name in captured}}
                    for i, feature in enumerate(features)]}
    for row in summary['curves']:
        assert all(0 <= item['captured_positive_forest_rounds'] <= total for item in row['models'].values())
    for name in ('candidate', 'kernel'):
        values = [row['models'][name]['captured_positive_forest_rounds'] for row in summary['curves']]
        assert all(a <= b for a, b in zip(values, values[1:]))
    (OUT / 'community-alerts.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
