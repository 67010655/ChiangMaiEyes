from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.forest_proposals import router


def client(monkeypatch, calls):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_url='https://db.example', supabase_service_role_key='service')
    monkeypatch.setattr('app.community_store.CommunityStore.call', lambda self, method, path, **kw: calls.append((method, path, kw)) or 'proposal-1')
    return TestClient(app)


GOOD = {'name': 'ป่าชุมชนบ้านทดสอบ', 'village': 'บ้านทดสอบ', 'latitude': 18.31, 'longitude': 98.33, 'contact_phone': '081-234-5678'}


def test_anyone_can_propose_a_forest_and_the_sender_is_only_kept_as_a_hash(monkeypatch):
    calls = []
    res = client(monkeypatch, calls).post('/api/community/forest-proposals', json=GOOD, headers={'x-forwarded-for': '203.0.113.9, 10.0.0.1'})
    assert res.status_code == 201 and res.json() == {'id': 'proposal-1', 'status': 'pending'}
    method, path, kw = calls[0]
    assert (method, path) == ('POST', '/rest/v1/rpc/cme_propose_forest')
    assert kw['json']['p']['name'] == 'ป่าชุมชนบ้านทดสอบ'
    assert len(kw['json']['p_ip_hash']) == 64 and '203.0.113.9' not in str(kw)


def test_points_outside_chiang_mai_bad_phones_and_extra_fields_are_refused(monkeypatch):
    calls = []
    c = client(monkeypatch, calls)
    assert c.post('/api/community/forest-proposals', json={**GOOD, 'latitude': 13.7, 'longitude': 100.5}).status_code == 422
    assert c.post('/api/community/forest-proposals', json={**GOOD, 'contact_phone': 'call me'}).status_code == 422
    assert c.post('/api/community/forest-proposals', json={**GOOD, 'status': 'accepted'}).status_code == 422
    assert c.post('/api/community/forest-proposals', json={**GOOD, 'name': 'x'}).status_code == 422
    assert calls == []
