import gzip
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import land_context as land


def samples(monkeypatch, world, cgls):
    monkeypatch.setattr(land, 'sample', lambda name, lat, lon: world if name == 'spread-landcover' else cgls)


def test_ldd_rice_has_priority_over_both_forest_maps(monkeypatch):
    samples(monkeypatch, 10, 112)
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
])
def test_ldd_subtypes_need_an_explicit_unambiguous_name(code, name, kind):
    assert land.ldd_context(code, name)[0] == kind


@pytest.mark.parametrize('world,cgls,kind', [(10,114,'deciduous'),(10,112,'evergreen'),(10,125,'mixed_forest'),
    (10,126,'unknown_forest'),(10,40,'unknown_forest'),(40,112,'crop'),(20,114,'shrub'),(30,112,'grass'),(None,114,'deciduous'),(None,None,'unknown')])
def test_map_precedence_does_not_turn_more_recent_crops_or_shrubs_into_2019_forest(monkeypatch, world, cgls, kind):
    samples(monkeypatch, world, cgls)
    data = land.resolve(18.8,98.9)
    assert data['kind'] == kind
    if world == 10 and cgls == 114:
        assert data['label'] == 'ป่าผลัดใบ (เช่น เต็งรัง/เบญจพรรณ)'
        assert data['map_years'] == [2021,2019]
    if kind == 'mixed_forest':
        assert 'เบญจพรรณ' not in data['label']


def test_jurisdiction_codes_are_not_treated_as_forest_types(monkeypatch):
    samples(monkeypatch,40,114)
    assert land.resolve(18.8,98.9,'NRF','ป่าสงวน')['kind'] == 'crop'
    assert land.ldd_context('A101+F201','พื้นที่ผสม') is None


def test_native_raster_is_valid_and_sampling_never_wraps_outside_the_grid():
    meta, raw = land.raster('forest-landcover')
    assert meta['license'] == 'CC BY 4.0' and meta['reference_year'] == 2019
    assert len(raw) == meta['width']*meta['height']
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    assert land.sample('forest-landcover',0,0) is None
    assert land.sample('forest-landcover',meta['north']+.01,meta['west']) is None
    assert land.sample('forest-landcover',meta['north'],meta['west']+meta['width']*meta['step_degrees']+.0001) is None


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
    summaries = json.loads((land.DATA/'community-forest-landcover.json').read_text(encoding='utf-8'))['forests']
    assert len(_official_forests) == len(summaries) == 677
    assert sum(s['status']=='sampled' for s in summaries.values()) == 672
    assert sum(bool(f.forest_types) for f in _official_forests) == 663
    for f in _official_forests:
        s=summaries[f.forest_id]
        assert f.forest_types == s['forest_types']
        if s['status'] == 'sampled':
            assert abs(sum(c['percent'] for c in s['composition'])-100) < .05
        else:
            assert not s['forest_types'] and not s['composition']


def test_missing_optional_summary_does_not_remove_official_forests(monkeypatch):
    from app.providers import community_forest_provider as provider
    monkeypatch.setattr(provider,'_landcover_summaries',lambda:{})
    forests=provider._load_official()
    assert len(forests)==677 and all(f.forest_types==[] for f in forests)


def test_context_endpoint_is_public_and_rejects_invalid_coordinates_and_oversized_codes():
    app=FastAPI();app.include_router(land.router)
    with TestClient(app) as client:
        assert client.get('/api/land-context',params={'latitude':18.8,'longitude':98.9,'landuse_type':'A101'}).json()['kind']=='crop'
        for params in [{'latitude':91,'longitude':98.9},{'latitude':18.8,'longitude':181},{'latitude':'nan','longitude':98.9},{'latitude':18.8,'longitude':98.9,'landuse_type':'x'*101}]:
            assert client.get('/api/land-context',params=params).status_code==422
