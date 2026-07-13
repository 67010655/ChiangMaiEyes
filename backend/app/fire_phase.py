"""Fire-lifecycle phase classifier (Phase 6).

Assigns each Chiang Mai district a phase in the disaster-management cycle:
  - during (red)   — active hotspots in the district right now
  - before (yellow) — no active fire but elevated danger (dry fuel + dry air)
  - after  (grey)   — recently burned: either Sentinel-2 dNBR burn-severity
                      (5 hardcoded zones, see _ZONE_DISTRICT) or, for any of
                      the 25 districts, "had an active fire within the last
                      _AFTER_FIRE_RETENTION_DAYS days per district_last_active"
  - normal (green)  — low danger, no fire

Enhanced with 3-phase workflow:
  - before: recommended preventive actions, nearby community forests
  - during: fire spread projection (wind + physics), forests in spread path,
            coordination note when multiple forests share a boundary zone
  - after:  historical PM2.5 correlation note
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.fire_spread_physics import DISTRICT_PHYSICS
from app.models import (
    CommunityForest,
    DistrictFirePhase,
    FirePhaseResponse,
    ForestRisk,
    Hotspot,
    HotspotResponse,
    NearbyForest,
    SatelliteLayerResponse,
    SpreadProjection,
    TambonWarning,
    WeatherResponse,
)

_PHASE_COLOR = {"normal": "green", "before": "yellow", "during": "red", "after": "grey"}
_YELLOW_THRESHOLD = 0.55
_DRY_AIR_GATE = 0.35
_DURING_FLOOR = 0.85

# Hotspots now stay in the live feed for up to 5 days (see hotspot_provider's
# NASA fetch) so a fire doesn't vanish from the map overnight. But "during"
# phase / active-hotspot-count / forest proximity must mean "burning right
# now" — a 4-day-old detection that was never re-seen should NOT floor a
# district's danger at 0.85 or mark a forest as next to an active fire.
_ACTIVE_HOTSPOT_HOURS = 24.0

# "After" phase retention window (2026-07): a district that had an active
# fire recently but doesn't right now stays flagged "after" (recovery) for
# this many days, then falls back to normal/before on its own — the source
# file (district_last_active.json, written hourly by refresh_snapshot.py)
# prunes entries past this window too, so the retention is enforced twice
# (belt-and-suspenders, cheap to keep both). This is additive alongside the
# existing dNBR satellite check below, not a replacement — dNBR only covers
# 5 hardcoded zones (_ZONE_DISTRICT), this covers all 25 districts.
_AFTER_FIRE_RETENTION_DAYS = 30


def _is_recent_detection(detected_at: str, now: datetime, hours: float) -> bool:
    try:
        dt = datetime.fromisoformat(detected_at)
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))
    return (now - dt) <= timedelta(hours=hours)


def _days_since_active(
    district: str, district_last_active: dict[str, str] | None, now: datetime
) -> int | None:
    """Days since `district`'s last active-fire date, or None if unknown/expired.

    Returns None (not "after") for day 0 — that's handled by the active>0
    "during" branch instead, since a district can't be both at once."""
    if not district_last_active or district not in district_last_active:
        return None
    try:
        last_date = date.fromisoformat(district_last_active[district])
    except (TypeError, ValueError):
        return None
    days = (now.date() - last_date).days
    return days if 0 < days <= _AFTER_FIRE_RETENTION_DAYS else None

# Which dNBR zone maps to which district (Phase 6.2 — Sentinel-2 burn scars).
_ZONE_DISTRICT = {
    "doi-suthep-pui": "เมืองเชียงใหม่",
    "doi-inthanon-west": "จอมทอง",
    "chiang-dao-limestone": "เชียงดาว",
    "mae-chaem-reserve": "แม่แจ่ม",
    "mae-taeng-headwater": "แม่แตง",
}
_BURNED_CLASSES = {"moderate", "high"}

# Approximate centroids for each district — used to find nearby forests
# when the district has active hotspots but no individual lat/lon is given.
_DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "แม่อาย":      (20.03, 99.20),
    "ฝาง":         (19.80, 99.10),
    "เชียงดาว":    (19.38, 98.95),
    "แม่แตง":      (19.10, 98.90),
    "กัลยาณิวัฒนา": (19.05, 98.35),
    "สะเมิง":      (18.80, 98.65),
    "แม่แจ่ม":     (18.50, 98.33),
    "จอมทอง":      (18.40, 98.70),
    "ฮอด":         (18.10, 98.60),
    "อมก๋อย":      (17.87, 98.35),
    "ไชยปราการ":   (19.68, 99.18),
    "ดอยสะเก็ด":   (18.98, 99.28),
    "ดอยเต่า":     (17.90, 98.65),
    "ดอยหล่อ":     (18.53, 98.75),
    "พร้าว":       (19.29, 99.22),
    "สันทราย":     (18.97, 99.05),
    "สันกำแพง":    (18.80, 99.12),
    "สันป่าตอง":   (18.60, 98.87),
    "แม่ออน":      (18.73, 99.30),
    "แม่วาง":      (18.63, 98.78),
    "หางดง":       (18.70, 98.95),
    "สารภี":       (18.73, 99.01),
    "แม่ริม":      (18.92, 98.95),
    "เวียงแหง":    (19.60, 98.65),
    "เมืองเชียงใหม่": (18.79, 98.99),
}

_SPREAD_DIR_LABELS = [
    "เหนือ", "ตะวันออกเฉียงเหนือ", "ตะวันออก", "ตะวันออกเฉียงใต้",
    "ใต้", "ตะวันตกเฉียงใต้", "ตะวันตก", "ตะวันตกเฉียงเหนือ",
]

_TAMBONS_GEOJSON = Path(__file__).resolve().parent / "data" / "chiangmai-tambons.geojson"


def _load_tambon_centroids() -> list[dict]:
    """Approximate centroid (average of all ring vertices — the same
    simplification used elsewhere in this codebase for boundary lookups) for
    every tambon, loaded once at import time. Returns [] on any error so a
    missing/bad file can't crash a request."""
    try:
        data = json.loads(_TAMBONS_GEOJSON.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[dict] = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        tambon = props.get("tambon_th")
        amphoe = props.get("amphoe_th")
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        gtype = geom.get("type")
        pts: list[tuple[float, float]] = []
        if gtype == "MultiPolygon":
            for polygon in coords:
                if polygon:
                    pts.extend((float(p[0]), float(p[1])) for p in polygon[0])
        elif gtype == "Polygon" and coords:
            pts.extend((float(p[0]), float(p[1])) for p in coords[0])
        if not (tambon and amphoe and pts):
            continue
        out.append({
            "tcode": props.get("tcode"),
            "tambon": tambon,
            "amphoe": amphoe,
            "longitude": sum(p[0] for p in pts) / len(pts),
            "latitude": sum(p[1] for p in pts) / len(pts),
        })
    return out


_TAMBON_CENTROIDS = _load_tambon_centroids()

# Per-forest fuel risk: a forest's score = its district's base danger_score,
# boosted the closer a real active hotspot is (real signal, not fabricated —
# just gives forests next to a live fire a higher score than a forest on the
# far side of the same district). Capped so it never exceeds 1.0.
_FOREST_PROXIMITY_RADIUS_KM = 15.0
_FOREST_PROXIMITY_BOOST_MAX = 0.3

# Forests within this radius are flagged as "nearby" for any phase.
_NEARBY_RADIUS_KM = 30.0
# Forests in spread path if bearing is within this cone of spread direction.
_SPREAD_CONE_HALF_DEG = 50.0
# ≥2 forests in spread path = coordination flag.
_COORDINATION_THRESHOLD = 2


def _normalize_district(name: str | None) -> str:
    return (name or "").replace("อำเภอ", "").replace("อ.", "").strip()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """True bearing from (lat1,lon1) to (lat2,lon2), degrees 0=N, 90=E."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = (math.cos(lat1_r) * math.sin(lat2_r)
         - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _nearest_hotspot_km(lat: float, lon: float, hotspots: list[Hotspot]) -> float | None:
    if not hotspots:
        return None
    return min(_haversine_km(lat, lon, h.latitude, h.longitude) for h in hotspots)


def _forest_danger_score(base_danger: float, nearest_km: float | None) -> float:
    if nearest_km is None:
        boost = 0.0
    else:
        boost = max(0.0, 1 - nearest_km / _FOREST_PROXIMITY_RADIUS_KM) * _FOREST_PROXIMITY_BOOST_MAX
    return round(min(1.0, base_danger + boost), 2)


def _spread_dir_text(deg: float) -> str:
    return _SPREAD_DIR_LABELS[round(deg / 45) % 8]


def _in_spread_cone(forest_bearing: float, spread_dir: float) -> bool:
    diff = abs((forest_bearing - spread_dir + 180) % 360 - 180)
    return diff <= _SPREAD_CONE_HALF_DEG


def _air_dryness(weather: WeatherResponse) -> float:
    humidity = weather.humidity_percent if weather.humidity_percent is not None else 50.0
    dryness = max(0.0, min(1.0, (100.0 - humidity) / 100.0))
    if (weather.rain_today_mm or 0) > 1.0:
        dryness *= 0.5
    return dryness


def dryness_from_humidity_rain(humidity_pct: float | None, rain_mm: float | None) -> float:
    """Same dryness formula as _air_dryness, but from raw numbers instead of a
    WeatherResponse — lets the predict module reuse it with forecast values."""
    humidity = humidity_pct if humidity_pct is not None else 50.0
    dryness = max(0.0, min(1.0, (100.0 - humidity) / 100.0))
    if (rain_mm or 0) > 1.0:
        dryness *= 0.5
    return dryness


def district_base_danger(district: str, dryness: float) -> float:
    """The exact district-danger formula used by classify_fire_phases (fuel +
    history + dryness), exposed so the predict module can project it forward
    with forecasted dryness instead of live — one formula, no drift risk."""
    phys = DISTRICT_PHYSICS.get(district, {"fuel_flammability": 1.2, "history_multiplier": 1.0})
    fuel_norm = min(1.0, phys["fuel_flammability"] / 1.8)
    history_norm = min(1.0, max(0.0, (phys["history_multiplier"] - 1.0) / 0.5))
    return round(0.4 * fuel_norm + 0.2 * history_norm + 0.4 * dryness, 2)


def _build_spread_projection(
    district: str,
    wind_speed_kmh: float,
    wind_dir_deg: float,
) -> SpreadProjection:
    """Rothermel-simplified spread rate from district physics + live wind."""
    phys = DISTRICT_PHYSICS.get(district, {
        "fuel_flammability": 1.2,
        "slope_deg": 20.0,
    })
    fuel = phys["fuel_flammability"]
    slope = phys["slope_deg"]

    spread_dir = (wind_dir_deg + 180) % 360
    # Rate of Spread (km/h): fuel × slope-factor × wind-factor
    slope_f = math.exp(0.069 * slope) / 4.0  # normalized around 20° ≈ 1.0
    wind_f = 1.0 + wind_speed_kmh / 15.0
    rate = round(0.5 * fuel * slope_f * wind_f, 2)

    return SpreadProjection(
        direction_deg=round(spread_dir, 1),
        direction_text=_spread_dir_text(spread_dir),
        rate_kmh=rate,
        km_6h=round(rate * 6, 1),
        km_12h=round(rate * 12, 1),
        km_24h=round(rate * 24, 1),
    )


def _nearby_forests(
    district: str,
    spread_dir: float,
    community_forests: list[CommunityForest],
    district_danger: float = 0.0,
    hotspot_items: list[Hotspot] | None = None,
) -> tuple[list[NearbyForest], str | None]:
    """Return (nearby_list, coordination_note) for a district."""
    centroid = _DISTRICT_CENTROIDS.get(district)
    if not centroid:
        return [], None

    clat, clon = centroid
    hotspot_items = hotspot_items or []
    nearby: list[NearbyForest] = []
    for cf in community_forests:
        dist = _haversine_km(clat, clon, cf.latitude, cf.longitude)
        if dist > _NEARBY_RADIUS_KM:
            continue
        bearing = _bearing(clat, clon, cf.latitude, cf.longitude)
        in_path = _in_spread_cone(bearing, spread_dir)
        nearest_km = _nearest_hotspot_km(cf.latitude, cf.longitude, hotspot_items)
        nearby.append(NearbyForest(
            name=cf.name,
            amphoe=cf.amphoe,
            distance_km=round(dist, 1),
            bearing_deg=round(bearing, 1),
            in_spread_path=in_path,
            fire_management_active=cf.fire_management_active,
            danger_score=_forest_danger_score(district_danger, nearest_km),
            nearest_hotspot_km=round(nearest_km, 1) if nearest_km is not None else None,
        ))

    nearby.sort(key=lambda f: f.distance_km)

    in_path_forests = [f for f in nearby if f.in_spread_path]
    coord_note: str | None = None
    if len(in_path_forests) >= _COORDINATION_THRESHOLD:
        names = " และ ".join(f.name for f in in_path_forests[:3])
        coord_note = (
            f"พื้นที่นี้อยู่ในแนวรอยต่อของหลายป่าชุมชน ({names}) "
            "ผู้มีอำนาจควรประสานงานร่วมกันก่อนสั่งการภาคสนาม"
        )

    return nearby[:8], coord_note  # cap at 8 to keep payload reasonable


def _recommended_actions(
    phase: str,
    danger_score: float,
    nearby: list[NearbyForest],
    spread: SpreadProjection | None,
) -> list[str]:
    actions: list[str] = []
    inactive = [f for f in nearby if not f.fire_management_active]
    in_path = [f for f in nearby if f.in_spread_path]

    if phase == "before":
        actions.append("ลาดตระเวนทุก 4 ชั่วโมงในพื้นที่เสี่ยง")
        actions.append("ตรวจสอบและซ่อมแนวกันไฟก่อนหน้าแล้งหนัก")
        if inactive:
            names = " · ".join(f.name for f in inactive[:2])
            actions.append(f"แจ้ง {names} จัดทำแผนจัดการเชื้อเพลิงด่วน (ยังไม่มีบันทึกกิจกรรม)")
        if danger_score >= 0.7:
            actions.append("ประสานทีมดับเพลิงสำรองให้พร้อมปฏิบัติการภายใน 2 ชั่วโมง")

    elif phase == "during":
        actions.append("แจ้งเตือนทีมดับเพลิงภาคสนามทันที")
        if in_path:
            names = " · ".join(f.name for f in in_path[:3])
            actions.append(f"แจ้งเตือนป่าชุมชนปลายลม: {names} ให้เตรียมรับมือ")
        if spread:
            actions.append(
                f"ไฟคาดลามทิศ{spread.direction_text} ~{spread.km_6h} กม./6ชม. "
                f"หรือ ~{spread.km_12h} กม./12ชม. ที่ความเร็ว {spread.rate_kmh} กม./ชม."
            )
        actions.append("ตรวจสอบแนวกันไฟและเส้นทางอพยพในทิศปลายลม")

    elif phase == "after":
        actions.append("ตรวจสอบรอยไหม้และประเมินพื้นที่เสียหายด้วย drone หรือลาดตระเวน")
        actions.append("ติดตาม PM2.5 รายชั่วโมง — ควันฟุ้งกระจายสูงสุดมักอยู่ใน 24-48 ชม. หลังไฟ")
        actions.append("วางแผนฟื้นฟูแนวกันไฟและพันธุ์ไม้ก่อนหน้าฝนถัดไป")

    return actions


def classify_fire_phases(
    hotspots: HotspotResponse,
    weather: WeatherResponse,
    satellite_layers: SatelliteLayerResponse | None = None,
    community_forests: list[CommunityForest] | None = None,
    hotspot_history: list[tuple[str, int]] | None = None,
    pm25_history: list[tuple[str, float]] | None = None,
    district_winds: dict[str, tuple[float, float]] | None = None,
    district_last_active: dict[str, str] | None = None,
) -> FirePhaseResponse:
    cf_list = community_forests or []

    now = datetime.now(timezone(timedelta(hours=7)))
    recent_hotspots = [h for h in hotspots.items if _is_recent_detection(h.detected_at, now, _ACTIVE_HOTSPOT_HOURS)]

    active_by_district: dict[str, int] = {}
    for item in recent_hotspots:
        name = _normalize_district(item.district)
        if name:
            active_by_district[name] = active_by_district.get(name, 0) + 1

    burned: dict[str, tuple[float, str]] = {}
    if satellite_layers:
        for zone in satellite_layers.dryness_zones:
            district = _ZONE_DISTRICT.get(zone.id)
            if district and zone.burn_severity in _BURNED_CLASSES and zone.dnbr is not None:
                burned[district] = (zone.dnbr, zone.burn_severity)

    dryness = _air_dryness(weather)
    humidity = weather.humidity_percent if weather.humidity_percent is not None else 50.0
    global_wind_speed = weather.wind_speed_kmh
    global_wind_dir = weather.wind_direction_deg

    phases: list[DistrictFirePhase] = []
    for district, phys in DISTRICT_PHYSICS.items():
        # Per-district wind from Open-Meteo centroid fetch; fall back to synoptic station.
        if district_winds and district in district_winds:
            dist_wind_speed, dist_wind_dir = district_winds[district]
            wind_source_label = "Open-Meteo (per-district centroid)"
        else:
            dist_wind_speed, dist_wind_dir = global_wind_speed, global_wind_dir
            wind_source_label = "สถานีอุตุนิยมวิทยา (synoptic)"

        spread_dir_dist = (dist_wind_dir + 180) % 360

        active = active_by_district.get(district, 0)
        fuel_norm = min(1.0, phys["fuel_flammability"] / 1.8)
        history_norm = min(1.0, max(0.0, (phys["history_multiplier"] - 1.0) / 0.5))
        danger = district_base_danger(district, dryness)  # same formula as fuel_norm/history_norm above

        calc_breakdown = {
            "formula": "danger = 0.4×fuel + 0.2×history + 0.4×dryness",
            "fuel_flammability": phys["fuel_flammability"],
            "fuel_norm": round(fuel_norm, 3),
            "history_level": phys.get("history_level", "ปานกลาง"),
            "history_multiplier": phys.get("history_multiplier", 1.0),
            "history_norm": round(history_norm, 3),
            "dryness": round(dryness, 3),
            "humidity_pct": round(humidity, 1),
            "rain_24h_mm": round(weather.rain_today_mm or 0, 1),
            "wind_speed_kmh": round(dist_wind_speed, 1),
            "wind_dir_deg": round(dist_wind_dir, 1),
            "wind_source": wind_source_label,
            "fuel_contrib": round(0.4 * fuel_norm, 3),
            "history_contrib": round(0.2 * history_norm, 3),
            "dryness_contrib": round(0.4 * dryness, 3),
        }

        spread: SpreadProjection | None = None
        nearby: list[NearbyForest] = []
        coord_note: str | None = None
        days_since_active = _days_since_active(district, district_last_active, now)

        if active > 0:
            phase = "during"
            danger = max(danger, _DURING_FLOOR)
            reasons = [f"พบจุดความร้อน {active} จุดในพื้นที่ตอนนี้"]
            spread = _build_spread_projection(district, dist_wind_speed, dist_wind_dir)
            nearby, coord_note = _nearby_forests(
                district, spread.direction_deg, cf_list,
                district_danger=danger, hotspot_items=recent_hotspots,
            )
        elif district in burned:
            phase = "after"
            dnbr_value, severity = burned[district]
            reasons = [f"พบรอยไหม้จากดาวเทียม (dNBR {dnbr_value}, ความรุนแรง {severity}) — ระยะฟื้นฟู"]
            nearby, _ = _nearby_forests(
                district, spread_dir_dist, cf_list,
                district_danger=danger, hotspot_items=recent_hotspots,
            )
        elif days_since_active is not None:
            phase = "after"
            reasons = [f"ไฟดับไปแล้ว {days_since_active} วันก่อน — อยู่ระยะฟื้นฟู"]
            nearby, _ = _nearby_forests(
                district, spread_dir_dist, cf_list,
                district_danger=danger, hotspot_items=recent_hotspots,
            )
        elif dryness < _DRY_AIR_GATE:
            phase = "normal"
            reasons = [f"อากาศชื้น ความชื้น {humidity:.0f}% เชื้อเพลิงไม่แห้งพอจะติดไฟ"]
        elif danger >= _YELLOW_THRESHOLD:
            phase = "before"
            reasons = [
                f"เชื้อเพลิงติดไฟง่าย ({phys['history_level']})",
                f"อากาศแห้ง ความชื้น {humidity:.0f}%",
            ]
            nearby, coord_note = _nearby_forests(
                district, spread_dir_dist, cf_list,
                district_danger=danger, hotspot_items=recent_hotspots,
            )
        else:
            phase = "normal"
            reasons = ["ยังไม่มีจุดความร้อน และดัชนีความเสี่ยงอยู่ระดับต่ำ"]

        actions = _recommended_actions(phase, danger, nearby, spread)

        phases.append(DistrictFirePhase(
            district=district,
            phase=phase,
            color=_PHASE_COLOR[phase],
            danger_score=danger,
            active_hotspots=active,
            reasons=reasons,
            recommended_actions=actions,
            nearby_forests=nearby,
            spread_projection=spread,
            coordination_note=coord_note,
            calc_breakdown=calc_breakdown,
        ))

    phases.sort(key=lambda p: -p.danger_score)

    # PM2.5 ↔ hotspot correlation (best-effort, requires both histories)
    correlation = _build_correlation(hotspot_history or [], pm25_history or [])

    source_label = f"thaicfnet.org ({len(cf_list)} ป่าชุมชน)" if cf_list else "ไม่มีข้อมูลป่าชุมชน"

    # Flat per-forest risk (every forest, not just ones near a before/during
    # district) — lets the map colour every community-forest marker by its
    # own fuel risk instead of one flat colour per district.
    danger_by_district = {p.district: p.danger_score for p in phases}
    fallback_danger = (sum(danger_by_district.values()) / len(danger_by_district)) if danger_by_district else 0.3
    forest_risk: list[ForestRisk] = []
    for cf in cf_list:
        base_danger = danger_by_district.get(_normalize_district(cf.amphoe), fallback_danger)
        nearest_km = _nearest_hotspot_km(cf.latitude, cf.longitude, recent_hotspots)
        forest_risk.append(ForestRisk(
            forest_id=cf.forest_id,
            name=cf.name,
            amphoe=cf.amphoe,
            latitude=cf.latitude,
            longitude=cf.longitude,
            danger_score=_forest_danger_score(base_danger, nearest_km),
            nearest_hotspot_km=round(nearest_km, 1) if nearest_km is not None else None,
            fire_management_active=cf.fire_management_active,
        ))

    # Tambon-level fire watch — same district-base-danger + hotspot-proximity
    # boost as forest_risk, but keyed to tambon centroids so the map can show
    # a warning symbol at the ตำบล drill-down level, not just per district.
    tambon_warnings: list[TambonWarning] = []
    for t in _TAMBON_CENTROIDS:
        base_danger = danger_by_district.get(_normalize_district(t["amphoe"]), fallback_danger)
        nearest_km = _nearest_hotspot_km(t["latitude"], t["longitude"], recent_hotspots)
        score = _forest_danger_score(base_danger, nearest_km)
        tambon_phase = "during" if score >= _DURING_FLOOR else "before" if score >= _YELLOW_THRESHOLD else "normal"
        tambon_warnings.append(TambonWarning(
            tcode=t["tcode"],
            tambon=t["tambon"],
            amphoe=t["amphoe"],
            latitude=t["latitude"],
            longitude=t["longitude"],
            danger_score=score,
            phase=tambon_phase,
            nearest_hotspot_km=round(nearest_km, 1) if nearest_km is not None else None,
        ))

    return FirePhaseResponse(
        generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_mode="DERIVED",
        phases=phases,
        notes=[
            "ระยะเหลือง/แดงคำนวณจากจุดความร้อนจริง + ดัชนีเชื้อเพลิงรายอำเภอ + ความชื้นอากาศสด "
            "เป็นตัวช่วยประเมิน ไม่ใช่คำเตือนทางการ",
            "การลามไฟประมาณจากสูตร Rothermel + ทิศลม + ความชัน เป็นค่าประมาณเท่านั้น",
            "ระยะใกล้ป่าชุมชนใช้ proximity จากพิกัด POINT ของ thaicfnet.org ยังไม่มี polygon เขตอำนาจจริง",
            "ระยะ 'หลังไฟ' (เทา) มาจาก dNBR Sentinel-2 — แสดงเมื่อเชื่อม Copernicus แล้ว",
            "คะแนนความเสี่ยงรายป่าชุมชน (forest_risk) = คะแนนอำเภอฐาน + ระยะใกล้จุดความร้อนจริง "
            "ยังไม่ใช่แบบจำลองเชื้อเพลิงระดับแปลง เป็นตัวช่วยจัดลำดับความสนใจเท่านั้น",
            "เฝ้าระวังระดับตำบล (tambon_warnings) ใช้คะแนนฐานเดียวกับอำเภอแม่ + ระยะใกล้จุดความร้อนจริง "
            "ตำบลในอำเภอเดียวกันจึงมีคะแนนต่างกันได้ตามความใกล้ไฟ ไม่ใช่ประกาศเตือนภัยทางการ",
        ],
        community_forests_source=source_label,
        fire_pm25_correlation=correlation,
        forest_risk=forest_risk,
        tambon_warnings=tambon_warnings,
    )


def _build_correlation(
    hotspot_history: list[tuple[str, int]],
    pm25_history: list[tuple[str, float]],
) -> list:
    """Cross-reference daily hotspot counts with PM2.5 readings.

    Returns list of FirePm25Correlation for days where hotspot_count > 3,
    annotating whether PM2.5 on the same day or next day was elevated (>37.5).
    """
    from app.models import FirePm25Correlation

    if not hotspot_history or not pm25_history:
        return []

    pm25_by_date = {date: val for date, val in pm25_history}
    result = []
    for date, count in hotspot_history:
        if count <= 3:
            continue
        same_day = pm25_by_date.get(date)
        # Next calendar day
        try:
            from datetime import date as dt_date
            next_day = (dt_date.fromisoformat(date) + timedelta(days=1)).isoformat()
        except Exception:
            next_day = None
        next_pm = pm25_by_date.get(next_day) if next_day else None
        elevated = (same_day is not None and same_day > 37.5) or (next_pm is not None and next_pm > 37.5)
        result.append(FirePm25Correlation(
            date=date,
            hotspot_count=count,
            pm25_same_day=same_day,
            pm25_next_day=next_pm,
            elevated=elevated,
        ))

    return sorted(result, key=lambda r: r.date, reverse=True)[:30]
