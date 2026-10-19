"""Private community workflow. All writes also enforce permissions in SQL."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings, get_settings
from app.community_store import CommunityStore

router = APIRouter(prefix='/api/community', tags=['Community'])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class MembershipRequest(StrictModel):
    forest_id: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=1000)


class ReviewMembership(StrictModel):
    status: Literal['approved', 'rejected', 'revoked']
    note: str = Field(default='', max_length=1000)


class IncidentCreate(StrictModel):
    id: UUID
    forest_id: str = Field(min_length=1, max_length=100)
    observation: Literal['smoke', 'fire']
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    observed_at: datetime
    description: str = Field(default='', max_length=2000)

    @field_validator('observed_at')
    @classmethod
    def observation_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('เวลาที่พบเหตุต้องระบุเขตเวลา')
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('เวลาที่พบเหตุอยู่ในอนาคต')
        return value


class IncidentUpdate(StrictModel):
    action: Literal['change_status', 'claim_coordination', 'invite_partner', 'respond_partner', 'add_note', 'publish_summary', 'merge_incident']
    target_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)
    status: Literal['pending', 'confirmed', 'coordinating', 'controlled', 'closed', 'cancelled', 'accepted', 'declined'] | None = None
    forest_id: str | None = Field(default=None, max_length=100)
    note: str = Field(default='', max_length=2000)
    published: bool | None = None


class NotificationPreferences(StrictModel):
    events_enabled: bool = False
    daily_enabled: bool = False
    quiet_enabled: bool = False
    quiet_start: int = Field(default=21, ge=0, le=23)
    quiet_end: int = Field(default=7, ge=0, le=23)


def session(authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)):
    if not authorization or not authorization.startswith('Bearer ') or len(authorization) > 8192:
        raise HTTPException(401, 'เข้าสู่ระบบเพื่อใช้พื้นที่ชุมชน')
    token = authorization[7:]
    store = CommunityStore(settings)
    return store, token, store.user(token)


@router.get('/status')
def community_status(settings: Settings = Depends(get_settings)):
    try:
        store = CommunityStore(settings)
        store.rows('cme_forests', select='forest_id', limit='1')
        ready = True
    except HTTPException:
        ready = False
    mode = 'live' if settings.community_email_enabled else 'test' if settings.community_email_test_recipient else 'unavailable'
    from app.community_line import enabled
    return {'ready': ready, 'email_mode': mode, 'line_available': enabled(settings), 'private_records': True}


@router.get('/public-incidents')
def public_incidents(settings: Settings = Depends(get_settings)):
    return CommunityStore(settings).call('POST', '/rest/v1/rpc/cme_public_incidents', json={})


@router.get('/me')
def me(ctx=Depends(session)):
    store, token, user = ctx
    data = store.rpc('me', {}, token)
    return {**data, 'user_id': user['id'], 'test_recipient': store.settings.community_email_test_recipient if data['is_admin'] else None}


def contact_forest_ids(forest_ids: list[str] = Query(min_length=1, max_length=3)):
    if any(not forest_id.strip() or len(forest_id) > 100 for forest_id in forest_ids):
        raise HTTPException(422, 'รหัสป่าไม่ถูกต้อง')
    return list(dict.fromkeys(forest_ids))


@router.get('/contact-status')
def contact_status(response: Response, forest_ids=Depends(contact_forest_ids), settings: Settings = Depends(get_settings)):
    response.headers['Cache-Control'] = 'no-store'
    rows = CommunityStore(settings).call('POST', '/rest/v1/rpc/cme_forest_contact_status',
                                         json={'p_forest_ids': forest_ids})
    # Explicit public allowlist, even if the DB function changes later.
    return [{'forest_id': r['forest_id'], 'has_representative': r['has_representative'] is True} for r in rows]


@router.get('/forest-contacts')
def forest_contacts(response: Response, forest_ids=Depends(contact_forest_ids), ctx=Depends(session)):
    store, token, _ = ctx
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Authorization'
    rows = store.call('POST', '/rest/v1/rpc/cme_forest_contacts', token=token,
                      json={'p_forest_ids': forest_ids})
    return [{'forest_id': r['forest_id'], 'representatives': [
        {'name': rep['name'], 'email': rep['email']} for rep in r['representatives']
    ]} for r in rows]


@router.post('/memberships')
def request_membership(payload: MembershipRequest, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('request_membership', payload.model_dump(), token)


@router.get('/review-queue')
def review_queue(ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('review_queue', {}, token)


@router.patch('/memberships/{membership_id}')
def review_membership(membership_id: UUID, payload: ReviewMembership, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('review_membership', {'id': str(membership_id), **payload.model_dump()}, token)


@router.put('/preferences')
def preferences(payload: NotificationPreferences, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('preferences', payload.model_dump(), token)


@router.get('/incidents')
def incidents(forest_id: str | None = None, offset: int = Query(default=0, ge=0, le=100000), ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('list_incidents', {'forest_id': forest_id, 'offset': offset}, token)


@router.post('/incidents', status_code=201)
def create_incident(payload: IncidentCreate, ctx=Depends(session)):
    store, token, _ = ctx
    result = store.rpc('create_incident', payload.model_dump(mode='json'), token)
    # The persistent outbox is reconstructed by the worker, including after a
    # transient failure. An email failure never rolls back a saved incident.
    return result


@router.get('/incidents/{incident_id}')
def incident_detail(incident_id: UUID, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('incident_detail', {'id': str(incident_id)}, token)


@router.get('/incidents/{incident_id}/events')
def incident_events(incident_id: UUID, offset: int = Query(default=0, ge=0, le=100000), ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('incident_events', {'id': str(incident_id), 'offset': offset}, token)


@router.post('/incidents/{incident_id}/photo')
async def incident_photo(incident_id: UUID, request: Request, ctx=Depends(session)):
    from app.community_evidence import upload_photo
    return await upload_photo(incident_id, request, ctx)


@router.get('/photos/{photo_id}')
def photo(photo_id: UUID, ctx=Depends(session)):
    from app.community_evidence import download_photo
    return download_photo(photo_id, ctx)


@router.patch('/incidents/{incident_id}')
def update_incident(incident_id: UUID, payload: IncidentUpdate, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc(payload.action, {'id': str(incident_id), **payload.model_dump(mode='json', exclude={'action'}, exclude_none=True)}, token)


@router.get('/my-reports')
def my_reports(ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('my_reports', {}, token)


@router.post('/my-reports/{report_id}/cancel')
def cancel_report(report_id: UUID, ctx=Depends(session)):
    store, token, _ = ctx
    return store.rpc('cancel_legacy', {'id': str(report_id)}, token)


@router.post('/test-email')
def test_email(ctx=Depends(session)):
    from app.community_mail import queue_test_email, process_outbox
    store, token, user = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    queued = queue_test_email(store, user)
    result = process_outbox(store, limit=1, only_id=queued)
    return {'queued_id': queued, **result}


@router.post('/run-alerts')
def run_alerts(ctx=Depends(session)):
    from app.community_mail import run_jobs
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    return run_jobs(store)


@router.post('/request-alert-check', status_code=202)
def request_alert_check(background_tasks: BackgroundTasks, ctx=Depends(session)):
    from app.community_mail import claim_job, background_jobs
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    from app.community_mail import alerts_configured
    if not alerts_configured(store.settings):
        raise HTTPException(503, 'ยังไม่ได้กำหนดการส่งอีเมลหรือ LINE')
    job_key = claim_job(store,'manual')
    if not job_key:
        return {'accepted':False,'already_checked':True}
    background_tasks.add_task(background_jobs,store.settings,None,'manual',job_key)
    return {'accepted':True}


@router.get('/mail-status')
def mail_status(ctx=Depends(session)):
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    return store.rows('cme_email_outbox', select='id,category,status,delivery_status,attempts,created_at,sent_at,last_error', order='created_at.desc', limit='20')


@router.get('/jobs/alerts')
def scheduled_alerts(authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)):
    if not settings.community_job_secret or not hmac.compare_digest(authorization or '', 'Bearer ' + settings.community_job_secret):
        raise HTTPException(401, 'Unauthorized')
    from app.community_mail import run_jobs
    return run_jobs(CommunityStore(settings),source='scheduled')


@router.get('/jobs-status')
def jobs_status(ctx=Depends(session)):
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    return {
        'scheduler_enabled': store.settings.community_scheduler_enabled,
        'scheduler_provider': 'Supabase Cron' if store.settings.community_scheduler_enabled else None,
        'interval_minutes': 10 if store.settings.community_scheduler_enabled else None,
        'runs': store.rows('cme_job_runs', select='started_at,completed_at,source,run_status,lease_until,summary,last_error',
                           order='started_at.desc', limit='20'),
    }


@router.post('/resend-webhook')
async def resend_webhook(request: Request, settings: Settings = Depends(get_settings)):
    from app.community_mail import handle_webhook
    if not settings.resend_webhook_secret:
        raise HTTPException(503, 'Webhook not configured')
    length = request.headers.get('content-length') or '0'
    if not length.isdecimal():
        raise HTTPException(400, 'Invalid content length')
    if int(length) > 65536:
        raise HTTPException(413, 'Payload too large')
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 65536:
            raise HTTPException(413, 'Payload too large')
    payload = bytes(payload)
    return handle_webhook(CommunityStore(settings), payload, dict(request.headers))


@router.get('/line')
def line_status(ctx=Depends(session)):
    from app.community_line import status
    store, _, user = ctx
    return status(store, user)


@router.post('/line/link-code')
def line_link_code(ctx=Depends(session)):
    from app.community_line import new_link_code
    store, _, user = ctx
    return new_link_code(store, user)


@router.delete('/line/link')
def line_unlink(ctx=Depends(session)):
    from app.community_line import unlink
    store, _, user = ctx
    return unlink(store, user)


@router.post('/line/test')
def line_test(ctx=Depends(session)):
    from app.community_line import queue_test, process_outbox
    store, token, user = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    queued = queue_test(store, user)
    return {'queued_id': queued, **process_outbox(store)}


@router.post('/line-webhook')
async def line_webhook(request: Request, settings: Settings = Depends(get_settings)):
    from app.community_line import enabled, handle_webhook
    if not enabled(settings):
        raise HTTPException(503, 'Webhook not configured')
    length = request.headers.get('content-length') or '0'
    if not length.isdecimal():
        raise HTTPException(400, 'Invalid content length')
    if int(length) > 262144:
        raise HTTPException(413, 'Payload too large')
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 262144:
            raise HTTPException(413, 'Payload too large')
    return handle_webhook(CommunityStore(settings), bytes(payload), request.headers.get('x-line-signature'))
