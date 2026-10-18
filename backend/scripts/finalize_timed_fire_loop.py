"""Write a readable final decision with measured values and reproducible artifacts."""
import hashlib
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
import timed_fire_spread_benchmark as b


def main():
    comparison=b.read(b.OUT/'COMPARISON.json')
    verification=b.read(b.OUT/'numerical-verification.json')
    frozen=b.verify_frozen_inputs()
    assert verification['frozen_case_count']==15
    assert verification['inference']['native20m_initial_only_replay']=='passed'
    assert verification['production']['unchanged_files']==6
    core=comparison['cohorts']['original_case_studies']
    community=comparison['cohorts']['community_known_hotspot_enriched']
    chosen=core['selected_overall']
    forest=comparison['community']['community_known_hotspot_enriched']['0.01']['scores']['selected_overall']
    physical=b.read(b.OUT/'spread-selection.json')
    growth=b.read(b.OUT/'growth-ml/selection.json')
    dense=b.read(b.OUT/'growth-20m/selection.json')
    labels={'selected_overall':'ตัวเลือกหลักจากปี2025: ฟิสิกส์ FM8 + ความชื้นเปลี่ยนตามอากาศ',
            'selected_physics':'ฟิสิกส์ FM8 + ความชื้นเปลี่ยนตามอากาศ',
            'selected_growth_policy':'วิธีฐาน: พืชพรรณภายใน500ม.จาก hotspot',
            'selected_dense20m':'โมเดลเรียนรู้ hotspot + ลม + PM ที่ระดับ20ม.',
            'full_small':'โมเดลเรียนรู้เต็ม100ม.ขนาดเล็ก',
            'full_large':'โมเดลเรียนรู้เต็ม100ม.ขนาดใหญ่',
            'without_pm':'โมเดล100ม.เมื่อตัด PM ออก',
            'without_wind_pm':'โมเดล100ม.เมื่อตัดลม/อากาศ/PMออก',
            'selected_isotropic':'วิธีฐานไฟขยายเท่ากันทุกทิศ',
            'no_growth':'ไม่ทำนายพื้นที่ไหม้ใหม่'}
    validation={'selected_physics':physical['validation'][physical['selected']]['macro_dice'],
                'selected_growth_policy':growth['validation'][growth['selected']]['macro_dice'],
                'selected_dense20m':dense['validation'][dense['selected']]['macro_dice']}
    rows=[]
    for name in ('selected_physics','selected_growth_policy','selected_dense20m','full_small','full_large','without_pm','without_wind_pm','selected_isotropic','no_growth'):
        v=core[name]
        validation_score=validation.get(name)
        if validation_score is None and name in comparison['choices_frozen_from2025'] and name not in ('selected_isotropic','no_growth'):
            key=comparison['choices_frozen_from2025'][name][1]
            validation_score=growth['validation'][key]['macro_dice']
        val='—' if validation_score is None else f'{validation_score*100:.2f}%'
        rows.append(f'| {labels[name]} | {val} | {v["pooled_dice"]*100:.2f}% | {v["macro_dice"]*100:.2f}% | {v["predicted_growth_km2"]:.3f} | {v["reference_coverage"]*100:.1f}% |')
    cases=[]
    for c in frozen['cases']:
        meta=b.read(b.OUT/'cases'/c['id']/'case.json')
        quality=b.read(b.OUT/'cases'/c['id']/'quality.json')
        cases.append(f'| {c["id"]} | {c["split"]} | {c["cohort"]} | {meta["initial_acquisition"]} | {meta["final_acquisition"]} | {meta["horizon_hours"]:.2f} | {quality["reference_growth_km2"]:.4f} |')
    interval=comparison['core_pooled_dice_intervals']['selected_overall']
    near=b.ROOT/'output/community-cell-model-20261017/decision.json'
    text=f'''# คำตอบสุดท้ายของรอบทดลอง ChiangMaiEyes

จัดทำ {datetime.now(timezone.utc).astimezone().isoformat()} · ทดลองออฟไลน์ · ไม่มี deploy

## สำหรับคนที่ต้องการรู้ว่าใช้ช่วยป่าได้จริงไหม

**มีหลักฐานว่าช่วยจัดลำดับพื้นที่เฝ้าระวังได้ แต่ยังไม่มีหลักฐานพอให้ใช้เส้นทำนายไฟลามเป็นตำแหน่งไฟในอนาคตที่เชื่อถือได้ และยังไม่ได้พิสูจน์ว่าลดความเสียหายป่าได้จริง**

- ตัวทดลองจัดอันดับ hotspot ที่ดีที่สุดเดิม: เลือกพื้นที่250ตร.กม./รอบ ครอบคลุมช่องที่มี VIIRS ใน12ชั่วโมงถัดไป **36.07% (6,988/19,372)** เทียบฐาน **28.44% (5,510/19,372)** เพิ่ม7.63จุดเปอร์เซ็นต์ หรือ26.8%เมื่อเทียบสัดส่วนกับฐาน แต่ยังพลาด63.93%ของช่องเป้าหมายในงบพื้นที่นี้
- เฉพาะขอบเขตป่าชุมชนและรอบขอบเขต1กม.: ครอบคลุมช่อง hotspot **57.89% (2,204/3,807)** เทียบฐาน55.06% เป็นคนละขอบเขต/ตัวหารกับ36.07% ไม่ใช่พัฒนาจาก36เป็น58บนโจทย์เดียวกัน และไม่ใช่อัตราช่วยป่าสำเร็จ
- **ไฟลามที่ทดสอบใหม่:** ตัวเลือกจากปี2025ได้ Dice ของพื้นที่ไหม้ใหม่ **{chosen['pooled_dice']*100:.2f}%** ใน8กรณีหลักปี2026 โมเดลทำนายพื้นที่รวม{chosen['predicted_growth_km2']:.2f}ตร.กม. เทียบรอยเปลี่ยนแปลงอ้างอิง{chosen['reference_growth_km2']:.3f}ตร.กม. และตรงกัน{chosen['intersection_km2']:.3f}ตร.กม. ปัญหาหลักคือพื้นที่เกินมาก
- ในกลุ่มเพิ่มที่เลือกจาก hotspot ภายในป่าชุมชน ตัวเลือกหลักเตือนตรง **{forest['observed_and_warned']}/{forest['observed_and_warned']+forest['observed_not_warned']} ช่วงป่าที่พบรอยไหม้ใหม่อย่างน้อย1เฮกตาร์** และมีอีก{forest['warned_without_observed_scar']}ช่วงที่เตือนแต่ไม่พบรอยไหม้ตามเกณฑ์ กลุ่มนี้เล็กและตั้งใจเลือกพื้นที่มีไฟ จึงใช้รับรองทั้ง677ป่าไม่ได้

**36%น่าพอใจไหม:** ดีกว่าวิธีฐานพอให้เก็บเป็นตัวช่วยเลือกพื้นที่ตรวจ แต่ไม่พอให้เชื่อว่าไม่เตือนแล้วปลอดไฟ ที่500ตร.กม./รอบครอบคลุม48.99%; ถ้าต้องการครอบคลุม80%ต้องขยายพื้นที่ประมาณ3,753.75ตร.กม./รอบในชุดย้อนหลังเดิม การเพิ่มพื้นที่เตือนไม่ใช่หลักฐานว่าแนวไฟแม่นขึ้น

**ต้องทำอะไรต่อในฐานะเจ้าของโครงการ:** รอบทดลองนี้ไม่ต้องกรอกข้อมูลหรืออนุมัติเพิ่ม ผลเลือกคือเก็บโมเดลจัดลำดับ hotspot เดิมเป็นผู้สมัครหลักสำหรับเว็บ เก็บตัวไฟลามเป็นงานทดลอง และยังไม่สลับโมเดลขึ้นเว็บ ผลทั้งหมดนี้เป็นผลออฟไลน์ ไม่ใช่คะแนนรับรองการทำงานสดของเว็บ

## ทำจริงอะไรไปแล้ว

1. ตรวจเส้นทางพยากรณ์เดิม และแยกโจทย์ hotspot/ไฟลาม/ลม/ฝุ่นให้วัดถูกอย่าง
2. งานจัดอันดับเดิมใช้ฝึกปี2024 เลือกปี2025 และประเมินย้อนหลังปี2026 รวม231รอบที่เปรียบเทียบกันได้ มีกราฟงบพื้นที่และการทดลองป่าชุมชนแล้ว
3. รอบนี้ดึงภาพ Sentinel-2 Collection1 ก่อนเริ่ม/ตอนเริ่ม/หลังเหตุที่มีเวลาชัด ผ่านคุณภาพ15กรณี: เลือกโมเดลปี2025จำนวน4กรณีที่หน้าต่างพื้นที่ไม่ทับกัน; ทดสอบหลักปี2026จำนวน8กรณี และกลุ่มป่าชุมชนเพิ่ม3กรณี อีก1กรณีป่าชุมชนไม่มีภาพผ่านเกณฑ์และเก็บเหตุผลคัดออกไว้
4. เปรียบเทียบ **67ตัวเลือก**: ฟิสิกส์และฐาน27แบบ, โมเดล100ม./เกณฑ์และฐาน28แบบ, และรอบแก้ความละเอียด20ม.อีก12แบบ เก็บทั้งผลชนะและแพ้ ไม่มีเลือกผู้ชนะใหม่ตามคะแนน2026
5. ใช้อัตราลามพื้นผิวของ Pyretechnics ที่ตรึง commit ร่วมกับตัวแก้บนกริดที่เขียนไว้ เปรียบเทียบชนิดเชื้อเพลิง ความชื้น จุดเริ่ม ลม และเวลาที่อนุญาตให้ไฟลาม นี่ไม่ใช่การรัน ELMFIRE/FARSITE เต็มตัว
6. พบและแก้ปัญหา calibration จริง: COG คอลเลกชันเดิมให้ offset ที่ทำให้สะท้อนแสงผิด0.1เมื่อใช้ตาม metadata เปลี่ยนใช้ Collection1 และเก็บหลักฐานเทียบภาพตรงกันไว้ ตรวจ QA ที่ตำแหน่งจริง ไม่ใช้แค่เปอร์เซ็นต์เมฆทั้ง tile
7. ตรึงไฟล์ข้อมูล97ไฟล์ก่อนประเมินรอบแรก ตรวจวันข้อมูล/ทิศลม/กำแพงเชื้อเพลิง/การข้ามชั่วโมงเศษ/รันซ้ำโดยไม่มีภาพหรือคำตอบอนาคต และ hash ไฟล์ production6ไฟล์ยังตรงเดิม

## ผลเปรียบเทียบไฟลามที่วัดบนข้อมูลชุดเดียวกัน

คะแนน Dice = 2×พื้นที่ทับซ้อน/(พื้นที่ทำนาย+พื้นที่อ้างอิง) หักคะแนนทั้งการพลาดและการทายกว้างเกิน; ไม่ใช่เปอร์เซ็นต์จำนวนเหตุที่ทายถูก ค่า pooled รวมพื้นที่ทุกกรณี; macro เฉลี่ยคะแนนกรณีละเท่ากัน

| วิธี | macro Dice ปี2025ที่ใช้เลือก | pooled Dice ปี2026หลัก | macro Dice ปี2026หลัก | พื้นที่ทำนายปี2026 (ตร.กม.) | ครอบคลุมรอยใหม่ |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

ตัวเลือกหลักชนะด้าน macro Dice ปี2025ที่{validation['selected_physics']*100:.2f}% จึงยังเป็นตัวเลือกตามกติกาเดิม แม้โมเดลอื่นบางตัวมีคะแนน2026สูงกว่า ก็ไม่ใช้2026เลือกใหม่ ช่วง bootstrap แบบกลุ่มกรณีของ pooled Dice ตัวหลักประมาณ{interval['lower']*100:.2f}–{interval['upper']*100:.2f}% แต่8กรณีที่เลือกมาไม่แทนความแม่นทั้งจังหวัด

เปลี่ยนเกณฑ์รอยอ้างอิง dNBR0.10/0.27 คะแนนตัวหลักเป็น{chosen['low_threshold_dice']*100:.2f}%/{chosen['high_threshold_dice']*100:.2f}%ตามลำดับ ผลต่ำไม่ได้หายไปเพียงเปลี่ยนเกณฑ์ ส่วนระยะขอบผิดเฉลี่ยสมมาตรประมาณ{chosen['boundary_mean_m']:.0f}เมตร เป็นค่าเฉลี่ยของแต่ละกรณีที่มีขอบทั้งสองฝั่ง

ถ้าดูเฉพาะรอยใหม่ที่ต่อกับรอยเริ่มต้น ตัวหลักครอบคลุม{chosen['connected_growth']['reference_coverage']*100:.1f}% แต่ Dice ยังเพียง{chosen['connected_growth']['pooled_dice']*100:.2f}% เพราะพื้นที่ทำนายเกินมาก นี่แสดงว่าค่า coverage มากกว่า80%อย่างเดียวไม่พอ

### รอบปรับเป็น20เมตรช่วยไหม

ตรวจข้อจำกัด100ม.เทียบรอย20ม.แล้ว แม้ให้คำตอบอนาคตแก่ oracle คะแนน Dice สูงสุดรายกรณียังประมาณ48–67% จึงลองเรียนรู้ระดับ20ม.ด้วยข้อมูลเริ่มต้นจริง ตัวใหม่เลือกด้วยปี2025เหมือนเดิม ได้ pooled Dice ปี2026หลัก **{core['selected_dense20m']['pooled_dice']*100:.2f}%** แต่ macro validation ปี2025เพียง{validation['selected_dense20m']*100:.2f}% จึงยังไม่ชนะตัวหลักตามเกณฑ์ที่ตรึงไว้ การเพิ่มความละเอียดอย่างเดียวไม่แก้ปัญหาสถานะไฟเริ่มต้น/ไฟเกิดใหม่/ข้อมูลฝึกน้อย

รอบ20ม.ถูกออกแบบหลังดูความผิดพลาด2026รอบแรก จึงระบุชัดว่า2026เป็นชุดประเมินย้อนหลังที่ใช้ซ้ำ ไม่ใช่ชุดยืนยันใหม่ แม้ไม่มี2026เข้าสู่การ fit หรือเลือก threshold

## ลมและ PM2.5 ช่วยจริงหรือไม่

โมเดล100ม.ขนาดเดียวกันและ threshold0.03เหมือนกัน ให้ pooled Dice **2.26%ทั้งแบบมีและไม่มี PM** ใน8กรณีหลักนี้ จึงยังไม่มีส่วนเพิ่มจาก PM ที่พิสูจน์ได้ในโจทย์รอยไหม้ใหม่รอบนี้ ไม่ได้แปลว่า PM ไม่มีประโยชน์กับสุขภาพ/ควัน/งานจัดอันดับ hotspot รุ่นเดิม ส่วนการตัดกลุ่มลมพร้อมอุณหภูมิ/ความชื้น/ฝนออกได้1.32% นี่ไม่ใช่การแยกผลลมเพียงตัวเดียว

หลักฐานลมย้อนหลังเดิมที่สนามบิน VTCC: GFSล่วงหน้า24ชม. เทียบ2,871คู่ ความเร็วคลาดเฉลี่ย0.87ม./วินาที; ทิศทางคลาดเฉลี่ย54.1°จาก1,013คู่ที่วัดทิศทางได้ สนามบินไม่ใช่ลมหุบเขาป่าทุกแห่ง

ฝุ่นรายวันเทียบ2สถานี35T/36Tช่วงม.ค.–เม.ย.2026จำนวน236station-days: CAMS MAE12.93µg/m³; ใช้ค่าก่อนหน้าเป็นฐาน MAE6.07µg/m³ ชุดนี้ยังไม่ยืนยันเวลาออกผลของทุกพยากรณ์ จึงใช้เป็นการเทียบ archive รายวัน ไม่รับรองพยากรณ์ล่วงหน้า1/2/3วันของเว็บ และไม่ใช่ค่าฝุ่นตรงทุกป่า

## ช่วยป่าชุมชนแค่ไหน

ตัดกับขอบเขต677polygonจริงที่ส่งให้ระบบ รอยอ้างอิงใช้ศูนย์กลาง pixel20ม.อยู่ภายใน polygon รวมส่วนป่า/ช่วงวันซ้ำด้วยพิกัด UTM ก่อนนับ รับเฉพาะส่วนป่าที่เห็นชัดอย่างน้อย65%

- 8กรณีหลัก:27ส่วนป่า/ช่วงวันผ่านเกณฑ์ แต่ไม่มีรอยใหม่ถึง1เฮกตาร์ จึงไม่มีตัวหารให้คำนวณ recall เหตุขนาดนี้ ห้ามเรียกคะแนนไม่เตือนว่าแม่น100%
- 3กรณีเพิ่มที่เลือกเพราะมี hotspot ในป่า:17ส่วนป่า/ช่วงวันผ่านเกณฑ์ พบ5ช่วงที่มีรอยใหม่อย่างน้อย1เฮกตาร์ ตัวหลักเตือน1และพลาด4; อีก1ช่วงเตือนแต่ไม่พบรอยตามเกณฑ์
- วิธีฐานเตือนวงกว้างครอบทั้ง5ได้ แต่เตือนอีก10ช่วงที่ไม่พบรอยใหม่ แสดงต้นทุนของการเอาเปอร์เซ็นต์ครอบคลุมสูงเพียงอย่างเดียว

นี่เป็นส่วนของป่าที่อยู่ในหน้าต่างภาพที่เลือกมา ไม่ใช่การติดตามทั้งพื้นที่ป่าทั้ง677แห่ง การไม่พบรอยด้วยดาวเทียมยังไม่ยืนยันว่าไม่มีไฟหรือความเสียหายจริง ประโยชน์ที่มีหลักฐานดีที่สุดตอนนี้คือจัดลำดับพื้นที่ให้ตรวจต่อ ไม่ใช่ผลลดพื้นที่เสียหายที่พิสูจน์แล้ว

## โลกมีโมเดลเกิน80%ไหม

**มีรายงานที่ได้เกิน80%ภายใต้นิยามและเงื่อนไขเฉพาะ** งาน FARSITE ปี2025รายงาน median Dice0.851และIoU0.741จาก63วันของ10ไฟยาวนานที่เลือกศึกษา แต่เปรียบเทียบ polygonแบบconvex hullจาก FIRMS กับผลจำลอง และตั้งต้นรายวันด้วยข้อมูลตรวจพบใหม่ จึงไม่ใช่คะแนนทำนายพื้นที่ไหม้ใหม่ของเชียงใหม่จากจุดตั้งต้นครั้งเดียวหลายวัน [บทความผู้เขียน](https://www.mdpi.com/2571-6255/8/5/166/xml), [สำเนาสถาบันผู้เขียน](https://research.unl.pt/ws/portalfiles/portal/123378974/_Eds._2025_..pdf)

Pyros ปี2024รายงาน similarityกรณีจริงสูงสุด0.76 ส่วนคะแนนสูงในกรณีอุดมคติไม่ใช่ผลรับรองเหตุจริงทุกแห่ง [สถาบันผู้เขียน](https://air.unimi.it/handle/2434/1048989)

ในข้อมูลของเราเอง การทายว่าไม่มีพื้นที่ไหม้ใหม่เลยยังได้ pixel accuracy **{comparison['reference_grid_diagnostics']['no_growth_pixel_accuracy']*100:.2f}%** เพราะพื้นที่ส่วนใหญ่ไม่ไหม้ แต่พลาดรอยใหม่ทั้งหมด และบางกรณีแค่คงรอยไหม้เดิมได้ cumulative Diceเกิน80%แล้ว จึงต้องถามว่า80%วัดอะไร/ล่วงหน้านานแค่ไหน/เตือนพื้นที่เท่าไร ก่อนนำมาเทียบกับ36%

## จะทำให้ดีขึ้นด้วยข้อมูลเปิดอย่างไร

สิ่งที่ลงมือและได้คำตอบแล้ว: แก้ calibration, จับคู่ภาพตามเวลา, ใช้สถานะพืช/รอยเริ่มต้น, ความชื้นจากอากาศ, เชื้อเพลิงหลายแบบ, ลมเปลี่ยนตามเวลา, เปรียบเทียบข้อมูล PM, และทดลอง20ม. ไม่มีวิธีใดใน67ตัวเลือกยืนยันการพยากรณ์ขอบไฟที่พร้อมใช้ได้

ลำดับถัดไปตามหลักฐานที่พบ โดยยังไม่ถือว่าทำหรือได้กำไรแล้ว:

1. **เรียนสถานะไฟและอัปเดตทุกครั้งที่มีการตรวจพบใหม่:** แยกไฟยังลุก/ดับแล้ว/เกิดคนละจุด ลดการลาก hotspot เก่าให้ลามต่อหลายวัน ใช้ VIIRSหลายดาวเทียมและภาพที่เข้าถึงก่อนเวลาออกผลจริง ทดสอบแต่ละรอบแยกกับ free-run ไม่เอาข้อมูลใหม่มาแก้คำตอบย้อนหลัง
2. **ขยายคลังภาพที่ผ่านคุณภาพหลายปี/หลายร้อยเหตุ:** รอบนี้มี4กรณีฝึกอิสระ ซึ่งน้อยกว่าจำนวนpixelมาก โมเดลภาพ20ม.ยังไม่เรียนรู้ทั่วไปเพียงพอ ใช้ pipelineดึง/QA/ตรึงข้อมูลที่สร้างแล้ว เพิ่ม splitปีใหม่ที่ไม่เคยใช้เลือกแนวทาง
3. **ปรับลมตามภูมิประเทศและปรับเชื้อเพลิงจริงตามฤดูกาล:** WindNinjaรองรับลมเปลี่ยนตามภูมิประเทศ; Sentinel-2/Sentinel-1ให้บริบทพืชและความชื้น แต่ไม่ใช่ค่าความชื้นเชื้อเพลิงที่วัดตรง ควร conditioningความชื้นก่อนเริ่มหลายวันแทนเริ่ม8/10/12%เพียงไม่กี่ชั่วโมง [USFS WindNinja](https://research.fs.usda.gov/firelab/products/dataandtools/windninja)
4. **ใช้แบบจำลองภาพตามลำดับเวลาเป็นผู้สมัครใหม่:** มีโค้ด WildfireSpreadTSและกระบวนการสร้างข้อมูลเปิดให้ศึกษา/ถ่ายโอนโมเดล ต้อง fine-tuneและวัดในเชียงใหม่ ไม่ยกคะแนนต่างประเทศมาใช้แทน [ผู้พัฒนา WildfireSpreadTS](https://github.com/SebastianGer/WildfireSpreadTS)

ขั้นเหล่านี้ทำจากข้อมูลเปิดและการทดลองในเครื่องได้ การลงพื้นที่ไม่ใช่ข้อกำหนดก่อนเริ่ม แต่ยังไม่มีหลักฐานว่าขั้นใดจะเพิ่มคะแนนเท่าไรจนกว่าจะทดสอบ

## ข้อจำกัดที่เปลี่ยนความหมายของผล

- รอบภาพนี้วัดช่วงจริงประมาณ48–120ชม. ส่วนใหญ่ปลายมี.ค.–เม.ย. ไม่ใช่แนวไฟ12ชม.หรือค่าเฉลี่ยไฟทุกเหตุในม.ค.–เม.ย.
- รอยอ้างอิงคือ spectral-change candidatesจาก dNBR/NDVI ไม่ใช่ขอบไฟสำรวจหรือเวลามาถึงของแนวไฟ อาจมีการเปลี่ยนสภาพพืช/แสง/พื้นที่เกษตรปนอยู่
- ให้ภาพเริ่มต้นแก่โมเดล ณ เวลา acquisitionแบบย้อนหลัง; เวลา catalog processing/เผยแพร่จริงเก็บไว้แต่ยังไม่จำลอง delay จึงยังไม่ใช่การทดสอบทำงานสด
- ลมมาจาก IFSหนึ่งรอบเริ่มอย่างน้อย6ชม.ก่อนภาพ ไม่มีต่อข้อมูลจากรอบอนาคต ผู้ให้บริการเรียก archiveก่อนพ.ค.2026ว่า Cycle49R1hindcasts จึงไม่อ้างว่าเป็น distributionเดิมที่เผยแพร่จริงทุกครั้ง [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api)
- ภูมิประเทศต้นฉบับประมาณ110ม., coverปี2021, ลมประมาณ9กม.; กริด20/100ม.ไม่ได้ทำให้ข้อมูลสิ่งแวดล้อมมีรายละเอียดอิสระเท่านั้น
- พื้นที่รวมเป็นผลรวมของหน้าต่างกรณี ไม่ใช่พื้นที่จังหวัดที่ deduplicateทั้งปี และกรณีต่างกันอาจมีความสัมพันธ์ทางพื้นที่/ฤดูกาล
- สมมติฐาน fuel/moisture/activeSWIRยังไม่ใช่ค่าที่วัดจากป่าไทย; ตัวแก้กริดไม่ได้รวมไฟเรือนยอด สะเก็ดไฟ การดับไฟ หรือการจุดไฟใหม่ทุกครั้ง
- Pyretechnicsเป็นโค้ดที่มีเงื่อนไข community/commercialของผู้พัฒนา ใช้ในโฟลเดอร์ทดลองและเก็บLICENSEเดิม ไม่ได้เพิ่มเข้า production [licenseที่ตรึงไว้](https://github.com/pyregence/pyretechnics/blob/a811ae508a5d7eeebb808b156e0e2066d4445602/LICENSE)

## ตารางเวลาและขนาดข้อมูลจริง

| รหัสกรณี | บทบาท | กลุ่ม | ภาพเริ่ม UTC | ภาพหลัง UTC | ชม. | รอยใหม่ (ตร.กม.) |
|---|---|---|---|---|---:|---:|
{chr(10).join(cases)}

## ไฟล์หลักและการรันซ้ำ

- `COMPARISON.json`: ตัวเลขทั้งสองกลุ่ม, forest-period counts, bootstrap, grid ceiling และ PM ablation
- `frozen-inputs.json`: hashข้อมูล97ไฟล์และผลเลือกก่อนทดสอบ; `growth-20m/frozen-selection.json`: น้ำหนัก/เกณฑ์รอบ20ม.ที่ตรึงก่อนประเมิน
- `numerical-verification.json`: การตรวจตัวเลข เวลา รันโดยไม่มีคำตอบอนาคต และproduction hash
- `spread-selection.json`, `growth-ml/selection.json`, `growth-20m/selection.json`: ผลเลือกและผลทุกfoldปี2025
- `test-results.json`, `growth-ml/test-results.json`, `growth-20m/test-results.json`: ผลปี2026ทุกตัวเลือก
- `MODEL_DECISION.json`: ตัวเลือกออฟไลน์และสถานะไม่promote
- โมเดลจัดอันดับเดิมอยู่ `../joint-fire-model-20261017/final-candidate/`; คำสั่งและfeature contractอยู่ในรายงานเดิม

รันจากราก repository ด้วย environmentวิจัยเดิม:

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/verify_timed_fire_benchmark.py
backend/.venv-research/Scripts/python -X utf8 backend/scripts/predict_timed_fire_candidate.py --case 2026-03-27 --output output/fire-perimeter-loop-20261017/offline-example.npz
backend/.venv-research/Scripts/python -X utf8 backend/scripts/predict_timed_fire_candidate.py --case 2026-03-27 --family dense20m --output output/fire-perimeter-loop-20261017/offline-example-20m.npz
```

ตัวทำนายโหลดเฉพาะ initialarraysที่ระบุชื่อไว้ ไม่อ่าน finalimage/target/futurecloudmask การรันนี้เป็น historical replayบนข้อมูลที่เก็บไว้ ไม่ใช่การเชื่อมพยากรณ์สดกับเว็บ

![ผลทุกกรณี](all-test-comparison.png)

ภาพตัวอย่างเลือกจากกรณีหลักแรกตามลำดับและกรณีป่าชุมชนที่ระบุไว้ ไม่เลือกจากคะแนนสวย: สีส้ม=ทำนายอย่างเดียว, เขียว=อ้างอิงอย่างเดียว, ม่วง=ทับกัน, น้ำเงิน=รอยเริ่มต้น, เทา=ไม่ประเมิน

![ก่อนหลังและคำทำนายกรณีหลัก](2026-03-27-comparison.png)

![ก่อนหลังและคำทำนายกรณีป่าชุมชน](2026-04-15-community-cmf-th-2892-comparison.png)
'''
    (b.OUT/'FINAL_RESULTS_TH.md').write_text(text,encoding='utf8')
    summary=f'''# ผลทดลองที่ใช้ตัดสินใจได้

รอบทดลองเสร็จ:15กรณีภาพตามเวลา,67ตัวเลือก,ตรวจรันซ้ำผ่าน,ไม่มีdeploy

**เก็บโมเดลจัดลำดับ hotspot เดิมเป็นตัวหลักสำหรับเว็บ ส่วนเส้นไฟลามยังไม่พร้อมใช้เป็นคำทำนายที่เชื่อถือได้**

| สิ่งที่ถาม | คำตอบจากการทดลอง |
|---|---|
| 36%คืออะไร | ครอบคลุมช่อง hotspotใน12ชม.ถัดไป36.07%เมื่อให้เฝ้า250ตร.กม./รอบ เทียบฐาน28.44% ยังพลาด63.93% |
| ช่วยป่าชุมชนไหม | มีหลักฐานช่วยเลือกช่องเฝ้าระวัง แต่ยังไม่พิสูจน์ว่าลดความเสียหายจริง บริเวณป่าชุมชน+1กม.ครอบคลุม57.89%เทียบฐาน55.06% คนละตัวหารกับ36% |
| แนวไฟลามแม่นไหม | ตัวเลือกที่เลือกจากปี2025ได้ Diceพื้นที่ไหม้ใหม่{chosen['pooled_dice']*100:.2f}%ใน8กรณีหลักปี2026 ทายพื้นที่เกินมาก ยังไม่พร้อม |
| ลองปรับจริงหรือยัง | ลองเชื้อเพลิง/ความชื้น/ลม/ภาพเริ่มต้น/PM และโมเดล20ม.แล้ว รวม67แบบ ยังไม่พบตัวที่สมควรนำเส้นไฟลามขึ้นเว็บ |
| โลกมีเกิน80%ไหม | มีงานรายงาน85.1%Diceในเงื่อนไขเฉพาะ แต่คนละข้อมูล/วิธีวัด/การตั้งต้นรายวัน เปรียบตรงกับ36%ไม่ได้ |
| ผู้ใช้ต้องทำอะไรตอนนี้ | ไม่มีข้อมูลหรืออนุมัติที่ต้องส่งเพิ่มสำหรับรอบนี้ โมเดลและผลรันอยู่ในเครื่อง ยังไม่เปลี่ยนเว็บ |

รอยอ้างอิงรอบใหม่เป็นการเปลี่ยนภาพ Sentinel-2ใน2–5วัน ไม่ใช่ขอบไฟสำรวจหรือผลแนวไฟ12ชม. ตัวเลขทั้งหมดเป็นการทดสอบย้อนหลัง ไม่ใช่คะแนนรับรองระบบสด

ดูรายละเอียด ตัวเลขป่าชุมชน ลม/ฝุ่น วิธีปรับต่อ แหล่งอ้างอิง และคำสั่งรันซ้ำใน [รายงานเต็ม](FINAL_RESULTS_TH.md)
'''
    (b.OUT/'SUMMARY_TH.md').write_text(summary,encoding='utf8')
    scripts=['build_timed_fire_cases.py','discover_image_conditioned_cases.py','build_community_timed_cases.py','prepare_timed_fire_arrays.py',
             'timed_fire_spread_benchmark.py','timed_fire_growth_ml.py','timed_fire_growth_dense.py','timed_community_reference.py',
             'summarize_timed_fire_results.py','render_timed_fire_summary.py','predict_timed_fire_candidate.py','verify_timed_fire_benchmark.py','freeze_timed_fire_inputs.py','finalize_timed_fire_loop.py']
    receipt={'python':sys.version,'platform':platform.platform(),'packages':{name:version(name) for name in ('numpy','scipy','scikit-learn','joblib','shapely','pyproj','matplotlib')},
             'scripts':{name:hashlib.sha256((b.ROOT/'backend/scripts'/name).read_bytes()).hexdigest() for name in scripts}}
    b.write(b.OUT/'research-environment-final.json',receipt)
    decision={'status':'completed_offline_experiment_no_promotion','candidate_configurations':67,'validation_cases2025':4,'core_test_cases2026':8,'enriched_test_cases2026':3,
              'selected_growth_on2025':comparison['choices_frozen_from2025']['selected_overall'],
              'growth_core_dice':chosen['pooled_dice'],'priority_candidate':'output/joint-fire-model-20261017/final-candidate/model.joblib',
              'priority_target':'Next12hVIIRS500mcellrankingatfixedarea;notphysicalfireperimeter',
              'priority_coverage_at250km2':6988/19372,'deploy_growth':False,'production_changed':False,'deployment_commands_issued':0,
              'limitation':'Best among finite tested choices, not a claim of global optimum. Small retrospective opticalcohort and reused2026design feedback.'}
    b.write(b.OUT/'MODEL_DECISION.json',decision)
    (b.OUT/'ENGINEERING_LOG.md').write_text('''# Engineering loop completed

See SUMMARY_TH.md, FINAL_RESULTS_TH.md and MODEL_DECISION.json for the final measured decision.

- 15 time-matched C1 cases, 4 spatially disjoint 2025 validation cases, 8 original 2026 cases, 3 enriched community cases; excluded retrievals retained.
- 67 candidate configurations across physical propagation, initial-state ML and a separate 20m resolution iteration. Choices/thresholds selected on 2025 only. Round2 designed after round1 test inspection, explicitly reused retrospective2026, not a new holdout.
- Frozen97sourcefiles plus separate20mselection/weight hashes. Actual 2–5day optical changes, not invented12hperimeters.
- Real oldCOGdouble-offset and fractional-hour solver bugs corrected with numerical fixtures. All inference replays use whitelisted initial inputs and no future labels/cloud masks; future PM removal leaves features unchanged.
- 677forestpolygon intersections, uniondeduplicatedforest-period portions, known-fire enriched cohort separately reported.
- Verification passed. Six frozen production files unchanged, no deploy. Existing hotspot priority candidate retained; new perimeter candidates not promoted.
- Final reports, before/after maps, all-case charts, native inference CLI and environment/source-code hashes saved.
''',encoding='utf8')
    print('FINAL_REPORTS_READY',b.OUT/'SUMMARY_TH.md',b.OUT/'FINAL_RESULTS_TH.md')


if __name__=='__main__':
    main()
