# Native numeric weather adapter probe for ChiangMaiEyes

ตรวจจริง 18 ตุลาคม 2026 ใน research environment เท่านั้น ไม่มีการแก้ production/UI หรือ deploy

## ผลที่ทำสำเร็จ

ดึง **ตัวเลขจาก GRIB2 ของ ECMWF IFS Open Data จริง** โดยไล่ลิงก์ directory listing ที่ผู้ให้บริการส่งมา เลือกรอบที่มีอยู่จริง แล้วใช้ index offset/length ดาวน์โหลดเฉพาะ 5 field ด้วย HTTP Range ทุก response เป็น **206** และจำนวน byte ตรง index ไม่ใช้ภาพสีหรือค่าที่อ่านจาก Baroclinic

| รายการ | ค่าที่อ่านจากข้อมูลจริง |
|---|---|
| รอบเริ่มโมเดล | 2026-10-17 18:00 UTC / 18 ต.ค. 01:00 ICT |
| เวลาที่ค่าพยากรณ์มีผล | 2026-10-18 00:00 UTC / 18 ต.ค. 07:00 ICT |
| Lead time | 6 ชั่วโมง |
| ช่วงดาวน์โหลด | ประมาณ 18 ต.ค. 04:58 UTC / 11:58 ICT; เวลาทุกรายการอยู่ใน receipt |
| Grid ดั้งเดิมของไฟล์ที่เผยแพร่ | regular latitude/longitude 0.25° × 0.25°, global 721 × 1440 |
| พื้นที่ที่ตัดออกมา | 98–100°E, 17–20.5°N; 15 × 9 จุด รวม 135 จุด |
| Fields | 10 m u/v wind, 2 m temperature/dewpoint, total precipitation |
| ขนาด GRIB ที่รับมา | 3,494,303 bytes |
| GRIB SHA256 | `975fb0466d736ed44669c7204d5714f2170237a7c064a528cb68576628c9e978` |
| CRS | Geographic latitude/longitude, sphere radius 6,371,229 m ตาม GRIB shapeOfTheEarth=6; ไม่ติด EPSG:4326 โดยไม่บอกความต่างของ datum |

คำว่า “native” ในงานนี้หมายถึงอ่านค่าตัวเลขบน **กริดที่ ECMWF เผยแพร่โดยตรง** ไม่ได้หมายความว่าไฟล์ 0.25° นี้มีความละเอียดเท่ากริดคำนวณ IFS 9 km และไม่ได้ downscale ลมในหุบเขา กริด 0.25° ใกล้เชียงใหม่มีระยะห่างประมาณ 26–28 km ภาพที่ขยายให้ละเอียดไม่เพิ่มรายละเอียดทางอุตุนิยมวิทยา

เอกสารต้นทางระบุ GRIB2/Open Data และ archive หมุนเวียน 12 รอบ ([ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)); official client อธิบายการเลือก parameter/level และ resolution ที่มีให้บริการ ([ecmwf-opendata](https://github.com/ecmwf/ecmwf-opendata)). การ probe นี้ตรึง 0.25° และตรวจ increment จากไฟล์จริง จึงไม่อาศัยคำโฆษณาความละเอียด

## Artifact และ contract สำหรับเชื่อม solver

Script: `backend/scripts/probe_native_weather_grid.py`

Root: `output/fire-engineering-20261018/native-weather/`

- `chiang-mai-surface-grid.npz`: `latitude[15]` เรียงเหนือ→ใต้, `longitude[9]` ตะวันตก→ตะวันออก; arrays `[15,9]` ไม่ใช่ขอบ pixel
- Raw keys: `10u`, `10v` หน่วย m/s (eastward/northward); `2t`, `2d` หน่วย K; `tp` หน่วย m สะสมตั้งแต่ชั่วโมง 0 ถึง 6 ของรอบนี้
- Derived keys: `wind_speed_10m_m_s`, `wind_from_direction_10m_deg`, `temperature_2m_c`, `relative_humidity_2m_pct` โดย RH คำนวณประมาณด้วย Magnus จาก T/dewpoint
- `grid-contract.json`: init/valid/retrieval, CRS, grid, units, SHA256, package versions และข้อจำกัด
- `surface-selected.grib2`, `surface.index`, `download-receipt.json`: เก็บต้นทาง index rows, byte ranges, HTTP headers และ SHA256 ทุกส่วน
- `listing-*.html` และ receipt: หลักฐานการ discover URL จริง ไม่ใช่ลองเดาวันและชื่อไฟล์ซ้ำ ๆ
- `numerical-verification.json`: ผลตรวจค่าตัวเลขและทิศทาง

API ที่เรียกจาก solver ได้:

```python
from probe_native_weather_grid import sample_wind
wind = sample_wind(
    'output/fire-engineering-20261018/native-weather/chiang-mai-surface-grid.npz',
    latitude=[18.7883], longitude=[98.9853],
)
# u10_m_s, v10_m_s, speed_m_s, from_direction_deg
```

เป็น bilinear บน u/v ก่อนแปลง speed/direction ไม่เฉลี่ยมุมลม และปฏิเสธจุดนอกขอบเขตแทน extrapolate ตัวอย่างกลางเชียงใหม่ได้ u=0.34944 m/s, v=−0.54639 m/s, speed=0.64858 m/s, FROM=327.399° สำหรับเวลา valid ข้างต้น ตัวเลขนี้เป็น output โมเดล ไม่ใช่การวัดที่สถานี

## การตรวจที่ผ่าน และขีดจำกัดของตัวอ่าน

1. อ่าน u/v ด้วย ecCodes 2.50.0 จริง; ค่า extracted grid เทียบ ecCodes nearest-node query ตรงกันทั้งสององค์ประกอบ (error=0)
2. GDAL/Rasterio อ่าน metadata grid, units, init/valid ของ u/v ได้ตรงกัน
3. Fixture ลม eastward/northward/westward/southward แปลงเป็น meteorological FROM 270°/180°/90°/0° ถูกต้อง
4. NPZ ทุก array เป็น finite; shape และ grid rectangle ครบ; source hashes ตรวจซ้ำผ่าน

**ไม่ได้อ้างว่ามี independent data decoder สองตัวผ่าน:** Rasterio/GDAL build นี้ไม่มี libaec จึงอ่านค่าที่บีบอัด GRIB template 5.42 ไม่สำเร็จ แม้ header เปิดได้ ข้อความ GDAL ระบุ “Out of memory” ตามหลังเหตุ libaec แต่ไม่ใช่หลักฐานว่า RAM เครื่องหมด ecCodes wheel อ่านได้ครบ จึงใช้ ecCodes เป็นตัวอ่านข้อมูลและบันทึกข้อจำกัดไว้ใน numerical-verification.json

## ข้อมูลย้อนหลัง 2024/2025/2026: ใช้ได้ระดับใด

ทดลอง endpoint **Open-Meteo Single Runs** ที่ `run=YYYY-03-24T00:00` ครบ 2024, 2025, 2026 ปีละ 4 พิกัดรอบเชียงใหม่ ทุกคำขอ HTTP200 ได้ลม/T/RH/rain ครบ 24 ชั่วโมง จุดตัวอย่างส่ง `cell_selection=nearest` และ `elevation=nan,nan,nan,nan` เพื่อปิด temperature elevation downscaling ไม่ตีความค่าที่ได้ว่าเป็นการวัดตรงพิกัดขอ

ตัวอย่าง requested 18.7N,98.9E คืน grid centre **18.664322N,98.92052E**; อีกสามจุดคืน (18.734621,99.10609), (18.87522,98.85827), (18.87522,99.124016) พิกัดไม่ใช่ regular lat/lon raster จึงเก็บ point arrays พร้อม returned coordinates จริง

ไฟล์ `historical-{year}-samples.json`/receipt และ `historical-{year}-point-forcing.npz` เก็บข้อมูลจริง; NPZ shape `[24,4]` = time × returned point มี `valid_time_utc`, `latitude`, `longitude`, `u10_m_s`, `v10_m_s`, T°C, RH%, precipitation_mm ข้อมูลฝนส่วนนี้เป็น hourly amount ของ API ต่างจาก raw GRIB `tp` สะสมทั้งช่วงรอบ

**ข้อจำกัดสำคัญ:** ผู้ให้บริการอธิบาย archive IFS HRES O1280 9 km เริ่ม 14 มี.ค. 2024 และข้อมูลก่อน 12 พ.ค. 2026 เป็น **Cycle49R1 hindcasts** จึงใช้ทดสอบการจำลองย้อนหลังแบบ single initialization ได้ แต่ยังไม่ใช่หลักฐานว่าเป็นไฟล์พยากรณ์ต้นฉบับที่เคยเผยแพร่ในวันนั้นจริง ([Single Runs docs](https://open-meteo.com/en/docs/single-runs-api)). การสุ่มตัวอย่าง API ก็ไม่ใช่การดาวน์โหลด native historical GRIB ตรงจาก ECMWF

ECMWF Open Data endpoint ที่ probe เก็บเพียงรอบล่าสุด จึงไม่ใช้ endpoint นี้ขอ GRIB ม.ค.–เม.ย. 2024/2025/2026 ได้โดยตรง ยังไม่ได้พิสูจน์ว่ามี original-as-issued native 9 km surface archive ครบฤดูแบบไม่ล็อกอิน/ไม่จ่ายเงิน การมี API ย้อนหลังตอบ 200 ไม่ลบข้อจำกัด provenance นี้

## Historical case adapter ที่พร้อมให้ root เรียก

เพิ่ม `fetch_historical_case_grid(meta, folder)` ใน script เดียวกัน โดยใช้ `meta.weather.request` จากกรณีเดิมและพิกัดสี่มุมของ `meta.bounds_utm47` ขนาด 10 km ไม่เลือก run ใหม่ ไม่รวมค่าจากคนละรอบ API คืน actual model-grid centres และ deduplicate พิกัดซ้ำให้แล้ว ถ้าทั้งสี่มุมตกกริดเดียวกันจะระบุ `all_corners_same_grid_point=true` ชัดเจน

```python
from probe_native_weather_grid import fetch_historical_case_grid
meta['weather_source_path'] = str(original_case_folder / 'single-run-weather.json')
forcing = fetch_historical_case_grid(meta, new_research_case_folder / 'weather-grid')
# numpy arrays time x UNIQUE returned point, plus forcing['receipt']
```

คืน `latitude`, `longitude`, `valid_time_utc`, `u10_m_s`, `v10_m_s`, `temperature_2m_c`, `relative_humidity_2m_pct`, `precipitation_mm`, `valid_forcing_mask` และ receipt บันทึก `corner-weather.json`, `corner-weather.npz`, receipt/contract ไว้ใน folder ที่ส่งเข้ามา หาก cache มี signature และ SHA ตรงจะไม่ยิง request ซ้ำ

ตรวจ run availability ก่อนเวลา initial image; ตรวจ valid times **เท่ากับ single-run-weather เดิมทุกชั่วโมง**; ตรวจ units; ตรวจ forcing ไม่ขาดภายในช่วงกรณีจริง Null ฝนที่ชั่วโมงเริ่มรอบเป็นช่วงสะสมก่อน initialization จึงยังคง NaN ไว้เช่นเดียวกับ null หลังจบ forecast horizon ไม่แทนด้วยศูนย์ ไม่ลากค่าท้ายไปต่อ ต้องใช้ `valid_forcing_mask` และจำกัดเวลาที่มีข้อมูล

ทดสอบเพียง **หนึ่งกรณี 2025-03-24** โดยเก็บผลที่ `native-weather/case-probe-2025-03-24/` ไม่แก้ original case: มี 4 unique returned points, valid times 216 ชั่วโมงตรงต้นฉบับ, 144 ชั่วโมงที่ทุกตัวแปรครบ (แยก null init-rain และ tail) ช่วง initial→final ที่ใช้ทดสอบครบ และโหลด cache ซ้ำให้ array shapes ตรงกัน การเลือก nearest/model elevation อาจให้ T ต่างจาก point forcing เดิมที่ใช้ terrain optimization จึงต้องรายงานการทดลองนี้เป็นการเปลี่ยน **spatial sampling + terrain downscaling convention** ไม่อ้างว่าต่างเฉพาะลมอย่างเดียว

ไม่ได้ fetch ทุกกรณีเอง เพื่อให้ขั้นสร้าง casebank ของ root เป็นผู้กำหนด cohort และตรวจเทียบ baseline บนรายชื่อกรณีเดียวกัน

## สรุปเพื่อใช้ในรอบ engineering

**พร้อมแล้ว:** ตัวรับกริดตัวเลข ECMWF ปัจจุบันพร้อม receipt/units/ทิศทางและฟังก์ชัน sampling; historical single-run multi-point proof ทั้งสามปีพร้อม actual returned grid centres

**ยังไม่ใช่ผลเพิ่มความแม่น:** probe ปัจจุบันมีเพียงหนึ่งเวลา valid และย้อนหลังมีเพียงวันละ 4 จุดตัวอย่าง ยังไม่ใช่ forcing ทุกชั่วโมงครอบคลุมทุกกรณีไฟ ไม่ใช้ค่า valid ปัจจุบันแทนลมย้อนหลัง และไม่แทนลม 10 m ด้วยลม 925 hPa ก่อนนำไปเป็นสมมติฐานปรับโมเดลต้องขยายชั่วโมง/พื้นที่โดยคง run เดียว ตรวจช่วงเวลา availability แล้วเปรียบเทียบบนกรณีเดียวกับ baseline โดยระบุ retrospective-hindcast status ต่อไป

คำสั่งรันซ้ำ:

```powershell
& backend/.venv-research/Scripts/python -X utf8 backend/scripts/probe_native_weather_grid.py
& backend/.venv-research/Scripts/python -X utf8 backend/scripts/probe_native_weather_grid.py --decode-only
& backend/.venv-research/Scripts/python -X utf8 backend/scripts/probe_native_weather_grid.py --historical-probe
```

Dependencies เพิ่มเฉพาะ `backend/.venv-research`: `ecmwf-opendata==0.3.35`, `eccodes==2.50.0` และ dependencies ไม่มีการเปลี่ยน production requirements รายการเวอร์ชันที่ใช้ decode อยู่ใน grid-contract.json
