"""Immutable NOAA model frames, separate from measured observations.

The database sets first_stored_at. Re-fetching an identical file does not
backdate evidence or overwrite a model frame that was already seen.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.community_store import CommunityStore

router = APIRouter(prefix='/api/ventilation/archive', tags=['GFS model archive'])
log = logging.getLogger(__name__)


def public_frame(frame: dict) -> dict:
    return {key: value for key, value in frame.items() if not key.startswith('_')}


def collect_frame(settings: Settings, frame: dict):
    if not settings.supabase_url or not settings.supabase_service_role_key or frame.get('status') not in ('available', 'partial'):
        return
    try:
        raw = frame['_archive_grib_base64']
        data = base64.b64decode(raw, validate=True)
        if not data.startswith(b'GRIB') or len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != frame['sha256']:
            raise ValueError('GRIB evidence mismatch')
        CommunityStore(settings).call('POST', '/rest/v1/rpc/cme_gfs_ingest', json={
            'p_frame': public_frame(frame), 'p_grib_base64': raw})
    except Exception:
        # Never log service credentials, database payloads or auth details.
        log.warning('GFS model archive did not finish; live data may still be available')


def cutoff(value: str | None):
    now = datetime.now(timezone.utc)
    try:
        end = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else now
        if end.tzinfo is None or end > now + timedelta(minutes=5):
            raise ValueError('Invalid evidence cutoff')
    except (ValueError, OverflowError):
        raise HTTPException(422, 'เลือกเวลาที่ระบบรู้ข้อมูลเป็น ISO พร้อมเขตเวลา ไม่เกินปัจจุบัน') from None
    return end


@router.get('')
def read_frames(days: int = Query(7, ge=1, le=366), as_of: str | None = Query(None, max_length=40),
                offset: int = Query(0, ge=0, le=1000000), limit: int = Query(20, ge=1, le=100),
                settings: Settings = Depends(get_settings)):
    end = cutoff(as_of)
    result = CommunityStore(settings).call('POST', '/rest/v1/rpc/cme_gfs_read', json={
        'p_start': (end - timedelta(days=days)).isoformat(), 'p_as_of': end.isoformat(),
        'p_offset': offset, 'p_limit': limit})
    return {**result, 'days': days, 'as_of': end.isoformat(), 'offset': offset, 'limit': limit,
            'next_offset': offset + limit if offset + limit < result['total'] else None,
            'measurement_kind': 'model', 'scope': 'frames_first_stored_in_window',
            'notes': ['เริ่มเก็บจากวันที่เปิดคลังนี้ ไม่มีการอ้างว่ามี GFS ย้อนหลังครบ 180 วัน',
                      'เลือกช่วงตามเวลาที่ระบบเก็บไฟล์ครั้งแรก เวลาที่แบบจำลองแทนอาจอยู่ในอนาคต',
                      'เก็บไฟล์ไม่ซ้ำและเก็บ revision ที่เปลี่ยน ไม่ใช่หลักฐานว่าต้นทางทำงานครบทุกชั่วโมง',
                      'ค่าแบบจำลองตามกริด ไม่ใช่ค่าตรวจวัดในป่าหรือผลรับรองความแม่นยำ']}


@router.get('/{frame_id}')
def read_frame(frame_id: str, as_of: str | None = Query(None, max_length=40), settings: Settings = Depends(get_settings)):
    import re
    if not re.fullmatch(r'[a-f0-9]{64}', frame_id):
        raise HTTPException(422, 'รหัสรอบแบบจำลองไม่ถูกต้อง')
    result = CommunityStore(settings).call('POST', '/rest/v1/rpc/cme_gfs_frame', json={
        'p_id': frame_id, 'p_as_of': cutoff(as_of).isoformat()})
    if not result:
        raise HTTPException(404, 'ยังไม่มีรอบนี้ในคลังก่อนเวลาที่เลือก')
    return result
