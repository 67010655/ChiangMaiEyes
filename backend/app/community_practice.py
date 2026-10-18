"""Owner-isolated rehearsal. Simulated actors never gain production rights."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from app.community import StrictModel, session
from app.community_evidence import prepare_photo, MAX_BYTES
from app.community_field import FieldCheck

router = APIRouter(prefix='/api/community/practice', tags=['Practice'])
Actor = Literal['A', 'B', 'outsider']
BUCKET = 'cme-practice-evidence'
TRANSITIONS = {'pending':['confirmed','cancelled'], 'confirmed':['coordinating','controlled','cancelled'],
               'coordinating':['controlled','cancelled'], 'controlled':['coordinating','closed'], 'closed':['pending'], 'cancelled':['pending']}


class Start(StrictModel):
    id: UUID
    title: str = Field(default='รอบซ้อม', min_length=1, max_length=120)
    scenario: Literal['smoke', 'no_response', 'duplicate', 'offline'] = 'smoke'


class Action(StrictModel):
    request_id: UUID
    version: int = Field(ge=1)
    actor: Actor
    action: Literal['create','claim','status','invite','respond','note','merge','feedback','check']
    incident_id: UUID | None = None
    target_id: UUID | None = None
    status: str = Field(default='', max_length=30)
    note: str = Field(default='', max_length=2000)
    outcome: Literal['done','needed_help','unable'] | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0, le=86400)
    observation: Literal['smoke','fire'] = 'smoke'
    field_check: FieldCheck | None = None


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(store, token, run_id=None):
    return store.call('POST', '/rest/v1/rpc/cme_practice_read', token=token, json={'p_id': str(run_id) if run_id else None})


def save(store, token, run_id, version, data):
    return store.call('POST', '/rest/v1/rpc/cme_practice_save', token=token,
                      json={'p_id': str(run_id), 'p_version': version, 'p_data': data})


def permissions(incident, actor):
    return {'read': actor == 'A' or actor == 'B' and incident.get('partner') in ('invited','accepted'),
            'manage': actor == 'A', 'note': actor == 'A' or actor == 'B' and incident.get('partner') == 'accepted'}


def visible(run, actor):
    result = copy.deepcopy(run)
    result['data']['incidents'] = [i for i in result['data']['incidents'] if permissions(i, actor)['read']]
    ids = {i['id'] for i in result['data']['incidents']}
    result['data']['events'] = [e for e in result['data']['events'] if e.get('incident_id') in ids or not e.get('incident_id') and e['actor']==actor]
    result['data']['feedback'] = [f for f in result['data']['feedback'] if actor=='A' or f['actor']==actor]
    for i in result['data']['incidents']:
        i['permissions'] = permissions(i, actor)
    return result


def evolve(run, payload):
    """Pure transition function; meaningful permissions, retries and stale writes."""
    data = copy.deepcopy(run['data'])
    digest = hashlib.sha256(json.dumps(payload.model_dump(mode='json', exclude={'request_id','version'}), sort_keys=True).encode()).hexdigest()
    prior = next((e for e in data['events'] if e['request_id'] == str(payload.request_id)), None)
    if prior:
        if prior['request_hash'] != digest:
            raise HTTPException(409, 'รหัสการส่งนี้ถูกใช้กับข้อมูลอื่นแล้ว')
        return None
    if payload.version != run['version']:
        raise HTTPException(409, 'มีคนอัปเดตรอบซ้อมแล้ว โหลดล่าสุดก่อนส่งอีกครั้ง')
    if len(data['events']) >= 400:
        raise HTTPException(400, 'รอบนี้ครบ 400 ขั้นตอนแล้ว เริ่มรอบใหม่ได้')
    iid = str(payload.incident_id) if payload.incident_id else None
    incident = next((i for i in data['incidents'] if i['id'] == iid), None)
    kind = payload.action
    if kind == 'feedback':
        if not payload.outcome or not payload.note:
            raise HTTPException(400, 'ระบุผลใช้งานและสิ่งที่ติดขัด')
        data['feedback'].append({'actor':payload.actor,'outcome':payload.outcome,'elapsed_seconds':payload.elapsed_seconds,'note':payload.note,'at':stamp()})
    elif kind == 'create':
        if payload.actor != 'A':
            raise HTTPException(403, 'บทบาทนี้ไม่มีสิทธิ์แจ้งเหตุในป่าซ้อม A')
        if not iid or incident or len(data['incidents']) >= 30:
            raise HTTPException(400, 'ใช้รหัสเหตุซ้อมใหม่ และไม่เกิน 30 เหตุต่อรอบ')
        data['incidents'].append({'id':iid,'forest_id':'practice-A','observation':payload.observation,'description':payload.note,
                                 'status':'pending','coordinator':None,'partner':None,'linked_id':None,'photos':[],'checks':[],'created_at':stamp()})
    else:
        if not incident or not permissions(incident, payload.actor)['read']:
            raise HTTPException(403, 'บทบาทนี้ยังไม่มีสิทธิ์ดูเหตุซ้อมนี้')
        allowed = permissions(incident, payload.actor)
        if kind in ('note','check'):
            if not allowed['note']:
                raise HTTPException(403, 'รับร่วมประสานก่อนเพิ่มข้อมูล')
            if kind == 'note' and not payload.note:
                raise HTTPException(400, 'ระบุบันทึกเพิ่มเติม')
            if kind == 'check':
                if payload.field_check is None:
                    raise HTTPException(400, 'ระบุผลตรวจให้ครบ')
                check = payload.field_check.model_dump(mode='json')
                if check['corrects_id'] and not any(c['id']==check['corrects_id'] for c in incident['checks']):
                    raise HTTPException(400, 'แก้ได้เฉพาะผลตรวจในเหตุซ้อมเดียวกัน')
                if any(c['id']==check['id'] for c in incident['checks']):
                    raise HTTPException(409, 'ใช้รหัสผลตรวจใหม่')
                incident['checks'].append(check)
        elif kind == 'respond':
            if payload.actor != 'B' or incident['partner'] != 'invited' or payload.status not in ('accepted','declined'):
                raise HTTPException(403, 'ตอบรับได้เฉพาะป่าซ้อม B ที่ได้รับคำเชิญ')
            incident['partner'] = payload.status
        else:
            if not allowed['manage'] or incident['linked_id']:
                raise HTTPException(403, 'บทบาทนี้เปลี่ยนสถานะเหตุหลักไม่ได้')
            if kind == 'status':
                if payload.status not in TRANSITIONS[incident['status']] or not payload.note:
                    raise HTTPException(400, 'เปลี่ยนตามขั้นตอนและระบุผลตรวจหรือเหตุผล')
                incident['status'] = payload.status
            elif kind == 'claim':
                if incident['coordinator']:
                    raise HTTPException(409, 'มีผู้รับประสานแล้ว')
                incident['coordinator'] = payload.actor
            elif kind == 'invite':
                if incident['partner'] in ('invited','accepted'):
                    raise HTTPException(409, 'มีคำขอร่วมประสานแล้ว')
                incident['partner'] = 'invited'
            elif kind == 'merge':
                target = next((i for i in data['incidents'] if i['id']==str(payload.target_id)), None)
                if incident['status']!='pending' or not target or target is incident or target['linked_id'] or target['status'] in ('closed','cancelled') or not payload.note:
                    raise HTTPException(400, 'เลือกเหตุหลักที่ยังเปิดและระบุเหตุผลที่ซ้ำกัน')
                incident['linked_id'] = target['id']; incident['status'] = 'cancelled'
    data['events'].append({'request_id':str(payload.request_id),'request_hash':digest,'actor':payload.actor,'kind':kind,
                           'incident_id':iid,'status':payload.status,'note':payload.note,'at':stamp()})
    return data


@router.get('/runs')
def runs(ctx=Depends(session)):
    store, token, _ = ctx
    return read(store, token)


@router.post('/runs', status_code=201)
def start(payload: Start, ctx=Depends(session)):
    store, token, _ = ctx
    # Retry-safe creation, without overwriting a previous completed rehearsal.
    try:
        existing = read(store, token, payload.id)
        if existing['data']['title'] != payload.title or existing['data']['scenario'] != payload.scenario:
            raise HTTPException(409, 'รหัสรอบซ้อมนี้ถูกใช้แล้ว')
        return existing
    except HTTPException as error:
        if error.status_code != 404:
            raise
    return save(store, token, payload.id, 0, {'mode':'practice','title':payload.title,'scenario':payload.scenario,
                                            'started_at':stamp(),'incidents':[],'events':[],'feedback':[]})


@router.get('/runs/{run_id}')
def detail(run_id: UUID, actor: Actor = 'A', ctx=Depends(session)):
    store, token, _ = ctx
    return visible(read(store, token, run_id), actor)


@router.post('/runs/{run_id}/actions')
def action(run_id: UUID, payload: Action, ctx=Depends(session)):
    store, token, _ = ctx
    run = read(store, token, run_id)
    data = evolve(run, payload)
    updated = save(store, token, run_id, run['version'], data) if data is not None else run
    return visible(updated, payload.actor)


@router.get('/runs/{run_id}/export')
def export(run_id: UUID, actor: Actor = 'A', ctx=Depends(session)):
    store, token, _ = ctx
    if actor != 'A':
        raise HTTPException(403, 'สลับเป็นผู้จัดซ้อมป่า A ก่อนส่งออกผลทั้งรอบ')
    return {'evidence_mode':'practice_only','warning':'ข้อมูลซ้อม ห้ามรวมกับผลความแม่นยำภาคสนามจริง','run':read(store,token,run_id)}


@router.post('/runs/{run_id}/incidents/{incident_id}/photo')
async def photo(run_id: UUID, incident_id: UUID, request: Request, photo_id: UUID, version: int = Query(ge=1), actor: Actor = 'A', ctx=Depends(session)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_BYTES:
            raise HTTPException(413, 'รูปต้องมีขนาดไม่เกิน 4 MB')
    return await run_in_threadpool(persist_photo, ctx, run_id, incident_id, photo_id, version, actor, bytes(raw))


def persist_photo(ctx, run_id, incident_id, photo_id, version, actor, raw):
    store, token, _ = ctx
    run=read(store,token,run_id); data=copy.deepcopy(run['data'])
    incident=next((i for i in data['incidents'] if i['id']==str(incident_id)),None)
    if not incident or not permissions(incident,actor)['note']:
        raise HTTPException(403,'บทบาทนี้เพิ่มรูปไม่ได้')
    clean=prepare_photo(raw); digest=hashlib.sha256(clean).hexdigest()
    prior=next((p for i in data['incidents'] for p in i['photos'] if p['id']==str(photo_id)),None)
    if prior:
        if prior['sha256']!=digest or prior not in incident['photos']:
            raise HTTPException(409,'รหัสรูปนี้ถูกใช้แล้ว')
        return visible(run,actor)
    if version!=run['version'] or len(incident['photos'])>=10:
        raise HTTPException(409,'โหลดสถานะล่าสุดก่อนแนบรูป ไม่เกิน 10 รูปต่อเหตุ')
    path=f'{run_id}/{photo_id}.jpg'; endpoint=store.settings.supabase_url.rstrip('/')+'/storage/v1/object/'+BUCKET
    try:
        response=store.client.post(endpoint+'/'+path,headers={**store.headers(),'Content-Type':'image/jpeg','x-upsert':'false'},content=clean)
        if response.status_code==409:
            existing=store.client.get(endpoint+'/'+path,headers=store.headers())
            if existing.status_code!=200 or hashlib.sha256(existing.content).hexdigest()!=digest:
                raise HTTPException(409,'รหัสรูปนี้มีไฟล์อื่นอยู่แล้ว ใช้รหัสใหม่')
        elif response.status_code>=400:
            raise HTTPException(503,'อัปโหลดรูปซ้อมไม่ได้ ลองอีกครั้ง')
        incident['photos'].append({'id':str(photo_id),'sha256':digest,'at':stamp()})
        try:
            updated=save(store,token,run_id,version,data)
        except HTTPException:
            # Keep an unreferenced private object until the same photo ID is
            # retried. Another request may have committed metadata already.
            raise
        return visible(updated,actor)
    except httpx.HTTPError:
        raise HTTPException(503,'ยังไม่ยืนยันผลแนบรูปซ้อม โหลดล่าสุดก่อนลองอีกครั้ง') from None


@router.get('/runs/{run_id}/photos/{photo_id}')
def download(run_id: UUID, photo_id: UUID, actor: Actor = 'A', ctx=Depends(session)):
    store,token,_=ctx
    run=visible(read(store,token,run_id),actor)
    if not any(p['id']==str(photo_id) for i in run['data']['incidents'] for p in i['photos']):
        raise HTTPException(404,'ไม่พบรูปซ้อมที่บทบาทนี้ดูได้')
    try:
        raw=store.client.get(store.settings.supabase_url.rstrip('/')+f'/storage/v1/object/{BUCKET}/{run_id}/{photo_id}.jpg',headers=store.headers())
    except httpx.HTTPError:
        raise HTTPException(503,'ยังโหลดรูปซ้อมไม่ได้ ลองอีกครั้ง') from None
    if raw.status_code!=200:
        raise HTTPException(503,'โหลดรูปซ้อมไม่ได้')
    return Response(raw.content,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
