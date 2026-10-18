# ส่งมอบผลทดลองโมเดลไฟป่า — 18 ตุลาคม 2026

จบรอบวิศวกรรมออฟไลน์สองรอบแล้ว ยังไม่มีการเปลี่ยนเว็บหรือ deploy โมเดลแนวไฟ เพราะผลทดสอบยังไม่เพียงพอ

- **จัดพื้นที่เฝ้าระวัง:** เก็บ `hotspot_wind_pm__large` ซึ่งใช้ hotspot + ลม + PM ไว้ ได้ coverage **36.07%** เมื่อเลือก 250 km² ต่อรอบ สำหรับช่อง 500 m ที่ VIIRS ตรวจพบใน 12 ชั่วโมงถัดไป เทียบ baseline 28.44% การเพิ่ม Himawari ได้ 35.97% บนเวลาออกคำทำนายเดียวกัน 231 รอบ จึงยังไม่เปลี่ยนรุ่น
- **ทายรอยไหม้ใหม่:** ทดลอง 99 ตัวเลือกในสองรอบ ใช้เหตุที่เตรียมได้ 38 เหตุ รุ่นรอบสองเลือกด้วยการเว้นวัน/เหตุปี 2025 แล้วฝึกจาก 19 เหตุปี 2024–2025 ได้ Dice **3.05%** ใน 11 เหตุเดิมปี 2026 และ **4.66%** ใน 8 เหตุเพิ่ม ไม่พร้อมใช้เป็นแนวไฟจริง ผลรอบสองใช้ปี 2026 ซ้ำหลังตรวจรอบแรกแล้ว จึงไม่ใช่ fresh holdout
- **ประโยชน์ต่อชุมชน:** หลักฐานตอนนี้สนับสนุนการจัดลำดับพื้นที่ให้ไปตรวจ มากกว่าทายเส้นไฟลาม การทดสอบแนวไฟในส่วนป่าที่มีภาพยังพลาดเหตุส่วนใหญ่ ห้ามตีความพื้นที่ที่โมเดลไม่ครอบคลุมว่าไม่มีไฟ

คะแนนสองงานมีเป้าหมาย ระยะเวลา และตัวหารต่างกัน จึงเทียบ 36.07% กับ 4.66% หรือคำโฆษณา “แม่น 80%” ตรง ๆ ไม่ได้ และยังไม่ใช่คะแนนรับรองเว็บสด

## ไฟล์หลักที่เก็บใน Git

- [ผลรวมภาษาคน](../../output/fire-engineering-20261018/SUMMARY_TH.md), [ข้อสรุปพร้อมตัวเลข](../../output/fire-engineering-20261018/CONSOLIDATED_DECISION.json), [ภาพสรุป](../../output/fire-engineering-20261018/final-results-overview.png)
- [ทะเบียนโมเดลและ SHA256](../../output/fire-engineering-20261018/MODEL_REGISTRY.json), น้ำหนักและ feature contracts ของทั้งโมเดลเฝ้าระวังและโมเดลแนวไฟทดลอง
- ผล selection/test ของทุกตัวเลือก, กฎแบ่งข้อมูล, เหตุผลคัดออก, reference/input QA และรายงานตรวจสอบสองรอบ
- ชุด replay สองเหตุ ซึ่งมีเฉพาะสถานะเริ่มต้นกับอากาศพยากรณ์ ไม่มีภาพหลังหรือ target label พร้อมคำตอบที่ตรึงไว้เพื่อตรวจซ้ำ
- โค้ดทดลองและ dependency ภายในที่แยกจาก API, raster ภูมิประเทศ/land cover พร้อม metadata และ checksum, reference solver ที่ตรึง commit

## ตรวจชุดส่งมอบจาก checkout ได้โดยไม่ใช้เครือข่าย

ใช้ Python 3.12 และติดตั้ง [เวอร์ชันที่ใช้จริง](../../output/fire-engineering-20261018/requirements-research-lock.txt) ใน virtual environment แยกจาก production จากนั้นรัน:

```powershell
python -X utf8 backend/scripts/verify_fire_engineering_release.py
```

คำสั่งนี้ตรวจ SHA ของโมเดล/selection/โค้ด, ฟิสิกส์ตัวอย่างที่ทราบคำตอบ, ทิศลม, สิ่งกีดขวาง, เวลาเดินทาง และการแยกคะแนนรอยไหม้ใหม่จากรอยเก่า แล้วรันสอง replay ในโฟลเดอร์ชั่วคราว ผลทั้งสี่ array ต้องตรงทุก pixel รวมถึง applicability/unknown ตรวจด้วยว่าไม่มีการ import API ของเว็บ ไม่แก้น้ำหนัก ไม่ฝึกใหม่ และไม่เขียนทับหลักฐานเดิม **การผ่านคำสั่งนี้หมายถึงรันซ้ำได้ ไม่ใช่ความแม่นบนเหตุใหม่**

## ข้อมูลดิบที่เก็บเฉพาะเครื่องนี้

Git เก็บชุดส่งมอบและสอง replay ไม่เก็บคลังภาพ Sentinel-2, Himawari, weather, HII, ESA และ training sample ทั้งหมด คลังดิบยังอยู่ใน `output/` บนเครื่องเดิม ไม่ได้ลบออก [manifest SHA256](../../output/fire-engineering-20261018/frozen-final-inputs.json) ระบุอินพุต 2,700 ไฟล์ที่ตรวจแล้วว่าไม่เปลี่ยน

การรัน benchmark เต็มหรือฝึกใหม่ต้องมีคลังเหล่านั้นและคลังปี 2024–2026 ตาม path ใน manifest ก่อน โค้ดดาวน์โหลดและ receipt ช่วยตรวจที่มา แต่ไม่รับประกันว่าแหล่งต้นทางจะให้ข้อมูลเดิมได้เสมอ รายงาน `verification.json` สองรอบเป็นหลักฐานจาก workspace ที่มีคลังครบ ส่วน `verify_fire_engineering_release.py` ใช้ตรวจเฉพาะสิ่งที่ส่งมอบใน Git ได้จริง

ข้อมูล GIS มาจาก Copernicus DEM และ ESA WorldCover 2021 ตาม URL, วิธี resample และ SHA ใน metadata ไม่ใช่การสำรวจเชื้อเพลิงไทยจริง ข้อมูล optical เป็น spectral-change reference ไม่ใช่ ground truth หน้างาน เวลาได้ภาพเริ่มต้นและ historical IFS ยังมีข้อจำกัดด้าน availability ตามรายงานหลัก

## ที่มาและเงื่อนไขของ reference

PYRETECHNICS developed by Spatial Informatics Group, LLC and contributors. Reference ถูกเก็บแบบไม่แก้ต้นฉบับที่ commit `a811ae508a5d7eeebb808b156e0e2066d4445602` พร้อม `LICENSE` และ `SOURCE.json` ใน `output/reference-tools/pyretechnics/` เป็น source-available ภายใต้ community/commercial terms ของเจ้าของ ไม่เรียกว่า dependency แบบ OSI ที่ใช้ได้ไม่จำกัด ใช้ในงานวิจัยออฟไลน์ครั้งนี้ ไม่มีการติดตั้งเข้าระบบเว็บ WRFx reference เก็บ MIT notice ไว้ในไฟล์ต้นฉบับ

## แนวทางพัฒนาถัดไป

[แผนห้าข้อพร้อมแหล่งข้อมูลและเกณฑ์หยุด](2026-10-18-next-model-improvements.md): แยกไฟ active/รอยเก่า/unknown และเหตุจุดใหม่, เพิ่ม B11/NDMI กับบริบทภาพก่อนทาย, เพิ่มเหตุอิสระและ hard negatives, moisture warm-up เฉพาะพื้นที่ และ calibration/abstention แนวทางเหล่านี้ยังไม่ถูกอ้างว่าเพิ่มความแม่นแล้ว

งานหน้าเว็บ/API/ฐานข้อมูลอื่นที่ค้างอยู่ก่อนรอบทดลองไม่ได้รวมใน commit ส่งมอบนี้

ผลตรวจจากสำเนา index ที่ไม่มีงาน API ค้างหรือคลังดิบ: [commit-snapshot-verification.json](../../output/fire-engineering-20261018/commit-snapshot-verification.json) — PASS ทั้งสอง replay ผลทั้งสี่ array ตรงกันทุก pixel
