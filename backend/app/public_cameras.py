"""Publicly published Chiang Mai camera snapshots and source directory.

Images remain hosted by their publishers. Only allow-listed station metadata is
read here; image URLs are validated before they are sent to the browser.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html.parser import HTMLParser
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urljoin, urlsplit
import re

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/public-cameras", tags=["Public cameras"])
ICT = timezone(timedelta(hours=7))
SOURCE_PAGE = "https://appserv.net/pingriver.php"
PAO_PAGE = "https://chiangmaipao.go.th/all_cctv"
STATIONS = (
    ("P.1", "สะพานนวรัฐ · แม่น้ำปิง", "อำเภอเมืองเชียงใหม่"),
    ("P.67", "บ้านแม่แต · แม่น้ำปิง", "อำเภอสันทราย"),
    ("P.75", "บ้านช่อแล · แม่น้ำปิง", "อำเภอแม่แตง"),
    ("P.92", "บ้านแม่กึ๊ด · แม่น้ำปิง", "อำเภอแม่แตง"),
    ("P.20", "บ้านเกาะ · แม่น้ำปิง", "อำเภอเชียงดาว"),
)
DOH_CAMERAS = (
    ("DOH-107-MAETANG", "ทางหลวง 107 · อำเภอแม่แตง", "อำเภอแม่แตง",
     "https://www.highwaytraffic.go.th/DOHMobile/Modules/InfoCamera.aspx?id=3126&direction=IN"),
    ("DOH-108-MUEANG", "ทางหลวง 108 · อำเภอเมืองเชียงใหม่", "อำเภอเมืองเชียงใหม่",
     "https://www.highwaytraffic.go.th/DOHMobile/Modules/InfoCamera.aspx?id=3065&direction=IN"),
)
_cache: dict | None = None
_expires = 0.0
_lock = Lock()


class CameraImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.src: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and attrs.get("id") == "cctvImage":
            self.src = attrs.get("src")


def parse_snapshot(html: str, station: str) -> tuple[str, str]:
    parser = CameraImageParser()
    parser.feed(html)
    if not parser.src:
        raise ValueError("publisher has no public snapshot")
    url = urlsplit(urljoin(SOURCE_PAGE, parser.src))
    if url.scheme != "https" or url.hostname != "appserv.net" or url.port not in (None, 443):
        raise ValueError("unexpected image host")
    query = parse_qs(url.query, strict_parsing=True) if url.query else {}
    if url.username or url.password or url.fragment or set(query) - {"t"}:
        raise ValueError("unexpected image URL fields")
    if query and (len(query["t"]) != 1 or not query["t"][0].isdigit()):
        raise ValueError("unexpected image cache field")
    if not re.fullmatch(r"/cache/P\.\d+/\d{4}/\d{2}/cctv_\d{14}_[a-f0-9]+\.jpg", url.path):
        raise ValueError("unexpected public image path")
    if not url.path.startswith(f"/cache/{station}/"):
        raise ValueError("image station does not match request")
    file_time = re.search(r"cctv_(\d{14})_", url.path).group(1)
    captured = datetime.strptime(file_time, "%Y%m%d%H%M%S").replace(tzinfo=ICT)
    if url.path.split("/")[3:5] != [captured.strftime("%Y"), captured.strftime("%m")]:
        raise ValueError("image path date does not match filename")
    return f"{url.scheme}://{url.netloc}{url.path}", captured.isoformat()


def fetch_station(info, *, get=httpx.get, now=None) -> dict:
    station, name, district = info
    checked = (now or datetime.now(ICT)).astimezone(ICT)
    result = {
        "id": station, "name": name, "district": district,
        "kind": "river_snapshot", "publisher": "AppServ PingRiver",
        "sourcePage": SOURCE_PAGE, "imageUrl": None,
        "filenameTimestamp": None, "checkedAt": checked.isoformat(),
        "status": "unavailable", "isStale": None, "ageMinutes": None,
        "locationNote": "ผู้เผยแพร่ระบุสถานีและอำเภอ ไม่พบพิกัดกล้องที่ยืนยันได้",
    }
    try:
        response = get(SOURCE_PAGE, params={"ajax_data_only": "true", "station": station},
                       timeout=8, follow_redirects=False)
        response.raise_for_status()
        if urlsplit(str(response.url)).hostname != "appserv.net":
            raise ValueError("unexpected publisher host")
        if len(response.content) > 2_000_000:
            raise ValueError("publisher page too large")
        image, captured_at = parse_snapshot(response.text, station)
        captured = datetime.fromisoformat(captured_at)
        age = int((checked - captured).total_seconds() // 60)
        if age < -5:
            status = "clock_mismatch"
        else:
            status = "stale" if age > 30 else "snapshot"
        result.update({"imageUrl": image, "filenameTimestamp": captured_at,
                       "ageMinutes": max(0, age), "isStale": age > 30,
                       "status": status})
    except Exception:
        # Do not expose request details or publisher response bodies publicly.
        pass
    return result


def public_sources(*, now=None, get=httpx.get) -> list[dict]:
    """Return five validated images and source-only public camera entries."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        snapshots = list(pool.map(lambda row: fetch_station(row, get=get, now=now), STATIONS))
    # The official PAO page lists four cameras, but when reviewed on 2026-10-10
    # showed standby/waiting-for-feed placeholders. Keep these discoverable as
    # source links, and never present them as a working stream or image.
    snapshots.extend({
        "id": f"PAO-CAM-{n:02d}", "name": label,
        "district": "จังหวัดเชียงใหม่ · ตำแหน่งกล้องไม่ระบุ",
        "kind": "live_video", "publisher": "องค์การบริหารส่วนจังหวัดเชียงใหม่",
        "sourcePage": PAO_PAGE, "imageUrl": None, "filenameTimestamp": None,
        "checkedAt": None, "reviewedAt": "2026-10-10",
        "status": "source_only", "isStale": None, "ageMinutes": None,
        "locationNote": "หน้าแหล่งข้อมูลประกาศรายการกล้อง แต่ไม่เปิดภาพหรือวิดีโอให้ดึง",
    } for n, label in enumerate((
        "กล้องทางเดินเท้า · ลานสาธารณะ", "กล้องมุมกว้าง · เมืองและแม่น้ำ",
        "กล้องจับภาพทางหลวง", "กล้องมุมสูง · แยกการจราจร",
    ), start=1))
    # The Department of Highways public list includes two Chiang Mai cameras,
    # but both detail pages returned the official service-down image when
    # reviewed on 2026-10-10. Keep the records discoverable without presenting
    # the placeholder as a working camera feed.
    snapshots.extend({
        "id": camera_id, "name": label, "district": district,
        "kind": "cctv_directory", "publisher": "กรมทางหลวง",
        "sourcePage": source_page, "imageUrl": None,
        "filenameTimestamp": None, "checkedAt": None,
        "reviewedAt": "2026-10-10", "status": "source_only",
        "isStale": None, "ageMinutes": None,
        "locationNote": "หน้ากล้องทางการแสดงภาพแจ้ง service-down ขณะตรวจ · ไม่ใช่ภาพสดที่ใช้ยืนยันสถานการณ์ได้",
    } for camera_id, label, district, source_page in DOH_CAMERAS)
    return snapshots


def camera_directory(*, force=False, now=None, get=httpx.get):
    global _cache, _expires
    with _lock:
        current = monotonic()
        if not force and _cache is not None and current < _expires:
            return _cache
        cameras = public_sources(now=now, get=get)
        _cache = {
            "cameras": cameras,
            "checkedAt": (now or datetime.now(ICT)).astimezone(ICT).isoformat(),
            "cacheSeconds": 180,
            "summary": {
                "publicSnapshots": sum(bool(x["imageUrl"]) for x in cameras),
                "staleSnapshots": sum(x["status"] == "stale" for x in cameras),
                "sourceOnly": sum(x["status"] == "source_only" for x in cameras),
            },
            "timestampNote": "เวลา snapshot อ่านจากชื่อไฟล์ของผู้เผยแพร่ ไม่ใช่เวลาที่กล้องบันทึกในภาพ",
        }
        _expires = current + 180
        return _cache


@router.get("")
def read_public_cameras():
    return camera_directory()
