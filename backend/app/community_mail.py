"""Opt-in email delivery with a persistent outbox and verified Resend callbacks.

Reference contracts:
https://resend.com/docs/api-reference/emails/send-email
https://resend.com/docs/dashboard/emails/idempotency-keys
https://docs.svix.com/receiving/verifying-payloads/how-manual
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.community_store import CommunityStore

log = logging.getLogger(__name__)
ICT = timezone(timedelta(hours=7))
STATUS = {'pending': 'รอตรวจสอบ', 'confirmed': 'ยืนยันเหตุ', 'coordinating': 'กำลังประสาน',
          'controlled': 'ควบคุมได้', 'closed': 'ปิดเหตุ', 'cancelled': 'ยกเลิกเหตุ'}


def parse_time(value):
    try:
        date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return date if date.tzinfo else None
    except (ValueError, TypeError):
        return None


def stamp(value):
    date = parse_time(value)
    return date.astimezone(ICT).strftime('%d/%m/%Y %H:%M น. (ไทย)') if date else 'ยังไม่ระบุเวลา'


def point_in_boundary(latitude: float, longitude: float, geometry: dict | None) -> bool:
    def ring_contains(ring):
        inside = False
        if not ring:
            return False
        previous = ring[-1]
        for current in ring:
            x, y = current[:2]
            px, py = previous[:2]
            if (y > latitude) != (py > latitude) and longitude < (px-x)*(latitude-y)/(py-y)+x:
                inside = not inside
            previous = current
        return inside
    if not geometry:
        return False
    polygons = [geometry['coordinates']] if geometry.get('type') == 'Polygon' else geometry.get('coordinates', []) if geometry.get('type') == 'MultiPolygon' else []
    return any(rings and ring_contains(rings[0]) and not any(ring_contains(r) for r in rings[1:]) for rings in polygons)


def next_delivery(preferences: dict, now: datetime) -> datetime:
    if not preferences.get('quiet_enabled'):
        return now
    local = now.astimezone(ICT)
    start, end = preferences.get('quiet_start', 21), preferences.get('quiet_end', 7)
    if start == end:
        return now
    quiet = start <= local.hour < end if start < end else local.hour >= start or local.hour < end
    if not quiet:
        return now
    release = local.replace(hour=end, minute=0, second=0, microsecond=0)
    if release <= local:
        release += timedelta(days=1)
    return release.astimezone(timezone.utc)


def email_body(store, title, paragraphs, *, incident_id=None):
    origin = store.settings.community_site_url.rstrip('/')
    url = origin + '/#community' + ('/incident/' + str(incident_id) if incident_id else '')
    content = ''.join('<p>' + html.escape(str(p)) + '</p>' for p in paragraphs)
    return f'''<html lang="th"><body style="font-family:Arial,sans-serif;color:#172d24;line-height:1.65;max-width:620px;margin:24px auto;padding:20px">
      <h1 style="font-size:22px;color:#14743a">{html.escape(title)}</h1>{content}
      <p><a href="{html.escape(url, quote=True)}">เปิดข้อมูลพื้นที่และประวัติใน ChiangMaiEyes</a></p>
      <hr><p style="font-size:13px">ข้อมูลดาวเทียมยังต้องตรวจสอบภาคสนาม การรับประสานในระบบไม่ใช่การแต่งตั้งผู้สั่งการตามกฎหมาย</p>
      <p style="font-size:13px">ปรับหรือหยุดรับอีเมลได้ในหน้า “ป่าของฉัน” → การแจ้งเตือน</p>
      <p style="font-size:13px">ที่มา: <a href="https://firms.modaps.eosdis.nasa.gov/">NASA FIRMS</a> ·
        <a href="https://dnp.gistda.or.th/">GISTDA</a> · ขอบเขต RECOFTC 677 แห่ง</p>
      </body></html>'''


def queue_test_email(store: CommunityStore, user: dict):
    recipient = user['email'] if store.settings.community_email_enabled else store.settings.community_email_test_recipient
    if not recipient:
        raise HTTPException(503, 'ยังไม่ได้กำหนดอีเมลรับทดสอบ')
    rows = store.insert('cme_email_outbox', {
        'dedup_key': 'test/' + user['id'] + '/' + str(uuid4()), 'user_id': user['id'], 'category': 'test',
        'recipient': recipient, 'subject': 'ทดสอบระบบอีเมล ChiangMaiEyes',
        'body_html': email_body(store, 'ทดสอบระบบอีเมลสำเร็จ', [
            'นี่เป็นอีเมลทดสอบการเชื่อมต่อ Resend ตามคำขอของผู้ดูแล ไม่ใช่การแจ้งเหตุไฟป่า',
            'เวลาที่สร้างข้อความ: ' + stamp(datetime.now(timezone.utc).isoformat()),
        ]),
    })
    return rows[0]['id']


def _still_subscribed(store, row):
    users = store.call('GET', '/auth/v1/admin/users/' + row['user_id'])
    if not users.get('email_confirmed_at'):
        return False
    if row['category'] == 'test':
        return bool(store.rows('cme_admins', select='user_id', user_id='eq.' + row['user_id']))
    if users.get('email', '').lower() != row['recipient'].lower():
        return False
    prefs = store.rows('cme_notification_preferences', select='*', user_id='eq.' + row['user_id'])
    field = 'daily_enabled' if row['category'] == 'daily' else 'events_enabled'
    return bool(prefs and prefs[0].get(field) and store.rows('cme_memberships', select='id',
        user_id='eq.' + row['user_id'], forest_id='eq.' + row['forest_id'], status='eq.approved'))


def process_outbox(store: CommunityStore, limit=2, only_id=None):
    settings = store.settings
    if not settings.resend_api_key or not (settings.community_email_enabled or settings.community_email_test_recipient):
        return {'provider_accepted': 0, 'failed': 0, 'suppressed': 0, 'email_mode': 'unavailable'}
    rows = store.call('POST', '/rest/v1/rpc/cme_claim_one_email' if only_id else '/rest/v1/rpc/cme_claim_emails',
                      json={'p_id': only_id} if only_id else {'p_limit': limit})
    result = {'provider_accepted': 0, 'failed': 0, 'suppressed': 0,
              'email_mode': 'live' if settings.community_email_enabled else 'test'}
    for row in rows:
        now = datetime.now(timezone.utc)
        try:
            permitted = settings.community_email_enabled or row['recipient'].lower() == settings.community_email_test_recipient.lower()
            if not permitted or not _still_subscribed(store, row):
                store.patch('cme_email_outbox', row['id'], {'status': 'suppressed', 'lease_until': None,
                                                          'last_error': 'Subscription, membership or sender eligibility changed'})
                result['suppressed'] += 1
                continue
            preferences = store.rows('cme_notification_preferences', select='*', user_id='eq.' + row['user_id'])
            release = next_delivery(preferences[0] if preferences else {}, now) if row['category'] != 'test' else now
            if release > now:
                # Quiet-hours checks occur before delivery, including retries.
                store.patch('cme_email_outbox', row['id'], {'status': 'pending', 'available_at': release.isoformat(),
                    'attempts': max(0, row['attempts']-1), 'lease_until': None})
                continue
            first = parse_time(row.get('first_attempt_at'))
            if first and now-first > timedelta(hours=23):
                store.patch('cme_email_outbox', row['id'], {'status': 'failed', 'lease_until': None,
                    'last_error': 'Provider idempotency window elapsed; review delivery before retry'})
                result['failed'] += 1
                continue
            if first is None:
                store.patch('cme_email_outbox',row['id'],{'first_attempt_at':now.isoformat()})
            sender = settings.resend_from_email if settings.community_email_enabled else 'ChiangMaiEyes <onboarding@resend.dev>'
            response = store.client.post('https://api.resend.com/emails', headers={
                'Authorization': 'Bearer ' + settings.resend_api_key,
                'Idempotency-Key': 'cme/' + row['id'],
            }, json={'from': sender, 'to': [row['recipient']], 'subject': row['subject'], 'html': row['body_html']}, timeout=8.0)
            if response.status_code >= 400:
                if response.status_code not in (408, 429) and response.status_code < 500:
                    store.patch('cme_email_outbox', row['id'], {'status': 'failed', 'lease_until': None,
                        'last_error': 'Resend HTTP ' + str(response.status_code) + '; sender or payload needs correction'})
                    result['failed'] += 1
                    continue
                # Provider response bodies may contain personal data. Store only the status.
                raise ValueError('Resend HTTP ' + str(response.status_code))
            provider_id = response.json().get('id')
            if not provider_id:
                raise ValueError('Resend did not return a message identifier')
            store.patch('cme_email_outbox', row['id'], {'status': 'sent', 'provider_id': provider_id,
                'sent_at': now.isoformat(), 'lease_until': None, 'last_error': None, 'delivery_status': 'provider_accepted'})
            result['provider_accepted'] += 1
        except (httpx.HTTPError, HTTPException, ValueError) as error:
            code = str(error) if isinstance(error, ValueError) else 'Delivery interrupted; retry with the same idempotency key'
            failed = row['attempts'] >= 5
            store.patch('cme_email_outbox', row['id'], {'status': 'failed' if failed else 'pending',
                'available_at': (now + timedelta(minutes=min(30, 2 ** row['attempts']))).isoformat(),
                'lease_until': None, 'last_error': code[:180]})
            result['failed'] += 1
    return result


def queue_incident_events(store: CommunityStore, now: datetime):
    since = (now-timedelta(hours=24)).isoformat()
    memberships = store.rows('cme_memberships', select='user_id,forest_id', status='eq.approved')
    preferences = {p['user_id']: p for p in store.rows('cme_notification_preferences', select='*', events_enabled='eq.true')}
    users = {}
    events = store.rows('cme_incident_events', select='*', created_at='gte.' + since, order='created_at.asc', limit='500')
    incidents = {i['id']: i for i in store.rows('cme_incidents', select='*', updated_at='gte.' + since, limit='500')}
    forests = {f['forest_id']: f for f in store.rows('cme_forests', select='forest_id,name')}
    partners = store.rows('cme_incident_partners', select='incident_id,forest_id,status')
    count = 0
    for event in events:
        incident = incidents.get(event['incident_id'])
        if not incident or event['kind'] not in ('created', 'status', 'partner_invited', 'partner_accepted', 'partner_declined', 'coordination'):
            continue
        scopes = {incident['forest_id']} | {p['forest_id'] for p in partners if p['incident_id']==incident['id'] and p['status'] in ('invited','accepted')}
        for membership in memberships:
            uid = membership['user_id']
            if membership['forest_id'] not in scopes or uid not in preferences:
                continue
            if uid not in users:
                users[uid] = store.call('GET', '/auth/v1/admin/users/' + uid)
            user = users[uid]
            if not user.get('email_confirmed_at') or not user.get('email'):
                continue
            if not store.settings.community_email_enabled and user['email'].lower() != (store.settings.community_email_test_recipient or '').lower():
                continue
            title = 'อัปเดตการประสานเหตุ: ' + forests[incident['forest_id']]['name']
            body = email_body(store, title, [
                'สถานะในระบบ: ' + STATUS.get(event.get('status_to') or incident['status'], 'อัปเดตการประสานงาน'),
                'เวลาที่พบเหตุ: ' + stamp(incident['observed_at']),
                'เวลาบันทึกความเปลี่ยนแปลง: ' + stamp(event['created_at']),
                'ข้อมูลจากรายงานชุมชน เปิดประวัติเพื่อดูผลการตรวจสอบและผู้รับประสาน',
            ], incident_id=incident['id'])
            inserted = store.insert('cme_email_outbox', {'dedup_key': f"incident/{event['id']}/{uid}/{membership['forest_id']}",
                'user_id': uid, 'forest_id': membership['forest_id'], 'category': 'incident', 'recipient': user['email'],
                'subject': title, 'body_html': body, 'available_at': next_delivery(preferences[uid], now).isoformat()}, dedup=True)
            count += len(inserted or [])
    return count


def queue_environment(store: CommunityStore, dashboard, now: datetime):
    from app.providers.community_forest_provider import _official_forests
    forests = {f.forest_id: f for f in _official_forests}
    members = store.rows('cme_memberships', select='user_id,forest_id', status='eq.approved')
    prefs = {p['user_id']: p for p in store.rows('cme_notification_preferences', select='*')}
    by_forest = {m['forest_id'] for m in members if prefs.get(m['user_id'], {}).get('events_enabled')}
    quality = dashboard.data_quality.get('hotspots')
    source_ready = quality is not None and not quality.is_stale and quality.source_mode in ('LIVE','SNAPSHOT')
    queued = 0
    if source_ready:
        for forest_id in by_forest:
            forest = forests.get(forest_id)
            if not forest:
                continue
            observations = []
            for h in dashboard.hotspots.items:
                observed = parse_time(h.detected_at)
                if not observed or not timedelta(0) <= now-observed <= timedelta(hours=24):
                    continue
                if point_in_boundary(h.latitude,h.longitude,forest.boundary):
                    key = hashlib.sha256(f'{h.latitude:.4f},{h.longitude:.4f}/{observed.isoformat()}'.encode()).hexdigest()
                    observations.append({'event_key': key, 'observed_at': observed.isoformat()})
            if observations:
                title = 'พบข้อมูลจุดความร้อนในพื้นที่: ' + forest.name
                body = email_body(store, title, [
                    f'มีจุดความร้อนจากดาวเทียม {len(observations)} จุดในขอบเขตป่า จากข้อมูล 24 ชั่วโมงที่ระบบได้รับ',
                    'จุดความร้อนยังไม่ใช่เหตุไฟที่ยืนยันแล้ว กรุณาตรวจสอบข้อมูลและประสานผู้รับผิดชอบ',
                    'ตรวจพบล่าสุด: ' + stamp(max(o['observed_at'] for o in observations)),
                    'แหล่งข้อมูล: ' + dashboard.hotspots.source,
                    'เวลาของชุดข้อมูล: ' + stamp(dashboard.hotspots.latest_update),
                ])
                queued += store.call('POST','/rest/v1/rpc/cme_enqueue_hotspots',json={'p_forest':forest_id,'p_observations':observations,'p_subject':title,'p_html':body})
    if now.astimezone(ICT).hour < 8:
        return queued
    users = {}
    for member in members:
        preference = prefs.get(member['user_id'],{})
        forest = forests.get(member['forest_id'])
        if not preference.get('daily_enabled') or not forest:
            continue
        uid = member['user_id']
        if uid not in users:
            users[uid] = store.call('GET','/auth/v1/admin/users/'+uid)
        user = users[uid]
        if not user.get('email_confirmed_at') or not user.get('email'):
            continue
        if not store.settings.community_email_enabled and user['email'].lower() != (store.settings.community_email_test_recipient or '').lower():
            continue
        stations = [s for s in dashboard.pm25.stations if s.pm25 is not None and point_in_boundary(s.latitude,s.longitude,forest.boundary)]
        pm_text = ('ฝุ่นรอบปัจจุบันเฉลี่ยจากสถานีในพื้นที่: '+str(round(sum(s.pm25 for s in stations)/len(stations),1))+' µg/m³') if stations else 'ยังไม่มีค่าฝุ่นจากสถานีในขอบเขตป่านี้ ไม่ใช้ค่าเฉลี่ยจังหวัดแทน'
        title = 'สรุปประจำวัน: '+forest.name
        body = email_body(store,title,[pm_text,'เวลาของชุดข้อมูลฝุ่น: '+stamp(dashboard.pm25.latest_update),
            'ตรวจสอบจุดความร้อน ลม และเวลารายชุดในหน้าเว็บก่อนตัดสินใจ',
            'สรุปสร้างเมื่อ: '+stamp(now.isoformat())])
        inserted = store.insert('cme_email_outbox',{'dedup_key':f"daily/{now.astimezone(ICT).date()}/{member['forest_id']}/{uid}",
            'user_id':uid,'forest_id':member['forest_id'],'category':'daily','recipient':user['email'],'subject':title,'body_html':body,
            'available_at':next_delivery(preference,now).isoformat()},dedup=True)
        queued += len(inserted or [])
    return queued


def claim_job(store: CommunityStore, source):
    now = datetime.now(timezone.utc)
    job_key = 'community/'+str(int(now.timestamp())//300)
    claimed = store.call('POST','/rest/v1/rpc/cme_claim_job',json={'p_key':job_key,'p_source':source})
    return job_key if claimed else None


def run_jobs(store: CommunityStore, dashboard=None, *, source='manual', claimed_key=None):
    if not (store.settings.community_email_enabled or store.settings.community_email_test_recipient):
        return {'queued':0,'provider_accepted':0,'email_mode':'unavailable'}
    now = datetime.now(timezone.utc)
    job_key = claimed_key or claim_job(store,source)
    if not job_key:
        return {'queued':0,'provider_accepted':0,'already_checked':True}
    def finish(data):
        store.call('PATCH','/rest/v1/cme_job_runs',params={'job_key':'eq.'+job_key},json=data)
    try:
        # Every successful interval includes environmental checks. A manual
        # check must not reserve the interval and exclude the dashboard data.
        if dashboard is None:
            from app.services import get_dashboard
            dashboard = get_dashboard(store.settings)
        queued = queue_incident_events(store,now) + queue_environment(store,dashboard,now)
        result = {'queued':queued,**process_outbox(store)}
        finish({'completed_at':datetime.now(timezone.utc).isoformat(),
                'run_status':'completed','lease_until':None,'summary':result,'last_error':None})
        return result
    except Exception:
        # Never persist exception text: it can contain tokens or private data.
        try:
            finish({'run_status':'failed','lease_until':None,'last_error':'worker_interrupted'})
        except Exception:
            pass  # Expiring lease permits recovery if the database is offline.
        raise


def background_jobs(settings, dashboard=None, source='dashboard', claimed_key=None):
    try:
        run_jobs(CommunityStore(settings),dashboard,source=source,claimed_key=claimed_key)
    except Exception:
        # No private payload, token or provider response is written to public logs.
        log.warning('Community email worker did not finish; persistent outbox will retry')


def verify_webhook(payload: bytes, headers: dict, secret: str, *, now=None):
    try:
        message_id, timestamp = headers['svix-id'], headers['svix-timestamp']
        if len(message_id)>200 or len(headers['svix-signature'])>2048 or abs((now or time.time())-int(timestamp))>300:
            raise ValueError()
        key = base64.b64decode(secret.removeprefix('whsec_'), validate=True)
        expected = base64.b64encode(hmac.new(key,(message_id+'.'+timestamp+'.').encode()+payload,hashlib.sha256).digest()).decode()
        if not any(part.startswith('v1,') and hmac.compare_digest(part[3:],expected) for part in headers['svix-signature'].split()):
            raise ValueError()
        return json.loads(payload)
    except (KeyError, ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(400,'Invalid webhook signature') from None


def handle_webhook(store, payload, headers):
    data = verify_webhook(payload,headers,store.settings.resend_webhook_secret)
    status = {'email.delivered':'delivered','email.bounced':'bounced','email.complained':'complained','email.failed':'failed'}.get(data.get('type'))
    if not status or not isinstance(data.get('data',{}).get('email_id'),str):
        return {'processed':False}
    processed = store.call('POST','/rest/v1/rpc/cme_receive_delivery',json={
        'p_receipt':headers['svix-id'],'p_provider_id':data['data']['email_id'],'p_status':status})
    return {'processed':processed}
