"""Convert Chiang Mai tambon shapefile into frontend/backend GeoJSON assets.

Source expected: "7 Tambon area.*" from the public Drive folder
"7 GIS เชียงใหม่ (CHIANG MAI) / 2 Boundary and Point".

The parser is intentionally dependency-free so the import can run on this
workspace without GDAL/pyshp.
"""

from __future__ import annotations

import argparse
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# The source shapefile predates the 2009 Galyani Vadhana district split and
# the ~2007 Doi Lo/Mae On กิ่งอำเภอ->อำเภอ promotions, so its amphoe_th/en/acode
# fields are stale for these 16 tambons (confirmed 2026-07-13 by computing each
# tambon polygon's TRUE intersection area against every real district polygon
# in chiangmai-districts.json — every one of these resolves at 68%+ land area,
# most 90%+ — not just a naive centroid guess). Applied here so a future
# re-import from the same stale source doesn't silently regress the fix.
_TCODE_AMPHOE_CORRECTIONS: dict[str, tuple[str, str, str]] = {
    # (amphoe_th, amphoe_en, acode)
    "502306": ("แม่ออน", "MAE ON", "5023"),
    "502304": ("แม่ออน", "MAE ON", "5023"),
    "502305": ("แม่ออน", "MAE ON", "5023"),
    "502301": ("แม่ออน", "MAE ON", "5023"),
    "502303": ("แม่ออน", "MAE ON", "5023"),
    "502302": ("แม่ออน", "MAE ON", "5023"),
    "502403": ("ดอยหล่อ", "DOI LO", "5024"),
    "502401": ("ดอยหล่อ", "DOI LO", "5024"),
    "502404": ("ดอยหล่อ", "DOI LO", "5024"),
    "502402": ("ดอยหล่อ", "DOI LO", "5024"),
    "500306": ("กัลยาณิวัฒนา", "GALYANI VADHANA", "5025"),
    "500310": ("กัลยาณิวัฒนา", "GALYANI VADHANA", "5025"),
    "500309": ("กัลยาณิวัฒนา", "GALYANI VADHANA", "5025"),
    "500511": ("สันกำแพง", "SAN KAMPHAENG", "5013"),
    "500510": ("สันกำแพง", "SAN KAMPHAENG", "5013"),
    "500509": ("สันกำแพง", "SAN KAMPHAENG", "5013"),
}

DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1z6ZWmM80NY9ZgwP6KuTv7wYGVUa6JnQA"
SOURCE_FILE_IDS = {
    "7 Tambon area.shp": "1ujW7BAIVFG-Ib8lTLO6LoG_-WnEyQvF2",
    "7 Tambon area.dbf": "133JsKr5JlHJmiUw7l8nZn-DyfKXl1GKv",
    "7 Tambon area.shx": "17q0F0y_paAj19QQLYf_r7awHZ36HBoP5",
    "7 Tambon area.prj": "1ZcyZd5fiJ5-Ojhmg13U3x7bnJMgvsLGT",
    "7 Tambon area.cpg": "1-M0Q9GIGY1ZDuMTehJ1vZFQ1iWmi5Rb1",
}


def _decode_dbf_text(raw: bytes, encoding: str) -> str:
    raw = raw.strip().rstrip(b"\x00")
    if not raw:
        return ""
    try:
        return raw.decode(encoding).strip()
    except UnicodeDecodeError:
        return raw.decode("cp874", errors="replace").strip()


def read_dbf(path: Path, encoding: str = "utf-8") -> list[dict[str, str]]:
    data = path.read_bytes()
    record_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]

    fields: list[tuple[str, str, int, int]] = []
    pos = 32
    while pos < header_len and data[pos] != 0x0D:
        desc = data[pos : pos + 32]
        name = desc[:11].split(b"\x00", 1)[0].decode("ascii", errors="ignore")
        fields.append((name, chr(desc[11]), desc[16], desc[17]))
        pos += 32

    records: list[dict[str, str]] = []
    for idx in range(record_count):
        start = header_len + idx * record_len
        raw_record = data[start : start + record_len]
        if not raw_record or raw_record[0:1] == b"*":
            continue
        offset = 1
        record: dict[str, str] = {}
        for name, field_type, field_len, _decimal_count in fields:
            raw = raw_record[offset : offset + field_len]
            offset += field_len
            text = _decode_dbf_text(raw, encoding)
            record[name] = text
        records.append(record)
    return records


def read_polygon_shp(path: Path) -> list[list[list[list[float]]]]:
    data = path.read_bytes()
    shapes: list[list[list[list[float]]]] = []
    pos = 100
    while pos + 8 <= len(data):
        _record_number, content_words = struct.unpack(">2i", data[pos : pos + 8])
        pos += 8
        content_len = content_words * 2
        content = data[pos : pos + content_len]
        pos += content_len
        if len(content) < 44:
            continue

        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type == 0:
            shapes.append([])
            continue
        if shape_type not in {5, 15, 25}:  # Polygon, PolygonZ, PolygonM
            raise ValueError(f"Unsupported shapefile shape type: {shape_type}")

        num_parts, num_points = struct.unpack("<2i", content[36:44])
        parts_start = 44
        points_start = parts_start + num_parts * 4
        parts = list(struct.unpack(f"<{num_parts}i", content[parts_start:points_start]))
        points_raw = content[points_start : points_start + num_points * 16]
        points = [
            [round(x, 7), round(y, 7)]
            for x, y in struct.iter_unpack("<2d", points_raw)
        ]

        rings: list[list[list[float]]] = []
        for part_idx, part_start in enumerate(parts):
            part_end = parts[part_idx + 1] if part_idx + 1 < len(parts) else len(points)
            ring = points[part_start:part_end]
            if ring and ring[0] != ring[-1]:
                ring = [*ring, ring[0]]
            if len(ring) >= 4:
                rings.append(ring)
        shapes.append(rings)
    return shapes


def _feature(record: dict[str, str], rings: list[list[list[float]]]) -> dict[str, Any]:
    p_code = record.get("P_CODE", "").zfill(2)
    a_code = record.get("A_CODE", "").zfill(2)
    t_code = record.get("T_CODE", "").zfill(2)
    full_tcode = f"{p_code}{a_code}{t_code}" if p_code and a_code and t_code else ""

    amphoe_th = record.get("A_NAME_T", "")
    amphoe_en = record.get("A_NAME_E", "")
    acode = f"{p_code}{a_code}" if p_code and a_code else ""
    source = "Drive: 7 Tambon area shapefile"
    fix = _TCODE_AMPHOE_CORRECTIONS.get(full_tcode)
    if fix:
        amphoe_th, amphoe_en, acode = fix
        source += (
            " | amphoe corrected: original shapefile predates the 2009 Galyani Vadhana "
            "district split and the Doi Lo/Mae On กิ่งอำเภอ promotions; verified against "
            "chiangmai-districts.json via true polygon intersection area"
        )

    return {
        "type": "Feature",
        "properties": {
            "pcode": p_code,
            "acode": acode,
            "tcode": full_tcode,
            "province_th": record.get("P_NAME_T", ""),
            "province_en": record.get("P_NAME_E", ""),
            "amphoe_th": amphoe_th,
            "amphoe_en": amphoe_en,
            "tambon_th": record.get("T_NAME_T", ""),
            "tambon_en": record.get("T_NAME_E", ""),
            "source": source,
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[ring] for ring in rings],
        },
    }


def build_geojson(source_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cpg_path = source_dir / "Tambon area.cpg"
    encoding = cpg_path.read_text(encoding="utf-8").strip() if cpg_path.exists() else "utf-8"
    records = read_dbf(source_dir / "Tambon area.dbf", encoding=encoding)
    shapes = read_polygon_shp(source_dir / "Tambon area.shp")
    if len(records) != len(shapes):
        raise ValueError(f"DBF/SHP feature count mismatch: {len(records)} != {len(shapes)}")

    features = [_feature(record, rings) for record, rings in zip(records, shapes) if rings]
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "source_name": "7 Tambon area shapefile",
        "source_folder": DRIVE_FOLDER_URL,
        "source_file_ids": SOURCE_FILE_IDS,
        "generated_at": now,
        "crs": "WGS 84 / EPSG:4326",
        "encoding": encoding,
        "feature_count": len(features),
        "license_note": (
            "Public Google Drive source did not expose an explicit license in the folder listing. "
            "Use with visible provenance until an official license is confirmed."
        ),
    }
    return {
        "type": "FeatureCollection",
        "name": "chiangmai_tambons",
        "metadata": metadata,
        "features": features,
    }, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--frontend-out", default=Path("frontend/public/chiangmai-tambons.geojson"), type=Path)
    parser.add_argument("--backend-out", default=Path("backend/app/data/chiangmai-tambons.geojson"), type=Path)
    args = parser.parse_args()

    geojson, metadata = build_geojson(args.source_dir)
    for path, payload in [
        (args.frontend_out, geojson),
        (args.backend_out, geojson),
        (args.frontend_out.with_suffix(".meta.json"), metadata),
        (args.backend_out.with_suffix(".meta.json"), metadata),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"wrote {len(geojson['features'])} tambon polygons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
