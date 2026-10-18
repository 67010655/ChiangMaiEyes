"""Package measured results only. No estimator dependencies in production."""
import hashlib,json
from pathlib import Path
from priority_forecast_experiment import ROOT,OUT,read,write

def main():
    summary=read(OUT/'summary.json');robust=read(OUT/'robustness.json');community=read(OUT/'community-subgroup.json')
    baseline=next(iter(robust['test']['hits']));n=summary['test']['target_cells_all'];rows=[]
    for budget in ('125.0','250.0','500.0'):
        ml=summary['test']['hits'][summary['selected']][budget];old=robust['test']['hits'][baseline][budget]
        rows.append({'alert_area_km2':float(budget),'target_cell_periods':n,'model_hits':ml,'baseline_hits':old,
          'model_coverage_pct':100*ml/n,'baseline_coverage_pct':100*old/n,'gain_percentage_points':100*(ml-old)/n,
          'relative_more_detected_cells_pct':100*(ml-old)/old,
          'model_selected_cell_periods_with_detection_pct':100*ml/(summary['test']['issues']*float(budget)/.25)})
    sources=[]
    for p in [OUT/'protocol.json',OUT/'selection.json',OUT/'boost15.joblib',OUT/'training2024.npz',
        OUT/'kernel-selection.json',OUT/'test2026.json',OUT/'kernel-test2026.json',OUT/'community-subgroup.json']:
        sources.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    report={'schema':'cme-priority-validation-v1','mode':'historical_replay_only','model':'HistGradientBoosting60trees15leaves',
      'protocol':summary['protocol'],'primary_budget_km2':250,'issues':summary['test']['issues'],'comparison':rows,
      'baseline':{'method':'Maximum recency-distance kernel over8nearest past24h points','config_selected_on2025':robust['baseline_config'],'tested_baseline_configs':18},
      'uncertainty':robust['paired_day_bootstrap'],'community_subgroup':{k:v for k,v in community.items() if k!='rows'},
      'examples':read(OUT/'examples.json'),'source_fingerprints':sources,
      'notes_th':['คะแนนนี้วัดการเลือกช่อง500เมตรที่ดาวเทียมจะตรวจพบจุดความร้อนใน12ชั่วโมงถัดไป ไม่ใช่ความแม่นของขอบไฟลาม',
        'ฝึกปี2024 เลือกโมเดลและวิธีฐานปี2025 ตรวจปี2026 รวม237รอบ ใช้ข้อมูลจุดความร้อนก่อนเวลาออกผลอย่างน้อย3ชั่วโมง',
        'ทั้งรุ่นใหม่และวิธีฐานเลือกพื้นที่ขนาดเท่ากันทุกครั้ง ช่องที่ไม่ถูกเลือกยังมีโอกาสเกิดไฟ',
        'ใช้ดาวเทียมหลายดวงและข้อมูลอากาศGFSย้อนหลังแบบprevious-day1 ไม่ใช่คลังการรับข้อมูลจริงณเวลานั้น',
        'ปี2026เคยถูกตรวจในงานอื่นแล้ว ผลนี้เป็นการทดสอบย้อนหลังข้ามปี ต้องเก็บผลที่ออกจริงเพื่อตรวจฤดูถัดไป',
        'คะแนนของโมเดลใช้จัดลำดับ ไม่ใช่เปอร์เซ็นต์โอกาสเกิดไฟที่สอบเทียบแล้ว การไม่พบจุดความร้อนไม่ยืนยันว่าไม่มีไฟ',
        'แผนที่เป็นตัวอย่างย้อนหลังสามวันตามปฏิทิน ป่าชุมชนเรียงตามพื้นที่เฝ้าระวังที่ซ้อนในระยะ1กม. ไม่ใช่คำสั่งส่งคนดับไฟ',
        'ข้อมูลสิ่งปกคลุมดินESAWorldCover2021และความสูงCopernicusDEMยังมีข้อจำกัดเรื่องความละเอียดและความเปลี่ยนแปลงของป่า']}
    target=ROOT/'backend/app/data/priority-validation.json';write(target,report);print('artifact',target.stat().st_size,flush=True)
    mainrow=rows[1];sub=report['community_subgroup'];total=sub['target_cells_near_forests']
    text=f'''# ผลพัฒนาพื้นที่เฝ้าระวัง 12 ชั่วโมง — 17 ตุลาคม 2026

## ผลที่ได้จริง

ใช้ข้อมูลจุดความร้อน ม.ค.–เม.ย. 2024 จำนวน36,396จุด และ2025 จำนวน14,313จุดเพิ่มจาก2026 จำนวน32,376จุด (รวมทุกระดับความเชื่อมั่นก่อนคัดกรอง) ฝึกจาก2024 เลือกหนึ่งใน3โมเดลด้วย2025 แล้วทดสอบกับ2026เท่านั้น ไม่ปรับค่ารุ่นตามผล2026

งานที่ทดสอบคือเลือกช่อง500เมตรเพื่อเฝ้าระวังจุดที่ดาวเทียมจะตรวจพบใน12ชั่วโมงถัดไป ออกผล08:00/20:00ICT สมมติข้อมูลเข้าใช้ได้ช้ากว่าเวลาตรวจ3ชั่วโมง ใช้ข้อมูลnominal/high รวม237รอบ และ{n:,}ช่อง-รอบที่มีการตรวจพบจริง

| พื้นที่เฝ้าระวังต่อรอบ | วิธีฐานที่ปรับจาก2025 | โมเดลใหม่ | เพิ่มเป็นจุดเปอร์เซ็นต์ |
|---|---:|---:|---:|
'''
    for r in rows:text+=f"| {r['alert_area_km2']:.0f}ตร.กม. | {r['baseline_coverage_pct']:.1f}% | {r['model_coverage_pct']:.1f}% | +{r['gain_percentage_points']:.1f} |\n"
    text+=f'''
ที่250ตร.กม. วิธีฐานพบ{mainrow['baseline_hits']:,}/{n:,}ช่อง-รอบ รุ่นใหม่{mainrow['model_hits']:,}/{n:,} หรือเพิ่ม{mainrow['relative_more_detected_cells_pct']:.1f}%ในเชิงจำนวนที่ครอบคลุมได้ พื้นที่แจ้งรวมเท่ากัน ได้เพิ่มด้วยการจัดลำดับ ไม่ใช่ขยายพื้นที่แจ้งเตือน ช่วงความไม่แน่นอน95%จากการสุ่มซ้ำแบบบล็อก7วันของผลเพิ่มเทียบวิธีฐานคือ{robust['paired_day_bootstrap']['moving_block7day_gain_pp_vs_tuned_kernel_95pct'][0]:.2f}–{robust['paired_day_bootstrap']['moving_block7day_gain_pp_vs_tuned_kernel_95pct'][1]:.2f}จุดเปอร์เซ็นต์

วิธีฐานค้น18ชุดค่าบน2025ก่อนเลือก500m/24h/noFRP แล้วประเมิน2026เพียงชุดที่เลือก รุ่นใหม่จึงไม่ได้เทียบแค่วิธีฐานที่ตั้งค่าอ่อนๆ

## ประโยชน์ต่อป่าชุมชน

ตรวจกลุ่มย่อยช่องที่ศูนย์กลางอยู่ภายใน1กม.จากขอบเขตป่าชุมชน677ขอบเขต: พบจุดความร้อน{total:,}ช่อง-รอบ วิธีดูจุด24ชม.ล่าสุดครอบคลุม{sub['baseline_hits_near_forests']:,}ช่อง-รอบ รุ่นใหม่{sub['ml_hits_near_forests']:,}ช่อง-รอบ ({100*sub['baseline_hits_near_forests']/total:.1f}% → {100*sub['ml_hits_near_forests']/total:.1f}%) ข้อเปรียบเทียบกลุ่มย่อยนี้ใช้วิธีฐานเดิมday ไม่ใช่kernelที่ปรับ18ชุด คะแนนข้างป่าไม่ใช่ไฟที่ยืนยันภายในป่า และพื้นที่แจ้งที่ซ้อนกลุ่มย่อยอาจต่างกัน แม้รวมจังหวัดเท่ากัน

ส่งออกตัวอย่าง15มี.ค.,15เม.ย.,30เม.ย.08:00 พร้อมพื้นที่เลือก250ตร.กม. จุดตรวจภายหลัง และรายชื่อป่าชุมชนที่มีพื้นที่เลือกใกล้ขอบเขต เพื่อเปิดตรวจบนเว็บ ผลเป็นhistorical replay ยังไม่ได้แทนพยากรณ์สดด้วยโมเดลนี้

## ข้อจำกัดที่มีผลต่อการใช้

- ครอบคลุม35.0%หมายถึงยังพลาดประมาณ65%ของช่องที่พบจุดความร้อนในรอบถัดไป จึงช่วยจัดลำดับพื้นที่เฝ้าระวัง ไม่ควรใช้ตัดสินว่าพื้นที่อื่นปลอดภัย
- ช่องที่ถูกเลือกแล้วมีจุดดาวเทียมภายหลังคิดเป็น{mainrow['model_selected_cell_periods_with_detection_pct']:.2f}%ของช่อง-รอบที่เลือกทั้งหมด การไม่พบจุดดาวเทียมยังเรียกว่าไม่มีไฟหรือเตือนผิดไม่ได้ ผลนี้ไม่พิสูจน์ว่า250ตร.กม.เป็นภาระงานที่ชุมชนรับไหว
- ไม่มีเปอร์เซ็นต์accuracyรวมของเว็บ และไม่ได้วัดขอบไฟจริง การลามจากไฟเดิมแยกจากจุดติดไฟใหม่ยังไม่ได้ติดป้ายในข้อมูลนี้
- โมเดลใช้ภูมิประเทศ ที่ตั้ง สิ่งปกคลุมดิน ระยะ/จำนวน/อายุ/FRPของจุดย้อนหลัง และอากาศGFSระดับจุดจังหวัด การทดลองนี้ยังไม่ได้แยกว่าส่วนไหนทำให้ผลดีขึ้น จึงไม่อ้างว่าการเติมข้อมูลลมเพียงอย่างเดียวทำให้ดีขึ้น
- มีข้อมูลอากาศ2024ต้นม.ค.ขาด444ชั่วโมง จึงข้ามรอบฝึกที่ข้อมูลไม่ครบ ไม่มีการเติมด้วยศูนย์
- ประวัติก่อน1ม.ค.ไม่ได้โหลดเข้าการทดลอง จึงมีช่วงต้นฤดูที่ประวัติ7/30วันยังไม่ครบ ใช้เงื่อนไขเดียวกันทุกวิธี
- SPเวลาเก็บภาพ+3ชั่วโมงเป็นสมมติฐานavailability และGFSprevious-day1เป็นforecastย้อนหลังที่ประกอบตามชั่วโมง ไม่ใช่การพิสูจน์ว่าไฟล์จริงพร้อมใช้ณเวลาออกผล
- ทดสอบย้อนหลังในปีที่เคยดูจากงานอื่น ช่วงความไม่แน่นอนอธิบายการสุ่มในฤดูนี้ ไม่ใช่การรับรองฤดูใหม่

## เปิดโมเดลโอเพนซอร์สมาทดลองจริงแล้ว

ทดลองPyretechnicsที่ตรึงcommit a811ae508a5d7eeebb808b156e0e2066d4445602 กับ1h/10h/100hเชื้อเพลิง และตัวคำนวณความชื้นตามอุณหภูมิ/RH/ฝนแบบWRFx(ไม่ใช่Nelson) เปรียบเทียบตัวคำนวณความชื้น48ขั้นกับโค้ดต้นฉบับแล้วคลาดเคลื่อนต่ำกว่า1e-12

บน35กรณีเดิม/411จุด: FM1ความชื้นเปลี่ยนตามอากาศครอบคลุมกรอบไม่เผื่อระยะ51จุดเทียบเดิม46จุด แต่เมื่อเผื่อ375เมตรได้354เท่ากัน และวิธีวงรอบพื้นที่เท่ากันได้354เช่นกัน การแทนพื้นที่ป่าด้วยFM9/พุ่มด้วยFM5ครอบคลุมน้อยลง จึงยังไม่มีเหตุให้แทนไฟลามบนเว็บด้วยชุดนั้น นี่เป็นpilotที่ยังมีข้อจำกัดsame-pass/availabilityเดิม ไม่ใช้เป็นหลักฐานaccuracyจริง

ทางต่อที่มีเหตุผลคือเพิ่มภาพSentinel-2ก่อนเวลาออกผลเพื่อแยกความแห้ง/รอยไหม้ล่าสุด และทดลองWindNinjaสำหรับลมตามภูเขา ข้อมูลหน้างานเป็นส่วนเสริมเพื่อปรับความไม่แน่นอน ไม่ใช่เงื่อนไขว่าต้องรอก่อนเริ่มพัฒนา

ดูรายละเอียดเครื่องมือและแหล่งต้นทางใน[บันทึกวิจัย](../../docs/research/2026-10-17-open-source-next-improvements.md) และprotocol/source_fingerprintsในartifact
'''
    (OUT/'RESULTS.md').write_text(text,encoding='utf8')
if __name__=='__main__':main()
