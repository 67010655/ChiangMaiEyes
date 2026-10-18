"""Build100m model grids and20m time-matched optical reference masks.

Optical labels remain spectral-change candidates. A positive pixel is not an
independently surveyed burn perimeter, and no subdaily burn time is invented.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import label, distance_transform_edt, binary_dilation
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.forecast_terrain import dataset as terrain_dataset
from app.grid_spread import landcover_dataset

OUT = ROOT / 'output/fire-perimeter-loop-20261017'
INVERSE = Transformer.from_crs(32647, 4326, always_xy=True)
PROJECT = Transformer.from_crs(4326, 32647, always_xy=True)


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def fraction20(mask):
    return mask.reshape(100, 5, 100, 5).mean(axis=(1, 3)).astype('float32')


def clean(mask):
    groups, n = label(mask, structure=np.ones((3, 3)))
    counts = np.bincount(groups.ravel())
    keep = counts >= 5
    keep[0] = False
    return keep[groups]


def changed(before, after, threshold):
    valid = before['valid'] & after['valid']
    return clean(valid & (before['nbr']-after['nbr'] >= threshold) &
                 (before['ndvi']-after['ndvi'] >= .10) & (before['ndvi'] >= .30))


def prepare(metadata):
    folder = OUT / 'cases' / metadata['id']
    before = dict(np.load(folder / (metadata['baseline_scene'] + '.npz')))
    initial = dict(np.load(folder / (metadata['initial_scene'] + '.npz')))
    after = dict(np.load(folder / (metadata['final_scene'] + '.npz')))
    valid = before['valid'] & initial['valid'] & after['valid']
    initial_scar20 = changed(before, initial, .20)
    primary20 = changed(initial, after, .20) & ~initial_scar20 & valid
    low20 = changed(initial, after, .10) & ~initial_scar20 & valid
    high20 = changed(initial, after, .27) & ~initial_scar20 & valid
    west, south, east, north = metadata['bounds_utm47']
    yy, xx = np.meshgrid(north-(np.arange(100)+.5)*100, west+(np.arange(100)+.5)*100, indexing='ij')
    lon, lat = INVERSE.transform(xx, yy)
    dem_meta, dem = terrain_dataset()
    lc_meta, cover = landcover_dataset()
    z = np.asarray(dem).reshape(dem_meta['height'], dem_meta['width'])
    col = (lon - dem_meta['west'])/dem_meta['step_degrees'] - .5
    row = (dem_meta['north'] - lat)/dem_meta['step_degrees'] - .5
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    dc, dr = col-c0, row-r0
    assert ((c0 >= 0) & (c0+1 < z.shape[1]) & (r0 >= 0) & (r0+1 < z.shape[0])).all()
    corners = np.stack([z[r0, c0], z[r0, c0+1], z[r0+1, c0], z[r0+1, c0+1]])
    terrain_valid = (corners != dem_meta['nodata']).all(axis=0)
    elevation = corners[0]*(1-dr)*(1-dc) + corners[1]*(1-dr)*dc + corners[2]*dr*(1-dc) + corners[3]*dr*dc
    dzdy, dzdx = np.gradient(elevation.astype('float64'), 100, 100)
    # Array y increases southward. Aspect is downslope, clockwise from north.
    slope = np.hypot(dzdx, dzdy)
    aspect = np.degrees(np.arctan2(-dzdx, dzdy)) % 360
    # Categorical data use nearest source pixel, never interpolated class IDs.
    cover = np.frombuffer(cover, dtype='uint8').reshape(lc_meta['height'], lc_meta['width'])
    cc = np.floor((lon-lc_meta['west'])/lc_meta['step_degrees']).astype(int)
    rr = np.floor((lc_meta['north']-lat)/lc_meta['step_degrees']).astype(int)
    landcover = cover[rr, cc]
    burnable = terrain_valid & np.isin(landcover, [10, 20, 30, 40, 90, 95, 100])
    seed_points = np.column_stack(PROJECT.transform([p['longitude'] for p in metadata['initial_hotspots']], [p['latitude'] for p in metadata['initial_hotspots']]))
    seed_row = np.floor((north-seed_points[:, 1])/100).astype(int)
    seed_col = np.floor((seed_points[:, 0]-west)/100).astype(int)
    seeds = np.zeros((100, 100), dtype=bool)
    for r, c in zip(seed_row, seed_col):
        if 0 <= r < 100 and 0 <= c < 100 and burnable[r, c]:
            seeds[r, c] = True
    if not seeds.any():
        raise ValueError('No past hotspot on burnable model grid; do not fabricate ignition.')
    initial_cells = fraction20(initial_scar20) >= .12
    components, _ = label(initial_cells, structure=np.ones((3, 3)))
    near_seed = distance_transform_edt(~seeds) <= 6
    active_components = np.unique(components[near_seed & initial_cells])
    active_components = active_components[active_components > 0]
    image_seeds = np.isin(components, active_components) & burnable
    # An active thermal detection may precede a visible scar; retain point seeds.
    image_seeds |= seeds
    # Initial-only activity proxy near past thermal detections, not a validated
    # Sentinel2fire detector. Keep this hypothesis separate in the benchmark.
    active20 = (initial['swir22'] > .5) & (initial['swir22'] > 1.5*initial['nir08'])
    active_seeds = (fraction20(active20) > 0) & near_seed & burnable
    # Secondary propagation-only reference: exclude detached new ignitions.
    # This reference definition never uses a model prediction/overlap score.
    post_scar20 = changed(before, after, .20) | initial_scar20 | primary20
    joined, _ = label(binary_dilation(post_scar20, iterations=5), structure=np.ones((3, 3)))
    active20 = np.repeat(np.repeat(image_seeds, 5, axis=0), 5, axis=1)
    active_ids = np.unique(joined[active20 & (joined > 0)])
    connected20 = primary20 & np.isin(joined, active_ids)
    support20 = valid & ~initial_scar20
    arrays = {'slope': slope.astype('float32'), 'aspect': aspect.astype('float32'),
        'elevation_m': elevation.astype('float32'), 'landcover': landcover, 'burnable': burnable,
        'seeds_point': seeds, 'seeds_image': image_seeds, 'seeds_active': active_seeds,
        'initial_scar_fraction': fraction20(initial_scar20), 'growth_support_fraction': fraction20(support20),
        'target_fraction': fraction20(primary20), 'target_low_fraction': fraction20(low20), 'target_high_fraction': fraction20(high20),
        'connected_target_fraction': fraction20(connected20), 'connected_target20': connected20,
        'initial_scar20': initial_scar20, 'target20': primary20, 'valid20': valid, 'initial_valid20': initial['valid'],
        'initial_nbr': initial['nbr'], 'final_nbr': after['nbr'],
        'initial_falsecolor': np.stack([initial['swir22'], initial['nir08'], initial['red']]),
        'final_falsecolor': np.stack([after['swir22'], after['nir08'], after['red']])}
    np.savez_compressed(folder / 'model-arrays.npz', **arrays)
    quality = {'id': metadata['id'], 'split': metadata['split'], 'horizon_hours': metadata['horizon_hours'],
        'valid_fraction_all3images': float(valid.mean()), 'initial_scar_km2': float(initial_scar20.sum() * .0004),
        'reference_growth_km2': float(primary20.sum() * .0004),
        'connected_reference_growth_km2': float(connected20.sum() * .0004),
        'reference_low_threshold_km2': float(low20.sum() * .0004), 'reference_high_threshold_km2': float(high20.sum() * .0004),
        'point_seed_cells': int(seeds.sum()), 'image_seed_cells': int(image_seeds.sum()), 'high_swir_activity_seed_cells': int(active_seeds.sum()),
        'forest_shrub_fraction': float(np.isin(landcover, [10, 20]).mean()),
        'reference_growth_outside_burnable_model_km2': float((fraction20(primary20) * ~burnable).sum() * .01),
        'model_arrays_sha256': hashlib.sha256((folder / 'model-arrays.npz').read_bytes()).hexdigest()}
    write(folder / 'quality.json', quality)
    return quality


def main():
    protocol = {'version': 1, 'mode': 'offline_time_matched_optical_growth_hindcast',
      'initialization': 'Initial optical image available at acquisition time only for retrospective model initialization; publication latency excluded and retained in scene receipt.',
      'reference': 'Newly detected Sentinel2C1spectral change between exact acquisition times, not ground-surveyed perimeter or burn arrival time.',
      'reference_primary': 'dNBR>=0.20,NDVI_drop>=0.10,initial_NDVI>=0.30; >=5connected20m pixels. Exclude earlier baseline-to-initial scar with same rule.',
      'reference_sensitivity': 'dNBR0.10and0.27, other conditions fixed. Thresholds fixed before propagation-model scoring, not selected by model overlap.',
      'secondary_connected_growth': 'Primary new-scar target intersected with post-scar connected components after100mChebyshev dilation that touch initial image+past-hotspot seed cells. Excludes detached ignitions/spotting; not model-prediction based.',
      'quality': 'SCL4/5; finite positive NIR and nonnegative red/SWIR; intersection of clear land in all3images. Unknown pixels not unburned.',
      'resolution': '20moptical reference;100mmodel cells;approx110mDEM interpolated, categorical2021WorldCovernearest.100mgrid is not100mindependent environmental information.',
      'seeds': 'Past nominal/high VIIRS acquisitions in prior24hwith3hdelay. Point seeds or optical initial scar components within600mofpast seeds; no later hotspots enter.',
      'weather': 'One ECMWFIFS initialization<=initial_image-6h; complete valid times for observed image interval. PreMay2026archive described by provider as reforecasts.',
      'selection': '2025case study overlap only selects model/config;2026images used for retrospective final comparison.2026hotspotcases previously inspected.',
      'production_changed': False, 'deployment_commands_issued': 0}
    write(OUT / 'timed-reference-protocol.json', protocol)
    quality, excluded = [], []
    for path in sorted((OUT / 'cases').glob('*/case.json')):
        metadata = read(path)
        if metadata.get('collection') != 'sentinel-2-c1-l2a':
            continue
        try:
            row = prepare(metadata)
            quality.append(row)
            print('ARRAY_READY', row, flush=True)
        except Exception as error:
            excluded.append({'id': metadata['id'], 'reason': str(error)})
    write(OUT / 'array-manifest.json', {'ready': quality, 'excluded': excluded})


if __name__ == '__main__':
    main()
