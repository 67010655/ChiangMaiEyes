# Google Earth Engine Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready contract for Google Earth Engine-derived satellite layers, starting with NDVI/fuel dryness zones for ChiangMaiEyes.

**Architecture:** Backend owns satellite layer truth, timestamps, and source labels. Frontend consumes `dashboard.intelligence.satellite_layers` and renders NDVI/fuel zones from API data when present, falling back to existing static zones only when API data is unavailable.

**Tech Stack:** FastAPI/Pydantic backend, existing dashboard JSON contract, React/Vite frontend, Google Earth Engine-ready JSON export format.

---

### Task 1: Backend Satellite Layer Contract

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services.py`
- Test: `backend/tests/test_weekly_forest_league.py`

- [ ] Add `SatelliteDrynessZone` and `SatelliteLayerResponse` Pydantic models.
- [ ] Add `satellite_layers` to `OperationalIntelligenceResponse`.
- [ ] Implement `get_satellite_layers()` in `backend/app/services.py` with deterministic Sentinel-2/CHIRPS/SRTM-ready seed data.
- [ ] Test that operational intelligence includes at least five NDVI zones, source mode is `DERIVED`, and dataset ids include `COPERNICUS/S2_SR_HARMONIZED`.

### Task 2: Frontend Contract and Map Rendering

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/DashboardMap.tsx`

- [ ] Add TypeScript types for satellite layers and dryness zones.
- [ ] Prefer `dashboard.intelligence?.satellite_layers?.dryness_zones` over static `DRY_FOREST_ZONES`.
- [ ] Keep existing static zones as fallback.
- [ ] Ensure map rendering still works when API is unavailable.

### Task 3: Truth Labels

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/tests/test_data_status.py`

- [ ] Change NDVI quality from `PROTOTYPE` to `DERIVED`.
- [ ] Set source to Sentinel-2/CHIRPS/SRTM-ready satellite layer.
- [ ] Keep clear note that this is an export-ready derived layer until live Earth Engine credentials/job are configured.

### Task 4: Verification and Deploy

**Commands:**
- `python -m pytest -q`
- `npm.cmd test -- --run`
- `npm.cmd run build`
- `npx.cmd vercel@latest deploy . --project backend --prod --yes`
- `npx.cmd vercel@latest deploy . --prod --yes` from `frontend/`

- [ ] Verify production `/api/dashboard` includes `intelligence.satellite_layers`.
- [ ] Verify frontend production loads without console errors.

### Task 5: Optional Earth Engine Export Provider

**Files:**
- Create: `backend/app/providers/earth_engine_provider.py`
- Create: `backend/scripts/refresh_satellite_layers.py`
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/requirements.txt`
- Modify: `scripts/refresh_and_deploy.ps1`
- Test: `backend/tests/test_earth_engine_provider.py`

- [ ] Add `earthengine-api` runtime dependency.
- [ ] Add config for `EARTH_ENGINE_ENABLED`, `EARTH_ENGINE_PROJECT`, `EARTH_ENGINE_SERVICE_ACCOUNT`, `EARTH_ENGINE_PRIVATE_KEY_PATH`, and `SATELLITE_LAYERS_FILE`.
- [ ] Implement provider behavior: load existing `satellite_layers.json`, refresh via Earth Engine when enabled, otherwise write deterministic seed export.
- [ ] Add script `python backend/scripts/refresh_satellite_layers.py` for daily/manual satellite export generation.
- [ ] Add tests for existing export load and no-credential seed export.
