# Task: ขยาย backend ChiangMaiEyes (FastAPI) เพื่อปลดล็อกฟีเจอร์วิเคราะห์

> อ้างอิงจากโค้ดจริง: `app/main.py`, `app/services.py`, `app/models.py`, `app/config.py`,
> `app/providers/*`, `migrations/0001_field_reports.sql`
> คู่กับ spec ฝั่ง frontend (`chiangmaieyes-analytics-upgrade.md`) — ไฟล์นี้คือฝั่งที่ปลดล็อกกลุ่ม C/D

## สถาปัตยกรรมจริง (ยืนยันจากโค้ดแล้ว — อ่านก่อนเริ่ม)
- **hotspot ไม่ persist**: `get_hotspots()` / `get_history()` fetch สดจาก NASA FIRMS + GISTDA ทุก request
  แล้ว cache ใน TTL cache (`_CACHE_TTL_SECONDS=900`, history `_HISTORY_TTL_SECONDS=1800`) + เขียน snapshot JSON
- **DB (Supabase/PostGIS) เก็บแค่ `field_activity_reports`** (รายงานภาคสนาม/league) — **ไม่ใช่ที่เก็บ hotspot**
- `allow_prototype_data=False` → demo/seed ปิดใน production แล้ว (drought zones, localizedPredictions gate ด้วยตัวนี้)
- `data_quality` มีระบบ `source_mode` (LIVE/SNAPSHOT/DERIVED/UNAVAILABLE) ครบ — **ของใหม่ทุกตัวต้องมี entry นี้ด้วย**
- snapshot pattern พร้อมใช้: `_read_snapshot_json()` อ่านจาก remote (GitHub raw) → cache_dir → `backend/data/` (bundled, อ่านได้บน read-only FS)

## ⚠️ Security ก่อนอื่น
`config.py` มี `DEFAULT_GISTDA_DISASTER_API_KEY` เป็น **key จริง hardcode** ใน source ที่ commit แล้ว
→ **rotate key ที่ GISTDA, ลบค่า default ออก, ใช้ env (`gistda_disaster_api_key`) อย่างเดียว**
ตรวจ `.env`/`.env.example` ว่าไม่มี secret หลุด และ `.env` อยู่ใน `.gitignore` แล้ว

---

## 🐞 บั๊กที่ต้องแก้ระหว่างทาง (เจอจากการอ่านโค้ด)

**BUG-1 — history cache key ไม่นับ `days`**
ใน `get_history()`: `_get_cached("history")` / `_set_cached("history")` ใช้คีย์คงที่ "history"
→ พอเปิด `?days=` แต่ละ window จะชนกัน คืนค่าที่ cache ไว้ก้อนแรกเสมอ
แก้: คีย์เป็น `f"history:{days}"` (เช่นเดียวกับ `_hotspot_trend` ที่เรียก `get_history(days=window_days)`)

**BUG-2 — frontend ยิง `/src/data/dashboardSnapshot.json` → 404**
เป็น fetch ฝั่ง frontend ที่ path ไม่มีบน deploy (คนละตัวกับ `_read_remote_snapshot` ฝั่ง backend)
→ จัดการในงาน frontend (กลุ่ม D cleanup) ไม่ใช่ backend แต่บันทึกไว้กันสับสน

---

## งาน backend แมปกับฟีเจอร์ที่ติด

### B1 — เปิด window ของ `/api/history` ให้ปรับได้  (ปลดล็อก: D1 "7วัน/30วัน/ทั้งฤดู")
- `main.py`: เปลี่ยน route เป็น `def history(days: int = 30, ...)` + validate (เช่น `1 <= days <= 180`)
  ส่งต่อ `get_history(settings, days=days)`
- แก้ BUG-1 (cache key ต่อ days)
- frontend เรียก `/api/history?days=7|30|...`
- **คาเวียต upstream**: `fetch_hotspot_history` ยิง NASA FIRMS — ช่วงยาว (>30) ช้า/โดน rate limit
  → ตั้ง TTL ยาวขึ้นสำหรับ days มาก, เพิ่ม cap, และถ้า provider ดึงไม่ครบให้ best-effort (เหมือนที่ทำอยู่)
- **"ทั้งฤดู" จริง** (ธ.ค.–เม.ย. ~150 วัน) ดึงสดทุกครั้งไม่ไหว → ใช้ B2 (precompute) แทน

### B2 — Persist ประวัติรายวัน เพื่อ YoY + ทั้งฤดู  (ปลดล็อก: C1 YoY, D1 ทั้งฤดู)
ปัญหา: ไม่มีที่เก็บ + NASA NRT API ดึงปีก่อนสด ๆ ไม่เวิร์ก (archive แยก endpoint, ช้า, rate limit)
แนวทางที่เข้ากับโค้ดเดิม (เลือกอย่างใดอย่างหนึ่ง):
- **(แนะนำ) precomputed JSON** ใน `backend/data/season_history.json`
  รูปแบบ: `{ "<season_label>": [{ "date":"YYYY-MM-DD", "count":n }, ...] }` (เช่น "2568", "2569")
  อ่านผ่าน `_read_snapshot_json()` ที่มีอยู่ → อ่านได้บน serverless read-only FS
  เติมข้อมูลด้วย job ใน `scripts/` (มี Windows refresh task อยู่แล้ว) ดึง FIRMS archive รายวันสะสมลงไฟล์
- **หรือ ตาราง Supabase** `hotspot_daily(date PK, count, [district])` แล้ว job append รายวัน
  (มี Supabase อยู่แล้ว แต่ field_activity_reports ใช้ service-role key + RLS — ทำตาราง read สาธารณะแยก)
- เพิ่ม route: `GET /api/history/season?year=2569` หรือพารามิเตอร์ `compare_year` ใน `/api/history`
  คืน series รายวัน align ตาม **day-of-season** (เริ่ม 1 ธ.ค.) เพื่อให้ frontend ซ้อนกราฟ YoY ได้
- model ใหม่ใน `models.py` + `data_quality["history_archive"]` (source_mode SNAPSHOT, ระบุ cadence/วันที่ build)
- **ห้าม fabricate ปีก่อน** ถ้ายังไม่ได้ build archive → คืน empty + source_mode UNAVAILABLE ให้ frontend ซ่อน toggle

### B3 — ประวัติรายอำเภอ  (ปลดล็อก: D3 ranking ย้อนหลัง, A2 ครบ 25 อำเภอตามช่วง)
ตอนนี้ `fetch_hotspot_history` คืนแค่ `(date, count)` ไม่มี district → ranking ย้อนหลังทำไม่ได้
- แก้ provider ให้คืน **per-detection** (lat/lng/detected_at) หรือ **daily-by-district** counts
  (FIRMS area CSV มี lat/lng ราย detection อยู่แล้ว → bucket เข้า 25 อำเภอด้วย logic เดียวกับ frontend
   หรือ `_DISTRICT_CENTROIDS` ใน `fire_phase.py` แบบ nearest)
- เก็บลง archive เดียวกับ B2 (เพิ่ม field district) เพื่อไม่ต้อง re-fetch
- expose ใน `/api/history` (เพิ่ม `by_district`) หรือ `/api/history/districts`
- **คาเวียตจริง**: snapshot ปัจจุบันมี district อยู่แล้วบน `items[]` → frontend ทำ ranking ของ "ตอนนี้" ได้ทันที (งาน A2/D3)
  B3 จำเป็นเฉพาะตอนต้องการ ranking ตามช่วง 7/30 วัน/ทั้งฤดู

### B4 — การกระจายรายชั่วโมง  (ปลดล็อก: D2 hourly จริง)
`HotspotHistoryDay` มีแค่ date+count (ไม่มีชั่วโมง) → hourly ทั้ง window ทำจาก history ไม่ได้
- ทางเลือก A (เบา): frontend ใช้ `items[].detected_at` ของ snapshot ปัจจุบัน (sparse นอกฤดู — ถูกต้องแล้ว) ไม่ต้องแตะ backend
- ทางเลือก B (ครบ): provider คืน **detection พร้อมเวลา** หรือ **`hour_histogram: [24]`** ต่อ window
  (FIRMS มี `acq_time` ราย detection → รวมเป็น 24 buckets ได้) เก็บลง archive (B2) ด้วยจะดีสุด
- ใส่ `data_quality` ของ hourly ตามแหล่งจริง

### B5 — พื้นที่เผาไหม้ (ไร่)  (ปลดล็อก: C2 burned area)
ไม่มี field ไร่ที่ไหน (`area_rai` มีแค่บน `CommunityForest` = พื้นที่ป่า ไม่ใช่รอยไหม้)
`data_quality.fire_zones = UNAVAILABLE` อยู่แล้ว
- เพิ่ม `providers/burnscar_provider.py` ต่อ **GISTDA burned-area / VIIRS burned area (เช่น MODIS MCD64A1 / VIIRS VNP64)**
- คืนไร่รายวัน + สะสม + ระบุ cadence (burn scar ออกเป็นงวด ไม่ใช่ราย ชม.) ใส่ `data_quality["burned_area"]`
- ก่อน config แหล่งจริง: source_mode UNAVAILABLE → frontend แสดงป้าย "ยังไม่ได้ต่อข้อมูล" **ห้ามประมาณจากจำนวนจุด**

---

## 🔁 Loop engineering — โปรโตคอลบังคับต่อทุกงาน

**ทำทีละงานแบบวน loop จนผ่านจริง** ใช้ pytest ใน `tests/` (มีอยู่แล้ว) เป็น exit-gate ไม่ใช่แค่ "รันแล้วดูเหมือนได้":

```
สำหรับแต่ละ task:
  1. IMPLEMENT
  2. VERIFY — พิสูจน์ด้วยของจริง:
     • curl/httpx เรียก endpoint จริง → ตรวจ schema (pydantic ผ่าน) + ค่าสมเหตุผล
     • เขียน/ขยาย pytest ใน tests/ ให้ครอบ: happy path, empty/best-effort (provider ล่ม),
       cache แยกตาม param, และ source_mode ถูกต้อง
     • กระทบยอด: เลขที่คืน ตรงกับที่ provider/snapshot ให้มาจริง (ไม่มีค่าแต่งเติม)
  3. DIAGNOSE → ถ้า test แดง แก้แล้วกลับไป 1
  4. DONE — pytest เขียว + acceptance ของ task นั้นครบ ถึงปิดงาน
```

**กฎกันโกง:** ถ้าแหล่งยังไม่ config → ต้องคืน `source_mode=UNAVAILABLE`/empty **ห้าม fabricate**
(สอดคล้อง `allow_prototype_data=False`). มี test ที่ assert ว่า "ไม่มี key/แหล่ง → ไม่มีข้อมูลปลอม"

### ตรวจผ่านเมื่อ (acceptance ต่อ task)
- **Security**: ไม่มี key จริงใน source/`git log`; `gistda_disaster_api_key` อ่านจาก env เท่านั้น; key เก่าถูก rotate
- **BUG-1**: เรียก `?days=7` กับ `?days=30` ติดกันได้คนละผลลัพธ์ (test ยืนยัน cache แยกตาม days)
- **B1**: `/api/history?days=N` คืน N วันจริง (len series ตรง), validate ขอบเขต, days ใหญ่ไม่ทำ request พัง (best-effort)
- **B2**: archive ปีก่อนมาจากไฟล์/ตารางจริง, `data_quality.history_archive` ระบุ build date; ไม่มี archive → UNAVAILABLE (ไม่ใช่เลขสุ่ม); job ใน scripts/ รันแล้วไฟล์อัปเดตจริง
- **B3**: ผลรวมรายอำเภอของวันหนึ่ง = count รวมของวันนั้น (กระทบยอด); district map ถูก (สุ่มเช็คพิกัด)
- **B4**: ผลรวม 24 buckets = count รวมของ window; ชั่วโมงมาจาก acq_time จริง
- **B5**: ไม่ config แหล่ง → UNAVAILABLE; config แล้ว → ไร่รายวัน/สะสมตรงกับ provider, cadence ระบุถูก
- **ทุก task**: เพิ่ม `data_quality` entry ของชั้นใหม่ + best-effort try/except + cache key ครอบ param ใหม่

### Done-gate รวม
`pytest` ทั้ง suite เขียว · ทุก endpoint ใหม่มี source_mode ถูกต้องทั้งเคสมี/ไม่มีแหล่ง ·
ไม่มี secret ใน source · cache ไม่ชนข้าม param · response เดิม (`/api/dashboard` ฯลฯ) ไม่ regression

### B6 — ขยายอำเภอให้ครบ 25  (ปลดล็อก: X4 consistency, เฟสไฟครบจังหวัด)
ตอนนี้ `_DISTRICT_CENTROIDS` (ใน `fire_phase.py`) + `get_district_physics` (ใน `fire_spread_physics.py`)
ครอบแค่ ~6 อำเภอ → `/api/fire-phases` คืน 6 การ์ด, ดัชนีเสี่ยงรายอำเภอไม่ครบ
- เติม centroid + physics (fuel/slope/history) ให้ครบ **25 อำเภอเชียงใหม่**
- `classify_fire_phases` วนครบ 25 (อำเภอไม่มีจุด = phase normal score ต่ำ ไม่ใช่ถูกตัดทิ้ง)
- กระทบยอดกับ report/analytics ให้นับอำเภอชุดเดียวกัน (X4)

---

## ลำดับงานที่แนะนำ
1. **Security**: rotate + ย้าย GISTDA key ออกจาก source
2. **B1 + BUG-1**: เปิด `?days=` (ปลดล็อก 7/30 วันให้ frontend D1 ทันที งานเล็ก)
3. **B2**: วาง persistence (precomputed `season_history.json` + job ใน `scripts/`) → ปลดล็อก YoY + ทั้งฤดู
4. **B3**: เพิ่ม district ลง archive → ranking ตามช่วง
5. **B4**: hourly histogram ลง archive
6. **B5**: burn-scar provider (งานใหญ่สุด ทำเมื่อพร้อมแหล่ง)

## หลักการคงเดิม
- ของใหม่ทุกชั้นต้องมี `data_quality` + `source_mode` ที่ตรงความจริง
- ไม่มีข้อมูล = UNAVAILABLE/empty อย่างซื่อสัตย์ ไม่ fabricate (ตรงกับ `allow_prototype_data=False` ที่ตั้งไว้แล้ว)
- best-effort ต่อ provider (provider เดียวล่มไม่ทำทั้ง response พัง) — ทำตามแพทเทิร์น try/except เดิมใน `get_history`
- cache ให้ครอบ param ใหม่ทุกตัว (อย่าซ้ำรอย BUG-1)
