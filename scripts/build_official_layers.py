"""Sync the RECOFTC supplied community forest boundaries to the React map.

The backend GeoJSON is the single source for the forest count and geometry.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "data" / "community-forests-chiangmai.geojson"
OUTPUT = ROOT / "frontend" / "src" / "data" / "community-forests-official.json"


def build_community_forests() -> dict:
    features = json.loads(SOURCE.read_text(encoding="utf-8"))["features"]
    forests = []
    for feature in features:
        props = feature["properties"]
        geometry = feature["geometry"]
        if geometry["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"Forest {props.get('id')} has no polygon boundary")
        forests.append({
            "id": str(props["id"]),
            "sourceId": str(props["id"]),
            "source": "Community forest boundary shapefile received from RECOFTC",
            "name": props.get("name") or props.get("village") or "ป่าชุมชน",
            "village": props.get("village") or "",
            "moo": props.get("moo") or "",
            "tambon": props.get("tambon") or "",
            "amphoe": props.get("amphoe") or "",
            "lat": props["lat"],
            "lng": props["lng"],
            "areaRai": props.get("areaRai") or 0,
            "boundary": geometry,
        })
    return {
        "summary": {
            "source": "Community forest boundary shapefile received from RECOFTC",
            "sourceMode": "SNAPSHOT",
            "geometryType": "Polygon",
            "recordCount": len(forests),
        },
        "forests": forests,
    }


def main() -> None:
    payload = build_community_forests()
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(payload['forests'])} boundaries to {OUTPUT}")


if __name__ == "__main__":
    main()
