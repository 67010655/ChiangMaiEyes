"""One-time, bounded markup migration. Preserve operational element IDs."""
from pathlib import Path
import re

p=Path('frontend/index.html')
s=p.read_text(encoding='utf-8')

def block(text,marker,tag='div'):
    start=text.index(marker);depth=0
    for m in re.finditer(rf'</?{tag}\b[^>]*>',text[start:]):
        depth += -1 if m.group().startswith('</') else 1
        if depth==0:return text[start:start+m.end()]
    raise ValueError(marker)

guide=block(s,'  <div class="guideview" id="guideview">')
sections=re.findall(r'      <section class="data-review"[\s\S]*?</section>',guide)
assert len(sections)==5, len(sections)  # admin archive jobs share the validation section
cameras=next(x for x in sections if 'id="camerasHeading"' in x)
data_sections=[x for x in sections if x!=cameras]
aqi=block(guide,'        <details class="gd-card" id="aqiDetails">','details')
notes=block(guide,'      <details class="gd-card" id="guideNotesCard">','details')

subnav='''<div class="workspace-links" aria-label="ส่วนของหน้าวิเคราะห์">
  <button type="button" data-open-view="analytics">สรุปย้อนหลัง</button>
  <button type="button" data-open-view="data">ข้อมูลในพื้นที่</button>
  <button type="button" data-open-view="report">สร้างรายงาน</button>
</div>'''

data='''  <div class="guideview" id="dataview">
    <div class="rp-toolbar"><div class="ttl">ข้อมูลในพื้นที่</div><button type="button" class="an-close" data-open-view="analytics" aria-label="กลับหน้าวิเคราะห์">✕</button></div>
    <div class="gd-body">'''+subnav+'''
      <p class="workspace-intro">เลือกดูข้อมูลที่ใช้ประกอบการอ่านพื้นที่ รายละเอียดเฉพาะทางเปิดเพิ่มได้เมื่อจำเป็น</p>
      <details class="data-section"><summary id="airDataHeading">ค่าฝุ่นและเวลาของข้อมูล</summary><div id="evidenceFreshness" class="evidence-freshness"></div>'''+aqi+'''</details>
'''+ '\n'.join(data_sections)+'''
    </div>
  </div>'''
# Fold specialist sections; forest selection and history stay immediately usable.
for heading,label in [('ventilationHeading','การระบายอากาศจากแบบจำลอง'),('fieldEvaluationHeading','ผลตรวจเทียบในพื้นที่')]:
    section=next(x for x in data_sections if f'id="{heading}"' in x)
    data=data.replace(section,f'<details class="data-section"><summary>{label}</summary>{section}</details>')

camera_page='''  <div class="guideview" id="cameraview">
    <div class="rp-toolbar"><div class="ttl">กล้องสาธารณะ</div><button type="button" class="an-close" data-open-view="home" aria-label="กลับแผนที่">✕</button></div>
    <div class="gd-body"><p class="workspace-intro">ภาพประกอบการสังเกตพื้นที่ ดูชื่อสถานที่และเวลาบนภาพก่อนใช้</p>'''+cameras+'''</div>
  </div>'''

guide_new='''  <div class="guideview" id="guideview">
    <div class="rp-toolbar"><div class="ttl">คู่มือเริ่มใช้งาน</div><button class="an-close" id="guideClose" aria-label="กลับหน้าสถานการณ์">✕</button></div>
    <div class="gd-body reader-guide">
      <h1>เริ่มดูไฟและฝุ่นในเชียงใหม่</h1>
      <p class="guide-lead">ChiangMaiEyes รวบรวมจุดความร้อน ฝุ่น ลม และขอบเขตป่าชุมชน 677 แห่ง เพื่อช่วยดูสถานการณ์และประสานผู้ดูแลพื้นที่ เปิดอ่านแผนที่ได้โดยไม่ต้องสมัคร</p>
      <ol class="guide-steps">
        <li><h2>เลือกพื้นที่ที่อยากดู</h2><p>เปิดหน้าสถานการณ์ แล้วค้นหาอำเภอ ตำบล หรือพิกัด ใช้แผนที่ 2D เพื่อเริ่มดูพื้นที่ เปลี่ยนเป็น 3D เมื่อต้องการเห็นภูเขา หรือเปิดภาพกล้องสาธารณะประกอบ</p></li>
        <li><h2>กดจุดความร้อนและอ่านเวลา</h2><p>หมุดคือสิ่งที่ดาวเทียมตรวจพบ กดเพื่อดูเวลาตรวจพบและรายละเอียด จุดจางเป็นข้อมูลเกิน 24 ชั่วโมง ต้องสอบถามคนในพื้นที่ก่อนยืนยันว่าไฟยังไหม้ การไม่พบหมุดก็ยังสรุปว่าไม่มีไฟไม่ได้</p></li>
        <li><h2>ดูฝุ่นและลมประกอบ</h2><p>ฝุ่นหน้าแรกใช้ค่าจากสถานีที่มีข้อมูล หน่วย µg/m³ ลูกศรลมชี้ไปทางที่ลมพัดไป อ่านแหล่งและเวลาด้วย แบบจำลองลมเคลื่อนไหว 10 เมตรกับลมสถานีเป็นคนละชุด</p></li>
        <li><h2>ตรวจสอบและติดตามเรื่อง</h2><p>ผู้ดูแลชุมชนเข้าสู่ระบบและขออนุมัติพื้นที่ใน “ป่าของฉัน” จึงบันทึกหรือประสานเหตุได้ ใช้ “ติดตามเหตุ” ดูงานที่เกี่ยวข้อง หากต้องดูแนวโน้มหรือทำเอกสาร ให้เปิด “วิเคราะห์” แล้วเลือกย้อนหลังหรือสร้างรายงาน</p></li>
      </ol>
      <button class="evidence-action" type="button" data-open-view="home">เริ่มดูแผนที่</button>
      <details class="guide-topic"><summary>สมัครและรับอีเมลแจ้งเตือนอย่างไร</summary><p>สมัครและยืนยันอีเมล ขอเป็นตัวแทนป่าที่ดูแล รอผู้ดูแลอนุมัติ แล้วเลือกเปิดรับอีเมลใน “ป่าของฉัน” ระบบส่งตามพื้นที่ที่ได้รับอนุมัติ เมื่อเปิดบริการส่งแล้วไม่ต้องเปิดเว็บค้างไว้ ขณะนี้การส่งถึงสมาชิกทั่วไปยังรอยืนยันโดเมนผู้ส่งและตั้งค่าอีเมล</p></details>
      <details class="guide-topic"><summary>ถ้าขึ้นว่าไม่มีข้อมูลหรือข้อมูลเก่า</summary><p>หมายถึงระบบยังไม่ได้ค่าที่ใช้ได้ในรอบนั้น ไม่ได้แปลว่าฝุ่นเป็นศูนย์หรือพื้นที่ปลอดภัย เปิด “วิเคราะห์ → ข้อมูลในพื้นที่” เพื่อดูแหล่งและเวลา หากมีเพียง AQI จะระบุว่าเป็นดัชนี ไม่แปลงเป็น PM2.5</p></details>
      <details class="guide-topic" id="guideMethods"><summary>ตัวเลขคำนวณและคาดการณ์อย่างไร</summary>
        <dl class="guide-methods">
          <dt>จำนวนจุดความร้อน</dt><dd>นับรายการตรวจพบในช่วงเวลาที่เลือก รวมรายการซ้ำที่พิสูจน์ว่าเป็นการตรวจพบเดียวกันตามแหล่ง เวลา ดาวเทียม และตำแหน่ง หนึ่งจุดยังไม่ใช่หนึ่งเหตุไฟที่คนยืนยัน</dd>
          <dt>ฝุ่นหน้าแรก</dt><dd>เฉลี่ยความเข้มข้นจากสถานีเชียงใหม่ที่ต้นทางมีค่าในชุดนั้น แต่ละสถานีแทนจุดติดตั้ง ไม่ใช่การวัดทุกป่าหรือทุกบ้าน AQI แสดงแยกจาก µg/m³</dd>
          <dt>ภูมิประเทศ</dt><dd>Copernicus GLO-30 เป็นพื้นผิวรวมต้นไม้และอาคาร นำมาทำกริด 30 เมตรใน UTM 47N แล้วคำนวณความชัน Horn 3×3 สรุปพิกเซลที่ศูนย์กลางอยู่ในขอบเขตป่า ค่ากลางของป่าไม่ใช่ความชันที่จุดไฟทุกจุด</dd>
          <dt>ดัชนีอากาศแห้งทดลอง</dt><dd>ใช้ (100 − ความชื้นสัมพัทธ์)/100 และลดครึ่งเมื่อฝนที่รายงานมากกว่า 1 mm เป็นเกณฑ์ทดลองจากอากาศอ้างอิงร่วม ยังไม่ใช่ปริมาณเชื้อเพลิงหรือโอกาสเกิดไฟรายป่า</dd>
          <dt>พยากรณ์อากาศและฝุ่น</dt><dd>อากาศล่วงหน้าจาก Open-Meteo และฝุ่นจาก CAMS เป็นแบบจำลองตามกริดและจุดอ้างอิง ดูรอบแบบจำลองและเวลาที่ข้อมูลแทน แยกจากค่าตรวจวัดสถานี</dd>
          <dt>การระบายอากาศ</dt><dd>อ่าน HPBL ลมในชั้น PBL และ VRATE ของ NOAA GFS โดยตรง หน่วย m, m/s และ m²/s เป็นคนละระดับกับลม 10 เมตร ไม่ใช้ยืนยันค่าฝุ่นในป่าหรือความปลอดภัย</dd>
          <dt>ไฟจะลามไปไหน</dt><dd>ยังไม่มีผลทำนายตำแหน่ง อัตรา หรือระยะไฟลามที่สอบเทียบแล้ว ภาพทิศปลายลมเป็นภาพประกอบ ต้องมีข้อมูลเชื้อเพลิง ความชื้น และเหตุจริงสำหรับตรวจแบบจำลองก่อนแสดงผลประเภทนี้</dd>
        </dl>
      </details>
      <details class="guide-topic" id="guideReferences"><summary>แหล่งข้อมูลและเอกสารอ้างอิง (References)</summary><p>แต่ละแหล่งมีหน้าที่และข้อจำกัดต่างกัน กดชื่อแหล่งเพื่ออ่านต้นทาง</p><div id="evidenceSources" class="source-grid"></div><p>สูตรสรุปและการเชื่อมข้อมูลที่อธิบายด้านบนเป็นวิธีของ ChiangMaiEyes แหล่งข้อมูลไม่ได้รับรองผลคำนวณหรือความแม่นยำของเว็บนี้</p></details>
'''+notes+'''
    </div>
  </div>'''
s=s.replace(guide,guide_new+'\n'+data+'\n'+camera_page)

for view in ['threed','report']:
    nav=block(s,f'      <div class="nav-item" data-view="{view}"');s=s.replace(nav+'\n','')
s=s.replace('<span>หน้าหลัก</span>','<span>สถานการณ์</span>',1)
s=s.replace('title="ข้อมูลย้อนหลัง กล้องสาธารณะ และที่มาข้อมูล"','title="เริ่มใช้งาน วิธีอ่านข้อมูล และเอกสารอ้างอิง"',1)
s=s.replace('<span>ข้อมูล</span>','<span>คู่มือ</span>',1)

map_modes='''<div class="map-view-actions" aria-label="มุมมองสถานการณ์"><span>แผนที่ 2D</span><button type="button" data-open-view="threed">ดูภูเขา 3D</button><button type="button" data-open-view="cameras">ดูกล้องสาธารณะ</button></div>'''
anchor='    <main class="mapwrap"'
start=s.index(anchor);idx=s.index('>',start)+1;s=s[:idx]+'\n'+map_modes+s[idx:]
s=s.replace('    <div class="an-body">','    <div class="an-body">\n'+subnav,1)
# Reports keep their full export workflow, entered from the analysis group.
report=block(s,'  <div class="reportview" id="reportview">')
toolbar=block(report,'    <div class="rp-toolbar">');s=s.replace(toolbar,toolbar+'\n'+subnav,1)

start=s.index("document.querySelectorAll('.nav-item').forEach(it=>{");end=s.index("document.getElementById('guideClose').onclick",start)
s=s[:start]+'''CmeNavigation.init({
  close:()=>{closeAllOverlays();closeMobileDrawers();},
  views:{
    home:()=>setTimeout(()=>map.invalidateSize(),60),
    analytics:()=>{analyticsEl.classList.add('open');renderAnalytics(currentRange);},
    report:openReport,threed:open3D,
    phase:()=>CmeCommunity.open('incidents'),community:()=>CmeCommunity.open('forest'),
    guide:()=>document.getElementById('guideview').classList.add('open'),
    data:()=>{document.getElementById('dataview').classList.add('open');renderAqiStations();loadArchive();loadFieldEvaluation();},
    cameras:()=>{document.getElementById('cameraview').classList.add('open');loadPublicCameraDirectory();startCameraDirectoryRefresh();}
  }
});
'''+s[end:]
start=s.index("document.getElementById('guideClose').onclick");end=s.index("document.getElementById('anClose').onclick",start)
s=s[:start]+"document.getElementById('guideClose').onclick=()=>CmeNavigation.open('home');\n"+s[end:]
s=s.replace("  document.getElementById('guideview').classList.remove('open');","  ['guideview','dataview','cameraview'].forEach(id=>document.getElementById(id).classList.remove('open'));",1)
s=s.replace("document.getElementById('guideview').classList.contains('open')","document.getElementById('cameraview').classList.contains('open')")
s=s.replace("n.dataset.view==='report'","n.dataset.view==='analytics'")
s=s.replace("exportForest:id=>{closeAllOverlays();openReport();","exportForest:id=>{CmeNavigation.open('report');")
s=s.replace(' · ดูในข้อมูล',' · ดูในวิเคราะห์')
s=s.replace('  const aqi=Math.round(pmAvg*1.6+20);','  // Composite AQI is supplied by its source; it is not computed from an ad-hoc PM formula.')
s=s.replace("document.getElementById('kpiAqi').textContent=pmReady?aqi:'—';","document.getElementById('kpiAqi').textContent='ดูรายสถานี';")
s=s.replace("document.getElementById('kpiAqi').style.color = aqi>150?'#ff4d4d':aqi>100?'#ff8a3d':'#facc15';","document.getElementById('kpiAqi').style.color='var(--muted)';")
s=s.replace("pmReady?`${pmAvg} µg/m³`:'ยังไม่มีข้อมูล'","pmReady?`${pmAvg} µg/m³`:'ยังอ่านค่าจากสถานีไม่ได้'")
s=s.replace("'รอค่า PM2.5 ที่วัดได้'","'ตรวจแหล่งและเวลาใน วิเคราะห์ → ข้อมูลในพื้นที่'")
s=s.replace("document.getElementById('publicPmMeta').textContent=pmReady?`${pmStations.length} สถานีที่วัด ·", "document.getElementById('publicPmMeta').textContent=pmReady?`Air4Thai ${pmStations.length} สถานี ·")
s=s.replace('<script src="/ux-clarity.js"></script>','<script src="/ux-clarity.js"></script>')
main_script=s.index('<script>',s.index('<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet'))
s=s[:main_script]+'<script src="/navigation-ui.js"></script>\n'+s[main_script:]
# Preserve all operational IDs and verify the guide no longer owns datasets.
assert len(re.findall(r'class="nav-item(?: active)?" data-view=',s))==5
for ident in ['forestTerrainSelect','ventilationLoad','archiveControls','cameraViewer','fieldEvaluationHeading','archiveBackfill']:
    assert s.count(f'id="{ident}"')==1,ident
g=block(s,'  <div class="guideview" id="guideview">')
assert 'id="cameraViewer"' not in g and 'id="forestTerrainSelect"' not in g
p.write_text(s,encoding='utf-8',newline='')
