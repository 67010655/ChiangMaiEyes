"""Append-only, access-controlled field observations. Not an accuracy score."""
import json
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator, model_validator
from app.community import StrictModel, session

router = APIRouter(prefix='/api/community', tags=['Field checks'])


class FieldCheck(StrictModel):
    id: UUID
    corrects_id: UUID | None = None
    checked_at: datetime
    outcome: Literal['fire_found', 'no_fire_found', 'unverified']
    method: Literal['on_site', 'phone', 'photo', 'unavailable']
    note: str = Field(min_length=5, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    position_accuracy_m: float | None = Field(default=None, ge=0, le=100000)
    satellite_match: Literal['matched', 'not_found', 'not_checked'] = 'not_checked'
    satellite_source: str = Field(default='', max_length=300)
    satellite_detected_at: datetime | None = None
    web_received_at: datetime | None = None
    email_delivered_at: datetime | None = None
    message_seen_at: datetime | None = None

    @field_validator('checked_at', 'satellite_detected_at', 'web_received_at', 'email_delivered_at', 'message_seen_at')
    @classmethod
    def valid_time(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('เวลาต้องระบุเขตเวลา')
            if value > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError('เวลาอยู่ในอนาคต')
        return value

    @model_validator(mode='after')
    def evidence_required(self):
        if self.method == 'unavailable' and self.outcome != 'unverified':
            raise ValueError('ยังไม่มีวิธีตรวจต้องเลือกยังตรวจไม่ได้')
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('ระบุพิกัดให้ครบทั้งสองค่า หรือเว้นทั้งคู่')
        if self.satellite_match == 'matched' and not (self.satellite_source and self.satellite_detected_at):
            raise ValueError('ระบุแหล่งและเวลาจุดดาวเทียมที่เทียบ')
        if self.satellite_match != 'matched' and self.satellite_detected_at:
            raise ValueError('เวลาจุดดาวเทียมใช้เมื่อมีจุดที่นำมาเทียบเท่านั้น')
        for before, after in ((self.satellite_detected_at, self.web_received_at), (self.email_delivered_at, self.message_seen_at)):
            if before and after and after < before:
                raise ValueError('เวลารับข้อมูลต้องไม่ก่อนเวลาต้นทาง')
        return self


class ResearchRecord(StrictModel):
    id: UUID
    kind: Literal['fuel', 'pilot', 'model', 'burned_area']
    data: dict
    corrects_id: UUID | None = None

    @field_validator('data')
    @classmethod
    def bounded_json_object(cls, value):
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        except (TypeError, ValueError):
            raise ValueError('ข้อมูลหลักฐานต้องเป็น JSON ที่ถูกต้อง') from None
        if len(encoded) > 400_000:
            raise ValueError('หลักฐานมีขนาดเกิน 400 KB')
        return value


@router.get('/incidents/{incident_id}/field-checks')
def checks(incident_id: UUID, ctx=Depends(session)):
    store, token, _ = ctx
    return store.call('POST', '/rest/v1/rpc/cme_field_check', token=token, json={'p_incident': str(incident_id)})


@router.post('/incidents/{incident_id}/field-checks', status_code=201)
def record_check(incident_id: UUID, payload: FieldCheck, ctx=Depends(session)):
    store, token, _ = ctx
    return store.call('POST', '/rest/v1/rpc/cme_field_check', token=token,
                      json={'p_incident': str(incident_id), 'p_id': str(payload.id), 'p_data': payload.model_dump(mode='json', exclude={'id'})})


@router.get('/forests/{forest_id}/research')
def research_records(forest_id: str, kind: Literal['fuel', 'pilot', 'model', 'burned_area'] | None = None,
                     limit: int = Query(100, ge=1, le=500), ctx=Depends(session)):
    store, token, _ = ctx
    params = {'forest_id': 'eq.' + forest_id, 'select': 'id,forest_id,kind,data,corrects_id,created_at',
              'order': 'created_at.desc', 'limit': str(limit)}
    if kind:
        params['kind'] = 'eq.' + kind
    # RLS on cme_research_records enforces admin/member visibility per forest.
    return store.call('GET', '/rest/v1/cme_research_records', token=token, params=params)


@router.get('/forests/{forest_id}/research/{record_id}')
def research_record(forest_id: str, record_id: UUID, ctx=Depends(session)):
    store, token, _ = ctx
    rows = store.call('GET', '/rest/v1/cme_research_records', token=token, params={
        'id': 'eq.' + str(record_id), 'forest_id': 'eq.' + forest_id,
        'select': 'id,forest_id,kind,data,corrects_id,created_at', 'limit': '1',
    })
    if not rows:
        raise HTTPException(404, 'ไม่พบหลักฐานหรือไม่มีสิทธิ์ดูในป่านี้')
    return rows[0]


@router.post('/forests/{forest_id}/research', status_code=201)
def save_research_record(forest_id: str, payload: ResearchRecord, ctx=Depends(session)):
    if not forest_id or len(forest_id) > 100:
        raise HTTPException(422, 'รหัสป่าชุมชนไม่ถูกต้อง')
    if payload.data.get('schema') == 'cme-spread-evaluation-v1':
        # Do not trust a client-supplied score or a reference to another forest.
        # Recheck against the exact private parent through the caller's RLS.
        from app.spread_scenario import SnapshotEvaluation, evaluate_snapshot, Evidence
        try:
            if payload.kind != 'model' or set(payload.data) != {'schema', 'scenario_record_id', 'evaluation', 'observations'}:
                raise ValueError('รูปแบบผลเปรียบเทียบไม่ถูกต้อง')
            parent_id = UUID(payload.data['scenario_record_id'])
            submitted = payload.data['evaluation']
            Evidence.time_zone(datetime.fromisoformat(submitted['evaluated_at'].replace('Z', '+00:00')))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(422, 'รูปแบบหลักฐานการเปรียบเทียบไม่ถูกต้อง') from None
        parent = research_record(forest_id, parent_id, ctx)
        if parent['kind'] != 'model' or parent['data'].get('schema') != 'cme-spread-scenario-v1':
            raise HTTPException(422, 'รายการอ้างอิงต้องเป็นผลจำลองที่บันทึกไว้')
        try:
            verified = evaluate_snapshot(SnapshotEvaluation(snapshot=parent['data']['result'], observations=payload.data['observations']))
        except (ValueError, KeyError):
            raise HTTPException(422, 'หลักฐานไม่สอดคล้องกับผลจำลองที่อ้างถึง') from None
        verified['evaluated_at'] = submitted['evaluated_at']  # Stable retry; DB created_at remains server-owned.
        if verified != submitted:
            raise HTTPException(422, 'ผลเปรียบเทียบไม่ตรงกับหลักฐานและผลจำลองเดิม กรุณากดเทียบใหม่')
    store, token, _ = ctx
    row = store.call('POST', '/rest/v1/rpc/cme_research_save', token=token,
                     json={'p_id': str(payload.id), 'p_forest': forest_id, 'p_kind': payload.kind,
                           'p_data': payload.data, 'p_corrects': str(payload.corrects_id) if payload.corrects_id else None})
    # Do not return the recorder's account identifier.
    return {key: row.get(key) for key in ('id', 'forest_id', 'kind', 'data', 'corrects_id', 'created_at')}


def summarize_field_checks(rows: list[dict], *, now: datetime | None = None) -> dict:
    """Summarize user-entered paired field checks without exposing their text or IDs.

    These are exploratory counts from a self-selected sample, not a certified
    province-wide accuracy estimate. Corrected records supersede their parents.
    """
    now = now or datetime.now(timezone.utc)
    superseded = {str(r.get('corrects_id')) for r in rows if r.get('corrects_id')}
    active = [r for r in rows if str(r.get('id')) not in superseded]
    methods, outcomes, matches = {}, {}, {}
    matrix = {'true_positive': 0, 'false_positive': 0, 'false_negative': 0, 'true_negative': 0}
    sources: dict[str, dict[str, int]] = {}
    satellite_to_web, delivery_to_seen = [], []
    eligible = 0

    def parsed(value):
        if not value:
            return None
        try:
            item = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return item if item.tzinfo and item.utcoffset() is not None else None
        except (ValueError, TypeError):
            return None

    def bump(target, key):
        if key:
            target[str(key)] = target.get(str(key), 0) + 1

    for row in active:
        data = row.get('data') if isinstance(row.get('data'), dict) else {}
        method, outcome, match = data.get('method'), data.get('outcome'), data.get('satellite_match')
        bump(methods, method); bump(outcomes, outcome); bump(matches, match)
        if method == 'on_site' and outcome in ('fire_found', 'no_fire_found') and match in ('matched', 'not_found'):
            eligible += 1
            key = 'true_positive' if outcome == 'fire_found' and match == 'matched' else \
                  'false_negative' if outcome == 'fire_found' else \
                  'false_positive' if match == 'matched' else 'true_negative'
            matrix[key] += 1
            raw_source = str(data.get('satellite_source') or '').upper()
            source = next((label for token, label in (
                ('NASA', 'NASA/FIRMS'), ('FIRMS', 'NASA/FIRMS'), ('GISTDA', 'GISTDA'),
                ('VIIRS', 'VIIRS'), ('MODIS', 'MODIS'), ('NOAA', 'NOAA'),
            ) if token in raw_source), 'แหล่งอื่น/ไม่ระบุ')
            source_row = sources.setdefault(source, {name: 0 for name in matrix})
            source_row[key] += 1
        detected, received = parsed(data.get('satellite_detected_at')), parsed(data.get('web_received_at'))
        if detected and received and received >= detected:
            satellite_to_web.append((received-detected).total_seconds())
        delivered, seen = parsed(data.get('email_delivered_at')), parsed(data.get('message_seen_at'))
        if delivered and seen and seen >= delivered:
            delivery_to_seen.append((seen-delivered).total_seconds())

    tp, fp, fn, tn = (matrix[key] for key in ('true_positive','false_positive','false_negative','true_negative'))
    total_pairs = tp + fp + fn + tn
    ratio = lambda numerator, denominator: round(100*numerator/denominator, 1) if denominator else None

    def timing(values):
        return {'samples': len(values), 'median_seconds': round(median(values), 1) if values else None}

    return {
        'generated_at': now.isoformat(),
        'status': 'no_paired_on_site_checks' if total_pairs == 0 else 'exploratory_pairs_available',
        'record_count': len(rows), 'active_record_count': len(active),
        'superseded_record_count': len(rows)-len(active),
        'methods': methods, 'outcomes': outcomes, 'satellite_matches': matches,
        'paired_on_site_count': total_pairs, 'confusion_matrix': matrix,
        'metrics_percent': {
            'precision': ratio(tp, tp+fp), 'recall': ratio(tp, tp+fn),
            'specificity': ratio(tn, tn+fp), 'accuracy': ratio(tp+tn, total_pairs),
        },
        'by_source': [{'source': name, **values} for name, values in sorted(sources.items())],
        'latency': {'satellite_to_web': timing(satellite_to_web), 'email_delivered_to_seen': timing(delivery_to_seen)},
        'scope': 'user_recorded_on_site_pairs_only',
        'limitations': [
            'ผลมาจากรายการที่ผู้ใช้เลือกตรวจ ไม่ใช่การสุ่มตัวอย่างแทนทั้งจังหวัด',
            'การจับคู่จุดดาวเทียมกับเหตุเป็นข้อมูลที่ผู้ตรวจบันทึก ต้องตรวจตำแหน่ง เวลา และวิธีค้นต้นทาง',
            'สถิตินี้ยังไม่ใช่ผลรับรองแบบจำลองหรือการตรวจครบทุกช่วงที่ไม่มีเหตุ',
        ],
    }


@router.get('/field-checks/evaluation')
def field_check_evaluation(ctx=Depends(session)):
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        from fastapi import HTTPException
        raise HTTPException(403, 'สำหรับผู้ดูแลระบบ')
    rows = store.rows('cme_field_checks', select='id,corrects_id,data,created_at', order='created_at.desc', limit='10000')
    summary = summarize_field_checks(rows)
    summary['truncated'] = len(rows) >= 10000
    return summary
