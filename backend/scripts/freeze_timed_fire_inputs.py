"""Freeze the finite retrospective cohort before any final 2026 scoring."""
import hashlib
from datetime import datetime, timezone
import timed_fire_spread_benchmark as b


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert (b.OUT / 'community-case-manifest.json').exists(), 'Finish community input-quality retrieval first'
    manifest = b.read(b.OUT / 'array-manifest.json')
    assert not manifest['excluded']
    cases, files = [], {}
    for quality in manifest['ready']:
        folder = b.OUT / 'cases' / quality['id']
        meta = b.read(folder / 'case.json')
        cases.append({'id': meta['id'], 'split': meta['split'], 'cohort': meta['candidate'].get('cohort', 'original_case_studies'),
                      'horizon_hours': meta['horizon_hours'], 'bounds_utm47': meta['bounds_utm47']})
        for name in ['case.json', 'model-arrays.npz', 'single-run-weather.json'] + [meta[k]+'.npz' for k in ('baseline_scene', 'initial_scene', 'final_scene')]:
            path = folder / name
            files[str(path.relative_to(b.ROOT)).replace('\\', '/')] = sha(path)
    for year in (2025, 2026):
        path = b.ROOT / f'output/joint-fire-model-20261017/pm-{year}.json'
        files[str(path.relative_to(b.ROOT)).replace('\\', '/')] = sha(path)
    forest_path = b.ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
    files[str(forest_path.relative_to(b.ROOT)).replace('\\', '/')] = sha(forest_path)
    for path in (b.OUT/'growth-ml').glob('*.joblib'):
        files[str(path.relative_to(b.ROOT)).replace('\\', '/')] = sha(path)
    training = [c for c in cases if c['split'] == 'selection2025']
    assert len(training) == 4
    overlaps = []
    for i, a in enumerate(training):
        for c in training[i+1:]:
            x1, y1, x2, y2 = a['bounds_utm47']
            u1, v1, u2, v2 = c['bounds_utm47']
            area = max(0, min(x2,u2)-max(x1,u1))*max(0, min(y2,v2)-max(y1,v1))
            if area:
                overlaps.append({'a': a['id'], 'b': c['id'], 'overlap_km2': area/1e6})
    assert not overlaps, 'Use spatial-group CV if validation windows overlap'
    result = {'frozen_at_utc': datetime.now(timezone.utc).isoformat(), 'cases': cases, 'files': files,
              'validation_windows_overlap': overlaps, 'training_cases': len(training),
              'selection_files': {str(p.relative_to(b.OUT)).replace('\\', '/'): sha(p) for p in (b.OUT/'spread-selection.json', b.OUT/'growth-ml/selection.json')},
              'rule': 'All ready quality-accepted cases; no exclusion by model score. Original eight tests and known-hotspot-enriched community tests must be reported separately.'}
    destination = b.OUT / 'frozen-inputs.json'
    if destination.exists():
        old = b.read(destination)
        assert old['files'] == files and old['selection_files'] == result['selection_files'], 'Frozen experiment inputs changed'
    else:
        b.write(destination, result)
    print('FROZEN', len(cases), 'cases', len(files), 'source files; 4 disjoint validation windows')


if __name__ == '__main__':
    main()
