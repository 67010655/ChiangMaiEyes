"""Consolidate completed offline trials, uncertainty and community relevance."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import importlib.metadata
import numpy as np
from scipy.ndimage import binary_erosion,distance_transform_edt
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import run_fire_engineering_loop as loop
import fire_engineering_physics as physical
import timed_fire_growth_dense as dense
from audit_fire_engineering_references import main as hii_audit
import timed_community_reference as community


def prediction(meta,choice):
    folder=c.OUT/'cases'/meta['id']
    if choice['family']=='surface_graph':
        mask=np.load(folder/(choice['name']+'-field-prediction.npz'))['predicted'];return np.repeat(np.repeat(mask,5,axis=0),5,axis=1)
    return np.load(folder/'engineering-prediction.npz')['predicted']


def dice_ci(rows,seed=20261018):
    if not rows:return None
    groups=defaultdict(lambda:np.zeros(3))
    for row in rows:
        s=row['score'];groups[row['initial_acquisition'][:10]]+=np.array([s[k] for k in ('predicted_growth_km2','reference_growth_km2','intersection_km2')])
    matrix=np.array(list(groups.values()));rng=np.random.default_rng(seed);draws=[]
    for _ in range(3000):
        p,r,i=matrix[rng.integers(0,len(matrix),len(matrix))].sum(axis=0)
        if p+r:draws.append(2*i/(p+r))
    return {'percentile95':list(np.percentile(draws,[2.5,97.5])) if draws else None,'sampling_unit':'initial-acquisition date, entire cases together','groups':len(matrix),'note':'Small retrospective sample; interval is descriptive, does not establish future deployment performance. No interval if all sampled support has zero predicted+reference area.'}


def priority_uncertainty():
    root=c.OUT/'priority-himawari';result=c.read(root/'test-results.json');selected=result['selected_on2025'];groups=defaultdict(lambda:np.zeros(3))
    for row in result['rows']:
        groups[row['issued_at'][:10]]+=np.array([row['target_cells_all'],row['scores']['parent']['250.0'],row['scores'][selected]['250.0']])
    matrix=np.array(list(groups.values()));rng=np.random.default_rng(20261018);draws=[]
    for _ in range(4000):
        starts=rng.integers(0,len(matrix),int(np.ceil(len(matrix)/7)));idx=np.concatenate([(s+np.arange(7))%len(matrix) for s in starts])[:len(matrix)]
        total,parent,new=matrix[idx].sum(axis=0);draws.append(100*(new-parent)/total)
    output={'selected_on2025':selected,'delta_percentage_points':result['summary'][selected]['coverage_pct']-result['summary']['parent']['coverage_pct'],
      'paired_circular7day_block95_pp':list(np.percentile(draws,[2.5,97.5])),'original_model_retained':True,
      'interpretation':'No demonstrated improvement at fixed250km2; source useful for positive monitoring evidence but this late-fusion hypothesis does not replace parent.'}
    c.write(root/'uncertainty.json',output);return output


def evaluate_selected(choice):
    rows=[];forests=[]
    for meta in loop.metas():
        if meta['engineering_split'] not in ('test2026_new_cases','regression2026'):continue
        folder=c.OUT/'cases'/meta['id'];mask=prediction(meta,choice)
        with np.load(folder/'model-arrays.npz') as data:
            arrays={key:data[key] for key in ('initial_scar20','valid20','target20','connected_target20')}
        score=dense.metrics(mask,arrays)
        initial=dict(np.load(folder/(meta['initial_scene']+'.npz')));after=dict(np.load(folder/(meta['final_scene']+'.npz')))
        for threshold,key in ((.1,'low20'),(.27,'high20')):
            arrays[key]=prep.changed(initial,after,threshold)&arrays['valid20']&~arrays['initial_scar20']
        sensitivity={key:dense.metrics(mask,arrays,key) for key in ('connected_target20','low20','high20')}
        visible=mask&arrays['valid20']&~arrays['initial_scar20'];aa=visible&~binary_erosion(visible);bb=arrays['target20']&~binary_erosion(arrays['target20'])
        if aa.any() and bb.any():
            distances=np.r_[distance_transform_edt(~aa)[bb]*20,distance_transform_edt(~bb)[aa]*20]
            boundary={'mean_m':float(distances.mean()),'p95_m':float(np.percentile(distances,95))}
        else:boundary={'mean_m':None,'p95_m':None}
        hii={}
        if (folder/'hii-monthly-positive-only.npz').exists():
            positives=np.load(folder/'hii-monthly-positive-only.npz')['positive']
            hii={'monthly_positive_area_km2':float(positives.sum()*.0004),
              'new_s2_reference_also_hii_monthly_positive_km2':float((positives&arrays['target20']).sum()*.0004),
              'prediction_also_hii_monthly_positive_km2':float((positives&visible).sum()*.0004),
              'semantics':'Secondarypositivecorroborationonly. No temporal precision/recall/accuracy fromHII; monthlypositives canpredateorigin andzerosareunknown.'}
        with np.load(folder/'community-forest-masks.npz') as masks:
            for forest_id in masks.files:
                fm=masks[forest_id];reference=int((fm&arrays['target20']).sum());predicted=int((fm&visible).sum());clear=int((fm&arrays['valid20']).sum())
                forests.append({'case_id':meta['id'],'split':meta['engineering_split'],'forest_id':forest_id,
                    'observed_pixels':clear,'reference_new_scar_pixels':reference,'predicted_new_scar_pixels':predicted,
                    'reference_ge1ha':reference>=25,'warning_ge1ha':predicted>=25})
        rows.append({'id':meta['id'],'split':meta['engineering_split'],'initial_acquisition':meta['initial_acquisition'],
           'horizon_hours':meta['horizon_hours'],'score':score,'sensitivity':sensitivity,'boundary':boundary,'hii_positive_corroboration':hii})
    summary={}
    for split in sorted({r['split'] for r in rows}):
        selected=[r for r in rows if r['split']==split];summary[split]=loop.pooled([{'scores':{'selected':r['score']}} for r in selected],'selected')
        summary[split]['uncertainty']=dice_ci(selected)
        portions=[r for r in forests if r['split']==split];positives=[r for r in portions if r['reference_ge1ha']]
        summary[split]['community_portions']={'observed_portion_periods':len(portions),'unique_forests':len({r['forest_id'] for r in portions}),
          'reference_positive_periods_ge1ha':len(positives),'warned_positive_periods':sum(r['warning_ge1ha'] for r in positives),
          'missed_positive_periods':sum(not r['warning_ge1ha'] for r in positives),
          'warned_without_reference_ge1ha':sum(r['warning_ge1ha'] and not r['reference_ge1ha'] for r in portions),
          'scope':'Case-coveredclearforestportionsonly, not677forestpopulation performance. No observedscar isnot verifiedabsence.'}
    c.write(c.OUT/'selected-growth-results.json',{'choice':choice,'by_split':summary,'cases':rows,'community_portions':forests})
    return summary,rows


def matched_legacy_comparison(choice):
    old=[];new=[]
    for meta in loop.metas():
        if meta['engineering_split']!='regression2026':continue
        arrays=dict(np.load(c.OUT/'cases'/meta['id']/'model-arrays.npz'))
        arrival=np.load(c.OLD/'cases'/meta['id']/'predictions/pyre_mapped8_dynamic_point_s1.npz')['arrival_minutes']
        mask=np.repeat(np.repeat(arrival<=meta['horizon_hours']*60,5,axis=0),5,axis=1)
        old.append({'scores':{'old':dense.metrics(mask,arrays)}});new.append({'scores':{'new':dense.metrics(prediction(meta,choice),arrays)}})
    result={'cohort':'Exactlythe same11previouslyinspected2026cases; nochoicebasedon2026.', 'old':loop.pooled(old,'old'),'new':loop.pooled(new,'new')}
    c.write(c.OUT/'same-case-old-versus-new.json',result);return result


def main():
    assert (c.OUT/'loop-execution-complete.json').exists()
    import subprocess,sys
    hii_audit();community.main()
    choice=c.read(c.OUT/'global-frozen-selection.json');summary,rows=evaluate_selected(choice);uncertainty=priority_uncertainty();legacy=matched_legacy_comparison(choice)
    subprocess.run([sys.executable,'-X','utf8',str(c.ROOT/'backend/scripts/verify_fire_engineering_loop.py')],check=True)
    verification=c.read(c.OUT/'verification.json');assert verification['status']=='PASS'
    ms=loop.metas();counts=dict(Counter(meta['engineering_split'] for meta in ms));monthly={split:dict(Counter(m['initial_acquisition'][:7] for m in ms if m['engineering_split']==split)) for split in counts}
    mlresult=c.read(loop.MODEL_DIR/'test-results.json');validation=c.read(loop.MODEL_DIR/'selection.json')
    raw_metas=[c.read(path) for path in (c.OUT/'cases').glob('*/case.json')]
    exclusions=c.read(c.OUT/'array-manifest.json')['excluded']
    for row in exclusions:
        if row['id']=='2025-02-02-T47QMV-4496-19118-bank' and not row.get('reason'):
            row['reason']='AssertionError: 10kmROIextendsoutsideavailableDEMgrid; excluded ratherthanextrapolatingunknownterrain. Verifiedprepare_timed_fire_arrays.py:71.'
    c.write(c.OUT/'casebank-quality-summary.json',{'raw_triplets_ready':len(raw_metas),'model_input_ready':len(ms),'excluded_model_inputs':exclusions,
       'initial_months_by_split':monthly,'unique_initial_scene_ids':len({m['initial_scene'] for m in ms}),
       'unique_initial_dates_by_split':{split:len({m['initial_acquisition'][:10] for m in ms if m['engineering_split']==split}) for split in counts},
       'spatial_time_separation':'Newcasecentres>=12kmOR>=14daysfromacceptedcaseswithinyear. Yearholdoutisnotanunseen-geographytest.',
       'source_roles':'engineering_split is authoritative for thisnewexperiment; legacy split field preserved fororiginalscriptaudit.'})
    ablations={name:{'selected_threshold_on2025':max([key for key in validation['summary'] if key.startswith(name+'__')],key=lambda key:validation['summary'][key]['pooled_dice'])} for name in loop.CONFIGS}
    for name,row in ablations.items():
        key=row['selected_threshold_on2025'];row['validation2025']=validation['summary'][key]
        row['test_by_split']={split:scores[key] for split,scores in mlresult['by_split'].items()}
    c.write(c.OUT/'input-ablations.json',ablations)
    matched={}
    for full,other in (('point_pm','point_no_pm'),('all','all_no_pm'),('all','all_no_wind')):
        reference=ablations[full]['selected_threshold_on2025'];threshold=reference.rsplit('__',1)[1];alternate=other+'__'+threshold
        matched[full+'_versus_'+other]={'threshold_selected_from_full_on2025':threshold,
            'same_train_cases_and_sampled_pixels':True,'same_learner_iterations_leaves':True,
            'test_by_split':{split:{'full':scores[reference],'without_component':scores[alternate],
                'difference_pooled_dice_pp':100*(scores[reference]['pooled_dice']-scores[alternate]['pooled_dice'])} for split,scores in mlresult['by_split'].items()},
            'interpretation':'Matchedthresholdretrospectiveablation; notcausalevidence or automaticallysignificant.'}
    c.write(c.OUT/'matched-input-ablations.json',matched)
    files={str(path.relative_to(c.ROOT)).replace('\\','/'):c.sha(path) for path in (c.OUT/'cases').glob('*/*') if path.is_file() and (path.name in ('case.json','single-run-weather.json','model-arrays.npz','initial-supplement.npz','initial-supplement.json','corner-weather.npz','corner-weather-contract.json') or (path.suffix=='.npz' and path.name.startswith('S2')))}
    for name in ('esa-prior','himawari-bank/raw','hii-qa','native-weather'):
        for path in (c.OUT/name).glob('*'):
            if path.is_file():files[str(path.relative_to(c.ROOT)).replace('\\','/')]=c.sha(path)
    c.write(c.OUT/'frozen-final-inputs.json',{'files':files,'model_choice_sha256':c.sha(c.OUT/'global-frozen-selection.json')})
    versions={name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn','joblib','pyproj','shapely','httpx','ecmwf-opendata','eccodes')}
    c.write(c.OUT/'environment.json',versions)
    code_names=('fire_engineering_common.py','build_fire_engineering_bank.py','fire_engineering_inputs.py','run_fire_engineering_loop.py','fire_engineering_physics.py',
       'compare_himawari_priority.py','predict_fire_engineering.py','verify_fire_engineering_loop.py','probe_himawari_fire_sources.py','probe_native_weather_grid.py',
       'probe_hii_monthly_reference.py','build_timed_fire_cases.py','timed_fire_spread_benchmark.py','timed_fire_growth_ml.py','timed_fire_growth_dense.py','prepare_timed_fire_arrays.py')
    c.write(c.OUT/'code-sha256.json',{name:c.sha(c.ROOT/'backend/scripts'/name) for name in code_names})
    priority=c.read(c.OUT/'priority-himawari/test-results.json')
    decision={'status':'completed_offline_no_promotion','case_counts':counts,'initial_months_by_split':monthly,'growth_choices':len(validation['summary'])+len(physical.CONFIGS),
      'priority_fusion_choices':13,'growth_selected_on2025':choice,'growth_test_by_split':summary,
      'priority_parent_coverage_pct':priority['summary']['parent']['coverage_pct'],'priority_fusion_coverage_pct':priority['summary'][priority['selected_on2025']]['coverage_pct'],
      'retain_priority_parent':True,'deploy_growth':False,'production_changed':False,'deployment_commands_issued':0,
      'verification':'PASS','scope':'Best among documented finite choices. Retrospective, small optical casebank; no claim global optimum or universal80percent.'}
    c.write(c.OUT/'FINAL_DECISION.json',decision)
    report=f'''# ผล engineering ไฟป่าเชียงใหม่ — รอบ18ตุลาคม2026

ทำงานออฟไลน์ครบตามแผน: ขยายชุดเหตุจริง เพิ่มHimawari เพิ่มลมตัวเลขหลายตำแหน่ง เพิ่มข้อมูลพืชพรรณ/ประวัติไหม้ ทดลองตัดPM และตรึงรุ่นก่อนประเมินปี2026 ไม่มีการdeployหรือเปลี่ยนเว็บ

## คำตอบที่ใช้ตัดสินใจ

- **การเลือกพื้นที่เฝ้าระวัง12ชั่วโมง:** รุ่นเดิมยังได้36.07%ที่250กม² (6988/19372ช่อง-รอบ ใน231รอบร่วม) รุ่นเพิ่มHimawariที่เลือกจาก2025ได้{priority['summary'][priority['selected_on2025']]['coverage_pct']:.2f}% จึงยังไม่แทนรุ่นเดิม ตัวเลขนี้ไม่ใช่ความแม่นของแนวไฟลาม
- **แนวไฟลาม:** เลือก`{choice['name']}`ตระกูล`{choice['family']}`ด้วยคะแนนnew-growthDiceปี2025={100*choice['validation2025']['pooled_dice']:.2f}%ก่อนเปิดผลทดสอบปี2026 บน11เหตุเดิมเดียวกัน คะแนนเพิ่มจาก{100*legacy['old']['pooled_dice']:.2f}%เป็น{100*legacy['new']['pooled_dice']:.2f}% พื้นที่ทำนายเกินลดลง แต่ยังไม่พร้อมใช้เป็นแนวไฟที่เชื่อถือได้ ผลชุดที่เพิ่มมาแยกอยู่ตารางด้านล่าง
- **ป่าชุมชน:** ระบบช่วยจัดลำดับการเฝ้าระวังได้ในฐานะตัวช่วย แต่ยังรับรองไม่ได้ว่าป่าแต่ละแห่งจะปลอดภัยหรือไฟจะมาถึงเมื่อใด ผลระดับป่าต้องอ่านเฉพาะส่วนที่ภาพเห็นชัดและอยู่ในcasebank ไม่เหมารวม677แห่ง

## ข้อมูลและการทดสอบ

จำนวนเหตุพร้อมข้อมูล: `{counts}` รวม{len(ms)}เหตุ จากเดิม15เหตุ ฝึกเฉพาะ2024 เลือกด้วย2025 แล้วประเมิน2026ใหม่กับ2026ที่เคยตรวจแล้วแยกกัน ไม่มีการสุ่มpixelข้ามเหตุไปเป็นชุดทดสอบ

2024ที่ใช้ฝึกมีเฉพาะมีนาคม–เมษายน เพราะคลังIFSsingle-runเริ่ม14มีนาคม2024 และรอบ18Zบางวันไม่มี จึงใช้รอบ12Zที่ยืนยันว่ามีและยังอยู่ก่อนเวลาเริ่มต้น ค้นหา2025/2026ในช่วงมกราคม–เมษายน แต่เดือนที่ผ่านQCจริงต้องดูinitial_months_by_splitในFINAL_DECISION.json ไม่อ้างว่ามีตัวอย่างภาพครบทุกเดือน เพียงเพราะค้นทั้งฤดู รายชื่อข้อคัดออกอยู่ในcases/*/excluded.jsonและcasebank-quality-summary.json ไม่คัดด้วยคะแนนโมเดลหรือขนาดรอยไหม้อนาคต

ลอง{len(validation['summary'])}ตัวเลือกML/threshold/baseline และ{len(physical.CONFIGS)}สมมติฐานsurfacegraph รวม{len(validation['summary'])+len(physical.CONFIGS)}ตัวเลือกแนวไฟ เพิ่มlate-fusion12ทางเลือกกับparentอีก1สำหรับโมเดลเฝ้าระวัง การเลือกทุกทางใช้2025เท่านั้น ปี2026เคยถูกศึกษาและมีfeedbackจากรอบก่อนแล้ว จึงเป็นretrospectivevalidation ไม่ใช่ปีใหม่ที่ไม่เคยเห็น

| ชุดปี2026 | เหตุ | Diceการลามใหม่ | IoU | พื้นที่ทำนายกม² | รอยไหม้อ้างอิงกม² | ทับซ้อนกม² |
|---|---:|---:|---:|---:|---:|---:|
'''
    for split,s in summary.items():report+=f"| {split} | {s['case_count']} | {100*s['pooled_dice']:.2f}% | {100*s['pooled_iou']:.2f}% | {s['predicted_growth_km2']:.3f} | {s['reference_growth_km2']:.3f} | {s['intersection_km2']:.3f} |\n"
    report+='''
Diceนับเฉพาะพื้นที่ไหม้ใหม่ที่ทับซ้อนกัน ไม่รวมรอยไหม้ที่รู้อยู่แล้วก่อนเริ่มทาย และไม่ให้คะแนนจากพื้นที่ส่วนใหญ่ที่ไม่เกิดไฟ ระยะภาพจริง2–7วันตามแต่ละcase ไม่อ้างว่าเป็นการทดสอบแนวไฟ12ชั่วโมงหรือเวลาถึงจุดหนึ่ง

ค่าความไม่แน่นอนแบบสุ่มทั้งวันที่เริ่มเหตุ ไม่สุ่มpixelแยกกัน อยู่selected-growth-results.json ชุดเก่ามีเหตุที่ใช้ภาพช่วงเดียวกัน/พื้นที่ใกล้กัน จึงไม่ถือทุกcaseเป็นหลักฐานอิสระเต็มจำนวน คะแนนรวมสองชุดโดยไม่แยกจะทำให้เข้าใจผิด

## ข้อมูลเพิ่มช่วยอะไรจริง

| การทดลอง | สิ่งที่นำมารันจริง | ข้อกำหนด |
|---|---|---|
| Himawari | JAXAไฟย้อนหลัง nominal3ชั่วโมง/8เฟรมในgrowth และ2เฟรมในpriority | delayสมมติ3ชม.;reliability3/5nonvolcanic;ไม่ใช้FRPที่หน่วยไม่ชัด;ไม่พบจุดไม่ได้แปลว่าไฟดับ |
| ลม | ECMWFGRIBจริง0.25°อ่านu/v/หน่วย/เวลา และทดสอบส่งเข้าsurfacegraph; historical4cornersทุกcaseพร้อมactualreturnedcoords | ลมปัจจุบันไม่ใช้แทนลมอดีต;ย้อนหลังIFS49R1hindcasts ไม่ยืนยันoriginalas-issued;nearest/no-elevationdownscalingเปลี่ยนทั้งsamplingและdownscaling |
| เชื้อเพลิง/ฤดู | NDVI/NBRและการเปลี่ยนจากbaseline→initial,ปฏิทิน,ESA2023เดือนเดียวกัน0.25° | ตัวแทนสภาพพืช/ประวัติ ไม่ใช่ฟืนวัดจริง;ไม่ใช้รอยไหม้ปีเป้าหมายเป็นfeature |
| PM2.5 |35T/36TวันD-2ย้อนหลัง7วัน เทียบโมเดลมี/ไม่มีPMภายใต้learnerและthresholdbudgetเดียวกัน | ค่าพื้นหลังเมือง ไม่ใช่ค่าฝุ่นที่ทุกจุดไฟหรือหลักฐานเชิงสาเหตุ |
| HII | GeoTIFFB2F20ม.ตัวเลขจริง+CSVหน่วยไร่;uniontileไม่บวกส่วนซ้ำ | ใช้positivecorroborationรายเดือนเท่านั้น;ไม่มีobservationmask;ศูนย์unknown;HIIเองยังไม่ประเมินความแม่นในป่าอย่างเป็นทางการ |

ผลแยกตัวแปรพร้อมthresholdที่เลือกจาก2025และคะแนน2026แต่ละชุดอยู่input-ablations.json ไม่สรุปจากfeatureimportance และไม่หยิบthresholdที่ชนะ2026มาเสนอแทน

## ความเกี่ยวข้องกับป่าชุมชน

'''
    for split,s in summary.items():
        f=s['community_portions'];report+=f"- {split}: {f['observed_portion_periods']}ส่วนป่า-ช่วงภาพ/{f['unique_forests']}ป่า มีรอยใหม่อ้างอิงอย่างน้อย1ha {f['reference_positive_periods_ge1ha']}ช่วง รุ่นที่เลือกเตือน{f['warned_positive_periods']} พลาด{f['missed_positive_periods']} และเตือนแต่ไม่พบรอยถึง1haอีก{f['warned_without_reference_ge1ha']}ช่วง การไม่พบรอยไม่ใช่การยืนยันว่าไม่มีไฟ\n"
    report+=f'''
## ขอบเขตที่ต้องรู้

- ภาพอ้างอิงเป็นspectral-changecandidateตามกฎdNBR/NDVI ไม่ใช่แนวไฟสำรวจภาคสนาม มีการตรวจความไวของthreshold.10/.27 และtargetที่เชื่อมกับไฟเดิมในselected-growth-results.json
- ภาพเริ่มต้นถูกให้แก่โมเดลที่เวลาacquisitionแบบretrospective ไม่ได้จำลองเวลาประมวลผล/เผยแพร่จริง ส่วนreceiptเก็บcatalog_created
- 20ม.เป็นขนาดpixelของภาพ ไม่ใช่ความแม่นตำแหน่งแนวไฟ20ม.;ลม9กม./0.25°กับภูมิประเทศหยาบไม่ได้กลายเป็นข้อมูล20ม.เพียงเพราะinterpolate
- surfacegraphใช้surface-rate+graph8ทิศ ไม่ใช่fullELMFIRE ไม่มีcrownfire/spotting/การดับไฟ pyretechnicsมีเงื่อนไขcommunity/commerciallicense ไม่อ้างว่าเป็นOSIopensourceแบบใช้ได้ไม่จำกัด
- HIIกับreferenceเราใช้Sentinel-2ร่วมกัน จึงไม่ใช่independentsensorหรือหลักฐานตรวจถูกทั้งหมดในป่า
- การเพิ่มHimawariในpriorityต่าง{uncertainty['delta_percentage_points']:+.3f}จุดเปอร์เซ็นต์ ช่วง95%แบบ7วัน={uncertainty['paired_circular7day_block95_pp']} จึงไม่กล่าวว่าเพิ่มaccuracyอย่างมั่นคง
- ไม่มีเกณฑ์เดียวที่ทำให้คำว่า80%เทียบได้ทุกงาน การตรวจพบhotspot,fire/no-fireaccuracy,Diceรอยไหม้ใหม่ และรวมรอยเก่าเป็นคนละโจทย์

## ของที่รันซ้ำได้และสถานะจบงาน

- FINAL_DECISION.json: รุ่นที่เลือก จำนวนทดลอง ผลและคำตัดสินไม่promote
- models/:9ชุดน้ำหนัก+featurecontract+protocol+frozen2025selection
- physics/:6สมมติฐานและผลตัวที่เลือก
- priority-himawari/:13ทางเลือก,231รอบ2025/231รอบ2026,paireduncertainty
- cases/:ภาพก่อน/เริ่ม/หลัง,weatherจากrunเดียว,inputs,reference,prediction,ข้อคัดออกและSHA
- replay-selected/:initializationbundleที่ไม่มีภาพหลังหรือtargetlabel และผลทำนายที่เท่ากับbenchmarkทุกpixel ตัวที่ชนะไม่ต้องใช้Himawari/ESA/corner-grid/PMในขั้นทำนาย
- verification.json:checksผ่าน รวมfuturePMpoisoning,ทิศลม,barrier,temporalalignment,exactreplayparity,ไฟล์production6ไฟล์และsourceเดิม97ไฟล์ยังเดิม
- frozen-final-inputs.json/environment.json:hashและเวอร์ชันสำหรับตรวจซ้ำ

ผลส่งออกมีapplicability20/initial_clear20/known_initial_scar20แยกจากpredicted พื้นที่นอกขอบเขตที่โมเดลใช้ได้หมายถึงไม่ทราบหรือโมเดลไม่ครอบคลุม ห้ามแสดงเป็นพื้นที่ปลอดไฟ

ถ้าจะเพิ่มความแม่นรอบถัดไป มีแผนทดลอง5ข้อพร้อมprimarysourcesและเกณฑ์หยุดใน`docs/research/2026-10-18-next-model-improvements.md`: แยกสถานะไฟกำลังไหม้/รอยเก่า/ไม่ทราบและเหตุจุดใหม่, เพิ่มB11/NDMIกับบริบทภาพตามเวลา, แบ่งกลุ่มเหตุจริง+hardnegatives, อุ่นสถานะความชื้นเฉพาะพื้นที่ด้วยข้อมูลก่อนเวลาเริ่ม, และcalibrateพร้อมงดฟันธงเมื่อไม่มั่นใจ แผนเหล่านี้ไม่ถูกอ้างว่าได้เพิ่มaccuracyแล้ว และไม่ได้เปลี่ยนรุ่นที่ตรึงไว้หลังเห็นผล2026

รันตัวทำนายออฟไลน์โดยไม่ฝึกใหม่:

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/predict_fire_engineering.py --case-id {verification['full']['labels_free_replay_case']} --prepare-bundle
```

จบรอบengineeringตามขอบเขตที่อนุมัติแล้ว ผลดีที่สุดคือดีที่สุดในชุดทดลองที่บันทึกนี้ ไม่ใช่คำรับรองglobaloptimum ระบบเฝ้าระวังเดิมยังเป็นcandidateหลัก การทำนายแนวไฟยังไม่พร้อมให้ชุมชนถือเป็นแนวไฟจริง ไม่มีงานdeployค้างและไม่มีการเปลี่ยนเว็บในรอบนี้

แหล่งหลัก: [JAXAP-Tree](https://www.eorc.jaxa.jp/ptree/),[ECMWFOpenData](https://www.ecmwf.int/en/forecasts/datasets/open-data),[OpenMeteoSingleRuns](https://open-meteo.com/en/docs/single-runs-api),[ESACEDA2023](https://data.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN/grid/v1.1/2023/),[HII](https://tamroypao.hii.or.th/),[HIIpublicnumericfiles](https://tamroypao.hii.or.th/product/B2F/2026/)
'''
    (c.OUT/'FINAL_RESULTS_TH.md').write_text(report,encoding='utf8')
    print('FINAL_ENGINEERING_COMPLETE',decision['case_counts'],choice['name'],flush=True)


if __name__=='__main__':main()
