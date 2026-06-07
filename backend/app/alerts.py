"""Email proximity alerts for pinned locations.

Users subscribe (via the frontend, with magic-link auth) to a pinned lat/lon +
radius, stored in Supabase (`alert_subscriptions`). After each refresh, this
module checks today's reconciled hotspots against every active subscription and
emails (via Resend) anyone with a new hotspot inside their radius. Sent matches
are recorded in `alert_notifications` so the same fire isn't emailed twice.

This only runs from the Thailand refresh worker (refresh_snapshot.py), not from
the Vercel backend — there's no always-on process to schedule it from there.
Entirely additive: if Supabase/Resend aren't configured, `check_and_send_alerts`
is a no-op and the refresh behaves exactly as before.
"""
import datetime
import logging
import math

import httpx

from app.models import Hotspot, HotspotResponse

logger = logging.getLogger(__name__)

BANGKOK_TZ = datetime.timezone(datetime.timedelta(hours=7))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _supabase_headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _fetch_active_subscriptions(base_url: str, headers: dict[str, str]) -> list[dict]:
    resp = httpx.get(
        f"{base_url}/rest/v1/alert_subscriptions",
        params={"is_active": "eq.true", "select": "*"},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _already_notified(base_url: str, headers: dict[str, str], subscription_id: str, day: str, hotspot: Hotspot) -> bool:
    resp = httpx.get(
        f"{base_url}/rest/v1/alert_notifications",
        params={
            "subscription_id": f"eq.{subscription_id}",
            "hotspot_date": f"eq.{day}",
            "hotspot_lat": f"eq.{hotspot.latitude}",
            "hotspot_lon": f"eq.{hotspot.longitude}",
            "select": "id",
            "limit": "1",
        },
        headers=headers,
        timeout=10.0,
    )
    resp.raise_for_status()
    return bool(resp.json())


def _record_notification(base_url: str, headers: dict[str, str], subscription_id: str, day: str, hotspot: Hotspot) -> None:
    httpx.post(
        f"{base_url}/rest/v1/alert_notifications",
        json={
            "subscription_id": subscription_id,
            "hotspot_lat": hotspot.latitude,
            "hotspot_lon": hotspot.longitude,
            "hotspot_date": day,
        },
        headers=headers,
        timeout=10.0,
    ).raise_for_status()


def _send_alert_email(
    api_key: str,
    from_email: str,
    to_email: str,
    location_name: str,
    radius_km: int,
    matches: list[tuple[Hotspot, float]],
) -> bool:
    rows = "".join(
        f"<li>ห่างออกไป <b>{dist:.1f} กม.</b> · ตำบล/อำเภอ {h.district}"
        f"{f'/{h.subdistrict}' if h.subdistrict else ''} · ความเชื่อมั่น {h.confidence}%"
        f" · ตรวจพบเมื่อ {h.detected_at[:16].replace('T', ' ')} น.</li>"
        for h, dist in matches
    )
    html = f"""
    <div style="font-family: sans-serif; line-height: 1.6;">
      <h2>🔥 พบจุดความร้อนใกล้ {location_name}</h2>
      <p>ระบบตรวจพบจุดความร้อนใหม่ภายในรัศมี {radius_km} กม. จากตำแหน่งที่คุณตั้งแจ้งเตือนไว้:</p>
      <ul>{rows}</ul>
      <p style="color:#666; font-size: 0.85em;">
        ข้อมูลจากดาวเทียม VIIRS/MODIS (NASA FIRMS, GISTDA, กรมป่าไม้) ผ่าน ChiangMaiEyes —
        ระบบนี้แจ้งเตือนแบบ best-effort ไม่ใช่บริการฉุกเฉิน หากพบเหตุไฟไหม้จริงโปรดแจ้ง 199 หรือหน่วยงานท้องถิ่น
      </p>
    </div>
    """
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": f"🔥 พบจุดความร้อน {len(matches)} จุดใกล้ {location_name}",
                "html": html,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — one failed email shouldn't break the run
        logger.warning("Failed to send alert email to %s: %s", to_email, exc)
        return False


def check_and_send_alerts(settings, hotspots: HotspotResponse) -> None:
    """Email subscribers whose pinned radius contains a newly-seen hotspot."""
    if not (settings.supabase_url and settings.supabase_service_role_key and settings.resend_api_key):
        return

    base_url = settings.supabase_url.rstrip("/")
    headers = _supabase_headers(settings.supabase_service_role_key)

    try:
        subscriptions = _fetch_active_subscriptions(base_url, headers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load alert subscriptions: %s", exc)
        return

    if not subscriptions:
        return

    today = datetime.datetime.now(BANGKOK_TZ).date().isoformat()
    todays_hotspots = [h for h in hotspots.items if h.detected_at[:10] == today]
    if not todays_hotspots:
        logger.info("Alerts: no hotspots detected today — nothing to check")
        return

    sent_count = 0
    for sub in subscriptions:
        matches: list[tuple[Hotspot, float]] = []
        for h in todays_hotspots:
            dist = _haversine_km(sub["latitude"], sub["longitude"], h.latitude, h.longitude)
            if dist > sub["radius_km"]:
                continue
            try:
                if _already_notified(base_url, headers, sub["id"], today, h):
                    continue
            except Exception as exc:  # noqa: BLE001 — skip this match rather than spam on dedup failure
                logger.warning("Alert dedup check failed for subscription %s: %s", sub["id"], exc)
                continue
            matches.append((h, dist))

        if not matches:
            continue

        sent = _send_alert_email(
            settings.resend_api_key,
            settings.resend_from_email,
            sub["email"],
            sub["location_name"],
            sub["radius_km"],
            matches,
        )
        if not sent:
            continue

        sent_count += 1
        for h, _dist in matches:
            try:
                _record_notification(base_url, headers, sub["id"], today, h)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not record sent alert (subscription %s): %s", sub["id"], exc)

    if sent_count:
        logger.info("Alerts: sent %d email(s) to subscribers with new nearby hotspots", sent_count)
