"""Human-readable offline model decision and frozen candidate package."""
import hashlib,json,math,shutil
from pathlib import Path
import joblib,numpy as np
from joint_fire_experiment import OUT,ROOT,GROUPS,COLS,ALL_NAMES,read,write

NAMES={'hotspot_context':'Hotspot + ข้อมูลพื้นฐาน','hotspot_wind':'Hotspot + ลม','hotspot_pm':'Hotspot + PM2.5','hotspot_wind_pm':'Hotspot + ลม + PM2.5'}
def group(model):return model.split('__')[0]
def intervals(rows,pairs):
    names=list(dict.fromkeys(n for pair in pairs.values() for n in pair));byday={}
    for row in rows:
        v=byday.setdefault(row['issued_at'][:10],np.zeros(len(names)+1));v[0]+=row['target_cells_all']
        for i,n in enumerate(names,1):v[i]+=row['scores'][n]['250.0']['hits']
    matrix=np.array(list(byday.values()));rng=np.random.default_rng(20261017);draws=[]
    for _ in range(4000):
        starts=rng.integers(0,len(matrix),math.ceil(len(matrix)/7));idx=np.concatenate([(s+np.arange(7))%len(matrix) for s in starts])[:len(matrix)];draws.append(matrix[idx].sum(axis=0))
    d=np.array(draws);total=matrix.sum(axis=0)
    return {label:{'gain_percentage_points':float(100*(total[names.index(a)+1]-total[names.index(b)+1])/total[0]),
      'moving_block7day_95pct':list(np.percentile(100*(d[:,names.index(a)+1]-d[:,names.index(b)+1])/d[:,0],[2.5,97.5]))} for label,(a,b) in pairs.items()}
def main():
    result=read(OUT/'summary.json');selection=result['selection'];chosen=selection['chosen_per_group'];rows=read(OUT/'results-2026.json')['rows']
    pairs={'add_wind_to_hotspot':(chosen['hotspot_wind'],chosen['hotspot_context']),
      'add_pm_to_hotspot':(chosen['hotspot_pm'],chosen['hotspot_context']),
      'add_pm_to_hotspot_wind':(chosen['hotspot_wind_pm'],chosen['hotspot_wind']),
      'add_wind_to_hotspot_pm':(chosen['hotspot_wind_pm'],chosen['hotspot_pm'])}
    comparisons=intervals(rows,pairs);write(OUT/'component-effects.json',comparisons)
    primary=selection['selected_primary'];test=result['test'];n=test['target_cells'];k=250/.25
    folder=OUT/'candidate';folder.mkdir(exist_ok=True);shutil.copyfile(OUT/(primary+'.joblib'),folder/'model.joblib')
    spec={'mode':'offline_experimental_candidate','model_selected_on2025':primary,'group':group(primary),'feature_columns':COLS[group(primary)],
      'feature_names':[ALL_NAMES[c] for c in COLS[group(primary)]],'full_feature_order':ALL_NAMES,
      'model_sha256':hashlib.sha256((folder/'model.joblib').read_bytes()).hexdigest(),'grid_sha256':hashlib.sha256((ROOT/'output/priority-forecast-20261017/grid.npz').read_bytes()).hexdigest(),
      'target':'Next12h nominal/high VIIRS detection in500m cells, not fire perimeter','hotspot_delay_hours':3,'pm_latest_date_lag_days':2,
      'unit':'rank score; not calibrated fire probability','not_for_automatic_dispatch':True,'production_changed':False}
    write(folder/'feature-contract.json',spec)
    training=read(OUT/'training-receipt.json');audit=read(OUT/'input-audit.json')
    text=f'''# โมเดล Hotspot + ลม + PM2.5 — ทดลองในเครื่องเท่านั้น

สถานะ: ทดลองครบ4กลุ่ม เลือกค่าด้วย2025 แล้วประเมิน2026 ไม่ deploy และไม่เพิ่ม/แก้เนื้อหาบนเว็บ

## สิ่งที่เปลี่ยนจากรอบก่อน

รุ่นเดิม35%ยังไม่มีPM2.5และมีเพียงความเร็วลมจากจุดอ้างอิงเดียว รอบนี้เพิ่มลมGFS12ตำแหน่ง แปลงทิศลมเป็นเวกเตอร์east/northและทิศสัมพันธ์ระหว่างhotspotกับแต่ละช่องพื้นที่ และเพิ่มPM2.5ที่วัดได้จริงจากPCD/Air4Thai35T/36Tย้อนหลัง3ฤดู

ข้อมูล2024มีPM242station-days,2025/2026ปีละ239station-days ใช้เฉพาะวันที่ไม่เกินวันออกผลลบ2วัน ไม่ใช้ค่าฝุ่นที่เกิดหลังเวลาออกผล ป้ายdaily24hมีข้อจำกัดexact-windowและเวลาเผยแพร่ จึงเป็นสมมติฐานavailabilityที่ระบุไว้ ไม่ใช่หลักฐานรับข้อมูลจริง

ฝึก2024: {len(training['issues'])}รอบ,{training['rows']:,}ตัวอย่าง,{training['positive_cells']:,}positive cells เลือกค่าจาก2025:{result['validation']['issues']}รอบ ตรวจ2026:{test['issues']}รอบ/{n:,}ช่อง-รอบที่มีจุดความร้อน ความครบของลม2024ช่วงต้นปีขาด444ชั่วโมง จึงข้ามรอบที่ข้อมูลไม่ครบ ไม่มีการเติมค่าที่ขาดด้วยศูนย์

ทุกกลุ่มใช้ภูมิประเทศ/สิ่งปกคลุมดิน/ปฏิทินและอุณหภูมิ/RH/ฝน/แสงอาทิตย์พื้นฐานเหมือนกัน ชื่อHotspotในตารางย่อจากHotspot+context เปรียบเทียบลม/PMได้โดยไม่เปลี่ยนองค์ประกอบพื้นฐาน

## ผลเปรียบเทียบที่พื้นที่เฝ้าระวัง250ตร.กม.เท่ากัน

| กลุ่ม | รุ่นที่เลือกบน2025 | ครอบคลุม2025 | ครอบคลุม2026 | จำนวนที่ตรง2026 |
|---|---|---:|---:|---:|
'''
    for g,model in chosen.items():
        val=result['validation']['scores'][model]['250.0']['hits'];hits=test['scores'][model]['250.0']['hits']
        text+=f"| {NAMES[g]} | {model.split('__')[1]} | {100*val/result['validation']['target_cells']:.1f}% | {100*hits/n:.1f}% | {hits:,}/{n:,} |\n"
    for model,label in [('previous_boost15','รุ่นก่อน35% (วัดใหม่บนวันเดียวกัน)'),('kernel','วิธีฐานระยะ/อายุhotspotที่ปรับบน2025')]:
        hits=test['scores'][model]['250.0']['hits'];text+=f"| {label} | คงเดิม | — | {100*hits/n:.1f}% | {hits:,}/{n:,} |\n"
    hits=test['scores'][primary]['250.0']['hits'];old=test['scores']['previous_boost15']['250.0']['hits'];base=test['scores']['kernel']['250.0']['hits']
    text+=f'''
รุ่นหลักที่เลือกจาก2025ก่อนดู2026คือ **{primary}** ({NAMES[group(primary)]}) ได้{100*hits/n:.1f}%ใน2026 เทียบรุ่นก่อนที่{100*old/n:.1f}% และวิธีฐาน{100*base/n:.1f}% การที่บางกลุ่มทำคะแนน2026สูงกว่าไม่ได้ใช้เปลี่ยนการเลือกย้อนหลัง คะแนนยังไม่ใช่accuracyรวมของเว็บหรือขอบไฟจริง

## การเติมลมและPMช่วยเท่าไร

| เปรียบเทียบ | ผลเพิ่มใน2026 (จุดเปอร์เซ็นต์) | ช่วง95%แบบบล็อก7วัน |
|---|---:|---:|
'''
    labels_={'add_wind_to_hotspot':'เพิ่มลมให้Hotspot','add_pm_to_hotspot':'เพิ่มPMให้Hotspot','add_pm_to_hotspot_wind':'เพิ่มPMให้Hotspot+ลม','add_wind_to_hotspot_pm':'เพิ่มลมให้Hotspot+PM'}
    for label,value in comparisons.items():
        lo,hi=value['moving_block7day_95pct'];text+=f"| {labels_[label]} | {value['gain_percentage_points']:+.2f} | {lo:+.2f}ถึง{hi:+.2f} |\n"
    text+='\nช่วงที่คร่อม0ยังไม่ชัดว่าช่วยเพิ่ม การเปรียบเทียบนี้เป็นกลุ่มโมเดลที่เลือกhyperparameterแยกกันบน2025 ไม่ใช่การพิสูจน์เหตุและผลของตัวแปรทางกายภาพ\n\n'
    text+='## ส่วนที่ไม่ใช่แค่ทายซ้ำจุดใกล้เดิม\n\n'
    expansion=test['expansion_target_cells'];text+=f'ตรวจเฉพาะช่องที่ห่างhotspotก่อนหน้าเกิน500เมตรแต่ไม่เกิน5กม.: {expansion:,}ช่อง-รอบ การตรวจพบนี้อาจเป็นไฟลามหรือจุดติดไฟใหม่ ยังไม่ได้แยกเหตุจริง\n\n'
    for g,model in chosen.items():
        h=test['scores'][model]['250.0']['expansion_hits'];text+=f'- {NAMES[g]}: {h:,}/{expansion:,} ({100*h/expansion:.1f}%)\n'
    text+='\n## ขนาดพื้นที่และความเสี่ยงที่พลาด\n\n| พื้นที่ต่อรอบ | ครอบคลุม | พลาด | ช่องที่เลือกแล้วมีจุดดาวเทียมภายหลัง |\n|---|---:|---:|---:|\n'
    for b in (125.,250.,500.):
        h=test['scores'][primary][str(b)]['hits'];recall=100*h/n;observed=100*h/(test['issues']*b/.25)
        text+=f'| {b:.0f}ตร.กม. | {recall:.1f}% | {100-recall:.1f}% | {observed:.2f}% |\n'
    text+='\nการไม่พบดาวเทียมยังยืนยันว่าไม่มีไฟหรือเป็นfalse alarmไม่ได้ แต่จำนวนช่องที่เลือกมากแสดงภาระการเฝ้าระวัง ต้องไม่แปลคะแนนครอบคลุมเป็นเปอร์เซ็นต์ว่าตำแหน่งที่เตือนจะมีไฟจริง\n\n'
    text+='## ผลรายเดือนของรุ่นหลัก\n\n| เดือน2026 | ช่อง-รอบที่มีจุดภายหลัง | รุ่นหลัก | รุ่นก่อน |\n|---|---:|---:|---:|\n'
    for month,value in result['monthly_test'].items():
        total=value['target_cells'];a=value['scores'][primary]['250.0']['hits'];b=value['scores']['previous_boost15']['250.0']['hits']
        text+=f'| {month} | {total:,} | {100*a/total:.1f}% | {100*b/total:.1f}% |\n'
    text+='''
## ขอบเขตหลักฐานและไฟล์ส่งต่อ

- เป็นretrospective comparisonข้าม3ปี ปี2026เคยถูกตรวจจากงานก่อนแล้ว ไม่ใช่ฤดูอนาคตที่ยังไม่เคยดู และไม่ได้ปรับค่าตามผล2026ในรอบนี้
- เป้าหมายคือดาวเทียมพบจุดความร้อนในช่อง500เมตรภายใน12ชั่วโมง ไม่ใช่ขอบไฟลามที่ยืนยันจริงหรือเวลาที่ไฟเข้าป่า
- ลม12ตำแหน่งเป็นGFScoarse samples ยังไม่ใช่ลมในหุบเขาระดับช่อง500เมตร PMเป็นสองสถานีเมือง ไม่ใช่แผนที่ค่าฝุ่นทั่วจังหวัด
- ข้อมูลhotspotใช้เวลาตรวจ+3ชั่วโมงเป็นproxyavailability;GFSprevious-day1เป็นเวลานำ24ชั่วโมงต่อvalid time ไม่ใช่คลังissueเดียวที่ล็อกไว้;PMใช้วันย้อนหลัง2วันตามสมมติฐานข้างต้น
- sampled negativesทำให้คะแนนโมเดลเป็นrankscore ยังไม่ใช่ความน่าจะเป็นไฟที่สอบเทียบแล้ว
- ไม่จำเป็นต้องรอออกหน้างานเพื่อทำขั้นทดลองนี้ ข้อมูลภาคสนามจะช่วยสอบเทียบในภายหลังได้

ไฟล์candidate/model.joblibและcandidate/feature-contract.jsonเป็นตัวทดลองที่ถูกเลือก ส่วนprotocol.json,selection.json,results-2025.json,results-2026.json,component-effects.jsonเก็บวิธีเลือกและผลรายรอบให้ตรวจซ้ำได้ ไม่ได้นำไฟล์เหล่านี้ไปใช้บนเว็บจริง

แหล่งข้อมูล: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/),[GFS previous-runs](https://open-meteo.com/en/docs/previous-runs-api),[Air4Thai daily export2024](https://air4thai.net/daily_download/PM2.5/2024.xlsx),[2025](https://air4thai.net/daily_download/PM2.5/2025.xlsx),[2026](https://air4thai.net/daily_download/PM2.5/2026.xlsx). Manifestและhashต้นฉบับอยู่ในโฟลเดอร์ทดลอง
'''
    (OUT/'RESULTS.md').write_text(text,encoding='utf8')
    write(OUT/'decision.json',{'primary_model_selected_on2025':primary,'primary_group':group(primary),'test_target_cells':n,
       'primary_coverage_250_pct':100*hits/n,'previous_coverage_250_pct':100*old/n,'baseline_coverage_250_pct':100*base/n,
       'component_effects':comparisons,'production_changed':False,'candidate_sha256':spec['model_sha256']})
    print('OFFLINE DECISION',json.dumps(read(OUT/'decision.json')),flush=True)
if __name__=='__main__':main()
