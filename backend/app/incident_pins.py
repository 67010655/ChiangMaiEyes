"""Incident pins: which forests are near a reported fire, who is told by LINE, and the
reminder and 3-day close. The site only informs; people coordinate by themselves.

The nearby list is worked out once, when the incident is created, and stored on the
incident. The map popup and the LINE recipients both read that one list.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from app.community_mail import ICT, parse_time, point_in_boundary, stamp
from app.community_store import CommunityStore

log = logging.getLogger(__name__)
RISK_KM = 5.0          # a forest whose boundary is this close to the report is "at risk"
NEAREST = 3            # the popup always lists the nearest forests too
MAX_LISTED = 12        # popup list size
MAX_ALERTED = 10       # forests alerted by LINE for one pin (free LINE plan has a monthly quota)
CANDIDATES = 40        # forests measured against their boundary (nearest by reference point)
OPEN_STATUSES = ('pending', 'confirmed', 'coordinating', 'controlled')
EXPIRY = timedelta(days=3)
FIRST_REMINDER = timedelta(hours=20)
COMPASS = ['เหนือ', 'ตะวันออกเฉียงเหนือ', 'ตะวันออก', 'ตะวันออกเฉียงใต้', 'ใต้', 'ตะวันตกเฉียงใต้', 'ตะวันตก', 'ตะวันตกเฉียงเหนือ']


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(a))


def _polygons(geometry: dict | None):
    if not geometry:
        return []
    if geometry.get('type') == 'Polygon':
        return [geometry['coordinates']]
    return geometry.get('coordinates', []) if geometry.get('type') == 'MultiPolygon' else []


def boundary_distance_km(lat: float, lon: float, geometry: dict | None) -> float | None:
    """0 inside the boundary, else the distance to the nearest edge. Same method as the map."""
    if not geometry:
        return None
    if point_in_boundary(lat, lon, geometry):
        return 0.0
    cos = math.cos(math.radians(lat))
    best = math.inf
    for rings in _polygons(geometry):
        for ring in rings:
            for i in range(1, len(ring)):
                ax, ay = ring[i - 1][:2]
                bx, by = ring[i][:2]
                dx, dy = (bx - ax) * cos, by - ay
                length = dx * dx + dy * dy
                t = max(0.0, min(1.0, ((lon - ax) * cos * dx + (lat - ay) * dy) / length)) if length else 0.0
                best = min(best, haversine_km(lat, lon, ay + t * (by - ay), ax + t * (bx - ax)))
    return None if math.isinf(best) else best


def bearing_text(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
    """Compass direction (Thai) of the second point as seen from the first."""
    y = math.sin(math.radians(to_lon - from_lon)) * math.cos(math.radians(to_lat))
    x = math.cos(math.radians(from_lat)) * math.sin(math.radians(to_lat)) - \
        math.sin(math.radians(from_lat)) * math.cos(math.radians(to_lat)) * math.cos(math.radians(to_lon - from_lon))
    return COMPASS[int(((math.degrees(math.atan2(y, x)) + 360) % 360 + 22.5) // 45) % 8]


def nearby_forests(lat: float, lon: float, own_forest_id: str, forests=None) -> list[dict]:
    """Reporter's forest first, then the 3 nearest and everything within 5 km, nearest first."""
    if forests is None:
        from app.providers.community_forest_provider import _official_forests as forests
    by_reference = sorted(forests, key=lambda f: haversine_km(lat, lon, f.latitude, f.longitude))
    wanted = by_reference[:CANDIDATES]
    own = next((f for f in forests if f.forest_id == own_forest_id), None)
    if own is not None and own not in wanted:
        wanted.append(own)
    rows = []
    for f in wanted:
        km = boundary_distance_km(lat, lon, f.boundary) if f.boundary_quality != 'needs_review' else None
        method = 'boundary'
        if km is None:
            km, method = haversine_km(lat, lon, f.latitude, f.longitude), 'reference'
        rows.append({'forest_id': f.forest_id, 'name': f.name, 'amphoe': f.amphoe, 'km': round(km, 1), 'method': method,
                     'reporter': f.forest_id == own_forest_id, 'risk': f.forest_id != own_forest_id and km <= RISK_KM,
                     'lat': f.latitude, 'lon': f.longitude})
    rows.sort(key=lambda r: (r['km'], r['forest_id']))
    chosen = {r['forest_id'] for r in rows[:NEAREST]} | {r['forest_id'] for r in rows if r['risk']}
    if own_forest_id in {r['forest_id'] for r in rows}:
        chosen.add(own_forest_id)
    return [r for r in rows if r['forest_id'] in chosen][:MAX_LISTED]


def pin_alert_text(store: CommunityStore, incident: dict, reporter_name: str, row: dict) -> str:
    what = 'เปลวไฟ' if incident.get('observation') == 'fire' else 'ควัน'
    direction = bearing_text(row['lat'], row['lon'], incident['latitude'], incident['longitude'])
    lines = [
        f'🚨 มีรายงานไฟใกล้ป่าชุมชนของคุณ',
        f'👁️ ตัวแทน{incident["forest_name"]} เห็น{what}',
        f'📏 อยู่ภายในขอบเขต{row["name"]}' if row['km'] == 0 else f'📏 อยู่ห่างขอบเขต{row["name"]} ประมาณ {row["km"]:.1f} กม. ทางทิศ{direction}ของป่านั้น',
        f'👤 แจ้งโดย {reporter_name} · 🕒 พบเมื่อ {stamp(incident["observed_at"])}',
    ]
    if incident.get('contact_phone'):
        lines.append('☎️ ติดต่อผู้แจ้ง ' + incident['contact_phone'])
    lines += ['',
              '💡 ควรทำ',
              '1. เปิดดูตำแหน่งและรายละเอียดบนแผนที่ (ลิงก์ด้านล่าง)',
              '2. คุยกับผู้แจ้งหรือป่าข้างเคียงเอง ว่าต้องช่วยอะไร',
              '3. ถ้าเห็นไฟหรือควันใกล้ป่าคุณ โทร 1362 (สายด่วนกรมอุทยานฯ แจ้งไฟป่า) ได้เลย',
              '',
              '📍 ' + store.settings.community_site_url.rstrip('/') + '/#pin/' + str(incident['id']),
              'ℹ️ เป็นรายงานจากตัวแทนป่า ยังไม่ใช่การยืนยันจากหน่วยงาน']
    return '\n'.join(lines)[:4000]


def reminder_text(store: CommunityStore, incident: dict, now: datetime) -> str:
    created = parse_time(incident['created_at']) or now
    left = max(timedelta(0), created + EXPIRY - now)
    hours = int(left.total_seconds() // 3600)
    return '\n'.join([
        '⏰ อย่าลืมปิดเหตุที่คุณแจ้ง',
        f'หมุดที่คุณแจ้งไว้เมื่อ {stamp(incident["created_at"])} ยังเปิดอยู่ และจะหายเองในอีกประมาณ {hours // 24} วัน {hours % 24} ชม.',
        '',
        '🧯 ถ้าไฟดับหรือจัดการเสร็จแล้ว กด "จบงาน"',
        '❌ ถ้าไม่ใช่ไฟ กด "ไม่ใช่ไฟ"',
        '',
        '📍 ' + store.settings.community_site_url.rstrip('/') + '/#community/incident/' + str(incident['id']),
    ])[:4000]


def expired_text(store: CommunityStore, incident_id: str) -> str:
    return '\n'.join([
        '📌 ระบบปิดหมุดที่คุณแจ้งให้แล้ว เพราะครบ 3 วัน',
        'ประวัติยังอยู่ในรายการเหตุของป่าคุณ ถ้ายังมีไฟ แจ้งเหตุใหม่ได้',
        '',
        '📋 ' + store.settings.community_site_url.rstrip('/') + '/#community/incident/' + incident_id,
    ])[:4000]


CLOSED_HEAD = {
    'closed': '✅ หมุดไฟใกล้ป่าคุณ จบงานแล้ว',
    'cancelled': '❌ หมุดไฟใกล้ป่าคุณ ถูกบันทึกว่าไม่ใช่ไฟ',
    'expired': '📌 หมุดไฟใกล้ป่าคุณ ถูกปิดอัตโนมัติ (ครบ 3 วัน)',
}
CLOSED_BODY = {
    'closed': 'หมุดนี้ถูกปิดว่าจบงานแล้ว และหายจากแผนที่แล้ว',
    'cancelled': 'หมุดนี้ถูกปิดว่าไม่ใช่ไฟ และหายจากแผนที่แล้ว',
    'expired': 'ไม่มีใครกดจบงานภายใน 3 วัน ระบบจึงปิดให้เอง ไม่ได้แปลว่าไฟดับ',
}


def pin_closed_text(incident: dict, outcome: str) -> str:
    """Short notice to the forests that were told about a pin: it is gone from the map."""
    what = 'เปลวไฟ' if incident.get('observation') == 'fire' else 'ควัน'
    return '\n'.join([
        CLOSED_HEAD[outcome],
        f'👁️ รายงานของตัวแทน{incident.get("forest_name") or "ป่าชุมชน"} ({what} พบเมื่อ {stamp(incident["observed_at"])})',
        CLOSED_BODY[outcome],
        '',
        'ℹ️ ถ้ายังเห็นไฟหรือควันใกล้ป่าคุณ โทร 1362 (สายด่วนกรมอุทยานฯ แจ้งไฟป่า) ได้เลย',
    ])[:4000]


def queue_pin_closed(store: CommunityStore, incident: dict, outcome: str) -> int:
    """Tell everyone who got the new-pin LINE (and still has it) that the pin is closed. The reporter is not told."""
    from app.community_line import enabled
    if not enabled(store.settings) or outcome not in CLOSED_HEAD:
        return 0
    told = store.rows('cme_line_outbox', select='user_id,forest_id,status', dedup_key=f'like.pin/{incident["id"]}/*') or []
    message = pin_closed_text(incident, outcome)
    queued = 0
    for row in told:
        if row.get('status') != 'sent' or row['user_id'] == incident['created_by']:
            continue
        inserted = store.insert('cme_line_outbox', {
            'dedup_key': f'pin-closed/{incident["id"]}/{row["user_id"]}', 'user_id': row['user_id'], 'forest_id': row['forest_id'],
            'category': 'incident', 'message': message}, dedup=True)
        queued += len(inserted or [])
    return queued


def _incident_for_notice(store: CommunityStore, incident_id: str) -> dict | None:
    found = store.rows('cme_incidents', select='id,forest_id,observation,observed_at,created_by,status', id='eq.' + incident_id)
    if not found:
        return None
    forest = store.rows('cme_forests', select='name', forest_id='eq.' + found[0]['forest_id'])
    return {**found[0], 'forest_name': forest[0]['name'] if forest else 'ป่าชุมชน'}


def notify_pin_closed(store: CommunityStore, incident_id: str) -> dict:
    """After the reporter or an admin closes a pin: LINE the forests that were alerted, and send now."""
    incident = _incident_for_notice(store, incident_id)
    if not incident or incident['status'] not in ('closed', 'cancelled'):
        return {'queued': 0}
    queued = queue_pin_closed(store, incident, incident['status'])
    from app.community_line import process_outbox
    return {'queued': queued, **process_outbox(store)}


def save_nearby(store: CommunityStore, incident: dict) -> list[dict]:
    rows = nearby_forests(incident['latitude'], incident['longitude'], incident['forest_id'])
    stored = [{k: v for k, v in r.items() if k not in ('lat', 'lon')} for r in rows]
    store.patch('cme_incidents', incident['id'], {'nearby': stored})
    return rows


def _members_by_forest(store: CommunityStore, forest_ids: list[str]) -> dict[str, list[str]]:
    if not forest_ids:
        return {}
    rows = store.rows('cme_memberships', select='user_id,forest_id', status='eq.approved',
                      forest_id='in.(' + ','.join(f'"{f}"' for f in forest_ids) + ')')
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row['forest_id'], []).append(row['user_id'])
    return result


def queue_pin_alerts(store: CommunityStore, incident: dict, rows: list[dict]) -> int:
    """LINE to reps of forests within 5 km (not the reporter's own forest, not the reporter)."""
    from app.community_line import enabled, linked_users
    if not enabled(store.settings):
        return 0
    risk = [r for r in rows if r['risk']][:MAX_ALERTED]
    members = _members_by_forest(store, [r['forest_id'] for r in risk])
    linked = linked_users(store)
    reporter = store.call('GET', '/auth/v1/admin/users/' + incident['created_by']) or {}
    reporter_name = (reporter.get('user_metadata') or {}).get('full_name') or 'ตัวแทนชุมชน'
    sent_to, queued = set(), 0
    for row in risk:  # nearest first: a rep of two risk forests hears about the nearer one only
        for uid in members.get(row['forest_id'], []):
            if uid in sent_to or uid == incident['created_by'] or uid not in linked:
                continue
            sent_to.add(uid)
            inserted = store.insert('cme_line_outbox', {
                'dedup_key': f'pin/{incident["id"]}/{uid}', 'user_id': uid, 'forest_id': row['forest_id'], 'category': 'incident',
                'message': pin_alert_text(store, incident, reporter_name, row)}, dedup=True)
            queued += len(inserted or [])
    return queued


def notify_new_pin(store: CommunityStore, incident_id: str) -> dict:
    """After an incident is created: store the nearby list, LINE the forests at risk, and send now."""
    found = store.rows('cme_incidents', select='*', id='eq.' + incident_id)
    if not found:
        return {'queued': 0}
    incident = found[0]
    forest = store.rows('cme_forests', select='name', forest_id='eq.' + incident['forest_id'])
    incident['forest_name'] = forest[0]['name'] if forest else 'ป่าชุมชน'
    rows = save_nearby(store, incident)
    queued = queue_pin_alerts(store, incident, rows)
    from app.community_line import process_outbox
    return {'queued': queued, **process_outbox(store)}


def run_pin_maintenance(store: CommunityStore, now: datetime) -> dict:
    """Close pins after 3 days, and remind reporters once per Bangkok day while a pin is open."""
    from app.community_line import enabled, linked_users
    result = {'pins_expired': 0, 'pin_reminders': 0, 'pin_closed_notices': 0}
    expired = store.call('POST', '/rest/v1/rpc/cme_expire_incidents', json={}) or []
    result['pins_expired'] = len(expired)
    if not enabled(store.settings):
        return result
    linked = linked_users(store)
    for item in expired:
        try:
            gone = _incident_for_notice(store, item['id'])
            if gone:
                result['pin_closed_notices'] += queue_pin_closed(store, gone, 'expired')
        except Exception:  # noqa: BLE001 — the reporter notice below must not depend on this
            log.warning('Pin-closed notices did not finish')
        if item['created_by'] in linked:
            store.insert('cme_line_outbox', {'dedup_key': f'pin-expired/{item["id"]}', 'user_id': item['created_by'],
                'forest_id': item['forest_id'], 'category': 'incident', 'message': expired_text(store, item['id'])}, dedup=True)
    old = (now - FIRST_REMINDER).isoformat()
    still_open = store.rows('cme_incidents', select='id,forest_id,created_by,created_at', status='in.(' + ','.join(OPEN_STATUSES) + ')',
                            created_at='lte.' + old, order='created_at.asc', limit='200')
    day = now.astimezone(ICT).strftime('%Y-%m-%d')
    for incident in still_open:
        created = parse_time(incident['created_at'])
        if not created or now - created >= EXPIRY or incident['created_by'] not in linked:
            continue
        inserted = store.insert('cme_line_outbox', {'dedup_key': f'pin-reminder/{incident["id"]}/{day}', 'user_id': incident['created_by'],
            'forest_id': incident['forest_id'], 'category': 'incident', 'message': reminder_text(store, incident, now)}, dedup=True)
        result['pin_reminders'] += len(inserted or [])
    return result
