from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.community import router, session, IncidentCreate
from app.community_store import CommunityStore
from app.community_mail import point_in_boundary, next_delivery, verify_webhook, process_outbox
from app.config import Settings


def test_worker_manual_check_includes_environment_and_records_completion(monkeypatch):
    from app import community_mail as mail
    calls=[]
    settings=Settings(community_email_test_recipient='fixture@example.test')
    store=SimpleNamespace(settings=settings,call=lambda method,path,**kw: calls.append((method,path,kw)) or True)
    monkeypatch.setattr('app.services.get_dashboard',lambda settings:'fixture-dashboard')
    monkeypatch.setattr(mail,'queue_incident_events',lambda store,now:2)
    def environment(store,dashboard,now):
        assert dashboard=='fixture-dashboard'
        return 3
    monkeypatch.setattr(mail,'queue_environment',environment)
    monkeypatch.setattr(mail,'process_outbox',lambda store:{'provider_accepted':1,'failed':0,'suppressed':0})
    assert mail.run_jobs(store)['queued']==5
    assert calls[-1][2]['json']['run_status']=='completed'
    assert calls[-1][2]['json']['summary']['provider_accepted']==1


def test_worker_failure_is_retryable_without_persisting_private_exception(monkeypatch):
    from app import community_mail as mail
    calls=[]
    store=SimpleNamespace(settings=Settings(community_email_test_recipient='fixture@example.test'),
        call=lambda method,path,**kw: calls.append((method,path,kw)) or True)
    def fail(*args):raise RuntimeError('fixture-private-token-and-payload')
    monkeypatch.setattr(mail,'queue_incident_events',fail)
    with pytest.raises(RuntimeError):mail.run_jobs(store,'fixture-dashboard')
    data=calls[-1][2]['json']
    assert data=={'run_status':'failed','lease_until':None,'last_error':'worker_interrupted'}
    assert 'fixture-private' not in str(calls)


def test_completed_or_running_job_is_not_queued_again(monkeypatch):
    from app import community_mail as mail
    store=SimpleNamespace(settings=Settings(community_email_test_recipient='fixture@example.test'),call=lambda *a,**kw:False)
    monkeypatch.setattr(mail,'queue_incident_events',lambda *args:pytest.fail('duplicate interval'))
    assert mail.run_jobs(store)['already_checked'] is True


def test_job_status_is_private_to_the_admin():
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[session]=lambda:(SimpleNamespace(rpc=lambda *args:{'is_admin':False}),'fixture-token',{})
    with TestClient(app) as client:assert client.get('/api/community/jobs-status').status_code==403


def test_manual_check_is_persisted_before_acknowledging_and_runs_in_background(monkeypatch):
    from app import community_mail as mail
    calls=[]
    store=SimpleNamespace(settings=Settings(community_email_test_recipient='fixture@example.test'),
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


def test_svix_official_signature_vector_and_replay_time_window():
    # Public reference fixture from Svix documentation, not a real credential.
    headers={'svix-id':'msg_loFOjxBNrRLzqYUf','svix-timestamp':'1731705121',
             'svix-signature':'v1,rAvfW3dJ/X/qxhsaXPOyyCGmRKsaKWcsNccKXlIktD0='}
    payload=b'{"event_type":"ping","data":{"success":true}}'
    secret='whsec_plJ3nmyCDGBKInavdOK15jsl'
    assert verify_webhook(payload,headers,secret,now=1731705121)['data']['success']
    with pytest.raises(HTTPException):verify_webhook(payload+b' ',headers,secret,now=1731705121)
    with pytest.raises(HTTPException):verify_webhook(payload,headers,secret,now=1731705500)


class MailStore:
    def __init__(self,provider_status=200,subscribed=True,recipient='fixture@example.test'):
        self.settings=Settings(supabase_url='https://example.supabase.co',supabase_service_role_key='fixture',
            resend_api_key='fixture',community_email_test_recipient='fixture@example.test')
        self.row={'id':'queued-fixture','user_id':'fixture-user','forest_id':'fixture-A','category':'hotspot',
                  'recipient':recipient,'attempts':1,'first_attempt_at':None,'subject':'Fixture','body_html':'Fixture'}
        self.patches=[];self.sent=[];self.subscribed=subscribed
        def transport(request):
            self.sent.append(request)
            return httpx.Response(provider_status,json={'id':'fixture-provider-id'} if provider_status==200 else {'error':'Fixture'})
        self.client=httpx.Client(transport=httpx.MockTransport(transport))
    def call(self,method,path,**kwargs):
        if path.endswith('cme_claim_emails'):return [self.row]
        if '/auth/v1/admin/users/' in path:return {'email':'fixture@example.test','email_confirmed_at':'2026-01-01T00:00:00Z'}
        raise AssertionError(path)
    def rows(self,table,**kwargs):
        if table=='cme_notification_preferences':return [{'events_enabled':self.subscribed}]
        if table=='cme_memberships':return [{'id':'fixture-membership'}]
        raise AssertionError(table)
    def patch(self,table,row_id,data):self.patches.append(data)


def test_email_rechecks_opt_in_and_test_recipient_before_delivery():
    store=MailStore(subscribed=False)
    assert process_outbox(store)['suppressed']==1
    assert not store.sent
    store=MailStore(recipient='someone-else@example.test')
    assert process_outbox(store)['suppressed']==1
    assert not store.sent


def test_email_worker_retries_provider_failures_with_the_same_idempotency_key():
    store=MailStore(provider_status=429)
    assert process_outbox(store)['failed']==1
    assert store.sent[0].headers['Idempotency-Key']=='cme/queued-fixture'
    assert store.patches[-1]['status']=='pending'
    assert 'available_at' in store.patches[-1]
    assert store.patches[-1]['last_error']=='Resend HTTP 429'


def test_accepted_email_is_distinct_from_confirmed_delivery():
    store=MailStore()
    assert process_outbox(store)['provider_accepted']==1
    assert store.patches[-1]['delivery_status']=='provider_accepted'
    assert store.patches[-1]['provider_id']=='fixture-provider-id'


def test_sender_rejection_is_terminal_instead_of_repeated_delivery():
    store=MailStore(provider_status=403)
    assert process_outbox(store)['failed']==1
    assert store.patches[-1]['status']=='failed'


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
