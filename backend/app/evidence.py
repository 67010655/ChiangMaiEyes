"""Shared observation semantics; no fuzzy matching or invented measurements."""
from datetime import datetime, timezone
import hashlib
import math
import re


def detection_identity(payload, source, lat, lon, observed_at):
    t = datetime.fromisoformat(str(observed_at).replace('Z', '+00:00'))
    if t.tzinfo is None or lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError('detection needs coordinates and an explicit time zone')
    satellite = re.sub(r'[^a-z0-9]', '', str(payload.get('satellite') or '').lower())
    aliases = {'n': 'snpp', 'suominpp': 'snpp', 'npp': 'snpp', 'n20': 'noaa20',
               'jpss1': 'noaa20', 'n21': 'noaa21', 'jpss2': 'noaa21',
               't': 'terra', 'a': 'aqua'}
    satellite = aliases.get(satellite, satellite)
    if satellite not in {'snpp', 'noaa20', 'noaa21', 'terra', 'aqua'}:
        # Unknown/composite satellite records stay in their provider namespace.
        satellite = 'source:' + str(source).strip().lower()
    utc = t.astimezone(timezone.utc).isoformat(timespec='microseconds')
    native = f'hotspot/v2|{satellite}|{lat:.6f}|{lon:.6f}|{utc}'
    return hashlib.sha256(native.encode()).hexdigest()


def native_confidence(raw, scheme='VIIRS'):
    value = str(raw).strip().lower() if raw is not None else ''
    if scheme == 'VIIRS':
        level = {'l': 'low', 'low': 'low', 'n': 'nominal', 'nominal': 'nominal',
                 'h': 'high', 'high': 'high'}.get(value, 'unknown')
    else:
        level = 'unknown'
    return {'confidence_level': level, 'confidence_raw': str(raw) if raw is not None else None,
            'confidence_scheme': scheme if level != 'unknown' else None}


def wind_to_text(from_deg):
    names = ['เหนือ', 'ตะวันออกเฉียงเหนือ', 'ตะวันออก', 'ตะวันออกเฉียงใต้',
             'ใต้', 'ตะวันตกเฉียงใต้', 'ตะวันตก', 'ตะวันตกเฉียงเหนือ']
    return names[int(((float(from_deg) + 180) % 360 + 22.5) // 45) % 8]


def pm_brief(pm):
    if pm.current_pm25 is None:
        return 'ยังไม่มีค่า PM2.5 ที่วัดได้ในรอบนี้' + (
            f' มีดัชนี AQI จาก {len(pm.aqi_stations)} สถานีแยกไว้ ไม่แปลงเป็นความเข้มข้นฝุ่น'
            if pm.aqi_stations else '')
    return f'PM2.5 เฉลี่ยจาก {len(pm.stations)} สถานี {pm.current_pm25:.0f} µg/m³ ({pm.category})'
