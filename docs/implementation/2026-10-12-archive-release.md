# ChiangMaiEyes: คลังย้อนหลังและคิวงาน — 12 ตุลาคม 2026

## งานที่ปล่อยในรอบนี้

ปล่อยงานชุด 2 ของแผนหลัง audit ขึ้น [เว็บจริง](https://chiangmaieyes.vercel.app/) แล้ว บันทึกนี้เป็นผลตรวจของชุดคลังย้อนหลัง ยังมีงาน UX, workflow หลายบัญชี และแบบจำลองตามแผนถัดไป

- หน้าวิเคราะห์เลือก 24 ชั่วโมง / 7 / 30 / 90 / 180 วันได้ ทุกกราฟของประวัติใช้ข้อมูลและช่วงเวลาเดียวกันจากฐานข้อมูล ไม่ใช้จุดบนแผนที่ 5 วันแทนสถิติย้อนหลัง
- FRP, ระดับความเชื่อมั่นต้นทาง, ดาวเทียม, อำเภอ, ตำบล และพิกัดในขอบเขตป่าชุมชนอ่านจาก observation keys เดียวกัน ตัดซ้ำตามดาวเทียม พิกัด และเวลาตรวจพบ
- แยก PM2.5 สถานีวัดกับแบบจำลอง CAMS มีตัวเลือกชัดเจน ไม่แปลง AQI เป็นความเข้มข้นฝุ่น ตารางย้อนหลังแยกลมสถานีและลมแบบจำลองด้วย
- แยกวันต้น/ท้ายที่มีเพียงบางชั่วโมงออกจากวันเต็มและวันที่คำขอขาด ใช้ 0 เฉพาะวันเต็มที่คำขอ VIIRS ทั้งสามดาวเทียมตอบรับถูกต้อง ช่องว่างไม่ใช่ 0 และการไม่พบจุดไม่ได้ยืนยันว่าไม่มีไฟ
- ค่าเฉลี่ยและความสัมพันธ์ใช้วันเต็มที่คำขอครบ จับคู่ PM กับจุดดาวเทียมในวันเดียวกัน ไม่เติมค่าที่หาย
- เลือกเวลาย้อนหลังและเลือกดูเฉพาะข้อมูลที่ระบบได้รับ ณ เวลานั้นได้ เก็บ revision เดิมไว้ ชื่ออำเภอ/ตำบลที่จับคู่ได้มาจาก polygon จริง และแยก spatial assignment จาก payload ต้นทาง
- ย้าย backfill เป็นคิวถาวร ปิดเว็บได้ มี progress, จำกัดสอง worker พร้อมกัน, lease fencing, retry/backoff และทำต่อเฉพาะชุดที่ล้มเหลว
- ล้างหน้าข้อมูลผู้ดูแลและยกเลิกผลคำขอที่ค้างเมื่อ session เปลี่ยน ป้องกันผลช่วง 7 วันมาทับ 180 วันเมื่อกดเปลี่ยนเร็ว

## ข้อผิดพลาดของขอบเขตที่พบและซ่อม

คำขอ NASA เดิมใช้กรอบ `97.25,17.35,99.68,20.28` แต่ไฟล์ `backend/app/data/chiangmai-province.json` มีขอบใต้ที่ 17.2732043° จึงตกหล่นพื้นที่ใต้ของ polygon ที่ระบบใช้

เปลี่ยนให้ live feed, historical import และคำขอ asset ของ GISTDA ใช้กรอบที่คำนวณจากไฟล์จริงและปัดออกด้านนอก: `98.0086,17.2732,99.5730,20.1474` ทดสอบว่าครอบคลุม vertices ทั้ง 14,869 จุดแล้ว นี่เป็นการตรวจเทียบกับขอบเขตในโปรเจกต์ ไม่ใช่การสำรวจหรือรับรองแนวเขตภาคสนาม

เก็บ bbox ของคำขอแต่ละรอบไว้ และไม่นับกรอบเดิมว่าครอบคลุมขอบเขตปัจจุบัน ระหว่างปล่อยรุ่นมี worker เก่าสองชุดใช้กรอบเดิม จึงนำสองชุดนั้นกลับเข้าคิว เพิ่มการปฏิเสธ geographic scope ที่ไม่ตรง และแก้ run identity ให้การนำเข้าซ้ำเก็บรอบใหม่ได้แม้รีเซ็ตตัวนับ retry ประวัติและ payload เดิมยังอยู่

## ข้อมูลจริงที่ตรวจ

| รายการ | ผลที่ตรวจรอบนี้ |
|---|---:|
| งานนำเข้า 180 วันครั้งแรก | 186/186 tasks; รับ 15,511 รายการ; failed 0 |
| ERA5 ที่ขาดในการนำเข้าครั้งแรก | 113 ชั่วโมง; เก็บเป็น partial |
| งานซ่อมพื้นที่ของ NASA | 112/112 tasks; completed; failed 0 |
| จุดตรวจพบในหน้าต่าง 180 วันหลังซ่อม | 5,846 unique observations |
| ยอดก่อนซ่อมกรอบพื้นที่ | 5,831; หลังซ่อมเพิ่ม 15 จุด |
| วันปฏิทินเต็มที่คำขอครบ | 179/179; อีก 2 วันเป็นส่วนของช่วงต้น/ท้าย |
| ทะเบียนขอบเขตป่าชุมชน | 677 ระเบียน |

จำนวนรับในคิวไม่ใช่จำนวนแถวใหม่หรือจำนวนเหตุไฟจริง เพราะอาจได้รับ observation เดิมซ้ำจากการนำเข้าอีกครั้ง ยอด unique ข้างต้นเป็น snapshot ของช่วงเวลาที่ตรวจ ไม่ใช่ค่าคงที่ตลอดไป

ข้อมูล NASA เป็นจุดตรวจพบความร้อน ส่วน PM และอากาศต้องใช้แหล่งแยกกัน API ของ FIRMS จำกัดแต่ละช่วงคำขอไว้สูงสุด 5 วัน จึงแบ่งงานตามช่วงที่ต้นทางเปิดให้ดึง [NASA FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/)

PM ที่นำเข้าเป็น CAMS global ณ กริดอ้างอิงเมืองเชียงใหม่ แยกจากค่าตรวจวัด ไม่มีสถานี PM measured ที่ใช้ได้ในชุดประวัติที่ตรวจ ข้อมูลแบบจำลองไม่ใช่เซนเซอร์ในป่าชุมชน [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)

ERA5 เป็น reanalysis โดยต้นทางระบุการอัปเดตล่าช้าประมาณ 5 วัน ระบบตรวจทั้งค่าที่เป็น null และ timestamp ที่หายไป แล้วเก็บช่องว่างตามจริง [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

## งานอัตโนมัติและสิทธิ์

- ติดตั้ง cron `chiangmaieyes-archive-worker` หมายเลข 2 ทุกหนึ่งนาที เพื่อเรียก worker URL ตายตัว งานจะทำเฉพาะ task ที่อยู่ในฐานข้อมูล ไม่รับ URL จากผู้ใช้
- เมื่อคิวเดิมหมด สร้างงาน recent FIRMS ต่อชั่วโมง และงาน model/recent archive ต่อวัน ด้วย request key ที่ป้องกันการสร้างซ้ำ
- ตรวจจาก SQL จริง: active=true, cron=succeeded, worker HTTP=200 และมีผล processed เมื่อ 2026-10-12 09:41 UTC โดยไม่มีคำสั่งจากหน้าเว็บที่เรียก worker ในช่วงนั้น
- anon เรียก claim หรืออ่าน heads โดยตรงไม่ได้ authenticated เรียก private job-status function โดยตรงไม่ได้ API jobs ต้องตรวจ session และสิทธิ์ admin
- ตรวจหน้าสถานะคิวบนเว็บจริงด้วยบัญชีเดิมที่มีสิทธิ์ admin ได้ และ staged API ที่ไม่ส่ง Authorization ตอบ 401; unit test ของสมาชิกที่ไม่ใช่ admin ตอบ 403
- มี snapshots ของข้อมูลดิบและ heads ในการตรวจ SQL: 24,047 raw rows / 16,903 latest keys ก่อนการซ่อมภูมิศาสตร์เสร็จ ตัวเลขนี้เปลี่ยนตามงานจัดเก็บอัตโนมัติและไม่ใช่จำนวน hotspot

## การทดสอบและความเร็ว

- Backend 181 tests ผ่าน; frontend/SQL 95 tests ผ่าน รวม 276 กรณี TypeScript และ production build ผ่าน
- ครอบคลุม native identity/revisions, replay, ขอบเขตที่เปลี่ยน, measured/model PM, missing timestamps, task retry/lease, worker รุ่นเก่า, run identity หลัง retry, สิทธิ์ และคำขอเปลี่ยนช่วงเวลาที่ตอบกลับไม่เรียงกัน
- ตรวจบนเว็บจริง: ตารางย้อนหลัง 7 วัน, analytics 180 วัน, PM model selector และ private job progress; console ของการตรวจล่าสุดไม่มี error/warning
- ตรวจ local Light/Dark และ viewport แคบ ตัวกรองไม่ซ้อนกัน รีเซ็ต viewport แล้ว การตั้ง viewport 390 px ใน runtime นี้ให้ layout width 415 px จึงไม่อ้างว่าตรวจ CSS width 390 px โดยตรง
- API history 180 วันหลังซ่อมตอบ 200 และใช้เวลาประมาณ 1.3–2.5 วินาทีในการ probe ที่ตรวจ; archive 7 วันประมาณ 0.6 วินาที ไม่ใช่ผลทดสอบโหลดพร้อมกันจำนวนมาก
- ลดตารางย้อนหลังให้ขอเพียง 1 raw row เพราะหน้าใช้ aggregate ไม่ต้องโหลด 1,000 payloads ทุกครั้ง
- materialize การตรวจ coverage เพื่อไม่คำนวณซ้ำตามทุก observation หลังนำเข้าข้อมูลครบ [PostgreSQL CTE documentation](https://www.postgresql.org/docs/current/queries-with.html)
- MapLibre ยังมี chunk มากกว่า 500 kB แม้โหลดแยกเมื่อเปิด 3D อยู่แล้ว ต้องวัด UX/performance ในงานชุดต่อไป

## การปล่อยและแหล่งโค้ด

| ส่วน | Deployment ที่ปล่อย |
|---|---|
| Frontend | `dpl_HnngsKgKYBpHdSrpWoXHCxhvsgEG` / `frontend-24hld1v9u-peerayoot425-6995s-projects.vercel.app` |
| Backend หลังแก้ geographic scope | `dpl_BsGR8trCSBzeR7gzGoztdaTqPZNt` / `backend-66zfy9nqk-peerayoot425-6995s-projects.vercel.app` |

Frontend SHA256 ที่เสิร์ฟจาก staged deployment ตรงกับ local build: `61e265877c90567645317f5912604dde57152b6ec7a7bfdf6ff774bc32f5b106` และตรวจหน้าเว็บจริงหลัง promote แล้ว Backend runtime เป็น sin1

Source เป็น working tree บน HEAD `41b9319062b600b3b8ea9b9a023146273d7346f3` รวมการแก้ไขที่ยังไม่ commit ติดตั้ง SQL ผ่าน SQL Editor ไม่ได้อ้างว่าลงทะเบียนเวอร์ชันใน Supabase CLI migration history

ไฟล์หลักของรอบนี้:

- `backend/app/archive_jobs.py`, `archive_history.py`, `archive_geography.py`, `environment_archive.py`
- `backend/app/services.py`, `models.py`, `main.py`, `providers/hotspot_provider.py`, `providers/verified_history.py`
- `frontend/index.html`
- migrations `20261012120000_archive_jobs_and_analytics.sql`, `20261012123000_archive_spatial_summary.sql`, `20261012140000_firms_geographic_scope.sql`
- operations `20261012_schedule_archive_worker.sql`, `20261012_verify_archive_worker.sql`, `20261012_scope_worker_compatibility.sql`

## งานที่ต้องทำต่อ

1. ชุด UX: ปรับความหนาแน่นของกราฟและคำอธิบายเก่า ตรวจ keyboard/focus, mobile ที่ CSS width 390 จริง และรายงานให้สอดคล้องกับข้อมูลย้อนหลังที่เลือก
2. ตรวจ workflow หลายบัญชี สมาชิก/ตัวแทน/ผู้ดูแล รูปส่วนตัว อีเมล และที่มาของกล้องต่อ หลักฐานรอบนี้ยังไม่ครอบคลุมการใช้ทุกบทบาทด้วยผู้ทดลองจริง
3. ตรวจสมมติฐานและค่าคงที่ในส่วนทดลอง โดยเฉพาะ `_localized_predictions` และคะแนน/ข้อความเกี่ยวกับเชื้อเพลิงหรือความเสี่ยง ห้ามถือข้อความ hardcoded ว่าเป็นหลักฐานภาคสนาม เพิ่มแหล่ง GFS/PBL/ventilation เมื่อตรวจผลิตภัณฑ์และหน่วยแล้ว
4. เก็บผลประเมินอิสระและทดลองกับชุมชนจริงก่อนรับรอง accuracy โดเมนผู้ส่ง/SMTP สำหรับสมาชิกทั่วไปยังต้องตั้งค่าด้วยโดเมนที่เจ้าของควบคุม

Browser เคยปฏิเสธการอัปโหลด/ดาวน์โหลดจากเว็บนี้ด้วยสิทธิ์ไฟล์ รอบนี้จึงไม่ได้ทดสอบส่งออกไฟล์หรือแนบรูปเพิ่มผ่าน Browser และไม่ได้สั่งส่งอีเมลทดสอบเพิ่ม รายการเหล่านี้ยังต้องมีผลตรวจแยกก่อนถือว่าจบ

หลักฐาน JSON และภาพอยู่ที่ `C:/Users/User/.codex/visualizations/2026/10/06/01a10fbb-e315-7c21-8852-fdaa133d0551/release2/`
