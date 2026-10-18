"""Package the verified offline results; never change/promote production."""
import importlib.metadata,shutil
from datetime import datetime,timezone
import fire_engineering_common as c
b,prep,physics,ml=c.configure()


def main():
    decision=c.read(c.OUT/'CONSOLIDATED_DECISION.json');verification=c.read(c.OUT/'refit-loop/verification.json');assert verification['status']=='PASS'
    package=c.OUT/'selected-growth-candidate';package.mkdir(exist_ok=True)
    source=c.ROOT/decision['model_path'];shutil.copyfile(source,package/'model.joblib');assert c.sha(source)==c.sha(package/'model.joblib')
    shutil.copyfile(c.OUT/'refit-loop/feature-contract.json',package/'feature-contract.json')
    c.write(package/'decision.json',decision)
    priority=c.ROOT/'output/joint-fire-model-20261017/final-candidate'
    registry={'production_promoted':False,'priority':{'path':str((priority/'model.joblib').relative_to(c.ROOT)),'sha256':c.sha(priority/'model.joblib'),
       'role':'Retainedofflinecandidatefornext12hhotspot-cellranking','coverage_pct_at250km2':36.07268222176337,
       'contract':str((priority/'feature-contract.json').relative_to(c.ROOT))},
       'growth':{'path':str((package/'model.joblib').relative_to(c.ROOT)),'sha256':c.sha(package/'model.joblib'),
         'role':'Experimentalnew-spectral-scarprediction; notreadyasoperationalfirefront','choice':decision['selected_growth_pipeline_on2025cv'],
         'final_train_cases':decision['final_train_cases'],'test_status':decision['test_status']}}
    c.write(c.OUT/'MODEL_REGISTRY.json',registry)
    model_card=f'''# โมเดลแนวไฟทดลองที่เลือกจากข้อมูลเก่า

ยังไม่พร้อมใช้เป็นเส้นแนวไฟจริง ไม่มีการเชื่อมเข้าเว็บหรือ deploy

รุ่น `{decision['selected_growth_pipeline_on2025cv']}` ฝึกสุดท้ายด้วย19เหตุปี2024–2025 ใช้ภาพและสถานะก่อนเริ่มทาย,จุดVIIRSย้อนหลังที่สมมติdelay3ชั่วโมง,ภูมิประเทศ/พืชพรรณ และอากาศพยากรณ์จากIFSrunก่อนหน้า รุ่นนี้ไม่ใช้PM/Himawari/ESA/corner-gridในขั้นทำนาย ไม่ต้องเรียกแหล่งเหล่านั้นเพื่อรันตัวที่เลือก

เลือกarchitecture/thresholdด้วย2025date-blockedCV แล้วตรึงก่อนประเมิน2026ซ้ำ ปี2026ถูกใช้ในรอบก่อนแล้ว จึงไม่ใช่freshholdout ไม่มีการปรับthresholdจากคะแนน2026

เป้าหมายคือรอยspectral-changeใหม่20ม.ที่ภาพหลังตรวจได้ตามช่วงภาพจริง ไม่ใช่fire-arrivaltime12hหรือprobabilityที่calibrateแล้ว ผลปี2026ได้Dice3.05%ใน11เหตุเดิม และ4.66%ใน8เหตุเพิ่ม พื้นที่นอกapplicability20คือunknown/unmodeled ห้ามเรียกปลอดไฟ

น้ำหนัก:model.joblib | schema:feature-contract.json | hash:{c.sha(package/'model.joblib')}

รันในworkspaceเดิมด้วยสภาพแวดล้อมวิจัยที่มีอยู่:

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/finalize_refit_fire_engineering.py --replay-case 2026-02-12-T47QMV-4771-19818-bank
```

ผลอยู่refit-loop/replay/<case-id>/prediction.npz พร้อมprediction-receipt.json ชุดinputที่ให้ตัวทำนายมีเพียงcase.json,initial-state.npz,single-run-weather.json ไม่มีภาพสุดท้ายหรือtargetlabel และตรวจแล้วpixelตรงกับbenchmark

ข้อมูลภาพเริ่มต้นถูกสมมติพร้อมที่acquisitionและคลังIFSเก่าเป็นhindcast;ไม่ใช่การรับรองas-issuedoperationalaccuracy. รายละเอียดผลรวมและข้อคัดออกอยู่SUMMARY_TH.md/CONSOLIDATED_DECISION.json
'''
    (package/'MODEL_CARD_TH.md').write_text(model_card,encoding='utf8')
    packages=('numpy','scipy','scikit-learn','joblib','pyproj','shapely','httpx','threadpoolctl','matplotlib','rasterio','ecmwf-opendata','eccodes','Cython','sortedcontainers')
    versions={name:importlib.metadata.version(name) for name in packages}
    (c.OUT/'requirements-research-lock.txt').write_text('\n'.join(name+'=='+version for name,version in versions.items())+'\n',encoding='utf8')
    c.write(c.OUT/'environment.json',versions)
    first=c.OUT/'FINAL_RESULTS_TH.md';text=first.read_text(encoding='utf8')
    marker='> เอกสารนี้เป็นผลรอบแรก'
    if marker not in text:
        lines=text.splitlines();lines[1:1]=['',marker+' ผลรวมสองรอบและรุ่นที่เลือกสุดท้ายอ่าน SUMMARY_TH.md และ CONSOLIDATED_DECISION.json',''];text='\n'.join(lines)
    text=text.replace('[np.float64(-0.25510016692525567), np.float64(0.06432818592420796)]','−0.255 ถึง +0.064 จุดเปอร์เซ็นต์')
    first.write_text(text,encoding='utf8')
    summary=c.OUT/'SUMMARY_TH.md';text=summary.read_text(encoding='utf8')
    extra='''
รอบสองไม่ได้ดีขึ้นทุกด้าน: ชุดเดิม Dice ลดจาก 3.15% เป็น 3.05%; ชุดเพิ่มเพิ่มจาก 4.15% เป็น 4.66% แต่ครอบคลุมรอยไหม้อ้างอิงลดจาก 4.86% เป็น 3.96% จึงยังไม่ถือว่าได้โมเดลแนวไฟที่ใช้ได้จริง รุ่นนี้เป็นตัวเลือกตามเกณฑ์ตรวจข้อมูลเก่าในชุดทดลอง ไม่ใช่ดีที่สุดทั่วไป

การมี/ไม่มี PM ในคู่เปรียบเทียบรอบแรกให้ผลเท่ากันที่ learner และ threshold เดียวกัน จึงยังไม่พิสูจน์ว่า PM ช่วยแนวไฟ หรือว่าการตัด PM ทำให้แม่นขึ้น ส่วนโมเดลเฝ้าระวังที่เก็บไว้ยังใช้ Hotspot + ลม + PM ตามเดิม
'''
    if 'รอบสองไม่ได้ดีขึ้นทุกด้าน' not in text:text=text.replace('## การลองเพิ่มข้อมูลฝึกอีกรอบ',extra+'\n## การลองเพิ่มข้อมูลฝึกอีกรอบ')
    text+='\n\n[รูปผลรวม](<'+(c.OUT/'final-results-overview.png').as_posix()+'>) · [โมเดลที่ส่งมอบ](<'+(package/'MODEL_CARD_TH.md').as_posix()+'>) · [แนวทางพัฒนา5ข้อ](<'+(c.ROOT/'docs/research/2026-10-18-next-model-improvements.md').as_posix()+'>)\n'
    summary.write_text(text,encoding='utf8')
    ideas=c.ROOT/'docs/research/2026-10-18-next-model-improvements.md';text=ideas.read_text(encoding='utf8')
    if 'อัปเดตหลังรอบฝึกเพิ่ม' not in text:
        lines=text.splitlines();lines[1:1]=['','> อัปเดตหลังรอบฝึกเพิ่ม: ทำแล้วเฉพาะการเว้นวัน/เหตุในการตรวจและ refit จาก19เหตุเก่า ส่วนการเพิ่ม hard negatives, B11/NDMI, active-state model, local moisture warm-up และ calibration ยังเป็นข้อเสนอ ผลล่าสุดอ่าน SUMMARY_TH.md ใน output/fire-engineering-20261018 เอกสารด้านล่างเก็บ snapshot ก่อนรอบฝึกเพิ่มไว้ตามเดิม',''];text='\n'.join(lines)
    ideas.write_text(text,encoding='utf8')
    log='''# Offline fire engineering — completed two finite rounds

All approved branches executed offline. No production promotion/deployment.

- Raw optical triplets39; usable model cases38, including8train2024/11selection2025/11legacy2026/8additional2026. OneROIexceededDEMcoverage andwasexcludedwithreason.
- Inputsactuallyretrieved: JAXAHimawari,actualnumericECMWFGRIBandhistoricalcornerforcing,ESA2023seasonalprior,HIInumericmonthlylegalforestpositives.
- Round1:79growthchoices.2025selectedpoint_no_pm__0.03;2026legacyDice3.151percent/additional4.155percent.
- Round2:20newdate-CVchoicesplusparent.2025selectedpoint_no_pm_large__0.03,finalfit19pastcases;reused2026legacyDice3.049percent/additional4.663percent. Noscore-based2026thresholdselection.
- Priority:12Himawarifusions+parent;parentretained36.073percentat250km2,fusion35.975percentonidentical231origins.
- Completedspatial/numeric/timecontractchecks,PMfuturepoisoning,labelsfreereplayexactparity,677boundarycount,2700frozenraw/inputhashes,6productionhashesand97oldsourcehashes;allPASS.
- Selectedmodel,featurecontract,registry,CLIreplay,researchdependencylock,sourceexclusions,fullscores,forestportionevaluation,reportsandvisuallycheckedfiguresdelivered.

Correctionsretained:STAC502→boundedretry/pagination;unavailable2024_18Zrun→earlierverified12Z;atomicuniquetempfiles;stricttile/cloudQC;HIItileunion/fixedinventoryandunknown-zero;minimalwinnerinferenceavoidsunusedproviders.

Completionmeansfiniteengineeringplan/test/artifactscomplete, notachievementofoperationalfire-frontaccuracy. No fire-front deployment recommended. Rankedfurtherexperimentswithsourcesandstopcriteriaarein docs/research/2026-10-18-next-model-improvements.md;theyarenotclaimedcompletedoraccurate.
'''
    (c.OUT/'ENGINEERING_LOG.md').write_text(log,encoding='utf8')
    scripts=('fire_engineering_common.py','build_fire_engineering_bank.py','fire_engineering_inputs.py','run_fire_engineering_loop.py','fire_engineering_physics.py','compare_himawari_priority.py',
      'predict_fire_engineering.py','verify_fire_engineering_loop.py','probe_himawari_fire_sources.py','probe_native_weather_grid.py','probe_hii_monthly_reference.py','build_timed_fire_cases.py',
      'timed_fire_spread_benchmark.py','timed_fire_growth_ml.py','timed_fire_growth_dense.py','prepare_timed_fire_arrays.py','refit_fire_engineering.py','finalize_refit_fire_engineering.py',
      'render_refit_fire_engineering.py','complete_fire_engineering_handover.py',
      'fire_research_geography.py','fire_research_moisture.py','priority_forecast_experiment.py','verify_fire_engineering_release.py')
    c.write(c.OUT/'code-sha256.json',{name:c.sha(c.ROOT/'backend/scripts'/name) for name in scripts})
    c.write(c.OUT/'completion.json',{'status':'complete','completed_utc':datetime.now(timezone.utc).isoformat(),'rounds':2,'all_approved_input_branches_executed':True,
      'round1_verification':'PASS','round2_verification':'PASS','manual_visual_reviewed_files':{str(path.relative_to(c.OUT)):c.sha(path) for path in (c.OUT/'final-results-overview.png',c.OUT/'refit-loop/2026-04-15-community-cmf-th-2892-two-round-comparison.png')},
      'selected_model_copy_hash_verified':True,'engineering_scope_complete':True,'operational_growth_accuracy_achieved':False,'production_changed':False,'deployment_commands':0})
    print('HANDOVER_COMPLETE',c.OUT/'SUMMARY_TH.md')


if __name__=='__main__':main()
