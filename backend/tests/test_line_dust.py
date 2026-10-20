from datetime import datetime, timedelta, timezone

from app import line_dust as d
from app.config import Settings

UID = 'U' + '0' * 32
ICT = timezone(timedelta(hours=7))
NOW = datetime(2026, 3, 10, 9, 30, tzinfo=ICT)
FANG = (19.92, 99.21)   # inside อ.ฝาง
HOD = (18.19, 98.61)    # inside อ.ฮอด


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def waqi(values, *, age_min=20, where=FANG):
    """Fake WAQI: stations 1..n at `where`, PM2.5 sub-index from `values`."""
    t = (NOW - timedelta(minutes=age_min)).isoformat()
    def get(url, params=None, **kw):
        if url == d.BOUNDS_URL:
            return Resp({'status': 'ok', 'data': [{'uid': i + 1, 'lat': where[0], 'lon': where[1], 'aqi': '999',
                                                   'station': {'time': t}} for i in range(len(values))]})
        if url.startswith('https://api.waqi.info/feed/@'):
            uid = int(url.split('@')[1].strip('/'))
            return Resp({'status': 'ok', 'data': {'aqi': 999, 'iaqi': {'pm25': {'v': values[uid - 1]}}, 'time': {'iso': t}}})
        if url == d.QUOTA_URL: return Resp({'type': 'limited', 'value': 1000})
        if url == d.USED_URL: return Resp({'totalUsage': 10})
        raise AssertionError(url)
    return get


class Store:
    def __init__(self, subs=(), enabled=True):
        self.settings = Settings(cache_dir='.', line_channel_secret='s', line_channel_access_token='t',
                                 aqicn_token='k', line_dust_alerts_enabled=enabled)
        self.subs, self.sent, self.state, self.calls = list(subs), [], {}, []
    def rows(self, table, **p):
        if table == 'cme_line_dust_subs': return self.subs
        if table == 'cme_dust_district_state':
            row = self.state.get(p['district'][3:]); return [row] if row else []
        return self.sent
    def call(self, method, path, **kw):
        self.calls.append((method, path, kw.get('params'), kw.get('json')))
        body = kw.get('json') or {}
        if path.endswith('cme_line_dust_sent') and method == 'POST': self.sent.append(body)
        if path.endswith('cme_dust_district_state'):
            key = (kw.get('params') or {}).get('district', 'eq.' + body.get('district', ''))[3:]
            if method == 'POST': self.state[body['district']] = dict(body)
            elif method == 'PATCH': self.state[key].update(body)
            elif method == 'DELETE': self.state.pop(key, None)


def run(store, values, at=NOW, **kw):
    pushed = []
    def post(url, **k): pushed.append(k['json']); return Resp({}, 200)
    return d.run_dust_alerts(store, at, get=waqi(values, **kw), post=post), pushed


def test_categories_are_us_epa_aqi_not_converted():
    assert d.category(100)[1] == 'ปานกลาง'
    assert d.category(101)[1] == 'เริ่มมีผลต่อกลุ่มเสี่ยง'
    assert d.category(151)[1] == 'มีผลต่อสุขภาพ'
    assert d.district_of(*FANG) == 'ฝาง' and d.district_of(*HOD) == 'ฮอด'
    assert d.parse_command('แจ้งเตือนฝุ่น อ.ฝาง') == ('sub', 'ฝาง') and d.parse_command('หยุด') == ('stop',)


def test_district_value_needs_two_fresh_sensors_and_uses_the_pm25_sub_index():
    r = d.district_readings('k', now=NOW, get=waqi([120, 140, 10]))
    assert r == {'ฝาง': {'n': 3, 'median': 120}}  # median of the PM2.5 sub-index; composite 999 ignored
    assert d.district_readings('k', now=NOW, get=waqi([150])) == {}            # one sensor is not enough
    assert d.district_readings('k', now=NOW, get=waqi([150, 150], age_min=200)) == {}  # stale readings


def test_alert_only_after_the_level_holds_an_hour_and_says_where_it_came_from():
    store = Store(subs=[{'line_user_id': UID, 'district': 'ฝาง'}])
    out, pushed = run(store, [130, 120])
    assert out['dust_sent'] == 0 and not pushed            # first sighting: wait
    out, pushed = run(store, [130, 120], at=NOW + timedelta(minutes=30))
    assert not pushed                                      # still under an hour
    out, pushed = run(store, [130, 120], at=NOW + timedelta(minutes=61))
    assert out['dust_sent'] == 1
    text = pushed[0]['messages'][0]['text']
    assert 'เริ่มมีผลต่อกลุ่มเสี่ยง' in text and 'เซนเซอร์ 2 จุด' in text and 'World Air Quality Index Project' in text
    assert 'µg' not in text                                 # never converted
    assert 'value' not in store.sent[0]                     # no reading stored
    out, pushed = run(store, [130, 120], at=NOW + timedelta(minutes=80))
    assert not pushed                                       # same level, same day
    run(store, [40, 50], at=NOW + timedelta(minutes=90))
    assert 'ฝาง' not in store.state                         # back to normal clears our state


def test_dry_run_keeps_only_counts_and_categories():
    store = Store(subs=[{'line_user_id': UID, 'district': 'ฝาง'}], enabled=False)
    out, pushed = run(store, [130, 120])
    assert out['dust_mode'] == 'dry_run' and out['dust_coverage'] == {'ฝาง': [2, 3]} and not pushed
    assert out['dust_diag'] == {'stations': 2, 'fresh': 2}
    out, _ = run(store, [130, 120], age_min=200)
    assert out['dust_diag'] == {'stations': 2, 'fresh': 0, 'stale': 2} and out['dust_coverage'] == {}
    assert not [c for c in store.calls if c[0] != 'GET']    # nothing written while dry


def test_subscribing_needs_enough_sensors_and_stop_always_works():
    store = Store()
    assert 'ยังมีเซนเซอร์' in d.handle_text(store, UID, 'แจ้งเตือนฝุ่น ฝาง', get=waqi([100]), now=NOW)
    assert not store.calls
    reply = d.handle_text(store, UID, 'แจ้งเตือนฝุ่น ฝาง', get=waqi([100, 90]), now=NOW)
    assert 'เซนเซอร์วัดฝุ่น 2 จุด' in reply and store.calls[-1][1] == '/rest/v1/cme_line_dust_subs'
    paused = Store(enabled=False)
    assert 'ยังไม่เปิด' in d.handle_text(paused, UID, 'แจ้งเตือนฝุ่น ฝาง', get=waqi([100, 90]), now=NOW) and not paused.calls
    assert 'หยุด' in d.handle_text(paused, UID, 'หยุด') and paused.calls[-1][0] == 'DELETE'
    paused.calls.clear(); d.forget(paused, UID)
    assert {c[1] for c in paused.calls} == {'/rest/v1/cme_line_dust_subs', '/rest/v1/cme_line_dust_sent'}


def test_coverage_endpoint_sends_counts_only(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.config import get_settings
    s = Settings(cache_dir='.', aqicn_token='k', line_dust_alerts_enabled=True)
    main.app.dependency_overrides[get_settings] = lambda: s
    main._dust_cov.clear()
    monkeypatch.setattr(d, 'coverage', lambda token: {'ฝาง': 3})
    try:
        body = TestClient(main.app).get('/api/dust-alerts/coverage').json()
    finally:
        main.app.dependency_overrides.clear()
    assert body == {'enabled': True, 'min_sensors': 2, 'districts': {'ฝาง': 3}}
