"""Fire-lifecycle phase classifier (Phase 6).

Assigns each Chiang Mai district a phase in the disaster-management cycle:
  - during (red)   — active hotspots in the district right now
  - before (yellow) — no active fire but elevated danger (dry fuel + dry air)
  - normal (green)  — low danger, no fire
  - after  (grey)   — recently burned; needs Sentinel-2 dNBR burn-severity, which
                      is not wired yet, so the classifier does NOT assign it (the
                      colour/legend exists for the upcoming Phase 6.2).

Every "before" decision is a transparent, deterministic blend of real inputs
(active hotspot count + district fuel/history physics + live air humidity/rain),
mirroring the risk-score discipline. It is a decision aid, never an official
warning. See memory: project-data-provenance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.fire_spread_physics import DISTRICT_PHYSICS
from app.models import DistrictFirePhase, FirePhaseResponse, HotspotResponse, WeatherResponse

_PHASE_COLOR = {"normal": "green", "before": "yellow", "during": "red", "after": "grey"}
_YELLOW_THRESHOLD = 0.55
_DRY_AIR_GATE = 0.35  # below this, air is too moist for elevated fire danger
_DURING_FLOOR = 0.85  # an active fire is always high danger regardless of the blend


def _normalize_district(name: str | None) -> str:
    return (name or "").replace("อำเภอ", "").replace("อ.", "").strip()


def _air_dryness(weather: WeatherResponse) -> float:
    """0 (humid/wet) .. 1 (very dry). Recent rain pulls it down."""
    humidity = weather.humidity_percent if weather.humidity_percent is not None else 50.0
    dryness = max(0.0, min(1.0, (100.0 - humidity) / 100.0))
    if (weather.rain_today_mm or 0) > 1.0:
        dryness *= 0.5
    return dryness


def classify_fire_phases(hotspots: HotspotResponse, weather: WeatherResponse) -> FirePhaseResponse:
    active_by_district: dict[str, int] = {}
    for item in hotspots.items:
        name = _normalize_district(item.district)
        if name:
            active_by_district[name] = active_by_district.get(name, 0) + 1

    dryness = _air_dryness(weather)
    humidity = weather.humidity_percent if weather.humidity_percent is not None else 50.0

    phases: list[DistrictFirePhase] = []
    for district, phys in DISTRICT_PHYSICS.items():
        active = active_by_district.get(district, 0)
        fuel_norm = min(1.0, phys["fuel_flammability"] / 1.8)
        history_norm = min(1.0, max(0.0, (phys["history_multiplier"] - 1.0) / 0.5))
        danger = round(0.4 * fuel_norm + 0.2 * history_norm + 0.4 * dryness, 2)

        if active > 0:
            phase = "during"
            danger = max(danger, _DURING_FLOOR)
            reasons = [f"พบจุดความร้อน {active} จุดในพื้นที่ตอนนี้"]
        elif dryness < _DRY_AIR_GATE:
            # Moist air (e.g. rainy season): fuel won't ignite, so no "before"
            # danger no matter how flammable the forest is — keep anxiety low.
            phase = "normal"
            reasons = [f"อากาศชื้น ความชื้น {humidity:.0f}% เชื้อเพลิงไม่แห้งพอจะติดไฟ"]
        elif danger >= _YELLOW_THRESHOLD:
            phase = "before"
            reasons = [
                f"เชื้อเพลิงติดไฟง่าย ({phys['history_level']})",
                f"อากาศแห้ง ความชื้น {humidity:.0f}%",
            ]
        else:
            phase = "normal"
            reasons = ["ยังไม่มีจุดความร้อน และดัชนีความเสี่ยงอยู่ระดับต่ำ"]

        phases.append(
            DistrictFirePhase(
                district=district,
                phase=phase,
                color=_PHASE_COLOR[phase],
                danger_score=danger,
                active_hotspots=active,
                reasons=reasons,
            )
        )

    phases.sort(key=lambda p: -p.danger_score)
    return FirePhaseResponse(
        generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_mode="DERIVED",
        phases=phases,
        notes=[
            "ระยะเหลือง/แดงคำนวณจากจุดความร้อนจริง + ดัชนีเชื้อเพลิงรายอำเภอ + ความชื้นอากาศสด "
            "เป็นตัวช่วยประเมิน ไม่ใช่คำเตือนทางการ",
            "ระยะ 'หลังไฟ' (เทา) ต้องใช้ดัชนีรอยไหม้ dNBR จาก Sentinel-2 ซึ่งยังไม่เชื่อม (Phase 6.2)",
        ],
    )
