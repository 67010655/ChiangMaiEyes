"""Public dust alerts on the LINE Official Account (no website account needed).

People subscribe by chatting "แจ้งเตือนฝุ่น <อำเภอ>" and stop with "หยุด".

Readings come live from the World Air Quality Index Project (WAQI) sensors in
each district - most are low-cost sensors, unvalidated at publication. We use
each sensor's PM2.5 sub-index (US EPA AQI scale, iaqi.pm25), never the
composite AQI and never converted to µg/m³. A district needs at least two
sensors that reported within the last three hours; its value is their median.

WAQI terms forbid redistributing cached or archived data, so no reading is
stored: only our own state (the district's level and when it was first seen)
and the send log (person, day, level). An alert goes out when the same level
holds on checks at least an hour apart, once per person per level per day,
and only while the LINE monthly quota keeps a reserve for forest alerts.
Off until LINE_DUST_ALERTS_ENABLED is set; until then the job runs dry and
records only sensor counts and categories.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx

log = logging.getLogger(__name__)
ICT = timezone(timedelta(hours=7))
SITE = 'https://chiangmaieyes.vercel.app'
BOUNDS_URL = 'https://api.waqi.info/v2/map/bounds'
FEED_URL = 'https://api.waqi.info/feed/@{uid}/'
PUSH_URL = 'https://api.line.me/v2/bot/message/push'
QUOTA_URL = 'https://api.line.me/v2/bot/message/quota'
USED_URL = 'https://api.line.me/v2/bot/message/quota/consumption'
CREDIT = 'ข้อมูล: World Air Quality Index Project และหน่วยงานเจ้าของสถานี'
MIN_SENSORS = 2
FRESH = timedelta(hours=3)   # WAQI often publishes low-cost sensors 2-3 h late
PERSIST = timedelta(minutes=60)
ALERT_FROM = 3             # US AQI category 3 = 101-150
QUOTA_RESERVE = 50
MAX_PER_RUN = 40

# US EPA AQI categories (the scale WAQI publishes), names in Thai.
CATEGORIES = [
    (50, 'ดี', ''),
    (100, 'ปานกลาง', ''),
    (150, 'เริ่มมีผลต่อกลุ่มเสี่ยง', 'เด็ก ผู้สูงอายุ และผู้มีโรคประจำตัว ควรลดกิจกรรมกลางแจ้ง ใส่หน้ากากกันฝุ่น'),
    (200, 'มีผลต่อสุขภาพ', 'ทุกคนควรลดกิจกรรมกลางแจ้ง ใส่หน้ากากกันฝุ่นเมื่ออยู่นอกอาคาร'),
    (300, 'มีผลต่อสุขภาพมาก', 'งดกิจกรรมกลางแจ้ง ปิดประตูหน้าต่าง ถ้ามีอาการให้พบแพทย์'),
    (float('inf'), 'อันตราย', 'อยู่ในอาคาร งดกิจกรรมกลางแจ้ง ถ้ามีอาการให้พบแพทย์ทันที'),
]

SUB_PATTERN = re.compile(r'^\s*(?:แจ้งเตือน\s*)?ฝุ่น\s+(?:อำเภอ|อ\.)?\s*(.+?)\s*$')
STOP_WORDS = {'หยุด', 'หยุดฝุ่น', 'ยกเลิก', 'ยกเลิกฝุ่น', 'stop'}


def category(aqi: float) -> tuple[int, str, str]:
    for i, (top, label, advice) in enumerate(CATEGORIES, start=1):
        if aqi <= top:
            return i, label, advice
    return len(CATEGORIES), CATEGORIES[-1][1], CATEGORIES[-1][2]


# ---------- districts ----------
def _area(r):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1])))


@lru_cache(maxsize=1)
def district_shapes() -> dict[str, list]:
    data = json.loads((Path(__file__).parent / 'data' / 'chiangmai-districts.json').read_text(encoding='utf-8'))
    out = {}
    for f in data['features']:
        name = str(f['properties'].get('amp_th') or '').replace('อำเภอ', '').strip()
        g = f['geometry']
        out[name] = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
    return out


def districts():
    return district_shapes()


def _inside(lon, lat, ring):
    inside = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > lat) != (y1 > lat) and lon < (x1 - x0) * (lat - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def district_of(lat: float, lon: float) -> str | None:
    for name, polys in district_shapes().items():
        for poly in polys:
            if _inside(lon, lat, [tuple(p[:2]) for p in poly[0]]) and not any(
                    _inside(lon, lat, [tuple(p[:2]) for p in hole]) for hole in poly[1:]):
                return name
    return None


def normalise(name: str) -> str | None:
    key = re.sub(r'\s+', '', str(name or '')).replace('อำเภอ', '').replace('อ.', '')
    for d in districts():
        if re.sub(r'\s+', '', d) == key:
            return d
    if key in ('เมือง', 'เมืองเชียงใหม่'):
        return next((d for d in districts() if d.startswith('เมือง')), None)
    return None


def parse_command(text: str):
    """('stop',) | ('sub', district) | ('unknown', words) | None."""
    t = str(text or '').strip()
    if t.lower() in STOP_WORDS:
        return ('stop',)
    m = SUB_PATTERN.match(t)
    if not m:
        return None
    d = normalise(m.group(1))
    return ('sub', d) if d else ('unknown', m.group(1)[:40])


# ---------- live WAQI readings (never stored) ----------
def _parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None


def sensors(token: str, *, get=httpx.get) -> list[dict]:
    """Stations inside Chiang Mai districts: uid, district, reported time (from the map)."""
    r = get(BOUNDS_URL, params={'latlng': '17.2,97.9,20.2,99.6', 'networks': 'all', 'token': token}, timeout=10.0)
    r.raise_for_status()
    body = r.json()
    if body.get('status') != 'ok':
        raise RuntimeError('waqi bounds not ok')
    out = []
    for s in body.get('data') or []:
        try:
            lat, lon, uid = float(s['lat']), float(s['lon']), int(s['uid'])
        except (KeyError, TypeError, ValueError):
            continue
        d = district_of(lat, lon)
        if d:
            st = s.get('station') or {}
            out.append({'uid': uid, 'district': d, 'time': _parse_time(st.get('time')),
                        'name': str(st.get('name') or 'WAQI ' + str(uid))[:120], 'lat': lat, 'lon': lon})
    return out


def pm25_sub_index(token: str, uid: int, *, get=httpx.get):
    """(PM2.5 AQI sub-index, reported time) from one station feed, or (None, None)."""
    r = get(FEED_URL.format(uid=uid), params={'token': token}, timeout=8.0)
    r.raise_for_status()
    body = r.json()
    if body.get('status') != 'ok':
        return None, None
    d = body.get('data') or {}
    v = ((d.get('iaqi') or {}).get('pm25') or {}).get('v')
    t = _parse_time((d.get('time') or {}).get('iso'))
    return (float(v), t) if isinstance(v, (int, float)) and v >= 0 else (None, t)


def district_readings(token: str, wanted: set[str] | None = None, *, now=None, get=httpx.get, diag: dict | None = None) -> dict:
    """{district: {'n': fresh sensors, 'median': sub-index}} for districts with enough fresh sensors.

    `diag`, if given, receives counts only (never readings) of where stations drop out."""
    now = now or datetime.now(timezone.utc)
    pool = [s for s in sensors(token, get=get) if wanted is None or s['district'] in wanted]
    def one(s):
        try:
            v, t = pm25_sub_index(token, s['uid'], get=get)
        except Exception:
            return 'feed_error'
        if t is None:
            return 'no_time'
        if v is None:
            return 'no_pm25'
        if not (now - FRESH <= t <= now + timedelta(minutes=30)):
            return 'stale'
        return s['district'], v
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, pool))
    got = [x for x in results if isinstance(x, tuple)]
    if diag is not None:
        diag.update({'stations': len(pool), 'fresh': len(got)})
        for x in results:
            if isinstance(x, str):
                diag[x] = diag.get(x, 0) + 1
    by: dict[str, list[float]] = {}
    for d, v in got:
        by.setdefault(d, []).append(v)
    return {d: {'n': len(v), 'median': statistics.median(v)} for d, v in by.items() if len(v) >= MIN_SENSORS}


def live_sensors(token: str, *, now=None, get=httpx.get) -> dict:
    """Live PM2.5 sub-index per sensor and the district median for the map.

    Shown live only (WAQI terms: no archive). Stale sensors are listed but
    never counted in a district median."""
    now = now or datetime.now(timezone.utc)
    pool = sensors(token, get=get)
    def one(s):
        try:
            v, t = pm25_sub_index(token, s['uid'], get=get)
        except Exception:
            return None
        if v is None or t is None:
            return None
        fresh = now - FRESH <= t <= now + timedelta(minutes=30)
        return {'uid': s['uid'], 'name': s['name'], 'lat': s['lat'], 'lon': s['lon'], 'district': s['district'],
                'aqi_pm25': round(v), 'time': t.isoformat(), 'fresh': fresh}
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, pool) if r]
    by: dict[str, list[float]] = {}
    for r in rows:
        if r['fresh']:
            by.setdefault(r['district'], []).append(r['aqi_pm25'])
    districts = {}
    for d, v in by.items():
        if len(v) >= MIN_SENSORS:
            m = statistics.median(v)
            districts[d] = {'n': len(v), 'median': round(m), 'level': category(m)[0]}
        else:
            districts[d] = {'n': len(v), 'median': None, 'level': None}
    return {'status': 'ok', 'retrieved_at': now.isoformat(), 'min_sensors': MIN_SENSORS,
            'fresh_hours': int(FRESH.total_seconds() // 3600), 'scale': 'US EPA AQI (PM2.5 sub-index)',
            'credit': CREDIT, 'sensors': rows, 'districts': districts}


def coverage(token: str, *, now=None, get=httpx.get) -> dict[str, int]:
    """Sensors per district that reported recently (map timestamps only, one request)."""
    now = now or datetime.now(timezone.utc)
    out: dict[str, int] = {}
    for s in sensors(token, get=get):
        if s['time'] and now - FRESH <= s['time'] <= now + timedelta(minutes=30):
            out[s['district']] = out.get(s['district'], 0) + 1
    return out


# ---------- messages ----------
def alert_text(district: str, reading: dict) -> str:
    _, label, advice = category(reading['median'])
    return '\n'.join(x for x in [
        f'⚠️ ฝุ่น PM2.5 อ.{district} ระดับ "{label}"',
        f'ดัชนี AQI ของ PM2.5 ค่ากลาง {reading["median"]:.0f} จากเซนเซอร์ {reading["n"]} จุดในอำเภอ (ค่ารายชั่วโมง ต่อเนื่องอย่างน้อย 1 ชม.)',
        f'คำแนะนำ: {advice}' if advice else '',
        'เกณฑ์ AQI ของ US EPA · เซนเซอร์ส่วนใหญ่เป็นเซนเซอร์ราคาประหยัด ค่าอาจคลาดเคลื่อน',
        CREDIT,
        f'ดูข้อมูลเพิ่ม: {SITE}',
        'หยุดรับแจ้ง พิมพ์ "หยุด"',
    ] if x)


def subscribe_reply(district: str, n: int) -> str:
    return (f'รับแจ้งเตือนฝุ่น อ.{district} แล้ว จากเซนเซอร์วัดฝุ่น {n} จุดในอำเภอ\n'
            'จะแจ้งเมื่อดัชนี AQI ของ PM2.5 ถึงระดับ "เริ่มมีผลต่อกลุ่มเสี่ยง" (101) ขึ้นไป ต่อเนื่องอย่างน้อย 1 ชม. ไม่เกินวันละครั้งต่อระดับ\n'
            f'{CREDIT}\n'
            'เปลี่ยนอำเภอ พิมพ์ "แจ้งเตือนฝุ่น ชื่ออำเภอ" · หยุด พิมพ์ "หยุด"')


PAUSED_REPLY = ('ยังไม่เปิดแจ้งเตือนฝุ่นรายอำเภอ เรากำลังตรวจข้อมูลเซนเซอร์ เมื่อพร้อมจะประกาศให้ทราบ ไม่มีการเก็บข้อมูลของคุณ\n'
                'ดูค่าฝุ่นล่าสุด: ' + SITE)


def handle_text(store, line_user: str, text: str, *, get=httpx.get, now=None):
    """Return the reply text for a dust command, or None if the text is not one."""
    cmd = parse_command(text)
    if not cmd:
        return None
    if cmd[0] == 'stop':
        store.call('DELETE', '/rest/v1/cme_line_dust_subs', params={'line_user_id': 'eq.' + line_user})
        return 'หยุดแจ้งเตือนฝุ่นแล้ว ข้อมูลอำเภอที่เลือกถูกลบ\nรับใหม่ได้ พิมพ์ "แจ้งเตือนฝุ่น ชื่ออำเภอ"'
    s = store.settings
    if not s.line_dust_alerts_enabled or not s.aqicn_token:
        return PAUSED_REPLY
    if cmd[0] == 'unknown':
        return f'ไม่พบอำเภอ "{cmd[1]}" ในเชียงใหม่ ลองพิมพ์ เช่น "แจ้งเตือนฝุ่น ฝาง"'
    district = cmd[1]
    try:
        n = coverage(s.aqicn_token, get=get, now=now).get(district, 0)
    except Exception:
        return 'ตรวจเซนเซอร์ไม่ได้ในตอนนี้ ลองใหม่อีกครั้งภายหลัง'
    if n < MIN_SENSORS:
        return f'อ.{district} ยังมีเซนเซอร์วัดฝุ่นที่ส่งข้อมูลไม่ถึง {MIN_SENSORS} จุด จึงยังแจ้งเตือนไม่ได้\nดูค่าฝุ่นภาพรวม: {SITE}'
    store.call('POST', '/rest/v1/cme_line_dust_subs', params={'on_conflict': 'line_user_id'},
               json={'line_user_id': line_user, 'district': district, 'updated_at': datetime.now(timezone.utc).isoformat()},
               headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})
    return subscribe_reply(district, n)


def forget(store, line_user: str):
    store.call('DELETE', '/rest/v1/cme_line_dust_subs', params={'line_user_id': 'eq.' + line_user})
    store.call('DELETE', '/rest/v1/cme_line_dust_sent', params={'line_user_id': 'eq.' + line_user})


def remaining_quota(token: str, *, get=httpx.get):
    """Messages left this month, or None for an unlimited plan."""
    head = {'Authorization': 'Bearer ' + token}
    q = get(QUOTA_URL, headers=head, timeout=6.0); q.raise_for_status()
    if q.json().get('type') != 'limited':
        return None
    used = get(USED_URL, headers=head, timeout=6.0); used.raise_for_status()
    return int(q.json().get('value', 0)) - int(used.json().get('totalUsage', 0))


# ---------- the 10-minute job ----------
def _held_level(store, district: str, level: int, now: datetime) -> bool:
    """Record our own state for the district; True once the level has held for PERSIST."""
    rows = store.rows('cme_dust_district_state', select='level,first_seen', district='eq.' + district) or []
    if rows and int(rows[0]['level']) == level:
        first = _parse_time(rows[0]['first_seen'])
        store.call('PATCH', '/rest/v1/cme_dust_district_state', params={'district': 'eq.' + district},
                   json={'checked_at': now.isoformat()})
        return bool(first and now - first >= PERSIST)
    store.call('POST', '/rest/v1/cme_dust_district_state', params={'on_conflict': 'district'},
               json={'district': district, 'level': level, 'first_seen': now.isoformat(), 'checked_at': now.isoformat()},
               headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})
    return False


def run_dust_alerts(store, now=None, *, get=httpx.get, post=httpx.post) -> dict:
    s = store.settings
    out = {'dust_checked': 0, 'dust_sent': 0, 'dust_skipped': 0}
    if not s.aqicn_token:
        return {**out, 'dust_mode': 'no_sensor_source'}
    now = now or datetime.now(timezone.utc)
    if not s.line_dust_alerts_enabled:
        # Dry run: verify the feed parses. Only counts and category numbers are kept, no readings.
        try:
            diag: dict = {}
            r = district_readings(s.aqicn_token, now=now, get=get, diag=diag)
        except Exception:
            return {**out, 'dust_mode': 'dry_run_failed'}
        return {**out, 'dust_mode': 'dry_run', 'dust_districts': len(r),
                'dust_diag': diag,
                'dust_coverage': {d: [v['n'], category(v['median'])[0]] for d, v in sorted(r.items())}}
    if not (s.line_channel_access_token and s.line_channel_secret):
        return {**out, 'dust_mode': 'unavailable'}
    day = now.astimezone(ICT).date().isoformat()
    subs = store.rows('cme_line_dust_subs', select='line_user_id,district') or []
    if not subs:
        return out
    store.call('DELETE', '/rest/v1/cme_line_dust_sent',
               params={'day': 'lt.' + (now.astimezone(ICT).date() - timedelta(days=35)).isoformat()})
    sent_today = {(r['line_user_id'], r['level']) for r in
                  (store.rows('cme_line_dust_sent', select='line_user_id,level', day='eq.' + day) or [])}
    by_district: dict[str, list[str]] = {}
    for r in subs:
        by_district.setdefault(r['district'], []).append(r['line_user_id'])
    try:
        readings = district_readings(s.aqicn_token, set(by_district), now=now, get=get)
    except Exception:
        return {**out, 'dust_mode': 'sensors_unavailable'}
    try:
        left = remaining_quota(s.line_channel_access_token, get=get)
    except Exception:
        return {**out, 'dust_mode': 'quota_unknown'}  # never send blind
    budget = MAX_PER_RUN if left is None else min(MAX_PER_RUN, max(0, left - QUOTA_RESERVE))
    for district, users in by_district.items():
        reading = readings.get(district)
        if not reading:
            store.call('DELETE', '/rest/v1/cme_dust_district_state', params={'district': 'eq.' + district})
            continue
        out['dust_checked'] += 1
        level = category(reading['median'])[0]
        if level < ALERT_FROM:
            store.call('DELETE', '/rest/v1/cme_dust_district_state', params={'district': 'eq.' + district})
            continue
        if not _held_level(store, district, level, now):
            continue
        text = alert_text(district, reading)
        for uid in users:
            if (uid, level) in sent_today:
                continue
            if budget <= 0:
                out['dust_skipped'] += 1
                continue
            try:
                r = post(PUSH_URL, headers={'Authorization': 'Bearer ' + s.line_channel_access_token},
                         json={'to': uid, 'messages': [{'type': 'text', 'text': text}]}, timeout=8.0)
            except httpx.HTTPError:
                out['dust_skipped'] += 1
                continue
            if r.status_code == 200:
                budget -= 1
                out['dust_sent'] += 1
                store.call('POST', '/rest/v1/cme_line_dust_sent', params={'on_conflict': 'line_user_id,day,level'},
                           json={'line_user_id': uid, 'day': day, 'level': level, 'district': district},
                           headers={'Prefer': 'resolution=ignore-duplicates,return=minimal'})
            else:  # blocking the account sends an unfollow event, which forgets them
                out['dust_skipped'] += 1
                if r.status_code == 429:  # quota or rate limit: stop this run
                    budget = 0
    return out
