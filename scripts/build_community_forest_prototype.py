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
    name = name.replace("อำเภอ", "").replace("กิ่ง", "").replace("อ.", "").strip()
    if name == "หัลยาณิวัฒนา" or name == "กัลยานิวัฒนา" or name == "กัลยานืวัฒนา":
        return "กัลยาณิวัฒนา"
    if name == "แมก๋อย" or name == "แแมก๋อย":
        return "อมก๋อย"
    return name


def clean_name(name: str) -> str:
    if not name:
        return ""
    name = str(name).strip()
    # Remove common prefixes
    name = re.sub(r"^(ป่าชุมชน|บ้าน|ป่าชุมชนบ้าน)\s*", "", name)
    # Remove common suffixes / subtext
    name = re.sub(r"\s*หมู่ที่\s*\d+", "", name)
    name = re.sub(r"\s*ม\.\s*\d+", "", name)
    # Remove brackets
    name = re.sub(r"\(.*?\)", "", name)
    # Clean whitespace
    return "".join(name.split())


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
        
        # Skip invalid coordinates that are in the south (e.g. lat=8.175598)
        if lat < 15.0 or lat > 21.0 or lng < 96.0 or lng > 101.0:
            continue
            
        area = 0.0
        try:
            area = float(fields.get("Area__Rai_", 0) or 0)
        except ValueError:
            area = 0.0
        points.append(
            {
                "name": fields.get("CMF_Name") or fields.get("displayName") or placemark.findtext("k:name", default="", namespaces=ns),
                "clean_name": clean_name(fields.get("CMF_Name") or fields.get("displayName") or ""),
                "village": fields.get("Village_Na", ""),
                "clean_village": clean_name(fields.get("Village_Na", "")),
                "tambon": fields.get("Tambon", "").strip(),
                "amphoe": normalize_district(fields.get("Amphoe", "")),
                "lat": lat,
                "lng": lng,
                "areaRai": area,
            }
        )
    return points


def thai_cf_records(rfd_list: list[dict] = None) -> tuple[int, list[dict]]:
    records = json.loads(THAICFNET_JSON.read_text(encoding="utf-8-sig"))
    output: list[dict] = []
    
    # Pre-parse KML points for matching
    kml_by_name = {}
    kml_by_village = {}
    if rfd_list:
        for p in rfd_list:
            kml_by_name[(p["clean_name"], p["amphoe"])] = (p["lat"], p["lng"])
            if p["clean_village"]:
                kml_by_village[(p["clean_village"], p["amphoe"])] = (p["lat"], p["lng"])

    for record in records:
        payload = record.get("json", {})
        
        # Original geo
        geo = payload.get("geo", {}) if isinstance(payload.get("geo"), dict) else {}
        orig_lat = geo.get("geoLat") or geo.get("lat")
        orig_lng = geo.get("geoLong") or geo.get("lng") or geo.get("lon")
        
        # Clean coordinates
        lat = float(orig_lat) if orig_lat else None
        lng = float(orig_lng) if orig_lng else None
        
        # Address
        address = payload.get("addresses", [[]])
        address = address[0] if address and isinstance(address[0], list) else []
        village = clean_text(address[1] if len(address) > 1 else "")
        tambon = clean_text(address[2] if len(address) > 2 else "")
        amphoe = normalize_district(address[3] if len(address) > 3 else "")
        province = clean_text(address[4] if len(address) > 4 else "")
        if province != "เชียงใหม่":
            continue

        c_name = clean_text(payload.get("name")) or clean_text(payload.get("communityForestName"))
        c_clean = clean_name(c_name)
        c_clean_village = clean_name(village)
        
        # Check if original coordinate is mock fallback
        is_default = (lat is not None and lng is not None and 
                      ((abs(lat - 18.7816) < 0.001 and abs(lng - 99.0064) < 0.001) or 
                       (abs(lat - 18.775442) < 0.001 and abs(lng - 98.949493) < 0.001)))
        
        # Attempt matching against RFD KML coordinates if missing or using default fallback coords
        matched_coords = None
        if lat is None or lng is None or is_default:
            # 1. Match by clean name and district
            if (c_clean, amphoe) in kml_by_name:
                matched_coords = kml_by_name[(c_clean, amphoe)]
            # 2. Match by clean village and district
            elif (c_clean_village, amphoe) in kml_by_village:
                matched_coords = kml_by_village[(c_clean_village, amphoe)]
            # 3. Match by looser name (substring)
            else:
                for clean_k, a_k in kml_by_name:
                    if a_k == amphoe and (c_clean in clean_k or clean_k in c_clean):
                        matched_coords = kml_by_name[(clean_k, a_k)]
                        break
            
            if matched_coords:
                lat, lng = matched_coords
            elif is_default:
                # If it's a default center fallback, let's clear it to allow district centroid fallback
                lat, lng = None, None
        
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
                "name": c_name,
                "village": village,
                "tambon": tambon,
                "amphoe": amphoe,
                "province": province,
                "lat": lat,
                "lng": lng,
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

    rfd = rfd_points()
    total_thaicf_records, detailed = thai_cf_records(rfd)
    district_features = district_feature_map()

    rfd_by_district: dict[str, list[dict]] = defaultdict(list)
    for item in rfd:
        rfd_by_district[item["amphoe"]].append(item)

    # Calculate district centroids
    district_centroids = {}
    for district, items in rfd_by_district.items():
        if items:
            district_centroids[district] = (
                mean([item["lat"] for item in items]),
                mean([item["lng"] for item in items])
            )

    # Resolve coordinates fallbacks for unmatched detailed forests using district centroids
    for forest in detailed:
        if forest["lat"] is None or forest["lng"] is None:
            dist = forest["amphoe"]
            if dist in district_centroids:
                forest["lat"], forest["lng"] = district_centroids[dist]
            else:
                # Default fallback: Chiang Mai center
                forest["lat"], forest["lng"] = 18.78, 98.98

    detail_by_district: dict[str, list[dict]] = defaultdict(list)
    for item in detailed:
        detail_by_district[item["amphoe"]].append(item)

    activity_count = sum(1 for item in detailed if item["fireActivities"] or item["fireManagement"])
    summary = {
        "generatedAt": "2026-06-07",
        "province": "เชียงใหม่",
        "officialInfographicCount": 573,
        "officialInfographicAreaRai": 812848,
        "rfdCoordinatePoints": len(rfd),
        "thaicfnetDetailedForests": len(detailed),
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
