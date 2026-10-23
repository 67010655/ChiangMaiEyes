"""The community alert job: queues LINE messages for new hotspots and incident events, runs the
pin reminders and the public dust alerts, and sends the LINE outbox.

Email is not used for alerts. It only carries account messages (confirm address, reset password),
which Supabase Auth sends itself.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from app.community_store import CommunityStore

log = logging.getLogger(__name__)
ICT = timezone(timedelta(hours=7))
STATUS = {'pending': 'เปิดอยู่', 'confirmed': 'ยืนยันเหตุ', 'coordinating': 'กำลังประสาน',
          'controlled': 'ควบคุมได้', 'closed': 'จบงานแล้ว', 'cancelled': 'ไม่ใช่ไฟ'}


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






def alerts_configured(settings) -> bool:
    from app.community_line import enabled
    return enabled(settings)


def queue_incident_events(store: CommunityStore, now: datetime):
    from app.community_line import incident_text, linked_users
    line_users = linked_users(store)
    since = (now-timedelta(hours=24)).isoformat()
    memberships = store.rows('cme_memberships', select='user_id,forest_id', status='eq.approved')
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
            if membership['forest_id'] not in scopes:
                continue
            if event['kind'] == 'created' and event.get('actor_id') == uid:
                continue  # the reporter does not need a message about their own report
            status_text = STATUS.get(event.get('status_to') or incident['status'], 'อัปเดตการประสานงาน')
            if uid not in line_users:
                continue
            inserted = store.insert('cme_line_outbox', {'dedup_key': f"incident/{event['id']}/{uid}/{membership['forest_id']}",
                'user_id': uid, 'forest_id': membership['forest_id'], 'category': 'incident',
                'message': incident_text(store, forests[incident['forest_id']]['name'], status_text,
                                         incident['observed_at'], event['created_at'], incident['id'])}, dedup=True)
            count += len(inserted or [])
    return count


def queue_environment(store: CommunityStore, dashboard, now: datetime):
    from app.providers.community_forest_provider import _official_forests
    forests = {f.forest_id: f for f in _official_forests}
    members = store.rows('cme_memberships', select='user_id,forest_id', status='eq.approved')
    from app.community_line import hotspot_text, linked_users
    line_users = linked_users(store)
    line_forests = {m['forest_id'] for m in members if m['user_id'] in line_users}
    quality = dashboard.data_quality.get('hotspots')
    source_ready = quality is not None and not quality.is_stale and quality.source_mode in ('LIVE','SNAPSHOT')
    queued = 0
    if source_ready:
        for forest_id in line_forests:
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
                line_text = hotspot_text(store, forest.name, len(observations), max(o['observed_at'] for o in observations),
                                         dashboard.hotspots.source, dashboard.hotspots.latest_update)
                queued += store.call('POST','/rest/v1/rpc/cme_enqueue_hotspots',json={'p_forest':forest_id,'p_observations':observations,
                    'p_subject':'','p_html':'','p_line_text':line_text})
    return queued


def claim_job(store: CommunityStore, source):
    now = datetime.now(timezone.utc)
    job_key = 'community/'+str(int(now.timestamp())//300)
    claimed = store.call('POST','/rest/v1/rpc/cme_claim_job',json={'p_key':job_key,'p_source':source})
    return job_key if claimed else None


def run_jobs(store: CommunityStore, dashboard=None, *, source='manual', claimed_key=None):
    if not alerts_configured(store.settings):
        return {'queued':0,'line_mode':'unavailable'}
    now = datetime.now(timezone.utc)
    job_key = claimed_key or claim_job(store,source)
    if not job_key:
        return {'queued':0,'already_checked':True}
    def finish(data):
        store.call('PATCH','/rest/v1/cme_job_runs',params={'job_key':'eq.'+job_key},json=data)
    try:
        # Every successful interval includes environmental checks. A manual
        # check must not reserve the interval and exclude the dashboard data.
        if dashboard is None:
            from app.services import get_dashboard
            dashboard = get_dashboard(store.settings)
        queued = queue_incident_events(store,now) + queue_environment(store,dashboard,now)
        pins = {}
        try:
            from app.incident_pins import run_pin_maintenance
            pins = run_pin_maintenance(store,now)
        except Exception:
            log.warning('Pin reminders and expiry did not run')
        from app.community_line import process_outbox as process_line
        result = {'queued':queued,**pins,**process_line(store)}
        try:
            from app.line_dust import run_dust_alerts
            result.update(run_dust_alerts(store, now))
        except Exception:
            log.warning('Public dust alerts did not run')
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
        log.warning('Community alert worker did not finish; persistent outbox will retry')

