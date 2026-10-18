"""Private evidence: decode/re-encode images, remove metadata, authorize each read."""
from __future__ import annotations

import io
import warnings
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError

BUCKET = 'cme-incident-evidence'
MAX_BYTES = 4 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 12_000_000


def prepare_photo(raw: bytes) -> bytes:
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413, 'รูปต้องมีขนาดไม่เกิน 4 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 12_000_000:
                    raise HTTPException(400, 'รองรับ JPEG, PNG และ WebP ขนาดไม่เกิน 12 ล้านพิกเซล')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((2400, 2400))
                clean = Image.new('RGB', image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, 'JPEG', quality=85, optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, 'ไฟล์รูปไม่ถูกต้องหรือมีขนาดภาพใหญ่เกินกำหนด') from None


async def upload_photo(incident_id: UUID, request: Request, ctx):
    store, token, _ = ctx
    detail = await run_in_threadpool(store.rpc, 'incident_detail', {'id': str(incident_id)}, token)
    if not detail['can_note']:
        raise HTTPException(403, 'รับร่วมประสานก่อนเพิ่มรูป')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, 'รูปต้องมีขนาดไม่เกิน 4 MB')
    return await run_in_threadpool(persist_photo, bytes(raw), incident_id, ctx)


def persist_photo(raw: bytes, incident_id: UUID, ctx):
    store, token, _ = ctx
    photo = prepare_photo(raw)
    photo_id = str(uuid4())
    path = str(incident_id) + '/' + photo_id + '.jpg'
    endpoint = store.settings.supabase_url.rstrip('/') + '/storage/v1/object/' + BUCKET
    try:
        result = store.client.post(endpoint + '/' + path, headers={**store.headers(), 'Content-Type': 'image/jpeg', 'x-upsert': 'false'}, content=photo)
        if result.status_code >= 400:
            raise HTTPException(503, 'อัปโหลดรูปไม่ได้ กรุณาลองใหม่')
        try:
            return store.call('POST', '/rest/v1/rpc/cme_add_photo', token=token,
                              json={'p_incident': str(incident_id), 'p_photo': photo_id})
        except HTTPException:
            store.client.request('DELETE', endpoint, headers=store.headers(), json={'prefixes': [path]})
            raise
    except httpx.HTTPError:
        raise HTTPException(503, 'การเชื่อมต่อรูปถูกขัดจังหวะ กรุณาลองใหม่') from None


def download_photo(photo_id: UUID, ctx):
    store, token, _ = ctx
    rows = store.call('GET', '/rest/v1/cme_incident_photos', token=token,
                      params={'id': 'eq.' + str(photo_id), 'select': 'object_path', 'limit': '1'})
    if not rows:
        raise HTTPException(404, 'ไม่พบรูปหรือไม่มีสิทธิ์ดู')
    try:
        result = store.client.get(store.settings.supabase_url.rstrip('/') + '/storage/v1/object/authenticated/' + BUCKET + '/' + rows[0]['object_path'], headers=store.headers())
        if result.status_code != 200:
            raise HTTPException(503, 'โหลดรูปไม่ได้ กรุณาลองใหม่')
        return Response(result.content, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    except httpx.HTTPError:
        raise HTTPException(503, 'เชื่อมต่อรูปไม่ได้ กรุณาลองใหม่') from None
