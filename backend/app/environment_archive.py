"""Durable observations, preserving upstream times, gaps and revisions."""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.models import Hotspot
from app.community_store import CommunityStore
from app.community import session
from app.community_mail import point_in_boundary
from app.providers.community_forest_provider import fetch_community_forests
from app.evidence import detection_identity

router = APIRouter(prefix='/api/archive', tags=['Environmental archive'])
ICT = timezone(timedelta(hours=7))
log = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stamp(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('upstream time has no timezone')
    return d


@lru_cache(maxsize=1)
def forest_index():
    index = []
    for f in fetch_community_forests():
        geom = f.boundary
        if not geom or f.boundary_quality == 'needs_review':
            continue
        coords = geom.get('coordinates', [])
        rings = [coords[0]] if geom.get('type') == 'Polygon' and coords else [p[0] for p in coords if p]
        points = [p for r in rings for p in r]
        if points:
            index.append((str(f.forest_id), geom, min(p[1] for p in points), max(p[1] for p in points), min(p[0] for p in points), max(p[0] for p in points)))
    return index


def containing_forests(lat, lon):
    if lat is None or lon is None:
        return []
    return [fid for fid, geom, south, north, west, east in forest_index()
            if south <= lat <= north and west <= lon <= east and point_in_boundary(lat, lon, geom)]


def observation(kind, source, observed_at, payload, retrieved_at, native_id, lat=None, lon=None):
    t = stamp(observed_at)
    if t > stamp(retrieved_at) + timedelta(minutes=5):
        raise ValueError('future observation')
    if lat is not None and (not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise ValueError('invalid location')
    if kind=='hotspot' and lat is not None:
        from app.archive_geography import assign
        payload={**payload,'spatial_assignment':assign(lat,lon)}
    key = (detection_identity(payload, source, lat, lon, observed_at) if kind == 'hotspot'
           else digest([kind, native_id, t.astimezone(timezone.utc).isoformat()]))
    return {'id': digest([key, source, payload]), 'observation_key': key, 'kind': kind,
            'observed_at': t.isoformat(), 'retrieved_at': retrieved_at, 'source': source,
            'latitude': lat, 'longitude': lon, 'forest_ids': containing_forests(lat, lon), 'payload': payload}


def dashboard_batch(dashboard, *, now=None):
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    rows, sources, counts = [], {}, {}
    for kind, data in [('hotspot', dashboard.hotspots), ('pm25', dashboard.pm25), ('weather', dashboard.weather)]:
        quality_key = {'hotspot': 'hotspots', 'pm25': 'pm25', 'weather': 'weather'}[kind]
        quality = dashboard.data_quality.get(quality_key) if dashboard.data_quality else None
        valid = not quality or quality.source_mode not in ('UNAVAILABLE', 'PROTOTYPE')
        if kind == 'pm25' and data.current_pm25 is None:
            valid = False
        sources[kind] = {'source': data.source, 'observed_at': data.latest_update,
                         'available': valid, 'mode': quality.source_mode if quality else 'unclassified'}
        counts[kind] = 0
        if not valid:
            continue
        values = ([part for item in data.items for part in
                   (item.source_observations or [item.model_dump(exclude={'source_observations'})])]
                  if kind == 'hotspot' else data.stations if kind == 'pm25' else [data])
        for item in values:
            try:
                if kind == 'hotspot':
                    item = Hotspot(**item)
                payload = item.model_dump(mode='json')
                t = item.detected_at if kind == 'hotspot' else item.updated_at if kind == 'pm25' else item.latest_update
                lat = item.latitude if kind != 'weather' else item.station_latitude
                lon = item.longitude if kind != 'weather' else item.station_longitude
                # Model weather uses its known grid reference, not a fictional station.
                if kind == 'weather' and (lat is None or lon is None):
                    lat, lon = None, None
                row = observation(kind, item.source if kind in ('hotspot','pm25') else data.source, t, payload, retrieved,
                                  item.id if kind != 'weather' else data.source, lat, lon)
                rows.append(row)
                counts[kind] += 1
            except (ValueError, TypeError, OverflowError):
                sources[kind]['invalid_rows'] = sources[kind].get('invalid_rows', 0) + 1
        if sources[kind].get('invalid_rows'):
            sources[kind]['available'] = False
    available = sum(bool(s['available']) for s in sources.values())
    run = {'run_key': 'environment/' + str(int(now.timestamp()) // 600), 'collected_at': retrieved,
           'mode': 'scheduled', 'status': 'complete' if available == 3 else 'partial' if available else 'unavailable',
           'sources': sources, 'counts': counts}
    return run, rows


def collect_dashboard(settings, dashboard):
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    try:
        store = CommunityStore(settings)
        run, rows = dashboard_batch(dashboard)
        store.call('POST', '/rest/v1/rpc/cme_archive_ingest', json={'p_run': run, 'p_rows': rows})
    except Exception:
        # Provider keys and row bodies must not appear in public logs.
        log.warning('Environmental archive collection did not finish')


def window(days, end=None):
    until = stamp(end) if end else datetime.now(ICT)
    if until > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, 'เลือกข้อมูลย้อนหลังถึงเวลาปัจจุบันเท่านั้น')
    return until - timedelta(days=days), until


@router.get('')
def read_archive(days: int = Query(7, ge=1, le=366), kind: str = Query('all', pattern='^(all|hotspot|pm25|pm25_model|weather)$'),
                 forest_id: str | None = Query(None, max_length=100), end: str | None = Query(None, max_length=40),
                 offset: int = Query(0, ge=0, le=1000000), limit: int = Query(500, ge=1, le=1000),
                 settings: Settings = Depends(get_settings)):
    try:
        start, until = window(days, end)
    except ValueError:
        raise HTTPException(422, 'เวลาต้องเป็น ISO พร้อมเขตเวลา') from None
    if forest_id and forest_id not in {f[0] for f in forest_index()}:
        raise HTTPException(404, 'ไม่พบขอบเขตป่าที่เลือก')
    store = CommunityStore(settings)
    result = store.call('POST', '/rest/v1/rpc/cme_archive_read', json={
        'p_start': start.isoformat(), 'p_end': until.isoformat(), 'p_kind': kind,
        'p_forest': forest_id, 'p_offset': offset, 'p_limit': limit})
    # UTC interval intersects Bangkok dates. Never fill unobserved days with zero.
    first, last = start.astimezone(ICT).date(), until.astimezone(ICT).date()
    known = {str(r['day']) for r in result['daily']}
    gaps = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
            if (first + timedelta(days=i)).isoformat() not in known]
    return {**result, 'start': start.isoformat(), 'end': until.isoformat(), 'days': days,
            'kind': kind, 'forest_id': forest_id, 'offset': offset, 'limit': limit,
            'next_offset': offset + limit if offset + limit < result['total'] else None,
            'days_without_observations': gaps, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'upstream_observations_received', 'interval_minutes': 10,
            'notes': ['เก็บข้อมูลที่ระบบได้รับ ไม่ใช่การสำรวจครบทุกจุดหรือทุกชั่วโมง',
                      'ไม่นำค่าเดิมที่แปลงจาก AQI มาใช้เป็นสถิติความเข้มข้น PM2.5',
                      'วันที่ไม่มีค่าจะเว้นว่าง การไม่พบจุดดาวเทียมไม่ยืนยันว่าไม่มีไฟ',
                      'ค่าเฉลี่ยฝุ่นเป็นค่าเฉลี่ยตัวอย่างที่ได้รับ ไม่ใช่ค่าเฉลี่ย 24 ชั่วโมงตามมาตรฐาน',
                      'ต้นทางแก้ค่าที่เวลาเดิมจะเก็บ revision เดิมไว้ และใช้ revision ล่าสุดในตารางนี้']}


@router.post('/backfill',status_code=202)
def backfill(days: int = Query(30, ge=1, le=180), models: bool = True, ctx=Depends(session)):
    store, token, _ = ctx
    if not store.rpc('me', {}, token)['is_admin']:
        raise HTTPException(403, 'ให้ผู้ดูแลนำเข้าข้อมูลย้อนหลัง')
    from app.archive_jobs import enqueue
    # Fixed calendar window makes retrying an interrupted submission idempotent.
    end=datetime.now(ICT).replace(hour=0,minute=0,second=0,microsecond=0)
    start=end-timedelta(days=days)
    from app.providers.verified_history import BBOX
    job=enqueue(store,start,end,models=models,request_key=f'manual/{end.date()}/{days}/{models}/'+digest(BBOX)[:12])
    return {'job':job,'note':'เข้าคิวแล้ว ปิดหน้านี้ได้ งานจะทำต่อและเก็บผลสำเร็จไว้ ช่องว่างไม่เติมเป็นศูนย์'}


@router.get('/jobs')
def archive_jobs(job_id: str | None = Query(None,max_length=36),ctx=Depends(session)):
    store,token,_=ctx
    if not store.rpc('me',{},token)['is_admin']: raise HTTPException(403,'เฉพาะผู้ดูแล')
    if job_id:
        import uuid
        try: uuid.UUID(job_id)
        except ValueError: raise HTTPException(422,'รหัสงานไม่ถูกต้อง') from None
    return {'jobs':store.call('POST','/rest/v1/rpc/cme_archive_job_status',json={'p_job':job_id})}


@router.post('/jobs/{job_id}/retry')
def retry_archive_job(job_id: str,ctx=Depends(session)):
    store,token,_=ctx
    if not store.rpc('me',{},token)['is_admin']: raise HTTPException(403,'เฉพาะผู้ดูแล')
    import uuid
    try: uuid.UUID(job_id)
    except ValueError: raise HTTPException(422,'รหัสงานไม่ถูกต้อง') from None
    return store.call('POST','/rest/v1/rpc/cme_archive_retry',json={'p_job':job_id})


@router.get('/worker')
def archive_worker(background_tasks: BackgroundTasks, settings: Settings=Depends(get_settings)):
    from app.archive_jobs import work_one
    from app.forecast_archive import capture_hourly
    background_tasks.add_task(capture_hourly, settings)
    return work_one(CommunityStore(settings))
