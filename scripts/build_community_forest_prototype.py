from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source"
FRONTEND_DATA = ROOT / "frontend" / "src" / "data"

RFD_KML = SOURCE_DIR / "rfd-community-forest.kml"
THAICFNET_JSON = SOURCE_DIR / "thaicfnet-chiangmai.json"
DISTRICTS_JSON = FRONTEND_DATA / "chiangmai-districts.json"

COMMUNITY_OUT = FRONTEND_DATA / "community-forests-prototype.json"
ZONES_OUT = FRONTEND_DATA / "fire-management-zones-prototype.json"


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def list_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [clean_text(item) for item in value if clean_text(item)]


def normalize_district(value: str) -> str:
    name = clean_text(value)
    name = name.replace("อำเภอ", "").replace("กิ่ง", "").strip()
    if name == "หัลยาณิวัฒนา":
        return "กัลยาณิวัฒนา"
    return name


def parse_kml_description(description: str) -> dict[str, str]:
    text = html.unescape(description or "")
    parts = [part.strip() for part in re.split(r"\s*<br>\s*", text) if part.strip()]
    result: dict[str, str] = {}
    if parts:
        result["displayName"] = parts[0]
    keys = [
        "FID",
        "Plot_No",
        "Tambon",
        "Amphoe",
        "Province",
        "Area__Rai_",
        "Area__Ngan",
        "Area__Tara",
        "CMF_Name",
        "Village_Na",
        "Moo",
    ]
    for part in parts[1:]:
        for key in keys:
            if part.startswith(key):
                result[key] = part.removeprefix(key).strip()
                break
    return result


def area_to_radius(area_rai: float) -> int:
    if area_rai <= 0:
        return 650
    square_meters = area_rai * 1600
    radius = math.sqrt(square_meters / math.pi)
    return max(450, min(2600, round(radius)))


def circle_polygon(lat: float, lng: float, radius_km: float = 11.0, steps: int = 40) -> dict:
    coords: list[list[float]] = []
    lat_degree_km = 110.574
    lng_degree_km = 111.320 * math.cos(math.radians(lat))
    for index in range(steps):
        angle = (index / steps) * math.tau
        coords.append([
            lng + (math.cos(angle) * radius_km) / lng_degree_km,
            lat + (math.sin(angle) * radius_km) / lat_degree_km,
        ])
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def thai_cf_records() -> tuple[int, list[dict]]:
    records = json.loads(THAICFNET_JSON.read_text(encoding="utf-8-sig"))
    output: list[dict] = []
    for record in records:
        payload = record.get("json", {})
        geo = payload.get("geo", {}) if isinstance(payload.get("geo"), dict) else {}
        lat = geo.get("geoLat") or geo.get("lat")
        lng = geo.get("geoLong") or geo.get("lng") or geo.get("lon")
        if not lat or not lng:
            continue

        address = payload.get("addresses", [[]])
        address = address[0] if address and isinstance(address[0], list) else []
        village = clean_text(address[1] if len(address) > 1 else "")
        tambon = clean_text(address[2] if len(address) > 2 else "")
        amphoe = normalize_district(address[3] if len(address) > 3 else "")
        province = clean_text(address[4] if len(address) > 4 else "")
        if province != "เชียงใหม่":
            continue

        area_rai = float(payload.get("area") or 0)
        fire_activities = list_values(payload.get("fireManagementActivityCheck"))
        forest_types = list_values(payload.get("forestType"))
        deed_types = list_values(payload.get("deedType"))
        management_plan = list_values(payload.get("managementPlanCheck"))
        fire_management = list_values(payload.get("fireManagementCheck"))
        committee = payload.get("committee", {}) if isinstance(payload.get("committee"), dict) else {}

        output.append(
            {
                "id": f"thaicfnet-{record.get('id')}",
                "sourceId": record.get("id"),
                "source": "Thaicfnet citizen database",
                "name": clean_text(payload.get("name")) or clean_text(payload.get("communityForestName")),
                "village": village,
                "tambon": tambon,
                "amphoe": amphoe,
                "province": province,
                "lat": float(lat),
                "lng": float(lng),
                "areaRai": area_rai,
                "estimatedBoundaryRadiusM": area_to_radius(area_rai),
                "fireManagement": bool(fire_management),
                "fireActivities": fire_activities,
                "managementPlan": bool(management_plan),
                "managementPlanYear": clean_text(
                    (payload.get("managementPlan") or {}).get("managementPlanYr")
                    if isinstance(payload.get("managementPlan"), dict)
                    else ""
                ),
                "forestTypes": forest_types,
                "deedTypes": deed_types,
                "households": int(payload.get("householdNum") or 0),
                "villagesCount": int(payload.get("moobaanNum") or 1),
                "committeeTotal": int(committee.get("committeeTotal") or 0),
            }
        )
    return len(records), output


def rfd_points() -> list[dict]:
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    root = ET.parse(RFD_KML).getroot()
    points: list[dict] = []
    for placemark in root.findall(".//k:Placemark", ns):
        description = placemark.findtext("k:description", default="", namespaces=ns)
        fields = parse_kml_description(description)
        if fields.get("Province") != "เชียงใหม่":
            continue
        coords = placemark.findtext(".//k:coordinates", default="", namespaces=ns).strip()
        if not coords:
            continue
        lng, lat, *_ = [float(part) for part in coords.split(",")]
        area = 0.0
        try:
            area = float(fields.get("Area__Rai_", 0) or 0)
        except ValueError:
            area = 0.0
        points.append(
            {
                "name": fields.get("CMF_Name") or fields.get("displayName") or placemark.findtext("k:name", default="", namespaces=ns),
                "village": fields.get("Village_Na", ""),
                "tambon": fields.get("Tambon", ""),
                "amphoe": normalize_district(fields.get("Amphoe", "")),
                "lat": lat,
                "lng": lng,
                "areaRai": area,
            }
        )
    return points


def district_feature_map() -> dict[str, dict]:
    data = json.loads(DISTRICTS_JSON.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for feature in data.get("features", []):
        name = feature.get("properties", {}).get("nameTh", "")
        amphoe = normalize_district(name)
        out[amphoe] = feature
    return out


def make_health_score(rfd_count: int, detail_count: int, activity_count: int, area_rai: float) -> tuple[str, int]:
    scale_risk = min(38, round(rfd_count * 0.38))
    area_risk = min(22, round(area_rai / 9000))
    proof_bonus = min(30, activity_count * 6 + detail_count * 2)
    raw = 72 - scale_risk - area_risk + proof_bonus
    score = max(18, min(92, raw))
    if score >= 70:
        return "Green", score
    if score >= 48:
        return "Yellow", score
    return "Red", score


def main() -> None:
    FRONTEND_DATA.mkdir(parents=True, exist_ok=True)

    total_thaicf_records, detailed = thai_cf_records()
    rfd = rfd_points()
    district_features = district_feature_map()

    rfd_by_district: dict[str, list[dict]] = defaultdict(list)
    for item in rfd:
        rfd_by_district[item["amphoe"]].append(item)

    detail_by_district: dict[str, list[dict]] = defaultdict(list)
    for item in detailed:
        detail_by_district[item["amphoe"]].append(item)

    activity_count = sum(1 for item in detailed if item["fireActivities"] or item["fireManagement"])
    summary = {
        "generatedAt": "2026-06-06",
        "province": "เชียงใหม่",
        "officialInfographicCount": 573,
        "officialInfographicAreaRai": 812848,
        "rfdCoordinatePoints": len(rfd),
        "thaicfnetDetailedForests": total_thaicf_records,
        "thaicfnetGeocodedForests": len(detailed),
        "detailedForestsWithFireManagement": activity_count,
        "sourceNotes": [
            "RFD KML is point geometry only; prototype boundaries are estimated buffers.",
            "Thaicfnet records provide community activity and management-plan detail for 52 Chiang Mai forests.",
            "Official infographic reports 573 community forests in Chiang Mai as of Dec 2023.",
        ],
    }

    community_output = {
        "summary": summary,
        "forests": sorted(detailed, key=lambda item: (item["amphoe"], item["tambon"], item["name"])),
    }

    zones: list[dict] = []
    all_districts = sorted(set(district_features) | set(rfd_by_district) | set(detail_by_district))
    for district in all_districts:
        feature = district_features.get(district)
        rfd_items = rfd_by_district.get(district, [])
        detail_items = detail_by_district.get(district, [])
        area = sum(float(item.get("areaRai") or 0) for item in rfd_items)
        activities = sum(1 for item in detail_items if item["fireActivities"] or item["fireManagement"])
        health, score = make_health_score(len(rfd_items), len(detail_items), activities, area)
        top_activities = Counter(
            activity for item in detail_items for activity in item.get("fireActivities", [])
        ).most_common(3)
        centroid_lat = mean([item["lat"] for item in rfd_items]) if rfd_items else None
        centroid_lng = mean([item["lng"] for item in rfd_items]) if rfd_items else None
        zones.append(
            {
                "id": f"fmz-{district}",
                "district": district,
                "name": f"เขตจัดการไฟ อ.{district}",
                "health": health,
                "healthScore": score,
                "rfdCoordinatePoints": len(rfd_items),
                "detailedForests": len(detail_items),
                "fireManagementForests": activities,
                "estimatedAreaRai": round(area),
                "prototypeBoundary": "district polygon",
                "centroid": [centroid_lat, centroid_lng] if centroid_lat and centroid_lng else None,
                "topActivities": [{"name": name, "count": count} for name, count in top_activities],
                "geometry": feature["geometry"] if feature else circle_polygon(centroid_lat or 18.78, centroid_lng or 98.98),
            }
        )

    zones.sort(key=lambda item: (-item["rfdCoordinatePoints"], item["district"]))
    zone_output = {"summary": summary, "zones": zones}

    COMMUNITY_OUT.write_text(json.dumps(community_output, ensure_ascii=False, indent=2), encoding="utf-8")
    ZONES_OUT.write_text(json.dumps(zone_output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {COMMUNITY_OUT.relative_to(ROOT)} ({len(detailed)} forests)")
    print(f"wrote {ZONES_OUT.relative_to(ROOT)} ({len(zones)} zones)")
    print(f"rfd Chiang Mai coordinate points: {len(rfd)}")


if __name__ == "__main__":
    main()
