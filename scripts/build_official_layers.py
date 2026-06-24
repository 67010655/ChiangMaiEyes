from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source"
FRONTEND_DATA = ROOT / "frontend" / "src" / "data"
BACKEND_DATA = ROOT / "backend" / "data"

RFD_KML = SOURCE_DIR / "rfd-community-forest.kml"
COMMUNITY_OUT = FRONTEND_DATA / "community-forests-official.json"
BACKEND_COMMUNITY_OUT = BACKEND_DATA / "community-forests-official.json"


def clean_text(value: object) -> str:
    return str(value or "").strip()


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


def parse_float(value: str, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def area_to_radius(area_rai: float) -> int:
    if area_rai <= 0:
        return 650
    square_meters = area_rai * 1600
    radius = math.sqrt(square_meters / math.pi)
    return max(450, min(2600, round(radius)))


def build_rfd_community_forests() -> dict:
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    root = ET.parse(RFD_KML).getroot()
    forests: list[dict] = []
    province_total = 0

    for placemark in root.findall(".//k:Placemark", ns):
        fields = parse_kml_description(
            placemark.findtext("k:description", default="", namespaces=ns)
        )
        if fields.get("Province") != "เชียงใหม่":
            continue
        province_total += 1

        coords = placemark.findtext(".//k:coordinates", default="", namespaces=ns).strip()
        if not coords:
            continue
        lng, lat, *_ = [parse_float(part) for part in coords.split(",")]
        if lat < 15 or lat > 21 or lng < 96 or lng > 101:
            continue

        area_rai = parse_float(fields.get("Area__Rai_", "0"))
        area_ngan = parse_float(fields.get("Area__Ngan", "0"))
        area_tarang_wa = parse_float(fields.get("Area__Tara", "0"))
        total_area_rai = area_rai + area_ngan / 4 + area_tarang_wa / 400
        fid = clean_text(fields.get("FID"))
        plot_no = clean_text(fields.get("Plot_No"))
        name = clean_text(fields.get("CMF_Name")) or clean_text(fields.get("displayName"))

        forests.append(
            {
                "id": f"rfd-cf-{fid or len(forests) + 1}",
                "sourceId": fid,
                "plotNo": plot_no,
                "source": "Royal Forest Department community forest coordinates KML",
                "sourceMode": "SNAPSHOT",
                "geometryType": "Point",
                "boundaryStatus": "point-only; official polygon boundary not yet available",
                "name": name,
                "village": clean_text(fields.get("Village_Na")),
                "moo": clean_text(fields.get("Moo")),
                "tambon": clean_text(fields.get("Tambon")),
                "amphoe": clean_text(fields.get("Amphoe")),
                "province": clean_text(fields.get("Province")),
                "areaRai": round(total_area_rai, 2),
                "estimatedBoundaryRadiusM": area_to_radius(total_area_rai),
                "lat": lat,
                "lng": lng,
            }
        )

    forests.sort(key=lambda item: (item["amphoe"], item["tambon"], item["name"]))
    return {
        "summary": {
            "source": "Royal Forest Department community forest coordinates KML",
            "sourceMode": "SNAPSHOT",
            "province": "เชียงใหม่",
            "geometryType": "Point",
            "boundaryStatus": "official point coordinates only; official polygon boundaries must be requested from agencies",
            "recordCount": len(forests),
            "provinceRecordCountBeforeCoordinateFilter": province_total,
        },
        "forests": forests,
    }


def main() -> None:
    payload = build_rfd_community_forests()
    for path in (COMMUNITY_OUT, BACKEND_COMMUNITY_OUT):
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"Wrote {COMMUNITY_OUT}")
    print(f"Wrote {BACKEND_COMMUNITY_OUT}")


if __name__ == "__main__":
    main()
