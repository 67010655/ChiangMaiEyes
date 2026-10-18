# แกนจำลองไฟลาม เชื้อเพลิง และการตรวจย้อนหลัง

ตรวจแหล่งข้อมูลวันที่ **15 ตุลาคม 2026 (ICT)** เอกสารนี้เสนอวิธีที่ลงมือทำได้โดยไม่เติมค่าภาคสนามที่เรายังไม่มี เป็นการตรวจสมการ ซอร์สโค้ด และหลักฐานอ้างอิง ยังไม่ใช่ผลยืนยันความแม่นยำในเชียงใหม่

## ข้อเสนอที่ทำได้ตอนนี้

ทำ **Rothermel–Albini สำหรับเชื้อเพลิงตายชนิดเดียวที่เป็นเนื้อเดียวกัน** เป็นเครื่องมือจำลองสำหรับผู้วิเคราะห์ รับค่ามวลแห้ง ความลึก ความชื้น คุณสมบัติเชื้อเพลิง ลมระดับกลางเปลวไฟ และความชัน/ทิศขึ้นเขาที่มีแหล่งข้อมูลระบุชัด แล้วคำนวณอัตราลาม ทิศลามสูงสุด และรูปวงรีตามเวลา ผู้ใช้ทั่วไปควรเห็นคำอธิบายว่าส่วนใดวัด ส่วนใดสมมติ และยังไม่ผ่านการสอบเทียบพื้นที่จริง รุ่นนี้ต้องไม่เรียกตัวเองว่าแบบจำลองไฟเรือนยอด สะเก็ดไฟ หรือไฟทั้งภูเขา [Rothermel 1972](https://research.fs.usda.gov/treesearch/32533) · [Andrews 2018](https://research.fs.usda.gov/treesearch/55928) · [ข้อจำกัดของ Behave โดย USFS](https://research.fs.usda.gov/firelab/products/dataandtools/behave)

**เหตุผลที่เลือกขอบเขตนี้:** Behave เป็นแบบจำลอง ณ จุด ใช้กับเชื้อเพลิงสม่ำเสมอ อากาศคงที่ และภูมิประเทศใกล้เคียงกัน เมื่อเงื่อนไขเปลี่ยนต้องคำนวณใหม่ การนำผล ณ จุดมาวาดวงรีไม่ทำให้กลายเป็นการจำลองเชื้อเพลิงต่างชนิดตามพื้นที่โดยอัตโนมัติ [USFS Behave](https://research.fs.usda.gov/firelab/products/dataandtools/behave)

ซอร์สต้นทางที่ตรวจคือ `firelab/behave` commit **`d4acc8a074646c754673b6725234fdf3a1e9c053`** ใช้เลข commit ใน provenance และ test แทนลิงก์ `master` ซึ่งเปลี่ยนได้ โค้ดของห้องปฏิบัติการระบุว่าเป็น public domain และไม่มีการรับประกันผลการใช้งาน การอ้างแหล่งนี้ไม่สื่อว่า USFS รับรอง ChiangMaiEyes [Repository](https://github.com/firelab/behave/tree/d4acc8a074646c754673b6725234fdf3a1e9c053) · [License](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/LICENCE.md)

## 1. สัญญาข้อมูลเข้า: ต้องมีค่า หน่วย เวลา และที่มา

| ตัวแปร | หน่วยที่หน้าเว็บ/API | การตีความ |
|---|---|---|
| มวลเชื้อเพลิงตายแห้งต่อพื้นที่ | kg/m² | มวลอบแห้งของชั้นที่พาไฟ ไม่ใช่มวลสดหรือมวลต้นไม้ทั้งต้น |
| ความลึกชั้นเชื้อเพลิง | m | ความลึกของ fuel bed ที่จำลอง |
| Surface area/volume, SAVR | m⁻¹ | พื้นที่ผิวอนุภาคต่อปริมาตรอนุภาค ไม่ใช่ความหนาแน่นต้นไม้ |
| ความชื้นเชื้อเพลิง | % ของมวลแห้ง | `(มวลสด−มวลแห้ง)/มวลแห้ง × 100` |
| ความชื้นที่ไฟไม่ลามในโมเดล, Mx | % ของมวลแห้ง | พารามิเตอร์ fuel model ต้องมีหลักฐานหรือระบุเป็นสมมติฐาน |
| ค่าความร้อน | kJ/kg | แปลงหน่วยก่อนเข้าสมการเชิงประจักษ์ |
| ความหนาแน่นเนื้ออนุภาค | kg/m³ | คนละค่ากับ bulk density ของชั้นเชื้อเพลิง |
| สัดส่วนแร่ธาตุรวม/ส่วนที่มีผล | fraction 0–1 | พารามิเตอร์ St/Se ของสมการ |
| ความเร็วลมกลางเปลวไฟ | m/s | `DirectMidflame`; ต้องระบุวิธีวัด/ที่มา |
| ทิศลม | องศาตามเข็มจากเหนือ | ระบุ **พัดมาจาก** เพื่อให้ตรงข้อมูลอุตุนิยมวิทยา |
| ความชัน/ทิศลาดลง | องศา/องศาตามเข็มจากเหนือ | ใช้ค่าที่จุดหรือกริด ไม่ใช้ median ทั้งป่าแทนจุดเกิดไฟ |

รายการคุณสมบัติเชื้อเพลิงและสมการอ้างอิงจาก [Rothermel 1972](https://research.fs.usda.gov/treesearch/32533), [USFS fuelbed intermediates](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFuelbedIntermediates.cpp#L126-L174), และ [คู่มือ FIREMON](https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164.pdf) ส่วนการกำหนด API ให้ใช้ SI และแยกหลักฐานเป็นข้อเสนอวิศวกรรมของโครงการ

ข้อมูล GFS/Open-Meteo 10 m ต้องคงป้ายความสูงเดิม **ห้ามคัดลงช่อง midflame โดยตรง** ต้นทาง Behave มีขั้นตอนแปลงความสูงและ Wind Adjustment Factor แยกต่างหาก จึงไม่ควรตั้งตัวคูณให้ป่าเชียงใหม่โดยเดา แม้สูตรจะยอมรับตัวคูณที่ผู้ใช้กรอกก็ตาม [USFS ขั้นตอน wind height](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L498-L547)

ลมอุตุนิยมวิทยา 0° หมายถึงพัดมาจากเหนือและพัดไปใต้ แปลง `wind_to = (wind_from + 180) mod 360`; ทิศขึ้นเขาเท่ากับ `(downslope_aspect + 180) mod 360` กรณีพื้นราบหรือลมสงบไม่สร้างทิศเหนือขึ้นมาแทนค่าที่ไม่มีทิศ [ECMWF: นิยามทิศลม](https://confluence.ecmwf.int/pages/viewpage.action?pageId=212441203) · [USFS การแปลงทิศลาม](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L592-L597)

## 2. สมการที่ใช้เขียนแกนคำนวณได้

ส่วนนี้เป็นการย่อสมการของต้นทางลงกรณี **single dead class** เท่านั้น ไม่ใช่การถัวเฉลี่ยเชื้อเพลิงหลายชั้นมาใส่ช่องเดียวโดยไม่มีการตรวจ สมการเชิงประจักษ์ชุดนี้ใช้ imperial ภายใน: `w0` lb/ft², `depth` ft, `rho_p` lb/ft³, `sigma` ft⁻¹, `heat` Btu/lb, `U` ft/min; `M`, `Mx`, `St`, `Se` เป็น fraction สมการให้ R เป็น ft/min แล้วจึงแปลงกลับ m/min

### 2.1 เชื้อเพลิงและอัตราเมื่อไม่มีลม/ทางลาด

```text
rho_b = w0 / depth
beta = rho_b / rho_p
beta_opt = 3.348 * sigma^(-0.8189)
relative_beta = beta / beta_opt
A = 133 * sigma^(-0.7913)              # Albini-adjusted variant
gamma_max = sigma^1.5 / (495 + 0.0594 * sigma^1.5)
gamma = gamma_max * relative_beta^A * exp(A * (1 - relative_beta))

r = M / Mx
eta_M = 1 - 2.59*r + 5.11*r² - 3.52*r³   when 0 <= r < 1
eta_M = 0                                when r >= 1
eta_S = min(1, 0.174 * Se^(-0.19))
I_R = gamma * w0 * (1 - St) * heat * eta_M * eta_S

xi = exp((0.792 + 0.681*sqrt(sigma)) * (beta + 0.1))
     / (192 + 0.2595*sigma)
epsilon = exp(-138 / sigma)
Q_ig = 250 + 1116*M
R_0 = I_R * xi / (rho_b * epsilon * Q_ig)
```

ต้นทางของ `beta`, `beta_opt`, `rho_b`: [surfaceFuelbedIntermediates.cpp 126–174](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFuelbedIntermediates.cpp#L126-L174); `xi`, `epsilon`, `Q_ig`, net load: [476–607](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFuelbedIntermediates.cpp#L476-L607); `gamma` และ damping: [surfaceFireReactionIntensity.cpp 71–147](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFireReactionIntensity.cpp#L71-L147); `R_0`: [surfaceFire.cpp 156–161](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L156-L161)

ต้องปฏิเสธค่าไม่ finite, depth/particle density/SAVR/Mx ที่ไม่เป็นบวก และแยก missing ออกจากศูนย์ กรณี `M >= Mx` ได้ศูนย์ **ภายใต้โมเดลและ input นี้** ไม่ได้แปลว่าพื้นที่ไม่มีทางเกิดไฟ ต้นทางมี SAVR size bin ต่ำสุด 16 ft⁻¹; ถ้ารุ่น single fine dead fuel ไม่รองรับเชื้อเพลิงหยาบกว่านี้ให้ตรวจขอบเขตอย่างชัดเจน ไม่แอบอ้างว่ารองรับเชื้อเพลิงทุกชนิด [USFS size-bin weighting](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFuelbedIntermediates.cpp)

### 2.2 รวมลมกับความชันเป็นเวกเตอร์

```text
C = 7.47 * exp(-0.133*sigma^0.55)
B = 0.02526 * sigma^0.54
E = 0.715 * exp(-0.000359*sigma)
phi_w = C * U_midflame^B * relative_beta^(-E)
phi_s = 5.275 * beta^(-0.3) * tan(slope_radians)^2

delta = wind_to - upslope                 # radians for trig
x = phi_s + phi_w*cos(delta)
y = phi_w*sin(delta)
phi_effective = hypot(x, y)
R_head = R_0 * (1 + phi_effective)
heading = upslope + atan2(y, x)
U_effective = (phi_effective * relative_beta^E / C)^(1/B)
```

นี่เป็นการรวมเวกเตอร์ของแรงส่งลม/ทางลาดตามต้นทาง ไม่ใช่เอาความเร็วลมเป็นความเร็วไฟ และไม่ใช่บวก `phi_s + phi_w` ทุกกรณี ลมสวนทิศขึ้นเขาหรือขวางทางลาดต้องให้ผลต่างจากลมตามทางลาด หาก resultant เป็นศูนย์ให้ heading เป็น `null` และใช้รูปสมมาตร [USFS wind/slope factors](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L478-L556) · [USFS vector composition/effective wind](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L394-L457)

**Wind cap ต้องเป็นชื่อ variant ที่เปิดเผย:** constructor ของต้นทางปัจจุบันตั้ง `isWindLimitEnabled_ = false` ถ้าเปิด old cap จะใช้ `U_limit = 0.9*I_R` แล้วคำนวณ phi/R ใหม่ ไม่ใช่ตัดความเร็ว R ตรง ๆ งานต้นฉบับปี 2013 พบ old/revised wind limits จำกัดเกินไปและเสนอให้จำกัด R ด้วย effective midflame wind แทน จึงไม่มีเหตุผลรองรับการเรียก old cap ว่า “ปลอดภัยกว่า” โดยอัตโนมัติ เสนอชื่อรุ่น `albini1976_single_dead_no_wind_cap` พร้อมบอกว่าเกิน legacy wind threshold หรือไม่ [USFS constructor](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L63-L77) · [optional cap](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L384-L391) · [Andrews, Cruz & Rothermel 2013](https://research.fs.usda.gov/treesearch/44352)

### 2.3 รูปวงรี ณ เวลาที่กำหนด

เมื่อใช้ `U_effective` **mph** (`ft/min ÷ 88`):

```text
q = min(8, .936*exp(.1147*U_effective_mph)
           + .461*exp(-.0692*U_effective_mph) - .397)
e = sqrt(q² - 1) / q
R_back = R_head * (1-e)/(1+e)
R_flank = (R_head + R_back)/(2*q)

a = (R_head + R_back)*t/2        # semimajor along heading
b = a/q                          # semiminor across heading
c = a - R_back*t                 # center offset from ignition toward heading
```

ใช้ t เป็นนาทีเมื่ออัตราลามเป็น m/min; กรณีลม/ทางลาดเป็นศูนย์ q=1 และได้วงกลม ระยะที่วาดคือผลคำนวณตามสมมติฐาน ไม่ใช่พื้นที่เผาไหม้ที่ตรวจยืนยัน ห้ามนำ wind 10 m มาใช้ในสูตร q โดยไม่ผ่าน fuel/wind model [USFS fireSize.cpp 83–150, 182–199](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/fireSize.cpp#L83-L150)

## 3. ตัวเลขอ้างอิงสำหรับ regression

**FM1 ต่อไปนี้ใช้ตรวจซอฟต์แวร์เท่านั้น ไม่ใช่เชื้อเพลิงมาตรฐานป่าเชียงใหม่** ค่าต้นทางคือ depth 1 ft, dead load .034 lb/ft², SAVR 3500 ft⁻¹, heat 8000 Btu/lb, Mx .12 ส่วน particle density 32 lb/ft³, St .0555, Se .01 เป็นค่าที่ต้นทางใช้ทั่วไป ต้องไม่แอบใส่เป็นค่าที่สำรวจจริง [Official FM1 record](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/fuelModels.cpp#L154-L168) · [Official initialization](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFuelbedIntermediates.cpp)

มี **external regression ที่ build official C++ แบบ pin commit** โดยผู้พัฒนา PyFireCA: Behave core `29888c7ad364aa18cfb340f4c25a8e395f24260f` และ Behave app `a3cfcd5903188d73445948af16644868225bb9d5` ตรวจอ่าน workflow และ GitHub Actions API ว่ารอบ vector run `31593021417` จบ `success` แล้ว ไม่ได้รัน official binary นี้เองบนเครื่องโครงการในงานวิจัยรอบนี้ [base/wind/slope workflow](https://github.com/hujinghaoabcd/PyFireCA/blob/3ffe93ddb4b6956f5942405e365f6f0bfdaab4c6/.github/workflows/behave7-r2-probe.yml) · [vector workflow](https://github.com/hujinghaoabcd/PyFireCA/blob/3ffe93ddb4b6956f5942405e365f6f0bfdaab4c6/.github/workflows/behave7-r3-vector.yml) · [successful vector run](https://github.com/hujinghaoabcd/PyFireCA/actions/runs/31593021417)

ทุกกรณีใช้ FM1 ความชื้นตาย 5%:

| กรณี | official-runtime regression ที่รายงาน (chains/h) |
|---|---:|
| ไม่มีลม/ความชัน | 4.4262698923571939 |
| slope 30% ไม่มีลม | 20.817222076028628 |
| midflame 100 ft/min ไม่มีความชัน | 8.834274755440232 |
| slope 30% และ midflame 100 ft/min ขวางทิศขึ้นเขา | 21.399596624626479 |

แหล่งตัวเลข: [FM1 fixture](https://github.com/hujinghaoabcd/PyFireCA/blob/3ffe93ddb4b6956f5942405e365f6f0bfdaab4c6/tests/validation/data/behave7_r2_zero_wind_zero_slope.csv), [base workflow](https://github.com/hujinghaoabcd/PyFireCA/blob/3ffe93ddb4b6956f5942405e365f6f0bfdaab4c6/.github/workflows/behave7-r2-probe.yml#L60-L99), [vector workflow](https://github.com/hujinghaoabcd/PyFireCA/blob/3ffe93ddb4b6956f5942405e365f6f0bfdaab4c6/.github/workflows/behave7-r3-vector.yml#L44-L82) ตัวเลขเป็นหลักฐานความสอดคล้องกับซอฟต์แวร์ต้นทาง ไม่ใช่ accuracy ต่อเหตุจริง

**ตรวจคำนวณซ้ำในงานนี้:** single-class scalar calculation จากสมการด้านบนได้ R0 `1.48403976950952 m/min` และ vector `7.174856756304765 m/min` ตรงกับ oracle เมื่อแปลง `1 chain = 20.1168 m` ตัวอย่าง SI คือ load `.16600253963702372 kg/m²`, depth `.3048 m`, SAVR `11482.939632545931 m⁻¹`, particle density `512.5908279667244 kg/m³`, heat `18608 kJ/kg`, midflame `.508 m/s`, slope `16.69924423399362°` (=30%)

สำหรับ upslope 0° และ wind-from 270° คำนวณได้ heading `15.0523735027703°`, effective wind `191.73135817679253 ft/min`, q `1.2012136371759516`, backing `2.0589673566830258 m/min` **ค่าทิศ/วงรีชุดนี้เป็นการคำนวณเชิงวิเคราะห์จากซอร์ส ไม่ใช่ output ของ binary ที่รันเอง** ควรใช้ test คนละกลุ่มกับค่าที่มี external runtime regression

## 4. ข้อมูลดาวเทียมช่วยเชื้อเพลิงส่วนใดได้

EVI บอกความเขียวของเรือนยอดและต้องใช้ QA/วันที่ composite ไม่ได้วัด kg/m² ของใบไม้/กิ่งไม้แห้งที่พื้น จึงไม่ใช้ EVI เป็น fuel load/moisture โดยตรง [NASA MODIS Vegetation Index](https://modis.gsfc.nasa.gov/data/dataprod/mod13.php) รายละเอียด DEM และแบบบันทึกภาคสนามอยู่ใน [บันทึกแหล่ง terrain/fuel เดิม](2026-10-13-terrain-and-fuel-sources.md)

ESA WorldCover 2021 v200 เป็น land-cover map 11 classes กริดประมาณ 10 m มี COG 3×3° ใน EPSG:4326 บน AWS anonymous ช่วยจำแนกบริบท tree/shrub/grass/water/built-up ได้ แต่ **ไม่มีพารามิเตอร์ fuel loading, moisture, depth หรือ SAVR ของสูตรเรา** เสนอใช้เป็นชั้นอ้างอิงลงสำรวจ/ตรวจสิ่งกีดขวาง ต้องไม่แปลง tree cover เป็น fuel model ไทยโดยไม่สอบเทียบ แสดงปี 2021 และเครดิต CC BY4.0 [ESA data access](https://esa-worldcover.org/en/data-access) ไม่ดาวน์โหลด raster เพิ่มในงานวิจัยรอบนี้

## 5. การตรวจย้อนหลัง: สิ่งที่ FIRMS ยืนยันได้และไม่ได้

FIRMS active fire เป็นการตรวจพบความร้อนใน pixel ณ เวลาผ่านของดาวเทียม พิกัดไม่ใช่ตำแหน่งเปลวไฟที่ละเอียดภายใน pixel; VIIRS มี nominal 375 m และความละเอียดเปลี่ยนตาม scan angle ส่วน MODIS ประมาณ 1 km การไม่ตรวจพบอาจเกิดจากข้อจำกัดการสังเกต จึงไม่เท่ากับไม่มีไฟ [NASA VIIRS FAQ](https://forum.earthdata.nasa.gov/viewtopic.php?t=5189) · [NASA MODIS FAQ](https://forum.earthdata.nasa.gov/viewtopic.php?t=5191)

NASA แนะนำ burned-area products สำหรับพื้นที่ไหม้ แทนการบวกพื้นที่ active-fire pixels เพราะมีปัญหาการสุ่มในเวลา/พื้นที่ การสร้าง convex hull ของ FIRMS จึงไม่กลายเป็น perimeter จริง [NASA FIRMS burned-area guidance](https://wiki.earthdata.nasa.gov/spaces/FIRMS/blog/2025/05/20/439977926/New%2BEnhanced%2BTools%2Bfor%2BInterannual%2Band%2BMonthly%2BComparisons%2Bof%2BBurned%2BArea)

**ข้อเสนอวิธีประเมินสำหรับโครงการ:**

1. ล็อก `as_of`, เวลา source observation/available/forecast issue, input hash, model version, assumptions และ prediction ก่อนอ่านผลอนาคต ถ้าใช้ reanalysis/ข้อมูลแก้ย้อนหลังให้เรียก **hindcast** ไม่อ้างว่าเท่ากับผล forecast ที่ทำไว้จริง
2. ชุดทดสอบ FIRMS ใช้เฉพาะจุดหลัง as_of และหลังจุดเริ่มต้น แยก sensor/confidence/source version; จุดเดียวกันต่างดาวเทียมต้องมีนโยบายซ้ำที่เปิดเผย การจัดจุดว่าเป็นไฟเหตุเดียวกันต้องมีหลักฐานหรือแสดงว่าเป็นข้อสมมติในการ clustering
3. รายงาน `จำนวนจุดทดสอบ`, `สัดส่วนจุดที่อยู่ภายในขอบเขตจำลอง`, `ระยะจุดนอกขอบเขตถึงขอบจำลอง` พร้อมเวลาทำนายล่วงหน้าและขนาดพื้นที่จำลอง เทียบ baseline ไม่ขยายจากจุดเริ่มต้น และวงกลมที่ใช้อัตราฐานเดียวกัน
4. **positive-only points ไม่ให้ precision/false-positive rate/accuracy ของพื้นที่** เพราะพื้นที่ที่ไม่มีจุด FIRMS ยังไม่ได้รับรองว่าไม่ไหม้ และ polygon ใหญ่ครอบจุดมากย่อมดูดีเกินจริง ต้องรายงานพื้นที่ควบคู่กัน การกัน buffer ตาม sensor uncertainty ต้องกำหนดล่วงหน้า ไม่ปรับเพื่อให้คะแนนดี
5. เมื่อมี perimeter ภาคสนาม/ภาพอ้างอิงที่ตีความและตรวจแล้วจึงวัด IoU, พื้นที่คาดเกิน/ขาด, ระยะคลาดของขอบ และเวลาไปถึงจุดที่สังเกต หน่วย m/min สำหรับอัตราลาม, m สำหรับตำแหน่ง, min สำหรับเวลา ไม่ใช้ PM2.5 เป็น ground truth ของแนวไฟ
6. แยก **ทั้งเหตุ** สำหรับปรับพารามิเตอร์ออกจากเหตุทดสอบ เก็บช่วงลม/ชนิดเชื้อเพลิงที่ยังไม่ครอบคลุม ไม่อ้างตัวเลขเดียวแทนทุกป่า ฤดู และสภาพอากาศ แนวทางให้เก็บผลจริงเพื่อ verification/adjustment มีเอกสาร USFS ต้นฉบับ [Field procedures](https://research.fs.usda.gov/treesearch/24636)

ข้อ 1–6 เป็น protocol ที่เสนอจากข้อจำกัดการสังเกตข้างต้น ไม่ใช่การอ้างว่า NASA รับรอง metric หรือผลของ ChiangMaiEyes

## 6. ขอบเขตที่ต้องแสดงกับผลจำลอง

- fuel observation/สมมติฐานแต่ละค่า รวมถึงชนิดเชื้อเพลิงที่ single-class ไม่แทนได้
- ลม midflame ที่โมเดลใช้ แยกจากลม 10 m ที่แสดงประกอบ และไม่ใช้ PM2.5 เป็นแรงผลักไฟ
- terrain แบบจุด/กริดที่ใช้จริง หากเป็นเพียง slope/aspect ที่ผู้วิเคราะห์ระบุให้บอกตามนั้น; DSM ไม่ใช่พื้นดินเปลือย
- สภาพคงที่/ไม่มี suppression, spotting, crown transition, การเริ่มต้นใหม่ และขอบเขตผลที่ยังไม่ได้ validate
- ช่วงผลหลาย input เป็น **sensitivity scenarios** ไม่ใช่ 90/95% confidence interval เว้นแต่ได้สร้างและตรวจ probability model แล้ว
- ห้ามเอาขอบเขตป่าชุมชนมาตัดไฟให้หยุดตรงเขตปกครองโดยไม่มีสิ่งกีดขวางจริง และไม่ตีความขอบเขตจำลองเป็นพื้นที่เผาไหม้ยืนยันหรือคำสั่งส่งกำลัง

รายการนี้เป็นข้อเสนอการสื่อสารของโครงการเพื่อรักษาสมมติฐานแบบจำลองและข้อจำกัดแหล่งข้อมูลให้มองเห็นได้ ไม่ใช่ข้อสรุปว่าความแม่นยำภาคสนามผ่านแล้ว

## 7. ขอบเขต implementation รุ่นแรก

โค้ด `backend/app/spread_scenario.py` ใช้รุ่น `cme-single-dead-albini1976-ellipse-v1` เป็น **conditional scenario** ของไฟผิวดิน ใช้ลมระดับ midflame และค่าความชันคงที่จากจุดเริ่ม หรือข้อมูลที่ผู้ใช้ระบุพร้อมที่มา ไม่มีการนำ PM2.5 มาเป็นแรงผลักไฟ ไม่อนุมานมวลเชื้อเพลิงจาก EVI/land cover และไม่ส่งผลทดลองเข้าอีเมลเตือนหรือคะแนนความเสี่ยงหน้าแรก

ความต่างที่ต้องเปิดเผย: รุ่นนี้ใช้ `phi_s` ตามสมการตีพิมพ์โดยไม่ตัดตามสาขาเก่า `phi_s ≤ 0.9 I_R` ใน Behave เมื่อเข้าเงื่อนไขนั้นจะส่ง diagnostic `legacy_slope_clamp_omitted` และข้อความให้ตรวจความเหมาะสม จึงอ้าง regression ตรงกับต้นทางเฉพาะสี่กรณี FM1 ที่ระบุในเอกสารนี้ ไม่อ้าง exact parity ทุก input [สาขา slope limit ของต้นทาง](https://github.com/firelab/behave/blob/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave/surfaceFire.cpp#L465-L475)

ข้อมูลภูมิประเทศที่ใช้จริงอยู่ใน `backend/app/data/forest-terrain-points.json`: จุดสมมติภายในขอบเขตที่ถูกต้อง 676 แห่งจากทั้งหมด 677 แห่ง กัน `cmf-th-3192` ออกจากการคำนวณ จุดนี้เป็นตำแหน่งเพื่อทดลอง ไม่ใช่ตำแหน่งที่ตรวจพบไฟ การคำนวณใช้ bilinear UTM47N 30 m / Horn 3×3 พร้อมแปลงทิศ grid north เป็น true north และเก็บ hash ของพิกเซลตัวอย่างกับต้นทาง

ระหว่างตรวจพบและแก้การรวม DSM ตรงรอยต่อ: รวมพิกเซลบน **native source grid** ก่อน reprojection ครั้งเดียว ไม่ตั้งกริดใหม่ตามเลขพิกัดเต็มซึ่งจะเลื่อนต้นทาง Copernicus ที่มี half-pixel origin แล้วคำนวณทั้งจุดตัวอย่างและค่าสรุปป่าใหม่ ตัวอย่าง `cmf-th-2869` หลังแก้ได้ slope `4.6354531205°` และ upslope `153.8048291823°` ค่านี้ตรวจย้อนไปยัง source SHA-256 ใน artifact ได้ [GDAL PixelIsPoint / half-pixel convention](https://gdal.org/en/stable/development/rfc/rfc33_gtiff_pixelispoint.html)

API ที่เพิ่ม:

- `GET /api/spread/terrain-point?forest_id=...`: อ่านจุด DSM พร้อม provenance
- `POST /api/spread/simulate`: ผล 30 นาทีต่อช่วง สูงสุด 6 ชั่วโมง พร้อมกรณีลองเปลี่ยนความชื้นและค่าฐานเชื้อเพลิงเดิม ไม่มีลม พื้นราบ
- `POST /api/spread/evaluate`: ตรวจย้อนหลัง แยก FIRMS detection ออกจาก field arrival; เว้นจุดซ้ำแม้เขตเวลาต่างกัน เก็บจำนวนตัวอย่าง MAE/median ของเวลาเฉพาะ field arrival และจำนวนที่โมเดลไม่ลามถึง ไม่แปลงเป็น accuracy หรือ IoU

หน้าเว็บอยู่ใน วิเคราะห์ → **ลองจำลองไฟลาม · สำหรับการศึกษา** ไม่เพิ่มเมนูหลัก ผู้มีสิทธิ์ป่านั้นบันทึกเชื้อเพลิงและผลผ่าน `cme_research_records` เดิมซึ่งใช้ RLS และเปิดผลเดิมคืนได้ ผลมี `issued_at`, input SHA-256, model version, เวลา/สถานะข้อมูล และแยกคุณสมบัติวัสดุมาตรฐานจากข้อมูลที่ผู้ใช้ระบุว่าตรวจวัด การเปิดผลเดิมไม่คำนวณใหม่โดยไม่แจ้งผู้ใช้

**ยังไม่สำเร็จในฐานะพยากรณ์ที่ยืนยันความแม่นยำ:** ไม่มีการแพร่ไฟบนกริดเชื้อเพลิง/ลม/ความชันที่เปลี่ยนตามพื้นที่ ยังไม่มีชุดเชื้อเพลิงเชียงใหม่ที่สอบเทียบครบ ไม่มีกรอบไฟและเวลาไฟมาถึงอิสระสำหรับทดสอบแบบ blind งานถัดไปจึงต้องสร้างข้อมูลภาคสนามและเหตุทดสอบที่แยกทั้งเหตุ พร้อมแช่แข็งข้อมูล/ผลล่วงหน้า แล้วค่อยเทียบค่าฐานตาม protocol ข้างต้น ไม่รายงานจุดจำลองหรือค่าจากสมการเป็นเหตุจริง
