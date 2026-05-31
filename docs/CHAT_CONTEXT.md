# ChiangMaiEyes Chat Context

เอกสารนี้บันทึกบริบทจากแชทที่ใช้สร้าง MVP เพื่อให้กลับมาต่อโปรเจกต์ได้โดยไม่ต้องไล่บทสนทนาใหม่ทั้งหมด

## เป้าหมายโปรเจกต์

ChiangMaiEyes เป็น public environmental intelligence dashboard สำหรับจังหวัดเชียงใหม่ ประเทศไทย

เป้าหมายไม่ใช่การทำนายไฟป่า แต่คือช่วยให้ประชาชนและหน่วยงานท้องถิ่นเห็นความสัมพันธ์ระหว่าง

- จุดความร้อนหรือ wildfire hotspots
- ค่า PM2.5
- ทิศทางลมและสภาพอากาศ
- ผลกระทบต่อชุมชน

## ข้อกำหนดหลักจากผู้ใช้

- คุยและเอกสารสำคัญควรรองรับภาษาไทย
- Frontend ใช้ React, Vite, TypeScript, Leaflet.js, OpenStreetMap
- Backend ใช้ Python และ FastAPI
- Deploy frontend ไป Vercel Free Tier
- Deploy backend ไป Render Free Tier ในขั้นถัดไป
- MVP ไม่มี database ใช้ cached JSON files
- ทุก API, dataset, SDK, library, deployment service ต้องใช้ฟรีหรือมี free tier สำหรับ MVP
- ต้องรองรับ mobile browsers
- ห้ามใช้ paid datasets, paid APIs, paid AI services หรือ paid infrastructure

## Data Sources ที่ตกลงไว้

### Hotspots

Primary: GISTDA Disaster daily hotspot update

Backup: NASA FIRMS API free public access

หมายเหตุ: ในแชทผู้ใช้ระบุชัดว่า hotspot ต้องการใช้ของ GISTDA Disaster เพราะมีอัปเดตรายวัน

### PM2.5

Primary: Air4Thai

Backup: OpenAQ

### Weather

Primary: Thai Meteorological Department Open Data ถ้าเข้าถึง parameter ที่ต้องใช้ได้

Backup: Open-Meteo API

Required fields:

- wind speed
- wind direction
- temperature
- humidity

### Maps

OpenStreetMap ผ่าน Leaflet

## Features ที่สร้างใน MVP แล้ว

- React dashboard shell
- Leaflet map
- hotspot markers
- PM2.5 station markers
- wind arrows
- province boundary overlay สำหรับเชียงใหม่แบบ simplified
- layer toggles: hotspots, PM2.5, wind, district/province boundary
- PM2.5 panel พร้อม category และ color coding
- hotspot panel พร้อม count และ density
- wind panel พร้อม direction, speed, temperature, humidity
- risk score 0-10 พร้อม formula โปร่งใส
- Thai situation summary fallback
- responsive layout สำหรับมือถือ

## API Endpoints ที่ backend มีแล้ว

- `GET /api/hotspots`
- `GET /api/pm25`
- `GET /api/weather`
- `GET /api/risk`
- `GET /api/summary`
- `GET /api/dashboard`
- `GET /health`

## Current Deployment

Frontend production alias:

```text
https://frontend-ruby-gamma-15.vercel.app
```

Latest production deployment observed in chat:

```text
https://frontend-9zghgy17e-peerayoot425-6995s-projects.vercel.app
```

Vercel project linked as:

```text
peerayoot425-6995s-projects/frontend
```

Status from Vercel inspect: `Ready`

## Current Backend Status

Backend exists locally under `backend/` and tests passed locally, but it has not yet been deployed to Render.

Current frontend therefore falls back to embedded sample data if `/api/dashboard` is unavailable.

To make live data work publicly:

1. Deploy `backend/` to Render
2. Set Vercel env var:

```text
VITE_API_BASE_URL=https://your-render-service.onrender.com
```

3. Redeploy frontend

## Risk Score Formula

Current deterministic MVP formula:

```text
min(10, round(min(PM2.5/15,4) + min(hotspot_count/50,4) + wind_factor))
```

`wind_factor = 2` เมื่อทิศทางลมมีแนวโน้มพัดควันเข้าสู่ตัวเมืองเชียงใหม่ ไม่เช่นนั้นเป็น `0`

Categories:

- `0-3`: Low
- `4-6`: Medium
- `7-10`: High

## Chiang Mai Boundary Decision

ผู้ใช้ขอให้โฟกัสเชียงใหม่และตีกรอบจังหวัดเชียงใหม่บนหน้าเว็บ

สิ่งที่ทำแล้ว:

- ปรับ map center/zoom ให้มองเชียงใหม่เป็นหลัก
- เพิ่ม `maxBounds` เพื่อให้ pan ไม่หลุดจากบริเวณเชียงใหม่มากเกินไป
- แทนกรอบหยาบเดิมด้วย simplified province boundary ใน `frontend/src/components/DashboardMap.tsx`

ข้อจำกัดปัจจุบัน:

- boundary ยังเป็น simplified outline ฝังใน frontend
- production-grade version ควรแทนด้วย GeoJSON ที่ละเอียดกว่า

แหล่ง boundary ที่ควรใช้ต่อ:

- OSM relation `1908771` สำหรับจังหวัดเชียงใหม่
- หรือ official Thai administrative GeoJSON ถ้าหาแหล่งเปิดที่เชื่อถือได้

## GISTDA Disaster Integration Plan

ยังไม่ได้ต่อ live GISTDA Disaster API เพราะต้องรู้ endpoint/format ที่แน่นอนก่อน

แนวทาง backend ที่ควรทำต่อ:

1. เพิ่ม service adapter เช่น `backend/app/providers/gistda_disaster.py`
2. ดึง daily hotspot feed จาก GISTDA Disaster
3. Normalize เป็น schema เดิมของ `HotspotResponse`
4. Filter เฉพาะพื้นที่จังหวัดเชียงใหม่
5. Cache last successful response ลง `backend/data/hotspots.json`
6. ถ้า GISTDA ล้มเหลว ให้ใช้ NASA FIRMS หรือ cached JSON

Schema ที่ frontend ใช้อยู่แล้ว:

```json
{
  "count": 134,
  "density_per_100_km2": 3.8,
  "latest_update": "2026-05-31T08:00:00+07:00",
  "source": "GISTDA Disaster daily hotspot update",
  "items": [
    {
      "id": "HS-001",
      "latitude": 18.9342,
      "longitude": 98.7424,
      "district": "แม่ริม",
      "confidence": 82,
      "source": "GISTDA Disaster",
      "detected_at": "2026-05-31T07:10:00+07:00"
    }
  ]
}
```

## Files Created or Changed

Key files:

- `README.md`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/services.py`
- `backend/data/hotspots.json`
- `backend/data/pm25.json`
- `backend/data/weather.json`
- `backend/tests/test_risk.py`
- `frontend/src/App.tsx`
- `frontend/src/components/DashboardMap.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/risk.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/styles/global.css`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/DEPLOYMENT.md`
- `docs/FALLBACKS.md`
- `docs/ROADMAP.md`

## Verification Already Done

Backend:

```text
python -m pytest
2 passed
```

Frontend:

```text
npm.cmd test
2 passed
```

Frontend build:

```text
npm.cmd run build
passed
```

Vercel deploy:

```text
npx.cmd vercel@latest --prod --yes
Ready
```

## Important Implementation Notes

- PowerShell `npm` can be blocked by execution policy, use `npm.cmd`
- Some files originally written by PowerShell had BOM; Vite build failed until JSON config files were converted to UTF-8 without BOM
- `moduleResolution` was changed to `Bundler` for current TypeScript/Vite compatibility
- `vite-env.d.ts` was added for Vite import typings and CSS imports
- `vite.config.ts` currently proxies local `/api` to `http://localhost:8000` for dev
- Production frontend needs `VITE_API_BASE_URL` once backend is deployed

## Next Best Tasks

1. Deploy backend to Render
2. Add GISTDA Disaster daily hotspot adapter
3. Replace simplified Chiang Mai boundary with official/detailed GeoJSON
4. Set `VITE_API_BASE_URL` in Vercel
5. Redeploy frontend
6. Add live PM2.5 and weather adapters
7. Add freshness indicators in the UI

## User Preference From This Chat

- Keep things practical and not too complicated
- Prefer getting a working deployed version quickly
- Thai language communication is preferred
- User wants Chiang Mai-specific framing, not generic Thailand map framing