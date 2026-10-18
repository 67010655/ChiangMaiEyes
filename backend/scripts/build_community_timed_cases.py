"""Add a labelled retrospective community-fire cohort, selected without model scores.

Select forests with most nominal/high thermal observations inside supplied
boundaries, then retrieve imagery. This is an enriched known-fire cohort, not
the prevalence of all community-forest alerts; report it separately.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import numpy as np
from shapely import STRtree, points, make_valid
from shapely.geometry import shape
from shapely.ops import transform

import build_timed_fire_cases as b


def main():
    forests = b.read(b.ROOT / 'backend/app/data/community-forests-chiangmai.geojson')['features']
    polygons = [make_valid(transform(b.PROJECT.transform, shape(forest['geometry']))) for forest in forests]
    source, times, xy = b.source_points(2026)
    indices, forest_indices = STRtree(polygons).query(points(xy), predicate='within')
    counts = Counter(forest_indices.tolist())
    candidates = []
    for forest_index, count in counts.most_common():
        if count < 3:
            continue
        members = indices[forest_indices == forest_index]
        days = Counter(source[i]['detected_at'][:10] for i in members)
        date, day_count = days.most_common(1)[0]
        if date[5:7] not in ('03', '04'):
            continue
        active = [i for i in members if source[i]['detected_at'][:10] == date]
        coordinates = xy[active]
        centre = np.median(coordinates, axis=0)
        nearest = active[int(np.argmin(np.linalg.norm(coordinates-centre, axis=1)))]
        p = source[nearest]
        forest = forests[forest_index]['properties']
        candidate = {'id': date+'-community-'+forest['id'], 'date': date, 'year': 2026,
            'latitude': p['latitude'], 'longitude': p['longitude'], 'cohort': 'community_known_hotspot_enriched',
            'forest_id': forest['id'], 'forest_name': forest['name'], 'season_inside_forest_detections': count,
            'peak_day_inside_forest_detections': day_count}
        position = np.array(b.PROJECT.transform(candidate['longitude'], candidate['latitude']))
        if any(np.linalg.norm(position-np.array(b.PROJECT.transform(c['longitude'], c['latitude']))) < 15000 for c in candidates):
            continue
        candidates.append(candidate)
        if len(candidates) == 4:
            break
    b.write(b.OUT / 'community-case-candidates.json', {'selection': 'Top2026inside-boundarythermalobservationcounts; no opticalgrowthamount/modelscore used. Known-fire enriched cohort, not randomalertsample.', 'candidates': candidates})
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(b.case, candidates))
    b.write(b.OUT / 'community-case-manifest.json', result)
    print('COMMUNITY_CASES', [(r['id'], 'ready' if 'initial_scene' in r else 'excluded') for r in result], flush=True)


if __name__ == '__main__':
    main()
