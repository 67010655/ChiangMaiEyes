"""LINE Official Account alerts: one-time-code linking, signed webhook, push outbox.

Reference contracts:
https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/
https://developers.line.biz/en/reference/messaging-api/#send-push-message
https://developers.line.biz/en/docs/messaging-api/retrying-api-request/
https://developers.line.biz/en/docs/messaging-api/using-line-url-scheme/
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.community_mail import next_delivery, parse_time, stamp
from app.community_store import CommunityStore

log = logging.getLogger(__name__)
API = 'https://api.line.me/v2/bot/message/'
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_PATTERN = re.compile(r'CME-([A-HJ-NP-Z2-9]{8})')
CODE_MINUTES = 10
HOTLINE = 'เห็นไฟจริง โทรสายด่วนไฟป่า 1362'
HELP = ('บัญชีนี้ส่งแจ้งเตือนอัตโนมัติ ไม่มีเจ้าหน้าที่ตอบแชท\n'
        'รับแจ้งเตือนฝุ่น พิมพ์ "แจ้งเตือนฝุ่น ชื่ออำเภอ" เช่น "แจ้งเตือนฝุ่น ฝาง" · หยุด พิมพ์ "หยุด"\n'
        'ตัวแทนป่าชุมชน ผูกบัญชีได้จากหน้า "ป่าของฉัน" → การแจ้งเตือน ใน ChiangMaiEyes\n' + HOTLINE)


def enabled(settings) -> bool:
    return bool(settings.line_channel_secret and settings.line_channel_access_token)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def urls(settings, code: str | None = None) -> dict:
    basic = quote(settings.line_basic_id, safe='')
    links = {'add_friend_url': 'https://line.me/R/ti/p/' + basic}
    if code:
        links['chat_url'] = 'https://line.me/R/oaMessage/' + basic + '/?' + quote('เชื่อมบัญชี ' + code, safe='')
    return links


def status(store: CommunityStore, user: dict) -> dict:
    rows = store.rows('cme_line_links', select='linked_at', user_id='eq.' + user['id'])
    return {'available': enabled(store.settings), 'linked': bool(rows), 'linked_at': rows[0]['linked_at'] if rows else None,
            'basic_id': store.settings.line_basic_id, **urls(store.settings)}


def new_link_code(store: CommunityStore, user: dict, now: datetime | None = None) -> dict:
    if not enabled(store.settings):
        raise HTTPException(503, 'ยังไม่ได้เปิดใช้การแจ้งเตือนทาง LINE')
    now = now or datetime.now(timezone.utc)
    # 32^8 codes: guessing one inside its ten-minute window is impractical.
    code = 'CME-' + ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    store.call('DELETE', '/rest/v1/cme_line_link_codes', params={'user_id': 'eq.' + user['id']})
    expires = now + timedelta(minutes=CODE_MINUTES)
    store.insert('cme_line_link_codes', {'code_hash': _hash(code), 'user_id': user['id'], 'expires_at': expires.isoformat()})
    return {'code': code, 'expires_at': expires.isoformat(), **urls(store.settings, code)}


def unlink(store: CommunityStore, user: dict) -> dict:
    store.call('DELETE', '/rest/v1/cme_line_links', params={'user_id': 'eq.' + user['id']})
    store.call('DELETE', '/rest/v1/cme_line_link_codes', params={'user_id': 'eq.' + user['id']})
    return {'linked': False}


def verify_signature(payload: bytes, signature: str | None, secret: str) -> dict:
    expected = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
    if not signature or len(signature) > 200 or not hmac.compare_digest(signature, expected):
        raise HTTPException(400, 'Invalid webhook signature')
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Invalid webhook payload') from None
    if not isinstance(data, dict) or not isinstance(data.get('events', []), list):
        raise HTTPException(400, 'Invalid webhook payload')
    return data


def reply(store: CommunityStore, token: str, text: str):
    # Replies are free and do not use the monthly push quota.
    try:
        store.client.post(API + 'reply', headers={'Authorization': 'Bearer ' + store.settings.line_channel_access_token},
                          json={'replyToken': token, 'messages': [{'type': 'text', 'text': text}]}, timeout=8.0)
    except httpx.HTTPError:
        log.warning('LINE reply was not delivered')


def handle_event(store: CommunityStore, event: dict) -> str:
    source = event.get('source') or {}
    line_user = source.get('userId')
    if source.get('type') != 'user' or not isinstance(line_user, str):
        return 'ignored'
    kind, token = event.get('type'), event.get('replyToken')
    if kind == 'unfollow':
        from app.line_dust import forget
        forget(store, line_user)  # public dust subscription, if any
        store.call('DELETE', '/rest/v1/cme_line_links', params={'line_user_id': 'eq.' + line_user})
        return 'unlinked'
    if kind == 'follow':
        if token:
            reply(store, token, 'ขอบคุณที่เพิ่มเพื่อน ChiangMaiEyes\n' + HELP)
        return 'followed'
    message = event.get('message') or {}
    if kind != 'message' or message.get('type') != 'text':
        return 'ignored'
    from app.line_dust import handle_text
    dust = handle_text(store, line_user, str(message.get('text', '')))
    if dust:
        if token:
            reply(store, token, dust)
        return 'dust'
    match = CODE_PATTERN.search(str(message.get('text', '')).upper())
    if not match:
        if token:
            reply(store, token, HELP)
        return 'help'
    result = store.call('POST', '/rest/v1/rpc/cme_line_redeem',
                        json={'p_code_hash': _hash('CME-' + match.group(1)), 'p_line_user_id': line_user})
    if token:
        reply(store, token, 'ผูกบัญชีกับ ChiangMaiEyes สำเร็จ จะได้รับแจ้งเมื่อพบจุดความร้อนใหม่หรือมีการประสานเหตุในป่าที่ได้รับอนุมัติ\n' + HOTLINE
              if result == 'linked' else 'รหัสไม่ถูกต้องหรือหมดอายุแล้ว (ใช้ได้ 10 นาที ครั้งเดียว) กรุณากดรับรหัสใหม่ในหน้าเว็บ')
    return result


def handle_webhook(store: CommunityStore, payload: bytes, signature: str | None) -> dict:
    data = verify_signature(payload, signature, store.settings.line_channel_secret)
    results = [handle_event(store, e) for e in data.get('events', [])[:50] if isinstance(e, dict)]
    return {'processed': len(results)}


def hotspot_text(store: CommunityStore, forest_name: str, count: int, latest: str, source: str, updated) -> str:
    return '\n'.join([
        f'พบจุดความร้อนจากดาวเทียม {count} จุดในป่า {forest_name}',
        'ตรวจพบล่าสุด: ' + stamp(latest),
        'จุดความร้อนยังไม่ใช่เหตุไฟที่ยืนยันแล้ว กรุณาตรวจสอบและประสานผู้รับผิดชอบ',
        'แหล่งข้อมูล: ' + source + ' · ชุดข้อมูลเวลา ' + stamp(updated),
        'เปิดดู: ' + store.settings.community_site_url.rstrip('/') + '/#community',
        HOTLINE,
    ])[:4000]


def incident_text(store: CommunityStore, forest_name: str, status_text: str, observed, changed, incident_id) -> str:
    return '\n'.join([
        'อัปเดตการประสานเหตุ: ' + forest_name,
        'สถานะในระบบ: ' + status_text,
        'เวลาที่พบเหตุ: ' + stamp(observed),
        'บันทึกเมื่อ: ' + stamp(changed),
        'เปิดดู: ' + store.settings.community_site_url.rstrip('/') + '/#community/incident/' + str(incident_id),
    ])[:4000]


def linked_users(store: CommunityStore) -> set[str]:
    if not enabled(store.settings):
        return set()
    return {r['user_id'] for r in store.rows('cme_line_links', select='user_id')}


def queue_test(store: CommunityStore, user: dict) -> str:
    if not enabled(store.settings):
        raise HTTPException(503, 'ยังไม่ได้เปิดใช้การแจ้งเตือนทาง LINE')
    if not store.rows('cme_line_links', select='user_id', user_id='eq.' + user['id']):
        raise HTTPException(409, 'ผูก LINE กับบัญชีนี้ก่อนส่งข้อความทดสอบ')
    rows = store.insert('cme_line_outbox', {'dedup_key': 'test/' + user['id'] + '/' + secrets.token_hex(8),
        'user_id': user['id'], 'category': 'test',
        'message': 'ทดสอบการแจ้งเตือนทาง LINE จาก ChiangMaiEyes สำเร็จ\nนี่ไม่ใช่การแจ้งเหตุไฟป่า\nสร้างเมื่อ: '
                   + stamp(datetime.now(timezone.utc).isoformat())})
    return rows[0]['id']


def _eligible(store: CommunityStore, row: dict):
    link = store.rows('cme_line_links', select='line_user_id', user_id='eq.' + row['user_id'])
    if not link:
        return None
    if row['category'] == 'test':
        return link[0]['line_user_id'] if store.rows('cme_admins', select='user_id', user_id='eq.' + row['user_id']) else None
    approved = store.rows('cme_memberships', select='id', user_id='eq.' + row['user_id'],
                          forest_id='eq.' + str(row['forest_id']), status='eq.approved')
    return link[0]['line_user_id'] if approved else None


def process_outbox(store: CommunityStore, limit=5) -> dict:
    result = {'line_accepted': 0, 'line_failed': 0, 'line_suppressed': 0}
    if not enabled(store.settings):
        return {**result, 'line_mode': 'unavailable'}
    rows = store.call('POST', '/rest/v1/rpc/cme_claim_line', json={'p_limit': limit})
    for row in rows or []:
        now = datetime.now(timezone.utc)
        try:
            to = _eligible(store, row)
            if not to:
                store.patch('cme_line_outbox', row['id'], {'status': 'suppressed', 'lease_until': None,
                                                          'last_error': 'LINE link or membership changed'})
                result['line_suppressed'] += 1
                continue
            if row['category'] != 'test':
                prefs = store.rows('cme_notification_preferences', select='*', user_id='eq.' + row['user_id'])
                release = next_delivery(prefs[0] if prefs else {}, now)
                if release > now:
                    store.patch('cme_line_outbox', row['id'], {'status': 'pending', 'available_at': release.isoformat(),
                        'attempts': max(0, row['attempts']-1), 'lease_until': None})
                    continue
            first = parse_time(row.get('first_attempt_at'))
            if first and now-first > timedelta(hours=23):
                # The retry key is honoured for 24 hours; past that a resend could duplicate.
                store.patch('cme_line_outbox', row['id'], {'status': 'failed', 'lease_until': None,
                    'last_error': 'Retry window elapsed; review delivery before retry'})
                result['line_failed'] += 1
                continue
            if first is None:
                store.patch('cme_line_outbox', row['id'], {'first_attempt_at': now.isoformat()})
            response = store.client.post(API + 'push', headers={
                'Authorization': 'Bearer ' + store.settings.line_channel_access_token,
                'X-Line-Retry-Key': str(row['retry_key']),
            }, json={'to': to, 'messages': [{'type': 'text', 'text': row['message']}]}, timeout=8.0)
            code = response.status_code
            # 409 with a retry key means LINE already accepted this exact request.
            if code == 200 or (code == 409 and response.headers.get('x-line-accepted-request-id')):
                store.patch('cme_line_outbox', row['id'], {'status': 'sent', 'sent_at': now.isoformat(),
                    'lease_until': None, 'last_error': None})
                result['line_accepted'] += 1
                continue
            if code == 429:
                try:
                    quota = 'monthly limit' in str(response.json().get('message', '')).lower()
                except ValueError:
                    quota = False
                if quota:
                    # Free-plan quota is exhausted; retrying only repeats the refusal.
                    store.patch('cme_line_outbox', row['id'], {'status': 'failed', 'lease_until': None,
                        'last_error': 'LINE monthly message quota reached'})
                    result['line_failed'] += 1
                    result['line_quota_reached'] = True
                    continue
                raise ValueError('LINE HTTP 429')
            if code < 500:
                store.patch('cme_line_outbox', row['id'], {'status': 'failed', 'lease_until': None,
                    'last_error': 'LINE HTTP ' + str(code) + '; token or payload needs correction'})
                result['line_failed'] += 1
                continue
            raise ValueError('LINE HTTP ' + str(code))
        except (httpx.HTTPError, HTTPException, ValueError) as error:
            text = str(error) if isinstance(error, ValueError) else 'Delivery interrupted; retry with the same retry key'
            store.patch('cme_line_outbox', row['id'], {'status': 'failed' if row['attempts'] >= 5 else 'pending',
                'available_at': (now + timedelta(minutes=min(30, 2 ** row['attempts']))).isoformat(),
                'lease_until': None, 'last_error': text[:180]})
            result['line_failed'] += 1
    return {**result, 'line_mode': 'live'}
