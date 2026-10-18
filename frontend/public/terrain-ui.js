(() => {
  let generation=0;
  const number=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('th-TH',{maximumFractionDigits:2}):'—';
  function render(data){
    const row=data?.forest,meta=data?.metadata,esc=CmeEvidence.escapeHtml;
    if(!row||!meta)return '<p class="evidence-note">ยังไม่มีค่าสรุปภูมิประเทศที่ตรวจต้นทางได้</p>';
    if(row.status==='boundary_needs_review')return '<p class="evidence-note">ขอบเขตป่านี้ต้องตรวจสอบก่อน ยังไม่คำนวณความสูงหรือความชัน และไม่เติมค่าคงที่แทน</p>';
    if(!row.slope_deg||!row.elevation_m)return '<p class="evidence-note">ยังมีพิกเซลไม่พอสำหรับคำนวณตามขอบเขตนี้ กริดประมาณ 30 เมตรอาจไม่เห็นรายละเอียดป่าขนาดเล็ก</p>';
    return `<dl class="ventilation-metrics"><div><dt>ความสูงพื้นผิวค่ากลาง</dt><dd>${number(row.elevation_m.median)} <small>m</small></dd></div><div><dt>ความชันค่ากลางของป่า</dt><dd>${number(row.slope_deg.median)} <small>องศา</small></dd></div><div><dt>พิกเซลที่คำนวณความชันได้</dt><dd>${number(row.slope_valid_pixels)} <small>จาก ${number(row.inside_pixels)}</small></dd></div></dl>
      <p class="evidence-note">DSM รวมเรือนยอดและสิ่งปลูกสร้าง เป็นค่าสรุปของป่า ไม่ใช่ค่าที่จุดไฟทุกจุดหรือการรับรองเส้นทางปลอดภัย ยังไม่ใช้แทนข้อมูลเชื้อเพลิง</p>
      <details><summary>ที่มาและวิธีคำนวณภูมิประเทศ</summary><p class="evidence-note">${esc(meta.dataset)} · ชุดเผยแพร่ ${esc(meta.release)} · ความสูงหน่วยเมตร อ้างอิง ${esc(meta.vertical_reference)}<br>กริด ${number(meta.grid_spacing_m)} m · ${esc(meta.horizontal_crs)} · ${esc(meta.slope_algorithm)} · ${esc(meta.resampling)}<br>คำนวณ ${esc(CmeEvidence.stamp(meta.generated_at))} · ใช้ศูนย์กลางพิกเซลที่อยู่ภายในขอบเขตป่า ไม่ขยายขอบเขตเพื่อเพิ่มจำนวนตัวอย่าง</p><p class="evidence-note">${esc(meta.attribution)}<br>${esc(meta.liability_notice)}</p>
      <a href="https://registry.opendata.aws/copernicus-dem/" target="_blank" rel="noopener noreferrer">Copernicus DEM · ต้นทางข้อมูล</a> · <a href="https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf" target="_blank" rel="noopener noreferrer">สิทธิ์การใช้ข้อมูล</a></details>`;
  }
  function setForests(forests){
    const select=document.getElementById('forestTerrainSelect');if(!select)return;
    const previous=select.value;select.replaceChildren(new Option('เลือกป่าชุมชน',''));
    const rows=[...forests].filter(f=>f.forest_id).sort((a,b)=>String(a.name||'').localeCompare(String(b.name||''),'th'));
    const label=f=>`${f.name||f.forest_id} · อ.${f.amphoe||'—'}`;
    const counts=new Map();rows.forEach(f=>counts.set(label(f),(counts.get(label(f))||0)+1));
    rows.forEach(f=>select.add(new Option(`${label(f)}${counts.get(label(f))>1?` · รหัส ${f.forest_id}`:''}`,f.forest_id)));
    select.value=previous;
  }
  async function load(){
    const id=document.getElementById('forestTerrainSelect')?.value,host=document.getElementById('forestTerrainBody'),button=document.getElementById('forestTerrainLoad');
    if(!host||!button)return;
    const request=++generation;
    if(!id){host.textContent='เลือกป่าที่ต้องการดูก่อน';button.disabled=false;return;}
    button.disabled=true;host.textContent='กำลังอ่านภูมิประเทศจากข้อมูลที่คำนวณไว้…';
    try{const data=await fetchJson(`/api/forest-terrain?forest_id=${encodeURIComponent(id)}`,20000);if(request===generation)host.innerHTML=render(data);}
    catch(_){if(request===generation)host.textContent='ยังอ่านภูมิประเทศไม่ได้ ลองอีกครั้งได้ ยังไม่ใช้ความชันคงที่แทน';}
    finally{if(request===generation)button.disabled=false;}
  }
  async function openForest(id){
    window.CmeNavigation?.open('data');
    const select=document.getElementById('forestTerrainSelect');if(!select)return;
    select.value=id;await load();
    const heading=document.getElementById('forestTerrainHeading');heading?.focus({preventScroll:true});heading?.scrollIntoView?.({block:'start',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth'});
  }
  document.getElementById('forestTerrainLoad')?.addEventListener('click',load);
  document.getElementById('forestTerrainSelect')?.addEventListener('change',load);
  document.addEventListener('click',event=>{const trigger=event.target.closest?.('[data-terrain-forest]');if(trigger)openForest(trigger.dataset.terrainForest);});
  if(typeof allForests!=='undefined')setForests(allForests);
  window.CmeTerrain={render,setForests};
})();
