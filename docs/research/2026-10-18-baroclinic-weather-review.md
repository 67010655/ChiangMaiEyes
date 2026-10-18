# BaroClinic Weather: ตรวจแหล่งจริงและความเหมาะสมกับ ChiangMaiEyes

ตรวจเมื่อ 18 ตุลาคม 2026 เวลา 00:50 น. ICT โดยประมาณ (17 ตุลาคม 17:50 UTC) แบบอ่านอย่างเดียว ไม่มีสมัครบริการ ติดต่อเจ้าของ หรือแก้ production

## ข้อสรุป

นำแนวทางแสดงข้อมูลมาใช้ได้ดี: เลือกรอบโมเดล เลื่อนเวลาพยากรณ์ เลือกระดับความกดอากาศ และสลับแผนที่/ลูกโลก แต่ยังไม่มีหลักฐานว่าตัวเว็บทำแบบจำลองอากาศใหม่ หรือทำให้ทำนายไฟแม่นกว่าเดิม การเชื่อมข้อมูลลมหลายระดับเพื่อศึกษาควันมีประโยชน์เชิงวิทยาศาสตร์มากกว่าการย้ายไปใช้ภาพลูกโลกอย่างเดียว

ควรดึงข้อมูลตัวเลขจากผู้ให้บริการต้นทางที่มีเอกสารและสิทธิใช้งานชัดเจน มากกว่านำ binary สำหรับแสดงสีของเว็บนี้ไปใช้เป็นอินพุตโมเดลไฟ ไม่พบเอกสาร API สาธารณะ ข้อตกลงให้บริการ หรือ license ของโค้ด/ข้อมูลแปรรูปจากลิงก์หน้าเว็บและไฟล์ที่หน้าเว็บอ้างอิง การดาวน์โหลดไฟล์ได้ไม่เท่ากับได้รับสิทธิ์คัดลอกโค้ด

## สิ่งที่ตรวจสอบได้จากเว็บจริง

เปิด [หน้าเว็บ](https://baroclinic-weather.pages.dev/) ในเบราว์เซอร์สำเร็จ เข้าหน้า Models เลือก 925mb Wind & Height และ 3D Globe ได้จริง และเห็นชั้นสีความเร็วลมกับเส้นระดับความสูงหลังโหลดเสร็จ ระดับซูมใกล้ทำให้มุมมองลูกโลกดูคล้ายแผนที่ราบ ไม่ควรใช้ภาพที่ซูมใกล้เป็นหลักฐานว่าลูกโลกเสีย

| รายการ | สิ่งที่พบ |
|---|---|
| เครื่องมือแผนที่ | HTML โหลด MapLibre GL JS `^5.0.0`; Three.js r128 ใช้กับส่วน polar/volumetric |
| โมเดลใน config | ECMWF ตัวเดียว; หมวด ensemble/hurricane/mesoscale/climate มีโครง UI แต่ยังไม่มีโมเดลใน config |
| ตัวแปรที่พร้อมใน config | 2m Temperature, Total Accum. Precip, Total Snowfall 10:1, Precip Type/Rate, Precipitable Water, 500mb Height & Vort, 500mb Height Anomaly, Wind & Height ที่ 250/300/500/700/850/925 mb |
| ตัวแปรที่ไม่พบใน supported_params | ลม 10 เมตร, RH 2 เมตร, PBL/mixing height, PM2.5, active-fire prediction, การปล่อยควัน |
| รูปแบบมุมมอง | 2D Mercator, 3D globe, north polar; timeline และเลือก model run; ปุ่ม GIF มีอยู่แต่ไม่ได้ทดสอบ export |
| Satellite / Tropics | หน้าหลักระบุ COMING SOON |
| Radar | โค้ด UI ระบุ NEXRAD Composite/IEM และเรดาร์สถานีสหรัฐ มี 3D storm-volume UI; ไม่มีหลักฐานรองรับเรดาร์ไทยจากการตรวจครั้งนี้ ไม่ได้ทดสอบเรดาร์ครบทุกสถานี |

หลักฐาน: [HTML](https://baroclinic-weather.pages.dev/), [models.json](https://baroclinic-weather.pages.dev/config/models.json), [app.js](https://baroclinic-weather.pages.dev/js/app.js), [radarUI.js](https://baroclinic-weather.pages.dev/js/components/radarUI.js).

## รุ่นข้อมูล เวลา และความละเอียด: มีจุดที่ต้องแยกให้ชัด

ภาพผู้ใช้บอก Run 12Z Mon, Oct 12 เป็นข้อมูลในภาพ ณ ตอนนั้น ไม่ใช่หลักฐานว่าบริการค้างอยู่วันที่ 12 ณ วันที่ตรวจจริง UI/manifest เปลี่ยนเป็น **06Z Sat, Oct 17** แล้ว

[manifest w925 ที่เปิดได้จริง](https://baroclinic-data-proxy.andrew-n-orsini.workers.dev/ecmwf_w925_manifest.json) ระบุ:

- `init_time = 2026-10-17T06:00:00Z` (17 ต.ค. 13:00 ICT)
- `generated_at = 2026-10-17T15:16:27.146907+00:00Z` (รูปแบบเวลามีทั้ง +00:00 และ Z; ไม่ควรคัดลอก parser โดยไม่แก้)
- 49 frames, forecast steps **0–144 ชั่วโมง ทุก 3 ชั่วโมง**: valid time ถึง 23 ต.ค. 06:00 UTC
- `frame_width=1440`, `frame_height=721`, ชนิด `volume_chunked`
- ตัวชี้ latest ณ เวลาตรวจเป็นรอบเริ่มประมาณ 12 ชั่วโมงก่อนหน้า และไฟล์สร้างประมาณ 2.5 ชั่วโมงก่อนหน้า ยังไม่ทราบ SLA/ความถี่อัปเดตจริงจากการตรวจเพียงครั้งเดียว

config เขียน resolution **9km** แต่ `cityOverlay.js` map ภาพครอบคลุม longitude 360° และ latitude 180° และ manifest ส่ง 1440×721 จึงเป็น **กริดภาพแสดงผลประมาณ 0.25°** (ราว 26×28 กม. บริเวณเชียงใหม่) สิ่งนี้ไม่ยืนยันว่าข้อมูลโมเดลต้นทางไม่ใช่ 9 กม.; ยืนยันได้เพียงภาพที่ส่งเข้า browser ไม่ได้เก็บทุกเซลล์ของกริดโลก 9 กม. ไม่พบ processing pipeline/GRIB receipt ที่ชี้รุ่นต้นทางและวิธี resample

อีกประเด็น: ตัวเว็บใช้ `Uint8Array` เป็น scalar raster พร้อม piecewise scaling ค่าลมที่แสดงจึงถูก quantize สำหรับภาพ ตัวอย่าง scaling ช่วง 0–50 knots ใช้ byte 0–40 จึงมีช่วงห่างประมาณ 1.25 knots (~0.64 m/s) ก่อน interpolation ไม่ควรแปลงภาพสีนี้กลับเป็นลมตัวเลขเพื่อฝึกโมเดล เมื่อดึง native u/v ได้โดยตรง

[dataLoader.js](https://baroclinic-weather.pages.dev/js/core/dataLoader.js), [stateManager.js](https://baroclinic-weather.pages.dev/js/core/stateManager.js), [cityOverlay.js](https://baroclinic-weather.pages.dev/js/layers/cityOverlay.js) แสดงว่าข้อมูลผ่าน worker ของผู้สร้าง `baroclinic-data-proxy.andrew-n-orsini.workers.dev` ใช้ manifest, gzip binary volumes และ contours ไม่พบ u/v vector contract ใน manifest ที่ตรวจ ชื่อ Wind & Height จึงไม่ควรถูกตีความว่ามี API ส่งเวกเตอร์ลมพร้อมป้อนโมเดลไฟ

## ข้อมูลต้นทางและสิทธิใช้งาน

[ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) อนุญาต CC BY 4.0 พร้อม Terms of Use และ attribution โดยข้อมูลเปิดเข้าถึงฟรีแต่ค่า compute/bandwidth/storage ของเราไม่ฟรีโดยอัตโนมัติ และบริการส่งข้อมูลเฉพาะอาจมีค่าใช้จ่าย

วันที่ตรวจเอกสาร official ยังระบุ subset แจกทั่วไปที่ 0.25°; ECMWF ประกาศ [30 ก.ย. 2026](https://forum.ecmwf.int/t/ecmwf-free-and-open-data-at-9-km-soon-to-come/15366) ว่าคาดย้ายแจก 0.1° ภายในปลาย ต.ค. 2026 จึงต้องตรวจ product/grid ของไฟล์จริงก่อนอ้างว่า free public mirror เป็น 9 กม. แล้ว แม้ข้อมูล full native resolution จะเปิดสิทธิ์แล้ว การแจกผ่านช่องทางต่าง ๆ และ service charge เป็นอีกเรื่อง

ทางเลือกที่เราควบคุม provenance ได้:

1. ECMWF [ecmwf-opendata](https://github.com/ecmwf/ecmwf-opendata) / cloud mirror: เลือก run, parameter, pressure level และ HTTP range ตาม index; ใช้ u/v โดยตรง เก็บ GRIB metadata และ native-grid definition
2. ผู้ให้บริการ point/grid ที่ใช้แล้ว เช่น Open-Meteo: เลือก ECMWF/GFS แบบ explicit และเก็บ init/valid/retrieval time แยกกัน ตรวจสิทธิ์บริการสำหรับรูปแบบใช้งานจริง ไม่อ้างว่าใครเปิด URL ได้ย่อมให้ production ใช้ไม่จำกัด
3. ไม่อาศัย undocumented worker ของเดโมเป็นระบบหลัก เพราะไม่มี SLA/contract/processing provenance ที่ยืนยันได้ และ UI/endpoint เปลี่ยนได้

## ประโยชน์กับไฟและ PM2.5 ในเชียงใหม่

**925 mb = 925 hPa เป็นระดับความดัน ไม่ใช่ความสูงคงที่เหนือพื้นดิน** บรรยากาศมาตรฐานระดับนี้ราว 0.75–0.8 กม. เหนือระดับทะเล แต่ความสูงจริงเปลี่ยนตามอุณหภูมิ/ความกดอากาศ และอาจอยู่ใต้ดินบนภูเขาเชียงใหม่ สูงเหนือทะเลกับสูงเหนือพื้นต้องแยกกัน

สำหรับ ingestion ต้อง mask ค่า pressure level เมื่อ surface pressure ต่ำกว่าระดับนั้น (เช่น `sp/100 < 925` hPa) พร้อมเช็ก geopotential height เทียบ model terrain/DEM เมื่อแปลงเป็นความสูงเหนือพื้น ลมระดับนี้ไม่ใช่ลม 10 เมตร และไม่ใช่ลมระดับเปลวไฟใต้เรือนยอด ห้ามนำไปแทนกันโดยตรง [ECMWF อธิบายลมต่างระดับ](https://www.ecmwf.int/en/forecasts/datasets/wind-and-geopotential-heights-various-pressure-levels), [การ mask ใต้ terrain](https://forum.ecmwf.int/t/atmospheric-variables-below-model-terrain/1225), [ความหมาย geopotential](https://codes.ecmwf.int/grib/param-db/129).

- **ไฟผิวดิน:** ใช้ surface 10m wind + terrain/fuel/canopy adjustment ที่ระบุสมมติฐาน และทดสอบการ downscale; ไม่คาดหวังว่าลม925hPaจะซ่อมปัญหากราฟไฟลามอัตโนมัติ
- **ควันระยะไกล:** ใช้ wind profile ที่ระดับ plume จริง เช่น pressure/model levels พร้อม mixing-height และ plume injection; 925/850/700hPaช่วยดูความต่างทิศกับผิวพื้น แต่ใช้ทุกจุด/ทุกเวลาเป็นระดับขนส่งเดียวไม่ได้
- **ความเข้มข้น PM2.5:** ยังต้อง emissions (เช่น FRP→emission ที่ตรวจสอบได้), dilution/vertical mixing, deposition, wet removal, background PM และค่าตรวจวัด ไม่สามารถเปลี่ยนลูกศรลมเป็นค่าฝุ่นที่แม่นยำโดยไม่มีส่วนเหล่านี้
- Precipitable Water เป็นน้ำไอน้ำรวมในคอลัมน์ ไม่ใช่ RH ใกล้เชื้อเพลิง; แผนที่ฝนต้องแยกสะสมตั้งแต่ run กับรายช่วงและหน่วยอย่างชัดเจน

## ตรวจสิ่งที่ ChiangMaiEyes มีอยู่แล้ว

ตรวจไฟล์ปัจจุบันใน checkout แบบอ่านอย่างเดียว:

- `frontend/index.html:2555` และ `frontend/src/lib/windGrid.ts` มีลม 10 เมตรจาก Open-Meteo **ตัวอย่าง 3×3 = 9 จุด** แล้ว bilinear เป็น 25×25; จุดที่วาดเพิ่มไม่ใช่การวัดหรือโมเดลอากาศใหม่ที่ละเอียดขึ้น URL ยังไม่เลือก `models` explicit ในส่วนนี้
- `backend/app/providers/weather_provider.py:128` fallback current model point ใช้ T2m/RH2m/10mwind/precip ที่เชียงใหม่ มี latest-time check; backend ใช้ TMD AWS ก่อนเมื่อพร้อม
- `backend/app/live_spread.py:124` ระบุ `models=gfs_seamless`, hourly10mwind, horizon2วัน
- `backend/scripts/build_timed_fire_cases.py` ชุดทดลองมี ECMWF single-run surface weather อยู่แล้ว ดังนั้นชื่อ ECMWF ไม่ใช่ความสามารถใหม่ที่เดโมเพิ่มให้เรา
- หลักฐานทดสอบของเรา `output/fire-perimeter-loop-20261017/existing-pm-wind-evidence.json`: GFS 24h speed MAE0.871m/s บน2871คู่ VTCC airport METAR; direction MAE54.114° บน1013คู่ ไม่ใช่คะแนนลมทุกป่าหรือ validation ของ BaroClinic

ปัญหาที่แก้ได้ตรงจุดกว่าเปลี่ยน viewer คือ provenance ของลมในหน้าเว็บให้สัมพันธ์กับ predictor, เพิ่ม actual spatial forecast fields แทนเก้าจุดห่างกัน ~160กม., ตรวจ wind direction ใกล้ภูเขาและแยกช่วงลมสงบซึ่งองศาไม่นิ่ง

## ลำดับบูรณาการที่แนะนำ

| ลำดับ | งาน | หลักฐานว่าคุ้มก่อนนำขึ้นเว็บ |
|---|---|---|
| 1 | ให้แผนที่/โมเดลใช้ weather run เดียวกัน เก็บ model/version/init/valid/ingested/grid/level และ badge stale | Replay เรียกคืน input เดิมได้ ไม่ปะปน current model กับ forecast ต่างรอบ |
| 2 | เพิ่ม surface U/V field จริงและชั้นเลือก 10m/925/850/700hPa พร้อม terrain mask ในห้องทดลอง | เทียบ TMD/METAR กับ GFS/IFS ชุดเวลาเดียวกัน แบ่งสถานี/เดือนและช่วงลมแรง; รายงาน vector RMSE กับ direction MAE |
| 3 | ใช้ 925/850/700 เป็นตัวแปรควัน/vertical shear พร้อม PBL และ plume assumptions | Ablation same held-out cases: surface only vs profile; PM MAE/RMSE และตำแหน่ง plume; ยังไม่ตีเป็น fire-spread accuracy |
| 4 | นำ timeline/run selector/2D–3D มาให้ผู้ใช้เข้าใจลมและดู replay | เปิดบนมือถือได้ เวลา/หน่วย/ความสูงชัด และไม่เพิ่มเมนูที่ยังไม่มีข้อมูลจริง |

ผลที่ยังไม่มี: ไม่ได้วัด skill ของ forecast บน BaroClinic เทียบสถานีเชียงใหม่, ไม่ได้ตรวจทุกเรดาร์/ทุก run, ไม่ได้ตรวจขั้นตอน GRIB→binary ของผู้สร้าง และไม่ได้ยืนยันสิทธิ reuse โค้ดของเดโม การไม่มีหลักฐานเหล่านี้ไม่เท่ากับไม่มีอยู่ แต่ยังใช้เป็นเหตุผลว่าโมเดลเขาเหนือกว่าเราไม่ได้
