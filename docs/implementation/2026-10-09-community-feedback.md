# งานจากข้อเสนอชุมชนและการประชุม 9 ตุลาคม 2026

## ขอบเขตชุดแรก

เริ่มจากข้อมูลที่อ่านแล้วตีความได้ถูกต้อง, ลม, 3D, แหล่งข้อมูล, ช่องทางติดต่อที่อ้างอิงได้ และรายงานเฉพาะพื้นที่ ก่อนระบบบัญชีตัวแทน เหตุการณ์ร่วม และการพยากรณ์ภาคสนาม

Production entry คือ `frontend/index.html` ขอบเขตป่าชุมชนยึด 677 polygon จาก RECOFTC ไม่เพิ่ม point-only records ในยอดรวม

## สิ่งที่ตรวจพบจากโค้ดและเว็บจริง

- 3D เริ่มที่ตัวเมือง zoom 16 และปิด terrain เมื่อ zoom >=12 จึงไม่เห็นภูเขาเมื่อสำรวจใกล้ แก้ให้ terrain เปิดต่อเนื่องและเพิ่มปุ่มดูภูเขา
- ลม particle ใช้ Open-Meteo 9 จุด แต่ลูกศรรายอำเภอใช้ผลอีกชุดจาก backend โดยเปิดพร้อมกัน แก้ให้ particle และลูกศรใช้ field เดียวกันและเปิดสลับกัน
- แหล่งอากาศ backend สลับได้ระหว่าง TMD และ Open-Meteo จึงต้องเปลี่ยนป้ายตาม source จริง ไม่เขียนว่าเป็นสถานีตลอดเวลา
- `fire_spread_physics.py` มี slope/fuel/history ที่กำหนดไว้รายอำเภอและค่า default ไม่ได้อ่าน DEM หรือ EVI ของแต่ละ polygon เข้าสูตร แบบจำลองยังไม่ได้สอบเทียบภาคสนาม
- กรวยบน 2D ใช้สูตรขนาดภาพจาก FRP+ลม ไม่มี time step หรือเชื้อเพลิงจริง เปลี่ยนป้ายเป็นภาพประกอบทิศปลายลม
- การเทียบย้อนหลัง 30 วันเดิมใช้ครึ่งเดือนคูณสอง แก้เป็นไม่มีข้อมูลเทียบเมื่อไม่มีชุดก่อนหน้า
- PM peak trend เดิมเทียบกับจำนวน hotspot และ visibility เดิมอนุมานจาก PM แก้ให้ไม่แสดงเป็นค่าที่วัดจริง
- กราฟ PM hourly จาก Open-Meteo/CAMS เดิมติดชื่อแหล่งสถานี AQICN แก้ชื่อแหล่งและ timezone ของกราฟ
- ไม่มีประวัติที่โหลดได้ต้องแสดงช่องว่าง ไม่ seed กราฟลม/ฝุ่นด้วยค่าตัวอย่างหรือกราฟศูนย์
- รายงานเดิมส่งทั้งจังหวัดและใช้หลายวันเป็นคำว่า “วันนี้” เปลี่ยนเป็นตัวเลือก 24/72 ชั่วโมง, ป่าเดียวจาก polygon จริง, หรือรัศมี 5 กม. จากจุดที่เลือก
- ชุดข้อมูลป่าประมาณ 1.48 MB ในไฟล์ต้นทาง การสร้าง polygon ทั้งหมดแม้ยังปิดชั้นข้อมูลเป็นงานเกินจำเป็น เปลี่ยนให้วาด 2D เมื่อเปิดชั้นป่า และโหลด MapLibre เฉพาะเมื่อเปิด 3D (entry JS ประมาณ 2.15 kB, renderer ประมาณ 1.06 MB ย้ายเป็น lazy chunk ไม่รวม HTML/CSS/tiles)
- พบว่าเลเยอร์เดิมชื่อพื้นที่เผาไหม้กลับวาดสีตาม danger_score รายอำเภอ ไม่ได้ใช้ burned-area polygons จึงเปลี่ยนเป็นคะแนนเฝ้าระวังทดลอง ไม่มีการอ้างสีนี้เป็นพื้นที่เผาไหม้จริง
- PNG เดิมใช้ data URL ซึ่ง Browser ไม่รับไฟล์ในการตรวจรอบนี้ เปลี่ยนเป็น Blob; การ clone animation ทำภาพว่าง จึงหยุด animation และแยก paper ใน cloned document เท่านั้น ดาวน์โหลดไฟล์และเปิดตรวจเนื้อหาแล้ว

## หลักฐานจากแหล่งทางการ

1. [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) ระบุข้อมูลทั่วโลกภายในประมาณ 3 ชั่วโมงหลังดาวเทียมสังเกต นี่ไม่ใช่เวลาอัปเดตต่อเนื่องของไฟในพื้นที่ ต้องแยก detection time และ retrieval time
2. [NOAA GFS บน Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/NOAA_GFS0P25) ระบุ horizon 384 ชั่วโมง (16 วัน), รอบ 6 ชั่วโมง, กริดประมาณ 28 กม. มีลม 10m, ลมใน PBL, PBLH และ ventilation rate ยังไม่เชื่อมเข้าระบบนี้
3. [NOAA NCEI](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast) มีช่องทางข้อมูลย้อนหลัง GFS และข้อมูลบนคลาวด์ อย่าใช้ 30-day archive window เป็น 30-day forecast horizon
4. [NASA EVI](https://science.nasa.gov/earth/earth-observatory/measuring-vegetation-ndvi-evi/) และ [ผลิตภัณฑ์ EVI 8-day](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD09A1G_EVI) เป็นข้อมูลพืชพรรณ การแปลงเป็นมวล/ระดับเชื้อเพลิงแห้งต้องมีวิธีสอบเทียบเพิ่มเติม
5. [US EPA Air Sensor FAQ](https://www.epa.gov/air-sensor-toolbox/frequent-questions-about-air-sensors) ระบุผลของความชื้น/อุณหภูมิและความจำเป็นในการสอบเทียบ ไม่รับรองว่าเซนเซอร์ทุกชนิดให้ผลเทียบเท่าสถานีมาตรฐาน
6. [Mapzen Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) เป็นข้อมูลความสูงบน AWS; [MapLibre terrain API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/) ใช้ raster-dem ผ่าน setTerrain ต้องแสดงอัตราขยายความสูงแยกจากความสูงจริง

ตัวเลข “ขั้นต่ำ 10 MW” ไม่ใช้เป็นกฎทั่วไป: feed ที่ตรวจผ่าน `/api/dashboard` ในรอบนี้มี FRP 1.47–3.87 MW ต้องตรวจ algorithm/product ของแต่ละ sensor ก่อนระบุ detection limit

## ช่องทางติดต่อ

- สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่): **052-081758**
- ต้นทาง: [บัญชีโทรศัพท์กรมป่าไม้](https://forestinfo.forest.go.th/telephone_region.aspx), ตรวจหน้า 2026-10-09
- ใส่เป็นช่องทางสอบถามผู้ประสานงานระดับหน่วยงาน ไม่ใช่ชื่อหัวหน้าหรือหมายเลขตรงของป่าทั้ง 677 แห่ง ไม่จัดให้เป็นผู้สั่งการของทุกเหตุ

## เว็บอ้างอิงที่ตรวจด้วย Browser

| เว็บ | สิ่งที่เห็นและสิ่งที่จะนำมาพิจารณา |
|---|---|
| [Warroom](https://warroom.pro/) | เปิดตั้งค่า พบการแยกลมสถานี/10m/80m/pressure levels และตัวเลือกเวลา นำหลักการแยกระดับมาใช้ แต่ไม่เอาเลเยอร์ทั้งหมดขึ้นหน้าเริ่มต้น |
| [Hazefree](https://hazefree.com/) | แยกหน้าอ่านง่ายกับ map/dashboard; หน้า landing มีวันที่ข้อมูลปี 2025 จึงใช้เป็นตัวอย่าง UX ไม่ใช้ตัวเลขบนหน้านี้เป็นข้อมูลปัจจุบันของเรา |
| [fireDNPX](https://dnp.gistda.or.th/) | แยกดาวเทียม/หน่วยงาน/วันที่และปุ่ม XLSX รายเลเยอร์ มีข้อจำกัดการใช้งานกำกับ |
| [FireD](https://fire-d.com/opendata) | กรองพื้นที่ เวลา ประเภทที่ดิน และชนิดเชื้อเพลิง แยกคำร้องรออนุมัติ/อนุมัติ/รายงานผลเป็นคนละสถานะ เหมาะอ้างอิงออกแบบ workflow |
| [Forest Fuel Wise](https://forestfuelwise.com/map) | เปิดหน้าตั้งเป้าพื้นที่/วิเคราะห์/สถิติได้ ไม่ได้ตรวจ accuracy, training set, API หรือสิทธิ์นำข้อมูลเชื้อเพลิงมาใช้ จึงไม่ถือคำโฆษณาเป็นผล validation |
| [CCDC](https://www.cmuccdc.org/) | เปิดผ่าน Browser ได้ แม้ web research ตอบ 403 มีหน้าฝุ่นรายชั่วโมง/รายวันและภาพกล้อง การเปิดหน้าได้ไม่เท่ากับใบอนุญาตนำภาพไปเผยแพร่ต่อ |

### กล้องที่พบจาก CCDC

ต้นทาง [ภาพถ่าย CCDC](https://www.cmuccdc.org/snapshots), เลือกวันที่ 2026-10-09 และกด Submit ในแต่ละสถานี

| สถานี | หลักฐานล่าสุดที่เห็น | สถานะสำหรับต้นแบบ |
|---|---|---|
| UNISERV Chiangmai university (4439) | Cam008_20261009140502.jpg และภาพรายชั่วโมงก่อนหน้า | พบภาพของวันนี้ ยังไม่ใช่วิดีโอสด |
| Chiang Mai University Mae Hia (6) | ป้ายแสดงวันที่วันนี้ แต่ filename Cam001_20260422130501.jpg | เวลาไม่สอดคล้อง ไม่ใช้เป็นภาพปัจจุบัน |
| RMUTL Doi Saket (20) | ป้ายแสดงวันที่วันนี้ แต่ filename Cam004_20260826040502.jpg | เวลาไม่สอดคล้อง ไม่ใช้เป็นภาพปัจจุบัน |
| RMUTL (106) | Cam005_20261009140501.jpg และภาพรายชั่วโมงก่อนหน้า | พบภาพของวันนี้ ยังไม่ใช่วิดีโอสด |

ยังไม่ฝังภาพหรือดึง feed เข้า production: ต้องตรวจสิทธิ์ reuse, ตำแหน่งกล้อง และเวลาของไฟล์จริง ไม่มีการลอง endpoint กล้องส่วนตัว

## บัญชีงานทั้ง 22 ข้อ

สถานะ “ชุดแรก” หมายถึงแก้หรือวางฐานใน frontend และปล่อยขึ้น production แล้ว ส่วน “ถัดไป” ยังไม่ใช่ฟีเจอร์ที่ใช้งานแล้ว รายละเอียดการตรวจอยู่ด้านล่าง ไม่ถือว่าทั้ง 22 ข้อเสร็จครบ

| ข้อ | สถานะและงานที่ยังเหลือ |
|---|---|
| 1 | ชุดแรกแยกภาพทิศปลายลมออกจากผลจำลอง; ถัดไปทำ DEM/fuel-driven spread และ validation |
| 2 | ชุดแรกลดความสูง top summary และระบุเวลาแยกรายชุด |
| 3 | ชุดแรกเพิ่มเบอร์หน่วยงานพร้อมต้นทางใน popup 2D/3D และรายงาน; ยังไม่มีหัวหน้าป่ารายแห่ง |
| 4 | ถัดไป persistent incident register, quick draft, timeline และสถิติหลายปี |
| 5 | ชุดแรกแยก LIVE connection, เวลาใน feed, เวลา hotspot และสถานี |
| 6 | ชุดแรกเปิด terrain ต่อเนื่องและเพิ่มปุ่มดูภูเขา/สถานะโหลด |
| 7 | ชุดแรกเพิ่ม retrospective/forecast panel ใน analytics; forecast อากาศจริงตาม horizon ที่ API มี ไม่สร้างข้อมูลอนาคต 30 วัน |
| 8 | ถัดไป approved community memberships + backend authorization + Resend + opt-in + outbox/dedup; ยังไม่ส่งอีเมล |
| 9 | พบ public snapshot candidates 4 จุด มีไฟล์วันปัจจุบัน 2 จุด; ยังไม่ยืนยัน live video/reuse |
| 10 | ถัดไปพื้นที่เกิดเหตุ/ผู้ประสาน/ผู้สนับสนุน/การรับเรื่อง ไม่จัดอำนาจจากเส้น polygon อย่างเดียว |
| 11 | ถัดไปคะแนนความพร้อม/คุณภาพข้อมูลที่ยืนยันแล้ว; ไม่ให้แต้มจากการเข้าดับไฟเสี่ยง |
| 12 | ยังไม่เปลี่ยน phase page เป็น persistent coordination workflow; รักษาฟังก์ชันเดิมพร้อมป้าย experimental |
| 13 | ชุดแรกมี source cards + links + limitations; โลโก้ทางการยังต้องตรวจ asset และสิทธิ์ใช้ |
| 14 | ชุดแรกเลือกพื้นที่/เวลา/องค์ประกอบ พร้อม geographic SVG preview; PNG ดาวน์โหลดและเปิดตรวจแล้ว PDF native print ยังไม่ได้ตรวจไฟล์จริง |
| 15 | ชุดแรกแก้ EVI เป็นความเขียวและไม่เรียก score ว่าปริมาณเชื้อเพลิง; ระดับเชื้อเพลิงต้องสอบเทียบ |
| 16 | ชุดแรกแก้เลเยอร์คะแนนรายอำเภอที่เดิมตั้งชื่อผิดว่า burned area; ยังไม่มีแผนที่ burned-area polygons ที่ยืนยันและ correction workflow |
| 17 | ชุดแรก unify model field, แยก source/height/time และไม่เปิดทั้งสองรูปแบบพร้อมกัน |
| 18 | ชุดแรก summary/station popup/source page/report มีเวลา; ถัดไปตรวจทุก legacy forecast/burned-layer surface |
| 19 | ชุดแรกแสดงที่มา เวลา และข้อจำกัดเซนเซอร์ใน popup/คู่มือ |
| 20 | ถัดไป GFS/PBL/ventilation provider + FIRMS historical validation dataset; ยังไม่คำนวณจากค่า default |
| 21 | ชุดแรก defer 2D polygon rendering, coalesce model-wind requests, lazy forecast; ยังไม่มี concurrency load test |
| 22 | ยังไม่ train ML; ต้อง baseline, ground truth, spatial/temporal holdout และ metrics false alarm/missed events |

## Gates ก่อนชุดต่อไป

- Runtime/browser: home → report scope → analytics → 3D → source page, dark/light, desktop/mobile, console
- Unit: polygon holes/MultiPolygon, time windows/future/unknown observation dates, point radius, bearing conversion, escaping
- Production: frontend HTML + helper asset + dashboard/data-status APIs และ count 677
- Phase 3: ตรวจ deployed Supabase schema/policies จริงก่อนทำ memberships; ห้ามให้ผู้สมัครเลือกรับ role เจ้าหน้าที่เอง
- Forecast: เก็บ actual incident perimeter/time/fuel/weather ที่มี provenance ก่อนเลือก model หรือวัด accuracy ไม่ใช้ข้อมูลอนาคตปน training

## ผลตรวจและการปล่อยชุดแรก

- Production: https://chiangmaieyes.vercel.app/ ปล่อย 2026-10-09 จาก deployment `dpl_6qWUvcckmJzQR1eH7gGeXwus1YG3` หลังตรวจ candidate แล้ว
- Unit tests: 46 ผ่าน จาก 12 ไฟล์; Vite build, syntax ของ inline JavaScript และ `git diff --check` ผ่าน
- Browser candidate: desktop 1280×720, mobile 390×844, dark/light, เปลี่ยนเมนู, ลมสองรูปแบบ, analytics ย้อนหลัง/forecast, รายงานและ 3D
- Browser production หลัง promote: reload แล้วตรวจ home, report options และ terrain; ปุ่มดูภูเขาแสดงภูมิประเทศพร้อมที่ ×2.2; console error/warning ไม่พบในรอบตรวจนี้
- Production HTTP 200: `/`, `/decision-support.js`, `/api/dashboard`, `/api/data-status`, `/api/community-forests`; API ป่าชุมชนคืน 677 records
- PNG: ดาวน์โหลดและเปิดไฟล์จริงแล้ว แผนที่และข้อความครบ; PDF native print ยังไม่ได้ตรวจไฟล์จริง
- ยังไม่ได้ทดสอบผู้ใช้พร้อมกันจำนวนมากหรือ accuracy ภาคสนาม; build มีคำเตือนขนาด lazy 3D chunk และ npm audit รายงาน 1 high vulnerability ยังไม่ได้แก้ในชุดนี้

ภาพหลักฐาน:

- `C:/Users/User/.codex/visualizations/2026/10/06/01a10fbb-e315-7c21-8852-fdaa133d0551/chiangmaieyes-production-20261009.jpg`
- `C:/Users/User/.codex/visualizations/2026/10/06/01a10fbb-e315-7c21-8852-fdaa133d0551/chiangmaieyes-terrain-20261009.jpg`
- `C:/Users/User/.codex/visualizations/2026/10/06/01a10fbb-e315-7c21-8852-fdaa133d0551/chiangmaieyes-forest-report-20261009.png`
