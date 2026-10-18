from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.providers.verified_history import daily_counts, fetch_verified_firms


class Response:
    def __init__(self, body, url):
        self.text = body
        self.content = body.encode()
        self.url = url

    def raise_for_status(self):
        return None


def test_verified_history_switches_between_standard_and_nrt_products():
    now = datetime(2026, 7, 5, 18, tzinfo=timezone.utc)
    availability = """data_id,min_date,max_date
VIIRS_SNPP_NRT,2026-07-01,2026-07-05
VIIRS_SNPP_SP,2012-01-20,2026-06-30
VIIRS_NOAA20_NRT,2026-07-01,2026-07-05
VIIRS_NOAA20_SP,2018-04-01,2026-06-30
VIIRS_NOAA21_NRT,2024-01-17,2026-07-05
"""
    requests = []

    def get(url, timeout):
        requests.append(url)
        if "/data_availability/" in url:
            return Response(availability, "https://firms.modaps.eosdis.nasa.gov/api/data_availability/")
        source = urlsplit(url).path.split("/")[5]
        detections = "latitude,longitude,acq_date,acq_time,satellite,frp,confidence\n"
        if source == "VIIRS_SNPP_SP":
            detections += "18.9160,98.9390,2026-06-26,1745,N,8.2,n\n"
        return Response(detections, "https://firms.modaps.eosdis.nasa.gov/api/area/")

    report = fetch_verified_firms("test-key", 10, now=now, get=get)

    area_urls = [url for url in requests if "/api/area/" in url]
    assert report["status"] == "complete"
    assert {urlsplit(url).path.split("/")[5] for url in area_urls} == {
        "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_SP",
        "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT",
    }
    assert all("/2026-06-" in url or "/2026-07-" in url for url in area_urls)
    assert len(report["items"]) == 1
    assert report["items"][0]["source"] == "VIIRS_SNPP_SP"
    counts = dict(daily_counts(report))
    assert counts["2026-06-27"] == 1


def test_verified_history_does_not_treat_failed_availability_as_zero_fires():
    area_requests = []

    def get(url, timeout):
        if "/data_availability/" in url:
            return Response("unexpected,columns\n", "https://firms.modaps.eosdis.nasa.gov/")
        area_requests.append(url)
        return Response("latitude,longitude,acq_date,acq_time\n", "https://firms.modaps.eosdis.nasa.gov/")

    report = fetch_verified_firms(
        "test-key", 7, now=datetime(2026, 7, 5, 18, tzinfo=timezone.utc), get=get
    )

    assert report["status"] == "unavailable"
    assert report["items"] == []
    assert report["coverage"][0]["status"] == "unavailable"
    assert area_requests == []
