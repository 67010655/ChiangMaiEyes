import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import community_line as line
from app.community import router
from app.config import Settings, get_settings

SECRET = 'fixture-channel-secret'
LINE_USER = 'U' + '0' * 31 + 'a'


def settings(**extra):
    return Settings(supabase_url='https://example.supabase.co', supabase_service_role_key='fixture',
                    line_channel_secret=SECRET, line_channel_access_token='fixture-token', **extra)


def sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


class LineStore:
    def __init__(self, status=200, body=None, headers=None, linked=True, approved=True, admin=False, category='hotspot'):
        self.settings = settings()
        self.calls, self.patches, self.inserts, self.sent = [], [], [], []
        self.linked, self.approved, self.admin = linked, approved, admin
        self.row = {'id': 'row-1', 'user_id': 'user-1', 'forest_id': 'forest-A', 'category': category,
                    'message': 'fixture', 'attempts': 1, 'first_attempt_at': None, 'retry_key': '0f8fad5b-d9cb-469f-a165-70867728950e'}
        def transport(request):
            self.sent.append(request)
            return httpx.Response(status, json=body or {}, headers=headers or {})
        self.client = httpx.Client(transport=httpx.MockTransport(transport))
    def call(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path.endswith('cme_claim_line'):
            return [self.row]
        if path.endswith('cme_line_redeem'):
            return 'linked' if kwargs['json']['p_code_hash'] == hashlib.sha256(b'CME-ABCD2345').hexdigest() else 'invalid'
        return None
    def rows(self, table, **kwargs):
        if table == 'cme_line_links':
            return [{'line_user_id': LINE_USER, 'user_id': 'user-1', 'linked_at': '2026-10-19T00:00:00Z'}] if self.linked else []
        if table == 'cme_memberships':
            return [{'id': 'm'}] if self.approved else []
        if table == 'cme_admins':
            return [{'user_id': 'user-1'}] if self.admin else []
        if table == 'cme_notification_preferences':
            return []
        raise AssertionError(table)
    def insert(self, table, row, **kwargs):
        self.inserts.append((table, row))
        return [{'id': 'new-row', **row}]
    def patch(self, table, row_id, data):
        self.patches.append(data)


def test_signature_must_match_the_raw_body():
    body = b'{"destination":"x","events":[]}'
    assert line.verify_signature(body, sign(body), SECRET) == {'destination': 'x', 'events': []}
    for bad in (None, '', sign(body + b' ')):
        with pytest.raises(HTTPException):
            line.verify_signature(body, bad, SECRET)


def test_console_verify_request_with_no_events_returns_ok():
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings()
    body = b'{"destination":"Uxxx","events":[]}'
    client = TestClient(app)
    assert client.post('/api/community/line-webhook', content=body, headers={'x-line-signature': sign(body)}).json() == {'processed': 0}
    assert client.post('/api/community/line-webhook', content=body, headers={'x-line-signature': 'forged'}).status_code == 400


def test_webhook_is_closed_until_line_is_configured():
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_url='https://example.supabase.co', supabase_service_role_key='fixture')
    assert TestClient(app).post('/api/community/line-webhook', content=b'{}').status_code == 503


def test_link_code_is_long_single_use_and_prefills_the_chat():
    store = LineStore()
    now = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
    result = line.new_link_code(store, {'id': 'user-1'}, now)
    assert line.CODE_PATTERN.fullmatch(result['code'])
    table, row = store.inserts[-1]
    assert table == 'cme_line_link_codes' and row['code_hash'] == hashlib.sha256(result['code'].encode()).hexdigest()
    assert result['code'] not in json.dumps(row)
    assert row['expires_at'] == '2026-10-19T03:10:00+00:00'
    assert ('DELETE', '/rest/v1/cme_line_link_codes') in [(m, p) for m, p, _ in store.calls]
    assert result['chat_url'].startswith('https://line.me/R/oaMessage/%40241mevgs/?')
    assert unquote(result['chat_url'].split('?', 1)[1]) == 'เชื่อมบัญชี ' + result['code']
    assert result['add_friend_url'] == 'https://line.me/R/ti/p/%40241mevgs'


def test_message_with_code_links_and_replies_for_free():
    store = LineStore()
    event = {'type': 'message', 'replyToken': 'r1', 'source': {'type': 'user', 'userId': LINE_USER},
             'message': {'type': 'text', 'text': 'เชื่อมบัญชี cme-abcd2345'}}
    assert line.handle_event(store, event) == 'linked'
    assert store.sent[-1].url.path == '/v2/bot/message/reply'
    assert 'สำเร็จ' in json.loads(store.sent[-1].content)['messages'][0]['text']
    event['message']['text'] = 'เชื่อมบัญชี CME-ZZZZ2345'
    assert line.handle_event(store, event) == 'invalid'
    assert 'หมดอายุ' in json.loads(store.sent[-1].content)['messages'][0]['text']


def test_group_events_are_ignored_and_unfollow_removes_the_link():
    store = LineStore()
    assert line.handle_event(store, {'type': 'message', 'source': {'type': 'group', 'groupId': 'G1'}}) == 'ignored'
    assert line.handle_event(store, {'type': 'unfollow', 'source': {'type': 'user', 'userId': LINE_USER}}) == 'unlinked'
    assert store.calls[-1][:2] == ('DELETE', '/rest/v1/cme_line_links')
    assert store.calls[-1][2]['params'] == {'line_user_id': 'eq.' + LINE_USER}
    assert not store.sent


def test_push_uses_the_stored_retry_key_and_marks_sent():
    store = LineStore()
    result = line.process_outbox(store)
    assert result['line_accepted'] == 1
    request = store.sent[0]
    assert request.url.path == '/v2/bot/message/push'
    assert request.headers['X-Line-Retry-Key'] == store.row['retry_key']
    assert json.loads(request.content)['to'] == LINE_USER
    assert store.patches[-1]['status'] == 'sent'


def test_push_is_suppressed_when_unlinked_or_membership_revoked():
    for store in (LineStore(linked=False), LineStore(approved=False), LineStore(category='test', admin=False)):
        assert line.process_outbox(store)['line_suppressed'] == 1
        assert not store.sent


def test_monthly_quota_is_terminal_but_rate_limit_retries():
    store = LineStore(status=429, body={'message': 'You have reached your monthly limit.'})
    result = line.process_outbox(store)
    assert result['line_quota_reached'] and store.patches[-1]['status'] == 'failed'
    assert store.patches[-1]['last_error'] == 'LINE monthly message quota reached'
    store = LineStore(status=429, body={'message': 'The API rate limit has been exceeded.'})
    line.process_outbox(store)
    assert store.patches[-1]['status'] == 'pending' and store.patches[-1]['last_error'] == 'LINE HTTP 429'


def test_already_accepted_retry_counts_as_sent_and_bad_token_is_terminal():
    store = LineStore(status=409, headers={'x-line-accepted-request-id': 'req-1'})
    assert line.process_outbox(store)['line_accepted'] == 1
    store = LineStore(status=401)
    line.process_outbox(store)
    assert store.patches[-1]['status'] == 'failed'


def test_nothing_is_sent_without_line_credentials():
    store = LineStore()
    store.settings = Settings(supabase_url='https://example.supabase.co', supabase_service_role_key='fixture')
    assert line.process_outbox(store)['line_mode'] == 'unavailable'
    assert line.linked_users(store) == set()
    assert not store.calls and not store.sent


def test_alert_text_says_hotspot_is_unconfirmed_and_gives_the_hotline():
    text = line.hotspot_text(LineStore(), 'ป่าชุมชนทดสอบ', 2, '2026-10-19T03:00:00+00:00', 'GISTDA', '2026-10-19T03:05:00+00:00')
    assert 'ยังไม่ใช่เหตุไฟที่ยืนยันแล้ว' in text and '1362' in text and '10:00 น.' in text


def test_migration_keeps_line_ids_private_and_queues_both_channels_atomically():
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[2] / 'supabase/migrations/20261019120000_line_alerts.sql').read_text(encoding='utf-8')
    assert 'revoke all on public.cme_line_links,public.cme_line_link_codes,public.cme_line_outbox from public,anon,authenticated' in sql
    assert 'grant select' not in sql
    body = sql.split('create or replace function public.cme_enqueue_hotspots')[1]
    assert body.index('cme_hotspot_seen') < body.index('cme_email_outbox') < body.index('cme_line_outbox')


def test_incident_update_queues_line_for_a_linked_member():
    from app.community_mail import queue_incident_events
    class Store:
        settings = settings()
        inserted = []
        def rows(self, table, **kw):
            return {'cme_memberships': [{'user_id': 'user-1', 'forest_id': 'forest-A'}],
                    'cme_notification_preferences': [], 'cme_line_links': [{'user_id': 'user-1'}],
                    'cme_incident_events': [{'id': 'ev-1', 'incident_id': 'inc-1', 'kind': 'status', 'status_to': 'confirmed', 'created_at': '2026-10-19T03:00:00+00:00'}],
                    'cme_incidents': [{'id': 'inc-1', 'forest_id': 'forest-A', 'status': 'confirmed', 'observed_at': '2026-10-19T02:00:00+00:00'}],
                    'cme_forests': [{'forest_id': 'forest-A', 'name': 'ป่าทดสอบ'}], 'cme_incident_partners': []}[table]
        def insert(self, table, row, **kw):
            self.inserted.append((table, row)); return [row]
    store = Store()
    assert queue_incident_events(store, datetime(2026, 10, 19, 4, tzinfo=timezone.utc)) == 1
    table, row = store.inserted[0]
    assert table == 'cme_line_outbox' and row['dedup_key'] == 'incident/ev-1/user-1/forest-A'
    assert 'ยืนยันเหตุ' in row['message'] and row['message'].endswith('/#community/incident/inc-1')


def test_help_reply_speaks_to_a_linked_rep_or_to_the_public():
    def help_for(linked):
        store = LineStore(linked=linked)
        event = {'type': 'message', 'replyToken': 'r1', 'source': {'type': 'user', 'userId': LINE_USER},
                 'message': {'type': 'text', 'text': 'สวัสดี'}}
        assert line.handle_event(store, event) == 'help'
        return json.loads(store.sent[-1].content)['messages'][0]['text']
    rep, public = help_for(True), help_for(False)
    assert 'ตัวแทนป่าชุมชน' in rep and '/#community' in rep
    assert 'แจ้งเตือนฝุ่น' in public and 'ตัวแทนป่าชุมชน' not in public
    assert '1362' in rep and '1362' in public
    # Both say when the satellites pass, so an empty evening map is not read as no fire.
    assert '13:00–14:30' in rep and '13:00–14:30' in public
    assert '2–5 ชม.' in rep and '3 ชม.' not in public


def test_hotspot_text_lists_what_to_do_next():
    text = line.hotspot_text(LineStore(), 'ป่าชุมชนบ้านทดสอบ', 3, '2026-10-19T03:00:00+00:00', 'GISTDA', '2026-10-19T03:05:00+00:00')
    assert text.startswith('🔥') and 'ในป่าชุมชนบ้านทดสอบ' in text and 'ในป่า ป่า' not in text
    assert '1.' in text and '2.' in text and '3.' in text
