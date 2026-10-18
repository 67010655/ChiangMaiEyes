import gzip
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import land_context as land


def samples(monkeypatch, world):
    monkeypatch.setattr(land, 'sample', lambda name, lat, lon: world)


def test_ldd_rice_has_priority_over_the_tree_map(monkeypatch):
    samples(monkeypatch, 10)
    data = land.resolve(18.8, 98.9, 'A101', 'นาข้าว')
    assert data['headline'] == 'พื้นที่เกษตร (นาข้าว) · น่าจะเป็นการเผาในแปลง ไม่ใช่ไฟป่า'
    assert len(data['sources']) == 1 and 'GISTDA' in data['sources'][0]['name']
    assert data['qualifier'] == 'ประเมินจากแผนที่ ไม่ใช่การสำรวจในพื้นที่'


@pytest.mark.parametrize('code,name,kind', [
    ('F201', '', 'deciduous'), ('F201', 'ป่าเบญจพรรณ', 'mixed_deciduous'),
    ('F202', 'ป่าเต็งรัง', 'dipterocarp'), ('F201', 'ป่าผลัดใบสมบูรณ์', 'deciduous'),
    ('F201', 'ป่าไม่ผลัดใบสมบูรณ์', 'evergreen'), ('F202', '', 'unknown_forest'),
    ('F201', 'ป่าเต็งรัง/ป่าเบญจพรรณ', 'deciduous'),
    ('F201', 'ป่าดิบ/ป่าเบญจพรรณ', 'unknown_forest'),
    ('A902', 'เพาะเลี้ยงปลา', 'water'), ('U201', 'หมู่บ้าน', 'built'),
    ('', 'ป่าเต็งรัง', 'dipterocarp'), ('', 'ป่าเบญจพรรณ', 'mixed_deciduous'),
    ('OTHER', 'ป่าเต็งรัง', 'dipterocarp'),
])
def test_ldd_subtypes_need_an_explicit_unambiguous_name(code, name, kind):
    assert land.ldd_context(code, name)[0] == kind


@pytest.mark.parametrize('world,kind', [(10,'unknown_forest'),(20,'shrub'),(30,'grass'),(40,'crop'),
    (50,'built'),(60,'bare'),(80,'water'),(90,'wetland'),(95,'unknown_forest'),(None,'unknown')])
def test_esa_reports_land_cover_without_inventing_a_forest_subtype(monkeypatch, world, kind):
    samples(monkeypatch, world)
    data = land.resolve(18.8,98.9)
    assert data['kind'] == kind
    if kind == 'unknown_forest':
        assert data['reference'] == land.reference()['profiles']['unknown_forest']
        assert data['province_context']['reference_year'] == 2000
        assert data['map_years'] == [2021]
    else:
        assert data['province_context'] is None


def test_jurisdiction_codes_are_not_treated_as_forest_types(monkeypatch):
    samples(monkeypatch,40)
    assert land.resolve(18.8,98.9,'NRF','ป่าสงวน')['kind'] == 'crop'
    assert land.ldd_context('A101+F201','พื้นที่ผสม') is None


def test_native_raster_is_valid_and_sampling_never_wraps_outside_the_grid():
    meta, raw = land.raster('spread-landcover')
    assert len(raw) == meta['width']*meta['height']
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    assert land.sample('spread-landcover',0,0) is None
    assert land.sample('spread-landcover',meta['north']+.01,meta['west']) is None
    assert land.sample('spread-landcover',meta['north'],meta['west']+meta['width']*meta['step_degrees']+.0001) is None
    with pytest.raises(ValueError,match='Only ESA'):
        land.raster('forest-landcover')


def test_no_reference_profile_invents_a_fuel_level_or_uses_intensity_carbon_or_evi_as_load():
    doc = land.reference()
    for p in doc['profiles'].values():
        assert p['fuel_level']['status'] == 'unknown'
        for field in ('fire_type','season','fuel','fuel_level'):
            assert p[field]['refs']
            for ref in p[field]['refs']:
                assert doc['sources'][ref['id']]['url'].startswith('https://')
        assert not any('ตัน/ไร่' in p[field]['text'] for field in p)


def test_community_forests_keep_all_677_records_and_distinguish_missing_or_unresolved_types():
    from app.providers.community_forest_provider import _official_forests
    assert len(_official_forests) == 677
    assert all(f.forest_types == [] and f.landcover_summary is None for f in _official_forests)


def test_leftover_retired_summary_cannot_restore_a_forest_subtype(monkeypatch,tmp_path):
    from app.providers import community_forest_provider as provider
    source=tmp_path/'community-forests-chiangmai.geojson'
    source.write_bytes(provider._OFFICIAL_GEOJSON.read_bytes())
    (tmp_path/'community-forest-landcover.json').write_text(json.dumps({'forests':{
        f.forest_id:{'forest_types':['ป่าไม่ผลัดใบ']} for f in provider._official_forests}}),encoding='utf-8')
    monkeypatch.setattr(provider,'_OFFICIAL_GEOJSON',source)
    forests=provider._load_official()
    assert len(forests)==677 and all(f.forest_types==[] for f in forests)
    assert all(f.landcover_summary is None for f in forests)


@pytest.mark.parametrize('lat,lon',[(17.80,98.40),(18.20,98.70),(19.30,98.95)])
def test_omkoi_hot_and_chiang_dao_do_not_inherit_the_retired_evergreen_map(lat,lon):
    data=land.resolve(lat,lon)
    assert data['kind']=='unknown_forest' and 'ป่าไม่ผลัดใบ' not in data['headline']
    assert data['reference']==land.reference()['profiles']['unknown_forest']
    assert all('CGLS' not in s['name'] for s in data['sources'])
    assert land.resolve(lat,lon,'F202','ป่าเต็งรัง')['kind']=='dipterocarp'
    assert land.resolve(lat,lon,'A101','นาข้าว')['kind']=='crop'


def test_context_endpoint_is_public_and_rejects_invalid_coordinates_and_oversized_codes():
    app=FastAPI();app.include_router(land.router)
    with TestClient(app) as client:
        assert client.get('/api/land-context',params={'latitude':18.8,'longitude':98.9,'landuse_type':'A101'}).json()['kind']=='crop'
        for params in [{'latitude':91,'longitude':98.9},{'latitude':18.8,'longitude':181},{'latitude':'nan','longitude':98.9},{'latitude':18.8,'longitude':98.9,'landuse_type':'x'*101}]:
            assert client.get('/api/land-context',params=params).status_code==422
