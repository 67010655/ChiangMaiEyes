"""Real building/gas-station data (OSM via Overpass) for 3D mode.

Proxied through this backend rather than fetched directly from the browser.
Moved server-side after root-causing (via direct testing, not guessing) why
the exact same query was unreliable from the browser but fine via curl:
overpass-api.de's WAF returns 406 for httpx's default User-Agent
("python-httpx/x.y.z") and for real browser User-Agent strings alike, but
accepts curl's — and a descriptive, honestly-identifying User-Agent (see
_USER_AGENT below) also gets through cleanly. It isn't an Origin/CORS or
bot-protection-on-browsers issue as first suspected; it's a User-Agent
allowlist. Confirmed with retries that this isn't a one-off fluke.
"""

from __future__ import annotations

import logging

import httpx

from app.models import OsmBuilding, OsmFuelStation, OsmStructuresResponse

logger = logging.getLogger(__name__)

_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_TIMEOUT_SECONDS = 15.0
# httpx's default User-Agent ("python-httpx/x.y.z") gets a flat 406 from
# overpass-api.de's WAF; a descriptive, honestly-identifying one does not.
_USER_AGENT = "ChiangMaiEyes/1.0 (wildfire dashboard; https://chiangmaieyes.vercel.app)"

# Only ever called for a single 3D-viewport bbox (province-wide building data
# isn't fetchable/meaningful at low zoom — the frontend already gates this to
# zoom>=14), but reject an absurdly large bbox outright rather than trusting
# the caller, since this endpoint could otherwise be used to run an
# unbounded Overpass query through our backend.
_MAX_BBOX_DEGREES = 0.5


def _fetch_overpass(query: str) -> dict | None:
    for url in _OVERPASS_MIRRORS:
        try:
            response = httpx.post(
                url,
                data={"data": query},
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except Exception as ex:  # noqa: BLE001 — one dead mirror must not crash the endpoint
            logger.warning("Overpass mirror %s failed: %s", url, ex)
    return None


def fetch_osm_structures(south: float, west: float, north: float, east: float) -> OsmStructuresResponse:
    if north - south > _MAX_BBOX_DEGREES or east - west > _MAX_BBOX_DEGREES:
        return OsmStructuresResponse(buildings=[], fuel_stations=[])

    bbox = f"{south},{west},{north},{east}"
    query = (
        f'[out:json][timeout:20];(way["building"]({bbox});node["amenity"="fuel"]({bbox}););out geom;'
    )
    data = _fetch_overpass(query)
    if not data:
        return OsmStructuresResponse(buildings=[], fuel_stations=[])

    buildings: list[OsmBuilding] = []
    fuel_stations: list[OsmFuelStation] = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if el.get("type") == "way" and tags.get("building") and isinstance(el.get("geometry"), list) and len(el["geometry"]) >= 3:
            try:
                levels = float(tags.get("building:levels"))
            except (TypeError, ValueError):
                levels = 0.0
            height_m = levels * 3 if levels > 0 else 8.0
            coordinates = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
            buildings.append(OsmBuilding(coordinates=coordinates, height_m=height_m))
        elif el.get("type") == "node" and tags.get("amenity") == "fuel":
            fuel_stations.append(
                OsmFuelStation(lon=el["lon"], lat=el["lat"], name=tags.get("name") or "ปั๊มน้ำมัน")
            )

    return OsmStructuresResponse(buildings=buildings, fuel_stations=fuel_stations)
