"""Optional offline GIS checks; production API does not require these packages."""
import importlib.util
from pathlib import Path
import pytest

np = pytest.importorskip('numpy')
rasterio = pytest.importorskip('rasterio')
pytest.importorskip('shapely')
from rasterio.transform import from_origin

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('forest_landcover_builder',ROOT/'scripts/build_forest_landcover.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def feature(key, coordinates):
    return {'type':'Feature','properties':{'id':key},'geometry':{'type':'Polygon','coordinates':coordinates}}


def test_zonal_statistics_exclude_holes_and_dont_invent_small_or_invalid_forest_types():
    grid=np.full((4,4),114,dtype='uint8');grid[1:3,1:3]=40
    outer=[[0,0],[4,0],[4,4],[0,4],[0,0]];hole=[[1,1],[1,3],[3,3],[3,1],[1,1]]
    features=[feature('hole',[outer,hole]),feature('small',[[[.01,.01],[.02,.01],[.02,.02],[.01,.02],[.01,.01]]]),
              feature('invalid',[[[0,0],[2,2],[0,2],[2,0],[0,0]]])]
    result=builder.summarize_forests(grid,from_origin(0,4,1,1),features)
    assert result['hole']['valid_cells']==12
    assert result['hole']['composition'][0]['kind']=='deciduous'
    assert result['hole']['composition'][0]['percent']==100
    assert result['small']['status']=='no_valid_cell_centers'
    assert result['invalid']['status']=='invalid_boundary'


def test_percentages_use_valid_samples_and_keep_nodata_out_of_the_denominator():
    grid=np.array([[114,40],[255,40]],dtype='uint8')
    result=builder.summarize_forests(grid,from_origin(98,20,1,1),[feature('A',[[[98,18],[100,18],[100,20],[98,20],[98,18]]])])['A']
    assert result['valid_cells']==3 and result['boundary_cell_centers']==4
    assert abs(sum(c['percent'] for c in result['composition'])-100)<.02
