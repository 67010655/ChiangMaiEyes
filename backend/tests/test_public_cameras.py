from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.public_cameras import STATIONS, camera_directory, fetch_station, parse_snapshot, public_sources

ICT = timezone(timedelta(hours=7))


def test_snapshot_url_and_time_are_allowlisted_and_station_specific():
    image, time = parse_snapshot(
        '<img id="cctvImage" src="cache/P.75/2026/10/cctv_20261010141503_abc123.jpg?t=1791627992">',
        "P.75",
    )
    assert image == "https://appserv.net/cache/P.75/2026/10/cctv_20261010141503_abc123.jpg"
    assert time == "2026-10-10T14:15:03+07:00"


@pytest.mark.parametrize("src", [
    "https://example.org/cache/P.1/2026/10/cctv_20261010141503_abc.jpg",
    "http://127.0.0.1/cache/P.1/2026/10/cctv_20261010141503_abc.jpg",
    "https://appserv.net/cache/P.67/2026/10/cctv_20261010141503_abc.jpg",
    "https://appserv.net/cache/P.1/2026/11/cctv_20261010141503_abc.jpg",
    "https://appserv.net/cache/P.1/2026/10/cctv_20261010141503_abc.jpg?redirect=https://example.org",
])
def test_unexpected_urls_and_mismatched_filename_paths_are_rejected(src):
    with pytest.raises(ValueError):
        parse_snapshot(f'<img id="cctvImage" src="{src}">', "P.1")


def test_missing_snapshot_is_not_fabricated():
    with pytest.raises(ValueError):
        parse_snapshot("<p>camera offline</p>", "P.1")


class Response:
    def __init__(self, body):
        self.text = body
        self.content = body.encode()
        self.url = httpx.URL("https://appserv.net/pingriver.php?ajax_data_only=true&station=P.1")

    def raise_for_status(self):
        return None


def test_timestamp_freshness_is_explicit_and_old_image_is_retained_as_stale():
    now = datetime(2026, 10, 10, 15, 0, tzinfo=ICT)
    def get(*args, **kwargs):
        return Response('<img id="cctvImage" src="cache/P.1/2026/10/cctv_20261010140000_abc123.jpg?t=1">')
    result = fetch_station(STATIONS[0], get=get, now=now)
    assert result["status"] == "stale"
    assert result["isStale"] is True
    assert result["ageMinutes"] == 60
    assert result["imageUrl"].startswith("https://appserv.net/")


def test_upstream_failure_returns_unavailable_without_url_or_time():
    def get(*args, **kwargs):
        raise httpx.ConnectError("offline")
    result = fetch_station(STATIONS[0], get=get)
    assert result["status"] == "unavailable"
    assert result["imageUrl"] is None
    assert result["filenameTimestamp"] is None


def test_public_directory_keeps_offline_source_entries_separate_from_images():
    def get(*args, **kwargs):
        return Response('<img id="cctvImage" src="cache/P.1/2026/10/cctv_20261010140000_abc123.jpg?t=1">')
    rows = public_sources(now=datetime(2026, 10, 10, 15, 0, tzinfo=ICT), get=get)
    assert len(rows) == 11
    assert sum(bool(row["imageUrl"]) for row in rows) == 1
    assert sum(row["status"] == "source_only" for row in rows) == 6
    assert all(row["imageUrl"] is None for row in rows if row["status"] == "source_only")
    doh_rows = [row for row in rows if row["publisher"] == "กรมทางหลวง"]
    assert len(doh_rows) == 2
    assert all(row["status"] == "source_only" for row in doh_rows)
    assert all(row["sourcePage"].startswith("https://www.highwaytraffic.go.th/") for row in doh_rows)
