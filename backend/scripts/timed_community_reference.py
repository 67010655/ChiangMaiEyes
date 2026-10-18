"""Intersect observed optical scar candidates with supplied forest boundaries."""
import sys
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).resolve().parents[2] / 'output/spread-deps'))
import rasterio.features
from rasterio.transform import from_origin
from shapely.geometry import shape, box, mapping
from shapely.ops import transform
from shapely import STRtree, make_valid

import timed_fire_spread_benchmark as b
from pyproj import Transformer


def main():
    source = b.ROOT / 'backend/app/data/community-forests-chiangmai.geojson'
    forests = b.read(source)['features']
    project = Transformer.from_crs(4326, 32647, always_xy=True).transform
    polygons = [make_valid(transform(project, shape(forest['geometry']))) for forest in forests]
    tree = STRtree(polygons)
    rows = []
    for quality in b.read(b.OUT / 'array-manifest.json')['ready']:
        folder = b.OUT / 'cases' / quality['id']
        meta = b.read(folder / 'case.json')
        west, south, east, north = meta['bounds_utm47']
        indices = tree.query(box(west, south, east, north), predicate='intersects')
        arrays = np.load(folder / 'model-arrays.npz')
        masks = {}
        facts = []
        for index in indices:
            mask = rasterio.features.rasterize([(mapping(polygons[index]), 1)], out_shape=(500, 500),
                 transform=from_origin(west, north, 20, 20), all_touched=False, dtype='uint8').astype(bool)
            if not mask.any():
                continue
            properties = forests[index]['properties']
            masks[properties['id']] = mask
            facts.append({'id': properties['id'], 'name': properties['name'], 'pixels_in_case': int(mask.sum()),
                'clear_observed_pixels': int((mask & arrays['valid20']).sum()),
                'new_scar_pixels': int((mask & arrays['target20']).sum()),
                'initial_scar_pixels': int((mask & arrays['initial_scar20']).sum())})
        np.savez_compressed(folder / 'community-forest-masks.npz', **masks)
        rows.append({'case': meta['id'], 'split': meta['split'], 'forests_in_case': len(facts),
                    'forests_with_observed_new_scar_ge1ha': sum(fact['new_scar_pixels'] >= 25 for fact in facts), 'forests': facts})
    result = {'source': str(source.relative_to(b.ROOT)), 'source_polygons': len(forests),
              'reference': '20mpixelcentresinside suppliedRFDpolygons; newlyobserved spectralscar, not confirmedincident/damage.',
              'unit': 'One20mpixel=0.0004km2.1ha=25pixels. Cloud/non-detection is not verified unburned.', 'cases': rows}
    b.write(b.OUT / 'community-reference.json', result)
    print([(row['case'], row['forests_in_case'], row['forests_with_observed_new_scar_ge1ha']) for row in rows], flush=True)


if __name__ == '__main__':
    main()
