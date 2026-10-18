"""Bounded public JAXA web-product probe; research use, not a stable API client.

Retains web FRP without assigning undocumented units. Absence of a detection or
of an archived frame is never interpreted as a clear-sky non-fire observation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://www.eorc.jaxa.jp/ptree/map2/himawari/L2_WLF/010"


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    q = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(q)))


def fetch(stamp, out):
    t = utc(stamp)
    name = f"H09_{t:%Y%m%d_%H%M}.json"
    url = f"{BASE}/{t:%Y/%m/%d}/{name}"
    path = out / "raw" / name
    receipt_path = path.with_suffix(".receipt.json")
    if path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf8"))
        return receipt, json.loads(path.read_text(encoding="utf8"))
    receipt = {"nominal_observation_time_utc": t.isoformat(), "url": url,
               "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
               "historical_publication_time_utc": None,
               "observation_time_basis": "official web filename, not per-pixel scan time"}
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "ChiangMaiEyes-research-probe/1.0"})
            with urlopen(req, timeout=60) as r:
                data = r.read(4_000_001)
                if len(data) > 4_000_000:
                    raise ValueError("Probe frame exceeds bounded 4 MB limit")
                frame = json.loads(data)
                assert frame["type"] == "FeatureCollection"
                path.write_bytes(data)
                receipt.update(status="ok", http_status=r.status, bytes=len(data),
                               sha256=hashlib.sha256(data).hexdigest(),
                               last_modified=r.headers.get("Last-Modified"),
                               feature_count=len(frame["features"]))
            break
        except HTTPError as e:
            receipt.update(status="missing_or_error", http_status=e.code, error=str(e))
            if e.code < 500 or attempt == 2:
                frame = None
                break
            time.sleep(attempt + 1)
        except Exception as e:
            receipt.update(status="missing_or_error", error=str(e))
            frame = None
            if attempt == 2:
                break
            time.sleep(attempt + 1)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf8")
    return receipt, frame


def normalize(frame, receipt, bbox):
    out = []
    if frame is None:
        return out
    west, south, east, north = bbox
    for index, feature in enumerate(frame["features"]):
        if feature["geometry"]["type"] != "Point":
            continue
        lon, lat = feature["geometry"]["coordinates"]
        if not (west <= lon <= east and south <= lat <= north):
            continue
        p = feature["properties"]
        reliability = int(p.get("RELIABILITY", -1))
        out.append({"id": f"{receipt['nominal_observation_time_utc']}:{index}",
                    "latitude": lat, "longitude": lon,
                    "observation_time_utc": receipt["nominal_observation_time_utc"],
                    "publication_time_utc": None,
                    "first_retrieved_at_utc": receipt["retrieved_at_utc"],
                    "source": "JAXA_H09_L2WLF010_public_web",
                    "source_url": receipt["url"], "source_sha256": receipt["sha256"],
                    "reliability": reliability,
                    "quality_eligible": reliability in (3, 5) and int(p.get("VOLCANO", 0)) == 0,
                    "level": int(p.get("LEVEL", -1)), "volcano": int(p.get("VOLCANO", 0)),
                    "frp_web_raw": p.get("FRP"), "frp_web_unit": "unverified",
                    "pixel_spacing_degrees_nominal": 0.02,
                    "not_detection_semantics": "no event does not establish clear sky or extinguished fire"})
    return out


def fetch_frame(observation_time_utc, output_dir, bbox=(98, 17.2, 99.8, 20.2)):
    """Return source receipt and normalized detections for an official web frame.

    The caller must independently apply an explicit historical-availability
    assumption. This interface never assigns a made-up publication timestamp.
    Only source observations are returned, with quality_eligible for filtering.
    A successful empty list proves neither cloud-free observation nor no fire.
    """
    t = observation_time_utc
    if isinstance(t, str):
        t = utc(t)
    if t.tzinfo is None:
        raise ValueError("An aware UTC datetime is required")
    t = t.astimezone(timezone.utc)
    if t.minute % 10 or t.second or t.microsecond:
        raise ValueError("Himawari nominal full-disk time must be a 10-minute boundary")
    out = Path(output_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    receipt, frame = fetch(t.isoformat(), out)
    receipt = dict(receipt, coverage_semantics="detections-only; no cloud/no-fire/valid-observation coverage mask")
    return receipt, normalize(frame, receipt, bbox)


def match_prior_viirs(events, points, radius_km=4.0):
    matches = []
    for event in events:
        if not event["quality_eligible"]:
            continue
        nominal = utc(event["observation_time_utc"])
        eligible = [(distance_km(event["latitude"], event["longitude"], v["latitude"], v["longitude"]), v)
                    for v in points if v.get("confidence") in ("n", "h")
                    and nominal-timedelta(hours=24) <= utc(v["detected_at"]) <= nominal-timedelta(hours=3)]
        close = [(d, v) for d, v in eligible if d <= radius_km]
        if close:
            d, v = min(close, key=lambda x: x[0])
            matches.append({"himawari_id": event["id"], "nominal_himawari_time_utc": nominal.isoformat(),
                            "nearest_prior_viirs_time_utc": utc(v["detected_at"]).isoformat(),
                            "distance_km": d, "prior_viirs_count": len(close),
                            "comparison_kind": "past-only corroboration, not sensitivity/precision validation",
                            "viirs_availability_delay_assumption_hours": 3})
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=["2026-01-15", "2026-02-15", "2026-03-24", "2026-04-02"])
    parser.add_argument("--hours", nargs="+", type=int, default=list(range(24)))
    parser.add_argument("--bbox", nargs=4, type=float, default=[98, 17.2, 99.8, 20.2])
    parser.add_argument("--out", type=Path, default=ROOT / "output/fire-engineering-20261018/himawari-probe")
    parser.add_argument("--probe-ten-minute-retention", action="store_true")
    args = parser.parse_args()
    assert len(args.dates)*len(args.hours) <= 200, "Use separate bounded probes, maximum 200 hourly frames"
    out = args.out
    (out / "raw").mkdir(parents=True, exist_ok=True)
    stamps = [f"{d}T{h:02d}:00:00+00:00" for d in args.dates for h in args.hours]
    if args.probe_ten_minute_retention:
        stamps += [f"2026-03-24T06:{m:02d}:00+00:00" for m in [10, 20, 30]]
    receipts, events = [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for receipt, frame in pool.map(lambda s: fetch(s, out), stamps):
            receipts.append(receipt)
            rows = normalize(frame, receipt, args.bbox)
            events.extend(rows)
            print(receipt["nominal_observation_time_utc"], receipt["status"], len(rows), flush=True)
    points_path = ROOT / "output/hindcast-2026/firms-points.json"
    points = json.loads(points_path.read_text(encoding="utf8")) if points_path.exists() else []
    matches = match_prior_viirs(events, points)
    summary = {"bbox_wsen": args.bbox, "roi_definition": "Chiang Mai bounding window, not province polygon",
               "frames_requested": len(receipts), "frames_ok": sum(r["status"] == "ok" for r in receipts),
               "bytes_downloaded": sum(r.get("bytes", 0) for r in receipts),
               "roi_events_all": len(events), "roi_events_quality_eligible": sum(e["quality_eligible"] for e in events),
               "eligible_events_corroborated_by_prior_viirs": len(matches),
               "prior_viirs_radius_km": 4.0,
               "status": "public historical detection access verified; operational latency and model gain unverified",
               "historical_availability": "Publication timestamps absent. Last-Modified is not proven first publication. Fixed-delay scenarios only.",
               "warning": "Sampled slots do not establish complete 10-minute archive coverage. Missing frame or no event is unknown, never non-fire."}
    if args.probe_ten_minute_retention:
        tests = [r for r in receipts if utc(r["nominal_observation_time_utc"]).minute]
        summary["ten_minute_retention_probe"] = {
            "requested": len(tests), "available": sum(r["status"] == "ok" for r in tests),
            "qualification": "FAQ pruning of old web images does not establish pruning of vectorJSON. Probe verifies only these requested frames."}
    for name, value in [("frame-manifest", receipts), ("events", events), ("past-viirs-corroboration", matches), ("summary", summary)]:
        (out / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
