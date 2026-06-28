"""Build backend/app/data/season_history.json from real NASA FIRMS detections.

This job is for season/YoY analytics. It precomputes expensive historical
grouping so Vercel request-time endpoints do not fetch long FIRMS windows.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.providers.hotspot_provider import BANGKOK_TZ, fetch_hotspot_history_detections
from app.services import read_json, write_json


def _season_label(today: dt.date) -> str:
    # Thai Buddhist Era label for the fire season ending in the current year.
    return str(today.year + 543)


def _empty_rows(days: int, today: dt.date) -> dict[str, dict]:
    earliest = today - dt.timedelta(days=days - 1)
    return {
        (earliest + dt.timedelta(days=i)).isoformat(): {
            "date": (earliest + dt.timedelta(days=i)).isoformat(),
            "count": 0,
            "districts": {},
            "hour_histogram": [0] * 24,
        }
        for i in range(days)
    }


def build_archive(days: int, season_label: str | None = None) -> dict:
    settings = get_settings()
    if not settings.nasa_firms_map_key:
        raise RuntimeError("NASA_FIRMS_MAP_KEY is required to refresh season_history.json")

    today = dt.datetime.now(BANGKOK_TZ).date()
    label = season_label or _season_label(today)
    rows_by_date = _empty_rows(days, today)

    detections = fetch_hotspot_history_detections(settings.nasa_firms_map_key, days=days)
    for item in detections:
        day = str(item["date"])
        if day not in rows_by_date:
            continue
        row = rows_by_date[day]
        district = str(item.get("district") or "ไม่ทราบอำเภอ")
        hour = int(item.get("hour") or 0)
        if 0 <= hour <= 23:
            row["hour_histogram"][hour] += 1
        row["districts"][district] = row["districts"].get(district, 0) + 1
        row["count"] += 1

    now = dt.datetime.now(BANGKOK_TZ).isoformat()
    output = {
        "metadata": {
            "season_label": label,
            "build_date": now,
            "source": "NASA FIRMS VIIRS Area API archive",
            "days": days,
            "note": "Rows are grouped from real in-province FIRMS detections; no district/hour values are fabricated.",
        },
        "seasons": {
            label: list(rows_by_date.values()),
        },
    }

    path = settings.cache_dir / "season_history.json"
    try:
        existing = read_json(settings.cache_dir, "season_history.json")
        existing_seasons = existing.get("seasons") if isinstance(existing.get("seasons"), dict) else {}
        output["seasons"] = {**existing_seasons, **output["seasons"]}
    except Exception:
        pass

    write_json(settings.cache_dir, "season_history.json", output)
    return {"path": str(path), "season_label": label, "days": days, "detections": len(detections)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=150)
    parser.add_argument("--season-label")
    args = parser.parse_args()
    if args.days < 1 or args.days > 180:
        raise SystemExit("--days must be between 1 and 180")

    result = build_archive(args.days, args.season_label)
    print(
        "wrote {path} season={season_label} days={days} detections={detections}".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
