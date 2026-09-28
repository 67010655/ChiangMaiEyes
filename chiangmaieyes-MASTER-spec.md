# ChiangMaiEyes — MASTER spec (cross-cutting + แผนที่ความครอบคลุม)

อ่านไฟล์นี้ก่อน แล้วค่อยลงรายละเอียดที่:
- `chiangmaieyes-analytics-upgrade.md` — หน้าวิเคราะห์ (frontend กลุ่ม A/B/C/D + loop)
- `chiangmaieyes-backend-upgrade.md` — backend FastAPI (security + BUG + B1–B5 + loop)

ไฟล์นี้คือชั้น "ข้ามทั้งแอป" + บอกตรงๆ ว่าอะไร **ตรวจจริงแล้ว** อะไร **ยังต้องเจาะ**

---

## 🗺️ แผนที่ความครอบคลุม (สถานะจริง)

| ส่วนของแอป | ตรวจจริงแล้ว? | คุมใน spec ไหน |
|---|---|---|
| หน้าวิเคราะห์ (Analytics) | ✅ เปิดดูครบทุก chart + ทุกช่วงเวลา | analytics A/B/C/D |
| Backend `/api/dashboard` `/api/history` | ✅ อ่าน response + โค้ดจริง | backend |
| Backend `/api/fire-phases` `/api/community-forests` | ✅ ยิง response จริงแล้ว | **ไฟล์นี้ X4/X10** |
| หน้าหลัก — panel ขวา (AQ now, PM2.5 24h, 7-day, wind rose, district risk) | ✅ เห็นจริง พบปัญหา (ดู X1–X3) | **ไฟล์นี้** |
| เฟสไฟ (Fire Phase) | ✅ เห็นจริง + response — ครอบแค่ 6 อำเภอ | **ไฟล์นี้ X4** |
| รายงานสถานการณ์ (Situation Report) | ✅ ทดสอบ PNG และ PDF print layout ใน Chromium แล้ว (29 ก.ย. 2569) | **ไฟล์นี้ X11** |
| 3D (MapLibre terrain) | ✅ เห็นจริง — marker semantics ปนกัน (X10) | **ไฟล์นี้ X10** |
| แผนที่หลัก (markers/heatmap/layers) | ✅ คลิก marker แล้ว — cyan = bubble รายอำเภอ (X10) | **ไฟล์นี้ X10** |

> ตรวจ export PDF/PNG ของรายงานแล้วใน Chromium: PNG ดาวน์โหลดจริง, PDF print layout ได้ 2 หน้า A4, ฟอนต์ไทยและตารางครบ (29 ก.ย. 2569)
> ปัญหา X1–X10 และ analytics/backend upgrade ยังต้องประเมินตาม done-gate ของแต่ละส่วน

---

## 🌐 ปัญหาข้ามทั้งแอป (เจอจากการสำรวจจริง — ต้องแก้)

**X1 — ข้อมูลสดบางรอบมา 0 / ไม่ครบ (reliability)**
สังเกตจริง: รีโหลดคนละรอบได้ ACTIVE HOTSPOTS = 1 บ้าง = 0 บ้าง, PM2.5 = 12 บ้าง = 0 บ้าง
→ provider บางตัว timeout/partial แล้ว UI โชว์ 0 เหมือนเป็นค่าจริง
แก้: แยก **loading / error / empty(จริง)** ออกจากกันให้ชัด — ห้ามโชว์ 0 ตอน fetch ยังไม่เสร็จ/ล้มเหลว;
ใช้ `data_quality[domain].source_mode` + `is_stale` ตัดสิน; ถ้า UNAVAILABLE/stale → ป้ายเตือน ไม่ใช่เลข 0 เฉยๆ

**X2 — เรียก Open-Meteo ซ้ำซ้อนจาก browser (network log ยืนยัน 3× forecast, 2× air-quality)**
หน้าหลักยิง Open-Meteo ตรงจาก client หลายครั้ง ทั้งที่ backend ก็มี weather/pm25 อยู่แล้ว
แก้: (ก) dedupe/debounce การ fetch ฝั่ง client; (ข) **ย้าย PM2.5-24h + wind rose + wind field ไปผ่าน backend**
ให้เป็น single source of truth (ลดความซ้ำ + แก้ X3) — frontend ไม่ควรมีท่อข้อมูลคู่ขนานกับ backend

**X3 — ป้ายแหล่งข้อมูลไม่ตรงกันทั้งแอป**
PM2.5 ถูกป้ายว่า "CAMS" (panel 24h) / "Air4Thai PCD + AQICN" (`/api/dashboard`) / "Open-Meteo Air Quality" (`/api/history`)
weather ป้ายว่า "TMD AWS" (dashboard) แต่ history ใช้ "Open-Meteo"
แก้: **แสดงป้ายจาก `source` / `data_quality.source` ของ API จริงเสมอ ห้าม hardcode** (เช่นเลิกใช้คำว่า CAMS ถ้าจริงคือ Air4Thai+AQICN)

**X4 — การนับรายอำเภอไม่ตรงกันหลายที่ (consistency bug ใหญ่)**
- รายงานสถานการณ์: ตารางอำเภอ **ถูกต้อง** (หางดง = 1 จุดจริง, มี ดัชนีเสี่ยง/จุดวิกฤต) ← reference
- หน้าหลัก: คลิกวงกลมรายอำเภอ → popup สรุป **ถูกต้อง** (PM2.5/จุด/ป่าชุมชน/ความเสี่ยง) ← reference
- หน้าวิเคราะห์ "รายอำเภอ": ลิสต์ตายตัว 6 อำเภอ = 0 หมด (ผิด — ดู analytics D3/A2)
- เฟสไฟ + `/api/fire-phases`: คืน **แค่ 6 อำเภอ** (ชุด `_DISTRICT_CENTROIDS`) ไม่ครบ 25
แก้: ทำ **ฟังก์ชันรวมการนับอำเภอชุดเดียว** (จาก `items[].district` จริง) ครอบ **25 อำเภอ** ใช้ทั้ง
analytics ranking + เฟสไฟ + report + map popup ให้ตรงกัน; **ฝั่ง backend ขยาย `_DISTRICT_CENTROIDS` + `classify_fire_phases` ให้ครบ 25 อำเภอ** (งานนี้ใส่ใน backend spec ด้วย)

**X4b — fire_pm25_correlation ซ้ำซ้อน**
`/api/fire-phases` มี `fire_pm25_correlation` จริงอยู่แล้ว (date + hotspot_count + pm25 วันเดียวกัน/วันถัดไป + elevated)
แต่ analytics scatter (HS×PM2.5) คำนวณเองจาก history → เสี่ยงไม่ตรงกัน
แก้: ให้ analytics scatter **ดึงจาก `fire_pm25_correlation` ของ backend** (มี next-day lag + elevated flag ครบกว่า) ไม่คำนวณซ้ำ

**X5 — "จุดวิกฤต" ไม่มีนิยามกลาง**
header "CRITICAL ZONES", รายงาน "จุดวิกฤต X จุด", ตารางป่าชุมชน (analytics B2) ต่างอ้าง "จุดวิกฤต" แต่ไม่มี constant ร่วม
ป้าย FRP legend บอกชัด: **>100 MW = extreme** → ใช้เป็นนิยาม
แก้: ตั้ง `CRITICAL_FRP_MW = 100` (หรือค่าที่ทีมยืนยัน) **ที่เดียว** แล้วอ้างอิงทุกที่ — frontend และ backend ให้ตรงกัน

**X6 — `data_quality` ของดีมาก แต่ไม่ได้โชว์ให้ผู้ใช้เลย**
API คืน `source`, `age_minutes`, `is_stale`, `update_cadence_minutes`, `decision_use` ครบทุก domain
→ สำหรับ ops console ผู้ว่าฯ การโชว์ "ข้อมูลล่าสุด X นาที" + ป้าย stale + tooltip `decision_use` มีค่ามาก และมีข้อมูลอยู่แล้ว
แก้: เพิ่ม badge ความสด/แหล่ง/ความเชื่อมั่นต่อ panel (อย่างน้อยใน header แต่ละการ์ด) อ่านจาก `data_quality`

**X7 — เขตวัน/timezone**
ทุกอย่างเป็น Asia/Bangkok (+07:00), backend ระบุ "Bangkok calendar day" → กราฟ/แกนวันที่ frontend ต้องยึด
Bangkok day ให้ตรง (อย่าใช้ UTC/local ของเครื่อง ผู้ใช้ที่ทำให้วันเหลื่อม)

**X8 — Thai mojibake**
backend มี `repair_thai_mojibake_tree` แต่ data จริงยังเจอชื่อเพี้ยน (เช่น "จ.ชียงใหม่") → verify ชื่ออำเภอ/สถานี/ป่าที่ render แล้วไม่เพี้ยน

**X9 — UI เล็กน้อย**
ข้อความ "กำลังเชื่อมต่อข้อมูลสด…" ทับปุ่มสลับ basemap (DARK/OSM/ดาวเทียม/TERRAIN) บนหน้าหลัก → จัด z-index/ตำแหน่ง

**X10 — สี marker สื่อความหมายต่างกันข้ามหน้า (ทำให้สับสน)**
- หน้าหลัก: วงกลม cyan ใหญ่ = **bubble สรุปรายอำเภอ** (คลิกแล้วมี popup PM2.5/จุด/ป่าชุมชน/ความเสี่ยง) — เป็น feature ที่ดี
- 3D: จุด cyan เคยใช้แทนป่าชุมชนจนเต็มจอ; ข้อมูลหลักปัจจุบันคือ **677 แปลงที่มีขอบเขต** จาก shapefile ที่ได้รับจาก RECOFTC ส่วน hotspot จริงมีไอคอนไฟแยก
- เลเยอร์ "PM2.5 stations" (72) เป็นอีกชุด
→ cyan ใช้แทน 3 อย่างคนละหน้า + ป่าชุมชนเต็มจอกลบ hotspot จริง
แก้: กำหนด **color/shape ต่อชนิดข้อมูลให้คงที่ทั้งแอป** (hotspot, ป่าชุมชน, PM2.5 station, district bubble ต้องแยกชัด),
ใส่ legend ที่ตรงกัน, พิจารณาลดความเด่น/ทำ toggle ของป่าชุมชนใน 3D; ใช้สี FRP (เหลือง→แดง, วิกฤต>100) กับ hotspot เท่านั้น

**X11 — export PDF/PNG ของรายงาน: ทดสอบแล้วใน Chromium (29 ก.ย. 2569)**
ก่อนข้อมูลสดพร้อม รายงานแสดงสถานะรอและปิดปุ่มส่งออก เพื่อไม่ให้เกิด NaN/-Infinity
ทดสอบกด PNG ดาวน์โหลดจริงและเปิดภาพตรวจแล้ว; ปุ่ม PDF เรียก print และ Chromium print layout ส่งออกเป็น A4 สองหน้า
ภาษาไทย ตาราง และส่วนท้ายอ่านได้ครบ ปัจจุบันรายงานไม่มีแผนที่ จึงไม่มีปัญหา tile/CORS ในไฟล์ส่งออก
หากเพิ่มแผนที่หรือเปลี่ยน renderer ในอนาคต ให้ทดสอบ export ซ้ำ

---

## 🔁 Loop & Done-gate ระดับแอป (ครอบของทั้งสองไฟล์)
ทำตาม loop ในแต่ละไฟล์ + เกณฑ์รวมนี้ก่อนเคลม "เสร็จทั้งงาน":
1. **Single-source-of-truth**: ไม่มีท่อข้อมูลซ้ำ (X2); ป้ายแหล่งมาจาก API ทุกที่ (X3)
2. **Consistency**: เลขเดียวกันตรงกันทุกหน้า — รัน **Golden trace ข้ามหน้า**: hotspot จริง 1 จุด ต้องตรงกันใน
   header / analytics ranking / report table / fire-phase / satellite donut / FRP histogram (X4, X5)
3. **Honesty**: ทุก panel เคารพ `source_mode`; 0/partial ไม่ปลอมเป็นค่าจริง (X1); demo ปิดใน production
4. **Provenance**: ความสด/แหล่งโชว์ให้ผู้ใช้เห็น (X6)
5. **Regression**: หน้า/chart เดิมไม่พัง; mobile + light/dark ผ่านทุกหน้า

---

## ✅ สถานะการสำรวจ
สำรวจครบทุก surface แล้ว (วิเคราะห์ · หน้าหลัก+map · 3D · เฟสไฟ · รายงาน · `/api/dashboard|history|fire-phases`)
ปัญหาจริงเก็บเข้า **X1–X11** + analytics A/B/C/D + backend B1–B5 ครบ

**X11 ผ่านการทดสอบพื้นฐานแล้ว:** ดาวน์โหลด PNG และตรวจ PDF print layout จาก Chromium เมื่อ 29 ก.ย. 2569
(ผมไม่กด export ให้ในขั้นสำรวจ เพราะมันเป็นการสร้าง/ดาวน์โหลดไฟล์ ควรให้คุณ/Claude Code รันบนเครื่องเอง)

> เมื่อแก้ X1–X11 + analytics A–D + backend B1–B5 ครบ และผ่าน done-gate ทั้ง 3 ไฟล์ = "ครอบคลุมทุกเรื่อง" จริง
