"""Freeze best2025candidate across offline experiments; summarize common2026rows."""
import hashlib,json,shutil,importlib.metadata
from datetime import datetime
import joblib,numpy as np
import joint_fire_experiment as j
from joint_spatial_pm_experiment import OUT as SPATIAL,CAMSNAMES

LABELS={'hotspot_context__large':'Hotspot+ข้อมูลพื้นฐาน','hotspot_wind__large':'Hotspot+ลม',
        'hotspot_pm__large':'Hotspot+PMสถานี','hotspot_wind_pm__large':'Hotspot+ลม+PMสถานี',
        'spatial_pm_hgb':'Hotspot+ลม+PMสถานี+PMเชิงพื้นที่','previous_boost15':'โมเดลก่อนหน้า','kernel':'วิธีฐานที่ปรับค่าแล้ว'}
def main():
    spatial=j.read(SPATIAL/'summary.json');selection=spatial['selection'];selected=selection['selected_overall_on2025']
    if selected=='spatial_pm_hgb':source=SPATIAL/'model.joblib';names=j.ALL_NAMES+CAMSNAMES;columns=list(range(59));pipeline='joint59_cams'
    elif '__lgb_' in selected:source=j.OUT/'lightgbm-comparison'/(selected+'.joblib');names=j.ALL_NAMES;columns=j.COLS[selected.split('__')[0]];pipeline='joint53'
    else:source=j.OUT/(selected+'.joblib');names=j.ALL_NAMES;columns=j.COLS[selected.split('__')[0]];pipeline='joint53'
    records=j.read(SPATIAL/'results-2026.json')['rows'];common={r['issued_at'] for r in records};merged={r['issued_at']:r for r in records}
    for file in (j.OUT/'results-2026.json',j.OUT/'lightgbm-comparison/results-2026.json'):
        for row in j.read(file)['rows']:
            if row['issued_at'] in common:merged[row['issued_at']]['scores'].update(row['scores'])
    rows=sorted(merged.values(),key=lambda r:r['issued_at']);score_names=list(rows[0]['scores'])
    assert selected in score_names,'Frozen chosen model must be tested before packaging.'
    summary=j.aggregate(rows,score_names);uncertainty=j.uncertainties(rows,score_names)
    n=summary['target_cells'];hits=summary['scores'][selected]['250.0']['hits'];old=summary['scores']['previous_boost15']['250.0']['hits'];base=summary['scores']['kernel']['250.0']['hits']
    folder=j.OUT/'final-candidate';folder.mkdir(exist_ok=True);shutil.copyfile(source,folder/'model.joblib')
    contract={'mode':'offline_experimental_candidate','model_selected_on2025':selected,'feature_pipeline':pipeline,
      'feature_columns':columns,'feature_names':[names[i] for i in columns],'full_feature_order':names,
      'model_sha256':hashlib.sha256((folder/'model.joblib').read_bytes()).hexdigest(),
      'target':'Next12h nominal/high VIIRS detection in500m cells, not verified perimeter or incident label.',
      'hotspot_delay_hours':3,'pm_latest_date_lag_days':2,'unit':'ranking score, not calibrated wildfire probability',
      'model_family':'LightGBM4.6.0' if '__lgb_' in selected else 'HistGradientBoosting',
      'selection':'Best2025coverage at250km2 across all candidates on common validation dates; frozen before this spatial-model test.',
      'production_changed':False,'research_package_versions':{name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn','lightgbm','pyproj','shapely','httpx','openpyxl','joblib')}}
    j.write(folder/'feature-contract.json',contract)
    decision={'selected_model_on2025':selected,'model_family':contract['model_family'],'common_validation_issues':selection['common_validation_issues'],
      'common_test_issues':summary['issues'],'common_test_target_cells':n,'selected_test_coverage_pct':100*hits/n,
      'old_test_coverage_pct':100*old/n,'baseline_test_coverage_pct':100*base/n,
      'gain_pp_vs_old':100*(hits-old)/n,'gain_pp_vs_old_7day_block_95pct':uncertainty[selected],
      'production_changed':False,'tested_new_candidates':12,'all_test_scores':summary['scores'],'model_sha256':contract['model_sha256']}
    j.write(j.OUT/'FINAL_DECISION.json',decision);j.write(j.OUT/'final-common-test-rows.json',rows)
    model=joblib.load(folder/'model.joblib')
    if hasattr(model,'booster_'):
        gain=model.booster_.feature_importance(importance_type='gain');splits=model.booster_.feature_importance(importance_type='split')
    else:
        gain=np.zeros(len(columns));splits=np.zeros(len(columns),dtype=int)
        for round_ in model._predictors:
            for tree in round_:
                for node in tree.nodes:
                    if not node['is_leaf']:
                        index=int(node['feature_idx']);splits[index]+=1;gain[index]+=max(0,float(node['gain']))
    diagnostics=sorted([{'feature':names[c],'training_split_count':int(splits[i]),'training_gain':float(gain[i])} for i,c in enumerate(columns)],key=lambda r:-r['training_gain'])
    j.write(folder/'training-feature-diagnostics.json',{'warning':'Training split/gain diagnostic only, not causal attribution or independent evidence of accuracy.','features':diagnostics})
    frozen=j.read(j.OUT/'production-files-frozen.json');actual={p:hashlib.sha256((j.ROOT/p).read_bytes()).hexdigest() for p in frozen};assert frozen==actual
    j.write(j.OUT/'no-production-change-check.json',{'unchanged':True,'files':actual,'deployment_commands_issued':0})
    report=f'''# ผลสรุปการหาโมเดลไฟ — Offline เท่านั้น

**รุ่นที่เลือกจากปี2025: {selected} ({contract['model_family']})**

ทดลอง12ตัวเลือกใหม่: HGB8ชุดใน4กลุ่มข้อมูล,LightGBM3ชุด และHGBเพิ่มข้อมูลCAMSเชิงพื้นที่1ชุด ใช้ข้อมูลฝึก2024และเลือกด้วย2025ก่อนประเมิน2026 ปี2026เคยถูกดูจากงานก่อนแล้ว ผลเป็นretrospective comparison ไม่ใช่ฤดูใหม่ที่ยังไม่เคยดู

## ผลบนวันเดียวกัน

เทียบทั้งหมดบน{summary['issues']}รอบ/{n:,}ช่อง-รอบที่มีจุดความร้อนภายหลัง และพื้นที่เฝ้าระวัง250ตร.กม.เท่ากัน

| โมเดล | ครอบคลุมจุดดาวเทียม12ชม.ถัดไป | จำนวนที่ตรง |
|---|---:|---:|
'''
    for name in score_names:
        value=summary['scores'][name]['250.0']['hits'];report+=f'| {LABELS.get(name,name)} | {100*value/n:.2f}% | {value:,}/{n:,} |\n'
    lo,hi=uncertainty[selected]
    report+=f'''
รุ่นที่เลือกได้{100*hits/n:.2f}% เทียบรุ่นก่อน{100*old/n:.2f}% และวิธีฐาน{100*base/n:.2f}% ผลเพิ่มเทียบรุ่นก่อน{100*(hits-old)/n:+.2f}จุดเปอร์เซ็นต์ ช่วง95%แบบบล็อก7วันคือ{lo:+.2f}ถึง{hi:+.2f}จุดเปอร์เซ็นต์

การเลือกอาศัยคะแนน2025บน{selection['common_validation_issues']}รอบร่วมเท่านั้น ไม่สลับเอาตัวที่คะแนน2026สูงสุดมาเรียกว่ารุ่นที่เลือก ดูselectionในspatial-pm-comparison/selection.jsonเพื่อไล่ทุกตัวเลือกย้อนหลัง

## สิ่งที่ต้องตีความให้ถูก

- นี่คือการทายช่อง500เมตรที่ดาวเทียมจะตรวจพบจุดความร้อนใน12ชั่วโมงถัดไป เพื่อช่วยเลือกพื้นที่เฝ้าระวัง ยังไม่ใช่เปอร์เซ็นต์ความแม่นของขอบไฟลามจริง
- ทดสอบแยกHotspot/Hotspot+ลม/Hotspot+PM/ครบสามส่วนแล้ว ผลเพิ่มจากลมและPMแยกส่วนในรอบHGBเดิมยังมีช่วงความไม่แน่นอนคร่อม0 จึงยังไม่กล่าวว่าตัวแปรเหล่านั้นเพิ่มความแม่นอย่างชัดเจนด้วยตัวมันเอง
- ตัวรุ่นที่เลือกอ่าน53หรือ59featuresตามfeature-contract ข้อมูลลมมี12ตำแหน่งพร้อมทิศที่สัมพันธ์กับhotspot ไม่ใช่เพียงความเร็วลมจุดเดียว และมีฝุ่นสถานีที่วัดจริงย้อนหลัง2วันเป็นข้อมูลประกอบ
- ได้ทดสอบเพิ่มPMเชิงพื้นที่จากCAMS12ตำแหน่งด้วย โดยใช้เฉพาะค่าเฉลี่ยของวันD-2ถึงD-4 ยังไม่ใช่ค่าฝุ่นวัดจริงทั่วจังหวัด และarchiveนี้ไม่ยืนยันexact issue time
- วันที่ประเมินรอบสุดท้ายลดลงเพราะต้องมีวันCAMSย้อนหลังครบ3วัน จึงคำนวณตัวเปรียบเทียบใหม่ทั้งหมดบนวันเดียวกัน ห้ามเทียบจำนวนตรงกับ237รอบจากรายงานเก่าโดยตรง
- PMสถานีเป็นสองจุดเมือง ลมGFSและPMจากCAMSยังหยาบกว่าช่อง500เมตร การมีข้อมูลเหล่านี้ไม่ทำให้ทราบเชื้อเพลิง/ไฟลามระดับทุกช่องโดยตรง
- มีsource-delayสมมติ3ชั่วโมงสำหรับFIRMS และPMวันD-2 มีavailability/windowที่ยังไม่ยืนยันจริง GFSใช้previous-day1จึงเป็นข้อมูลforecastย้อนหลังตามเวลานำ ไม่ใช่คลังissueเดียวที่ล็อกไว้
- scoresเป็นrankingไม่ใช่เปอร์เซ็นต์โอกาสไฟเพราะsampled training negatives; จุดที่ไม่ถูกเลือกยังมีความเสี่ยง และการไม่พบดาวเทียมไม่ยืนยันว่าไม่มีไฟ

## ผลส่งมอบ

- final-candidate/model.joblib: น้ำหนักรุ่นที่เลือก
- final-candidate/feature-contract.json: รายการข้อมูล หน่วย/ข้อกำหนดเวลา SHA256 และรุ่นไลบรารี
- final-candidate/training-feature-diagnostics.json: ตัวแปรที่ถูกใช้แบ่งต้นไม้ เป็นdiagnosticไม่ใช่หลักฐานเชิงสาเหตุ
- FINAL_DECISION.json,final-common-test-rows.json: ตัวเลขและผลรายรอบ
- RESULTS.md,component-effects.json: ผลทดลองแยกส่วนและข้อจำกัด
- no-production-change-check.json: hashยืนยันไฟล์เว็บและapplicationคงเดิม ไม่มีคำสั่งdeployในรอบนี้

ทดลองคาดการณ์ในเครื่องโดยไม่ฝึกใหม่และไม่อ่านfuture labels:

`backend/.venv-research/Scripts/python backend/scripts/predict_joint_fire_candidate.py --as-of 2026-04-15T08:00:00+07:00`

ไฟล์อยู่ในเครื่องทั้งหมด ยังไม่เพิ่มหน้าเว็บ ไม่เปลี่ยนโมเดลสด และไม่deploy จนกว่าผู้ใช้จะสั่งให้นำขึ้นเว็บ

แหล่งต้นทางและhashอยู่ในprotocol/receipts: NASA FIRMS, GFS previous-runsผ่านOpen-Meteo, PCD/Air4Thai daily export, CAMS global archiveผ่านOpen-Meteo
'''
    (j.OUT/'FINAL_RESULTS.md').write_text(report,encoding='utf8')
    (folder/'README.md').write_text('Offline frozen candidate. Read ../FINAL_RESULTS.md and feature-contract.json before use. No production deployment. Run predict_joint_fire_candidate.py for historical inference; outputs stay in this folder.\n',encoding='utf8')
    print('FINAL OFFLINE CANDIDATE',json.dumps({k:v for k,v in decision.items() if k!='all_test_scores'}),flush=True)
if __name__=='__main__':main()
