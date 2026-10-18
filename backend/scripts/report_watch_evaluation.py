"""Create local research figures and a Thai interpretation of frozen replay."""
import csv
import importlib.metadata
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/watch-budget-20261017'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    summary = read(OUT / 'summary.json')
    protocol = read(OUT / 'protocol.json')
    verification = read(OUT / 'verification.json')
    scars = read(OUT / 'scar-agreement/summary.json')
    acquisition_coverage = [100 * row['acquisition_covered_candidate_area_km2'] / row['candidate_area_km2'] for row in scars['rows']]
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.7), layout='constrained')
    scopes = [('province_candidates', 'All province candidates'),
              ('community_forest_plus_1km', 'Community forests + 1 km (pooled)')]
    for axis, (scope_name, title) in zip(axes, scopes):
        scope = summary['scopes'][scope_name]
        curves = [row for row in scope['curves'] if row['requested_area_km2'] <= scope['candidate_area_km2']]
        x = [row['actual_selected_area_km2'] for row in curves]
        for name, label, color in [('candidate', 'Frozen candidate', '#00796b'), ('kernel', 'Tuned baseline', '#c57028')]:
            axis.plot(x, [row['coverage_pct'][name] for row in curves], marker='o', markersize=4, label=label, color=color)
        axis.fill_between(x, [row['coverage_pct_95'][0] for row in curves], [row['coverage_pct_95'][1] for row in curves], color='#00796b', alpha=.12, label='Candidate block 95% interval')
        axis.axhline(80, linestyle=':', color='#687786', linewidth=1)
        at250 = next(row for row in curves if row['requested_area_km2'] == 250)
        axis.annotate(f"250 km²: {at250['coverage_pct']['candidate']:.1f}%", (250, at250['coverage_pct']['candidate']), xytext=(10, -23), textcoords='offset points', fontsize=10, color='#005e54')
        axis.set(xscale='log', ylim=(0, 100), title=title, xlabel='Selected area per issue (km², log scale)', ylabel='Future VIIRS target cells covered (%)')
        axis.grid(alpha=.18)
        axis.legend(loc='upper left', fontsize=8)
    figure.suptitle('Same frozen model: coverage increases when the alert area grows', fontsize=14)
    figure.savefig(OUT / 'coverage-area.png', dpi=180)
    figure.savefig(OUT / 'coverage-area.svg')
    plt.close(figure)
    with (OUT / 'coverage-area.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(['scope', 'requested_area_km2', 'actual_area_km2', 'candidate_coverage_pct', 'kernel_coverage_pct', 'gain_pp', 'candidate_low95', 'candidate_high95'])
        for name, scope in summary['scopes'].items():
            for row in scope['curves']:
                writer.writerow([name, row['requested_area_km2'], row['actual_selected_area_km2'], row['coverage_pct']['candidate'], row['coverage_pct']['kernel'], row['gain_pp'], *row['coverage_pct_95']])
    figure, axis = plt.subplots(figsize=(10, 4.4), layout='constrained')
    dates = [row['start_date'][4:6] + '/' + row['start_date'][6:] for row in scars['rows']]
    locations = np.arange(len(dates))
    for name, offset, color in [('candidate', -.19, '#00796b'), ('kernel', .19, '#c57028')]:
        values = [row['models'][name]['250']['first_observed_scars']['observed_scar_coverage_pct'] for row in scars['rows']]
        axis.bar(locations + offset, [v if v is not None else 0 for v in values], width=.36, label=name, color=color)
    axis.set_xticks(locations, dates, rotation=45)
    axis.set(xlabel='Weekly composite start (MM/DD, 2026)', ylabel='First-observed weekly scar area covered (%)',
             title='Independent-sensor spatial diagnostic at 250 km² per issue')
    axis.text(.5, -.32, 'Weekly Sentinel-2 scars versus a 12-hour forecast footprint: NOT fire-spread accuracy.', transform=axis.transAxes, ha='center', fontsize=10, color='#754a36')
    axis.legend()
    figure.savefig(OUT / 'weekly-scar-diagnostic.png', dpi=180, bbox_inches='tight')
    plt.close(figure)
    province = summary['scopes']['province_candidates']
    community = summary['scopes']['community_forest_plus_1km']
    inside = summary['scopes']['community_forest_centres']
    row250 = next(row for row in province['curves'] if row['requested_area_km2'] == 250)
    near250 = next(row for row in community['curves'] if row['requested_area_km2'] == 250)
    area80 = summary['province_minimum_fixed_area_for_80pct_retrospective']
    report = f'''# ผลทดสอบความคุ้มของพื้นที่เฝ้าระวังและข้อมูลรอยไหม้อิสระ

สถานะ: ทดลองในเครื่อง ไม่เปลี่ยนโมเดลหรือหน้าเว็บ ไม่ deploy

## คำตอบสำหรับผู้ใช้

โมเดลช่วยจัดลำดับพื้นที่เฝ้าระวังได้ดีกว่าวิธีฐาน แต่ผลนี้ยังไม่ใช่ความแม่นของแนวไฟลามจริง คะแนนต้องอ่านคู่กับขนาดพื้นที่ที่เลือก: โมเดลเดิมได้36.07%เมื่อเลือก250ตร.กม. และถึง80%ได้โดยขยายพื้นที่เป็นประมาณ{area80['candidate']:,.2f}ตร.กม.ต่อรอบ จึงไม่ควรใช้80%เป็นเป้าหมายเดี่ยว

## วิธีทดสอบ

- ใช้โมเดลที่เลือกด้วยปี2025เดิม ไม่ฝึกใหม่ ไม่เลือกโมเดลหรือ threshold จากคะแนน2026
- ประเมิน231รอบเวลา08/20น.ไทย มกราคม–เมษายน2026 มีเป้าหมาย19,372ช่อง-รอบ ที่ดาวเทียมVIIRSพบจุดความร้อนใน12ชั่วโมงถัดไป
- เป้าหมายไม่ใช่จำนวนเหตุไฟหรือพื้นที่ไหม้จริง และไม่ได้พิสูจน์ว่า hotspot แต่ละจุดเป็นไฟป่า
- พื้นที่ตัวเลือก500เมตรรวม21,634ตร.กม. ไม่ใช่การวัดพื้นที่จังหวัดอย่างเป็นทางการ มี103ช่อง-รอบเป้าหมายอยู่นอก candidate mask; ตัวหารจังหวัดรวมไว้ให้ตรงรายงานเดิม
- ปี2026เคยถูกดูในงานก่อน จึงเป็นการทดสอบย้อนหลัง ไม่ใช่ฤดูใหม่ที่ไม่เคยเห็น
- ช่วงความไม่แน่นอนใช้ paired circular blocks ของ7วันออกผลที่มีข้อมูล จำนวน3,000ครั้ง ไม่ใช่การรับรองคะแนนในฤดูถัดไป

## พื้นที่เตือนมากขึ้น ครอบคลุมมากขึ้น

| พื้นที่ที่เลือกต่อรอบ ตร.กม. | โมเดลเดิม | วิธีฐาน | เพิ่มขึ้น จุดเปอร์เซ็นต์ |
|---:|---:|---:|---:|
'''
    for row in province['curves']:
        report += f"| {row['actual_selected_area_km2']:,.0f} | {row['coverage_pct']['candidate']:.2f}% | {row['coverage_pct']['kernel']:.2f}% | {row['gain_pp']:+.2f} |\n"
    report += f'''
ที่250ตร.กม. คะแนนโมเดลมีช่วง95%ประมาณ{row250['coverage_pct_95'][0]:.1f}–{row250['coverage_pct_95'][1]:.1f}% ส่วนที่เพิ่มจากวิธีฐานคือ{row250['gain_pp']:.2f}จุดเปอร์เซ็นต์ ช่วง95% {row250['gain_pp_vs_kernel_95'][0]:.2f}–{row250['gain_pp_vs_kernel_95'][1]:.2f}จุดเปอร์เซ็นต์

การกลับเส้นคะแนนย้อนหลังพบว่า80%ต้องเลือกประมาณ{area80['candidate']:,.2f}ตร.กม.สำหรับโมเดล และ{area80['kernel']:,.2f}ตร.กม.สำหรับวิธีฐาน ตัวเลขนี้เป็นคำอธิบายชุดทดสอบ ไม่ใช่งบพื้นที่ที่แนะนำหรือ threshold ที่ผ่านการทดสอบล่วงหน้า

![พื้นที่เตือนเทียบกับการครอบคลุม](coverage-area.png)

## เฉพาะป่าชุมชน

อ่านขอบเขตจริง{protocol['community']['polygon_count']}รูป มีรูปที่ต้องซ่อมความถูกต้องในหน่วยความจำ{protocol['community']['invalid_geometries_repaired_in_memory']}รูป ไม่แก้ไฟล์ต้นฉบับ

การทดลองสองขอบเขตต่อไปนี้กรองและจัดอันดับใหม่ในขอบเขตนั้น โดยใช้โมเดลเดิมทุกค่า พื้นที่250ตร.กม.เป็นงบรวมของป่าทั้งชุด ไม่ใช่ต่อป่า เป้าหมายก็เปลี่ยนเป็นเฉพาะช่องในขอบเขต จึงห้ามเรียกคะแนนที่สูงขึ้นว่าโมเดลพัฒนาจาก36%เป็นคะแนนนี้

| ขอบเขต | พื้นที่ช่องตัวเลือก ตร.กม. | เป้าหมายช่อง-รอบ | โมเดลเมื่อเลือก250ตร.กม. | วิธีฐาน |
|---|---:|---:|---:|---:|
'''
    for label, scope in [('ศูนย์กลางช่องอยู่ในป่าชุมชน', inside), ('ป่าชุมชนและระยะรอบขอบเขต1กม.', community)]:
        row = next(row for row in scope['curves'] if row['requested_area_km2'] == 250)
        report += f"| {label} | {scope['candidate_area_km2']:,.1f} | {scope['target_cell_periods']:,} | {row['coverage_pct']['candidate']:.2f}% | {row['coverage_pct']['kernel']:.2f}% |\n"
    report += f'''
บริเวณป่าชุมชนรวมรอบขอบเขต1กม. โมเดลดีกว่าวิธีฐาน{near250['gain_pp']:.2f}จุดเปอร์เซ็นต์ ช่วง95% {near250['gain_pp_vs_kernel_95'][0]:.2f}–{near250['gain_pp_vs_kernel_95'][1]:.2f}จุดเปอร์เซ็นต์ จึงมีหลักฐานว่าช่วยจัดลำดับได้ แต่ส่วนเพิ่มยังไม่มาก และยังไม่ได้วัดเวลาหรือจำนวนคนที่ประหยัดได้

## ตรวจด้วยรอยไหม้จากเซนเซอร์อีกชนิดแล้ว

ใช้[ตามรอยเผา B4 ของ HII/มหาวิทยาลัยเกษตรศาสตร์](https://tamroypao.hii.or.th/) ความละเอียด20เมตร จำนวน{scars['listed_files_used']}ไฟล์ตามรายการที่มีจริง ครบช่วงสัปดาห์ที่สิ้นสุดภายในเมษายน2026 เปรียบเทียบได้{scars['weeks_compared']}สัปดาห์ ใช้ forecast เวลา08น.ของวันเริ่มสัปดาห์ที่มีใน231รอบเดิม ข้ามสัปดาห์ที่ไม่มีรอบนั้น ไม่เลือกวันตามคะแนน

Band1คือจำนวนตรวจพบรอยไหม้ Band2คือจำนวนภาพที่ผ่าน ไม่ใช่จำนวนภาพไร้เมฆหรือหลักฐานว่าช่องที่ไม่พบรอยไหม้ไม่เคยไหม้ รวมพื้นที่ซ้ำระหว่างtileด้วยunionระดับ20เมตร ก่อนรวมเป็นช่อง500เมตร เก็บ acquisition coverage และ hash ไฟล์ทุกไฟล์

พื้นที่ที่มีข้อมูลภาพผ่านมีตั้งแต่{min(acquisition_coverage):.1f}%ถึง{max(acquisition_coverage):.1f}%ของช่องตัวเลือกต่อสัปดาห์ มี{sum(value < 50 for value in acquisition_coverage)}จาก{len(acquisition_coverage)}สัปดาห์ที่ต่ำกว่า50% การมีภาพผ่านก็ยังไม่ยืนยันว่าไร้เมฆ ตัดรอยไหม้ที่ไม่มีacquisitionกำกับออกอีก{sum(row['excluded_scar_without_acquisition_candidate_pixels'] for row in scars['rows']):,}พิกเซล20เมตร-สัปดาห์ จึงห้ามนำผลรวมไปอ้างว่ามีภาพตรวจครบทุกพื้นที่ทุกสัปดาห์

| เป้าหมายรอยไหม้รายสัปดาห์ ที่พื้นที่เลือก250ตร.กม. | โมเดลครอบคลุมรอยไหม้ที่ตรวจพบ | วิธีฐาน |
|---|---:|---:|
'''
    for target, label in [('all_observed_scars', 'รอยไหม้ทั้งหมดที่ตรวจพบในสัปดาห์'), ('first_observed_scars', 'เฉพาะพิกเซลที่ยังไม่พบในสัปดาห์ก่อนหน้าในชุดข้อมูล')]:
        candidate = scars['pooled']['candidate']['250'][target]
        baseline = scars['pooled']['kernel']['250'][target]
        report += f"| {label} | {candidate['observed_scar_coverage_pct']:.2f}% | {baseline['observed_scar_coverage_pct']:.2f}% |\n"
    report += '''
ตารางนี้เป็นการตรวจความสอดคล้องเชิงพื้นที่จากเซนเซอร์อีกชนิด ไม่ใช่คะแนนไฟลาม12ชั่วโมง สัปดาห์รวม8ชั่วโมงก่อนออกผลและอีกหลายวันหลังช่วงพยากรณ์ รอยไหม้อาจเก่าหรือเพิ่งเห็นหลังเมฆเปิด การตัดพิกเซลที่เคยพบในสัปดาห์ก่อนออกก็ไม่ทำให้ทราบวันไหม้จริง ผู้ให้ข้อมูลระบุว่ายังไม่ได้ประเมินความแม่นอย่างเป็นทางการสำหรับป่าและเรือนยอดอาจบังรอยไหม้

![ความสอดคล้องกับรอยไหม้รายสัปดาห์](weekly-scar-diagnostic.png)

## ผลต่อการพัฒนารอบถัดไป

1. ประเมินโมเดลด้วยพื้นที่เตือนเท่ากันและขอบเขตป่าชุมชนเดียวกันต่อไป ไม่เลือกผู้ชนะจากเปอร์เซ็นต์ที่เพิ่มเพราะเตือนกว้างขึ้น
2. ชุดรอยไหม้อิสระและเครื่องมือเทียบพื้นที่พร้อมรันแล้ว ใช้ตรวจจุดที่โมเดลพลาดและเทียบตัวเลือกใหม่ โดยต้องแยกข้อมูลเลือกโมเดลกับข้อมูลประเมิน
3. การวัดแนวไฟลามโดยตรงยังต้องมีขอบไฟจากภาพก่อน–หลังที่มีเวลาถ่ายชัดเจน ข้อมูลรายสัปดาห์ที่ทดสอบครั้งนี้ยังตอบความคลาดเคลื่อน12ชั่วโมงไม่ได้ ขั้นตอนต่อไปคือจับคู่ภาพSentinel2/Landsatและตรวจคุณภาพเมฆในกรณีที่มีภาพเหมาะสม ไม่ได้จำกัดว่าต้องมีการสำรวจหน้างานอย่างเดียว
4. ลมและPMมีอยู่ในโมเดล แต่ผลทดลองก่อนหน้ายังไม่แสดงว่าตัวแปรเหล่านั้นเพิ่มคะแนนชัดเจนด้วยตัวมันเอง จึงไม่กล่าวว่าการเพิ่มข้อมูลสองชนิดนี้แก้ข้อจำกัดแนวไฟลามแล้ว

## ตรวจสอบและไฟล์ส่งมอบ

- verification.json: ทดสอบตำแหน่งพิกเซล20ม.→500ม., union tileซ้ำ, พื้นที่พิกเซลที่ทราบคำตอบ และการไม่ตีความข้อมูลขาดเป็นไม่ไหม้ ผ่าน
- ผล231รอบตรงกับรายงานเดิมทุกจำนวนที่250ตร.กม.; เส้นครอบคลุมไม่ลดเมื่อเพิ่มพื้นที่
- production-file-check.json: หน้าเว็บและbackend/appไม่เปลี่ยน ไม่มีคำสั่งdeploy
- protocol.json, summary.json, rows.json, coverage-area.csv: ขั้นตอน แหล่งข้อมูล ผลรวมและผลรายรอบ
- scar-agreement/protocol.json, downloads.json, summary.json: ข้อจำกัดช่วงเวลา hash และผลรอยไหม้รายสัปดาห์
- rank-cache/: อันดับเต็มที่ตรึงไว้เพื่อทำการวิเคราะห์ซ้ำโดยไม่ฝึกโมเดลใหม่

รันซ้ำ:

```powershell
backend/.venv-research/Scripts/python backend/scripts/evaluate_watch_budget.py
backend/.venv/Scripts/python backend/scripts/evaluate_weekly_scar_agreement.py
backend/.venv/Scripts/python backend/scripts/verify_watch_evaluation.py
backend/.venv-research/Scripts/python backend/scripts/report_watch_evaluation.py
```
'''
    (OUT / 'RESULTS_TH.md').write_text(report, encoding='utf8')
    (OUT / 'plot-environment.json').write_text(json.dumps({name: importlib.metadata.version(name) for name in ('matplotlib', 'numpy')}, indent=2), encoding='utf8')
    print('Local report and figures:', OUT)


if __name__ == '__main__':
    main()
