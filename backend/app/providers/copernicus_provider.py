"""Copernicus Data Space (CDSE) Sentinel-2 dryness provider.

Replaces the seeded NDVI/NDMI/NBR values with real Sentinel-2 zonal means using
the CDSE Sentinel Hub Statistical API. CDSE is free and — unlike Google Earth
Engine's noncommercial tier — is usable for ongoing/operational and government
workloads, which matches ChiangMaiEyes' "free, even when handed to authorities"
constraint. See memory: project-data-provenance.

Auth: OAuth2 client-credentials (CDSE OAuth client id/secret).
Falls back to the seeded layer when credentials are missing or CDSE fails, so a
misconfiguration never errors the dashboard.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import SatelliteDrynessZone, SatelliteLayerResponse
from app.providers.earth_engine_provider import (
    DATASET_IDS,
    SEED_DRYNESS_ZONES,
    _dryness_class,
    seeded_satellite_layers,
)

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
CDSE_STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# ~30 m expressed in degrees (Sentinel-2 native is 10–20 m; 30 m keeps the
# per-zone pixel count modest for the Statistical API while matching the
# resolution the seeded contract documented).
_RES_DEG = 0.00027
_LOOKBACK_DAYS = 45
# Pre-fire baseline window for dNBR (~2–4 months back, before the burn season).
_BASELINE_START_DAYS = 120
_BASELINE_END_DAYS = 60


def _burn_severity_class(dnbr: float | None) -> str | None:
    """USGS dNBR thresholds → burn-severity class."""
    if dnbr is None:
        return None
    if dnbr < 0.1:
        return "unburned"
    if dnbr < 0.27:
        return "low"
    if dnbr < 0.66:
        return "moderate"
    return "high"

# Single evalscript computing the three dryness indices, masking clouds/shadow/
# snow via the Scene Classification Layer (SCL) so zonal means reflect ground.
_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "B12", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "ndmi", bands: 1, sampleType: "FLOAT32" },
      { id: "nbr", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  // SCL: 3=cloud shadow, 8=cloud medium, 9=cloud high, 10=cirrus, 11=snow
  var valid = s.dataMask;
  if (s.SCL == 3 || s.SCL == 8 || s.SCL == 9 || s.SCL == 10 || s.SCL == 11) {
    valid = 0;
  }
  return {
    ndvi: [index(s.B08, s.B04)],
    ndmi: [index(s.B08, s.B11)],
    nbr: [index(s.B08, s.B12)],
    dataMask: [valid]
  };
}
"""


def copernicus_enabled(settings: Settings) -> bool:
    return bool(
        getattr(settings, "copernicus_client_id", None)
        and getattr(settings, "copernicus_client_secret", None)
    )


def _zone_polygon(lat: float, lon: float, radius_m: float, segments: int = 24) -> dict[str, Any]:
    """Approximate a buffer circle as a WGS84 polygon (Statistical API takes
    GeoJSON geometry, not point+radius)."""
    lat_deg = radius_m / 111_320.0
    lon_deg = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    ring = []
    for i in range(segments):
        theta = (2 * math.pi * i) / segments
        ring.append([lon + lon_deg * math.cos(theta), lat + lat_deg * math.sin(theta)])
    ring.append(ring[0])  # close the ring
    return {"type": "Polygon", "coordinates": [ring]}


def _get_token(settings: Settings, client: httpx.Client | None = None) -> str:
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.copernicus_client_id,
        "client_secret": settings.copernicus_client_secret,
    }
    poster = client.post if client else httpx.post
    response = poster(CDSE_TOKEN_URL, data=payload, timeout=20)
    response.raise_for_status()
    return response.json()["access_token"]


def _statistics_payload(geometry: dict[str, Any], start: str, end: str) -> dict[str, Any]:
    return {
        "input": {
            "bounds": {
                "geometry": geometry,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {"mosaickingOrder": "leastCC"},
                }
            ],
        },
        "aggregation": {
            "timeRange": {"from": start, "to": end},
            # One bucket over the whole window → a single, stable zonal mean.
            "aggregationInterval": {"of": f"P{_LOOKBACK_DAYS}D"},
            "resx": _RES_DEG,
            "resy": _RES_DEG,
            "evalscript": _EVALSCRIPT,
        },
        "calculations": {"default": {}},
    }


def _extract_means(stats: dict[str, Any]) -> dict[str, float | None]:
    """Pick the interval with the most valid samples and return band means."""
    best: dict[str, Any] | None = None
    best_samples = -1
    for entry in stats.get("data", []):
        bands = (entry.get("outputs", {}).get("data", {}).get("bands", {})) or {}
        ndvi_stats = bands.get("ndvi", {}).get("stats", {})
        samples = ndvi_stats.get("sampleCount", 0) - ndvi_stats.get("noDataCount", 0)
        if samples > best_samples and ndvi_stats.get("mean") is not None:
            best_samples = samples
            best = bands
    if not best:
        return {"ndvi": None, "ndmi": None, "nbr": None}
    return {
        band: best.get(band, {}).get("stats", {}).get("mean")
        for band in ("ndvi", "ndmi", "nbr")
    }


def build_satellite_layers_from_copernicus(
    settings: Settings, now: str | None = None
) -> SatelliteLayerResponse:
    generated_at = now or datetime.now(timezone(timedelta(hours=7))).isoformat()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_LOOKBACK_DAYS)
    start_iso = start.strftime("%Y-%m-%dT00:00:00Z")
    end_iso = end.strftime("%Y-%m-%dT00:00:00Z")
    base_start_iso = (end - timedelta(days=_BASELINE_START_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    base_end_iso = (end - timedelta(days=_BASELINE_END_DAYS)).strftime("%Y-%m-%dT00:00:00Z")

    with httpx.Client(timeout=30) as client:
        token = _get_token(settings, client=client)
        headers = {"Authorization": f"Bearer {token}"}

        zones: list[SatelliteDrynessZone] = []
        for seed in SEED_DRYNESS_ZONES:
            geometry = _zone_polygon(seed["latitude"], seed["longitude"], seed["radius_m"])
            response = client.post(
                CDSE_STATISTICS_URL,
                json=_statistics_payload(geometry, start_iso, end_iso),
                headers=headers,
            )
            response.raise_for_status()
            means = _extract_means(response.json())
            ndvi = _round_or_seed(means["ndvi"], seed.get("ndvi"), 3)
            ndmi = _round_or_seed(means["ndmi"], seed.get("ndmi"), 3)
            nbr = _round_or_seed(means["nbr"], seed.get("nbr"), 3)
            # NDVI/NDMI came back empty (all-cloud window) → keep seed but flag it.
            measured = means["ndvi"] is not None

            # dNBR = pre-fire baseline NBR − current NBR (post). Needs both a
            # cloud-free baseline and current NBR; otherwise stays None.
            dnbr: float | None = None
            if means["nbr"] is not None:
                base = client.post(
                    CDSE_STATISTICS_URL,
                    json=_statistics_payload(geometry, base_start_iso, base_end_iso),
                    headers=headers,
                )
                base.raise_for_status()
                base_nbr = _extract_means(base.json())["nbr"]
                if base_nbr is not None:
                    dnbr = round(base_nbr - means["nbr"], 3)

            zones.append(
                SatelliteDrynessZone(
                    id=seed["id"],
                    name=seed["name"],
                    latitude=seed["latitude"],
                    longitude=seed["longitude"],
                    radius_m=seed["radius_m"],
                    ndvi=ndvi,
                    ndmi=ndmi,
                    nbr=nbr,
                    rainfall_30d_mm=seed.get("rainfall_30d_mm"),
                    slope_mean_deg=seed.get("slope_mean_deg"),
                    dryness_class=_dryness_class(ndvi, ndmi, seed.get("rainfall_30d_mm")),
                    dnbr=dnbr,
                    burn_severity=_burn_severity_class(dnbr),
                    updated_at=generated_at,
                    source=(
                        "Copernicus Data Space Sentinel-2 L2A zonal mean"
                        if measured
                        else "Seed value (no cloud-free Sentinel-2 pixels in window)"
                    ),
                )
            )

    return SatelliteLayerResponse(
        source_mode="LIVE",
        source="Copernicus Data Space Sentinel-2 L2A (Statistical API)",
        generated_at=generated_at,
        dataset_ids=DATASET_IDS,
        cadence="Daily CDSE Statistical API zonal means over Chiang Mai dry-forest zones.",
        dryness_zones=zones,
        notes=[
            "NDVI=(B08-B04)/(B08+B04), NDMI=(B08-B11)/(B08+B11), NBR=(B08-B12)/(B08+B12).",
            "Clouds/shadow/snow masked via Sentinel-2 SCL before averaging.",
            f"Zonal means over the last {_LOOKBACK_DAYS} days; rainfall/slope still pending a free feed.",
        ],
    )


def _round_or_seed(value: Any, seed: Any, digits: int) -> float | None:
    if value is None:
        return seed
    return round(float(value), digits)


def load_copernicus_or_seed(settings: Settings, now: str | None = None) -> SatelliteLayerResponse:
    """Public entry: real CDSE layer when configured, else the seeded layer."""
    if not copernicus_enabled(settings):
        return seeded_satellite_layers(now=now)
    try:
        return build_satellite_layers_from_copernicus(settings, now=now)
    except Exception as exc:  # noqa: BLE001 — never let a feed failure error the dashboard
        logger.warning("Copernicus dryness refresh failed, using seed: %s", exc)
        return seeded_satellite_layers(now=now)
