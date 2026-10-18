"""FIRMS backfill with per-request coverage; failed windows are not zero fires."""
from __future__ import annotations
import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from app.providers.hotspot_provider import _province_ring, _point_in_ring, _nasa_detected_at, estimate_district,province_bbox

ICT = timezone(timedelta(hours=7))
FIRMS = 'https://firms.modaps.eosdis.nasa.gov/api/area/csv/'
AVAILABILITY = 'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/'
BBOX = province_bbox()
# Use NRT when the product reports that a date is available, then use NASA's
# standard-processed (SP) VIIRS product for older dates. NOAA-21 currently has
# no SP product in the FIRMS API catalogue, so it is tracked as NRT only.
PRODUCTS = {
    'SNPP': ('VIIRS_SNPP_NRT', 'VIIRS_SNPP_SP'),
    'NOAA-20': ('VIIRS_NOAA20_NRT', 'VIIRS_NOAA20_SP'),
    'NOAA-21': ('VIIRS_NOAA21_NRT',),
}


def fetch_verified_firms(key, days, *, now=None, get=None):
    now = now or datetime.now(ICT)
    # Resolve the transport at call time so tests and local operations can
    # provide their own client without capturing the pre-patched httpx.get.
    get = get or httpx.get
    if not key:
        return {'items': [], 'coverage': [], 'status': 'unavailable'}
    try:
        availability_response = get(AVAILABILITY + f'{key}/all', timeout=22)
        availability_response.raise_for_status()
        availability_reader = csv.DictReader(io.StringIO(availability_response.text))
        if not {'data_id', 'min_date', 'max_date'}.issubset(availability_reader.fieldnames or []):
            raise ValueError('not a FIRMS availability CSV')
        availability = {}
        for row in availability_reader:
            try:
                availability[row['data_id']] = (
                    datetime.strptime(row['min_date'], '%Y-%m-%d').date(),
                    datetime.strptime(row['max_date'], '%Y-%m-%d').date(),
                )
            except (KeyError, ValueError):
                continue
    except Exception:
        return {'items': [], 'coverage': [{
            'source': 'NASA FIRMS data availability', 'status': 'unavailable',
            'error': 'upstream_request_or_format_failed',
        }], 'status': 'unavailable'}

    earliest = now.astimezone(ICT).date() - timedelta(days=days - 1)
    # FIRMS date windows are UTC; include the preceding UTC day for Bangkok.
    start = earliest - timedelta(days=1)
    last = now.astimezone(timezone.utc).date()
    jobs, uncovered = [], []
    for sensor, sources in PRODUCTS.items():
        day = start
        while day <= last:
            # The most current available product wins when NASA reports overlap.
            source = next((candidate for candidate in sources
                           if candidate in availability and availability[candidate][0] <= day <= availability[candidate][1]), None)
            span = 1
            while day + timedelta(days=span) <= last and span < 5:
                next_day = day + timedelta(days=span)
                next_source = next((candidate for candidate in sources
                                    if candidate in availability and availability[candidate][0] <= next_day <= availability[candidate][1]), None)
                if next_source != source:
                    break
                span += 1
            if source:
                jobs.append((sensor, source, day, span))
            else:
                uncovered.append({'sensor': sensor, 'source': 'NASA FIRMS availability',
                                  'utc_start': day.isoformat(), 'days': span,
                                  'status': 'not_available'})
            day += timedelta(days=span)
    ring = _province_ring()

    def one(job):
        sensor, source, start, span = job
        meta = {'sensor': sensor, 'source': source, 'utc_start': start.isoformat(), 'days': span,
                'bbox':BBOX,
                'status': 'unavailable', 'invalid_rows': 0,
                'source_url': 'https://firms.modaps.eosdis.nasa.gov/api/area/'}
        rows = []
        try:
            r = get(FIRMS + f'{key}/{source}/{BBOX}/{span}/{start.isoformat()}', timeout=22)
            r.raise_for_status()
            if urlsplit(str(getattr(r, 'url', FIRMS))).hostname not in (None, 'firms.modaps.eosdis.nasa.gov'):
                raise ValueError('unexpected FIRMS response host')
            reader = csv.DictReader(io.StringIO(r.text))
            if not {'latitude', 'longitude', 'acq_date', 'acq_time'}.issubset(reader.fieldnames or []):
                raise ValueError('not a FIRMS CSV')
            for v in reader:
                try:
                    lat, lon = float(v['latitude']), float(v['longitude'])
                    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                        raise ValueError('invalid location')
                    t = _nasa_detected_at(v['acq_date'], v['acq_time'])
                    parsed = datetime.fromisoformat(t)
                    if parsed > now + timedelta(minutes=5):
                        raise ValueError('future detection')
                    if parsed.astimezone(ICT).date() < earliest or ring and not _point_in_ring(lon, lat, ring):
                        continue
                    satellite = v.get('satellite') or source
                    native = f'{satellite}/{lat:.6f}/{lon:.6f}/{t}'
                    frp = float(v['frp']) if v.get('frp') else None
                    if frp is not None and (not math.isfinite(frp) or frp < 0):
                        raise ValueError('invalid FRP')
                    rows.append({'native_id': native, 'latitude': lat, 'longitude': lon,
                                 'detected_at': t, 'district': estimate_district(lat, lon),
                                 'source': source, 'satellite': satellite, 'frp': frp,
                                 'confidence': v.get('confidence'), 'source_url': meta['source_url']})
                except (ValueError, TypeError, KeyError):
                    meta['invalid_rows'] += 1
            meta['status'] = 'partial' if meta['invalid_rows'] else 'received'
            meta['received'] = len(rows)
        except Exception:
            # Never log a URL containing the FIRMS credential.
            meta['error'] = 'upstream_request_or_format_failed'
        return meta, rows

    coverage, items, seen = [], [], set()
    with ThreadPoolExecutor(max_workers=6) as pool:
        for meta, rows in pool.map(one, jobs):
            coverage.append(meta)
            for row in rows:
                if row['native_id'] not in seen:
                    items.append(row)
                    seen.add(row['native_id'])
    coverage.extend(uncovered)
    received = sum(m['status'] == 'received' for m in coverage)
    return {'items': sorted(items, key=lambda x: x['detected_at']), 'coverage': coverage,
            'status': 'complete' if received == len(coverage) else 'partial' if items or received else 'unavailable'}


def daily_counts(report):
    """Only return dates covered by all sources on both intersecting UTC days."""
    days = {}
    for item in report['items']:
        d = item['detected_at'][:10]
        days[d] = days.get(d, 0) + 1
    covered = {s: set() for s in PRODUCTS}
    for c in report['coverage']:
        if c['status'] != 'received':
            continue
        start = datetime.fromisoformat(c['utc_start']).date()
        sensor = c.get('sensor')
        if sensor in covered:
            covered[sensor].update(start + timedelta(days=i) for i in range(c['days']))
    all_utc = set.intersection(*covered.values()) if covered else set()
    complete = [d for d in sorted(all_utc) if d - timedelta(days=1) in all_utc]
    return [(d.isoformat(), days.get(d.isoformat(), 0)) for d in complete]
