# Task: ต่อยอดหน้า "วิเคราะห์" ChiangMaiEyes — LIVE ONLY (ไม่มี demo ในหน้า deploy)

> เป้าหมายของเจ้าของ: **หน้า production แสดงข้อมูลจริงทั้งหมด ไม่มี synthetic/demo เลย**
> หลักการนี้ตรงกับ backend ที่มีอยู่แล้ว ซึ่งคืน `data_quality.source_mode` และโน้ตว่า
> *"Prototype intelligence layers are disabled. Only live, derived-from-live, or configured verified data is returned."*
> → ดังนั้นทุก component ใหม่ต้องยึดหลักเดียวกัน: **ถ้าไม่มีข้อมูลจริง ให้แสดง empty/unavailable state อย่างซื่อสัตย์ ห้าม fabricate**

## STEP 0 — สำรวจไฟล์จริงก่อน (บังคับ)
ไฟล์ dashboard เป็น HTML self-contained ไฟล์เดียวที่เจ้าของแก้เองมาเยอะ **ห้ามสมมติจากความจำ**
อ่านไฟล์จริง จด: วิธีวาด hand-drawn SVG charts, CSS tokens (dark/light), ตำแหน่ง fetch ของ
`/api/dashboard` `/api/history`, และคำศัพท์ไทยเดิม (จุดวิกฤต ฯลฯ) แล้วใช้ตามนั้น
**ห้ามพัง:** mobile responsiveness, ธีม, และอย่าลืม `transform-box:fill-box; transform-origin:center` ใน SVG animation

---

## สถาปัตยกรรมข้อมูลจริง (ยืนยันจาก network + response แล้ว)

**Backend (Vercel serverless) — แหล่ง hotspot อยู่ที่นี่ ปลอดภัย ไม่หลุด key:**
- `GET /api/dashboard` — สถานการณ์ปัจจุบัน (schema ด้านล่าง)
- `GET /api/history` — ย้อนหลัง **30 วันเท่านั้น** รายวัน
- `GET /api/community-forests` — จุดป่าชุมชน
- `GET /api/fire-phases` — ข้อมูลเฟสไฟ

**Static GeoJSON:** `/chiangmai-province.json`, `/chiangmai-districts.json` (25 อำเภอ)
**ไม่มีไฟล์ตำบล** | **External (เรียกตรงจาก browser, keyless):** Open-Meteo (กราฟ PM2.5 24h + wind field grid)

**🔴 บั๊กต้องเก็บกวาด:** หน้าโหลด `/src/data/dashboardSnapshot.json` → **404** ทุกครั้ง (ไฟล์หาย) ให้ลบ ref หรือสร้างไฟล์ให้ถูก

### schema `/api/dashboard` (ย่อ)
```
hotspots: { count, density_per_100_km2, latest_update, source,
  items[]: { id, latitude, longitude, district, subdistrict(=null!), landuse_type(=null),
             landuse_name(=null), satellite("N20"), confidence, frp, brightness,
             source, detected_at, sources[], source_count },
  source_breakdown: { "GISTDA Disaster STAC VIIRS 3-day":n, "GISTDA API Gateway VIIRS 1-day":n, "NASA FIRMS":n } }
pm25: { current_pm25, category, color, trend, source("Air4Thai PCD + AQICN"),
  stations[]: { id, name, district, latitude, longitude, pm25, trend, updated_at } }   // ~72 สถานี
weather: { wind_speed_kmh, wind_direction_deg, wind_direction_text, temperature_c, humidity_percent,
  source("Thai Meteorological Department AWS"), pressure_hpa, rain_*, temperature_min/max_today_c }
risk: { score, category, formula, factors{ pm25_points, hotspot_points, spread_points, ... } }  // สูตรเปิดเผยชัด
intelligence: { hotspot_trend: { window_days:30, recent_count, previous_count, change_percent, source },
  satellite_layers{...NDVI/NDMI/NBR (seeded)}, landuse_breakdown[], ... }
data_quality: { <domain>: { label, source, source_mode(LIVE|DERIVED|SNAPSHOT|UNAVAILABLE),
  latest_update, age_minutes, confidence, is_stale, note, decision_use } }
```
### schema `/api/history`
```
{ days:30, hotspots[]:{date,count}, pm25[]:{date,value},
  weather[]:{date,temp_max,temp_min,wind_max,humidity},
  sources:{ hotspots:"NASA VIIRS (SNPP/NOAA-20/NOAA-21)", pm25:"Open-Meteo Air Quality", weather:"Open-Meteo" } }
```

---

## ⚠️ มีอยู่แล้ว อย่าสร้างซ้ำ
30-day trend, confidence donut, hourly pattern, FRP histogram, HS×PM2.5 scatter, อำเภอ ranking (คลิกได้),
VIIRS/MODIS donut, stat summary, การ์ด "เทียบช่วงก่อนหน้า" — **ครบแล้ว** ต่อยอดเท่านั้น

## กฎกลางสำหรับทุก component ใหม่
1. อ่านจาก `/api/dashboard` หรือ `/api/history` เท่านั้น — **ห้ามมี demo array ใน production**
2. เคารพ `data_quality[domain].source_mode`: ถ้า `UNAVAILABLE` → แสดงป้าย "ยังไม่ได้ต่อข้อมูล" ไม่ใช่กราฟเปล่าหรือเลขปลอม
3. นอกฤดูไฟข้อมูลจะ ~0 → ทำ empty state ที่ดูตั้งใจ ("นอกฤดูไฟ · ไม่มีเหตุการณ์ช่วงนี้")
4. DEMO toggle เก็บไว้เป็น **dev-only flag** (เช่นเช็ค hostname=localhost) — build production ซ่อน/ปิด

---

## ฟีเจอร์ — แบ่งเป็น "ทำได้เลยด้วยข้อมูลจริง" vs "ต้องเพิ่มแหล่งก่อน"

### ✅ กลุ่ม A — ทำได้เลย 100% จริง (ทำกลุ่มนี้ก่อน)

**A1. แตก source-product + per-satellite**
- source-product: ใช้ `hotspots.source_breakdown` ตรงๆ (STAC 3-day / API 1-day / FIRMS) ทำเป็น panel
- per-satellite: group `items[].satellite` → normalize **N20→NOAA-20, N21→NOAA-21, N/SNPP→Suomi NPP**,
  MODIS→Terra/Aqua ถ้ามี; ค่าที่ map ไม่ได้ → bucket "VIIRS (ไม่ระบุดวง)" **ห้ามเดา**
- เขียนเป็น `normalizeSatellite(raw)` มี mapping ชัด + fallback

**A2. ขยาย district ranking ให้ครบ 25 อำเภอ**
- ใช้ `items[].district` group เอง (ปัจจุบันโชว์ ~6) ทำให้เลื่อน/พับดูครบ 25 ได้
- คงพฤติกรรมคลิกเพื่อซูมแผนที่เดิมไว้

> หยุดให้ review หลังจบกลุ่ม A

### 🟡 กลุ่ม B — ต้องเพิ่มไฟล์/แหล่ง frontend ทำต่อเองได้

**B1. drill ตำบล (ตำบล)**
- ติดที่: `items[].subdistrict = null` และ **ไม่มีไฟล์ขอบเขตตำบล**
- วิธีจริง: เพิ่ม **tambon GeoJSON ของเชียงใหม่** (GADM level-3 / กรมการปกครอง) แล้วทำ
  point-in-polygon ฝั่ง frontend เพื่อหา tambon ของแต่ละ hotspot → drill อำเภอ→ตำบลได้
- ก่อนมีไฟล์: แสดงเฉพาะระดับอำเภอ + โน้ต "ระดับตำบลรอข้อมูลขอบเขต"

**B2. ตารางป่าชุมชน**
- มี shapefile ขอบเขตที่ได้รับจาก RECOFTC แล้ว: 677 แปลงเป็นตัวเลขป่าชุมชนหลักเพียงตัวเดียว
- จัดอันดับ hotspot/จุดวิกฤตที่ **อยู่ภายใน polygon** ด้วย point-in-polygon; ถ้าจะแสดงจุดใกล้เคียงนอกเขต
  ให้แยกเป็นคอลัมน์ proximity พร้อมระยะและป้ายว่า "นอกขอบเขต"
- เกณฑ์จุดวิกฤต: ใช้ค่าจาก `frp` + เกณฑ์เดิมในไฟล์ (อย่านิยามใหม่)

### 🔴 กลุ่ม C — ต้องแก้ backend ก่อน (อย่าทำ frontend จนกว่าจะมี endpoint)

**C1. YoY เทียบฤดูปีก่อน**
- ติดที่: `/api/history` มีแค่ **30 วัน** ไม่มี archive ปีก่อน
- ต้องการ backend เปิด เช่น `GET /api/history?from=YYYY-MM-DD&to=YYYY-MM-DD` หรือ
  endpoint season-archive ที่คืนรายวันของฤดูปีก่อน (แหล่งเดิม GISTDA/FIRMS query ย้อนหลัง + cache เป็น JSON)
- เมื่อมี endpoint แล้ว frontend: ซ้อนเส้นปีนี้ (ทึบ) กับปีก่อน (จาง/ประ) align ตาม day-of-season,
  reuse การ์ด ▲/▼ % เดิม โชว์ "เทียบฤดูเดียวกันปีก่อน ±X%"
- **อย่าใช้ demo ปีก่อนเด็ดขาด** — ถ้ายังไม่มี endpoint ให้ซ่อน toggle นี้ไว้

**C2. พื้นที่เผาไหม้ (ไร่)**
- ติดที่: **ไม่มี field ไร่ที่ไหนเลย** และ `data_quality.fire_zones = UNAVAILABLE`
- ต้องการ backend ต่อ **burn-scar product จริง** (GISTDA burned area / VIIRS) คืนไร่รายวัน + สะสม
  พร้อมระบุ cadence (burn scar มักออกเป็นงวด ไม่ใช่ realtime) ใน `data_quality`
- เมื่อมีแล้ว: การ์ด "พื้นที่เผาสะสม (ไร่)" + กราฟเส้นสะสม (เน้นช่วง cumulative ชันเพื่อเล่าเรื่องอัตราเร่ง)
- ก่อนมีแหล่ง: แสดง source_mode UNAVAILABLE อย่างซื่อสัตย์ ห้ามประมาณจากจำนวนจุด

---

### 🐞 กลุ่ม D — แก้บั๊ก component เดิม (เจ้าของชี้มาเอง — ทำคู่กับกลุ่ม A)

**D1. กราฟ "แนวโน้มจุดความร้อน 30 วัน" + ปุ่มช่วงเวลาไม่ทำงาน**
อาการจริง (ยืนยันแล้ว): กดสลับ 24ชม./7วัน/30วัน/ทั้งฤดู **การ์ดบนเปลี่ยน แต่กราฟไม่เปลี่ยน window** —
กราฟค้าง 30 วันตลอด, แกน x เป็น offset `-29..-0` อ่านยาก, พอเลือก 7 วัน (ข้อมูล ~0) แกน y ยุบเป็น `0/0/1/1`
ป้ายซ้ำ แท่งลอยไม่ติดฐาน
แก้:
- ผูก window ของกราฟเข้ากับปุ่มช่วงเวลาจริง (7วัน=7จุด, 30วัน=30จุด ฯลฯ) ไม่ใช่ค้าง 30
- เปลี่ยนแกน x เป็น **วันที่จริง** (เช่น 30 พ.ค., 6 มิ.ย.) ไม่ใช่ `-29`
- แกน y: ใช้ tick จำนวนเต็ม ไม่มีป้ายซ้ำ, ตั้ง max ขั้นต่ำ (เช่น ≥4) เพื่อไม่ให้กราฟยุบตอนข้อมูลน้อย,
  ให้แท่งอิงฐาน 0 เดียวกับเส้น MA
- หัวข้อกราฟเปลี่ยนตามช่วงที่เลือก (อย่าค้าง "30 วัน")
- **"24 ชม."**: history เป็นรายวัน ทำกราฟรายวันไม่ได้ → ถ้าจะมีโหมดนี้ ต้องเป็นกราฟ **รายชั่วโมง**
  จาก `items[].detected_at` (ดู D2) มิฉะนั้นให้ปิดปุ่มนี้สำหรับกราฟ trend หรือสลับไปโชว์ hourly แทน
- **"ทั้งฤดู"**: `/api/history` มีแค่ 30 วัน → ครอบทั้งฤดูไม่ได้จริง ต้องรอ backend (กลุ่ม C) ก่อน
  ระหว่างนี้ให้ป้ายชัดว่าเป็น 30 วันล่าสุด อย่าแกล้งทำเป็นทั้งฤดู
- **การ์ด "เทียบช่วงก่อนหน้า"** ตอนนี้ใช้ `previous_count` 30 วันคงที่ทุกโหมด → โหมด 24ชม./7วัน เทียบผิด
  ให้คำนวณ current vs previous ตาม **window เดียวกับที่เลือก** (เช่น 7 วันนี้ vs 7 วันก่อนหน้า)

**D2. "รูปแบบการเผาตามช่วงเวลา" เป็น demo อยู่ ไม่ใช่ข้อมูลจริง**
อาการ: โชว์ระฆังคว่ำเต็มสวยทุกโหมด ทั้งที่มี hotspot จริง 1 จุด → เป็น synthetic ฝังไว้
แก้: คำนวณจาก **ชั่วโมงของ `items[].detected_at` จริง** (group by hour 0-23) — off-season จะมี 1-2 แท่ง ซึ่ง **ถูกต้องแล้ว**
- ตอบโจทย์เจ้าของ: ใช่ จะอัปเดตเมื่อ backend มี hotspot มากขึ้น **ก็ต่อเมื่อ wire เข้า detected_at จริง**
- ข้อจำกัด: dashboard ปัจจุบันมีแต่ snapshot ตอนนี้ ถ้าต้องการ hourly ทั้ง window ต้องให้ backend
  คืน detected_at ของ hotspot ย้อนหลัง (ไม่ใช่แค่ count รายวัน) — ระบุเป็น backend task ถ้าจำเป็น
- ถ้ายังไม่มีข้อมูลพอ ให้ empty state ซื่อสัตย์ ห้ามคง bell curve ปลอม

**D3. "จุดความร้อนรายอำเภอ" ไม่ดึงจากข้อมูลจริง**
อาการ: โชว์ลิสต์ตายตัว 6 อำเภอ (แม่แจ่ม/เชียงดาว/จอมทอง/ฝาง/แม่ริม/เมือง) = 0 หมด
ทั้งที่ hotspot จริงอยู่ **"แม่วาง"** ซึ่งไม่อยู่ในลิสต์
แก้:
- group `items[].district` จากข้อมูลจริง อำเภอที่มีจุดต้องโผล่ (แม่วาง ต้องขึ้น 1)
- **แสดงครบทั้ง 25 อำเภอ** จาก `/chiangmai-districts.json` (อำเภอที่ไม่มีจุด = 0) เรียง count มาก→น้อย
  ทำให้เลื่อน/พับดูครบได้ คงพฤติกรรมคลิกเพื่อซูมแผนที่
- ข้อจำกัด: `/api/history` ไม่มี field district → การนับรายอำเภอตอนนี้ได้จาก **snapshot items ปัจจุบัน** เท่านั้น
  ถ้าต้องการให้ ranking สะท้อนช่วง 7/30 วัน/ทั้งฤดู ต้องให้ backend ใส่ district ลง history (backend task)

**D4. (บั๊กแถมที่เจอ) normalization ดาวเทียมผิด**
โดนัท "แหล่งข้อมูลดาวเทียม" จัด `satellite="N20"` (= NOAA-20 ซึ่งเป็น **VIIRS**) ไปเป็น **MODIS 100%**
→ แก้ `normalizeSatellite()` ใน A1 ให้ map N20/N21/N/SNPP → VIIRS, MOD/MYD/Terra/Aqua → MODIS ให้ถูก
(บั๊กนี้ทับซ้อนกับงาน A1 — แก้ทีเดียว)

## 🔁 Loop engineering — โปรโตคอลบังคับต่อทุกฟีเจอร์

**อย่าทำรอบเดียวแล้วเชื่อว่าเสร็จ** ทุกฟีเจอร์ต้องวน loop จน "ตรวจผ่าน" จริงก่อนไปต่อ:

```
สำหรับแต่ละฟีเจอร์:
  1. IMPLEMENT — เขียนโค้ด
  2. VERIFY — เปิดหน้าจริง (local/preview) แล้วพิสูจน์กับข้อมูลจริง:
     • เปิด /api/dashboard และ /api/history ในอีกแท็บ → กระทบยอดเลขให้ตรงกับที่กราฟแสดง
     • เปิด console: ต้องไม่มี error/warning ใหม่
     • กดทุก toggle/ปุ่มช่วงเวลา (24ชม./7วัน/30วัน/ทั้งฤดู) → ดูว่ากราฟเปลี่ยนจริง
     • ทดสอบ empty state (นอกฤดูข้อมูล ~0) → ต้องไม่พัง/ไม่โชว์เลขปลอม
     • ทดสอบ mobile width + light/dark
  3. DIAGNOSE — ถ้าข้อไหนไม่ผ่าน ระบุสาเหตุ (อย่าเดา) แล้วกลับไป 1
  4. DONE — ผ่านครบทุกข้อใน "ตรวจผ่านเมื่อ" ของฟีเจอร์นั้นเท่านั้นถึงปิดงาน
```

**Golden trace test (ใช้ยืนยันว่าทุก component ดึงเลขเดียวกันจริง):**
หยิบ hotspot จริง 1 จุดจาก `/api/dashboard` (เช่นจุดใน **แม่วาง**, `satellite=N20`, `frp=2.52`) แล้วเช็คว่ามันโผล่ถูกทุกที่:
อำเภอ ranking → แม่วาง = 1 (ไม่ใช่ 0), โดนัทดาวเทียม → **VIIRS** (ไม่ใช่ MODIS), FRP histogram → 1 แท่งที่ช่วงต่ำ
ถ้าจุดนี้หายหรือไปโผล่ผิดที่ = ยังไม่ผ่าน

**กฎกันโกง loop:** ห้ามนับว่า "ผ่าน" ถ้าผลที่เห็นมาจาก demo/synthetic — ผูกกับ `data_quality[domain].source_mode`
ถ้า source_mode = UNAVAILABLE แล้ว component ยังโชว์กราฟสวย = ผิด ต้องเป็น empty/ป้าย "ยังไม่ได้ต่อข้อมูล"

### ตรวจผ่านเมื่อ (acceptance ต่อฟีเจอร์)
- **A1 ดาวเทียม/แหล่ง**: N20→VIIRS, N21→VIIRS, N/SNPP→Suomi, ค่าที่ map ไม่ได้→"VIIRS (ไม่ระบุดวง)"; source-product ตรงกับ `source_breakdown`; donut รวม = `hotspots.count`
- **A2 รายอำเภอ**: แสดงครบ 25 อำเภอจาก districts.json, เรียง count desc, อำเภอที่มีจุดจริงโผล่ค่า >0 ตรงกับ items, คลิกแล้วซูมแผนที่ได้
- **B1 ตำบล**: หลังใส่ tambon GeoJSON, จุดถูก map เข้าตำบลถูกต้อง (สุ่มเช็ค 3 จุดกับพิกัดจริง); ยังไม่มีไฟล์ = โชว์เฉพาะอำเภอ + ป้ายชัด
- **B2 ป่าชุมชน**: ตารางนับจุดใน polygon จริง; จุดใกล้นอกเขตต้องแยกและติดป้าย "ระยะใกล้ ไม่ใช่ในเขต"; คอลัมน์จุดวิกฤตใช้เกณฑ์ FRP เดิม
- **C1 YoY**: toggle ซ่อนเมื่อ backend ยังไม่มี endpoint ปีก่อน; เมื่อมี—เส้นปีก่อน align day-of-season, การ์ด % คำนวณจากข้อมูลจริง 2 ฤดู, ไม่มี array ปีก่อน hardcode
- **C2 ไร่**: เมื่อ source_mode=UNAVAILABLE ต้องเป็นป้าย "ยังไม่ได้ต่อข้อมูล"; เมื่อมีแหล่ง—การ์ด+กราฟสะสมตรงกับค่าไร่จาก API
- **D1 กราฟ trend**: window เปลี่ยนตามปุ่มจริง (นับจำนวนจุดบนแกน x ให้ตรง 7/30), แกน x เป็นวันที่จริง, แกน y tick จำนวนเต็มไม่ซ้ำ, หัวข้อเปลี่ยนตามช่วง, การ์ดเทียบใช้ window เดียวกัน
- **D2 รายชั่วโมง**: ค่ามาจาก `detected_at` จริง (off-season = 1-2 แท่ง ถือว่าถูก), ไม่มี bell curve คงที่; ข้อมูลไม่พอ = empty state
- **D3 รายอำเภอ**: (= A2) แม่วางต้องโผล่, ไม่มีลิสต์ตายตัว 6 อำเภอ
- **D4 ดาวเทียม**: จุด N20 เดี่ยวต้องเป็น VIIRS 100% ไม่ใช่ MODIS

### Done-gate รวม (ก่อนปิดทั้งงาน)
รัน Golden trace ครบ · ไม่มี error console · ทุกปุ่มช่วงเวลาเปลี่ยนกราฟจริง · empty state ทุก panel ดูตั้งใจ ·
mobile + light/dark ผ่าน · **regression**: 6 chart เดิมที่ "อย่าแตะ" ยังทำงานเหมือนเดิม · ไม่มี demo ใน build production

## ลำดับงาน
1. STEP 0 + สรุป inventory กลับมายืนยัน
2. ทำกลุ่ม **A + D** (จริงทั้งหมด เห็นผลทันที) → review
3. กลุ่ม **B** (ต้องเพิ่มไฟล์ tambon / ตัดสินใจ proximity vs รอ polygon)
4. กลุ่ม **C** เฉพาะเมื่อ backend เปิด endpoint แล้ว
5. เก็บบั๊ก `/src/data/dashboardSnapshot.json` 404 + ปิด DEMO ใน production

## เสร็จเมื่อ
ทุก component อ่านจาก API จริง, เคารพ source_mode, มี empty/unavailable state ที่ซื่อสัตย์,
เข้าธีม/ภาษา/SVG เดิม, mobile ไม่พัง, ไม่มี demo สักบรรทัดใน build production
