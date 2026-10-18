"""Consolidate both finite engineering rounds and verify the selected replay."""
from datetime import datetime,timedelta
from pathlib import Path
import argparse,itertools,shutil
import numpy as np
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import run_fire_engineering_loop as loop
import refit_fire_engineering as r
import predict_fire_engineering as original
from verify_fire_engineering_loop import frozen_production


def make_bundle(case_id,destination):
    selection=c.read(r.OUT/'selection.json');name=selection['selected']
    group='point_no_pm' if name=='parent' else r.CONFIGS[name.rsplit('__',1)[0]][0]
    source=c.OUT/'cases'/case_id;folder=destination/'cases'/case_id;folder.mkdir(parents=True,exist_ok=True)
    meta=c.read(source/'case.json');c.write(folder/'case.json',meta)
    with np.load(source/'model-arrays.npz') as archive:known={key:archive[key] for key in original.KNOWN}
    np.savez_compressed(folder/'initial-state.npz',**known)
    files=('single-run-weather.json',) if group.startswith('point_') else ('initial-supplement.npz','initial-supplement.json','single-run-weather.json','corner-weather.json','corner-weather.npz','corner-weather-contract.json')
    for name in files:shutil.copyfile(source/name,folder/name)
    if group!='point_no_pm':
        date=datetime.fromisoformat(meta['initial_acquisition']).astimezone(ml.j.ICT).date()-timedelta(days=2);first=date-timedelta(days=6)
        source_pm=c.read(ml.j.OUT/f'pm-{date.year}.json')['dates'];c.write(destination/'context'/f'pm-{date.year}.json',{'dates':{d:v for d,v in source_pm.items() if str(first)<=d<=str(date)}})
    c.write(destination/'bundle-contract.json',{'case_id':case_id,'selected':selection['selected'],'group':group,
      'selection_sha256':c.sha(r.OUT/'selection.json'),'future_optical_or_target_labels_included':False,
      'included_case_files':['case.json','initial-state.npz',*files],'operational_status':'Offline retrospective candidate, not promoted.'})
    return meta


def replay(destination,case_id):
    selection=c.read(r.OUT/'selection.json')
    with original.input_root(destination):
        meta=c.read(destination/'cases'/case_id/'case.json')
        with np.load(destination/'cases'/case_id/'initial-state.npz') as archive:initial={key:archive[key] for key in loop.dense.KNOWN}
        mask=r.predict(meta,initial,selection)
    applicable,clear,scar=original.forecast_domain(destination,case_id)
    assert not (mask&~applicable).any()
    np.savez_compressed(destination/'prediction.npz',predicted=mask,applicability20=applicable,initial_clear20=clear,known_initial_scar20=scar)
    c.write(destination/'prediction-receipt.json',{'case_id':case_id,'selected':selection['selected'],'initial_acquisition':meta['initial_acquisition'],
      'requested_valid_until':meta['final_acquisition'],'predicted_area_km2':float(mask.sum()*.0004),'applicable_fraction':float(applicable.mean()),
      'unknown_semantics':'Outsideapplicabilityisunknown/unmodeled, notanallclear.', 'future_images_or_labels_read':False,
      'prediction_sha256':c.sha(destination/'prediction.npz'),'production_changed':False})
    return mask


def verify():
    frozen=c.read(r.OUT/'frozen-selection.json')
    for name,digest in frozen['files'].items():assert c.sha(r.OUT/name)==digest
    for name,digest in c.read(loop.MODEL_DIR/'frozen-selection.json')['files'].items():assert c.sha(loop.MODEL_DIR/name)==digest
    for case_id,digest in frozen['source_array_content_sha256'].items():assert c.array_content_sha(c.OUT/'cases'/case_id/'model-arrays.npz')==digest
    # Check every raw/input file frozen at the end of round1, not only models.
    sources=c.read(c.OUT/'frozen-final-inputs.json')['files']
    for path,digest in sources.items():assert c.sha(c.ROOT/path)==digest,'Changed frozen input '+path
    validation=[m for m in loop.metas() if m['engineering_split']=='validation2025'];overlap=[]
    for a,b in itertools.combinations(validation,2):
        aa,bb=a['bounds_utm47'],b['bounds_utm47'];area=max(0,min(aa[2],bb[2])-max(aa[0],bb[0]))*max(0,min(aa[3],bb[3])-max(aa[1],bb[1]));time_overlap=max(a['initial_acquisition'],b['initial_acquisition'])<min(a['final_acquisition'],b['final_acquisition'])
        if area and time_overlap and a['initial_acquisition'][:10]!=b['initial_acquisition'][:10]:overlap.append([a['id'],b['id']])
    assert not overlap,'Merge overlapping label windows into the same validation group'
    selection=c.read(r.OUT/'selection.json')
    for fold in selection['folds']:
        assert set(fold['fit_ids']).isdisjoint(fold['held_ids'])
        fitting={m['initial_acquisition'][:10] for m in validation if m['id'] in fold['fit_ids']};assert not fitting&set(fold['held_dates'])
        assert not any(case_id.startswith('2026') for case_id in fold['fit_ids'])
    cases=[next(m for m in loop.metas() if m['engineering_split']=='test2026_new_cases')['id'],'2026-04-15-community-cmf-th-2892'];checks=[]
    for case_id in cases:
        destination=r.OUT/'replay'/case_id;make_bundle(case_id,destination);actual=replay(destination,case_id);expected=np.load(r.OUT/(case_id+'-prediction.npz'))['predicted'];np.testing.assert_array_equal(actual,expected)
        assert not (destination/'cases'/case_id/'model-arrays.npz').exists()
        checks.append({'id':case_id,'exact_prediction_parity':True,'labels_free_input_files':[p.name for p in (destination/'cases'/case_id).iterdir()]})
    result={'status':'PASS','round1_all_frozen_raw_inputs_unchanged':len(sources),'frozen_selection_and_weights':'PASS','no_held_date_or_event_pixels_in_training':'PASS',
      'crossdate_spatially_overlapping_label_windows':overlap,'replays':checks,'production':frozen_production()}
    c.write(r.OUT/'verification.json',result);return result


def finalize():
    verification=verify();selection=c.read(r.OUT/'selection.json');test=c.read(r.OUT/'test-results.json');parent=c.read(c.OUT/'selected-growth-results.json');old=c.read(c.OUT/'same-case-old-versus-new.json');primary=c.read(c.OUT/'FINAL_DECISION.json')
    name=selection['selected'];winner=selection['summary'][name];parent_score=selection['summary']['parent'];final_train=8 if name=='parent' else 19
    group='point_no_pm' if name=='parent' else r.CONFIGS[name.rsplit('__',1)[0]][0]
    parent_contract=c.read(loop.MODEL_DIR/'feature-contract.json');columns=parent_contract['groups'][group]
    weight_path=loop.MODEL_DIR/'point_no_pm.joblib' if name=='parent' else r.OUT/'model.joblib'
    c.write(r.OUT/'feature-contract.json',{'selected':name,'feature_group':group,'feature_names':[parent_contract['names'][i] for i in columns],
        'source_full_schema_sha256':c.sha(loop.MODEL_DIR/'feature-contract.json'),'model_sha256':c.sha(weight_path),'final_train_cases':final_train,
        'target':'New20mspectral-change pixels over exact observedimageinterval, notvalidated12harrival/perimeter.',
        'initial_only':True,'test_status':'2026reusedretrospectiveafterround1; notfreshholdout','production_changed':False})
    matched={split:{'round1':parent['by_split'][split],'round2':test['by_split'][split]} for split in test['by_split']}
    decision={'status':'completed_two_offline_engineering_rounds','selected_growth_pipeline_on2025cv':name,'validation2025_pooled_dice':winner['pooled_dice'],
      'round1_validation2025_pooled_dice':parent_score['pooled_dice'],'final_train_cases':final_train,'cv2025_cases':11,
      'growth_choices_across_rounds':99,'priority_fusion_choices_including_parent':13,'case_count':38,'growth_test_by_split':test['by_split'],
      'community':test['community'],'priority_retained':'hotspot_wind_pm__large','priority_coverage_at250km2_pct':primary['priority_parent_coverage_pct'],
      'test_status':'2026reusedretrospectiveafterround1; nofreshholdoutclaim. Hyperparametersandthresholdchosenonlyfromdateblocked2025CV.',
      'model_path':str((loop.MODEL_DIR/'point_no_pm.joblib' if name=='parent' else r.OUT/'model.joblib').relative_to(c.ROOT)),
      'no_usable_growth_claim':True,'verification':'PASS','production_changed':False,'deployment_commands_issued':0}
    c.write(c.OUT/'CONSOLIDATED_DECISION.json',decision);c.write(r.OUT/'round1-versus-round2.json',matched)
    text=f'''# ผลงานรอบทดลองไฟป่าเชียงใหม่ — 18 ตุลาคม 2026

**ทำการทดลองออฟไลน์ครบ 2 รอบแล้ว เว็บยังคงเดิม ไม่มีการ deploy**

ข้อมูลภาพครบ 39 เหตุ ใช้รันโมเดลได้ 38 เหตุ อีกเหตุเกินขอบเขตข้อมูลภูมิประเทศจึงไม่นำมาปะปน ฝึก/เลือกจากปี 2024–2025 และประเมินปี 2026 แยก 11 เหตุเดิมกับ 8 เหตุที่เพิ่มมา

## คำตอบภาษาคน

**การเลือกพื้นที่เฝ้าระวังยังใช้รุ่นเดิมเป็นหลัก:** หากเลือกดูพื้นที่ 250 ตร.กม.ต่อรอบ รุ่นนี้ครอบคลุมช่องที่ดาวเทียมพบจุดความร้อนใน 12 ชั่วโมงถัดไป 36.07% เทียบวิธีฐานเดิม 28.44% การเพิ่ม Himawari ที่ทดลองได้ 35.97% จึงยังไม่มีหลักฐานให้เปลี่ยนรุ่น ตัวเลขนี้เป็นผลย้อนหลังของโมเดลทดลอง ไม่ใช่ความแม่นของเส้นแนวไฟหรือการรับรองเว็บสด

**แนวไฟลามยังไม่พร้อมให้ชุมชนยึดเป็นแนวไฟจริง:** หลังทดสอบ 99 ตัวเลือกในสองรอบ ผลรุ่นที่เลือกจากข้อมูลเก่ามีดังนี้ ค่านี้เป็น Dice วัดการทับซ้อนของรอยไหม้ใหม่จากภาพดาวเทียม ช่วงภาพประมาณ 2–5 วัน ไม่ใช่เปอร์เซ็นต์โอกาสไฟหรือคะแนนพยากรณ์ 12 ชั่วโมง

| ชุดทดสอบย้อนหลังปี 2026 | เหตุ | คะแนนทับซ้อนรอยไหม้ใหม่ |
|---|---:|---:|
| เหตุเดิมที่เคยตรวจแล้ว | 11 | {100*test['by_split']['regression2026']['pooled_dice']:.2f}% |
| เหตุที่เพิ่มเข้ามา | 8 | {100*test['by_split']['test2026_new_cases']['pooled_dice']:.2f}% |

ในชุดเหตุเดิมเดียวกัน รุ่นฟิสิกส์รอบก่อนเคยได้ 1.40% รอบแรกของวันนี้ได้ 3.15% การเพิ่มคะแนนไม่ได้หมายความว่าครอบคลุมไฟได้มากขึ้นทุกด้าน: รอบแรกทำนายเกินลดลง แต่ครอบคลุมรอยไหม้อ้างอิงลดจาก 16.42% เป็น 11.99% ต้องดูพื้นที่พลาดและพื้นที่เกินพร้อมกัน

## การลองเพิ่มข้อมูลฝึกอีกรอบ

รอบแรกฝึกจากปี 2024 เพียง 8 เหตุ จึงลองรอบที่สองโดยใช้ข้อมูลปี 2025 มาช่วยฝึกแบบเว้นทั้งวันและเหตุไว้ตรวจ แต่ละรอบตรวจไม่มี pixel ของเหตุหรือวันนั้นอยู่ในข้อมูลฝึก ตรวจแล้วไม่มีพื้นที่และช่วงเวลาของคำตอบซ้ำข้ามวันในชุดตรวจนี้ ลองเพิ่มอีก 4 รูปแบบ × 5 เกณฑ์ตัดสิน และให้รุ่นเดิมเป็นตัวเปรียบเทียบที่มีสิทธิชนะ

ตัวที่เลือกจากคะแนนปี 2025 คือ `{name}` คะแนนตรวจปี 2025 จากเดิม {100*parent_score['pooled_dice']:.2f}% เป็น {100*winner['pooled_dice']:.2f}% แล้วฝึกน้ำหนักสุดท้ายด้วย {final_train} เหตุเก่าตามสูตรที่เลือก ก่อนคำนวณปี 2026 ซ้ำ ไม่ใช้คะแนนปี 2026 เพื่อเลือกเกณฑ์

ปี 2026 เคยถูกเปิดผลในรอบแรกแล้ว ผลรอบสองจึงเป็นการประเมินย้อนหลังที่ใช้ซ้ำ **ไม่ใช่ชุดทดสอบใหม่ที่ไม่เคยเห็น** และไม่ควรนำคะแนนตรวจปี 2025 ไปเรียกว่าเป็นความแม่นที่ใช้งานจริง

## ช่วยป่าชุมชนได้จริงแค่ไหน

'''
    for split,label in (('regression2026','ชุดเดิม'),('test2026_new_cases','ชุดเพิ่ม')):
        f=test['community'][split];text+=f"- {label}: เห็นส่วนป่าในกรอบภาพ {f['portion_periods']} ช่วง มีรอยไหม้อ้างอิงอย่างน้อย 1 เฮกตาร์ {f['positive_periods_ge1ha']} ช่วง รุ่นแนวไฟเตือนได้ {f['warned_positive_periods']} พลาด {f['missed_positive_periods']} และเตือนแต่ไม่พบรอยถึงเกณฑ์อีก {f['warned_without_reference_ge1ha']} ช่วง\n"
    text+='''
จำนวนนี้ยังน้อยและครอบคลุมเพียงส่วนป่าที่มีภาพ ไม่ใช่ผลทดสอบครบป่าชุมชน 677 แห่ง การไม่พบรอยไหม้ไม่ได้ยืนยันว่าไม่มีไฟ หลักฐานตอนนี้รองรับการใช้โมเดลเฝ้าระวังเพื่อช่วยเลือกพื้นที่ไปตรวจ มากกว่าการแสดงเส้นไฟลามให้ใช้ตัดสินใจ

## สิ่งที่ส่งมอบแล้ว

- ชุดเหตุ 38 เหตุ พร้อมภาพ เวลา พิกัด ข้อมูลอากาศจากรอบเดียว และเหตุผลที่ตัดข้อมูลออก
- โมเดลและผลเปรียบเทียบมี/ไม่มี PM2.5, Himawari, ลมหลายตำแหน่ง และข้อมูลพืชพรรณ/ประวัติไหม้ ไม่พบว่าเติมข้อมูลทุกอย่างแล้วจะชนะเสมอ
- ตัวทำนายออฟไลน์ที่รันซ้ำได้จากข้อมูลก่อนเริ่มทาย ตรวจแล้วผลตรงกับ benchmark ทุก pixel โดยไม่มีภาพหลังเกิดเหตุหรือคำตอบอนาคตในชุดรัน
- แยกพื้นที่ไม่ทราบ/โมเดลไม่ครอบคลุมออกจากผลทำนาย ไม่แสดงว่าเป็นพื้นที่ปลอดไฟ
- ตรวจน้ำหนักที่ตรึงไว้ ขอบเขตเวลา อินพุตดิบ 2,700 ไฟล์ ไฟล์ระบบหลัก 6 ไฟล์ และแหล่งข้อมูลเดิม 97 ไฟล์แล้ว ไม่มีการเปลี่ยนเว็บหรือ deploy

## ถ้าจะพัฒนาต่อให้ตรงจุด

เตรียมแผนทดลองพร้อมแหล่งข้อมูลเปิดและเกณฑ์วัดไว้ 5 ข้อ: แยกไฟที่ยัง active/รอยเก่า/ไม่ทราบกับเหตุจุดใหม่, เพิ่ม SWIR1/NDMI และภาพหลายเวลาก่อนเริ่มทาย, เพิ่มกลุ่มเหตุอิสระและตัวอย่างที่ไม่ควรเตือน, ปรับสถานะความชื้นเชื้อเพลิงเฉพาะพื้นที่จากข้อมูลย้อนหลัง และตรวจเทียบความน่าจะเป็นพร้อมงดฟันธงเมื่อข้อมูลไม่พอ รายละเอียดอยู่ใน docs/research/2026-10-18-next-model-improvements.md ยังไม่อ้างว่าแนวคิดเหล่านี้เพิ่มความแม่นแล้ว และไม่ได้บังคับให้ไปหน้างานก่อนเริ่มทดลอง

หลักฐานละเอียด: FINAL_RESULTS_TH.md, CONSOLIDATED_DECISION.json, refit-loop/selection.json, refit-loop/test-results.json, refit-loop/verification.json และรูปผลการเปรียบเทียบ
'''
    (c.OUT/'SUMMARY_TH.md').write_text(text,encoding='utf8')
    report=f'''# Engineering รอบ2: เพิ่มข้อมูลฝึกเก่าแบบเว้นวันและเหตุ

เลือก `{name}` จาก2025date-CV pooledDice {100*winner['pooled_dice']:.3f}% เทียบparent {100*parent_score['pooled_dice']:.3f}%. Finalfitใช้{final_train}เหตุเก่า. 2026เป็นreusedretrospectiveหลังออกแบบรอบ1 ไม่ใช่unseenholdout. No2026labelsเลือกhyperparameters/threshold.

## เทียบรอบ1–2บนคำตอบชุดเดียวกัน

| ชุด | รอบ1 Dice | รอบ2 Dice | รอบ2พื้นที่ทำนายกม² | referenceกม² | intersectionกม² |
|---|---:|---:|---:|---:|---:|
'''
    for split,s in matched.items():
        a=s['round1'];bb=s['round2'];report+=f"| {split} | {100*a['pooled_dice']:.3f}% | {100*bb['pooled_dice']:.3f}% | {bb['predicted_growth_km2']:.4f} | {bb['reference_growth_km2']:.4f} | {bb['intersection_km2']:.4f} |\n"
    report+='''
ข้อแยกสำคัญ: CVcandidateได้เรียนจากวันอื่นในปี2025 ส่วนparentเรียน2024เท่านั้น จึงเป็นการทดลองเพิ่มtrainingdata ไม่ใช่yearholdoutที่มีbudgetข้อมูลฝึกเท่ากัน คะแนนCVก่อนfinalrefitไม่ใช่คะแนนตรวจของน้ำหนักที่fitทุก19เหตุแล้ว แยกtest2026ไว้และไม่สลับthresholdตามผลนั้น

Verificationผ่าน: frozenweights/sourcearraycontent, ข้อมูลดิบ2700ไฟล์ยังเดิม, heldcase/date disjoint, ไม่มีcrossdateoverlappinglabelwindows, replay2เหตุไม่มีfutureimage/labelsและpixelตรงกัน, production6ไฟล์/old97sourcesยังเดิม ไม่มีdeploy

## รันซ้ำ

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/refit_fire_engineering.py --phase selection
backend/.venv-research/Scripts/python -X utf8 backend/scripts/refit_fire_engineering.py --phase test
backend/.venv-research/Scripts/python -X utf8 backend/scripts/finalize_refit_fire_engineering.py
```
'''
    (r.OUT/'RESULTS_TH.md').write_text(report,encoding='utf8')
    c.write(c.OUT/'completion.json',{'status':'complete','completed_utc':datetime.now().astimezone().isoformat(),'rounds':2,'all_proposed_input_branches_executed':True,
      'loop1_verification':c.read(c.OUT/'verification.json')['status'],'loop2_verification':verification['status'],'plots_visually_inspected_round1':True,'production_changed':False,'deployments':0})
    print('TWO_ROUND_ENGINEERING_COMPLETE',decision,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--replay-case');args=parser.parse_args()
    if args.replay_case:
        destination=r.OUT/'replay'/args.replay_case;make_bundle(args.replay_case,destination);replay(destination,args.replay_case);print(destination)
    else:finalize()


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
