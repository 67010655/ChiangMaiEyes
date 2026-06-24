from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models import SatelliteDrynessZone, SatelliteLayerResponse

logger = logging.getLogger(__name__)

DATASET_IDS = [
    "COPERNICUS/S2_SR_HARMONIZED",
    "UCSB-CHC/CHIRPS/DAILY",
    "USGS/SRTMGL1_003",
    "ESA/WorldCover/v200",
]

SEED_DRYNESS_ZONES: list[dict[str, Any]] = [
    {
        "id": "doi-suthep-pui",
        "name": "Doi Suthep-Pui dry forest belt",
        "latitude": 18.81,
        "longitude": 98.9,
        "radius_m": 7000,
        "ndvi": 0.28,
        "ndmi": -0.08,
        "nbr": 0.19,
        "rainfall_30d_mm": None,
        "slope_mean_deg": None,
        "dryness_class": "high",
    },
    {
        "id": "doi-inthanon-west",
        "name": "Doi Inthanon western slope",
        "latitude": 18.54,
        "longitude": 98.52,
        "radius_m": 9500,
        "ndvi": 0.35,
        "ndmi": -0.03,
        "nbr": 0.27,
        "rainfall_30d_mm": None,
        "slope_mean_deg": None,
        "dryness_class": "moderate",
    },
    {
        "id": "chiang-dao-limestone",
        "name": "Chiang Dao limestone forest",
        "latitude": 19.4,
        "longitude": 98.88,
        "radius_m": 8000,
        "ndvi": 0.22,
        "ndmi": -0.14,
        "nbr": 0.11,
        "rainfall_30d_mm": None,
        "slope_mean_deg": None,
        "dryness_class": "critical",
    },
    {
        "id": "mae-chaem-reserve",
        "name": "Mae Chaem reserved forest",
        "latitude": 18.5,
        "longitude": 98.37,
        "radius_m": 11000,
        "ndvi": 0.25,
        "ndmi": -0.11,
        "nbr": 0.14,
        "rainfall_30d_mm": None,
        "slope_mean_deg": None,
        "dryness_class": "critical",
    },
    {
        "id": "mae-taeng-headwater",
        "name": "Mae Taeng headwater forest",
        "latitude": 19.16,
        "longitude": 99.04,
        "radius_m": 7500,
        "ndvi": 0.32,
        "ndmi": -0.05,
        "nbr": 0.23,
        "rainfall_30d_mm": None,
        "slope_mean_deg": None,
        "dryness_class": "high",
    },
]


def satellite_layers_path(settings: Settings) -> Path:
    return settings.satellite_layers_file or settings.cache_dir / "satellite_layers.json"


def load_satellite_layers(settings: Settings, now: str | None = None) -> SatelliteLayerResponse:
    path = satellite_layers_path(settings)
    if path.exists():
        try:
            return SatelliteLayerResponse(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Invalid satellite layer export %s: %s", path, exc)

    # Preferred real source: Copernicus Data Space (free + operational/government
    # usable). Imported lazily to avoid a circular import (copernicus_provider
    # imports seeds from this module).
    from app.providers.copernicus_provider import copernicus_enabled

    if copernicus_enabled(settings):
        try:
            from app.providers.copernicus_provider import (
                build_satellite_layers_from_copernicus,
            )

            response = build_satellite_layers_from_copernicus(settings, now=now)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
            return response
        except Exception as exc:  # noqa: BLE001
            logger.warning("Copernicus satellite layer refresh failed: %s", exc)

    if settings.earth_engine_enabled:
        try:
            response = build_satellite_layers_from_earth_engine(settings, now=now)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
            return response
        except Exception as exc:  # noqa: BLE001
            logger.warning("Earth Engine satellite layer refresh failed: %s", exc)

    if settings.allow_prototype_data:
        return seeded_satellite_layers(now=now)

    generated_at = now or datetime.now(timezone(timedelta(hours=7))).isoformat()
    return SatelliteLayerResponse(
        source_mode="UNAVAILABLE",
        source="No real Sentinel/CDSE/GEE satellite layer configured",
        generated_at=generated_at,
        dataset_ids=[],
        cadence="Unavailable until COPERNICUS_CLIENT_ID/SECRET, Earth Engine, or satellite_layers_file is configured.",
        dryness_zones=[],
        notes=[
            "Prototype seeded satellite layers are disabled in production.",
            "Configure Copernicus Data Space, Earth Engine, or a verified satellite_layers_file to enable this layer.",
        ],
    )


def refresh_satellite_layers(settings: Settings, now: str | None = None) -> SatelliteLayerResponse:
    from app.providers.copernicus_provider import copernicus_enabled

    if copernicus_enabled(settings):
        from app.providers.copernicus_provider import build_satellite_layers_from_copernicus

        response = build_satellite_layers_from_copernicus(settings, now=now)
    elif settings.earth_engine_enabled:
        response = build_satellite_layers_from_earth_engine(settings, now=now)
    elif settings.allow_prototype_data:
        response = seeded_satellite_layers(now=now)
    else:
        generated_at = now or datetime.now(timezone(timedelta(hours=7))).isoformat()
        response = SatelliteLayerResponse(
            source_mode="UNAVAILABLE",
            source="No real Sentinel/CDSE/GEE satellite layer configured",
            generated_at=generated_at,
            dataset_ids=[],
            cadence="Unavailable until COPERNICUS_CLIENT_ID/SECRET, Earth Engine, or satellite_layers_file is configured.",
            dryness_zones=[],
            notes=["Prototype seeded satellite layers are disabled in production."],
        )

    path = satellite_layers_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    return response


def seeded_satellite_layers(now: str | None = None) -> SatelliteLayerResponse:
    generated_at = now or datetime.now(timezone(timedelta(hours=7))).isoformat()
    return SatelliteLayerResponse(
        source_mode="DERIVED",
        source="Google Earth Engine-ready Sentinel-2/CHIRPS/SRTM derived layer",
        generated_at=generated_at,
        dataset_ids=DATASET_IDS,
        cadence="Prepare daily after Sentinel-2/CHIRPS availability; fall back to latest generated export.",
        dryness_zones=[
            SatelliteDrynessZone(
                **zone,
                updated_at=generated_at,
                source="Seeded Chiang Mai dry-zone geometry; replace values from Earth Engine export job.",
            )
            for zone in SEED_DRYNESS_ZONES
        ],
        notes=[
            "NDVI, NDMI, and NBR are shaped to match a future Earth Engine export contract.",
            "Current values are deterministic seed values until the Earth Engine service account/export job is configured.",
            "Use this layer for UI integration and data-quality labeling, not as official satellite evidence yet.",
        ],
    )


def build_satellite_layers_from_earth_engine(settings: Settings, now: str | None = None) -> SatelliteLayerResponse:
    import ee  # type: ignore[import-untyped]

    generated_at = now or datetime.now(timezone(timedelta(hours=7))).isoformat()
    _initialize_earth_engine(ee, settings)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=45)
    rain_start = end - timedelta(days=30)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start.isoformat(), end.isoformat())
        .filterBounds(_chiang_mai_bounds(ee))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        .median()
    )
    ndvi = s2.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndmi = s2.normalizedDifference(["B8", "B11"]).rename("ndmi")
    nbr = s2.normalizedDifference(["B8", "B12"]).rename("nbr")
    rain = (
        ee.ImageCollection("UCSB-CHC/CHIRPS/DAILY")
        .filterDate(rain_start.isoformat(), end.isoformat())
        .sum()
        .rename("rainfall_30d_mm")
    )
    terrain = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope_mean_deg")
    stack = ndvi.addBands(ndmi).addBands(nbr).addBands(rain).addBands(terrain)

    zones: list[SatelliteDrynessZone] = []
    for seed in SEED_DRYNESS_ZONES:
        geometry = ee.Geometry.Point([seed["longitude"], seed["latitude"]]).buffer(seed["radius_m"])
        stats = stack.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=30,
            bestEffort=True,
            maxPixels=1_000_000,
        ).getInfo()
        values = {key: _round_or_seed(stats.get(key), seed.get(key), 3) for key in ("ndvi", "ndmi", "nbr")}
        rainfall = _round_or_seed(stats.get("rainfall_30d_mm"), seed.get("rainfall_30d_mm"), 1)
        slope = _round_or_seed(stats.get("slope_mean_deg"), seed.get("slope_mean_deg"), 1)
        zones.append(
            SatelliteDrynessZone(
                id=seed["id"],
                name=seed["name"],
                latitude=seed["latitude"],
                longitude=seed["longitude"],
                radius_m=seed["radius_m"],
                ndvi=values["ndvi"],
                ndmi=values["ndmi"],
                nbr=values["nbr"],
                rainfall_30d_mm=rainfall,
                slope_mean_deg=slope,
                dryness_class=_dryness_class(values["ndvi"], values["ndmi"], rainfall),
                updated_at=generated_at,
                source="Google Earth Engine Sentinel-2/CHIRPS/SRTM zonal mean",
            )
        )

    return SatelliteLayerResponse(
        source_mode="LIVE",
        source="Google Earth Engine Sentinel-2/CHIRPS/SRTM export",
        generated_at=generated_at,
        dataset_ids=DATASET_IDS,
        cadence="Daily Earth Engine zonal statistics over configured Chiang Mai dry forest zones.",
        dryness_zones=zones,
        notes=[
            "NDVI uses Sentinel-2 B8/B4, NDMI uses B8/B11, and NBR uses B8/B12.",
            "Rainfall is CHIRPS 30-day accumulated rainfall; slope is SRTM terrain slope.",
            "Values are zonal means over operational dry-forest watch zones.",
        ],
    )


def _initialize_earth_engine(ee: Any, settings: Settings) -> None:
    if settings.earth_engine_service_account and settings.earth_engine_private_key_path:
        credentials = ee.ServiceAccountCredentials(
            settings.earth_engine_service_account,
            str(settings.earth_engine_private_key_path),
        )
        ee.Initialize(credentials, project=settings.earth_engine_project)
        return

    import google.auth  # type: ignore[import-untyped]

    credentials, project_id = google.auth.default()
    ee.Initialize(credentials, project=settings.earth_engine_project or project_id)


def _chiang_mai_bounds(ee: Any) -> Any:
    return ee.Geometry.Rectangle([97.25, 17.35, 99.68, 20.28])


def _round_or_seed(value: Any, seed: Any, digits: int) -> float | None:
    if value is None:
        return seed
    return round(float(value), digits)


def _dryness_class(ndvi: float, ndmi: float, rainfall_30d_mm: float | None) -> str:
    rain = rainfall_30d_mm if rainfall_30d_mm is not None else 999
    if ndvi <= 0.25 or ndmi <= -0.1 or rain < 15:
        return "critical"
    if ndvi <= 0.33 or ndmi <= -0.04 or rain < 35:
        return "high"
    return "moderate"
