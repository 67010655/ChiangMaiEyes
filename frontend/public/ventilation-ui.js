(() => {
  let generation=0,archiveGeneration=0;
  const number=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('th-TH',{maximumFractionDigits:2}):'ยังไม่มีข้อมูล';
  function render(data){
    const esc=CmeEvidence.escapeHtml,c=data?.reference_cell;
    if(!c)return '<p class="evidence-note">ยังไม่ได้รับ GFS ที่ตรวจเวลา หน่วย และกริดครบ ไม่มีการเติมค่าศูนย์หรือใช้ลมสถานีแทน</p>';
    const direction=c.wind_to_deg==null?'ไม่ระบุทิศเมื่อไม่มีค่าลมหรือลมสงบ':`พัดไป ${number(c.wind_to_deg)}°`;
    return `<p class="evidence-note"><b>กริดอ้างอิง ${number(c.latitude)}, ${number(c.longitude)}</b> · แบบจำลองระดับภูมิภาค 0.25° รวมพื้นที่ข้างเคียง ไม่ใช่ค่าตรวจวัดในป่าชุมชน</p>
      <dl class="ventilation-metrics">
        <div><dt>ความสูงชั้น PBL</dt><dd>${number(c.pbl_height_m)} <small>m</small></dd></div>
        <div><dt>ลมในชั้น PBL · ${esc(direction)}</dt><dd>${number(c.wind_pbl_m_s)} <small>m/s</small></dd></div>
        <div><dt>Ventilation rate จาก NOAA</dt><dd>${number(c.ventilation_rate_m2_s)} <small>m²/s</small></dd></div>
      </dl>
      <div class="ventilation-flow" aria-hidden="true"><span>ชั้น PBL</span><i class="ventilation-air">→　→　→</i><small>ภาพประกอบแนวคิด ไม่แสดงมาตราส่วนหรือทิศภูมิศาสตร์</small></div>
      <p class="evidence-note">VRATE แสดงศักยภาพการระบายอากาศจากแบบจำลอง ไม่ใช่ระดับฝุ่นหรือความปลอดภัย ลมชั้น PBL เป็นคนละระดับกับลมสถานีและลม 10 เมตร</p>
      <dl class="method-values"><dt>เวลาที่ข้อมูลแทน</dt><dd>${esc(CmeEvidence.stamp(data.valid_at))}</dd>
        <dt>รอบแบบจำลอง</dt><dd>${esc(CmeEvidence.stamp(data.run_at))} · พยากรณ์จากรอบนี้ ${number(data.forecast_hour)} ชั่วโมง</dd>
        <dt>รับข้อมูลเมื่อ</dt><dd>${esc(CmeEvidence.stamp(data.retrieved_at))}</dd>
        <dt>ไฟล์รอบใหม่</dt><dd>${data.cycle_fallback?'รอบใหม่ยังไม่ครบ ใช้รอบก่อนหน้าที่มีไฟล์จริง':'ใช้รอบล่าสุดที่ผู้เผยแพร่มีไฟล์'}</dd>
      </dl>
      <details><summary>ดูที่มาและวิธีตรวจข้อมูล</summary><p class="evidence-note">${data.cells.length} จุดกริด · หน่วย HPBL อ้างอิงตารางรหัสของ NCEP แม้ตัวอ่านไฟล์ยังไม่รู้จักชื่อรหัสท้องถิ่น · ใช้ VRATE ของ NOAA โดยตรง ไม่คำนวณแทนด้วย PBL × ลม 10 เมตร</p>
      <a href="https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f000.shtml" target="_blank" rel="noopener noreferrer">รายการตัวแปร GFS ของ NOAA</a> ·
      <a href="https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-3.shtml" target="_blank" rel="noopener noreferrer">นิยามหน่วย HPBL ของ NCEP</a></details>`;
  }
  async function load(){
    const request=++generation,host=document.getElementById('ventilationBody'),button=document.getElementById('ventilationLoad');
    if(!host||!button)return;
    button.disabled=true;button.setAttribute('aria-busy','true');host.textContent='กำลังอ่านแบบจำลอง NOAA และตรวจหน่วยข้อมูล…';
    try{
      const lead=document.getElementById('ventilationLead').value;
      const result=await fetchJson(`/api/ventilation?lead_hours=${lead}`,50000);
      if(request===generation)host.innerHTML=render(result);
    }catch(_){if(request===generation)host.innerHTML='<p class="evidence-note">ยังโหลด GFS ไม่สำเร็จ ลองอีกครั้งได้ ยังไม่มีผลระบายอากาศที่ใช้ได้ในรอบนี้</p>';}
    finally{if(request===generation){button.disabled=false;button.removeAttribute('aria-busy');}}
  }
  async function loadArchive(){
    const request=++archiveGeneration,button=document.getElementById('gfsArchiveLoad'),status=document.getElementById('gfsArchiveStatus'),list=document.getElementById('gfsArchiveList');
    if(!button||!status||!list)return;
    button.disabled=true;status.textContent='กำลังตรวจรอบที่เก็บสำเร็จ…';list.replaceChildren();
    try{
      const result=await fetchJson(`/api/ventilation/archive?days=${document.getElementById('gfsArchiveDays').value}&limit=12`,20000);
      if(request!==archiveGeneration)return;
      const frames=Array.isArray(result.frames)?result.frames:[],esc=CmeEvidence.escapeHtml;
      status.textContent=result.total?`เก็บไว้ ${number(result.total)} ไฟล์ไม่ซ้ำ · แสดงล่าสุด ${frames.length} ไฟล์ · เริ่มเก็บ ${CmeEvidence.stamp(result.first_stored_at)} ไม่ยืนยันว่าเก็บครบทุกชั่วโมง`:'ยังไม่มีรอบที่บันทึกสำเร็จในช่วงนี้ ไม่เติมประวัติที่ขาดเป็นข้อมูลตัวอย่าง';
      list.innerHTML=frames.filter(f=>/^[a-f0-9]{64}$/.test(f.id)).map(f=>`<li><button type="button" data-gfs-frame="${f.id}">เปิดข้อมูลที่แทน ${esc(CmeEvidence.stamp(f.valid_at))}</button><p>รอบแบบจำลอง ${esc(CmeEvidence.stamp(f.run_at))} · พยากรณ์จากรอบนี้ ${number(f.forecast_hour)} ชั่วโมง<br>ระบบบันทึกครั้งแรก ${esc(CmeEvidence.stamp(f.first_stored_at))} · ${number(f.cell_count)} จุดกริด</p></li>`).join('');
    }catch(_){if(request===archiveGeneration)status.textContent='ยังตรวจคลังไม่ได้ ข้อมูลสดกับการบันทึกลงคลังเป็นคนละขั้นตอน ลองตรวจอีกครั้งได้';}
    finally{if(request===archiveGeneration)button.disabled=false;}
  }
  async function openArchivedFrame(id){
    if(!/^[a-f0-9]{64}$/.test(id))return;
    const request=++generation,host=document.getElementById('ventilationBody'),button=document.getElementById('ventilationLoad');
    button.disabled=true;button.setAttribute('aria-busy','true');host.textContent='กำลังอ่านรอบจากคลัง…';
    try{
      const result=await fetchJson(`/api/ventilation/archive/${id}`,20000);
      if(request===generation){
        host.innerHTML=`<p class="evidence-note"><b>กำลังดูรอบจากคลัง</b> · ระบบบันทึกครั้งแรก ${CmeEvidence.escapeHtml(CmeEvidence.stamp(result.first_stored_at))} · กดโหลดข้อมูล GFS เพื่อกลับไปดูรอบใกล้ปัจจุบันหรือเวลาข้างหน้าที่เลือกไว้</p>`+render(result.frame);
        const heading=document.getElementById('ventilationHeading');
        heading?.focus({preventScroll:true});
        heading?.scrollIntoView?.({block:'start',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth'});
      }
    }catch(_){if(request===generation)host.textContent='ยังอ่านรอบนี้ไม่ได้ ลองตรวจคลังอีกครั้ง';}
    finally{if(request===generation){button.disabled=false;button.removeAttribute('aria-busy');}}
  }
  document.getElementById('ventilationLoad')?.addEventListener('click',load);
  document.getElementById('ventilationLead')?.addEventListener('change',load);
  document.getElementById('gfsArchiveLoad')?.addEventListener('click',loadArchive);
  document.getElementById('gfsArchiveDays')?.addEventListener('change',loadArchive);
  document.getElementById('gfsArchiveList')?.addEventListener('click',event=>{
    const button=event.target.closest('button[data-gfs-frame]');
    if(button)openArchivedFrame(button.dataset.gfsFrame);
  });
  window.CmeVentilation={render};
})();
