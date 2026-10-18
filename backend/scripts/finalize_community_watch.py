"""Package the2025-selected, equal-area community watch policy, offline."""
import hashlib
import math
import shutil

import numpy as np

import joint_fire_experiment as j
from train_community_watch_model import OUT


def main():
    folder = OUT / 'area-budget'
    protocol = j.read(OUT / 'protocol.json')
    selection = j.read(folder / 'selection.json')
    test = j.read(folder / 'test-2026.json')
    validation = selection['validation_summary']['policies']
    criterion = lambda name: (-validation[name]['250']['hits'], validation[name]['250']['mean_union_area_km2'], name)
    chosen = sorted(validation, key=criterion)[0]
    assert chosen == selection['selected_policy']
    baseline = sorted([name for name in validation if name.startswith('kernel__')], key=criterion)[0]
    parent = sorted([name for name in validation if name.startswith('cell_candidate__')], key=criterion)[0]
    model_name, power = chosen.split('__area_power')
    package = OUT / 'candidate'
    package.mkdir(exist_ok=True)
    source = OUT / (model_name + '.joblib') if model_name.startswith('forest_') else j.OUT / 'final-candidate/model.joblib'
    digest = None
    if model_name != 'kernel':
        shutil.copy2(source, package / 'model.joblib')
        digest = hashlib.sha256((package / 'model.joblib').read_bytes()).hexdigest()
    contract = {'mode': 'offline_historical_community_area_watch', 'selected_policy_on2025': chosen,
        'model_family_key': model_name, 'area_power': float(power), 'model_sha256': digest,
        'feature_pipeline': 'forest_pool160' if model_name.startswith('forest_') else 'parent53_or_kernel',
        'feature_names': protocol['features'], 'parent_feature_names': j.ALL_NAMES,
        'parent_feature_columns': j.read(j.OUT / 'final-candidate/feature-contract.json')['feature_columns'],
        'scope': protocol['scope'], 'target': protocol['target'],
        'algorithm': j.read(folder / 'protocol.json')['selection_algorithm'],
        'selection': selection['criterion'], 'evaluated_area_caps_km2': [125, 250, 500],
        'score_meaning': 'Ranking only for future satellite-detection watch priority; not calibrated fire probability.',
        'time_contract': '08/20ICT; hotspot acquisition<=issue-3h; PM dates<=issueDate-2; stitched GFS previousDay1 archive, not verified exact issue runs.',
        'input_source_sha256': protocol['source_sha256'], 'production_changed': False}
    j.write(package / 'feature-contract.json', contract)
    names = list(dict.fromkeys([chosen, baseline, 'cell_candidate__area_power0']))
    days = {}
    for row in test['rows']:
        value = days.setdefault(row['issued_at'][:10], np.zeros(len(names) + 1))
        value += [row['targets']] + [row['policies'][name]['250']['hits'] for name in names]
    matrix = np.array(list(days.values()))
    rng = np.random.default_rng(20261018)
    draws = []
    for _ in range(4000):
        starts = rng.integers(0, len(matrix), math.ceil(len(matrix) / 7))
        indices = np.concatenate([(start + np.arange(7)) % len(matrix) for start in starts])[:len(matrix)]
        totals = matrix[indices].sum(axis=0)
        if totals[0]:
            draws.append(totals)
    values = np.array(draws)
    uncertainty = {'unit': 'Paired circular blocks of7available issue days,4000replicates; positive forest-rounds, not distinct incidents.',
        'selected_coverage_pct_95': np.percentile(100 * values[:, 1] / values[:, 0], [2.5, 97.5]).tolist(),
        'gain_pp_95': {name: np.percentile(100 * (values[:, 1] - values[:, i + 1]) / values[:, 0], [2.5, 97.5]).tolist() for i, name in enumerate(names) if name != chosen}}
    j.write(OUT / 'uncertainty.json', uncertainty)
    scores = test['summary']['policies']
    decision = {'selected_policy_on2025': chosen, 'strongest_kernel_policy_on2025': baseline,
        'strongest_parent_policy_on2025': parent, 'test_issues': test['summary']['issues'],
        'positive_forest_rounds': test['summary']['positive_forest_rounds'], 'selected_test_at250': scores[chosen]['250'],
        'kernel_test_at250': scores[baseline]['250'], 'unadjusted_parent_at250': scores['cell_candidate__area_power0']['250'],
        'uncertainty': uncertainty, 'production_changed': False, 'not_fire_spread_accuracy': True}
    j.write(OUT / 'FINAL_DECISION.json', decision)
    count_test = j.read(OUT / 'test-2026.json')['summary']['models']
    report = f'''# ผลทดลองโมเดลและวิธีจัดลำดับป่าชุมชนในเครื่อง

เลือกด้วยปี2025: **{chosen}** ไม่เปลี่ยนโมเดลจังหวัดหรือเว็บ ไม่deploy

**ผลทดสอบ2026ยังสูสีกับวิธีฐานที่ปรับพื้นที่แล้ว:** วิธีที่เลือกได้{scores[chosen]['250']['coverage_pct']:.2f}% และวิธีฐาน{scores[baseline]['250']['coverage_pct']:.2f}% ที่งบ250ตร.กม.เท่ากัน ช่วง95%ของผลต่างคือ{uncertainty['gain_pp_95'].get(baseline, [0, 0])[0]:+.2f}ถึง{uncertainty['gain_pp_95'].get(baseline, [0, 0])[1]:+.2f}จุดเปอร์เซ็นต์ จึงยังไม่มีหลักฐานว่าตัวเลือกใหม่เหนือกว่าวิธีฐานอย่างชัดเจนในโจทย์รายป่านี้ ไม่เปลี่ยนวิธีที่เลือกไว้โดยอาศัยคะแนน2026ย้อนหลัง

## ผลที่ใช้ตัดสิน

ฝึก2024 เลือก2025 แล้วประเมินย้อนหลัง2026บน{test['summary']['issues']}รอบเวลา08/20น. เป้าหมายคือพบจุดVIIRSใน12ชั่วโมงถัดไปภายในป่าชุมชนรวมbuffer1กม. ใช้ศูนย์กลางช่อง500ม. ทั้ง677ป่า ขอบเขตซ้อนกันอาจมีจุดเดียวเป็นเป้าหมายหลายป่า จึงไม่ใช่จำนวนเหตุไฟจริง

ทดลองโมเดลรายป่าใหม่2ชุด(HistGradientBoosting160ตัวแปร) เทียบโมเดลจังหวัดเดิมและวิธีฐานใกล้hotspot เพิ่มวิธีปรับคะแนนด้วยขนาดพื้นที่3แบบต่อโมเดล รวม12นโยบายจัดลำดับ ใช้ปี2025เลือกที่งบพื้นที่250ตร.กม.เหมือนกัน ไม่เลือกตัวที่คะแนน2026สูงสุดมาสลับชื่อผู้ชนะ

## เทียบที่พื้นที่เฝ้าระวังรวมเท่ากัน

| วิธี | 125ตร.กม. | 250ตร.กม. | 500ตร.กม. | จำนวนป่าเฉลี่ยที่เลือกเมื่อ250ตร.กม. |
|---|---:|---:|---:|---:|
'''
    display = list(dict.fromkeys([chosen, 'cell_candidate__area_power0', baseline]))
    for name in display:
        item = scores[name]
        report += f"| {name}{' (เลือกจาก2025)' if name == chosen else ''} | {item['125']['coverage_pct']:.2f}% | {item['250']['coverage_pct']:.2f}% | {item['500']['coverage_pct']:.2f}% | {item['250']['mean_selected_forests']:.1f} |\n"
    lo, hi = uncertainty['selected_coverage_pct_95']
    report += f'''
ที่250ตร.กม. วิธีที่เลือกได้{scores[chosen]['250']['coverage_pct']:.2f}% ช่วง95%ประมาณ{lo:.2f}–{hi:.2f}% ของรอบป่าที่พบจุดภายหลังทั้งหมด{test['summary']['positive_forest_rounds']:,}รอบป่า พื้นที่unionจริงเฉลี่ย{scores[chosen]['250']['mean_union_area_km2']:.2f}ตร.กม. จำกัดทุกissueไม่เกิน250ตร.กม.

การปรับคะแนนเป็นscore/(พื้นที่bufferช่องตัวเลือกยกกำลัง{float(power):g})แล้วเรียงก่อนเลือก โดยเพิ่มทั้งป่าเฉพาะเมื่อพื้นที่ใหม่รวมยังไม่เกินงบ ข้ามป่าที่ไม่พอดี และพิจารณาป่าต่อไป การเลือกใช้เฉพาะคะแนนกับรูปทรงขอบเขต ไม่อ่านจุดความร้อนในอนาคต

ตัวเลขนี้เปรียบเทียบกันภายในโจทย์เดียวกัน ไม่ใช่การทำให้คะแนนจังหวัด36%กลายเป็นคะแนนนี้ เพราะเป้าหมายเปลี่ยนจากช่องทั่วจังหวัดเป็นรอบป่าที่พบจุดภายในbuffer และจุดเดียวอาจเกี่ยวกับหลายป่าได้

## ทำไมไม่ใช้จำนวนป่าอย่างเดียว

ที่เลือก50ป่าเท่ากัน พื้นที่เฝ้าระวังอาจต่างกันมาก จึงไม่ใช้คะแนนตารางนี้อย่างเดียวเลือกวิธีสุดท้าย:

| โมเดล | ครอบคลุมรอบป่าที่พบจุด เมื่อเลือก50ป่า | พื้นที่unionเฉลี่ย ตร.กม. |
|---|---:|---:|
'''
    for name, item in count_test.items():
        report += f"| {name} | {item['50']['coverage_pct']:.2f}% | {item['50']['mean_union_area_km2']:.1f} |\n"
    report += '''
ปี2026เคยถูกดูจากงานก่อน ผลนี้ยังเป็นการศึกษาเปรียบเทียบย้อนหลัง ไม่ใช่ผลรับรองฤดูใหม่ ไม่ได้วัดแนวไฟลามจริง การไม่พบhotspotไม่ใช่หลักฐานว่าไม่มีไฟ คะแนนใช้จัดอันดับ ไม่ใช่เปอร์เซ็นต์โอกาสเกิดไฟ buffer1กม.เป็นสถานการณ์ทดลอง ยังไม่ใช่ระยะคุกคามป่าที่พิสูจน์แล้ว

## ทดลองใช้น้ำหนักและวิธีเลือกที่แพ็กแล้ว

```powershell
backend/.venv-research/Scripts/python backend/scripts/predict_community_watch.py --as-of 2026-04-15T08:00:00+07:00 --area-km2 250
```

ผลJSONอยู่ในcandidate/เท่านั้น มีชื่อและรหัสป่า อันดับ พื้นที่รวม ช่วงเวลา และข้อกำหนดข้อมูล ไม่มีการส่งแจ้งเตือนหรืออัปเดตเว็บ

ไฟล์หลัก: protocol.json,area-budget/protocol.json,area-budget/selection.json,area-budget/test-2026.json,FINAL_DECISION.json,uncertainty.json,candidate/model.joblib,candidate/feature-contract.json,verification.json
'''
    (OUT / 'RESULTS_TH.md').write_text(report, encoding='utf8')
    print('PACKAGED COMMUNITY POLICY', decision, flush=True)


if __name__ == '__main__':
    main()
