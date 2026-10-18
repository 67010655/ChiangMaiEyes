"""Append-only forecast evidence in a private Supabase Storage bucket.

The public API serves only system-generated forecasts. No client upload route,
credentials, community reports or private research records enter this archive.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from app.config import Settings, get_settings
from app.community_store import CommunityStore

BUCKET = 'cme-forecast-evidence'
ICT = timezone(timedelta(hours=7))
router = APIRouter(prefix='/api/forecast/archive', tags=['Forecast evidence'])
log = logging.getLogger(__name__)
_seen: set[str] = set()
_lock = Lock()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def envelope(payload, kind='primary', *, now=None):
    now = now or datetime.now(timezone.utc)
    body = payload.model_dump(mode='json') if hasattr(payload, 'model_dump') else payload
    # Re-reading the same provider cache must not create another forecast run.
    identity = {k: v for k, v in body.items() if k not in ('generated_at', 'issued_at', 'archive')}
    files = ('predict.py',) if kind == 'primary' else ('pm25_station_forecast.py','data/pm25-station-models.json') if kind == 'station' else ('grid_spread.py','live_spread.py','spread_scenario.py','forecast_terrain.py') if kind == 'grid' else ('live_spread.py', 'spread_scenario.py')
    versions = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in files}
    run_id = hashlib.sha256(canonical({'kind': kind, 'versions': versions, 'payload': identity})).hexdigest()
    return {'schema': 'cme-forecast-evidence-v1', 'run_id': run_id, 'kind': kind,
            'captured_at': now.isoformat(), 'code_sha256': versions,
            'model_initialized_at': None,
            'time_basis': 'System capture time; provider retrieval time is not a model issue time.',
            'forecast': body}, f'{now.astimezone(ICT).date()}/{kind}/{run_id}.json'


def storage_request(settings, method, path, **kwargs):
    store = CommunityStore(settings)
    try:
        return store.client.request(method, settings.supabase_url.rstrip('/') + '/storage/v1/' + path,
                                    headers={**store.headers(), **kwargs.pop('headers', {})}, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(503, 'คลังผลพยากรณ์ยังเชื่อมต่อไม่ได้') from None


def put_once(settings, path, doc):
    raw = canonical(doc)
    if len(raw) > 3_000_000:
        raise ValueError('forecast archive payload too large')
    response = storage_request(settings, 'POST', 'object/' + BUCKET + '/' + path, content=raw,
                               headers={'Content-Type': 'application/json', 'x-upsert': 'false'})
    if response.is_success:
        return 'stored'
    if response.status_code in (400, 409):
        # A collision is accepted only if this exact logical run already exists.
        old = storage_request(settings, 'GET', 'object/authenticated/' + BUCKET + '/' + path)
        if old.is_success and old.json().get('run_id') == doc.get('run_id'):
            return 'already_stored'
    raise HTTPException(503, 'ยังบันทึกผลพยากรณ์ไม่ได้ ผลที่แสดงยังไม่ถือว่าอยู่ในคลัง')


def collect(settings, payload, kind='primary'):
    doc, path = envelope(payload, kind)
    with _lock:
        if path in _seen:
            return {'status': 'already_stored', 'path': path, 'run_id': doc['run_id']}
    status = put_once(settings, path, doc)
    with _lock:
        if len(_seen) > 512:
            _seen.clear()
        _seen.add(path)
    return {'status': status, 'path': path, 'run_id': doc['run_id']}


def collect_background(settings, payload, kind='primary'):
    try:
        collect(settings, payload, kind)
    except Exception:
        log.warning('Forecast evidence was not stored; live forecast remains available')


def capture_hourly(settings):
    """Invoked by the existing minute worker; only the first capture per hour wins.

    The marker is written after durable forecast storage. Failed captures retry
    next minute. A concurrent duplicate may compute twice but cannot overwrite.
    """
    now = datetime.now(timezone.utc)
    key = 'hourly/' + now.strftime('%Y-%m-%dT%H') + '.json'
    try:
        present = storage_request(settings, 'GET', 'object/authenticated/' + BUCKET + '/' + key)
        if present.is_success:
            return
        if present.status_code not in (400, 404):
            return
        from app.services import get_fire_predictions
        prediction = get_fire_predictions(settings)
        if not any(v == 'available' for v in prediction.provider_status.values()):
            return  # Provider outage must not claim a completed hourly capture.
        stored = collect(settings, prediction)
        put_once(settings, key, {**stored, 'captured_at': now.isoformat()})
    except Exception:
        log.warning('Hourly forecast evidence capture did not complete')


def checked_day(value):
    try:
        day = date.fromisoformat(value) if value else datetime.now(ICT).date()
        if day > datetime.now(ICT).date():
            raise ValueError()
        return str(day)
    except ValueError:
        raise HTTPException(422, 'ระบุวันที่ YYYY-MM-DD ไม่เกินวันนี้') from None


@router.get('')
def read_runs(day: str | None = Query(None, max_length=10), kind: str = Query('primary', pattern='^(primary|spread|station|grid)$'),
              offset: int = Query(0, ge=0, le=10000), settings: Settings = Depends(get_settings)):
    day = checked_day(day)
    response = storage_request(settings, 'POST', 'object/list/' + BUCKET,
        json={'prefix': day + '/' + kind, 'limit': 100, 'offset': offset,
              'sortBy': {'column': 'created_at', 'order': 'desc'}})
    if not response.is_success:
        raise HTTPException(503, 'คลังผลพยากรณ์ยังไม่พร้อม')
    rows = response.json()
    return {'day_ict': day, 'kind': kind,
            'runs': [{'run_id': r['name'].removesuffix('.json'), 'first_stored_at': r.get('created_at'),
                      'path': day + '/' + kind + '/' + r['name']} for r in rows if r.get('id')],
            'next_offset': offset + 100 if len(rows) == 100 else None,
            'note': 'ผลที่ระบบเก็บจริงหลังเปิดคลังนี้ ไม่ใช่ผลพยากรณ์ย้อนหลังที่สร้างก่อนเริ่มเก็บ'}


@router.get('/{day}/{kind}/{run_id}')
def read_run(day: str, kind: str, run_id: str, settings: Settings = Depends(get_settings)):
    checked_day(day)
    if kind not in ('primary', 'spread', 'station', 'grid') or not re.fullmatch('[a-f0-9]{64}', run_id):
        raise HTTPException(422, 'รหัสผลพยากรณ์ไม่ถูกต้อง')
    response = storage_request(settings, 'GET', f'object/authenticated/{BUCKET}/{day}/{kind}/{run_id}.json')
    if response.status_code in (400, 404):
        raise HTTPException(404, 'ไม่พบผลพยากรณ์ที่บันทึกไว้')
    if not response.is_success:
        raise HTTPException(503, 'อ่านคลังผลพยากรณ์ไม่ได้')
    return response.json()
