from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.community import router, session, IncidentCreate
from app.community_store import CommunityStore
from app.community_mail import point_in_boundary, next_delivery
from app.config import Settings


def test_worker_manual_check_includes_environment_and_records_completion(monkeypatch):
    from app import community_mail as mail
    calls=[]
    settings=Settings(line_channel_secret='s',line_channel_access_token='t')
    store=SimpleNamespace(settings=settings,call=lambda method,path,**kw: calls.append((method,path,kw)) or True)
    monkeypatch.setattr('app.services.get_dashboard',lambda settings:'fixture-dashboard')
    monkeypatch.setattr(mail,'queue_incident_events',lambda store,now:2)
    def environment(store,dashboard,now):
        assert dashboard=='fixture-dashboard'
        return 3
    monkeypatch.setattr(mail,'queue_environment',environment)
    monkeypatch.setattr('app.community_line.process_outbox',lambda store:{'line_accepted':1,'line_failed':0,'line_suppressed':0})
    assert mail.run_jobs(store)['queued']==5
    assert calls[-1][2]['json']['run_status']=='completed'
    assert calls[-1][2]['json']['summary']['line_accepted']==1


def test_worker_failure_is_retryable_without_persisting_private_exception(monkeypatch):
    from app import community_mail as mail
    calls=[]
    store=SimpleNamespace(settings=Settings(line_channel_secret='s',line_channel_access_token='t'),
        call=lambda method,path,**kw: calls.append((method,path,kw)) or True)
    def fail(*args):raise RuntimeError('fixture-private-token-and-payload')
    monkeypatch.setattr(mail,'queue_incident_events',fail)
    with pytest.raises(RuntimeError):mail.run_jobs(store,'fixture-dashboard')
    data=calls[-1][2]['json']
    assert data=={'run_status':'failed','lease_until':None,'last_error':'worker_interrupted'}
    assert 'fixture-private' not in str(calls)


def test_completed_or_running_job_is_not_queued_again(monkeypatch):
    from app import community_mail as mail
    store=SimpleNamespace(settings=Settings(line_channel_secret='s',line_channel_access_token='t'),call=lambda *a,**kw:False)
    monkeypatch.setattr(mail,'queue_incident_events',lambda *args:pytest.fail('duplicate interval'))
    assert mail.run_jobs(store)['already_checked'] is True


def test_job_status_is_private_to_the_admin():
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[session]=lambda:(SimpleNamespace(rpc=lambda *args:{'is_admin':False}),'fixture-token',{})
    with TestClient(app) as client:assert client.get('/api/community/jobs-status').status_code==403


def test_manual_check_is_persisted_before_acknowledging_and_runs_in_background(monkeypatch):
    from app import community_mail as mail
    calls=[]
    store=SimpleNamespace(settings=Settings(line_channel_secret='s',line_channel_access_token='t'),
        rpc=lambda *args:{'is_admin':True},call=lambda method,path,**kw:calls.append(('claim',kw)) or True)
    monkeypatch.setattr(mail,'background_jobs',lambda *args:calls.append(('background',args)))
    app=FastAPI();app.include_router(router);app.dependency_overrides[session]=lambda:(store,'fixture-token',{})
    with TestClient(app) as client:
        response=client.post('/api/community/request-alert-check')
        assert response.status_code==202 and response.json()=={'accepted':True}
    assert calls[0][0]=='claim' and calls[0][1]['json']['p_source']=='manual'
    assert calls[1][0]=='background' and calls[1][1][-1].startswith('community/')


def test_auth_is_required_before_community_reads():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/community/me').status_code == 401
        assert client.post('/api/community/incidents',json={}).status_code == 401


def test_provider_auth_validation_rejects_expired_or_unconfirmed_users():
    settings=Settings(supabase_url='https://example.supabase.co',supabase_service_role_key='fixture-key')
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401,json={'message':'invalid'}))) as client:
        with pytest.raises(HTTPException) as error:
            CommunityStore(settings,client).user('expired-fixture-token')
        assert error.value.status_code == 401
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,json={'id':'fixture-user','email_confirmed_at':None}))) as client:
        with pytest.raises(HTTPException) as error:
            CommunityStore(settings,client).user('unconfirmed-fixture-token')
        assert error.value.status_code == 403


def test_api_rejects_role_and_verification_injection_before_writing():
    calls=[]
    store=SimpleNamespace(rpc=lambda *args: calls.append(args))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[session]=lambda:(store,'fixture-token',{'id':'fixture-user'})
    report={'id':'20000000-0000-4000-8000-000000000001','forest_id':'fixture-A','observation':'smoke',
            'latitude':18.8,'longitude':98.9,'observed_at':'2026-01-01T10:00:00+07:00','status':'confirmed','created_by':'someone-else'}
    with TestClient(app) as client:
        assert client.post('/api/community/incidents',json=report).status_code == 422
        assert client.post('/api/community/memberships',json={'forest_id':'fixture-A','role':'system_admin'}).status_code == 422
    assert calls==[]


def test_observation_requires_timezone_and_rejects_future_time():
    args={'id':'20000000-0000-4000-8000-000000000001','forest_id':'fixture-A','observation':'fire','latitude':18.8,'longitude':98.9}
    with pytest.raises(ValueError): IncidentCreate(**args,observed_at='2026-01-01T00:00:00')
    with pytest.raises(ValueError): IncidentCreate(**args,observed_at='2099-01-01T00:00:00+07:00')


def test_polygon_holes_and_multipolygon_used_for_notification_matching():
    geom={'type':'Polygon','coordinates':[[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[2,1],[2,2],[1,2],[1,1]]]}
    assert point_in_boundary(.5,.5,geom)
    assert not point_in_boundary(1.5,1.5,geom)
    assert not point_in_boundary(8,8,geom)
    assert point_in_boundary(.5,.5,{'type':'MultiPolygon','coordinates':[geom['coordinates']]})


def test_quiet_hours_handle_overnight_and_same_hour_without_infinite_delay():
    now=datetime(2026,10,9,16,30,tzinfo=timezone.utc)  # 23:30 Bangkok
    prefs={'quiet_enabled':True,'quiet_start':21,'quiet_end':7}
    assert next_delivery(prefs,now)==datetime(2026,10,10,0,0,tzinfo=timezone.utc)
    assert next_delivery({'quiet_enabled':False},now)==now
    assert next_delivery({'quiet_enabled':True,'quiet_start':7,'quiet_end':7},now)==now


def test_email_carries_no_alerts_only_account_mail_from_supabase_auth():
    # Fires, pins and incident updates go by LINE only. Community email routes are gone, and the
    # "events"/"daily" email switches are always stored as off, even from an older open page.
    sent = []
    store = SimpleNamespace(rpc=lambda action, payload, token: sent.append((action, payload)) or {}, settings=Settings())
    app = FastAPI(); app.include_router(router); app.dependency_overrides[session] = lambda: (store, 'fixture-token', {'id': 'u'})
    with TestClient(app) as client:
        for method, path in [('post', '/api/community/test-email'), ('get', '/api/community/mail-status'), ('post', '/api/community/resend-webhook')]:
            assert getattr(client, method)(path).status_code in (404, 405), path
        assert client.put('/api/community/preferences', json={'events_enabled': True, 'daily_enabled': True, 'quiet_enabled': True}).status_code == 200
        assert 'email_mode' not in client.get('/api/community/status').json()
    assert sent[-1] == ('preferences', {'events_enabled': False, 'daily_enabled': False, 'quiet_enabled': True, 'quiet_start': 21, 'quiet_end': 7})


def test_photo_reencoding_removes_metadata_and_rejects_invalid_or_large_inputs():
    import io
    from PIL import Image
    from app.community_evidence import prepare_photo, MAX_BYTES
    raw=io.BytesIO();image=Image.new('RGB',(30,20),'green');exif=Image.Exif();exif[270]='private metadata'
    image.save(raw,'JPEG',exif=exif)
    clean=Image.open(io.BytesIO(prepare_photo(raw.getvalue())))
    assert clean.format=='JPEG' and not clean.getexif()
    with pytest.raises(HTTPException):prepare_photo(b'<svg>not a photo</svg>')
    with pytest.raises(HTTPException) as error:prepare_photo(b'x'*(MAX_BYTES+1))
    assert error.value.status_code==413


def test_private_photo_read_denies_missing_rls_row_before_storage_request():
    from app.community_evidence import download_photo
    from uuid import UUID
    store=SimpleNamespace(call=lambda *args,**kwargs:[])
    with pytest.raises(HTTPException) as error:
        download_photo(UUID('30000000-0000-4000-8000-000000000001'),(store,'fixture-token',{}))
    assert error.value.status_code==404
