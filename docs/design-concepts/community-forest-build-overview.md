# Community Forest Build Overview

สถานะ: draft for review before build
วันที่: 2026-06-21

เอกสารนี้สรุป tech stack และข้อมูลที่จะใช้ก่อนเริ่ม build concept “Community Forest Accountability” ให้ตรวจสอบก่อนลงโค้ดจริง

## เป้าหมายของ build

ทำ UI แยกสำหรับแกนป่าชุมชนของ ChiangMaiEyes:

- เห็นป่าชุมชนและขอบเขตการดูแลบนแผนที่
- เห็นเขตจัดการไฟ / ขอบเขตอำนาจ / ขอบเขตที่เป็น prototype อย่างซื่อสัตย์
- เห็นอันดับรายสัปดาห์ของผลงานดูแลไฟป่าและกิจกรรมไฟป่า
- เชื่อม ranking row กับ map selection และ inspector
- แยกสถานะข้อมูล `LIVE`, `DERIVED`, `PROTOTYPE`, `UNAVAILABLE`, และ fallback ให้ชัด

## Frontend Stack

ใช้ stack เดิมของ repo:

- React `19.2.6`
- TypeScript `6.0.3`
- Vite `8.0.14`
- Leaflet `1.9.4`
- `leaflet-velocity` สำหรับ wind particle layer
- `lucide-react` สำหรับ icons
- Vitest `4.1.7`
- jsdom สำหรับ frontend tests

ไฟล์หลักที่จะเกี่ยว:

- `frontend/src/App.tsx`
- `frontend/src/components/DashboardMap.tsx`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/styles/global.css`
- `frontend/src/data/community-forests-prototype.json`
- `frontend/src/data/fire-management-zones-prototype.json`
- `frontend/src/data/chiangmai-province.json`
- `frontend/src/data/chiangmai-districts.json`

แนวทาง build frontend:

- ไม่แทน UI ปัจจุบันทันที
- ทำเป็น route/view/mode แยกก่อน เช่น community forest view
- ใช้ components แยก ไม่ยัดเพิ่มใน `App.tsx` จนใหญ่กว่าเดิม
- reuse `DashboardMap` layer ที่มีอยู่: `communityForests`, `fireZones`, `hotspots`, `wind`, `fuelRisk`, `predictions`
- ranking table/list ต้อง click/hover แล้วเลือก map selection ได้
- mobile ต้องจัดลำดับ: map preview -> selected forest -> weekly ranking -> contacts

## Backend Stack

ใช้ stack เดิม:

- Python `>=3.12`
- FastAPI `0.115.6`
- Uvicorn `0.34.0`
- Pydantic `2.10.4`
- pydantic-settings `2.7.1`
- httpx `0.28.1`
- python-dotenv `1.0.1`
- earthengine-api `>=1.5.0`
- google-generativeai `>=0.8.0`
- pytest `8.3.4`

ไฟล์หลักที่จะเกี่ยว:

- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/services.py`
- `backend/app/weekly_forest_league.py`
- `backend/app/providers/hotspot_provider.py`
- `backend/app/providers/earth_engine_provider.py`
- `backend/tests/test_weekly_forest_league.py`

API ปัจจุบันที่ใช้ได้:

- `GET /api/dashboard`
- `GET /api/data-status`
- `GET /api/history`
- `GET /api/hotspots`
- `GET /api/hotspots/history`
- `GET /api/pm25`
- `GET /api/weather`
- `GET /api/risk`
- `POST /api/advisor/briefing`
- `POST /api/advisor/chat`

community forest data อยู่ใน `DashboardResponse.intelligence.weekly_forest_league`

## Current Data Sources

### Live / near-live

- Hotspots:
  - Royal Forest Department Firemap
  - GISTDA Disaster STAC VIIRS 3-day
  - GISTDA API Gateway VIIRS 1-day
  - NASA FIRMS VIIRS
  - backend reconcile/deduplicate sources และ clip ให้อยู่ในเชียงใหม่
- PM2.5:
  - Air4Thai Live API
- Weather/wind:
  - Thai Meteorological Department AWS

### Derived

- Risk score:
  - deterministic formula จาก PM2.5, hotspots, weather/wind, fire-spread factors
- Localized predictions:
  - rule-based estimate จาก dashboard inputs
- Satellite dryness layer:
  - Google Earth Engine-ready contract
  - dataset ids: `COPERNICUS/S2_SR_HARMONIZED`, `UCSB-CHC/CHIRPS/DAILY`, `USGS/SRTMGL1_003`, `ESA/WorldCover/v200`
  - ตอนนี้ยังมี seeded fallback ถ้า Earth Engine ยังไม่เปิด

### Prototype / seed

- Community forest geometry:
  - `frontend/src/data/community-forests-prototype.json`
  - source note ระบุว่า RFD KML เป็น point geometry เท่านั้น และ prototype boundaries เป็น estimated buffers
- Fire-management zones:
  - `frontend/src/data/fire-management-zones-prototype.json`
  - ใช้ district polygon / prototype zone aggregation
- Weekly forest league:
  - `backend/app/weekly_forest_league.py`
  - seed records และ seed field reports ใน `backend/app/services.py`
  - production จริงต้องเชื่อม reporting database หรือ verified source ก่อน

## Data Contract For New UI

Frontend ใช้ type เดิม:

- `DashboardResponse`
- `OperationalIntelligenceResponse`
- `WeeklyForestLeagueResponse`
- `WeeklyForestRankingEntry`
- `DataQualityMetadata`
- `SourceMode`

ranking entry fields ที่มีแล้ว:

- `forest_id`
- `forest_name`
- `village`
- `tambon`
- `amphoe`
- `latitude`
- `longitude`
- `total_score`
- `rank`
- `report_count`
- `last_report_at`
- `score_breakdown.management`
- `score_breakdown.prevention`
- `score_breakdown.utilization`
- `score_breakdown.ecological_outcome`
- `reasons`

data ที่ UI concept ต้องการ แต่ contract ยังไม่ครบ:

- authority owner / responsible agency ต่อ forest
- boundary confidence ต่อ forest
- official boundary geometry ต่อ forest
- weekly hotspot activity delta ต่อ forest
- patrol/firebreak/fuel-management raw activity metrics ต่อ forest
- field report media/photo status
- verification status ของรายงานภาคสนาม

ข้อเสนอ: build รอบแรกใช้ fields ที่มี + prototype JSON เฉพาะ UI; backend contract ใหม่ค่อยเพิ่มหลังตรวจข้อมูล

## Suggested Component Plan

Frontend components ใหม่:

- `CommunityForestView`
- `CommunityForestMapPanel`
- `CommunityForestInspector`
- `WeeklyForestLeagueTable`
- `WeeklyForestRankList`
- `SourceModeChip`
- `BoundaryLegend`
- `FieldReportCTA`
- `CommunityForestLayerControls`

shared logic:

- map selection helper ใช้ `MapSelection` เดิม
- source mode display ใช้ `DataQualityMetadata`
- ranking sorting/filtering อยู่ frontend ชั่วคราว ถ้า dataset ยังเล็ก

## Backend Changes Likely Needed

ถ้าจะ build ให้เกิน prototype:

- เพิ่ม endpoint เฉพาะ `GET /api/community-forests`
- เพิ่ม endpoint เฉพาะ `GET /api/community-forests/league`
- เพิ่ม model สำหรับ `CommunityForestBoundary`
- เพิ่ม `authority_owner`, `boundary_source`, `boundary_confidence`, `verification_status`
- ย้าย seed `_FOREST_RECORDS` / `_FIELD_REPORTS` ออกจาก `services.py` ไปเป็น data provider หรือ DB
- เพิ่ม tests สำหรับ ranking explainability และ boundary confidence

ถ้าจะ build เฉพาะ visual prototype:

- ไม่ต้องเพิ่ม backend endpoint รอบแรก
- ใช้ `/api/dashboard` + local prototype JSON ได้

## Deployment / Runtime

Frontend:

- Vercel static build
- `npm --prefix frontend install`
- `npm --prefix frontend run build`
- output: `frontend/dist`

Backend:

- Vercel FastAPI project
- root directory should be `backend`
- entrypoint: `api.index:app`
- backend rewrites all paths to `/api/index.py`

Local dev:

- frontend Vite port `5173`
- frontend proxies `/api` and `/health` to `http://localhost:8000`
- backend run via Uvicorn/FastAPI

Windows note:

- ใช้ `npm.cmd` / `npx.cmd` บนเครื่องนี้เพื่อเลี่ยง PowerShell execution-policy issue

## Verification Plan

ก่อน merge:

- `npm.cmd run build` ใน `frontend`
- `npm.cmd run test` ใน `frontend`
- `python -m pytest -q` ใน `backend`
- browser verification desktop และ mobile
- ตรวจว่า source mode labels ไม่หลอกว่า prototype เป็น live
- ตรวจว่า Thai text ไม่ overflow บน mobile

## Open Questions For Review

1. Ranking ควรจัดจาก “ผลงานดูแลไฟป่า” อย่างเดียว หรือควรหักคะแนนจาก “กิจกรรมไฟป่า/จุดความร้อนในพื้นที่” ด้วย
2. ขอบเขตอำนาจควรแสดงระดับไหนก่อน: ป่าชุมชน, เขตจัดการไฟ, อำเภอ, หรือหน่วยงานรัฐ
3. รายงานภาคสนามรอบแรกควรเป็น UI mock เท่านั้น หรือเริ่มวาง backend contract ด้วย
4. source ที่ถือว่า official สำหรับ community forest boundary คืออะไร: RFD KML, Thaicfnet, หรือ dataset อื่น
5. weekly recompute ใช้วันอาทิตย์ 23:55 ตาม backend เดิมได้เลยไหม

## Recommended First Build Scope

ทำ narrow first pass:

- เพิ่ม community forest view แยก
- ใช้ `/api/dashboard` + prototype JSON
- ทำ desktop table + mobile ranking list
- map selection เชื่อมกับ forest/ranking
- source labels ชัดว่า community forest/ranking ยังเป็น `PROTOTYPE`

ยังไม่ทำ:

- database รับรายงานจริง
- auth/operator workflow
- official boundary ingestion
- Figma component library เต็มชุด
