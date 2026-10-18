import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app import ventilation_archive as archive
from app.providers.gfs_ventilation import decode_subset

RAW = (Path(__file__).parent / 'fixtures/gfs_pbl_20261012_06_f000.grib2').read_bytes()


def frame():
    return {**decode_subset(RAW, datetime(2026, 10, 12, 6, tzinfo=timezone.utc), 0, '98.0086,17.2732,99.5730,20.1474'),
            'status': 'available', 'sha256': hashlib.sha256(RAW).hexdigest(),
            '_archive_grib_base64': base64.b64encode(RAW).decode('ascii'),
            'measurement_kind': 'model', 'publisher': 'NOAA NCEP', 'product': 'GFS 0.25° PBL'}


def test_saves_verified_raw_evidence_without_internal_fields(monkeypatch):
    calls = []
    class Store:
        def __init__(self, settings): pass
        def call(self, method, path, json): calls.append(json)
    monkeypatch.setattr(archive, 'CommunityStore', Store)
    settings = Settings(supabase_url='https://example.test', supabase_service_role_key='test-service')
    archive.collect_frame(settings, frame())
    assert len(calls) == 1
    assert base64.b64decode(calls[0]['p_grib_base64']) == RAW
    assert '_archive_grib_base64' not in calls[0]['p_frame']
    bad = frame(); bad['sha256'] = '0' * 64
    archive.collect_frame(settings, bad)
    archive.collect_frame(settings, {'status': 'unavailable'})
    assert len(calls) == 1  # no false archive record for missing/corrupt evidence


def test_public_endpoint_never_exposes_internal_binary_and_keeps_live_data_when_archive_fails(monkeypatch):
    from app.providers import gfs_ventilation
    calls = []
    monkeypatch.setattr(gfs_ventilation, 'ventilation', lambda lead: frame())
    monkeypatch.setattr(archive, 'collect_frame', lambda settings, result: calls.append(result))
    response = TestClient(app).get('/api/ventilation')
    assert response.status_code == 200 and len(response.json()['cells']) == 66
    assert '_archive_grib_base64' not in response.json()
    assert calls[0]['_archive_grib_base64']


@pytest.mark.parametrize('stamp', ['2026-10-10T12:00:00', 'invalid', '2099-01-01T00:00:00Z'])
def test_evidence_cutoff_rejects_unzoned_invalid_or_future(stamp):
    with pytest.raises(HTTPException) as error: archive.cutoff(stamp)
    assert error.value.status_code == 422


def test_archive_routes_limit_requests_and_keep_model_frames_separate(monkeypatch):
    calls = []
    class Store:
        def __init__(self, settings): pass
        def call(self, method, path, json):
            calls.append((path, json))
            return {'total': 2, 'frames': [], 'first_stored_at': None} if path.endswith('cme_gfs_read') else None
    monkeypatch.setattr(archive, 'CommunityStore', Store)
    client = TestClient(app)
    result = client.get('/api/ventilation/archive?limit=1&as_of=2026-10-10T12:00:00Z')
    assert result.status_code == 200 and result.json()['next_offset'] == 1
    assert result.json()['measurement_kind'] == 'model'
    assert calls[0][1]['p_as_of'] == '2026-10-10T12:00:00+00:00'
    assert client.get('/api/ventilation/archive/' + 'a' * 64).status_code == 404
    assert client.get('/api/ventilation/archive/invalid').status_code == 422
    for query in ['days=0', 'limit=101', 'as_of=2099-01-01T00:00:00Z', 'offset=-1']:
        assert client.get('/api/ventilation/archive?' + query).status_code == 422
