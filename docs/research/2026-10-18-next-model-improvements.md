# หาก prediction ยังไม่ดี: รอบทดลองถัดไปที่แก้ปัญหาตรงจุด

> อัปเดตหลังรอบฝึกเพิ่ม: ทำแล้วเฉพาะการเว้นวัน/เหตุในการตรวจและ refit จาก19เหตุเก่า ส่วนการเพิ่ม hard negatives, B11/NDMI, active-state model, local moisture warm-up และ calibration ยังเป็นข้อเสนอ ผลล่าสุดอ่าน SUMMARY_TH.md ใน output/fire-engineering-20261018 เอกสารด้านล่างเก็บ snapshot ก่อนรอบฝึกเพิ่มไว้ตามเดิม


จัดทำ 18 ตุลาคม 2026 — ข้อเสนอการทดลองจากโค้ดและผลที่ตรวจจริง ยัง **ไม่ได้ implement, train, เปลี่ยนตัวเลือกที่ freeze แล้ว หรือปรับข้อมูลทดสอบเพิ่มปี 2026** ไม่มีเงื่อนไขบังคับให้ไปเก็บข้อมูลหน้างานก่อนเริ่มได้ และไม่มีคำรับประกัน 80%

## เหตุที่ต้องเปลี่ยนวิธี มากกว่าเติม feature เดิม

ณ snapshot ที่อ่าน `output/fire-engineering-20261018/models/test-results.json` ตัวที่เลือกด้วยปี 2025 คือ `point_no_pm__0.03`: บน **11 กรณี regression2026 ที่เคยตรวจแล้ว** ทำนายพื้นที่ใหม่ 29.1536 km² เทียบรอยไหม้ใหม่อ้างอิง 4.4100 km² ทับกัน 0.5288 km² จึงได้ Dice 3.151%, precision ต่อพื้นที่ 1.814%, coverage ของรอยไหม้ 11.991% ตัวเลขเหล่านี้ยังไม่รวมกรณี 2026 ชุดเพิ่มที่ root กำลังดึงและยังไม่เปิดคะแนนตอนเขียนโน้ต

ปัญหามีทั้ง **พื้นที่ทำนายเกินมาก** และ **ทำนายผิดตำแหน่ง** ไม่ใช่แค่ปรับ threshold ให้พื้นที่รวมเท่ากันแล้วจะถูก การใช้เพียง 8 กรณีฝึกจาก 4 วัน initial image ก็ไม่ได้กลายเป็นตัวอย่างอิสระหลายล้านตัวเพราะแบ่งภาพเป็น pixel

สิ่งที่รันแล้ว ได้แก่ point vs corner-grid weather, past Himawari distance/count, NDVI/NBR change ระหว่างสองภาพ, season/ESA prior, PM ablation และ physics seasonal-NDVI multiplier การทดลองด้านล่าง **ไม่ใช่เสนอให้รันชุดเดิมซ้ำ**

## 1. แยกไฟเดิมที่ยัง active ออกจากไฟที่ดับ/รอยไหม้เก่า และแยกการลามออกจากจุดเกิดใหม่

**ปัญหาที่แก้:** ปัจจุบัน `all new spectral scar` รวมพื้นที่แยกห่างจากกองไฟตั้งต้นด้วย ขณะที่ graph ลามจาก seed และภาพ initial scar ไม่ได้บอกทุกจุดว่ายังลุกอยู่ สร้างวงลามรอบรอยไหม้เก่าจึงอาจเพิ่มพื้นที่ผิดโดยตรง

**เปลี่ยนโค้ดรอบใหม่:**

- แยก schema ใน `prepare_timed_fire_arrays.py` เป็น initial burned/observed active/unknown และ target `connected_growth`/`detached_new_burn` โดยตรึงกฎก่อนดูคะแนน รายงานเป้าหมายรวมเดิมควบคู่เสมอ ไม่ตัดไฟที่ทำนายยากทิ้งเพื่อเพิ่มคะแนน
- เพิ่ม `event_id` และลำดับสถานะใน `fire_engineering_inputs.initial_features()` แทนการรวม detection 24 ชั่วโมงเป็น distance/count อย่างเดียว เช่น age since most recent **positive**, จำนวนครั้งที่พบต่อช่วงเวลา และ clear-observation coverage ที่มีหลักฐานจริง การไม่พบ hotspot ภายใต้เมฆเป็น unknown ไม่ใช่ fire-out
- ทดลองสองหัว: active-state gated **spread** ใกล้เหตุเดิม และ **new-ignition risk** สำหรับส่วนแยก ไม่ยืนยันว่า disconnected scar ทุกชิ้นเป็น ignition ใหม่ เพราะอาจเป็น spotting หรือไฟที่ดาวเทียมไม่เห็น
- เพิ่ม rolling-update experiment ใน `predict_fire_engineering.py` ที่ออกคำทำนายใหม่หลังรับ observation ตามเวลาจริง โดยข้อมูลที่ใช้ในรอบใหม่ต้องมาถึงก่อน origin ใหม่ รายงาน lead 6/12/24h แยกจาก free-run เดิมที่ไม่มี update ระหว่างทาง

**ข้อมูล/ซอฟต์แวร์:** ใช้ VIIRS/Himawari และภาพเดิมได้; OpenWFM มี implementation การ initialize จาก perimeter และ assimilation เป็นตัวอย่างวิธีตั้งสถานะ ไม่ต้องอ้างว่า graph ของเราเป็น WRF-SFIRE ([official source](https://github.com/openwfm/wrfxpy/blob/master/src/forecast.py)). NASA ย้ำว่าจุด active fire ไม่ใช่พื้นที่ทั้ง pixel ที่ไหม้และเมฆอาจบัง detection ([FIRMS map](https://firms.modaps.eosdis.nasa.gov/map/?os=firetv)).

**วัด/หยุด:** เปรียบเทียบ fixed-origin vs rolling ด้วย horizon และ observation delay เดียวกัน; วัด new-growth Dice/precision/coverage, unmatched predicted km², event-level detection latency และ missed events เมื่อคุม false warnings เท่ากัน หยุด branch ถ้าลดพื้นที่ผิดด้วยการพลาดไฟมากขึ้นอย่างเดียว หรือ gain หายเมื่อคืน detached targets เข้า denominator; ถ้าไม่มี reference ที่เวลา 12h ต้องเรียกการวัดนั้นว่า hotspot detection/coverage ไม่ใช่แนวไฟ 20 m

## 2. เพิ่ม SWIR1 และบริบทภาพหลายเวลา แทน NDVI ตัวเดียวหรือ feature pixel แยกกัน

**ปัญหาที่แก้:** feature ปัจจุบันมี NIR/red/SWIR2 และ local mean 100 m แต่ยังไม่มี SWIR1 สำหรับความเปลี่ยนแปลงด้านน้ำในพืช และโมเดล pixel ไม่ได้เห็นรูปทรง/ความต่อเนื่องของรอยไหม้เต็มพื้นที่

**เปลี่ยนโค้ดรอบใหม่:** `build_timed_fire_cases.py` เพิ่ม asset `swir16` (Sentinel-2 B11) ให้ **collection1 receipt รุ่นใหม่** ไม่เขียนทับ frozen scene cache; `prepare_timed_fire_arrays.py` เพิ่ม initial-only NDMI = (NIR−SWIR1)/(NIR+SWIR1), validity และ age ของแต่ละภาพ ใช้ NIR เฉลี่ยมาที่ **20 m** เพื่อให้ตรง B11 ไม่เรียก NDMI ว่ามีข้อมูลอิสระ 10 m

เริ่ม HGB ablation ที่เพิ่ม NDMI/ΔNDMI และ multi-scale neighbourhood 100/500/1000 m เพียงชุดเล็กก่อน จากนั้นถ้ามี independent events พอ ค่อยเพิ่ม branch temporal patch model (เช่น compact U-Net จาก baseline code แบบเปิด) ในไฟล์ใหม่จาก `timed_fire_growth_dense.features()` รับภาพ past-only อย่างน้อยสามเวลา พร้อม masks/age; เทียบกับ HGB ที่ใช้ bands/time เดียวกัน เพื่อแยกผลข้อมูลออกจากสถาปัตยกรรม

**หลักฐานต้นทาง:** B11/B12 ของ Sentinel-2 เป็น 20 m ([Copernicus SentiWiki](https://sentiwiki.copernicus.eu/web/s2-mission)); สูตร NDMI ใช้ NIR กับ B11 ([provider example](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/ndmi_special/)). NDMI เป็น spectral proxy ไม่ใช่ dead-fuel moisture ที่วัดได้โดยตรง งาน Google ใช้แผนที่หลายตัวแปรและ spatial model ในข้อมูลสหรัฐฯ พร้อม baseline code เปิด เหมาะหยิบโครงสร้างทดลอง ไม่ย้ายคะแนน/น้ำหนักมาอ้างว่าใช้เชียงใหม่ได้ทันที ([paper](https://research.google/pubs/next-day-wildfire-spread-a-machine-learning-dataset-to-predict-wildfire-spreading-from-remote-sensing-data/), [code](https://github.com/google-research/google-research/blob/master/simulation_research/next_day_wildfire_spread/README.md)).

**วัด/หยุด:** ตรึง cohort/threshold-selection เหมือนกัน รายงาน Dice/PR-AUC และ excess area แยกภูมิประเทศ/เดือน ทดสอบไม่อ่านภาพสุดท้ายกับ future QA ใน inference หยุดก่อน deep model ถ้า NDMI+past context ไม่ชนะ HGB บน held-out events หรือข้อมูลเพิ่มทำให้สูญเสียกรณีเพราะ cloud มากจนการเทียบไม่ใช่ชุดเดียวกัน

## 3. เพิ่ม “เหตุอิสระ + วันอิสระ + พื้นที่ไม่เกิดไฟ” และฝึกให้โมเดลรู้จักการไม่เตือน

**ปัญหาที่แก้:** ตัวอย่างปัจจุบันเลือกใกล้ past-hotspot เป็นหลัก จึงไม่แสดงอัตราเหตุจริงบนพื้นที่ป่าที่มีหน้าที่เฝ้าระวังทั้งหมด และ 8 tiles จาก 4 วัน initial อาจให้น้ำหนักสภาพอากาศวันเดียวมากเกินไป พื้นที่ผิด 28.6248 km² จาก 29.1536 km² ที่ทำนาย แสดงว่าควรแก้ false positives โดยตรง

**เปลี่ยนโค้ดรอบใหม่:**

- `build_fire_engineering_bank.proposals()` เพิ่ม protocol จัดกลุ่มเหตุจาก time/space และแบ่งตาม event/date/tile overlap; เพิ่มภาพวันที่ไม่มี past hotspot และ hard negatives เช่นเกษตร/แปลงเปิด/รอยไหม้เก่าที่ภาพยังชัด เลือกด้วยกฎข้อมูลตั้งต้นก่อนดู future label เหมือนกรณีบวก
- `run_fire_engineering_loop.fit_phase()` เพิ่ม event/date balancing และ hard-negative mining **เฉพาะ training folds** ไม่เลือก negative ตามข้อผิดพลาดปี 2026 แล้วกลับมาประกาศ test ใหม่
- เพิ่ม grouped cross-validation ด้วย explicit indices ทั้ง fitting, calibration และ threshold selection ไม่ random split pixels ใน tile เดียวกัน ([GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html)). ตั้งเป้ารอบทรัพยากร 24–40 เหตุอิสระจากหลายวันในปีก่อนหน้าเป็นตัวอย่างแผน ไม่รับประกันว่าจะผ่าน optical/weather QC ครบทุกเหตุ

**วัด/หยุด:** วัด learning curve ตามจำนวน **events** ไม่ใช่ pixel; false warning events ต่อ forest-day และ coverage ณ alert area คงที่ พร้อม bootstrap ตาม event/date ถ้ายังมี valid events น้อยจนช่วงความไม่แน่นอนกว้าง ให้คงสถานะ research ไม่เอาพิกเซลจำนวนมากมาอ้างความมั่นใจ หยุดเพิ่มปี/tiles เมื่อการเพิ่มสอง batch ที่กำหนดไว้ล่วงหน้าไม่ทำให้ held-event error ลดลง แล้วสรุปต้นเหตุ ไม่วนเพิ่มข้อมูลโดยไม่มีเพดาน

**เรื่องปีเก่า:** ภาพเก่าฝึก spectral representation ได้ แต่ weather archive/processing ต้องมี provenance เป็นรายปี หากใช้ reanalysis สำหรับ pretraining ให้แยกผลจาก forecast-conditioned evaluation; อย่านำ reanalysis ที่รู้สภาพอากาศหลัง origin มารับรองพยากรณ์ operational

## 4. ความชื้นเชื้อเพลิงต้องมีประวัติรายกรณี ไม่เริ่ม 8/10/12% ก่อนภาพไม่กี่ชั่วโมง

**สิ่งที่เคยทำแล้ว:** `benchmark_open_fuels.moisture_series()` เคยมี warm-up 168h ที่ **จุดอ้างอิงจังหวัดเดียว** ใน pilot66cases ดังนั้น “ทำ warm-up 7 วัน” เฉย ๆ ไม่ใช่ไอเดียใหม่ สิ่งที่ยังต่างจากรอบ optical growth ปัจจุบันคือการ warm-up **แต่ละกรณีตามพิกัดและเวลาเดียวกับกรณีนั้น**; `timed_fire_spread_benchmark.weather_for()` ยังเริ่ม state .08/.10/.12 ณรอบ IFS แล้ว conditioning เพียงช่วงก่อนภาพประมาณหลายชั่วโมง

**เปลี่ยนโค้ดรอบใหม่:** เพิ่ม past-weather receipt ต่อกรณีใน `fire_engineering_inputs.py`; ก่อน `weather_for()` ให้ evolve state ย้อนหลัง 168h ผ่าน `benchmark_open_fuels.equilibria/advance` แล้วส่ง state ณ init เข้า forecast run เดิม เปรียบเทียบ warm-up 24/72/168h และ initial-moisture sensitivity ที่กำหนดไว้ก่อน ไม่เพิ่ม rain จากหลัง origin เข้า state ตั้งต้น

**ข้อมูลที่มีจริง:** cache `output/priority-forecast-20261017/gfs-weather-{year}.json` เป็น GFS `*_previous_day1` T/RH/rain hourly ที่ **returned point18.802475N,99.02344E** ไม่ใช่ corner grid: ปี2024ครบสามตัวแปร 2460/2904h เริ่ม 19ม.ค.12UTC; ปี2025/2026ครบ2880/2880h ม.ค.–เม.ย. ต้องดึง local sampling เพิ่มถ้าจะทดสอบ spatial warm-up และกรณีต้นม.ค.ต้องหาเดือนธ.ค.ปีก่อน/ยอม exclude อย่างชัดเจน ไม่เติมช่องว่างเป็นศูนย์

Previous-day1 คือ forecast ที่ lead24hสำหรับแต่ละ valid hour **เป็นหลาย initialization ต่อกัน** ใช้เป็น past-state-conditioning sensitivity ได้เมื่อทุก validtime อยู่ก่อน origin และระบุ availability assumption แต่ไม่เรียก single issued run หรือ observation ([Open-Meteo official docs](https://open-meteo.com/en/docs/previous-runs-api)). WRFx/OpenWFM ให้ time-lag moisture model แบบเปิด และระบุ response1/10/100h/ผลฝน ([model description](https://wiki.openwfm.org/wiki/Fuel_moisture_model), [original source](https://github.com/openwfm/wrfxpy/blob/master/src/fmda/fuel_moisture_model.py)).

**วัด/หยุด:** เปรียบเทียบทั้ง initial moisture spread across assumptions และ new-growth Dice/excess area บน cohort เดียวกัน หาก conditioning สองช่วงยาวสุดให้ state ต่างน้อยกว่าเกณฑ์ที่ตรึงไว้แต่ผลไฟยังไม่ดี อย่าขยาย spin-up ต่อโดยหวังว่าจะแก้ทุกอย่าง; ถ้า branch ไม่ชนะให้เลิก ไม่อ้าง estimate นี้เป็นค่าความชื้นเชื้อเพลิงวัดจริง

## 5. ทำ probability ให้ใช้ตัดสินใจได้ และอนุญาตให้โมเดลตอบ “หลักฐานไม่พอ”

**ปัญหาที่แก้:** คะแนน threshold0.03 เป็น **decision threshold ของโมเดล** ไม่ใช่หลักฐานว่าโอกาสไฟจริง3% การบังคับวาดแนวไฟทุกกรณีทั้งที่ภาพ/สภาพปัจจุบันไม่พอเพิ่มพื้นที่เตือนเกิน

**เปลี่ยนโค้ดรอบใหม่:** เพิ่ม separate calibration stage หลัง HGB ใน `run_fire_engineering_loop.py` ใช้ held-event/year calibration ที่ไม่ปะปนกับ training; เริ่ม sigmoid calibration (ข้อมูลน้อยไม่เริ่ม isotonicที่ยืดหยุ่นมาก) ตาม official API ([scikit-learn calibration](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html)). เพิ่ม output uncertainty/abstention จาก initial cloud fraction, time since optical image, last positive age และ ensemble disagreement โดยไม่ใช้ future-cloudmask

**วัด/หยุด:** Brier/log loss/reliability plot และ precision–coverage curve; เปรียบเทียบ alert area budget250km²สำหรับ priority กับพื้นที่ทับกันของ optical-growth แยกกัน วัดว่าการ abstain ลด error เท่าไรและทิ้งกี่ forest-days/positive events Calibration อาจช่วยความหมายคะแนนแต่ **ไม่รับประกัน ranking หรือ Dice เพิ่ม**; หยุดถ้า Brierดีขึ้นเพียงทำนายต่ำทุกจุด หรือ errorลดเพราะระบบเงียบจนพลาดเหตุส่วนใหญ่

## กติกาก่อนเริ่มรอบถัดไป

1. จบรอบ frozen ปัจจุบันก่อน ข้อเสนอในเอกสารนี้ไม่เปลี่ยน model choice/threshold ของกรณี2026ชุดเพิ่มที่กำลังรอประเมิน
2. รักษารายงาน all-new-growth เดิมไว้; เพิ่ม connected/detached/horizon metrics เป็นคำอธิบาย ไม่เปลี่ยน denominator เงียบ ๆ ภาพ Sentinel-2 ห่าง2–5วันไม่กลายเป็นตำแหน่งไฟทุก12h และ HIIรายเดือนเป็น corroboration ไม่ใช่ timing truth20m
3. ตรึงรายชื่อ events, train/validation/test groups, model/threshold budget และ failure criteria ก่อน fit ใหม่ ปี/กรณี2026ที่เคยเปิดแล้วเป็น retrospective regression ต่อไป
4. ตัวอย่าง promotion gate ที่ควรตกลงก่อนรัน: held-event Diceเพิ่มอย่างน้อย10%สัมพัทธ์ **พร้อม** excess-areaไม่เพิ่ม, gainไม่ได้มาจากเหตุเดียว และ event-bootstrap gainไม่คร่อมศูนย์; สำหรับ priorityใช้ coverage ณพื้นที่เตือนเท่ากัน เกณฑ์นี้เป็นข้อเสนอการตัดสินใจของโครงการ ไม่ใช่มาตรฐานสากล
5. หากไม่ผ่าน ให้เก็บตัวเดิม/แสดงเป็น research output และรายงาน branchที่แพ้ ไม่ deployเพราะทำ3Dหรือเพิ่มแหล่งข้อมูลสำเร็จ ทั้งห้าทางเริ่มทำได้จาก open data/software; การลงพื้นที่เป็นข้อมูลเสริมที่อาจมีคุณค่า ไม่ใช่ข้อกำหนดบังคับก่อนพัฒนาได้