# Community Forest Existing Capabilities

Status: implementation audit
Date: 2026-06-21

## Frontend

- Main app shell: `frontend/src/App.tsx`
- Leaflet map component: `frontend/src/components/DashboardMap.tsx`
- API client: `frontend/src/lib/api.ts`
- Shared response types: `frontend/src/lib/types.ts`
- Map selection model: `frontend/src/lib/mapSelection.ts`
- Wind field helper: `frontend/src/lib/windGrid.ts`
- Current map layers: PM2.5, hotspots, wind, landmarks, fuel risk, community forests, fire zones, predictions.
- Community forest and fire-zone toggles already exist in the map layer strip.
- MapTiler support already exists through `VITE_MAPTILER_KEY`; fallback basemaps render without a key.
- Source/freshness state comes from `DashboardResponse.data_quality`.

## Backend

- Main API app: `backend/app/main.py`
- Main dashboard endpoint: `GET /api/dashboard`
- Data status endpoint: `GET /api/data-status`
- Dashboard orchestration: `backend/app/services.py`
- Response models: `backend/app/models.py`
- Community forest scoring: `backend/app/weekly_forest_league.py`
- Community forest ranking lives under `DashboardResponse.intelligence.weekly_forest_league`.
- Source modes are modeled as `LIVE`, `DERIVED`, `PROTOTYPE`, and `UNAVAILABLE`.

## Data

- Community forest prototype data: `frontend/src/data/community-forests-prototype.json`
- Fire-management zone prototype data: `frontend/src/data/fire-management-zones-prototype.json`
- Province boundary: `frontend/src/data/chiangmai-province.json`
- District boundaries: `frontend/src/data/chiangmai-districts.json`
- Satellite layer contract: `backend/app/providers/earth_engine_provider.py`
- Hotspot providers: `backend/app/providers/hotspot_provider.py`
- PM2.5 provider: `backend/app/providers/pm25_provider.py`
- Weather provider: `backend/app/providers/weather_provider.py`

## Live / Derived / Prototype Split

- Live or near-live: RFD Firemap, GISTDA Disaster STAC, GISTDA VIIRS, NASA FIRMS VIIRS, Air4Thai, TMD AWS.
- Derived: risk score, localized predictions, Earth Engine-ready NDVI/NDMI/NBR/rainfall/slope layers.
- Prototype: community forest boundaries, fire-management zones, seed weekly forest league reports.

## Gaps

- No auth/user accounts yet.
- No persistent field-report database yet.
- No official community forest polygon source has been wired.
- Weekly ranking does not yet use verified user reports.
- Weekly ranking does not yet calculate hotspot deltas per official boundary.
- No 3D map engine is installed yet.
- Earth Engine live export depends on service-account/env setup and currently has seeded fallback behavior.
