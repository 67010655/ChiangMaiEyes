"""PRODUCT_BRIEF #7: private contacts never enter the public response."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.community import router, session


def client_app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_contact_details_require_a_session_even_for_known_forests():
    with TestClient(client_app()) as client:
        response = client.get('/api/community/forest-contacts', params={'forest_ids': 'cmf-A'})
        assert response.status_code == 401
        assert 'representatives' not in response.text


def test_public_status_has_an_explicit_allowlist_and_no_personal_data(monkeypatch):
    calls = []
    def call(self, method, path, **kwargs):
        calls.append((path, kwargs))
        return [{'forest_id': 'cmf-A', 'has_representative': True,
                 'name': 'PRIVATE', 'email': 'private@example.test', 'representatives': ['PRIVATE']}]
    monkeypatch.setattr('app.community.CommunityStore.__post_init__', lambda self: None)
    monkeypatch.setattr('app.community.CommunityStore.call', call)
    with TestClient(client_app()) as client:
        response = client.get('/api/community/contact-status', params={'forest_ids': 'cmf-A'})
    assert response.json() == [{'forest_id': 'cmf-A', 'has_representative': True}]
    assert response.headers['cache-control'] == 'no-store'
    assert calls[0][0].endswith('/cme_forest_contact_status')
    assert 'token' not in calls[0][1]


def test_private_read_forwards_verified_user_token_and_disables_shared_caching():
    calls = []
    def call(method, path, **kwargs):
        calls.append((path, kwargs))
        return [{'forest_id': 'cmf-A', 'representatives': [{'name': 'Approved', 'email': 'approved@example.test', 'request_note': 'PRIVATE'}]}]
    app = client_app()
    app.dependency_overrides[session] = lambda: (SimpleNamespace(call=call), 'fixture-user-token', {'id': 'fixture-user'})
    with TestClient(app) as client:
        response = client.get('/api/community/forest-contacts', params=[('forest_ids', 'cmf-A'), ('forest_ids', 'cmf-A')])
    assert response.json() == [{'forest_id': 'cmf-A', 'representatives': [{'name': 'Approved', 'email': 'approved@example.test'}]}]
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['vary'] == 'Authorization'
    assert calls[0][1] == {'token': 'fixture-user-token', 'json': {'p_forest_ids': ['cmf-A']}}


def test_contacts_limit_queries_to_three_forests_and_reject_missing_ids(monkeypatch):
    monkeypatch.setattr('app.community.CommunityStore.__post_init__', lambda self: None)
    monkeypatch.setattr('app.community.CommunityStore.call', lambda *a, **kw: [])
    with TestClient(client_app()) as client:
        for ids in [[], [''], ['A', 'B', 'C', 'D'], ['x' * 101]]:
            assert client.get('/api/community/contact-status', params=[('forest_ids', value) for value in ids]).status_code == 422
