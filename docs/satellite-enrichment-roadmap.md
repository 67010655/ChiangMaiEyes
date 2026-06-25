# Satellite Enrichment Roadmap

## Purpose

This roadmap keeps ChiangMaiEyes honest about which map layers are live operational signals and which layers are slower satellite-derived context. The goal is to help community forest committees, district officers, and field teams understand fire pressure, terrain risk, and boundary confidence without pretending that every layer updates in real time.

## Current Layers

| Layer | Current status | Source | Use |
|---|---|---|---|
| Hotspots | live/near-live | RFD, GISTDA Disaster STAC, GISTDA API Gateway, NASA FIRMS VIIRS | Active fire points and operational refresh |
| PM2.5 | live | Air4Thai | Public health and smoke exposure |
| Wind/weather | live | Thai Meteorological Department AWS | Smoke movement and fire-spread context |
| NDVI | derived contract/seed fallback | Sentinel-2 | Vegetation and fuel condition |
| NDMI | derived contract/seed fallback | Sentinel-2 | Moisture stress |
| NBR | derived contract/seed fallback | Sentinel-2 | Burn and fuel signal |
| Rainfall 30d | derived contract/seed fallback | CHIRPS | Drought context |
| Slope | derived contract/seed fallback | SRTM | Terrain-driven fire spread context |
| Land cover | contract/seed context | ESA WorldCover | Forest, agriculture, and urban context |
| Community forest points | prototype | Thaicfnet/RFD-derived local dataset | Community forest locations and weekly ranking context |
| Fire-management zones | prototype | Local planning dataset | Operating zones and boundary discussion |

## Recommended Next Layers

| Layer | Source candidate | Product value | Refresh cadence |
|---|---|---|---|
| Aspect | SRTM or Copernicus DEM | Shows slope direction for sun exposure and fire spread | Monthly or on demand |
| Elevation bands | SRTM or Copernicus DEM | Helps explain valley smoke pooling, ridges, and access difficulty | Monthly or on demand |
| Hotspot history density | RFD/GISTDA/NASA FIRMS archive | 7/30/365 day rolling fire pressure around each community forest | Daily |
| Burn scar history | MODIS MCD64A1, Sentinel-2 NBR delta, GISTDA burn products if available | Shows repeated burn zones and post-fire recovery | Monthly during fire season |
| Road/access layer | OSM roads, local government roads if available | Supports field response planning and firebreak access | Weekly/monthly |
| Settlement exposure | OSM villages, schools, health facilities, local DOPA/admin data | Identifies people and services exposed to smoke or nearby fire | Weekly/monthly |
| Boundary confidence | RFD official polygons, Thaicfnet records, prototype geometry | Separates official, estimated, and prototype community forest boundaries | Whenever source changes |
| Water-source proximity | OSM water, local water points, field reports | Helps crews plan suppression and patrol routes | Weekly plus report updates |
| Fuel-treatment evidence | Field reports, Sentinel-2 vegetation delta | Connects weekly ranking to visible fuel management impact | Weekly |

## Data Truth Rules

- Hotspots, PM2.5, and weather can be labeled `LIVE` only when the current backend fetch succeeds or a fresh cache is within the accepted age window.
- Earth Engine/Sentinel-derived layers should be labeled `DERIVED` unless a credentialed export job has actually completed with a current timestamp.
- Community forest boundaries stay `PROTOTYPE` until official polygons are imported or a trusted local authority verifies the geometry.
- Weekly ranking can combine user reports and satellite context, but the UI must show the source mode and verification status for each forest.

## Earth Engine Export Path

1. Keep Earth Engine analysis separate from the 15-minute hotspot refresh.
2. Export zonal metrics by community forest or fire-management zone.
3. Write normalized output to `backend/data/satellite_layers.json` or a future database table.
4. Include dataset IDs, generated timestamp, source mode, and notes in every export.
5. Let the frontend consume the existing `satellite_layers` contract instead of coupling UI directly to Earth Engine.

## Boundary Confidence Model

| Status | Meaning | UI treatment |
|---|---|---|
| official | Official polygon from RFD or accepted government source | Strong boundary line, normal ranking |
| estimated | Geometry estimated from points, village names, or planning buffers | Dashed line, caution label |
| prototype | Demo or seed data not yet verified | Prototype chip, ranking caveat |

## First Production Slice

The best next build slice is hotspot history density by community forest:

- It strengthens weekly ranking without requiring user auth first.
- It explains whether community activity correlates with lower fire pressure.
- It can be computed from existing hotspot sources.
- It is useful for both map users and district-level reporting.
