from datetime import datetime, timedelta, timezone

from app import line_dust as d
from app.config import Settings

UID = 'U' + '0' * 32
ICT = timezone(timedelta(hours=7))
NOW = datetime(2026, 3, 10, 9, 30, tzinfo=ICT)


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def aq(value):
    """Hourly CAMS values ending at the current hour (Bangkok)."""
    stop = NOW.replace(minute=0, tzinfo=None)
    times = [(stop - timedelta(hours=h)).isoformat(timespec='minutes') for h in range(30, -6, -1)]
    return Resp({'hourly': {'time': times, 'pm2_5': [value] * len(times)}})


class Store:
    def __init__(self, subs=(), sent=()):
        self.settings = Settings(cache_dir='.', line_channel_secret='s', line_channel_access_token='t', line_dust_alerts_enabled=True)
        self.subs, self.sent, self.calls = list(subs), list(sent), []
    def rows(self, table, **p):
        return self.subs if table == 'cme_line_dust_subs' else self.sent
    def call(self, method, path, **kw):
        self.calls.append((method, path, kw.get('params'), kw.get('json')))
        if method == 'POST' and path.endswith('cme_line_dust_sent'):
            self.sent.append(kw['json'])


def test_commands_are_thai_district_names_or_stop():
    assert d.parse_command('แจ้งเตือนฝุ่น ฝาง') == ('sub', 'ฝาง')
    assert d.parse_command('ฝุ่น อ.ฝาง') == ('sub', 'ฝาง')
    assert d.parse_command('แจ้งเตือนฝุ่น อำเภอเมือง')[0] == 'sub'
    assert d.parse_command('หยุด') == ('stop',)
    assert d.parse_command('แจ้งเตือนฝุ่น ลอนดอน')[0] == 'unknown'
    assert d.parse_command('CME-ABCDEFGH') is None  # rep link codes still go to the old path
    assert len(d.districts()) == 25


def test_24_hour_mean_needs_enough_hours():
    assert d.pm24(18.8, 98.9, now=NOW, get=lambda *a, **k: aq(42)) == 42
    thin = Resp({'hourly': {'time': [NOW.replace(minute=0, tzinfo=None).isoformat()], 'pm2_5': [99]}})
    assert d.pm24(18.8, 98.9, now=NOW, get=lambda *a, **k: thin) is None


def _run(store, value, quota=(1000, 10)):
    pushed = []
    def get(url, **kw):
        if url == d.QUOTA_URL: return Resp({'type': 'limited', 'value': quota[0]})
        if url == d.USED_URL: return Resp({'totalUsage': quota[1]})
        return aq(value)
    def post(url, **kw):
        pushed.append(kw['json']); return Resp({}, 200)
    return d.run_dust_alerts(store, NOW, get=get, post=post), pushed


def test_alerts_only_at_unhealthy_once_per_day_and_say_it_is_a_model():
    store = Store(subs=[{'line_user_id': UID, 'district': 'ฝาง'}])
    out, pushed = _run(store, 30)            # ปานกลาง: no alert
    assert out['dust_sent'] == 0 and not pushed
    out, pushed = _run(store, 52)            # เริ่มมีผลต่อสุขภาพ
    assert out['dust_sent'] == 1
    text = pushed[0]['messages'][0]['text']
    assert 'เริ่มมีผลต่อสุขภาพ' in text and 'แบบจำลอง CAMS' in text and 'หยุด' in text
    store.sent = [{'line_user_id': UID, 'level': 4}]
    out, pushed = _run(store, 55)            # same level, same day: nothing
    assert out['dust_sent'] == 0 and not pushed


def test_keeps_a_quota_reserve_for_forest_alerts():
    store = Store(subs=[{'line_user_id': UID, 'district': 'ฝาง'}])
    out, pushed = _run(store, 80, quota=(300, 300 - d.QUOTA_RESERVE))
    assert not pushed and out['dust_skipped'] == 1


def test_stop_and_unfollow_forget_the_person():
    store = Store()
    assert 'หยุด' in d.handle_text(store, UID, 'หยุด')
    assert store.calls[-1][0] == 'DELETE'
    store.calls.clear(); d.forget(store, UID)
    assert {c[1] for c in store.calls} == {'/rest/v1/cme_line_dust_subs', '/rest/v1/cme_line_dust_sent'}


def test_paused_by_default_stores_nothing_and_sends_nothing():
    store = Store(subs=[{'line_user_id': UID, 'district': 'ฝาง'}])
    store.settings = Settings(cache_dir='.', line_channel_secret='s', line_channel_access_token='t')
    assert store.settings.line_dust_alerts_enabled is False
    reply = d.handle_text(store, UID, 'แจ้งเตือนฝุ่น ฝาง')
    assert 'ยังไม่เปิด' in reply and 'อ.เมือง' in reply
    assert not store.calls  # nothing written
    out, pushed = _run(store, 90)
    assert out.get('dust_mode') == 'paused' and not pushed
    assert 'หยุด' in d.handle_text(store, UID, 'หยุด') and store.calls[-1][0] == 'DELETE'
