# ChiangMaiEyes — ปล่อยงานแก้ข้อมูลหลัง audit

ตรวจถึง 10 ตุลาคม 2026 เวลา 23:17 ICT

## ผลรอบนี้

ติดตั้ง migration ที่ค้างและปล่อย backend/frontend ขึ้น [เว็บจริง](https://chiangmaieyes.vercel.app/) แล้ว การควบคุม Chrome กลับมาใช้ได้หลังเปิดโปรไฟล์ kmitl.ac.th ใหม่และเชื่อมส่วนขยายใหม่

นี่เป็นการปล่อยงานแกนข้อมูลของชุด 1 และแก้ข้อความตกค้างใน FRP legend ยังไม่ใช่การจบแผนหลัง audit ทั้ง 6 ชุด และยังไม่ใช่การยืนยันความแม่นยำภาคสนาม

## ฐานข้อมูล

- รัน `supabase/migrations/20261010220000_observation_identity_and_pm_semantics.sql` ใน SQL Editor ของ `zskizogquupkneubcayc` สำเร็จ ตรวจข้อความที่วางตรงไฟล์ทั้ง 95 บรรทัดก่อน Run
- ซ่อม observation keys 7,686 แถว มี audit ของ key ก่อน/หลัง เก็บ id และ payload ต้นทางเดิม
- ก่อนรันมี observation rows 8,135; หลังรันตรวจพบ 8,136 เพราะระบบจัดเก็บรอบใหม่ระหว่างตรวจ ไม่มีคำสั่งลบแถวใน migration
- SQL ตรวจหลังติดตั้งพบ canonical key ที่ไม่ตรงกัน 0 แถว
- คลัง hotspot ช่วง 7 วันที่ตรวจ จากเดิม 38 keys เป็น 19 unique observations ไม่รวมการตรวจคนละเวลา/ดาวเทียมจากการอยู่ใกล้กัน
- แยกค่า AQI ที่เคยถูกแปลงเป็น PM2.5 จำนวน 425 แถวออกจากสถิติ PM ของช่วงที่ตรวจ ผล PM measured ในคลังช่วงนั้นเป็น 0 รายการ; ข้อมูลดิบยังอยู่
- ตาราง audit เปิด RLS; `anon` และ `authenticated` ไม่มี SELECT และ `anon` เรียก archive read/ingest functions โดยตรงไม่ได้ API เว็บยังตรวจสิทธิ์ตามหน้าที่ของ endpoint
- Migration นี้รันผ่าน SQL Editor รายงานนี้ไม่ได้ยืนยันว่ามีการลงทะเบียนเวอร์ชันใน Supabase CLI migration history

## ข้อมูลและ UI ที่ตรวจบนเว็บจริง

- Dashboard/API: 19 observations เป็น nominal 17 + low 2 กราฟแสดงสูง 0%, ปกติ 89%, ต่ำ 11%, ไม่ระบุ 0% ตัวเลขสัดส่วนนี้เป็นสัดส่วนรายการในชุดข้อมูล ไม่ใช่ accuracy
- PM measured เป็น null แสดงว่าขาดข้อมูล; AQI สำรอง 60 สถานีแสดงเป็นดัชนี แยกเวลาต้นทางกับเวลารับ ไม่มีหน่วย µg/m³ ติดกับ AQI
- ทะเบียนป่าชุมชนยัง 677 แห่ง ขอบเขต cmf-th-3192 แสดงข้อความให้ตรวจทบทวน และไม่สรุปยอดในขอบเขตนั้น
- ตัวอย่างรายงาน 24 ชั่วโมงพบ 2 จุด แสดงฝุ่น `— µg/m³` และอธิบายว่าไม่มีสถานีที่ใช้ได้ ไม่เติมค่าศูนย์
- ผลตรวจภาคสนามสำหรับผู้ดูแลเปิดได้จากหน้า Data; session เดิมและพื้นที่ป่าชุมชนโหลดได้
- 3D โหลด Mapzen DEM และหมุดได้ แก้คำอธิบายสีเป็นช่วง FRP ใน MW ทั้ง 2D/3D ไม่มีคำว่า “วิกฤต/extreme” ใน legend นี้
- ตรวจ Dark/Light บน desktop และหน้าข้อมูลมือถือ 390 px: body/document width เท่ากับ viewport ไม่มี overflow แนวนอน คืน viewport และ Dark mode แล้ว
- Console ของหน้าเว็บที่ตรวจล่าสุดไม่มี error/warning

## การปล่อย

| ส่วน | Deployment | Target | Status | ที่ตรวจ |
|---|---|---|---|---|
| Backend | `dpl_9VzrFHxuSodQYPTYiH3A79hMGCat` | production | READY | health/dashboard/archive/677 forests ตอบ 200; runtime sin1 |
| Frontend รุ่นสุดท้าย | `dpl_GzGHar91jpyyYNw5SpmKacrLN318` | production | READY | HTML ที่เสิร์ฟตรง SHA256 ของ local build; FRP legend ใหม่ตรวจบนเว็บจริง |

- Frontend build บน Vercel รุ่นสุดท้ายประมาณ 10.3 วินาทีจาก created → ready; runtime backend Singapore ส่วน build machine อยู่ iad1
- ยืนยันโดเมน `chiangmaieyes.vercel.app` และ `backend-mocha-tau-49.vercel.app` ชี้ deployment ที่ปล่อยแล้ว
- Source provenance: working tree บน HEAD `41b9319062b600b3b8ea9b9a023146273d7346f3` รวมการแก้ที่ยังไม่ commit ไม่ได้อ้างว่าเป็น clean commit release
- Staged deployment มี Vercel Authentication ใช้ `vercel curl` ตรวจ HTTP และ SHA256; ตรวจ UI จาก local build ที่ตรงกันก่อนปล่อยและเว็บจริงหลังปล่อย ไม่สร้าง share link หรือเปลี่ยน protection
- Error log scan backend ช่วง 30 นาทีที่ตรวจไม่คืนรายการ error ไม่ใช่การรับรองว่าไม่มีปัญหาที่ไม่ถูกบันทึก; drains/ระบบแจ้งเตือนโครงสร้างพื้นฐานยังไม่ได้ตรวจในรอบนี้

## การทดสอบและข้อจำกัด

- Backend 173 tests ผ่าน; frontend/SQL PGlite 90 tests ผ่าน (รัน frontend ซ้ำหลังแก้ legend); TypeScript และ build ผ่าน
- มี Starlette TestClient/httpx deprecation warning 1 รายการ และ MapLibre chunk ใหญ่กว่า 500 kB ยังไม่แก้ด้วยการปิด warning
- ยังไม่ได้ดาวน์โหลด PDF/CSV/รูปหรืออัปโหลดไฟล์เพิ่มในรอบนี้ เนื่องจาก Browser เคยปฏิเสธสิทธิ์ไฟล์และไม่ได้เปลี่ยนสถานะข้อจำกัดนั้น ตรวจเฉพาะตัวอย่างรายงานบนหน้าเว็บ
- ไม่ส่งอีเมลทดสอบซ้ำในรอบนี้ การยืนยันโดเมนอีเมลและการทดลองกับสมาชิกหลายบัญชี/ชุมชนจริงยังคงเป็นงานถัดไป
- การตรวจ geometry เป็น structural check ไม่ใช่ full topology audit หรือการยืนยันกับ RECOFTC; ยังไม่มี ground truth ที่พิสูจน์ model accuracy

## งานถัดไปตามแผนที่อนุมัติ

1. ชุด 2: รวม analytics/archive ให้ใช้ช่วงเวลาและตัวตน observation เดียวกัน ย้าย backfill/history ยาวออกจาก request หน้าเว็บ มีคิว/progress/resume และวัด performance
2. ชุด 3: เก็บ UX ของกราฟ/ลำดับข้อมูล/mobile/keyboard/report และทำ source/time labels ให้สอดคล้องทุกจุด
3. ชุด 4: ตรวจ workflow หลายบัญชี สิทธิ์ รูป คิวอีเมล และแหล่งกล้อง
4. ชุด 5–6: เพิ่มข้อมูล/แบบจำลองที่มีต้นทางชัดเจน และตรวจ accuracy ด้วยเหตุจริง/หลักฐานภาคสนามก่อนกล่าวอ้างผล

## หลักฐาน

ภาพและ JSON อยู่ที่ `C:/Users/User/.codex/visualizations/2026/10/06/01a10fbb-e315-7c21-8852-fdaa133d0551/release1/`

- `migration-success.png`, `migration-verified.txt`, `database-read.json`
- `staged-dashboard.json`, `staged-archive.json`, `staged-forests.json`, `production-dashboard.json`, `production-pm-archive.json`
- `production-final-archive.png`, `production-confidence-dark.png`, `production-confidence-light.png`, `production-mobile-aqi.png`

ความหมายระดับ VIIRS อ้างอิง [NASA product documentation](https://modaps.modaps.eosdis.nasa.gov/services/about/products/viirs-land-c2-nrt/vj114imgtdl_nrt.html) ส่วน PM ย้อนหลังแบบจำลองอ้างอิง [Open-Meteo/CAMS documentation](https://open-meteo.com/en/docs/air-quality-api)
