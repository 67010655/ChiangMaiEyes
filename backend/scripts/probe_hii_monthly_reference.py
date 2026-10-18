"""Read provider monthly legal-forest burn positives; zero is not a negative.

The public numeric B2F raster has no observation/cloud mask. Return None for
observation coverage so callers cannot silently use its zeros as no-burn truth.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request

import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "output/spread-deps"))
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling


def download_numeric_tile(grid, yyyymm, folder, max_bytes=3_000_000):
    assert re.fullmatch(r"\d{2}[A-Z]{3}", grid)
    assert re.fullmatch(r"20\d{4}", yyyymm)
    datetime.strptime(yyyymm, "%Y%m")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"BURNSCAR_{grid}_20M_{yyyymm}_B2F.tif"
    path = folder / name
    receipt_path = path.with_suffix(".receipt.json")
    url = f"https://tamroypao.hii.or.th/product/B2F/{yyyymm[:4]}/{name}"
    if path.exists():
        data = path.read_bytes()
        receipt = json.loads(receipt_path.read_text(encoding="utf8")) if receipt_path.exists() else {}
    else:
        with urlopen(Request(url, method="HEAD"), timeout=45) as r:
            if int(r.headers.get("Content-Length", "0")) > max_bytes:
                raise ValueError(f"Tile exceeds configured bounded download: {name}")
        with urlopen(url, timeout=60) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError(f"Tile exceeds configured bounded download: {name}")
            receipt = {"http_status": r.status, "last_modified": r.headers.get("Last-Modified"),
                       "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        path.write_bytes(data)
    receipt.update(url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                   period=yyyymm, product="HII_B2F_monthly_legal_forest", positive_class=6000)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf8")
    return path, receipt


def read_case_monthly(meta, folder, month=None, download=True):
    """Return (positive_mask20m, observation_coverage=None, receipt).

    Month defaults to initial-image month; callers must explicitly request each
    month for a cross-month interval. A monthly positive may predate the origin
    and is not exact-interval ground truth. All non-positive pixels are unknown.
    The target grid is the case UTM47 bounds at20m, not a20m accuracy guarantee.
    """
    month = month or meta["initial_acquisition"][:7].replace("-", "")
    match = re.search(r"_T(\d{2}[A-Z]{3})_", meta["initial_scene"])
    if not match:
        raise ValueError("Case has no Sentinel MGRS tile identifier")
    grid = match.group(1)
    folder = Path(folder)
    if download:
        primary, _ = download_numeric_tile(grid, month, folder)
    else:
        primary = folder / f"BURNSCAR_{grid}_20M_{month}_B2F.tif"
        if not primary.exists():
            raise FileNotFoundError(primary)
    bounds = meta["bounds_utm47"]
    width = round((bounds[2]-bounds[0])/20)
    height = round((bounds[3]-bounds[1])/20)
    transform = from_bounds(*bounds, width, height)
    positive = np.zeros((height, width), dtype=bool)
    footprint = np.zeros((height, width), dtype=bool)
    sources = []
    # Include only already-downloaded adjoining tiles; never mosaic by summing
    # overlapping Sentinel tile areas (footprint overlaps are substantial).
    for path in sorted(folder.glob(f"BURNSCAR_*_20M_{month}_B2F.tif")):
        with rasterio.open(path) as source:
            from rasterio.warp import transform_bounds
            b = transform_bounds("EPSG:32647", source.crs, *bounds)
            s = source.bounds
            if b[2] <= s.left or b[0] >= s.right or b[3] <= s.bottom or b[1] >= s.top:
                continue
            a = source.read(1)
            classes = np.unique(a)
            if not set(classes.tolist()) <= {0, 6000}:
                raise ValueError(f"Unexpected B2F classes: {classes}")
            projected = np.zeros((height, width), dtype=np.int16)
            reproject(a, projected, src_transform=source.transform, src_crs=source.crs,
                      dst_transform=transform, dst_crs="EPSG:32647", resampling=Resampling.nearest)
            covered = np.zeros((height, width), dtype=np.uint8)
            reproject(np.ones_like(a, dtype=np.uint8), covered, src_transform=source.transform,
                      src_crs=source.crs, dst_transform=transform, dst_crs="EPSG:32647",
                      resampling=Resampling.nearest)
            positive |= projected == 6000
            footprint |= covered > 0
            sources.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "crs": str(source.crs), "nodata": source.nodata, "classes": classes.tolist()})
    receipt = {"case_id": meta["id"], "period_yyyymm": month,
               "period_match": "monthly cumulative; not exact image-to-image growth",
               "crs": "EPSG:32647", "pixel_size_m": 20,
               "shape": [height, width], "bounds": bounds,
               "positive_pixels": int(positive.sum()), "positive_area_km2": float(positive.sum()*0.0004),
               "raster_footprint_fraction": float(footprint.mean()),
               "observation_coverage_available": False,
               "negative_semantics": "unknown; zero conflates no-classification/no-burn/nonforest and observation gaps",
               "formal_forest_accuracy_validation": "provider explicitly states not formally evaluated",
               "scope": "legal forest; differs from WorldCover vegetation and community forest boundaries",
               "sources": sources}
    return positive, None, receipt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", default="2026-03-29")
    parser.add_argument("--month", default="202603")
    parser.add_argument("--manifest", type=Path, default=ROOT / "output/fire-perimeter-loop-20261017/case-manifest.json")
    parser.add_argument("--folder", type=Path, default=ROOT / "output/fire-engineering-20261018/hii-qa")
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text(encoding="utf8"))
    case = next(x for x in cases if x["id"] == args.case_id)
    mask, coverage, receipt = read_case_monthly(case, args.folder, args.month, download=not args.local_only)
    assert coverage is None
    args.folder.mkdir(parents=True, exist_ok=True)
    stem = f"{args.case_id}-{args.month}"
    np.savez_compressed(args.folder / f"{stem}-positive-only.npz", positive_mask=mask)
    (args.folder / f"{stem}-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    print(json.dumps(receipt, indent=2))
