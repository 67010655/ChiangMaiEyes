# ChiangMaiEyes: ภูมิประเทศตามขอบเขตป่าและหยุดค่าการลามที่ไม่มีหลักฐาน

วันที่ 13 ตุลาคม 2026 · ต่อจาก [คลัง GFS](2026-10-13-gfs-archive-release.md)

## ข้อมูลและวิธีทำ

- ดาวน์โหลด Copernicus GLO-30 Public จาก AWS จริง 8 tiles พร้อม SHA-256/ETag เก็บต้นฉบับใน `output/terrain/dem/` ไม่ส่ง raster ขนาดใหญ่เข้า runtime เว็บ
- ใช้ DSM จากชุดเผยแพร่ 2021 ของ mirror นี้ ความสูงหน่วยเมตร EGM2008 รวมต้นไม้และสิ่งปลูกสร้าง ไม่เรียกเป็นการสำรวจพื้นดินเปลือย
- preprocess เป็น EPSG:32647 กริด 30 m ด้วย bilinear แล้วใช้ Horn 3×3 คำนวณ slope เป็นองศา neighborhood ที่มีค่าขาดจะไม่มี slope ไม่กำหนด 0 เป็น nodata โดยเดา
- สรุปค่าตาม polygon RECOFTC โดยใช้ศูนย์กลางพิกเซลภายในพื้นที่ แสดงค่ากลางความสูง/ความชัน จำนวนพิกเซล และรายละเอียดแหล่ง/วิธี/เครดิต
- มี **677 records**: **676 available** และ `cmf-th-3192` เป็น `boundary_needs_review` ไม่คำนวณหรือเติมค่าแทน ไม่มีการแก้ขอบเขตต้นฉบับ
- API `/api/forest-terrain?forest_id=...` อ่าน JSON ที่คำนวณแล้ว ไม่ดาวน์โหลด DEM ต่อคำขอ ตรวจ hash ขอบเขตให้ตรงกับรุ่นที่ใช้คำนวณก่อนแสดง
- หน้า “ข้อมูล” มีตัวเลือกป่าและค่าสรุป ปุ่มในหมุดป่า 2D/3D เปิดรายละเอียดส่วนนี้ได้ พร้อมลิงก์ต้นทางและ license
- รายการป่าที่ชื่อและอำเภอซ้ำกันแสดงรหัสป่าเพิ่ม เพื่อแยก record ตามชุดขอบเขตเดิม ไม่รวม polygon โดยเดา

รายละเอียดและหลักฐานต้นทาง: [บันทึกวิจัย](../research/2026-10-13-terrain-and-fuel-sources.md) · [AWS Registry](https://registry.opendata.aws/copernicus-dem/) · [license](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)

## แก้ตัวเลขที่ไม่มีหลักฐาน

สูตรเดิมใช้ fuel flammability ความชัน และประวัติไฟคงที่รายอำเภอ ไม่ใช่ข้อมูลสำรวจหรือ Rothermel ที่สอบเทียบแล้ว จึงหยุดสร้างอัตรา/ระยะไฟลามและคะแนนหมอกควันรวมจากค่าเหล่านั้น ส่ง `score=null` และแสดง “ยังประเมินไม่ได้” แทนศูนย์/ต่ำ

ข้อมูลดาวเทียม ลม ฝุ่น แบบจำลองอากาศ/CAMS/GFS และดัชนีอากาศแห้งทดลองยังอยู่ แต่ความชันจาก DSM เพียงอย่างเดียวไม่ทำให้แบบจำลองไฟลามผ่าน validation ต้องมีข้อมูลเชื้อเพลิง/ความชื้น/ลมที่ระดับเหมาะสม และการตรวจเทียบผลตามเวลาในพื้นที่

## ผลตรวจ

- Backend **208 ผ่าน**: เพิ่มการตรวจ slope หน่วยเมตรกับระนาบ 45°, neighborhood ขาด, 0 m จริง, geometry quarantine, source hash และ endpoint
- Frontend **110 ผ่าน**: ค่าศูนย์/ข้อมูลขาดต่างกัน, metadata escape, รายการป่าปลอดภัย, response เก่าไม่ทับป่าที่เลือก และ risk null ไม่แสดงเป็นศูนย์/ต่ำ
- TypeScript และ production build ผ่าน มีคำเตือนขนาด MapLibre เดิม

## เวอร์ชันและเว็บจริง

- Backend `dpl_yBJvETtDWLWeKFDDvYQsT8CdMMZY` · `https://backend-cumke7mfb-peerayoot425-6995s-projects.vercel.app` · alias `https://backend-mocha-tau-49.vercel.app`
- Frontend `dpl_69mtcCoKmt6fw74SNfE27sdCJm2M` · `https://frontend-rd8hm00yj-peerayoot425-6995s-projects.vercel.app` · เว็บหลัก `https://chiangmaieyes.vercel.app`
- Staged API: `/health`, terrain ป่าปกติ, terrain ขอบเขตรอตรวจ และ `/api/dashboard` ได้ HTTP 200; dashboard ส่ง `risk.score=null`, `source_mode=UNAVAILABLE` และระบุว่าขาดเชื้อเพลิง/ผลสอบเทียบ
- ตรวจผ่าน proxy เว็บหลัก: 677 records / 676 available / 1 boundary_needs_review; `cmf-th-2522` ได้ median ความสูง 1324.97 m และ slope 22.07° ตรงกับ artifact และผลหน้าเว็บ
- เล่น UI จริง: เลือกป่า โหลดข้อมูล และกรณี `cmf-th-3192` แสดงว่าต้องตรวจขอบเขต ไม่แสดง 0; เปิดผ่านหมุด 2D `cmf-th-2950` ได้ 1024.35 m / 24.34° / 327 pixels และหมุด 3D `cmf-th-3042` ได้ 468.93 m / 17.07° / 226 pixels ตรงรหัสที่เลือก
- ตรวจ Desktop 1280×920 โหมดมืด และ viewport 390×844 โหมดสว่าง การ์ดอยู่ภายใน viewport, document scrollWidth=clientWidth=390; เป็นการจำลอง viewport ไม่ใช่ผลทดลองโทรศัพท์จริง
- ลบ legend สี `SPREAD RISK INDEX` ที่เป็นข้อความคงที่ไม่มีค่าข้อมูลรองรับ และแก้คู่มือ/คำอธิบายสถานการณ์ให้ตรงกับการหยุดค่าระยะลามจากสมมติฐานเดิม
- หลักฐานหน้าจอ: `output/terrain-release/terrain-dark-desktop.png`, `terrain-light-mobile.png`, `terrain-open-from-3d.png`, `terrain-final-live.png`; ผล staged APIs เก็บใน directory เดียวกัน
- ยืนยัน alias frontend รุ่นสุดท้ายเป็น READY ตาม ID ด้านบน; reload เว็บหลักแล้วตัวเลือกมี 677 ป่า + placeholder, ชื่อซ้ำแสดงรหัสจริง และไม่พบ legend เดิม คืน viewport override ก่อนจบการตรวจ
- หลังแก้ข้อความและป้ายรายชื่อป่า ทดสอบ frontend ทั้ง 23 files / 110 cases ผ่านอีกครั้ง; รวมกับ backend 208 เป็น **318 automated cases** ไม่ใช่การรับรองความแม่นยำของข้อมูลในพื้นที่

## อีเมลตามที่ผู้ใช้ยืนยัน

คงการส่งสำหรับตัวแทนที่อนุมัติพื้นที่และเปิดรับแจ้งเตือน ไม่เพิ่มการสมัครข่าวสาธารณะหรือเปลี่ยนสิทธิ์สมาชิกในงานนี้ ยังไม่ได้ซื้อโดเมน เปลี่ยน DNS หรือส่งอีเมลใหม่ ตัวเลือกที่อ่านจาก Registrar API อยู่ใน [บันทึกโดเมนผู้ส่ง](2026-10-13-sender-domain-options.md)

## งานต่อ

ยังไม่มี dataset เชื้อเพลิงภาคสนามที่ใช้รับรองค่าการลาม ต้องเก็บ/ตรวจวัดและจับคู่กับผลไฟตามเวลา พร้อมแยกชุดปรับโมเดลจากชุดทดสอบ การมีผล DSM 676 ป่าไม่ได้เป็นผลความแม่นยำภาคสนามหรือการรับรองเส้นทางปลอดภัย
