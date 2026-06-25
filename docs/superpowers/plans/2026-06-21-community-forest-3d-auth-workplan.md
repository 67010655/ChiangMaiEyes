# Community Forest, 3D Map, Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate ChiangMaiEyes community-forest accountability experience with verified 2D map flow first, then optional 3D terrain/map mode, richer satellite-derived context, and auth/user-data foundation.

**Architecture:** Keep current Leaflet operational map stable and add focused modules around it. Add new data contracts behind existing FastAPI/Pydantic patterns, then integrate MapLibre 3D as a separate view instead of forcing Leaflet to do 3D. Add auth as a gated follow-up with Supabase so reports/user locations can be stored safely with Row Level Security.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Leaflet 1.9, leaflet-velocity, lucide-react, optional MapLibre GL JS, FastAPI, Pydantic, httpx, Google Earth Engine, pytest, Vitest, Supabase Auth/Postgres if approved.

---

## Current Repo Inventory

### Already Exists

- Frontend app: `frontend/src/App.tsx`
- Leaflet map component: `frontend/src/components/DashboardMap.tsx`
- Map data types: `frontend/src/lib/types.ts`
- API client: `frontend/src/lib/api.ts`
- Global UI styles: `frontend/src/styles/global.css`
- Community forest prototype data: `frontend/src/data/community-forests-prototype.json`
- Fire-management zone prototype data: `frontend/src/data/fire-management-zones-prototype.json`
- Province/district geometry: `frontend/src/data/chiangmai-province.json`, `frontend/src/data/chiangmai-districts.json`
- Wind grid builder for `leaflet-velocity`: `frontend/src/lib/windGrid.ts`
- Backend API app: `backend/app/main.py`
- Backend models: `backend/app/models.py`
- Dashboard orchestration: `backend/app/services.py`
- Weekly forest scoring: `backend/app/weekly_forest_league.py`
- Earth Engine satellite layer contract: `backend/app/providers/earth_engine_provider.py`
- Hotspot providers: `backend/app/providers/hotspot_provider.py`
- PM2.5 provider: `backend/app/providers/pm25_provider.py`
- Weather provider: `backend/app/providers/weather_provider.py`
- Weekly league tests: `backend/tests/test_weekly_forest_league.py`
- Design concept docs/images: `docs/design-concepts/`

### Current Map Capabilities

- Leaflet map created manually in React with refs/effects.
- Layer toggles already include `communityForests`, `fireZones`, `hotspots`, `wind`, `fuelRisk`, `predictions`.
- `DashboardMap` already renders community forest markers/buffer-like estimated boundaries and fire-management zones.
- MapTiler basemap hook exists through `VITE_MAPTILER_KEY`.
- `leaflet-velocity` already renders wind particles from TMD AWS.
- Selection model uses `MapSelection` from `frontend/src/lib/mapSelection.ts`.

### Current Data Capabilities

- Live/near-live hotspots: RFD Firemap, GISTDA Disaster STAC VIIRS, GISTDA VIIRS 1-day, NASA FIRMS VIIRS.
- Live PM2.5: Air4Thai.
- Live weather/wind: TMD AWS.
- Derived risk: deterministic score from PM2.5, hotspots, weather/wind, fire physics.
- Derived satellite contract: Sentinel-2 NDVI/NDMI/NBR, CHIRPS rainfall, SRTM slope, ESA WorldCover.
- Prototype community forest data: Thaicfnet/RFD-derived local JSON.
- Prototype weekly league: seed reports in `backend/app/services.py`, scoring in `backend/app/weekly_forest_league.py`.

### Gaps Before Production

- No auth/user accounts yet.
- No persistent report database yet.
- Community forest boundaries are estimated/prototype, not official polygons.
- Weekly ranking does not yet include verified user reports or hotspot delta by boundary.
- 3D map engine not installed yet.
- Earth Engine live export disabled unless env/service account configured.

---

## Approval Gates

Do not implement everything at once. Ask for approval after each gate.

1. Gate A: 2D community forest accountability view using existing data only.
2. Gate B: Backend data contract cleanup for community forest/ranking.
3. Gate C: 3D map prototype with MapLibre terrain.
4. Gate D: Satellite enrichment export path.
5. Gate E: Supabase auth/user reports.

---

## Task 1: Create Existing-Capability Audit Doc

**Files:**
- Create: `docs/community-forest-existing-capabilities.md`

- [ ] **Step 1: Write audit doc**

Create sections:

```markdown
# Community Forest Existing Capabilities

## Frontend

- Leaflet map lives in `frontend/src/components/DashboardMap.tsx`.
- Current layers: PM2.5, hotspots, wind, landmarks, fuel risk, community forests, fire zones, predictions.
- Current map source mode labels come from `DashboardResponse.data_quality`.

## Backend

- Main dashboard endpoint: `GET /api/dashboard`.
- Community forest ranking lives under `dashboard.intelligence.weekly_forest_league`.
- Source modes are modeled as `LIVE`, `DERIVED`, `PROTOTYPE`, `UNAVAILABLE`.

## Data

- Community forest prototype data: `frontend/src/data/community-forests-prototype.json`.
- Fire zone prototype data: `frontend/src/data/fire-management-zones-prototype.json`.
- Satellite contract: `backend/app/providers/earth_engine_provider.py`.

## Gaps

- No auth.
- No report persistence.
- No official community forest polygon source.
- No 3D engine.
```

- [ ] **Step 2: Verify references exist**

Run:

```powershell
Test-Path frontend\src\components\DashboardMap.tsx
Test-Path backend\app\weekly_forest_league.py
Test-Path frontend\src\data\community-forests-prototype.json
Test-Path frontend\src\data\fire-management-zones-prototype.json
```

Expected: all `True`.

- [ ] **Step 3: Commit**

```powershell
git add docs/community-forest-existing-capabilities.md
git commit -m "docs: audit community forest map capabilities"
```

---

## Task 2: Extract Community Forest UI Data Helpers

**Files:**
- Create: `frontend/src/features/communityForest/communityForestData.ts`
- Create: `frontend/src/features/communityForest/communityForestData.test.ts`
- Modify: `frontend/src/lib/types.ts` only if type gaps block compile.

- [ ] **Step 1: Add failing tests**

```ts
import { describe, expect, it } from "vitest";
import { buildCommunityForestRows, sourceModeForCommunityForest } from "./communityForestData";
import type { DashboardResponse } from "../../lib/types";

describe("communityForestData", () => {
  it("combines weekly league ranking with prototype fallback rows", () => {
    const dashboard = {
      intelligence: {
        weekly_forest_league: {
          week_id: "2026-06-07",
          scoring_window: "2026-06-01 to 2026-06-07",
          scheduled_recompute: "Sunday 23:55",
          rate_limit_rule: "one report per forest/village/day",
          ranking: [
            {
              forest_id: "cf-1",
              forest_name: "ป่าชุมชนแม่แจ่ม",
              village: "บ้านแม่ปาน",
              tambon: "ช่างเคิ่ง",
              amphoe: "แม่แจ่ม",
              latitude: 18.503,
              longitude: 98.361,
              total_score: 87,
              rank: 1,
              report_count: 3,
              last_report_at: "2026-06-07T07:30:00+07:00",
              score_breakdown: { management: 25, prevention: 30, utilization: 17, ecological_outcome: 15 },
              reasons: ["ลาดตระเวน", "แนวกันไฟ"],
            },
          ],
        },
      },
      data_quality: {
        community_forests: {
          label: "Community forest league",
          source: "Seed reports",
          source_mode: "PROTOTYPE",
          confidence: 0.4,
          is_stale: false,
          note: "prototype",
        },
      },
    } as DashboardResponse;

    const rows = buildCommunityForestRows(dashboard);
    expect(rows[0].forestName).toBe("ป่าชุมชนแม่แจ่ม");
    expect(rows[0].score).toBe(87);
    expect(rows[0].sourceMode).toBe("PROTOTYPE");
  });

  it("defaults community forest source mode to PROTOTYPE when data_quality is missing", () => {
    expect(sourceModeForCommunityForest({} as DashboardResponse)).toBe("PROTOTYPE");
  });
});
```

- [ ] **Step 2: Run failing test**

```powershell
cd frontend
npm.cmd run test -- communityForestData.test.ts
```

Expected: fail because file/functions do not exist.

- [ ] **Step 3: Implement helper**

```ts
import type { DashboardResponse, SourceMode } from "../../lib/types";

export type CommunityForestRow = {
  id: string;
  rank: number;
  forestName: string;
  amphoe: string;
  score: number;
  reportCount: number;
  lastReportAt: string;
  reasons: string[];
  sourceMode: SourceMode;
  latitude: number;
  longitude: number;
};

export function sourceModeForCommunityForest(dashboard: DashboardResponse): SourceMode {
  return dashboard.data_quality?.community_forests?.source_mode ?? "PROTOTYPE";
}

export function buildCommunityForestRows(dashboard: DashboardResponse): CommunityForestRow[] {
  const sourceMode = sourceModeForCommunityForest(dashboard);
  const ranking = dashboard.intelligence?.weekly_forest_league.ranking ?? [];
  return ranking.map((entry) => ({
    id: entry.forest_id,
    rank: entry.rank,
    forestName: entry.forest_name,
    amphoe: entry.amphoe,
    score: entry.total_score,
    reportCount: entry.report_count,
    lastReportAt: entry.last_report_at,
    reasons: entry.reasons,
    sourceMode,
    latitude: entry.latitude,
    longitude: entry.longitude,
  }));
}
```

- [ ] **Step 4: Run test**

```powershell
cd frontend
npm.cmd run test -- communityForestData.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/communityForest/communityForestData.ts frontend/src/features/communityForest/communityForestData.test.ts
git commit -m "feat: add community forest data helpers"
```

---

## Task 3: Add Source Mode Chip Component

**Files:**
- Create: `frontend/src/features/communityForest/SourceModeChip.tsx`
- Create: `frontend/src/features/communityForest/SourceModeChip.test.tsx`
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: Add component test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceModeChip } from "./SourceModeChip";

describe("SourceModeChip", () => {
  it("renders prototype label honestly", () => {
    render(<SourceModeChip mode="PROTOTYPE" />);
    expect(screen.getByText("ข้อมูลต้นแบบ")).toBeTruthy();
  });

  it("renders live label", () => {
    render(<SourceModeChip mode="LIVE" />);
    expect(screen.getByText("สด")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Install test renderer only if missing**

Check:

```powershell
cd frontend
npm.cmd ls @testing-library/react
```

If missing, install:

```powershell
cd frontend
npm.cmd install -D @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 3: Implement component**

```tsx
import type { SourceMode } from "../../lib/types";

const LABELS: Record<SourceMode, string> = {
  LIVE: "สด",
  DERIVED: "คำนวณ",
  PROTOTYPE: "ข้อมูลต้นแบบ",
  UNAVAILABLE: "ไม่พร้อม",
};

export function SourceModeChip({ mode }: { mode: SourceMode }) {
  return <span className={`source-mode-chip source-mode-chip--${mode.toLowerCase()}`}>{LABELS[mode]}</span>;
}
```

- [ ] **Step 4: Add CSS**

```css
.source-mode-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1;
  border: 1px solid var(--line);
  background: #f6faf7;
  color: #10231d;
}

.source-mode-chip--live {
  background: #dff5e7;
  color: #0f6b54;
}

.source-mode-chip--derived {
  background: #e7f0ff;
  color: #1d4ed8;
}

.source-mode-chip--prototype {
  background: #fff4df;
  color: #9a5a00;
}

.source-mode-chip--unavailable {
  background: #f1f5f3;
  color: #5a6d63;
}
```

- [ ] **Step 5: Run tests**

```powershell
cd frontend
npm.cmd run test -- SourceModeChip.test.tsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/features/communityForest/SourceModeChip.tsx frontend/src/features/communityForest/SourceModeChip.test.tsx frontend/src/styles/global.css
git commit -m "feat: add source mode chip"
```

---

## Task 4: Build 2D Community Forest View

**Files:**
- Create: `frontend/src/features/communityForest/CommunityForestView.tsx`
- Create: `frontend/src/features/communityForest/WeeklyForestLeagueTable.tsx`
- Create: `frontend/src/features/communityForest/WeeklyForestRankList.tsx`
- Create: `frontend/src/features/communityForest/CommunityForestInspector.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: Create table/list components**

Use `CommunityForestRow[]` from Task 2. Desktop table columns:

```tsx
type Props = {
  rows: CommunityForestRow[];
  selectedId: string | null;
  onSelect: (row: CommunityForestRow) => void;
};
```

Mobile list uses same props and renders top 5 rows.

- [ ] **Step 2: Create inspector component**

Inspector props:

```tsx
type Props = {
  row: CommunityForestRow | null;
};
```

Empty state text:

```tsx
เลือกป่าชุมชนบนแผนที่หรือในอันดับรายสัปดาห์
```

- [ ] **Step 3: Create view component**

View responsibilities:

- Build rows from `dashboard`.
- Track selected row.
- Set layers default: community forests, fire zones, hotspots, wind.
- Render `DashboardMap`.
- Render table/list/inspector.
- Keep emergency contacts lower priority on mobile.

- [ ] **Step 4: Wire into `App.tsx` behind a mode**

Add a view switch option labeled:

```tsx
ป่าชุมชน
```

Do not delete existing dashboard mode.

- [ ] **Step 5: Add CSS**

Add classes:

```css
.community-forest-shell
.community-forest-main
.community-forest-map
.community-forest-inspector
.weekly-forest-table
.weekly-forest-rank-list
```

Constraints:

- Desktop map remains dominant.
- Mobile order: map -> selected forest -> ranking -> contacts.
- No nested card overload.
- Thai text wraps cleanly.

- [ ] **Step 6: Run frontend tests/build**

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

Expected: both pass.

- [ ] **Step 7: Browser verify**

Run dev server:

```powershell
cd frontend
npm.cmd run dev
```

Check:

- desktop `1440x900`
- laptop `1366x768`
- mobile `390x844`
- selecting ranking row updates inspector and map selection
- source chip says prototype for community forest/ranking

- [ ] **Step 8: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/features/communityForest frontend/src/styles/global.css
git commit -m "feat: add community forest accountability view"
```

---

## Task 5: Backend Community Forest Contract Review

**Files:**
- Create: `backend/tests/test_community_forest_contract.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/services.py`

- [ ] **Step 1: Add contract test for existing dashboard**

```py
from app.config import get_settings
from app.services import get_dashboard


def test_dashboard_exposes_weekly_forest_league_contract():
    dashboard = get_dashboard(get_settings())

    assert dashboard.intelligence is not None
    league = dashboard.intelligence.weekly_forest_league
    assert league.week_id
    assert league.scoring_window
    assert league.ranking

    first = league.ranking[0]
    assert first.forest_id
    assert first.forest_name
    assert first.total_score >= 0
    assert first.score_breakdown.management >= 0
    assert first.score_breakdown.prevention >= 0
```

- [ ] **Step 2: Run test**

```powershell
cd backend
python -m pytest tests/test_community_forest_contract.py -q
```

Expected: pass with current contract.

- [ ] **Step 3: Add optional fields only if UI needs them**

Extend `WeeklyForestRankingEntry` with safe optional fields:

```py
authority_owner: str | None = None
boundary_source: str | None = None
boundary_confidence: str | None = None
verification_status: str | None = None
hotspot_activity_delta_percent: float | None = None
```

- [ ] **Step 4: Add tests for optional fields**

```py
def test_weekly_forest_entries_can_carry_boundary_confidence():
    dashboard = get_dashboard(get_settings())
    entry = dashboard.intelligence.weekly_forest_league.ranking[0]
    assert hasattr(entry, "boundary_confidence")
```

- [ ] **Step 5: Run backend tests**

```powershell
cd backend
python -m pytest -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models.py backend/app/services.py backend/tests/test_community_forest_contract.py
git commit -m "feat: clarify community forest ranking contract"
```

---

## Task 6: MapLibre 3D Terrain Spike

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/features/threeD/MapLibreTerrainView.tsx`
- Create: `frontend/src/features/threeD/mapLibreLayers.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/.env.example`

- [ ] **Step 1: Install MapLibre**

```powershell
cd frontend
npm.cmd install maplibre-gl
```

- [ ] **Step 2: Add env docs**

Add to `frontend/.env.example`:

```env
# Optional MapLibre/MapTiler terrain mode.
# Required for hosted Terrain RGB and vector styles.
VITE_MAPTILER_KEY=
```

- [ ] **Step 3: Create terrain view component**

Use separate container. Do not replace Leaflet.

```tsx
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

export function MapLibreTerrainView() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current || !MAPTILER_KEY) return;

    const map = new maplibregl.Map({
      container: ref.current,
      style: `https://api.maptiler.com/maps/outdoor-v2/style.json?key=${MAPTILER_KEY}`,
      center: [98.98, 18.78],
      zoom: 8.5,
      pitch: 62,
      bearing: -20,
      attributionControl: true,
    });

    map.on("load", () => {
      map.addSource("terrain", {
        type: "raster-dem",
        url: `https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${MAPTILER_KEY}`,
        tileSize: 256,
      });
      map.setTerrain({ source: "terrain", exaggeration: 1.4 });
    });

    return () => map.remove();
  }, []);

  if (!MAPTILER_KEY) {
    return <div className="terrain-missing-key">ต้องตั้งค่า VITE_MAPTILER_KEY เพื่อเปิด 3D terrain</div>;
  }

  return <div ref={ref} className="maplibre-terrain-view" />;
}
```

- [ ] **Step 4: Add style**

```css
.maplibre-terrain-view {
  width: 100%;
  min-height: 520px;
  height: min(76vh, 760px);
  overflow: hidden;
  background: #eef3ef;
}

.terrain-missing-key {
  display: grid;
  min-height: 360px;
  place-items: center;
  color: #5a6d63;
  background: #eef3ef;
  border: 1px solid #e3ece6;
}
```

- [ ] **Step 5: Wire as separate tab/mode**

Add label:

```tsx
ภูมิประเทศ 3D
```

Keep default map as Leaflet.

- [ ] **Step 6: Run build**

```powershell
cd frontend
npm.cmd run build
```

Expected: pass.

- [ ] **Step 7: Browser verify**

Verify:

- If key missing: helpful missing-key message.
- If key present: terrain renders, pitch visible, map nonblank.
- Existing Leaflet map still works.

- [ ] **Step 8: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/.env.example frontend/src/features/threeD frontend/src/App.tsx frontend/src/styles/global.css
git commit -m "feat: add experimental 3d terrain view"
```

---

## Task 7: Satellite Enrichment Workplan

**Files:**
- Create: `docs/satellite-enrichment-roadmap.md`
- Modify later only after approval: `backend/app/providers/earth_engine_provider.py`

- [ ] **Step 1: Document current and next satellite layers**

Create table:

```markdown
| Layer | Current status | Source | Use |
|---|---|---|---|
| Hotspots | live/near-live | RFD, GISTDA, NASA FIRMS VIIRS | active fire points |
| NDVI | derived contract/seed fallback | Sentinel-2 | vegetation/fuel condition |
| NDMI | derived contract/seed fallback | Sentinel-2 | moisture stress |
| NBR | derived contract/seed fallback | Sentinel-2 | burn/fuel signal |
| Rainfall 30d | derived contract/seed fallback | CHIRPS | drought context |
| Slope | derived contract/seed fallback | SRTM | fire spread terrain context |
| Land cover | contract only | ESA WorldCover | forest/agri/urban context |
```

- [ ] **Step 2: Add recommended next layers**

Add:

```markdown
- Aspect: slope direction; useful for sun exposure and fire spread.
- Elevation bands: valley/ridge smoke pooling context.
- Hotspot history density: 7/30/365 day rolling fire pressure.
- Road/access layer: field response planning.
- Settlement exposure layer: villages/schools/health facilities near smoke plume.
- Boundary confidence layer: official/estimated/prototype geometry status.
```

- [ ] **Step 3: Commit**

```powershell
git add docs/satellite-enrichment-roadmap.md
git commit -m "docs: plan satellite enrichment layers"
```

---

## Task 8: Supabase Auth And User Data Design

**Files:**
- Create: `docs/auth-user-data-plan.md`
- Do not install Supabase package until approved.

- [ ] **Step 1: Document auth proposal**

```markdown
# Auth And User Data Plan

Recommended provider: Supabase.

Why:

- Auth + Postgres in one product.
- Row Level Security supports user-owned rows and admin verification.
- Good fit for field reports, saved locations, and weekly ranking inputs.

Initial roles:

- resident
- community_reporter
- committee
- district_admin
- system_admin
```

- [ ] **Step 2: Document tables**

```sql
create table profiles (
  id uuid primary key references auth.users(id),
  display_name text not null,
  role text not null default 'resident',
  community_id text,
  created_at timestamptz not null default now()
);

create table user_saved_locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  label text not null,
  latitude double precision not null,
  longitude double precision not null,
  created_at timestamptz not null default now()
);

create table field_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  forest_id text not null,
  report_type text not null,
  patrol_count integer not null default 0,
  firebreak_km numeric not null default 0,
  fuel_management_rai numeric not null default 0,
  latitude double precision,
  longitude double precision,
  note text not null default '',
  verification_status text not null default 'pending',
  submitted_at timestamptz not null default now()
);
```

- [ ] **Step 3: Document RLS rules**

```sql
alter table profiles enable row level security;
alter table user_saved_locations enable row level security;
alter table field_reports enable row level security;

create policy "Users can read own profile"
on profiles for select
using (auth.uid() = id);

create policy "Users can manage own saved locations"
on user_saved_locations for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "Users can create own field reports"
on field_reports for insert
with check (auth.uid() = user_id);

create policy "Users can read own field reports"
on field_reports for select
using (auth.uid() = user_id);
```

- [ ] **Step 4: Commit**

```powershell
git add docs/auth-user-data-plan.md
git commit -m "docs: plan auth and user data model"
```

---

## Task 9: Final Verification Before First Build Approval

**Files:**
- No file edits unless earlier task failed.

- [ ] **Step 1: Check git state**

```powershell
git status --short
```

Expected: only intended docs/plans untracked or clean after commits.

- [ ] **Step 2: Run current tests**

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
cd ..\backend
python -m pytest -q
```

Expected: pass.

- [ ] **Step 3: Write approval summary**

Summary must say:

- What already exists.
- What will be built first.
- What is intentionally postponed.
- What data is prototype vs live.
- Whether 3D/auth require external accounts/keys.

---

## Recommended Execution Order

1. Task 1: audit doc
2. Task 2: data helpers
3. Task 3: source chip
4. Task 4: 2D community forest view
5. Task 5: backend contract optional fields
6. Stop for approval
7. Task 6: MapLibre 3D terrain spike
8. Stop for approval
9. Task 7: satellite enrichment roadmap
10. Task 8: Supabase auth/user data design
11. Stop for approval before real auth integration

## First Build Scope I Recommend

Build only Gate A first:

- 2D community forest accountability view.
- Existing `/api/dashboard`.
- Existing prototype JSON.
- Honest source chips.
- Desktop table and mobile ranking list.
- No Supabase yet.
- No MapLibre 3D yet.
- No backend DB migration yet.

Reason: fastest way to make product value visible while avoiding auth/data-source complexity too early.
