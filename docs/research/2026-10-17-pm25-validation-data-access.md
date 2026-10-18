# ข้อมูล PM2.5 อิสระสำหรับตรวจผล Dashboard ที่ดาวน์โหลดได้จริง

ดำเนินการ **17 ตุลาคม 2026 เวลาไทย ประมาณ 00:31–00:36 น.** ได้ข้อมูลสถานี PCD/Air4Thai ม.ค.–เม.ย. **2025 และ 2026** จากไฟล์ public ที่หน้าเว็บทางการเชื่อมไปหา โดยไม่สมัครบัญชี ส่งข้อความ หรือใช้ข้อมูลลับ และไม่แก้ application code ข้อค้นพบนี้แทนข้อจำกัดในบันทึกรอบก่อนที่ยังเปิด history ไม่สำเร็จ: **ตอนนี้มี reference สถานีรายวันให้เทียบแล้ว** แต่ยังต้องรักษาข้อจำกัดช่วงเฉลี่ย/พิกัด/QA

## เส้นทางดาวน์โหลดที่ตรวจจริง

1. เปิด [Air4Thai Web V3 ทางการ](https://air4thai.pcd.go.th/webV3/) ได้ HTTP 200 แล้วอ่าน `js/app.366ea557.js` ตาม script ที่หน้า HTML โหลด
2. Route `/History` โหลด [History JavaScript ทางการ](https://air4thai.pcd.go.th/webV3/js/chunk-2e034b96.4231c507.js) ซึ่งมีลิงก์ดาวน์โหลด PM2.5 รายวันและป้ายเฉลี่ย 24 ชั่วโมง รวมทั้ง endpoint history บน `air4thai.com` จึงมีหลักฐานเชื่อมโดเมน `.net`/`.com` จาก PCD โดยตรง ไม่ได้ใช้ endpoint ที่เดาจากเว็บไซต์ภายนอก
3. ดาวน์โหลด [PM2.5 daily 2026.xlsx](https://air4thai.net/daily_download/PM2.5/2026.xlsx) และ [2025.xlsx](https://air4thai.net/daily_download/PM2.5/2025.xlsx) ได้ HTTP 200 เปิดเป็น XLSX ได้จริง แม้ Content-Type ต้นทางระบุ `text/plain` ทั้งสองมีแท็บ `DATA` และ `รายละเอียดจุดตรวจวัด` ไฟล์ 2026 มีวันที่ 1 ม.ค.–30 มิ.ย.; ไฟล์ 2025 มีข้อมูลปีเต็ม รอบนี้สกัดเฉพาะ 1 ม.ค.–30 เม.ย. ให้ตรงฤดูเป้าหมาย

ต้นฉบับอยู่ใน `output/decision-validation-20261017/pm25/` เป็น `daily-2026.xlsx`/`daily-2025.xlsx` พร้อม URL, retrieval time, byte count และ SHA-256 ใน `history-download-manifest.json`; สำเนา HTML/JS และ `public-js-manifest.json` เก็บเส้นทางหลักฐานไว้ด้วย ไม่ได้รับรองว่า URL/บริการนี้มี SLA หรือไม่มี revision ในอนาคต

## จำนวนข้อมูลที่สกัด ไม่เติมค่าที่หาย

| ปี/สถานี | สถานที่ตาม XLSX | วันที่ในช่วง | ค่า numeric ไม่ติดลบ | ขาด |
|---|---|---:|---:|---|
| 2025 / 35T | ศูนย์ราชการจังหวัดเชียงใหม่ ต.ช้างเผือก อ.เมือง | 120 | 119 | 21 ก.พ. |
| 2025 / 36T | โรงเรียนยุพราชวิทยาลัย ต.ศรีภูมิ อ.เมือง | 120 | 120 | ไม่มี |
| 2026 / 35T | ศูนย์ราชการจังหวัดเชียงใหม่ ต.ช้างเผือก อ.เมือง | 120 | 119 | 12 เม.ย. |
| 2026 / 36T | โรงเรียนยุพราชวิทยาลัย ต.ศรีภูมิ อ.เมือง | 120 | 120 | ไม่มี |

รวม **239/240 station-days ต่อปี** ทั้งสองสถานีอยู่ในอำเภอเมือง จึงไม่ใช้แทนความแม่นยำทั้งจังหวัดหรือทุกป่าชุมชน ไม่มีการสรุปตัวเลขนี้ว่าเป็นผลพยากรณ์หรือ percentage accuracy

ไฟล์ที่พร้อมใช้:

- `chiangmai-air4thai-daily-2025-jan-apr.csv`
- `chiangmai-air4thai-daily-2026-jan-apr.csv`
- `official-daily-extraction-metadata.json`: เก็บชื่อแท็บ header ทั้งแถว, station metadata พร้อมแถว Excel, source footnotes, column index, จำนวนรายเดือน/ค่าที่ขาด และ hash ต้นฉบับ
- `extract_official_daily.py`: script สกัดที่รันได้ด้วย bundled Python/openpyxl แบบ read-only ไม่เขียน workbook กลับ

CSV ทั้งสองปีมี schema เดียวกัน: `date, station_id, pm25_ug_m3, raw_value, source_excel_row, source_excel_column, source, averaging` ค่า missing เป็นช่องว่าง ไม่ใช่ 0 วันที่เป็น date ตามไฟล์โดยไม่มีการแปลง timezone หรือแต่งเวลาสิ้นสุดช่วงเฉลี่ย

**QA และ averaging ที่ทราบจริง:** footnote XLSX ระบุข้อมูลผ่านการตรวจสอบระดับเบื้องต้น และ N/A คือไม่มีข้อมูล; ป้ายดาวน์โหลดทางการระบุค่าเฉลี่ย 24 ชั่วโมง แต่อยู่ในไฟล์เป็น `Date` ไม่มี time/window-end/completeness threshold/method ต่อค่าที่ชัดเจน จึงยังไม่ได้ยืนยันว่า 24 ชั่วโมงนั้นคือ 00:00–24:00 ICT หรือหน้าต่างที่สิ้นสุดเวลาอื่น หากนำ CAMS มาทำ calendar-day mean ต้องบันทึกว่าเป็นสมมติฐานของการเปรียบเทียบ ไม่ยกระดับเป็น verified forecast error

## CAMS ที่ดึงตามตำแหน่งสถานีเพื่อให้ทดลองเปรียบเทียบได้

ดึง Open-Meteo CAMS global archive ตาม [API ผู้ให้บริการ](https://open-meteo.com/en/docs/air-quality-api) ช่วง 1 ม.ค.–30 เม.ย. 2026 ตัวแปร `pm2_5`, timezone `Asia/Bangkok` ได้ **2,880 hourly timestamps ต่อคำขอ**, units µg/m³:

| สถานีที่ร้องขอ | พิกัดที่ส่ง | ไฟล์ |
|---|---|---|
| 35T | 18.840732°N, 98.96978°E | `cams-35t-jan-apr-2026.json` |
| 36T | 18.7909333°N, 98.990000°E | `cams-36t-jan-apr-2026.json` |

พิกัดได้จาก [Air4Thai live station metadata](https://air4thai.pcd.go.th/services/getNewAQI_JSON.php) ที่ดึงรอบนี้ ชื่อสถานที่ตรงกับ XLSX แต่ **XLSX ไม่ให้พิกัดและยังไม่มี historical position log** จึงไม่รับรองว่าพิกัดทุกวันในปีเก่าตรงตำแหน่งปัจจุบัน Metadata ใน [history station list](https://air4thai.com/forweb/getHistoryStation.php) มีชื่อ/พื้นที่ แต่ OpenDate/CloseDate ของสองสถานีเป็น `0000-00-00` ใช้ยืนยันวันเปิด/ย้ายไม่ได้

คำขอ CAMS ทั้งสองตอบกริดเดียวกัน **18.800003°N, 99.0°E** จึงเป็นสอง station comparisons กับ model grid เดียว ไม่ใช่ผลจากสองกริดอิสระ เก็บ request URL, requested/returned coordinates, units และ hash ใน `paired-input-download-manifest.json` ข้อมูล archive นี้ **ไม่ได้ล็อก forecast issue/lead ที่ออกก่อนเหตุ** จึงใช้ประเมิน retrospective dataset agreement ตามสมมติฐานช่วงเฉลี่ยได้ ห้ามเรียกผลว่า genuine lead-24-hour forecasting skill

## Hourly history ในช่วงใกล้ปัจจุบันใช้งานได้จริง

JS History ทางการประกอบ URL ดังนี้:

`https://air4thai.com/forweb/getHistoryData.php?stationID=35t&param=PM25&type=hr&sdate=2026-09-17&edate=2026-10-16&stime=00&etime=23`

คำขอนี้ได้ HTTP 200 / `result=OK` มี **720 timestamps ไม่ซ้ำ, 716 ค่า numeric, 4 ค่า null** ตรง source summary `count=716`, `totalcount=720`, `countPercentage=99.44` JSON อยู่ `history-35t-latest30days.json` และสกัดเป็น `chiangmai-air4thai-35t-hourly-20260917-20261016.csv` ค่าที่ขาดคือ 18 ก.ย. 13:00/14:00, 20 ก.ย. 13:00 และ 16 ต.ค. 16:00 ตาม timestamp ที่ต้นทางให้

ขอ **36t** ด้วย parameters เดียวกันได้ **720/720 ค่า numeric ไม่ซ้ำ ไม่มี null** ตรง source summary 100%; raw อยู่ `history-36t-latest30days.json` และ normalized อยู่ `chiangmai-air4thai-36t-hourly-20260917-20261016.csv` รวมสองสถานี **1,436/1,440 station-hours** ทั้งสอง CSV ใช้ schema `datetime_as_published,station_id,pm25_ug_m3,raw_value,source_type,source` เก็บ provenance และ summary ต้นทางใน `paired-input-download-manifest.json` ชุดนี้เป็นช่วง 17 ก.ย.–16 ต.ค. จึงต้องรายงานผลแยกจากฤดูไฟพีค ม.ค.–เม.ย.

UI เลือก `type=hr`, time options เช่น 00:00–01:00 และระบุหน่วย PM25 เป็น µg/m³ จึงมีหลักฐานว่าเป็น hourly-history interface แยกจาก live AQI/PM2.5 เฉลี่ย 24 ชั่วโมง แต่ยังไม่ได้ยืนยันว่า `DATETIMEDATA` เป็น start/end ของชั่วโมงและรายละเอียด QC/เวลาที่ข้อมูลพร้อมใช้งานจริง ต้องกำหนดก่อน scoring ระดับชั่วโมงอย่างเป็นทางการ ส่วนการขอมีนาคม 2026 ด้วย endpoint เดียวกันตอบ OK แต่ `data=[]`; JS ตั้ง minDate ย้อนหลัง 30 วัน ผลนี้ไม่ใช่หลักฐานว่าต้นทางไม่มีข้อมูลปีเก่า จึงใช้ daily XLSX เป็นช่องทางเปิดที่ยืนยันได้ในฤดูต้นปี

## ทางเลือกอื่นและขอบเขต

- CMU CCDC: [เอกสาร API](https://open-api.cmuccdc.org/?lang=english) เปิดได้ แต่ต้อง register/verify/Bearer key ไม่มีชื่อ key ของ CCDC/DustBoy ที่พบในไฟล์ env ที่ตรวจแบบ presence-only จึงไม่สมัครหรือเรียก protected history โดยไม่มีสิทธิ์ ไม่ได้แสดงค่า secret
- [Chiang Mai government catalogue](https://chiangmai.gdcatalog.go.th/api/3/action/package_show?id=69_18) เปิด metadata ได้ แต่ชุดเดิมอ้าง GISTDA และไม่ให้ station ID/averaging-window ที่พอทำ station validation; เมื่อพบ official PCD station export แล้วให้ใช้ไฟล์สถานีที่อธิบายข้างต้นสำหรับการเทียบนี้
- สามารถใช้ปี 2025 ปรับ correction แล้วล็อกปี 2026 เป็น temporal hold-out เพื่อศึกษาการถ่ายโอนข้ามฤดู โดยรายงานว่า retrospective เพราะข้อมูล/ผลปี 2026 มีให้ดูแล้ว ไม่อ้าง blind prospective test ข้อมูลที่ฝึก/ทดสอบต้องจับคู่ averaging/หน่วย/station และรายงาน count ตามคู่ที่เหลือจริง
- สำหรับ forward forecast ที่วัดผลได้จริง ควรเก็บ immutable raw forecast issue/lead ตั้งแต่ตอนนี้ และจับคู่สถานีเมื่อ observation มาถึงภายหลัง การดึง archive ย้อนหลังพร้อมกันไม่ทดแทนหลักฐานว่า forecast ถูกออกก่อนเหตุ

รอบนี้ได้ข้อมูลจริงและ provenance สำหรับให้งานหลักคำนวณ/ตรวจคู่เวลา ยังไม่ได้ฝึกโมเดลหรืออ้างคะแนน PM2.5 ของ Dashboard ในบันทึกนี้
