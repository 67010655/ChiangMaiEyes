from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

from pydantic import BaseModel, Field

from app.models import WeeklyForestRankingEntry, WeeklyForestScoreBreakdown


SQLITE_SCHEMA = """
CREATE TABLE community_forests (
  id TEXT PRIMARY KEY,
  forest_name TEXT NOT NULL,
  village TEXT NOT NULL,
  tambon TEXT NOT NULL,
  amphoe TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL
);

CREATE TABLE field_activity_reports (
  id TEXT PRIMARY KEY,
  forest_id TEXT NOT NULL REFERENCES community_forests(id),
  village_id TEXT NOT NULL,
  reporter_hash TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  patrol_count INTEGER NOT NULL DEFAULT 0,
  firebreak_km REAL NOT NULL DEFAULT 0,
  fuel_management_rai REAL NOT NULL DEFAULT 0,
  water_points_checked INTEGER NOT NULL DEFAULT 0,
  committee_meeting INTEGER NOT NULL DEFAULT 0,
  budget_used_baht REAL NOT NULL DEFAULT 0,
  community_use_activity INTEGER NOT NULL DEFAULT 0,
  biodiversity_note TEXT NOT NULL DEFAULT '',
  no_burn_agreement INTEGER NOT NULL DEFAULT 0,
  UNIQUE(forest_id, village_id, date(submitted_at))
);

CREATE TABLE weekly_forest_rankings (
  week_id TEXT NOT NULL,
  forest_id TEXT NOT NULL REFERENCES community_forests(id),
  total_score INTEGER NOT NULL,
  management_score INTEGER NOT NULL,
  prevention_score INTEGER NOT NULL,
  utilization_score INTEGER NOT NULL,
  ecological_outcome_score INTEGER NOT NULL,
  report_count INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  calculated_at TEXT NOT NULL,
  PRIMARY KEY (week_id, forest_id)
);
"""


class CommunityForestRecord(BaseModel):
    forest_id: str
    forest_name: str
    village: str
    tambon: str
    amphoe: str
    latitude: float
    longitude: float


class FieldActivityReport(BaseModel):
    report_id: str
    forest_id: str
    village_id: str
    reporter_hash: str
    submitted_at: datetime
    patrol_count: int = Field(default=0, ge=0)
    firebreak_km: float = Field(default=0, ge=0)
    fuel_management_rai: float = Field(default=0, ge=0)
    water_points_checked: int = Field(default=0, ge=0)
    committee_meeting: bool = False
    budget_used_baht: float = Field(default=0, ge=0)
    community_use_activity: bool = False
    biodiversity_note: str = ""
    no_burn_agreement: bool = False


def can_accept_daily_report(
    forest_id: str,
    village_id: str,
    submitted_at: datetime,
    existing_reports: Iterable[FieldActivityReport],
) -> bool:
    submitted_day = submitted_at.date()
    return not any(
        report.forest_id == forest_id
        and report.village_id == village_id
        and report.submitted_at.date() == submitted_day
        for report in existing_reports
    )


def score_daily_report(report: FieldActivityReport) -> WeeklyForestScoreBreakdown:
    management = min(
        25,
        (10 if report.committee_meeting else 0)
        + min(8, int(report.budget_used_baht / 1000))
        + (7 if report.reporter_hash else 0),
    )
    prevention = min(
        35,
        min(12, report.patrol_count * 4)
        + min(12, int(report.firebreak_km * 6))
        + min(8, int(report.fuel_management_rai / 5))
        + min(3, report.water_points_checked),
    )
    utilization = 20 if report.community_use_activity else 6
    ecological_outcome = min(
        20,
        (10 if report.no_burn_agreement else 0)
        + (10 if report.biodiversity_note.strip() else 0),
    )
    return WeeklyForestScoreBreakdown(
        management=management,
        prevention=prevention,
        utilization=utilization,
        ecological_outcome=ecological_outcome,
    )


def sunday_week_id(day: date) -> str:
    start = day - timedelta(days=(day.weekday() + 1) % 7)
    return start.isoformat()


def should_recompute_weekly_rankings(moment: datetime) -> bool:
    """Sunday 23:55-23:59 Bangkok cron window for weekly roll-up jobs."""
    return moment.weekday() == 6 and moment.hour == 23 and moment.minute >= 55


def rolling_7_day_window(moment: datetime) -> tuple[date, date]:
    end = moment.date()
    return end - timedelta(days=6), end


def aggregate_weekly_rankings(
    forests: Iterable[CommunityForestRecord],
    reports: Iterable[FieldActivityReport],
    week_start: date,
) -> list[WeeklyForestRankingEntry]:
    forest_map = {forest.forest_id: forest for forest in forests}
    week_end = week_start + timedelta(days=7)
    totals: dict[str, WeeklyForestScoreBreakdown] = defaultdict(
        lambda: WeeklyForestScoreBreakdown(
            management=0,
            prevention=0,
            utilization=0,
            ecological_outcome=0,
        )
    )
    counts: dict[str, int] = defaultdict(int)
    last_seen: dict[str, str] = {}
    reasons: dict[str, set[str]] = defaultdict(set)

    for report in reports:
        if not (week_start <= report.submitted_at.date() < week_end):
            continue
        if report.forest_id not in forest_map:
            continue
        score = score_daily_report(report)
        current = totals[report.forest_id]
        totals[report.forest_id] = WeeklyForestScoreBreakdown(
            management=current.management + score.management,
            prevention=current.prevention + score.prevention,
            utilization=current.utilization + score.utilization,
            ecological_outcome=current.ecological_outcome + score.ecological_outcome,
        )
        counts[report.forest_id] += 1
        last_seen[report.forest_id] = max(
            last_seen.get(report.forest_id, report.submitted_at.isoformat()),
            report.submitted_at.isoformat(),
        )
        if report.patrol_count:
            reasons[report.forest_id].add("ลาดตระเวน")
        if report.firebreak_km:
            reasons[report.forest_id].add("แนวกันไฟ")
        if report.fuel_management_rai:
            reasons[report.forest_id].add("จัดการเชื้อเพลิง")
        if report.no_burn_agreement:
            reasons[report.forest_id].add("ข้อตกลงงดเผา")

    rows: list[WeeklyForestRankingEntry] = []
    for forest_id, score in totals.items():
        forest = forest_map[forest_id]
        capped = WeeklyForestScoreBreakdown(
            management=min(score.management, 25),
            prevention=min(score.prevention, 35),
            utilization=min(score.utilization, 20),
            ecological_outcome=min(score.ecological_outcome, 20),
        )
        total = (
            capped.management
            + capped.prevention
            + capped.utilization
            + capped.ecological_outcome
        )
        rows.append(
            WeeklyForestRankingEntry(
                forest_id=forest.forest_id,
                forest_name=forest.forest_name,
                village=forest.village,
                tambon=forest.tambon,
                amphoe=forest.amphoe,
                latitude=forest.latitude,
                longitude=forest.longitude,
                total_score=total,
                rank=0,
                report_count=counts[forest_id],
                last_report_at=last_seen.get(forest_id, ""),
                score_breakdown=capped,
                reasons=sorted(reasons[forest_id]),
            )
        )

    rows.sort(key=lambda row: (-row.total_score, row.forest_name))
    for index, row in enumerate(rows, start=1):
        row.rank = index
    return rows
