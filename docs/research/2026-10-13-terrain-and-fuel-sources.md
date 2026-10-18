# แหล่งความสูงและข้อจำกัดเรื่องเชื้อเพลิงสำหรับ ChiangMaiEyes

ตรวจแหล่งข้อมูลวันที่ **13 ตุลาคม 2026 (ICT)** งานนี้เป็นการตรวจเอกสารและการเข้าถึงไฟล์สาธารณะ ยังไม่ได้คำนวณความชันครบทุกป่า หรือยืนยันความแม่นยำกับพื้นที่จริง

## 1. แหล่งที่ใช้ทำงานต่อได้ทันที

แนะนำ **Copernicus DEM GLO-30 Public บน AWS** เป็นแหล่งเริ่มต้น: เป็น Cloud Optimized GeoTIFF (COG) ซึ่งอ่านบางช่วงของไฟล์ผ่าน HTTP Range ได้ ไม่ต้องมี AWS account/API key ตามทะเบียนผู้เผยแพร่ เป็นข้อมูลเผยแพร่ชุดปี 2021 ของ mirror นี้ ไม่ใช่ภูมิประเทศที่วัดใหม่ทุกวัน และเป็น **DSM** ซึ่งรวมต้นไม้และสิ่งปลูกสร้างด้วย ไม่ใช่ DTM ของพื้นดินเปลือย [AWS Open Data Registry](https://registry.opendata.aws/copernicus-dem/)

**หลักฐานที่ตรวจเอง:** อ่าน TIFF header ผ่าน HTTP Range ของทั้ง 8 tiles `N17–N20 × E098/E099` ได้ HTTP **206** ทุกไฟล์โดยไม่ส่ง credential ตรวจ GeoKey ได้ EPSG:4326, RasterPixelIsPoint=2, Float32, ขนาด 3600×3600 และระยะกริด 1/3600 องศา ทั้งนี้ยังไม่ได้สแกนคุณภาพทุก pixel [ผลการตรวจไฟล์](../../output/terrain-source-probe.json) · [สคริปต์ตรวจ](../../output/terrain-source-probe.py)

ขอบเขตพิกัดที่อ่านจาก `backend/app/data/community-forests-chiangmai.geojson` จำนวน 677 features อยู่ระหว่าง longitude 98.0929454–99.4597061 และ latitude 17.3561857–20.0886658 จึงอยู่ภายในชุด tiles ที่ตรวจข้างต้น การมีไฟล์ครอบคลุมขอบเขตนี้ไม่ได้ยืนยันว่า geometry ทุกป่าถูกต้อง

รูปแบบ URL ที่ตรวจแล้ว:

```text
https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif
tile = Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM
lat = 17,18,19,20 ; lon = 98,99
```

[ตัวอย่าง N18/E098 ที่ตอบจริง](https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N18_00_E098_00_DEM/Copernicus_DSM_COG_10_N18_00_E098_00_DEM.tif)

`COG_10` ในชื่อไฟล์ **ไม่ใช่ 10 เมตร**; spacing ของ GLO-30 คือ 1 arc-second ส่วนผู้เผยแพร่ตัดแถว/คอลัมน์ที่ซ้ำทางใต้/ตะวันออกของต้นฉบับออก และสร้าง overviews แบบ average ควรอ่าน native level เพื่อคำนวณความชัน [คำอธิบาย COG จากผู้เผยแพร่](https://copernicus-dem-30m.s3.amazonaws.com/readme.html)

ความสูงมีหน่วย **เมตร อ้างอิง EGM2008** ส่วนพิกัดแนวนอนเป็นองศา WGS84 ข้อกำหนดความแม่นยำความสูงแบบ absolute <4 m ที่ระดับ 90% ใน handbook เป็นสถิติรวม ไม่ใช่การรับประกันทุกจุดในเชียงใหม่ ค่าติดลบอาจเป็นค่าความสูงจริงและไม่ควรถูกทิ้งโดยอัตโนมัติ [Copernicus Product Handbook หน้า 10, 13](https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf)

## 2. วิธีคำนวณและแสดงความชันอย่างตรงไปตรงมา

**ข้อเสนอวิศวกรรมสำหรับโปรเจกต์:**

1. ทำงาน preprocess ครั้งเดียว อ่าน COG เฉพาะหน้าต่างที่ต้องใช้ พร้อม halo สำหรับอนุพันธ์ และรวมรอยต่อ tiles ก่อนคำนวณ อย่าดาวน์โหลด/คำนวณ raster ใหม่ในทุก API request
2. ใช้ GDAL/rasterio อ่าน geotransform ของ PixelIsPoint อย่าใช้ tiepoint เป็นมุม pixel โดยตรง มิฉะนั้นคลาดครึ่ง pixel [GDAL RFC 33](https://gdal.org/en/stable/development/rfc/rfc33_gtiff_pixelispoint.html)
3. ขอบเขตป่าที่ตรวจอยู่ใน UTM zone 47N; เสนอแปลงพิกัดแนวนอนเป็น **EPSG:32647** และกริด 30 m ด้วย bilinear resampling โดยคงค่าความสูงเมตร EGM2008 อย่าหารความต่างความสูงเป็นเมตรด้วยความต่างพิกัดเป็นองศา [PROJ: หลักการ UTM](https://proj.org/en/stable/operations/projections/utm.html) · [GDAL: หน่วยของ slope](https://gdal.org/en/stable/programs/gdaldem.html)
4. คำนวณ slope ด้วย Horn 3×3 ระบุ algorithm/spacing/CRS ไว้ใน provenance; output เป็น **องศา** โดย `atan(sqrt((dz/dx)^2+(dz/dy)^2))` ถ้าส่ง percent slope ให้ระบุแยก เพราะ 45° =100% และหน่วยสองแบบใช้แทนกันไม่ได้ [GDAL slope](https://gdal.org/en/stable/programs/gdaldem.html)
5. ตัดตาม polygon จริง แสดง median/mean/P90 ความชัน จำนวน valid samples และสัดส่วนพื้นที่ที่มีข้อมูล การใช้ค่าเฉลี่ยแทนทั้งป่าไม่ใช่ความชัน ณ จุดเกิดเหตุ; ป่าขนาดเล็กต้องแสดงจำนวน samples เพื่อให้เห็นข้อจำกัด
6. ในไฟล์ 8 tiles ที่ตรวจไม่พบ GDAL_NODATA tag ห้ามกำหนด `0` หรือ `-32767` เป็น nodata ทุกไฟล์โดยเดาเอง ใช้ dataset mask/nodata ที่ reader อ่านได้ร่วมกับ finite-value checks; 0 m เป็นค่าที่เป็นไปได้ อย่าเติมข้อมูลขาดเป็นศูนย์ ความชันต้องไม่มีค่าถ้า neighborhood ที่ต้องใช้ไม่ครบ ตาม default GDAL จะให้ nodata เมื่อ 3×3 มี nodata; `compute_edges` เป็นการ interpolation จึงควรเลี่ยงหรือระบุว่าใช้ [GDAL nodata behavior](https://gdal.org/en/stable/programs/gdaldem.html)

**ขอบเขตการตีความ:** กริดประมาณ 30 m และ neighborhood 3×3 ไม่เห็นความชันระดับคันนา/ทางเดิน/ร่องเขาเล็ก ทั้งการ resampling และ DSM เรือนยอดอาจเปลี่ยนความชันที่ได้ จึงควรใช้ชื่อ “ความชันจากแบบจำลองพื้นผิวดาวเทียม” พร้อมแหล่งและปีข้อมูล ห้ามเรียก “ความชันพื้นดินที่ตรวจวัดจริง” หรือใช้ค่านี้รับรองเส้นทางปลอดภัย ข้อนี้เป็นข้อสรุปจากชนิดข้อมูลและวิธีอนุพันธ์ข้างต้น

## 3. License และเครดิต

License GLO-30 อนุญาตใช้ ทำซ้ำ แจกจ่าย และดัดแปลงโดยไม่คิดค่าข้อมูล แต่ไม่ใช่การยกให้เป็น public domain ให้คัดลอก **ข้อความเครดิตสำหรับข้อมูลดัดแปลงจาก Article 6(b)** ไปไว้ในหน้าแหล่งข้อมูล/ไฟล์ export และใส่คำอธิบายความรับผิดตาม **Article 6(c)** รวมถึงไม่สื่อว่าโครงการได้รับการรับรองจากผู้ให้ข้อมูล สำหรับผล slope ซึ่งเป็นอนุพันธ์ควรใช้เครดิตแบบดัดแปลง [License COP-DEM-GLO-30-F](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)

บริการ View Service ของ CDSE มีข้อกำหนดลงทะเบียนที่เปลี่ยนเมื่อ 28 กรกฎาคม 2026 จึงไม่ควรถือว่าหน้า CDSE ทุกช่องทางดึง anonymous ได้; URL AWS ข้างต้นตรวจเข้าถึงจริงในรอบนี้แล้ว แยกการเข้าถึงสองบริการให้ชัด [CDSE ประกาศ View Service](https://dataspace.copernicus.eu/news/2026-7-17-copernicus-dem-30m-view-service-license-acceptance)

## 4. EVI ช่วยอะไร และสิ่งที่ยังวัดแทนไม่ได้

NASA อธิบาย MODIS EVI เป็นดัชนีจาก reflectance ที่ช่วยติดตาม **ความเขียวของเรือนยอด** ซึ่งขึ้นกับ leaf area/chlorophyll/canopy structure โดยผลิตภัณฑ์ MOD13 ทั่วไปมีช่วง composite 16 วัน และต้องใช้ QA คัด pixels คุณภาพต่ำ ไม่ใช่ภาพสภาพป่ารายวัน ณ เวลาเหตุ [NASA MODIS Vegetation Index Products](https://modis.gsfc.nasa.gov/data/dataprod/mod13.php)

**ข้อสรุปสำหรับเรา:** EVI เป็นดัชนีไม่มีหน่วย ไม่ใช่ kg/m² ของใบไม้แห้ง/กิ่งไม้ที่พื้น การจะเปลี่ยน EVI เป็น “เชื้อเพลิงต่ำ/กลาง/สูง” ต้องมีนิยามว่าจัดกลุ่มความเขียวหรือมวลเชื้อเพลิง หากหมายถึงมวลเชื้อเพลิงต้องมีข้อมูลวัดภาคสนามและสมการที่ทดสอบในสภาพป่าเชียงใหม่ก่อน ไม่ใช้ threshold EVI ที่ตั้งเองแล้วประกาศว่าเป็นปริมาณเชื้อเพลิง เหตุผลคือข้อมูลที่ EVI สังเกตกับตัวแปร fuel loading/ moisture/bed depth ที่แบบจำลองการลามใช้เป็นคนละปริมาณ [NASA EVI](https://modis.gsfc.nasa.gov/data/dataprod/mod13.php) · [USFS Rothermel inputs](https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr371.pdf)

## 5. ข้อมูลภาคสนามก่อนกล่าวว่าโมเดลลามผ่านการตรวจสอบ

เก็บอย่างน้อย **ชนิดเชื้อเพลิงและการกระจาย**, มวลแห้งต่อพื้นที่ kg/m² แยกใบไม้/หญ้า/กิ่งไม้และ live/dead, ความลึกชั้นเชื้อเพลิง m, ความชื้นเชื้อเพลิง % ของน้ำหนักแห้ง รวมทั้งขนาด/ความแน่นที่จำเป็นต่อ fuel model; ความชื้นเชื้อเพลิง = `(มวลสด−มวลแห้ง)/มวลแห้ง×100` ลมที่ใช้กับ Rothermel เป็น **midflame wind** จึงเอาลม GFS 10 m หรือ PBL มาใส่ตรง ๆ โดยไม่ปรับ/ทดสอบไม่ได้ [USFS Rothermel comprehensive explanation](https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr371.pdf)

FIREMON มีวิธีเก็บกิ่งไม้ด้วย planar intercept แยก size classes พร้อมวัด litter/duff depth และ cover ของพืช ใช้เป็นต้นแบบคู่มือเก็บข้อมูลได้ แต่ไม่ควรยืมค่าความหนาแน่น/น้ำหนักของพืชอเมริกามาใช้กับไทยโดยไม่มีหลักฐาน [USFS FIREMON, Fuel Load](https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164.pdf)

**แผนตรวจของเรา:** จับคู่ input ณ เวลาเดียวกันกับขอบเขต/ตำแหน่งไฟตามเวลาและอัตราการลามที่สังเกต m/min จากเหตุจริงหรือกิจกรรมที่หน่วยงานจัดอยู่แล้ว เก็บเวลา พิกัด เครื่องมือ ผู้บันทึก และข้อจำกัด; แยกเหตุสำหรับปรับสมการออกจากเหตุที่ใช้ทดสอบ รายงาน error และเปรียบเทียบ baseline ไม่ใช้ hotspot เพียงอย่างเดียวเป็น ground truth เส้นขอบไฟต่อเนื่อง และไม่อ้างความแม่นยำจนมีผลทดสอบจริง แนวทางการตรวจและปรับ fire behavior prediction มีเอกสารต้นฉบับของ USFS รองรับ [USFS Field verification procedures](https://research.fs.usda.gov/treesearch/24636)

## ข้อเสนอสำหรับงานชุดนี้

ทำ **terrain summary จากข้อมูลจริง + provenance/coverage** และ **แบบบันทึกเชื้อเพลิงที่มีหน่วย/หลักฐาน** ก่อน ส่วนการคาดการณ์ลามให้แสดงว่าค่าที่ไม่มีข้อมูลจริงยังเป็น scenario assumptions ไม่ควรแทน fuel/slope ด้วยค่าคงที่แล้วให้สีเหมือนผลความเสี่ยงที่ผ่านการตรวจสอบ การมี DEM/EVI จริงทำให้ input บางส่วนดีขึ้น แต่ยังไม่เท่ากับโมเดลลามได้รับการ validation
