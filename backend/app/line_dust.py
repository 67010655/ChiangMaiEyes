"""Public dust alerts on the LINE Official Account (no website account needed).

People subscribe by chatting "แจ้งเตือนฝุ่น <อำเภอ>" and stop with "หยุด".
There is a PM2.5 station only in Mueang, so every district uses the CAMS
model (Open-Meteo Air Quality) at the district's centre, as a 24-hour mean of
the hourly values - always labelled as a model estimate, never a station
reading. An alert goes out when that mean reaches the PCD level
"เริ่มมีผลต่อสุขภาพ" (> 37.5 µg/m³) or higher, once per person per level per
day, and only while the account's monthly push quota keeps a reserve for the
community-forest alerts.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx

log = logging.getLogger(__name__)
ICT = timezone(timedelta(hours=7))
SITE = 'https://chiangmaieyes.vercel.app'
AQ_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
PUSH_URL = 'https://api.line.me/v2/bot/message/push'
QUOTA_URL = 'https://api.line.me/v2/bot/message/quota'
USED_URL = 'https://api.line.me/v2/bot/message/quota/consumption'
ALERT_LEVEL = 4            # PCD level 4 = เริ่มมีผลต่อสุขภาพ
QUOTA_RESERVE = 50         # messages kept for community-forest alerts
MAX_PER_RUN = 40

# PCD 2566 AQI bands for 24-hour PM2.5 (same table as the website).
LEVELS = [
    (15, 'ดีมาก', ''),
    (25, 'ดี', ''),
    (37.5, 'ปานกลาง', 'ลดกิจกรรมกลางแจ้งที่ใช้แรงมาก กลุ่มเสี่ยงใส่หน้ากากเมื่ออยู่นอกอาคาร'),
    (75, 'เริ่มมีผลต่อสุขภาพ', 'ใส่หน้ากากกันฝุ่นเมื่ออยู่นอกอาคาร ลดกิจกรรมกลางแจ้ง'),
    (float('inf'), 'มีผลต่อสุขภาพ', 'งดกิจกรรมกลางแจ้ง ถ้ามีอาการให้พบแพทย์'),
]

SUB_PATTERN = re.compile(r'^\s*(?:แจ้งเตือน\s*)?ฝุ่น\s+(?:อำเภอ|อ\.)?\s*(.+?)\s*$')
STOP_WORDS = {'หยุด', 'หยุดฝุ่น', 'ยกเลิก', 'ยกเลิกฝุ่น', 'stop'}


def level_of(value: float) -> tuple[int, str, str]:
    for i, (top, label, advice) in enumerate(LEVELS, start=1):
        if value <= top:
            return i, label, advice
    return 5, LEVELS[-1][1], LEVELS[-1][2]


def _ring_centroid(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        f = x0 * y1 - x1 * y0
        a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    if not a:
        n = len(ring) or 1
        return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n
    return cx / (3 * a), cy / (3 * a)


@lru_cache(maxsize=1)
def districts() -> dict[str, tuple[float, float]]:
    """District name (Thai, no prefix) -> (lat, lon) of the largest part's centroid."""
    data = json.loads((Path(__file__).parent / 'data' / 'chiangmai-districts.json').read_text(encoding='utf-8'))
    out = {}
    for f in data['features']:
        name = str(f['properties'].get('amp_th') or '').replace('อำเภอ', '').strip()
        g = f['geometry']
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        ring = max((p[0] for p in polys), key=lambda r: abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))))
        lon, lat = _ring_centroid([tuple(pt[:2]) for pt in ring])
        out[name] = (round(lat, 4), round(lon, 4))
    return out


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


def pm24(lat: float, lon: float, *, now=None, get=httpx.get):
    """24-hour mean of hourly CAMS PM2.5 ending at the current hour, or None."""
    now = (now or datetime.now(timezone.utc)).astimezone(ICT)
    r = get(AQ_URL, params={'latitude': lat, 'longitude': lon, 'hourly': 'pm2_5', 'past_days': 1,
                            'forecast_days': 1, 'timezone': 'Asia/Bangkok'}, timeout=8.0)
    r.raise_for_status()
    h = r.json().get('hourly') or {}
    stop = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    vals = []
    for t, v in zip(h.get('time') or [], h.get('pm2_5') or []):
        try:
            at = datetime.fromisoformat(t)
        except ValueError:
            continue
        if stop - timedelta(hours=24) < at <= stop and isinstance(v, (int, float)):
            vals.append(float(v))
    return round(sum(vals) / len(vals), 1) if len(vals) >= 18 else None


def alert_text(district: str, value: float) -> str:
    lvl, label, advice = level_of(value)
    return '\n'.join([
        f'⚠️ ฝุ่น PM2.5 อ.{district} ระดับ "{label}"',
        f'ค่าเฉลี่ย 24 ชม. ประมาณ {value:.0f} µg/m³',
        'ค่าประมาณจากแบบจำลอง CAMS ไม่ใช่สถานีวัดในอำเภอ',
        f'คำแนะนำ: {advice}' if advice else '',
        f'ดูข้อมูลเพิ่ม: {SITE}',
        'หยุดรับแจ้ง พิมพ์ "หยุด"',
    ]).replace('\n\n', '\n')


def subscribe_reply(district: str, value: float | None) -> str:
    now = ''
    if value is not None:
        _, label, _ = level_of(value)
        now = f'\nตอนนี้ฝุ่นเฉลี่ย 24 ชม. ประมาณ {value:.0f} µg/m³ ระดับ "{label}" (แบบจำลอง CAMS)'
    return (f'รับแจ้งเตือนฝุ่น อ.{district} แล้ว{now}\n'
            'จะแจ้งเมื่อค่าเฉลี่ย 24 ชม. ถึงระดับ "เริ่มมีผลต่อสุขภาพ" ขึ้นไป ไม่เกินวันละครั้งต่อระดับ\n'
            'เปลี่ยนอำเภอ พิมพ์ "แจ้งเตือนฝุ่น ชื่ออำเภอ" · หยุด พิมพ์ "หยุด"')


PAUSED_REPLY = ('ยังไม่เปิดแจ้งเตือนฝุ่นรายอำเภอ เพราะตอนนี้มีสถานีวัดฝุ่นจริงเฉพาะ อ.เมือง\n'
                'เรากำลังเพิ่มสถานีวัดในอำเภออื่น เมื่อพร้อมจะประกาศให้ทราบ ไม่มีการเก็บข้อมูลของคุณ\n'
                'ดูค่าฝุ่นล่าสุด: ' + SITE)


def handle_text(store, line_user: str, text: str, *, get=httpx.get):
    """Return the reply text for a dust command, or None if the text is not one."""
    cmd = parse_command(text)
    if not cmd:
        return None
    if not store.settings.line_dust_alerts_enabled:
        if cmd[0] == 'stop':
            # Nothing new is stored while paused; still honour a stop for anyone subscribed earlier.
            store.call('DELETE', '/rest/v1/cme_line_dust_subs', params={'line_user_id': 'eq.' + line_user})
            return 'หยุดแจ้งเตือนฝุ่นแล้ว ข้อมูลอำเภอที่เลือกถูกลบ'
        return PAUSED_REPLY
    if cmd[0] == 'stop':
        store.call('DELETE', '/rest/v1/cme_line_dust_subs', params={'line_user_id': 'eq.' + line_user})
        return 'หยุดแจ้งเตือนฝุ่นแล้ว ข้อมูลอำเภอที่เลือกถูกลบ\nรับใหม่ได้ พิมพ์ "แจ้งเตือนฝุ่น ชื่ออำเภอ"'
    if cmd[0] == 'unknown':
        return f'ไม่พบอำเภอ "{cmd[1]}" ในเชียงใหม่ ลองพิมพ์ เช่น "แจ้งเตือนฝุ่น ฝาง"'
    district = cmd[1]
    store.call('POST', '/rest/v1/cme_line_dust_subs', params={'on_conflict': 'line_user_id'},
               json={'line_user_id': line_user, 'district': district, 'updated_at': datetime.now(timezone.utc).isoformat()},
               headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})
    value = None
    try:
        lat, lon = districts()[district]
        value = pm24(lat, lon, get=get)
    except Exception:  # the reply still confirms the subscription
        log.info('dust estimate unavailable for reply')
    return subscribe_reply(district, value)


def forget(store, line_user: str):
    store.call('DELETE', '/rest/v1/cme_line_dust_subs', params={'line_user_id': 'eq.' + line_user})
    store.call('DELETE', '/rest/v1/cme_line_dust_sent', params={'line_user_id': 'eq.' + line_user})


def remaining_quota(token: str, *, get=httpx.get):
    """Messages left this month, or None for an unlimited plan / unknown."""
    head = {'Authorization': 'Bearer ' + token}
    q = get(QUOTA_URL, headers=head, timeout=6.0); q.raise_for_status()
    if q.json().get('type') != 'limited':
        return None
    used = get(USED_URL, headers=head, timeout=6.0); used.raise_for_status()
    return int(q.json().get('value', 0)) - int(used.json().get('totalUsage', 0))


def run_dust_alerts(store, now=None, *, get=httpx.get, post=httpx.post) -> dict:
    s = store.settings
    out = {'dust_checked': 0, 'dust_sent': 0, 'dust_skipped': 0}
    if not s.line_dust_alerts_enabled:
        return {**out, 'dust_mode': 'paused'}
    if not (s.line_channel_access_token and s.line_channel_secret):
        return {**out, 'dust_mode': 'unavailable'}
    now = now or datetime.now(timezone.utc)
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
    budget = MAX_PER_RUN
    try:
        left = remaining_quota(s.line_channel_access_token, get=get)
        if left is not None:
            budget = min(budget, max(0, left - QUOTA_RESERVE))
    except Exception:
        return {**out, 'dust_mode': 'quota_unknown'}  # never send blind
    for district, users in by_district.items():
        if district not in districts():
            continue
        try:
            value = pm24(*districts()[district], now=now, get=get)
        except Exception:
            continue
        out['dust_checked'] += 1
        if value is None:
            continue
        lvl = level_of(value)[0]
        if lvl < ALERT_LEVEL:
            continue
        text = alert_text(district, value)
        for uid in users:
            if (uid, lvl) in sent_today:
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
                           json={'line_user_id': uid, 'day': day, 'level': lvl, 'district': district, 'value': value},
                           headers={'Prefer': 'resolution=ignore-duplicates,return=minimal'})
            else:  # blocking the account sends an unfollow event, which forgets them
                out['dust_skipped'] += 1
                if r.status_code == 429:  # quota or rate limit: stop this run
                    budget = 0
    return out
