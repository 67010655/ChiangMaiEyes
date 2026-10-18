"""Local design preview with an allowlisted public-camera metadata adapter.

Only fetches public HTML metadata. Images are loaded directly from their publisher
by the user's browser, and are never downloaded, stored, or proxied here.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, build_opener
import json
import re
import threading
import time

ROOT = Path(__file__).resolve().parent
BASE = "https://appserv.net/"
SOURCE_PAGE = BASE + "pingriver.php"
THAI_TIME = timezone(timedelta(hours=7))
CACHE_SECONDS = 180
STATIONS = (
    ("P.1", "สะพานนวรัฐ · แม่น้ำปิง", "อำเภอเมืองเชียงใหม่"),
    ("P.67", "บ้านแม่แต · แม่น้ำปิง", "อำเภอสันทราย"),
    ("P.75", "บ้านช่อแล", "อำเภอแม่แตง"),
    ("P.92", "บ้านแม่กึ๊ด", "อำเภอแม่แตง"),
    ("P.20", "บ้านเกาะ", "อำเภอเชียงดาว"),
)
_lock = threading.Lock()
_cache = None
_expires = 0


class PublisherRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "appserv.net":
            raise ValueError("Unexpected metadata redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = build_opener(PublisherRedirectHandler)


class PublicImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.src = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "img" and attributes.get("id") == "cctvImage":
            self.src = attributes.get("src")


def parse_public_image(page_html, station):
    parser = PublicImageParser()
    parser.feed(page_html)
    if not parser.src:
        raise ValueError("Public page contains no camera image")
    url = urlsplit(urljoin(SOURCE_PAGE, parser.src))
    # Only the observed publisher's station-specific public cache is allowed.
    # No arbitrary URL, redirect destination, credentials, or playback token.
    prefix = "/cache/" + station + "/"
    if url.scheme != "https" or url.hostname != "appserv.net" or not url.path.startswith(prefix):
        raise ValueError("Unexpected camera image origin or station")
    if not re.fullmatch(r"/cache/P\.\d+/\d{4}/\d{2}/cctv_\d{14}_[a-f0-9]+\.jpg", url.path):
        raise ValueError("Unexpected public image path")
    image_url = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    filename_time = re.search(r"cctv_(\d{14})_", url.path).group(1)
    timestamp = datetime.strptime(filename_time, "%Y%m%d%H%M%S").replace(tzinfo=THAI_TIME).isoformat()
    return image_url, timestamp


def fetch_station(station_info):
    station, name, district = station_info
    result = {
        "id": station, "name": name, "district": district,
        "kind": "river_snapshot", "publisher": "AppServ PingRiver",
        "sourcePage": SOURCE_PAGE, "imageUrl": None,
        "filenameTimestamp": None, "capturedAt": None,
        "checkedAt": datetime.now(THAI_TIME).isoformat(),
        "status": "unavailable",
    }
    try:
        # This query is the public station-switching request used by the site.
        url = SOURCE_PAGE + "?ajax_data_only=true&station=" + station
        with _opener.open(url, timeout=15) as response:
            if urlsplit(response.url).hostname != "appserv.net":
                raise ValueError("Unexpected metadata redirect")
            html = response.read(2_000_001)
            if len(html) > 2_000_000:
                raise ValueError("Metadata page too large")
        result["imageUrl"], result["filenameTimestamp"] = parse_public_image(
            html.decode("utf-8", errors="replace"), station
        )
        result["status"] = "public_snapshot"
    except (URLError, ValueError, TimeoutError, OSError):
        result["error"] = "อ่านรายการภาพจากต้นทางไม่ได้"
    return result


def public_camera_metadata():
    global _cache, _expires
    with _lock:
        if _cache is not None and time.monotonic() < _expires:
            return _cache
        with ThreadPoolExecutor(max_workers=5) as pool:
            cameras = list(pool.map(fetch_station, STATIONS))
        _cache = {
            "cameras": cameras, "checkedAt": datetime.now(THAI_TIME).isoformat(),
            "cacheSeconds": CACHE_SECONDS,
            "timestampNote": "เวลาจากชื่อไฟล์ต้นทาง ไม่ใช่เวลาบันทึกที่ยืนยันจากกล้อง",
        }
        _expires = time.monotonic() + CACHE_SECONDS
        return _cache


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path == "/api/public-cameras":
            data = json.dumps(public_camera_metadata(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()


if __name__ == "__main__":
    print("ChiangMaiEyes design preview: http://127.0.0.1:8766/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8766), PreviewHandler).serve_forever()
