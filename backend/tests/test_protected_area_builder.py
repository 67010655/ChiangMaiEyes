"""Offline geometry checks; native GIS packages are not production dependencies."""
import importlib.util
import json
from pathlib import Path

import pytest
pytest.importorskip('shapely')
pytest.importorskip('pyproj')
from shapely.geometry import Point, box, mapping, shape
from shapely import transform
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('protected_builder',ROOT/'scripts/build_protected_areas.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def test_reference_geometry_identifies_hang_dong_and_distinguishes_near_and_far():
    doc=json.loads((ROOT/'frontend/public/protected-areas-chiangmai.geojson').read_text(encoding='utf-8'))
    assert len(doc['features'])==21
    park=shape(next(f for f in doc['features'] if f['id']=='1024')['geometry'])
    p=Point(98.87560547145418,18.7985022)
    assert park.covers(p)
    tambons=json.loads((ROOT/'frontend/public/chiangmai-tambons.geojson').read_text(encoding='utf-8'))['features']
    matched=[f['properties'] for f in tambons if shape(f['geometry']).covers(p)]
    assert len(matched)==1 and matched[0]['tambon_th']=='บ้านปง' and matched[0]['amphoe_th']=='หางดง'
    project=Transformer.from_crs(4326,32647,always_xy=True).transform
    metric=transform(park,project,interleaved=False)
    assert 2300<metric.distance(transform(Point(98.96,18.75),project,interleaved=False))<2500
    assert metric.distance(transform(Point(99.03,18.78),project,interleaved=False))>8000
    for f in doc['features']:
        assert shape(f['geometry']).is_valid
        assert -180<=f['bbox'][0]<=f['bbox'][2]<=180 and -90<=f['bbox'][1]<=f['bbox'][3]<=90
    assert max(a['max_geometry_difference_m'] for a in doc['metadata']['geometry_audit'])<=20.3


def test_build_transforms_coordinates_and_keeps_the_original_park_edge_across_province_lines():
    g=box(98.4,18.4,98.6,18.6)
    projection=Transformer.from_crs(4326,3857,always_xy=True).transform
    src={'type':'FeatureCollection','crs':{'properties':{'name':'EPSG:3857'}},'features':[
        {'id':'unknown','properties':{'pro_id':'9999','name_th':'ชนิดยังไม่ยืนยัน'},'geometry':mapping(transform(g,projection,interleaved=False))},
        {'id':'far','properties':{'pro_id':'9998','name_th':'นอกจังหวัด'},'geometry':mapping(transform(box(100,20,101,21),projection,interleaved=False))},
    ]}
    result,audit,types=builder.build(src,mapping(box(98.5,18.5,98.7,18.7)))
    assert len(result)==1 and result[0]['id']=='9999'
    assert result[0]['properties']['area_type']=='protected_area' and types=={}
    assert shape(result[0]['geometry']).bounds[0]==pytest.approx(98.4,abs=.000001)
    assert shape(result[0]['geometry']).covers(Point(98.45,18.45))  # outside province, still inside park
    assert audit[0]['max_geometry_difference_m']<=20.3


@pytest.mark.parametrize('crs',[None,'EPSG:4326'])
def test_unverified_or_unexpected_source_crs_is_rejected(crs):
    with pytest.raises(ValueError,match='EPSG:3857'):
        builder.build({'crs':{'properties':{'name':crs}},'features':[]},mapping(box(98,18,99,19)))


def test_a_changed_name_anchor_disables_the_prefix_instead_of_guessing():
    assert builder.crosschecked_types([{'properties':{'pro_id':'1024','name_th':'ดอยสุเทพ-ปุย'}}])=={}
