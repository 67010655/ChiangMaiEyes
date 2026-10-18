# หลักฐานและทางเลือกทำควัน/PM2.5 ให้ทดสอบใช้งานได้

ตรวจแหล่งปฐมภูมิวันที่ **17 ตุลาคม 2026 (เวลาไทย)** บันทึกนี้เป็นงานวิจัยและข้อเสนอทางวิศวกรรม ยังไม่ได้ติดตั้ง HYSPLIT/BlueSky, ขอสิทธิ์ข้อมูล, ดาวน์โหลด archive เพิ่ม, benchmark เครื่อง หรือยืนยันความแม่นยำในเชียงใหม่

## ข้อเสนอหลัก

**ทำพยากรณ์ PM2.5 ที่สถานีด้วย CAMS + ข้อมูลวัดจริงให้ผ่านการทดสอบก่อน พร้อมพัฒนาควันจากไฟเป็นอีกสายงาน** การพยากรณ์ความเข้มข้นที่คนได้รับกับการระบุว่าควันจากไฟกองใดมาถึงตรงไหนเป็นผลผลิตต่างกัน สายแรกเริ่มได้โดยไม่ต้องรอไฟลามสมบูรณ์ สายหลังต้องมีการปล่อยมลพิษ ความสูงปล่อย และการแพร่กระจาย การเชื่อมลูกศรลมกับวงรีไฟอย่างเดียวให้ PM2.5 หน่วย µg/m³ ไม่ได้ ข้อเสนอนี้อิงโครงสร้าง concentration run ของ NOAA และแนวทาง MOS ของ CAMS แต่เป็นการเลือกขอบเขตของโครงการเรา [S1, S3, S9]

ผลใน `output/hindcast-2026/RESULTS.md` ยังไม่มีสถานีที่ตรวจ QC/เวลาเฉลี่ยแล้วสำหรับให้คะแนน PM2.5 และ CAMS archive ในชุดนั้นยังไม่ใช่ forecast ที่ล็อก issue time/lead ดังนั้นยังใช้ตัวเลขจากการทดลองเดิมรับรองความแม่นยำของระบบนี้ไม่ได้

## 1. HYSPLIT: ใช้ทดสอบควันได้ แต่ต้องเลือกผลผลิตและสิทธิ์ให้ตรง

| ประเด็น | หลักฐานที่ตรวจ | ผลต่อ ChiangMaiEyes |
|---|---|---|
| รันที่ใด | NOAA มี Windows, Mac และ Linux; รัน GUI หรือ script ได้ [S1] | ทดลองบน Windows เดิมได้; งานประจำเสนอ worker ที่เรียก executable แบบ batch แล้วเก็บผล ไม่ต้องฝัง solver ใน browser |
| trajectory กับ concentration | concentration ต้องเพิ่ม emission characteristics, concentration grid/ช่วงเฉลี่ย และ deposition/removal จาก input trajectory [S3] | เส้นทางอากาศ 6–24 ชั่วโมงใช้บอกทิศทางตามเงื่อนไขได้ แต่ยังไม่ใช่ความเข้มข้น PM2.5 |
| มวลที่ปล่อย | HYSPLIT รับ mass/hour; เช่น kg/hour ให้ concentration เป็น kg/m³; EMITIMES เปลี่ยนหลายแหล่ง/เวลาได้ [S3, S4] | ต้องมี PM2.5 emission rate, เวลาเริ่ม–หยุด, พื้นที่/ตำแหน่ง และความสูง ห้ามใช้จำนวน hotspot เป็น kg/hour โดยตรง |
| plume rise | namelist มี Briggs/Sofiev/Freitas เมื่อมี heat/FRP ใน emissions input [S5] | เลือกวิธีและเก็บค่า input/version; ลองความสูงปล่อยหลายแบบเป็น sensitivity ก่อนมีหลักฐานรองรับ uncertainty |
| hindcast | public unregistered version ใช้ dispersion กับ archived met ได้; ห้ามใช้ forecast met เพื่อ dispersion ในรุ่นนี้ [S2] | เริ่มทดสอบเหตุย้อนหลังได้โดยไม่รอ registered forecast edition แต่ต้องปฏิบัติตาม download/use agreement |
| live forecast | non-NOAA users ต้องลงทะเบียนสำหรับ forecast-met dispersion; มีการยืนยัน affiliation รวมถึงนักศึกษา [S2] | จัดเป็น dependency การขอสิทธิ์ผ่านสถาบัน ห้ามสมมติว่ามี API key/registered executable อยู่แล้ว |
| เผยแพร่ | use agreement ห้ามแจกซอฟต์แวร์ต่อโดยไม่อนุญาต; ผล dispersion ที่ใช้ **forecast met จาก NOAA ARL** ต้องได้รับอนุญาตก่อนเผยนอกองค์กร/สาธารณะ; archived-data results ไม่ต้อง permission แต่ electronic redistribution ต้องมี copy/link agreement และ attribution [S6] | แยก experimental hindcast ออกจาก public forecast; ไม่ bundle binary ขึ้น repo/container สาธารณะโดยอัตโนมัติ และไม่ถือว่าเผย live layer ได้ทันที |

NOAA archive มี GDAS 1° ตั้งแต่ ธ.ค. 2004 และ GFS 0.25° ตั้งแต่ มิ.ย. 2019 รวมถึง cloud/HTTPS และ checksum; ส่วน NCEP/NCAR reanalysis ที่หน้านี้ระบุจบ **17 มี.ค. 2026** จึงไม่ควรเลือกชื่อนั้นเป็นทางเดียวสำหรับฤดู ม.ค.–เม.ย. 2026 [S7] รายการ archive บอกว่ามี dataset ไม่ได้รับรองว่าทุกไฟล์ช่วงเป้าหมายครบแล้ว ต้องทำ manifest และตรวจ missing listing/ไฟล์จริงก่อน batch ทั้งฤดู

**ข้อเสนอเชิงวิศวกรรม:** เริ่ม GFS 0.25° archived หรือ GDAS ที่ตรวจไฟล์แล้วเพื่อ smoke hindcast ระดับภูมิภาค; กริดประมาณ 1 km ที่ใช้แสดงผลไม่ได้ทำให้ลม 0.25° มีรายละเอียดหุบเขา 1 km และอากาศสูงหลายระดับ/การผสมแนวดิ่งต้องมาจาก met files ที่เข้ากับ solver ไม่ใช่ดึงแค่ wind 10 m ที่จุดเมือง [อนุมานจาก S3, S7] การพิสูจน์ความคลาดเคลื่อนลมหุบเขาต้องเทียบสถานี/เหตุจริง แล้วค่อยตัดสินใจว่าคุ้มพัฒนา regional met หรือไม่; ไม่เริ่ม WRF-Chem เป็น MVP

## 2. GFAS ใช้เป็น emission inventory ตั้งต้นได้: ต้องใช้เวอร์ชันปี 2026 ให้ถูก

Catalogue ปัจจุบันระบุ **GFAS v1.2 = 1 ม.ค. 2003–31 ธ.ค. 2025** และ **v1.4.2 = 1 ม.ค. 2026–ปัจจุบัน** รุ่นหลังมี hourly estimates และ daily averages ใช้ VIIRS Suomi-NPP ร่วมกับ MODIS Terra/Aqua เท่าที่มี ไม่ใช่เอาคำอธิบาย daily MODIS-only ของ v1.2 มาอธิบายข้อมูล 2026 ทั้งหมด ทั้งสองช่วงเป็นผลิตภัณฑ์กริด **0.1° × 0.1°** มี PM2.5 flux หน่วย **kg m⁻² s⁻¹** และ plume injection-height estimates จาก FRP/อุตุนิยมวิทยา [S8]

**หลักฐานตรวจสดเมื่อเอกสาร cache ขัดกัน:** HTTP GET ไป URL S8 ตอบ 200, response Date `Fri, 16 Oct 2026 17:23:22 GMT` (= 17 ต.ค. 00:23 น. ไทย), body มี version `1.4.2` และ hourly coverage ตั้งแต่ 2026; JSON-LD `temporalCoverage` มีค่า `2003-01-01T00:00:00+00:00Z/2026-10-16T00:00:00+00:00Z` จึงใช้หน้า HTTP สดเป็นหลัก ไม่ใช้ cached snippet ที่ยังบอก v1.2 อย่างเดียว หลักฐาน HTML ของงานหลักเก็บที่ `output/prediction-readiness-20261017/gfas-page.html` ทั้งนี้ยังไม่ใช่หลักฐานว่าดาวน์โหลด data files ทุกชั่วโมงครบแล้ว

**ความต่างที่ต้องรักษา:** emission flux คือมวลที่ไฟปล่อยต่อพื้นที่ต่อเวลา ไม่ใช่ PM2.5 ที่สถานีวัดหน่วย µg/m³ GFAS ไม่ใช่เส้นแนวไฟละเอียด 10–30 m และ plume height เป็น estimate ไม่ใช่ตรวจวัดตรงทุกกอง การใช้ในโครงการเสนอแปลง `flux × พื้นที่ cell (m²) × 3600` เป็น `kg/hour` พร้อมจัด vertical distribution ให้ HYSPLIT และทดสอบผลเปลี่ยนตามการปล่อย/ความสูง; สูตรแปลงหน่วยนี้เป็นข้อเสนอ implementation ไม่ใช่ผลรันที่ยืนยันแล้ว [S3, S8]

GFAS มีผ่าน ADS ซึ่งใช้บัญชี/token และยอมรับเงื่อนไข dataset ก่อนเรียก API [S12] หน้านี้เป็นการตรวจเอกสาร ยังไม่ได้ใช้ credentials ดึง ม.ค.–เม.ย. 2026 มายืนยัน completeness/latency รายชั่วโมง; ใส่ `dataset_version`, `valid_time`, `retrieved_at`, resolution และ hash ใน manifest แล้วค่อยยืนยัน

**ข้อเสนอเชิงวิศวกรรม:** เริ่มแหล่งปล่อยกว้างกว่าจังหวัดเชียงใหม่ตาม transport domain ที่ทดสอบ เพราะฝุ่นที่สถานีรวมแหล่งนอกจังหวัดและแหล่งอื่นด้วย แยกผล `smoke_increment_from_modelled_fires` จาก `total_PM2.5_forecast` และอย่านำ HYSPLIT smoke ทั้งก้อนบวก CAMS total ตรง ๆ: catalogue ระบุ GFAS ถูกใช้ใน CAMS forecast อยู่แล้ว จึงเสี่ยงนับไฟเดิมซ้ำ การทำ total แบบผสมต้องกำหนด background/source replacement อย่างชัดเจนและตรวจแยก [อนุมานจาก S8, S10]

## 3. BlueSky เป็นโครง pipeline ที่ดี แต่ไม่ได้แก้ข้อมูลเชื้อเพลิงไทยให้เอง

USFS ระบุ BlueSky เป็น framework เชื่อม fire information → fuel loading → consumption → emissions → plume profile/dispersion โดยเลือกโมเดลแต่ละช่วงได้ ไม่ใช่ solver เดียว [S11] Source repository มี GPL-3.0 และระบุผลเป็น provisional/research; dependency สำหรับ HYSPLIT ต้องได้ executable จาก NOAA แยก และมีเครื่องมือประกอบตาม module; มีแนวทาง Docker ของเจ้าของโครงการ [S13–S15]

**ข้อเสนอเชิงวิศวกรรม:** ใช้สัญญาข้อมูล/โครง module ของ BlueSky เป็นแบบอย่างก่อน แล้วทดลองส่วน emissions/plume/dispersion ที่ต้องการใน worker แยก version; ไม่ย้าย default fuel map/FCCS หรือ emission factor ของสหรัฐมาเรียกว่าค่าป่าเชียงใหม่โดยไม่มีการตรวจสอบ ระยะแรกที่ยังไม่มี field consumption ใช้ GFAS inventory เป็นสมมติฐานระดับภูมิภาคและเปรียบเทียบกับการประมาณ consumption ที่มี provenance ในเหตุทดลอง ส่วนการเชื่อมไฟลามจริงต้องมี incremental area burned, dry fuel consumed และ emission factors ตามชนิดการเผา ไม่ใช้พื้นที่วงรีทั้งหมดคูณค่าเดียวทุกชั่วโมงซ้ำ

## 4. ทางที่พร้อมทดสอบเร็วกว่า: CAMS + สถานี + bias correction

CAMS global มี forecast วันละสองรอบ ล่วงหน้าถึงห้าวัน ใช้ฟิสิกส์/เคมีและ emissions; เป็นคนละความหมายกับ reanalysis [S10] CAMS มีแนวทาง **MOS** ที่รวม forecast ดิบ อุตุนิยมวิทยา และค่าตรวจวัดล่าสุดเพื่อปรับพยากรณ์ที่สถานี แต่ผลิตภัณฑ์ MOS สำเร็จรูปนี้ครอบคลุม **ยุโรป** จึงใช้เป็นหลักฐานวิธี ไม่ใช่ API พยากรณ์เชียงใหม่ที่พร้อมนำมาใช้ [S9] งานต้นฉบับ Bertrand et al. (2023) ตรวจการแก้ forecast กับสถานีจริงและประเมินทั้ง error และ pollution peaks; ไม่มีเหตุผลให้ยกคะแนนยุโรปมาเป็นความแม่นยำเชียงใหม่ [S16]

**pipeline ที่เสนอสำหรับโครงการ**:

1. เลือกสถานีอ้างอิงที่ metadata ชัดเจนและครอบคลุมเมือง/นอกเมือง เทียบผลแต่ละสถานี; สถานีที่ไม่เคยฝึกต้องทดสอบ hold-out ก่อนแสดงความสามารถนอกจุดวัด
2. เก็บ CAMS **issue time + valid time + lead time** ทุกครั้งพร้อมค่าต้นฉบับ และ observation แยก `observed_at`, `available_at`, station/version, QC/หน่วย/ช่วงเฉลี่ย ห้ามเอาค่าที่เพิ่งแก้ย้อนหลังเข้า forecast รอบก่อน
3. เริ่ม raw CAMS, ค่าล่าสุดคงที่ (persistence), ค่าชั่วโมงเดียวกันวันก่อน และ rolling bias correction แยกตาม lead/station; เทียบแบบจำลองง่ายก่อนเพิ่ม ridge/gradient boosting ตามข้อมูลที่พอจริง
4. predictors ใช้ raw CAMS, lag PM2.5 ที่พร้อมก่อน issue time, forecast wind u/v, RH, อุณหภูมิ, boundary-layer height/ฝนเมื่อ source มี พร้อมระบุ missing strategy ไม่แทน missing ด้วยศูนย์
5. ตรวจ **1/6/12/24/48 ชั่วโมง** แยกกัน และแยก PM2.5 รายชั่วโมงจากค่าเฉลี่ย 24 ชั่วโมง หากแสดง rolling 24 h ที่ target time ต้องสร้างหน้าต่างค่าที่วัดแล้ว + ค่าพยากรณ์อนาคตให้ตรง ไม่ใช้ target observations มาประกอบก่อนเวลา
6. แบ่ง train/validation/test ตามเวลา เช่น train ฤดูเก่าที่มีครบ ปรับค่าเฉพาะ validation แล้วล็อก 2026 เป็น test; ถ้ามีเพียง 2026 ให้ใช้ walk-forward และเว้น hold-out สัปดาห์/เหตุควันช่วงท้ายจริง ห้าม random split hourly rows ที่ทำให้ค่าข้างเคียงรั่วข้ามชุด

ข้อ 1–6 เป็น protocol ที่เสนอ ไม่ใช่ผลว่าโมเดลใดผ่านแล้ว ให้คะแนนบนคู่เวลาชุดเดียวกันและรายงานจำนวนคู่/coverage, MAE/RMSE/bias หน่วย µg/m³, recall/precision ของการเกิน threshold ที่ตกลงก่อน, จำนวน missed peaks และ false alarms; ใช้ `skill = 1 − MAE_model / MAE_baseline` พร้อมช่วง uncertainty แบบ block ตามวัน/เหตุ และรายงานรายสถานี/เดือน/lead แยกวันพีค อย่ารายงาน R² หรือเปอร์เซ็นต์เดียวครอบทั้งจังหวัด

**เกณฑ์พร้อมเปิด pilot ที่เสนอ:** ต้องชนะทั้ง raw CAMS และ persistence ที่ lead ที่จะเปิดใช้งานบน hold-out; หากช่วง uncertainty ยังคร่อม skill=0 ให้บอกว่ายังพิสูจน์ improvement ไม่ชัด; ความครบข้อมูล/latency ต้องผ่านระดับที่ตกลงกับผู้ใช้ และมี stale fallback แสดง issue time หากสถานี/forecast ขาด เกณฑ์ absolute MAE และ missed peak ที่ยอมรับได้ต้องกำหนดจากการใช้งานและ baseline ที่วัดจริงก่อนรับรองระบบ ไม่ตั้งตัวเลขความแม่นยำล่วงหน้า

## 5. สถานี PM2.5 ไทย: พบทางเข้าจริง แต่สิทธิ์/QA เป็นงานที่ต้องปิด

**CMU CCDC มีเอกสาร Open API ที่ตรวจได้จริง** ระบุ register/verification/approval และ Bearer API key; มี endpoint hourly history 30 วัน/1 ปี/5 ปีและ monthly database รวมรายการเดือน ม.ค.–เม.ย. 2026 แต่การเห็นรายการไม่เท่ากับดึงได้ครบ บัญชี general public จำกัด 10 จุดติดตั้ง และการแสดงข้อมูลต้องอ้างที่มา; ตารางสิทธิ์บางส่วนใช้สัญลักษณ์ที่ text extraction ไม่แสดง จึงยังไม่รับรองว่าประเภทบัญชีเราดึงทุก endpoint ได้ ทดลองเปิด monthly link โดยไม่มี session รอบนี้ได้ HTTP 403 และไม่ได้ลอง login ด้วยบัญชีผู้ใช้ [S17] ต้องขอ/ยืนยันสิทธิ์ที่เหมาะสมและทดสอบ station/sample ก่อน bulk; ไม่มีการส่งข้อความขอข้อมูลแทนผู้ใช้ในรอบนี้

CCDC ระบุว่ามาจาก DustBoy และเอกสาร API เน้น outdoor installations [S17] เสนอแยก sensor network นี้จากสถานีอ้างอิงมาตรฐานและเก็บรุ่นเครื่อง/การสอบเทียบ/การย้ายจุด/RH sensitivity เมื่อมีหลักฐาน ไม่ถือว่าทุกจุดเท่ากับ PCD reference monitor โดยอัตโนมัติ

**PCD/Air4Thai:** มี URL history ทางการ แต่การเปิด `https://air4thai.pcd.go.th/webV3/#/History` ผ่านเครื่องมือวิจัยรอบนี้ไม่สำเร็จ ยังไม่ได้ตรวจ bulk download/API SLA/สิทธิ์และข้อมูลรายชั่วโมง ม.ค.–เม.ย. 2026 จึงไม่เขียนว่าใช้ฟรีแบบเสถียรหรือไม่มีข้อมูล ต้องยืนยันการเข้าถึง/ขอ export ที่มี station ID, coordinates, method, averaging period, UTC offset, validation flags แล้วค่อยนำเป็น evaluation reference [S18] ข้อมูลจังหวัดที่ manifest เดิมระบุ GISTDA ยังไม่ใช้แทนสถานีโดยปริยาย

**อัปเดตทุกชั่วโมงไม่ได้แปลว่าเป็น hourly concentration:** ต้องตรวจ metadata ว่าค่า PM2.5 จาก Air4Thai endpoint นั้นเป็น 1-hour, calendar-day หรือ rolling 24-hour mean ที่ update ทุกชั่วโมง เอกสาร CCDC เองแยก endpoint hourly average ออกจาก PM2.5 ที่ใช้คำนวณ TH AQI ซึ่งระบุ average 24 continuous hours [S17] ห้ามใช้ความถี่ timestamp ตัดสิน averaging period แล้วเทียบ CAMS hourly โดยตรง; ต้องกำหนด target/window-end และ aggregate โมเดลให้ตรง reference ก่อน MAE/RMSE มิฉะนั้นผลคะแนนไม่มีความหมาย แม้จำนวนแถวจะครบแล้ว

## 6. งาน worker ที่ควรทำและผลส่งมอบ

ทั้งหมดต่อไปนี้เป็นข้อเสนอ ยังไม่แก้ production:

| ลำดับ | งาน | ผลส่งมอบที่ตรวจได้ |
|---|---|---|
| 1 | ตรวจสิทธิ์/metadata สถานีและคู่เวลาที่ครบ; บันทึก raw CAMS forecast ทุก issue ตั้งแต่ตอนนี้ | station registry, coverage report, immutable forecast/observation manifests; แม้ historical access ยังรอ ก็เริ่ม archive อนาคตได้ |
| 2 | backtest PM2.5 raw/baselines/rolling correction; ใช้ chronological hold-out | ตาราง error ตาม lead/station พร้อมจำนวนคู่และ leakage audit; ไม่อ้าง PM2.5 score หากยังไม่มี reference คู่เวลา |
| 3 | HYSPLIT archive smoke pilot เหตุควันหลายวัน รวมวันลมเปลี่ยน/ข้ามแดน | source term, met/config hash, NetCDF/grid + receptor series, sensitivity, runtime/memory/disk log; benchmark จากเครื่องจริงก่อนเสนอราคา/สเปก |
| 4 | รันประจำบน worker แยกจาก HTTP request: fetch → validate → enqueue → model → QC → publish precomputed artifacts | run ID/status, timeout/retry/idempotency, last successful run; เว็บอ่าน tiles/JSON สถานะพร้อมเวลาข้อมูล ไม่รอ solver จบใน request |
| 5 | shadow forecast แล้วทบทวน missed peaks/false alerts และสิทธิ์เผยแพร่ HYSPLIT | ผลที่ล็อกก่อนเหตุหลายสัปดาห์/หลายสถานการณ์, gate ต่อ lead/พื้นที่ และเกณฑ์เปิด pilot ที่ประกาศก่อนดูผล |

PM2.5 corrected forecast พิสูจน์ความแม่นยำของความเข้มข้นที่สถานีเท่านั้น ไม่พิสูจน์ว่ากองไฟที่ระบุเป็นต้นเหตุ ส่วน HYSPLIT smoke ที่เข้าใกล้สถานีไม่ได้พิสูจน์เส้นไฟลาม ระบบควรเปิดผลเหล่านี้ตามหลักฐานของแต่ละส่วน

## แหล่งปฐมภูมิที่ใช้

- **S1 — NOAA official software page:** https://www.ready.noaa.gov/HYSPLIT.php
- **S2 — NOAA registration / forecast restriction:** https://www.ready.noaa.gov/HYSPLIT_register.php
- **S3 — NOAA concentration setup / units:** https://www.ready.noaa.gov/hysplitusersguide/S310.htm และ https://www.ready.noaa.gov/hysplitusersguide/S312.htm
- **S4 — NOAA EMITIMES:** https://www.ready.noaa.gov/hysplitusersguide/S417.htm
- **S5 — NOAA plume-rise namelist:** https://www.ready.noaa.gov/hysplitusersguide/S410.htm
- **S6 — NOAA Use Agreement:** https://www.ready.noaa.gov/HYSPLIT_agreement.php และ public download https://www.ready.noaa.gov/HYSPLIT_hytrial.php
- **S7 — NOAA met archive catalogue / access / checksum:** https://www.ready.noaa.gov/archives.php
- **S8 — ECMWF/CAMS ADS GFAS catalogue, version/variables/licence:** https://ads.atmosphere.copernicus.eu/datasets/cams-global-fire-emissions-gfas?tab=overview
- **S9 — ECMWF CAMS MOS official method and scope:** https://www.ecmwf.int/en/forecasts/datasets/cams-european-air-quality-forecasts-optimised-observation-sites และ https://confluence.ecmwf.int/spaces/CKB/pages/384140005/CAMS+Regional+European+Air+Quality+Forecast+Optimised+at+Observation+Sites+data+documentation
- **S10 — ECMWF global forecast official description:** https://www.ecmwf.int/en/forecasts/datasets/cams-global-atmospheric-composition-forecasts
- **S11 — USFS BlueSky official product:** https://research.fs.usda.gov/pnw/products/dataandtools/bluesky-framework
- **S12 — ECMWF ADS API setup/terms:** https://ads.atmosphere.copernicus.eu/how-to-api
- **S13 — USFS AirFire source repository/readme/licence:** https://github.com/pnwairfire/bluesky
- **S14 — source-owned BlueSky dependencies:** https://raw.githubusercontent.com/pnwairfire/bluesky/master/docs/dependencies.md
- **S15 — source-owned BlueSky Docker instructions:** https://raw.githubusercontent.com/pnwairfire/bluesky/master/docs/docker.md
- **S16 — peer-reviewed original research:** Bertrand et al. (2023), *Technical note: Improving the European air quality forecast of the Copernicus Atmosphere Monitoring Service using machine learning techniques*, Atmospheric Chemistry and Physics 23, 5317–5333. https://acp.copernicus.org/articles/23/5317/2023/ (DOI https://doi.org/10.5194/acp-23-5317-2023)
- **S17 — CMU CCDC official API documentation / access terms:** https://open-api.cmuccdc.org/?lang=english (เอกสารเปิดได้; sample monthly endpoint ที่ลิงก์พาไป `https://open-api.cmuccdc.org/api/dustboy/database/202412` ตอบ 403 เมื่อไม่มี session)
- **S18 — PCD Air4Thai history URL:** https://air4thai.pcd.go.th/webV3/#/History (รอบนี้เครื่องมือเปิดไม่สำเร็จ; ไม่ใช้ยืนยันว่าดาวน์โหลดครบ/สิทธิ์พร้อม)
