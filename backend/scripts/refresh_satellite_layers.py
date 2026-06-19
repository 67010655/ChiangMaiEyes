"""Refresh Google Earth Engine-derived satellite layer export.

With EARTH_ENGINE_ENABLED=true and valid Google credentials, this computes
Sentinel-2 NDVI/NDMI/NBR, CHIRPS 30-day rainfall, and SRTM slope zonal means.
Without credentials, it writes the deterministic Earth Engine-ready seed layer
so the frontend/API contract remains available but clearly labeled as derived.
"""

import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.providers.earth_engine_provider import refresh_satellite_layers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_satellite_layers")


def main() -> int:
    settings = get_settings()
    response = refresh_satellite_layers(settings)
    logger.info(
        "Wrote satellite layer export (mode=%s zones=%d)",
        response.source_mode,
        len(response.dryness_zones),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
