"""Add validation cases chosen by past fire detections at actual image times.

Selection uses initial-image availability/metadata and past hotspots, not future
optical changes or propagation scores. Spatially separate from existing centres.
"""
import json
from pathlib import Path
from datetime import datetime
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import shape as geometry_shape
from shapely.ops import transform as geometry_transform
from shapely import contains_xy

import build_timed_fire_cases as b


def main():
    points, times, xy = b.source_points(2025)
    catalogue_files = sorted((b.OUT / 'catalogs').glob('c1-2025*.json'))
    seen = set()
    proposals = []
    for path in catalogue_files:
        for scene in b.read(path)['features']:
            if scene['id'] in seen or scene['properties'].get('eo:cloud_cover', 100) > 90:
                continue
            seen.add(scene['id'])
            asset = scene['assets'].get('nir08', {})
            transform, shape = asset.get('proj:transform'), asset.get('proj:shape')
            if not transform or not shape:
                continue
            west, north = transform[2], transform[5]
            east, south = west+shape[1]*transform[0], north+shape[0]*transform[4]
            when = b.stamp(scene['properties']['datetime'])
            eligible = (times <= when.timestamp()-3*3600) & (times > when.timestamp()-27*3600)
            eligible &= (xy[:, 0] > west+6000) & (xy[:, 0] < east-6000) & (xy[:, 1] > south+6000) & (xy[:, 1] < north-6000)
            footprint = geometry_transform(b.PROJECT.transform, geometry_shape(scene['geometry'])).buffer(-7500)
            eligible &= contains_xy(footprint, xy[:, 0], xy[:, 1])
            indices = np.flatnonzero(eligible)
            if len(indices) < 3:
                continue
            counts = cKDTree(xy[indices]).query_ball_point(xy[indices], 1500, return_length=True)
            best = int(np.argmax(counts))
            point = points[indices[best]]
            position = b.PROJECT.transform(point['longitude'], point['latitude'])
            spatial_id = f'{int(position[0]//100)}-{int(position[1]//100)}'
            proposals.append({'id': str(when.date())+'-'+scene['id'].split('_')[1]+'-'+spatial_id, 'date': str(when.date()), 'year': 2025,
                'latitude': point['latitude'], 'longitude': point['longitude'], 'initial_neighbour_count': int(counts[best]),
                'forced_initial_scene': scene['id'], 'discovery_catalog_source': str(path.relative_to(b.OUT)).replace('\\', '/')})
    existing = [b.read(path)['candidate'] for path in (b.OUT / 'cases').glob('*/case.json') if b.read(path).get('split') == 'selection2025']
    needed = max(0, 4-len(existing))
    if not needed:
        ready = [b.read(path) for path in (b.OUT / 'cases').glob('*/case.json')
                 if b.read(path).get('split') == 'selection2025' and b.read(path)['candidate'].get('forced_initial_scene')]
        b.write(b.OUT / 'extra-validation-manifest.json', ready)
        print('VALIDATION_READY', len(existing), flush=True)
        return
    chosen = []
    results = []
    attempted = []
    for candidate in sorted(proposals, key=lambda item: (-item['initial_neighbour_count'], item['id'])):
        position = np.array(b.PROJECT.transform(candidate['longitude'], candidate['latitude']))
        if all(np.linalg.norm(position - np.array(b.PROJECT.transform(item['longitude'], item['latitude']))) >= 12000 for item in existing + chosen):
            attempted.append(candidate)
            result = b.case(candidate)
            results.append(result)
            if 'initial_scene' in result:
                chosen.append(candidate)
        if len(chosen) == needed:
            break
        if len(attempted) >= 16:
            break
    b.write(b.OUT / 'extra-validation-candidates.json', {'selection': 'Past24hVIIRSwith3hdelayatactualinitialimage;>=12kmfromexistingacceptedvalidationcentres; rejectonlyinitial/finalreferencevisibility failures, never opticalchange amount or overlap score. Up to16input-qualityattempts; require2additionalacceptedcases before model selection.', 'candidates': chosen, 'attempted': attempted})
    b.write(b.OUT / 'extra-validation-manifest.json', results)
    print('EXTRA_VALIDATION', [(row['id'], 'ready' if 'initial_scene' in row else 'excluded') for row in results], flush=True)


if __name__ == '__main__':
    main()
