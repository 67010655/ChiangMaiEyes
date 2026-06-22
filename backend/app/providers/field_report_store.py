"""Supabase-backed store for real community field-report submissions.

Reads/writes the ``field_activity_reports`` table via Supabase's PostgREST API
(httpx — no extra dependency). When Supabase isn't configured the store is
"disabled": reads fall back to the seeded demo reports and writes are rejected
with a clear demo-mode message, so the dashboard keeps working unchanged.
See memory: project-data-provenance (Phase 3).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import httpx

_BANGKOK = timezone(timedelta(hours=7))

from app.config import Settings
from app.weekly_forest_league import FieldActivityReport

logger = logging.getLogger(__name__)

_TABLE = "field_activity_reports"
_TIMEOUT = 15.0


def supabase_enabled(settings: Settings) -> bool:
    return bool(
        getattr(settings, "supabase_url", None)
        and getattr(settings, "supabase_service_role_key", None)
    )


def _rest_url(settings: Settings) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{_TABLE}"


def _headers(settings: Settings, *, write: bool = False) -> dict[str, str]:
    key = settings.supabase_service_role_key
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if write:
        headers["Content-Type"] = "application/json"
        # Don't echo the inserted row back — we only need the status.
        headers["Prefer"] = "return=minimal"
    return headers


def _row_to_report(row: dict) -> FieldActivityReport:
    return FieldActivityReport(
        report_id=str(row.get("id") or row.get("report_id") or ""),
        forest_id=str(row["forest_id"]),
        village_id=str(row["village_id"]),
        reporter_hash=str(row.get("reporter_hash") or ""),
        submitted_at=row["submitted_at"],
        patrol_count=row.get("patrol_count") or 0,
        firebreak_km=row.get("firebreak_km") or 0,
        fuel_management_rai=row.get("fuel_management_rai") or 0,
        water_points_checked=row.get("water_points_checked") or 0,
        committee_meeting=bool(row.get("committee_meeting")),
        budget_used_baht=row.get("budget_used_baht") or 0,
        community_use_activity=bool(row.get("community_use_activity")),
        biodiversity_note=row.get("biodiversity_note") or "",
        no_burn_agreement=bool(row.get("no_burn_agreement")),
    )


def fetch_field_reports(settings: Settings, *, since_days: int = 60) -> list[FieldActivityReport]:
    """Recent reports (default 60 days) ordered newest-first."""
    earliest = (datetime.now().date() - timedelta(days=since_days)).isoformat()
    params = {
        "select": "*",
        "submitted_at": f"gte.{earliest}",
        "order": "submitted_at.desc",
    }
    response = httpx.get(_rest_url(settings), params=params, headers=_headers(settings), timeout=_TIMEOUT)
    response.raise_for_status()
    return [_row_to_report(row) for row in response.json()]


def report_exists_today(settings: Settings, forest_id: str, village_id: str, day: date) -> bool:
    """Best-effort check for the 1-report-per-forest/village/day rule. Uses
    tz-aware Bangkok day bounds so a same-day report stored as +07:00 is not
    mis-bucketed to the previous UTC day. The DB unique index is the
    authoritative backstop (see the 409 handling in submit_field_report)."""
    start = datetime.combine(day, time.min, tzinfo=_BANGKOK)
    end = start + timedelta(days=1)
    # PostgREST range on one column = repeat the key, so pass params as tuples.
    params = [
        ("select", "id"),
        ("forest_id", f"eq.{forest_id}"),
        ("village_id", f"eq.{village_id}"),
        ("submitted_at", f"gte.{start.isoformat()}"),
        ("submitted_at", f"lt.{end.isoformat()}"),
        ("limit", "1"),
    ]
    response = httpx.get(_rest_url(settings), params=params, headers=_headers(settings), timeout=_TIMEOUT)
    response.raise_for_status()
    return len(response.json()) > 0


def insert_field_report(settings: Settings, report: FieldActivityReport) -> None:
    row = {
        "id": report.report_id,
        "forest_id": report.forest_id,
        "village_id": report.village_id,
        "reporter_hash": report.reporter_hash,
        "submitted_at": report.submitted_at.isoformat(),
        "patrol_count": report.patrol_count,
        "firebreak_km": report.firebreak_km,
        "fuel_management_rai": report.fuel_management_rai,
        "water_points_checked": report.water_points_checked,
        "committee_meeting": report.committee_meeting,
        "budget_used_baht": report.budget_used_baht,
        "community_use_activity": report.community_use_activity,
        "biodiversity_note": report.biodiversity_note,
        "no_burn_agreement": report.no_burn_agreement,
    }
    response = httpx.post(
        _rest_url(settings), json=row, headers=_headers(settings, write=True), timeout=_TIMEOUT
    )
    response.raise_for_status()
