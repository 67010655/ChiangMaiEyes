import hashlib,json
from pathlib import Path
from shapely.geometry import shape,mapping
from shapely.ops import transform
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/grid-spread-validation-20261017'
report=json.loads((OUT/'summary.json').read_text(encoding='utf8'));example=json.loads((OUT/'example.json').read_text(encoding='utf8'))
to_m=Transformer.from_crs(4326,32647,always_xy=True).transform;to_ll=Transformer.from_crs(32647,4326,always_xy=True).transform
example['weekly_reference']=mapping(transform(to_ll,transform(to_m,shape(example['weekly_reference'])).simplify(20,preserve_topology=True)))
example['display_simplification_m']=20
report['example']=example
report['decision_th']='รุ่นกริดยังไม่มีหลักฐานว่าชนะวิธีวงรอบจุดเดิมที่ใช้พื้นที่เท่ากัน จึงเปิดให้เปรียบเทียบและคงรุ่นหลักไว้ในสถานะทดลอง'
report['notes_th']=['ใช้กรณีเริ่ม 02:00 ทุกวันจากข้อมูลที่รู้ก่อนเริ่ม ตัด confidence ต่ำออก ใช้เชื้อเพลิง FM1 ความชื้น 8% ลม ×0.2 โดยไม่ปรับตามรอยเผา',
  'ทางลาดเปลี่ยนทุกช่อง WorldCover ปี 2021 ใช้เป็นหน้ากากสิ่งปกคลุมดิน ไม่ใช่ข้อมูลเชื้อเพลิงหรือถนนที่วัดจริงปี 2026',
  'ทดสอบ 35 วัน / 411 จุดใน 23 มีนาคม–30 เมษายน; กรณีที่ไม่มีจุดภายหลังไม่ถูกนับว่าทำนายถูก และวันติดกันอาจเป็นไฟเดียวกัน',
  'เฉพาะ 23/35 กรณีทดสอบมีรอยเผาอ้างอิงพร้อมจำนวนภาพบางส่วน ไม่เติมกรณีข้อมูลขาดเป็นไม่มีไฟ',
  'รอยเผา B4 ของ TamRoyPao มาจาก Sentinel-2 ราย 7 วัน ผู้ผลิตยังไม่ประเมินความแม่นยำในป่าอย่างเป็นทางการและมีข้อจำกัดเมฆ/เรือนยอด',
  'ไม่มีข้อมูลยืนยันการมาถึงของไฟระดับ 6 ชั่วโมง จึงแสดงความสอดคล้องกับรอยเผา ไม่เรียกเป็น accuracy ของขอบเขตไฟ',
  'พื้นที่เป็นผลรวมรายกรณีซึ่งอาจซ้อนกัน ไม่ใช่ยอดพื้นที่ไหม้รวมของจังหวัด; แผนที่ตัวอย่างลดรายละเอียด 20 เมตรเฉพาะการแสดงผล',
  'WorldCover nearest-neighbour และกราฟ 8 ทิศอาจพลาดพื้นที่แคบและมีความคลาดเชิงตัวเลข; ไม่มีการคำนวณสะเก็ดไฟหรือการดับไฟ']
report['cases']=[{'id':c['id'],'split':c['split'],'points':c['points'],'models':c['models'],
    'weekly_reference':c['weekly_reference'],'grid_excluded':c['grid_excluded'],'truncated':c['truncated']} for c in report['cases']]
report['source_files_downloaded']=len(list((ROOT/'output/burn-reference-research/tiles').glob('*.tif')))
report['software_sources']=[{'name':'GeoMaster','url':'https://skills.sh/k-dense-ai/scientific-agent-skills/geomaster',
    'commit':'a1043ef544e3a100c28e70a736b6cf32554d0677','use':'CRS alignment, categorical resampling, QA and evidence limits'}]
target=ROOT/'backend/app/data/grid-spread-validation.json';target.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')),encoding='utf8')
print({'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'reference_tiles':report['source_files_downloaded']})
