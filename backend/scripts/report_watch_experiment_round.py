"""Collect this offline round into one short Thai result and audit manifest."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/watch-budget-20261017'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    watch = read(OUT / 'summary.json')
    scoped_root = ROOT / 'output/community-cell-model-20261017'
    scoped = read(scoped_root / 'decision.json')
    regional = scoped['test']
    region_selection = read(scoped_root / 'selection.json')
    area_root = ROOT / 'output/community-model-20261017'
    area = read(area_root / 'FINAL_DECISION.json')
    scars = read(OUT / 'scar-agreement/summary.json')
    parent_at250 = next(row for row in watch['scopes']['community_forest_plus_1km']['curves'] if row['requested_area_km2'] == 250)
    assert regional['target_cell_periods'] == watch['scopes']['community_forest_plus_1km']['target_cell_periods'] == 3807
    assert abs(regional['models']['parent']['250']['coverage_pct'] - parent_at250['coverage_pct']['candidate']) < 1e-10
    # Keep both selection records and all test scores; never switch to a test winner.
    chosen = scoped['selected_on2025']
    global_area80 = watch['province_minimum_fixed_area_for_80pct_retrospective']['candidate']
    report = f'''# สรุปภาษาคน: ผลทดลองเพิ่ม17ตุลาคม2026

**โมเดลเดิมยังเป็นตัวที่เลือกได้ดีที่สุดในชุดทดลองสำหรับทายช่องhotspot รอบนี้ยังไม่พบโมเดลใหม่ที่ให้เหตุผลพอจะเปลี่ยนขึ้นเว็บ** ทดลองเสร็จและเก็บหลักฐานครบในเครื่อง ไม่มีdeploy

## ทำเพิ่มแล้วอะไรบ้าง

- วัดโมเดลเดิมครบ231รอบ โดยเปลี่ยนพื้นที่เฝ้าระวัง11ขนาด ตั้งแต่5ถึง8,000ตร.กม. ผลที่250ตร.กม.ตรงกับรายงานเดิมทุกจำนวน
- แยกการทดลองเฉพาะป่าชุมชน677ขอบเขตและบริเวณรอบขอบเขต1กม. และทดลองเลือกเป็นรายป่าตามจำนวน/ตามพื้นที่รวม
- ฝึกโมเดลใหม่4ตัว: เรียนรู้รายป่า2ตัว และเรียนรู้เฉพาะช่องบริเวณป่าชุมชนอีก2ตัว ใช้hotspot+ลม+PMและบริบทเดิม
- เปรียบเทียบ12วิธีจัดลำดับรายป่า โดยบังคับงบพื้นที่เท่ากัน เลือกด้วยปี2025ก่อนประเมิน2026
- ดาวน์โหลดและตรวจรอยไหม้อิสระจากSentinel2 B4ครบ173ไฟล์ตามรายการจริง เทียบได้16สัปดาห์
- แพ็กโมเดลและวิธีเลือกไว้ทดลองออฟไลน์ ตรวจว่าตัดhotspot/PMในอนาคตออกแล้วfeaturesไม่เปลี่ยน และบล็อกฟังก์ชันอ่านคำตอบขณะทำนาย ผลยังรันได้

## 36%น่าพอใจหรือไม่

ที่เลือก250ตร.กม.ต่อรอบ โมเดลครอบคลุมช่องhotspotใน12ชั่วโมงถัดไปได้36.07% เทียบวิธีฐาน28.44% นี่เป็นส่วนเพิ่มที่วัดได้ แต่ยังไม่ใช่ความแม่นของแนวไฟลามจริง

เมื่อเลือก500ตร.กม.ได้48.99%; ถ้าจะให้ครอบคลุม80%ต้องเลือกประมาณ{global_area80:,.2f}ตร.กม.ต่อรอบในชุดทดสอบนี้ ดังนั้นเปอร์เซ็นต์ต้องมาพร้อมพื้นที่ที่ต้องเฝ้าระวัง ไม่ใช่ไล่80%เพียงตัวเดียว

## ใกล้ป่าชุมชนโดยเฉพาะ

เมื่อเลือกเฉพาะช่องในป่าชุมชนรวมbuffer1กม. ใช้พื้นที่250ตร.กม.เท่ากัน:

| วิธี | ครอบคลุมช่องที่พบhotspotภายหลัง |
|---|---:|
'''
    for name, values in regional['models'].items():
        label = {'parent': 'โมเดลเดิม', 'kernel': 'วิธีฐานที่ปรับด้วย2025เดิม',
                 'scoped_hgb_small': 'โมเดลฝึกเฉพาะพื้นที่ชุดเล็ก', 'scoped_hgb_large': 'โมเดลฝึกเฉพาะพื้นที่ชุดใหญ่'}[name]
        report += f"| {label}{' — เลือกด้วย2025' if name == chosen else ''} | {values['250']['coverage_pct']:.2f}% |\n"
    report += f'''
ตัวเลขนี้เปลี่ยนขอบเขตและตัวหารเป็นเฉพาะบริเวณป่าชุมชน จึงไม่ได้แปลว่าโมเดลพัฒนาจาก36%เป็นคะแนนนี้ และbuffer1กม.เป็นระยะสมมติสำหรับทดลอง ยังไม่ใช่ระยะที่รับรองว่าไฟจะเข้าป่า

การเลือกเป็นรายป่าเต็มขอบเขตเป็นอีกโจทย์หนึ่ง วิธีที่เลือกด้วย2025ได้{area['selected_test_at250']['coverage_pct']:.2f}% เทียบวิธีฐานที่ปรับตามขนาดพื้นที่แล้ว{area['kernel_test_at250']['coverage_pct']:.2f}% ในปี2026 ที่250ตร.กม.เท่ากัน ผลยังสูสีกัน ช่วงความไม่แน่นอนของผลต่างคร่อมศูนย์ จึงไม่กล่าวว่ามีโมเดลใหม่ชนะวิธีฐานชัดเจน

## ตรวจรอยไหม้จริงจากเซนเซอร์อีกชนิดแล้วได้อะไร

ที่เลือก250ตร.กม.ในเวลาเริ่มแต่ละสัปดาห์ โมเดลครอบคลุมรอยไหม้ที่เพิ่งตรวจพบในชุดข้อมูล{scars['pooled']['candidate']['250']['first_observed_scars']['observed_scar_coverage_pct']:.2f}% เทียบวิธีฐาน{scars['pooled']['kernel']['250']['first_observed_scars']['observed_scar_coverage_pct']:.2f}% ผลความสอดคล้องนี้ยังต่ำ และไม่ใช่คะแนนทำนายไฟลาม12ชั่วโมง เพราะข้อมูลรอยไหม้รวมทั้งสัปดาห์ บางรอยอาจไหม้ก่อนออกผลหรือหลายวันหลังช่วงทำนาย และมีบางสัปดาห์ที่ภาพครอบคลุมพื้นที่น้อย

จึงยังยืนยันไม่ได้ว่าเว็บทายแนวไฟลามจริงแม่นเท่าไร ข้อมูลรอยไหม้และเครื่องมือเทียบพื้นที่พร้อมแล้ว แต่การวัดแนวไฟลาม12ชั่วโมงยังต้องใช้ภาพก่อน–หลังที่มีเวลาชัดและคุณภาพเหมาะสม ข้อมูลรายสัปดาห์ครั้งนี้ใช้แทนไม่ได้

## ผลที่นำไปใช้ตัดสินใจได้ตอนนี้

มีหลักฐานย้อนหลังว่าโมเดลเดิมช่วยจัดลำดับช่องที่ควรเฝ้าระวังได้ดีกว่าวิธีฐานในโจทย์เดิม ส่วนการจัดลำดับรายป่ายังไม่แสดงส่วนเพิ่มชัดเจน และยังไม่มีผลรับรองแนวไฟลามหรือผลลดความเสียหายป่า ปี2026เคยถูกดูจากงานก่อน ผลทั้งหมดจึงเป็นการเปรียบเทียบย้อนหลัง ไม่ใช่ฤดูทดสอบใหม่ที่ไม่เคยเห็น

คงโมเดลเดิมไว้เป็นตัวหลักสำหรับทดลอง เก็บตัวเลือกใหม่พร้อมผลแพ้/ชนะทั้งหมด ไม่มีการสลับผู้ชนะตามคะแนนปี2026 ไม่เปลี่ยนหน้าเว็บ ไม่ส่งแจ้งเตือน และไม่deploy

## เปิดหลักฐาน

- [ผลพื้นที่เตือนและรอยไหม้ฉบับเต็ม](RESULTS_TH.md)
- [ผลโมเดลและนโยบายรายป่า](../community-model-20261017/RESULTS_TH.md)
- [ตัวเลขโมเดลเฉพาะพื้นที่](../community-cell-model-20261017/decision.json)
- [กราฟพื้นที่เตือนเทียบการครอบคลุม](coverage-area.png)
- [การตรวจสอบGISและการรันซ้ำ](verification.json)
- [การตรวจการทำนายโดยไม่อ่านคำตอบ](../community-model-20261017/verification.json)
'''
    (OUT / 'SUMMARY_TH.md').write_text(report, encoding='utf8')
    scoped_report = f'''# โมเดลเฉพาะพื้นที่ป่าชุมชน

เลือกด้วย2025: {chosen} จากตัวเลือก parent/kernel/scoped_hgb_small/scoped_hgb_large

ฝึก2024ด้วยแถวเดิมที่อยู่เฉพาะขอบเขตป่าชุมชน+1กม. ไม่ฝึกจาก2025หรือ2026 ผล2025อยู่selection.json ผล2026ทั้งหมดอยู่decision.json

ผล2026ที่250ตร.กม.ในขอบเขตเดียวกัน:

'''
    for name, values in regional['models'].items():
        scoped_report += f"- {name}: {values['250']['hits']}/{regional['target_cell_periods']} = {values['250']['coverage_pct']:.2f}%\n"
    scoped_report += '\nไม่เปลี่ยนผู้ชนะที่เลือกจาก2025เพื่อเอาตัวที่2026สูงกว่า เป้าหมายคือช่องhotspot12ชม. ไม่ใช่ขอบไฟลาม ปี2026เป็นการเปรียบเทียบย้อนหลังที่เคยถูกดูแล้ว ไม่deploy\n'
    (scoped_root / 'RESULTS_TH.md').write_text(scoped_report, encoding='utf8')
    labels = list(regional['models'])
    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False})
    figure, axis = plt.subplots(figsize=(8.5, 4.3), layout='constrained')
    axis.bar(['Scoped HGB small', 'Scoped HGB large', 'Frozen parent', 'Tuned baseline'],
             [regional['models'][name]['250']['coverage_pct'] for name in labels],
             color=['#a8b9c5', '#a8b9c5', '#00796b', '#c57028'])
    axis.set(ylim=(0, 75), ylabel='Future VIIRS target cells covered (%)',
             title='Community forests + 1 km: same 250 km² selected area')
    for i, name in enumerate(labels):
        value = regional['models'][name]['250']['coverage_pct']
        axis.text(i, value + 1.2, f'{value:.2f}%', ha='center')
    figure.savefig(OUT / 'community-cell-comparison.png', dpi=180)
    plt.close(figure)
    sources = {}
    for path in (ROOT / 'backend/scripts').glob('*.py'):
        if path.name in ('evaluate_watch_budget.py', 'evaluate_weekly_scar_agreement.py', 'evaluate_community_alerts.py',
           'train_community_watch_model.py', 'evaluate_community_area_budget.py', 'compare_community_cell_models.py',
           'finalize_community_watch.py', 'predict_community_watch.py', 'verify_watch_evaluation.py',
           'verify_community_watch.py', 'report_watch_evaluation.py', 'report_watch_experiment_round.py'):
            sources[str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'analysis-code-sha256.json').write_text(json.dumps(sources, indent=2), encoding='utf8')
    print('FINAL OFFLINE ROUND:', OUT / 'SUMMARY_TH.md')


if __name__ == '__main__':
    main()
