from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import incident_pins as pins
from app.community import router, session
from app.config import Settings
from app.models import CommunityForest

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def square(lon, lat, size=0.02):
    """A square forest, `size` degrees on a side (about 2.1 km at this latitude)."""
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]
    return {'type': 'Polygon', 'coordinates': [ring]}


def forest(forest_id, name, lon, lat, quality='ok'):
    return CommunityForest(forest_id=forest_id, name=name, village='v', tambon='t', amphoe='a', latitude=lat + 0.01, longitude=lon + 0.01,
                           boundary=square(lon, lat), boundary_quality=quality)


FORESTS = [
    forest('A', 'ป่าชุมชนบ้านเอ', 98.90, 18.80),
    forest('B', 'ป่าชุมชนบ้านบี', 98.94, 18.80),    # about 2 km east of A
    forest('C', 'ป่าชุมชนบ้านซี', 98.98, 18.80),    # about 6 km east of A
    forest('D', 'ป่าชุมชนบ้านดี', 99.30, 18.80),    # far away
    forest('E', 'ป่าชุมชนบ้านอี', 98.90, 18.70),    # about 9 km south
]
INCIDENT = {'id': 'inc-1', 'forest_id': 'A', 'forest_name': 'ป่าชุมชนบ้านเอ', 'created_by': 'rep-a', 'observation': 'fire',
            'latitude': 18.81, 'longitude': 98.91, 'observed_at': '2026-10-23T14:00:00+07:00', 'created_at': '2026-10-23T14:05:00+07:00',
            'contact_phone': '081-234-5678'}


def test_distance_is_zero_inside_and_measured_to_the_edge_outside():
    geometry = square(98.90, 18.80)
    assert pins.boundary_distance_km(18.81, 98.91, geometry) == 0.0
    km = pins.boundary_distance_km(18.81, 98.95, geometry)  # 0.03 degrees east of the east edge
    assert 3.0 < km < 3.5
    assert pins.boundary_distance_km(18.81, 98.95, None) is None


def test_nearby_list_has_the_reporters_forest_first_the_nearest_three_and_marks_risk():
    rows = pins.nearby_forests(18.81, 98.91, 'A', FORESTS)
    assert [r['forest_id'] for r in rows][:1] == ['A'] and rows[0]['reporter'] is True and rows[0]['km'] == 0
    by_id = {r['forest_id']: r for r in rows}
    assert by_id['B']['risk'] is True and by_id['B']['km'] <= 5     # within 5 km
    assert by_id['C']['risk'] is False                              # nearest three, but beyond 5 km
    assert 'D' not in by_id and 'E' not in by_id                    # not in the nearest three, not at risk
    assert all(r['risk'] is False for r in rows if r['reporter'])


def test_the_reporters_forest_is_listed_even_when_the_fire_is_far_from_it():
    rows = pins.nearby_forests(18.70, 98.91, 'D', FORESTS)
    assert 'D' in {r['forest_id'] for r in rows}


def test_forest_with_a_boundary_to_review_is_measured_from_its_reference_point():
    rows = pins.nearby_forests(18.81, 98.97, 'A', [FORESTS[0], forest('R', 'ป่ารอตรวจ', 98.97, 18.80, quality='needs_review')])
    assert {r['forest_id']: r['method'] for r in rows}['R'] == 'reference'


def test_alert_text_says_who_where_how_far_and_links_to_the_pin():
    store = SimpleNamespace(settings=Settings(community_site_url='https://site.example'))
    row = {'name': 'ป่าชุมชนบ้านบี', 'km': 2.3, 'lat': 18.81, 'lon': 98.95}
    text = pins.pin_alert_text(store, INCIDENT, 'สมชาย', row)
    assert 'ป่าชุมชนบ้านเอ' in text and 'เห็นเปลวไฟ' in text and '2.3 กม.' in text and 'ทิศตะวันตก' in text
    assert 'สมชาย' in text and '081-234-5678' in text and 'โทร 1362' in text
    assert text.endswith('ยังไม่ใช่การยืนยันจากหน่วยงาน') and 'https://site.example/#pin/inc-1' in text


class FakeStore:
    def __init__(self, members, linked, stale=()):
        self.settings = Settings(supabase_url='https://x.supabase.co', supabase_service_role_key='k', line_channel_secret='s',
                                 line_channel_access_token='t', community_site_url='https://site.example')
        self.members, self.linked, self.inserts, self.stale = members, linked, [], list(stale)
        self.expired = []

    def rows(self, table, **kw):
        if table == 'cme_memberships':
            return self.members
        if table == 'cme_line_links':
            return [{'user_id': u} for u in self.linked]
        if table == 'cme_incidents':
            return self.stale
        return []

    def call(self, method, path, **kw):
        if path.startswith('/auth/v1/admin/users/'):
            return {'user_metadata': {'full_name': 'สมชาย'}}
        if path.endswith('cme_expire_incidents'):
            return self.expired
        return None

    def insert(self, table, row, **kw):
        if any(i[1]['dedup_key'] == row['dedup_key'] for i in self.inserts):
            return []
        self.inserts.append((table, row))
        return [row]


def test_line_goes_to_linked_reps_of_forests_within_5_km_once_each():
    rows = pins.nearby_forests(18.81, 98.91, 'A', FORESTS)
    store = FakeStore(members=[
        {'user_id': 'rep-a', 'forest_id': 'A'},       # the reporter: never told about their own report
        {'user_id': 'rep-b1', 'forest_id': 'B'},
        {'user_id': 'rep-b2', 'forest_id': 'B'},      # approved but no LINE linked
        {'user_id': 'rep-c', 'forest_id': 'C'},       # nearest three but beyond 5 km: no message
    ], linked={'rep-a', 'rep-b1', 'rep-c'})
    assert pins.queue_pin_alerts(store, INCIDENT, rows) == 1
    table, row = store.inserts[0]
    assert (table, row['user_id'], row['forest_id'], row['category']) == ('cme_line_outbox', 'rep-b1', 'B', 'incident')
    assert row['dedup_key'] == 'pin/inc-1/rep-b1' and 'ป่าชุมชนบ้านบี' in row['message']
    assert pins.queue_pin_alerts(store, INCIDENT, rows) == 0       # same pin, same person: not twice
    assert len(store.inserts) == 1


def test_a_rep_of_two_forests_at_risk_hears_once_about_the_nearer_one():
    rows = pins.nearby_forests(18.81, 98.935, 'A', FORESTS)          # B is nearer than C
    store = FakeStore(members=[{'user_id': 'rep-bc', 'forest_id': 'C'}, {'user_id': 'rep-bc', 'forest_id': 'B'}], linked={'rep-bc'})
    assert pins.queue_pin_alerts(store, INCIDENT, rows) == 1 and store.inserts[0][1]['forest_id'] == 'B'


def test_no_alerts_when_line_is_not_configured():
    store = FakeStore(members=[{'user_id': 'rep-b', 'forest_id': 'B'}], linked={'rep-b'})
    store.settings = Settings(supabase_url='https://x.supabase.co', supabase_service_role_key='k')
    assert pins.queue_pin_alerts(store, INCIDENT, pins.nearby_forests(18.81, 98.91, 'A', FORESTS)) == 0


def stale(created_ago):
    return {'id': 'inc-' + str(created_ago), 'forest_id': 'A', 'created_by': 'rep-a',
            'created_at': (NOW - created_ago).isoformat()}


def test_reporter_is_reminded_once_per_bangkok_day_between_20_hours_and_3_days():
    store = FakeStore(members=[], linked={'rep-a'}, stale=[stale(timedelta(hours=26)), stale(timedelta(days=3, hours=1))])
    first = pins.run_pin_maintenance(store, NOW)
    assert first['pin_reminders'] == 1                                # the 3-day-old one is not reminded
    key = store.inserts[0][1]['dedup_key']
    assert key == f'pin-reminder/inc-{timedelta(hours=26)}/2026-10-23'                      # one key per incident per Bangkok day
    assert pins.run_pin_maintenance(store, NOW + timedelta(hours=2))['pin_reminders'] == 0   # same day: no second one
    assert pins.run_pin_maintenance(store, NOW + timedelta(days=1))['pin_reminders'] == 1    # next day: one more
    assert 'อย่าลืมปิดเหตุ' in store.inserts[0][1]['message'] and '#community/incident/' in store.inserts[0][1]['message']


def test_reminders_only_go_to_a_reporter_with_line_linked():
    store = FakeStore(members=[], linked=set(), stale=[stale(timedelta(hours=30))])
    assert pins.run_pin_maintenance(store, NOW)['pin_reminders'] == 0


def test_closing_after_3_days_tells_the_reporter_once():
    store = FakeStore(members=[], linked={'rep-a'})
    store.expired = [{'id': 'inc-9', 'forest_id': 'A', 'created_by': 'rep-a'}]
    assert pins.run_pin_maintenance(store, NOW)['pins_expired'] == 1
    assert store.inserts[0][1]['dedup_key'] == 'pin-expired/inc-9' and 'ครบ 3 วัน' in store.inserts[0][1]['message']


def test_routes_pass_the_caller_token_and_keep_the_phone_out_of_the_idempotent_payload():
    calls = []

    class Store:
        settings = Settings(supabase_url='https://x.supabase.co', supabase_service_role_key='k')

        def rpc(self, action, payload, token):
            calls.append(('rpc', action, payload))
            return {'id': payload['id'], 'status': 'pending'}

        def call(self, method, path, **kw):
            calls.append((path.rsplit('/', 1)[-1], kw.get('token'), kw.get('json')))
            return [] if path.endswith('cme_open_pins') else {'status': 'closed'}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session] = lambda: (Store(), 'caller-token', {'id': 'u'})
    body = {'id': '30000000-0000-4000-8000-000000000001', 'forest_id': 'A', 'observation': 'fire', 'latitude': 18.8, 'longitude': 98.9,
            'observed_at': '2026-10-23T14:00:00+07:00', 'description': 'x', 'contact_phone': '081-234-5678'}
    with TestClient(app) as client:
        assert client.post('/api/community/incidents', json=body).status_code == 201
        assert client.post('/api/community/incidents', json={**body, 'contact_phone': 'not a phone'}).status_code == 422
        assert client.get('/api/community/pins').headers['cache-control'] == 'private, no-store'
        assert client.post('/api/community/incidents/30000000-0000-4000-8000-000000000001/close', json={'outcome': 'closed'}).status_code == 200
        assert client.post('/api/community/incidents/30000000-0000-4000-8000-000000000001/close', json={'outcome': 'pending'}).status_code == 422
    assert calls[0] == ('rpc', 'create_incident', {k: v for k, v in body.items() if k != 'contact_phone'} | {'observed_at': calls[0][2]['observed_at']})
    assert ('cme_set_incident_contact', 'caller-token', {'p_id': body['id'], 'p_phone': '081-234-5678'}) in calls
    assert ('cme_open_pins', 'caller-token', {}) in calls
    assert ('cme_close_incident', 'caller-token', {'p_id': body['id'], 'p_outcome': 'closed', 'p_note': ''}) in calls
