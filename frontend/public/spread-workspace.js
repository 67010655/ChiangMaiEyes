/* Conditional fire experiments are isolated from public risk and mail alerts. */
(() => {
  'use strict';
  const host=document.getElementById('spreadWorkspace');if(!host)return;
  const esc=value=>CmeEvidence.escapeHtml(value),stamp=value=>CmeEvidence.stamp(value);
  const fmt=(n,d=2)=>Number.isFinite(n)?n.toLocaleString('th-TH',{maximumFractionDigits:d}):'—';
  const thaiNow=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()).replace(' ','T');
  const iso=value=>value?(value.length===16?value+':00':value)+'+07:00':null;
  const number=(name,label,min,max,step='any',value='')=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="${step}" value="${value}" required></label>`;
  const evidence=(prefix,title)=>`<label>${title}<select name="${prefix}_basis"><option value="assumed">ค่าทดลอง / ยังไม่ได้สำรวจ</option><option value="measured">ตรวจวัด พร้อมหลักฐาน</option><option value="reference">แบบเชื้อเพลิงอ้างอิง</option></select></label><label>ที่มาและวิธีได้ค่า<textarea name="${prefix}_source" required minlength="5" maxlength="1000"></textarea></label><label>เวลาของข้อมูล (ประเทศไทย)<input name="${prefix}_time" type="datetime-local" required></label>`;
  host.innerHTML=`<summary>ลองจำลองไฟลาม · สำหรับการศึกษา</summary><div class="spread-inner">
    <p class="spread-intro">ทดลองว่า <strong>ถ้ามีไฟเริ่มแล้ว</strong> เชื้อเพลิง ลม และทางลาดที่กำหนดจะให้แนวลามอย่างไร เลื่อนเวลาเพื่อดูพื้นที่ตามเงื่อนไข ยังไม่ใช่การคาดการณ์ไฟจริงที่สอบเทียบกับเชียงใหม่</p>
    <div class="spread-grid"><form id="spreadForm">
      <label>ป่าชุมชนที่ศึกษา<select name="forest_id" required><option value="">กำลังอ่านรายชื่อป่า…</option></select></label>
      <button type="button" data-spread-example>ลองด้วยตัวอย่างเชื้อเพลิง USFS FM1</button><p class="evidence-note">ตัวอย่างเป็นเชื้อเพลิงอ้างอิงของสหรัฐฯ ไม่ใช่ผลสำรวจป่าที่เลือก</p>
      <fieldset><legend>เชื้อเพลิงที่พาไฟตามพื้น</legend>
        <div class="spread-pair">${number('load','มวลแห้ง (kg/m²)',.0001,10)}${number('depth','ความหนาชั้นเชื้อเพลิง (m)',.001,3)}</div>
        ${number('savr','พื้นที่ผิวต่อปริมาตรอนุภาค SAVR (m⁻¹)',200,40000)}
        <div class="spread-pair">${number('moisture','ความชื้น (% มวลแห้ง)',0,300)}${number('extinction','ความชื้นที่โมเดลหยุดลาม (%)',.001,100)}</div>
        ${evidence('fuel','สถานะข้อมูลเชื้อเพลิง')}
        <details><summary>ลองเปลี่ยนความชื้นและดูคุณสมบัติวัสดุ</summary><p class="evidence-note">กรอกช่วงความชื้นทั้งสองช่องเพื่อเปรียบเทียบกรณีแห้ง/ชื้น ช่วงนี้ไม่ใช่ความน่าจะเป็นหรือช่วงความเชื่อมั่น</p>
        <div class="spread-pair"><label>ความชื้นต่ำสุด (%)<input name="moisture_lo" type="number" min="0" max="300" step="any"></label><label>ความชื้นสูงสุด (%)<input name="moisture_hi" type="number" min="0" max="300" step="any"></label></div>
        <p class="evidence-note">ค่าด้านล่างเริ่มจากค่ามาตรฐานใน Behave ยังไม่ใช่ค่าตรวจวัสดุในพื้นที่</p>
        <label>แหล่งคุณสมบัติวัสดุ<select name="material_basis"><option value="behave_reference">ใช้ค่ามาตรฐาน Behave</option><option value="user_specified">ระบุเอง พร้อมที่มาแยก</option></select></label><label>ที่มาคุณสมบัติวัสดุที่ระบุเอง<input name="material_source" minlength="5" maxlength="1000"></label>
        ${number('density','ความหนาแน่นเนื้อเชื้อเพลิง (kg/m³)',100,1500,'any',512.5908279667244)}${number('heat','ค่าความร้อน (kJ/kg)',1000,30000,'any',18608)}
        <div class="spread-pair">${number('mineral','แร่ธาตุรวม (%)',.0001,99.99,'any',5.55)}${number('effective_mineral','แร่ธาตุส่วนที่มีผล (%)',.0001,99.99,'any',1)}</div></details>
      </fieldset>
      <fieldset><legend>ลมใกล้เปลวไฟ</legend><div class="spread-pair">${number('wind','ความเร็ว (m/s)',0,20)}${number('wind_from','พัดมาจาก (องศา)',0,359.999)}</div>
      <p class="evidence-note">0° = เหนือ · 90° = ตะวันออก ไม่ใช้ลม 10 เมตรบนแผนที่แทนลมระดับนี้โดยตรง</p>${evidence('wind','สถานะข้อมูลลม')}</fieldset>
      <fieldset><legend>จุดเริ่มและทางลาด</legend><label>ตำแหน่งและแหล่งความชัน<select name="terrain_mode"><option value="copernicus_forest_point">จุดสมมติในป่า + DSM ที่จุดนั้น</option><option value="manual">ระบุพิกัดและความชันเอง</option></select></label>
      <p class="evidence-note" id="spreadTerrainNote" role="status">เลือกป่าก่อน จุดตัวอย่างไม่ใช่ตำแหน่งไฟจริง</p>
      <div id="spreadManual" hidden><div class="spread-pair">${number('latitude','ละติจูด',17,21)}${number('longitude','ลองจิจูด',98,100)}</div>
      <div class="spread-pair">${number('slope','ความชัน (องศา)',0,60)}${number('upslope','ทิศขึ้นเขา (องศา)',0,359.999)}</div>${evidence('terrain','สถานะข้อมูลทางลาด')}<p class="evidence-note">คลิกแผนที่เพื่อกรอกพิกัดได้ ความชันต้องมีหลักฐานของจุดนั้น</p></div>
      <label>เวลาเริ่มสมมติ (ประเทศไทย)<input name="start_at" type="datetime-local" required></label><label>ดูนานเท่าไร<select name="duration"><option value="60">1 ชั่วโมง</option><option value="180" selected>3 ชั่วโมง</option><option value="360">6 ชั่วโมง</option></select></label></fieldset>
      <button class="spread-primary" type="submit">จำลองตามข้อมูลนี้</button>
    </form><div class="spread-output" id="spreadOutput" tabindex="-1">
      <h3>ผลตามเงื่อนไขจำลอง</h3>
      <p class="evidence-note" id="spreadStatus" role="status" aria-live="polite">ยังไม่มีผลจำลอง กรอกข้อมูลหรือเริ่มด้วยตัวอย่างอ้างอิง</p>
      <div id="spreadMap" class="spread-map" role="region" aria-label="แผนที่พื้นที่ตามเงื่อนไขจำลอง"></div>
      <div id="spreadResult" hidden><div class="spread-key"><span>เงื่อนไขหลัก</span><span>ลองเปลี่ยนความชื้น</span><span>เชื้อเพลิงเดิม ไม่มีลม พื้นราบ</span></div>
      <div class="spread-timeline"><button type="button" id="spreadPlay" aria-label="เล่นลำดับเวลาจำลอง" aria-pressed="false">เล่นเวลา</button><input id="spreadTime" type="range" min="0" value="0" step="1" aria-label="เวลาหลังเริ่มจำลอง"><output id="spreadTimeLabel" for="spreadTime"></output></div>
      <div id="spreadReadout" class="spread-readout"></div><div id="spreadInputs"></div>
      <details><summary>วิธีคำนวณ ข้อจำกัด และข้อมูลที่ใช้จริง</summary><ul id="spreadLimits" class="evidence-note"></ul><p class="evidence-note">สูตร Rothermel–Albini สำหรับเชื้อเพลิงแห้งชนิดเดียว รวมแรงส่งลมกับทางลาดเป็นเวกเตอร์ แล้ววาดวงรีตามเวลา ถือว่าค่าทั้งพื้นที่คงที่ ไม่รวมไฟเรือนยอด สะเก็ดไฟ และการดับไฟ</p><p><a href="https://github.com/firelab/behave/tree/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave" target="_blank" rel="noopener noreferrer">สมการต้นทาง USFS Behave</a> · <a href="https://research.fs.usda.gov/treesearch/32533" target="_blank" rel="noopener noreferrer">Rothermel 1972</a></p><label>ชุดข้อมูลและผลสำหรับตรวจซ้ำ<textarea id="spreadRaw" readonly rows="7"></textarea></label></details>
      <div class="spread-actions"><button type="button" id="spreadSave">บันทึกเชื้อเพลิงและผลไว้ในป่านี้</button></div><p class="evidence-note" id="spreadSaveStatus" role="status">บันทึกได้เฉพาะผู้ดูแลหรือตัวแทนที่ได้รับอนุมัติ ผลนี้ไม่ส่งแจ้งเตือนอัตโนมัติ</p>
      <details id="spreadEvaluation"><summary>เทียบกับหลักฐานที่เกิดขึ้นภายหลัง</summary><p class="evidence-note">เป็นการวินิจฉัยย้อนหลัง ยังไม่ใช่คะแนนความแม่นยำ FIRMS บอกจุดตรวจพบความร้อน ไม่ใช่ขอบเขตไฟหรือเวลาที่ไฟมาถึง</p>
      <button type="button" id="spreadImport">อ่านจุด NASA ที่มีในคลังช่วงเวลานี้</button><p class="evidence-note" id="spreadImportStatus" role="status"></p>
      <form id="spreadObservation"><div class="spread-pair">${number('latitude','ละติจูด',-90,90)}${number('longitude','ลองจิจูด',-180,180)}</div><label>เวลาที่ตรวจพบ (ประเทศไทย)<input name="observed_at" type="datetime-local" required></label><label>ชนิดหลักฐาน<select name="kind"><option value="firms_detection">จุดความร้อน FIRMS</option><option value="field_arrival">ผู้ตรวจเห็นเวลาไฟมาถึงจริง</option></select></label><label>ที่มาหรือรหัสหลักฐาน<input name="source" required minlength="5" maxlength="1000"></label><button type="submit">เพิ่มจุดสำหรับเทียบ</button></form>
      <div id="spreadObservations" class="evidence-note"></div><button type="button" id="spreadCompare">เทียบกับแบบจำลองและค่าฐาน</button><div id="spreadComparison" role="status" aria-live="polite"></div><button type="button" id="spreadCompareSave" disabled>บันทึกหลักฐานและผลเปรียบเทียบ</button><p id="spreadCompareSaveStatus" class="evidence-note" role="status">บันทึกผลจำลองก่อน เพื่อผูกหลักฐานกับผลเดิม</p></details>
      </div><details><summary>เปิดผลที่เคยบันทึกในป่านี้</summary><button type="button" id="spreadSavedLoad">อ่านรายการจากบัญชี</button><p id="spreadSavedStatus" class="evidence-note" role="status">เลือกป่าด้านบน แล้วเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดูป่านั้น</p><label id="spreadSavedLabel" hidden>ผลจำลอง / ผลเปรียบเทียบที่บันทึกไว้<select id="spreadSaved"><option value="">เลือกผลที่ต้องการดู</option></select></label></details></div></div></div>`;
  const $=id=>document.getElementById(id),form=$('spreadForm'),field=name=>form.elements.namedItem(name);
  let map=null,overlay=null,marker=null,last=null,observations=[],generation=0,pointGeneration=0,timer=null,savingIds=null,savedRows=[],savedModelId=null,comparison=null,comparisonId=null,observationRevision=0;
  const status=text=>{$('spreadStatus').textContent=text;};
  function stop(){if(timer)clearInterval(timer);timer=null;$('spreadPlay').textContent='เล่นเวลา';$('spreadPlay').setAttribute('aria-pressed','false');}
  function clearComparison(){observationRevision++;comparison=null;comparisonId=null;$('spreadCompareSave').disabled=true;$('spreadCompareSaveStatus').textContent='บันทึกผลจำลองและเทียบหลักฐานก่อนบันทึกผลเปรียบเทียบ';}
  function invalidate(){clearComparison();savedModelId=null;generation++;stop();last=null;savingIds=null;observations=[];$('spreadResult').hidden=true;overlay?.clearLayers();status('ข้อมูลถูกเปลี่ยนแล้ว กดจำลองตามข้อมูลนี้เพื่อคำนวณใหม่');}
  function initMap(){if(map){map.invalidateSize({pan:false});return;}if(typeof L==='undefined')return;
    map=L.map('spreadMap',{scrollWheelZoom:false,zoomAnimation:false}).setView([18.79,98.99],9);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(map);overlay=L.layerGroup().addTo(map);
    map.on('click',event=>{if(field('terrain_mode').value!=='manual')return;field('latitude').value=event.latlng.lat.toFixed(6);field('longitude').value=event.latlng.lng.toFixed(6);invalidate();setMarker(event.latlng.lat,event.latlng.lng);});
  }
  function setMarker(lat,lon){if(!map)return;marker?.remove();marker=L.circleMarker([lat,lon],{radius:6,color:'#fff',weight:2,fillColor:'#166c40',fillOpacity:1}).addTo(map).bindPopup('จุดเริ่มที่กำหนดสำหรับจำลอง ไม่ใช่รายงานไฟจริง');map.setView([lat,lon],13,{animate:false});}
  async function catalog(){try{const rows=typeof allForests!=='undefined'&&allForests.length?allForests:(await fetchJson('/api/community-forests',20000)).forests;
      const previous=field('forest_id').value;field('forest_id').replaceChildren(new Option('เลือกป่าชุมชน',''));
      [...rows].sort((a,b)=>String(a.name).localeCompare(String(b.name),'th')).forEach(f=>field('forest_id').add(new Option(`${f.name||f.forest_id} · อ.${f.amphoe||'—'} · ${f.forest_id}`,f.forest_id)));field('forest_id').value=previous;
    }catch(_){field('forest_id').replaceChildren(new Option('อ่านรายชื่อป่าไม่ได้ ปิดและเปิดส่วนนี้เพื่อลองอีกครั้ง',''));}}
  async function loadPoint(){const id=field('forest_id').value,seq=++pointGeneration;
    if(!id){$('spreadTerrainNote').textContent='เลือกป่าเพื่อดูจุดตัวอย่าง';return;}
    $('spreadTerrainNote').textContent='กำลังอ่านความชันที่จุดตัวอย่าง…';
    try{const d=await fetchJson('/api/spread/terrain-point?forest_id='+encodeURIComponent(id),12000);if(seq!==pointGeneration)return;const p=d.point;
      $('spreadTerrainNote').textContent=`จุดสมมติ ${fmt(p.latitude,6)}, ${fmt(p.longitude,6)} · DSM ความชัน ${fmt(p.slope_deg)}° · ขึ้นเขาทาง ${fmt(p.upslope_to_deg,1)}° · กริด 30 m ไม่ใช่ค่ากลางทั้งป่า`;
      if(field('terrain_mode').value==='copernicus_forest_point'&&!last)setMarker(p.latitude,p.longitude);
    }catch(_){if(seq===pointGeneration)$('spreadTerrainNote').textContent='ใช้จุด DSM นี้ไม่ได้ ขอบเขตอาจต้องตรวจสอบ หรือชุดข้อมูลยังอ่านไม่ได้ ไม่มีการใส่ความชันแทน';}}
  function terrainMode(){const manual=field('terrain_mode').value==='manual';$('spreadManual').hidden=!manual;$('spreadManual').querySelectorAll('input,select,textarea').forEach(el=>{el.disabled=!manual;});if(!manual)loadPoint();}
  function materialMode(){const ref=field('material_basis').value==='behave_reference';const defaults={density:512.5908279667244,heat:18608,mineral:5.55,effective_mineral:1};for(const [k,v] of Object.entries(defaults)){field(k).disabled=ref;if(ref)field(k).value=String(v);}field('material_source').disabled=ref;field('material_source').required=!ref;}
  function getEvidence(prefix){return {basis:field(prefix+'_basis').value,source:field(prefix+'_source').value.trim(),observed_at:iso(field(prefix+'_time').value)};}
  function payload(){const n=name=>{const v=field(name).value;if(v==='')throw new Error('กรอกข้อมูลที่จำเป็นให้ครบ');return Number(v);};
    const manual=field('terrain_mode').value==='manual',lo=field('moisture_lo').value,hi=field('moisture_hi').value;
    if((lo==='')!==(hi===''))throw new Error('กรอกช่วงความชื้นทั้งสองค่า หรือเว้นทั้งคู่');
    return {forest_id:field('forest_id').value,start_at:iso(field('start_at').value),duration_minutes:n('duration'),
      fuel:{load_kg_m2:n('load'),depth_m:n('depth'),savr_per_m:n('savr'),moisture_pct:n('moisture'),extinction_moisture_pct:n('extinction'),
            particle_density_kg_m3:n('density'),heat_kj_kg:n('heat'),total_mineral_pct:n('mineral'),effective_mineral_pct:n('effective_mineral'),
            material_basis:field('material_basis').value,material_source:field('material_basis').value==='user_specified'?field('material_source').value.trim():null,evidence:getEvidence('fuel')},
      wind:{midflame_mps:n('wind'),from_deg:n('wind_from'),evidence:getEvidence('wind')},
      terrain:manual?{mode:'manual',slope_deg:n('slope'),upslope_to_deg:n('upslope'),evidence:getEvidence('terrain')}:{mode:'copernicus_forest_point'},
      ...(manual?{latitude:n('latitude'),longitude:n('longitude')}:{}),moisture_range_pct:lo===''?null:[Number(lo),Number(hi)]};}
  async function request(path,data,token){const ctl=new AbortController(),timeout=setTimeout(()=>ctl.abort(),20000);
    try{const response=await fetch((typeof API_BASE==='undefined'?'':API_BASE)+path,{method:data?'POST':'GET',headers:{...(data?{'Content-Type':'application/json'}:{}),...(token?{Authorization:'Bearer '+token}:{})},...(data?{body:JSON.stringify(data)}:{}),cache:'no-store',signal:ctl.signal});
      const body=await response.json();if(!response.ok){const detail=body.detail;throw new Error(typeof detail==='string'?detail:Array.isArray(detail)?detail.map(r=>r.msg).join(' · '):'ยังทำรายการไม่ได้');}return body;
    }finally{clearTimeout(timeout);}}
  function draw(){if(!last)return;initMap();overlay?.clearLayers();const i=Number($('spreadTime').value),central=last.cases[0],f=central.frames[i],r=central.rates;
    const drawGeometry=(geometry,style)=>{if(geometry&&overlay)L.geoJSON(geometry,{style}).addTo(overlay);};
    last.cases.slice(1).forEach(c=>drawGeometry(c.frames[i].geometry,{color:'#0b8d7b',dashArray:'2 6',weight:2,fillOpacity:.025}));
    drawGeometry(last.baseline.frames[i].geometry,{color:'#677d94',dashArray:'6 5',weight:2,fillOpacity:0});
    drawGeometry(f.geometry,{color:'#db791d',weight:3,fillColor:'#ed9a32',fillOpacity:.14});
    $('spreadTimeLabel').textContent=f.minutes+' นาที';
    $('spreadReadout').innerHTML=`<strong>${fmt(f.head_distance_m,0)} เมตร</strong> ตามแนวลามสูงสุดใน ${f.minutes} นาที · อัตรา ${fmt(r.head_m_min)} m/min<br>ทิศลามสูงสุด ${r.heading_to_deg===null?'ไม่มีทิศเด่นในเงื่อนไขนี้':fmt(r.heading_to_deg,1)+'° จากเหนือ'} · พื้นที่วงรีจำลอง ${fmt(f.scenario_area_ha)} ha <small>(ไม่ใช่พื้นที่ไหม้จริง)</small>`;
  }
  function render(result){clearComparison();savedModelId=null;last=result;savingIds={fuel:crypto.randomUUID(),model:crypto.randomUUID()};observations=[];stop();$('spreadResult').hidden=false;
    const req=result.inputs.request,terrain=result.inputs.terrain,ig=result.inputs.ignition;
    $('spreadTime').max=result.cases[0].frames.length-1;$('spreadTime').value=$('spreadTime').max;
    $('spreadLimits').innerHTML=result.limitations.map(s=>`<li>${esc(s)}</li>`).join('');
    const basis={measured:'ผู้กรอกระบุว่าตรวจวัด',assumed:'ค่าทดลอง',reference:'แบบอ้างอิง'};
    $('spreadInputs').innerHTML=`<p class="evidence-note">เชื้อเพลิง: <b>${esc(basis[req.fuel.evidence.basis])}</b> · ${esc(req.fuel.evidence.source)} · ${esc(stamp(req.fuel.evidence.observed_at))}<br>ลม: <b>${esc(basis[req.wind.evidence.basis])}</b> ${fmt(req.wind.midflame_mps)} m/s ระดับใกล้เปลวไฟ พัดมาจาก ${fmt(req.wind.from_deg)}° · ${esc(req.wind.evidence.source)} · ${esc(stamp(req.wind.evidence.observed_at))}<br>ทางลาดที่ใช้: ${fmt(terrain.slope_deg)}° ขึ้นเขา ${fmt(terrain.upslope_to_deg,1)}° · ${terrain.mode==='manual'?'ผู้ใช้ระบุพร้อมที่มา':'Copernicus DSM 30 m ที่จุดเริ่มสมมติ'}<br>เวลาเริ่ม: ${esc(stamp(req.start_at))} · คำนวณผลเมื่อ ${esc(stamp(result.issued_at))}<br>รุ่น ${esc(result.model_version)} · รหัสข้อมูล ${esc(result.input_sha256.slice(0,12))}</p>`;
    if(terrain.source)$('spreadInputs').innerHTML+=`<details><summary>ที่มา DSM และสิทธิ์การใช้</summary><p class="evidence-note">${esc(terrain.source.attribution)}<br>${esc(terrain.source.liability_notice)}</p><a href="https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf" target="_blank" rel="noopener noreferrer">ใบอนุญาต Copernicus DEM</a></details>`;
    $('spreadInputs').innerHTML+=`<p class="evidence-note">ความหนาแน่นเนื้อเชื้อเพลิง ค่าความร้อน และแร่ธาตุ: <b>${req.fuel.material_basis==='user_specified'?'ผู้กรอกระบุเอง':'ค่ามาตรฐานอ้างอิง Behave ไม่ใช่ผลสำรวจในป่านี้'}</b>${req.fuel.material_source?' · '+esc(req.fuel.material_source):''}</p>`;
    $('spreadRaw').value=JSON.stringify(result,null,2);$('spreadComparison').textContent='';$('spreadObservations').textContent='ยังไม่มีจุดสำหรับเทียบ';$('spreadImportStatus').textContent='';
    $('spreadSave').disabled=false;$('spreadSaveStatus').textContent='ผลนี้ยังไม่บันทึกในบัญชี และไม่ส่งแจ้งเตือนอัตโนมัติ';setMarker(ig.latitude,ig.longitude);draw();
    const coords=result.cases.flatMap(c=>c.frames.at(-1).geometry?.coordinates[0]||[]);if(coords.length&&map)map.fitBounds(coords.map(c=>[c[1],c[0]]),{padding:[24,24],maxZoom:16,animate:false});
  }
  form.addEventListener('input',invalidate);form.addEventListener('change',event=>{invalidate();if(event.target===field('forest_id')){savedRows=[];$('spreadSavedLabel').hidden=true;$('spreadSavedStatus').textContent='อ่านรายการจากบัญชีอีกครั้งเพื่อดูป่าที่เลือก';loadPoint();}if(event.target===field('terrain_mode'))terrainMode();if(event.target===field('material_basis'))materialMode();});
  form.addEventListener('submit',async event=>{event.preventDefault();stop();const seq=++generation,button=form.querySelector('[type="submit"]');button.disabled=true;status('กำลังคำนวณจากข้อมูลที่ระบุ…');
    try{const result=await request('/api/spread/simulate',payload());if(seq!==generation)return;render(result);status('คำนวณแล้ว · เป็นผลตามเงื่อนไขทดลอง ยังไม่สอบเทียบกับเหตุจริง');$('spreadOutput').focus({preventScroll:true});$('spreadOutput').scrollIntoView({block:'start',behavior:'auto'});}
    catch(error){if(seq===generation)status('คำนวณไม่ได้: '+(error.name==='AbortError'?'การเชื่อมต่อใช้เวลานาน ลองใหม่ได้':error.message));}
    finally{button.disabled=false;}});
  host.querySelector('[data-spread-example]').addEventListener('click',()=>{invalidate();const values={load:.16600253963702372,depth:.3048,savr:11482.939632545931,moisture:5,extinction:12,wind:.508,wind_from:270,
      density:512.5908279667244,heat:18608,mineral:5.55,effective_mineral:1,material_basis:'behave_reference',fuel_basis:'reference',wind_basis:'assumed',fuel_source:'USFS Anderson FM1; ตัวอย่างทดสอบสูตร ไม่ใช่ผลสำรวจป่านี้',wind_source:'ลมสมมติ 0.508 m/s พัดมาจากตะวันตก ไม่ใช่ลมปัจจุบัน',moisture_lo:2,moisture_hi:10};
    Object.entries(values).forEach(([k,v])=>{field(k).value=String(v);});materialMode();for(const k of ['fuel_time','wind_time','start_at'])field(k).value=thaiNow();status('กรอกตัวอย่างอ้างอิงแล้ว เลือกป่าก่อนจำลอง ค่าชุดนี้ไม่ได้วัดจากเชียงใหม่');});
  $('spreadTime').addEventListener('input',()=>{stop();draw();});$('spreadPlay').addEventListener('click',()=>{if(timer){stop();return;}if(!last)return;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches){status('เปิดลดการเคลื่อนไหวอยู่ ใช้แถบเวลาเลือกทีละช่วงได้');return;}
    if(Number($('spreadTime').value)>=$('spreadTime').max){$('spreadTime').value='0';draw();}$('spreadPlay').textContent='หยุดเวลา';$('spreadPlay').setAttribute('aria-pressed','true');
    timer=setInterval(()=>{if(!host.open||document.hidden){stop();return;}const next=Number($('spreadTime').value)+1;if(next>Number($('spreadTime').max)){stop();return;}$('spreadTime').value=next;draw();},900);});
  $('spreadSave').addEventListener('click',async()=>{if(!last||!savingIds)return;const result=last,ids=savingIds,button=$('spreadSave');button.disabled=true;
    try{const session=typeof sb!=='undefined'&&sb?(await sb.auth.getSession()).data.session:null;if(!session){$('spreadSaveStatus').textContent='เข้าสู่ระบบด้วยบัญชีตัวแทนก่อนบันทึก';if(typeof openAuthModal==='function')openAuthModal();return;}
      const path='/api/community/forests/'+encodeURIComponent(result.inputs.request.forest_id)+'/research';
      await request(path,{id:ids.fuel,kind:'fuel',data:{schema:'cme-single-dead-fuel-v1',fuel:result.inputs.request.fuel,used_by_input_sha256:result.input_sha256}},session.access_token);
      await request(path,{id:ids.model,kind:'model',data:{schema:'cme-spread-scenario-v1',fuel_record_id:ids.fuel,result}},session.access_token);
      if(last!==result)return;savedModelId=ids.model;$('spreadCompareSave').disabled=!comparison;
      $('spreadSaveStatus').textContent='บันทึกเชื้อเพลิงและผลแล้ว เก็บเวลาและรหัสข้อมูลไว้ตรวจย้อนหลัง ไม่ส่งการแจ้งเตือน';
    }catch(error){if(last!==result)return;$('spreadSaveStatus').textContent='ยังบันทึกไม่ครบ: '+error.message+' · ลองซ้ำได้ ระบบใช้รหัสเดิมป้องกันบันทึกซ้ำ';}finally{button.disabled=false;}});
  $('spreadSavedLoad').addEventListener('click',async()=>{const id=field('forest_id').value;if(!id){$('spreadSavedStatus').textContent='เลือกป่าที่ต้องการอ่านก่อน';return;}const button=$('spreadSavedLoad');button.disabled=true;
    try{const session=typeof sb!=='undefined'&&sb?(await sb.auth.getSession()).data.session:null;if(!session){$('spreadSavedStatus').textContent='เข้าสู่ระบบก่อนอ่านผลที่บันทึก';if(typeof openAuthModal==='function')openAuthModal();return;}
      const rows=await request('/api/community/forests/'+encodeURIComponent(id)+'/research?kind=model&limit=100',null,session.access_token);
      if(id!==field('forest_id').value)return;
      savedRows=rows.filter(r=>(r.data?.schema==='cme-spread-scenario-v1'&&r.data?.result?.model_version==='cme-single-dead-albini1976-ellipse-v1')||r.data?.schema==='cme-spread-evaluation-v1');
      $('spreadSaved').replaceChildren(new Option('เลือกผลที่ต้องการดู',''));savedRows.forEach(r=>$('spreadSaved').add(new Option(`${r.data.schema==='cme-spread-evaluation-v1'?'ผลเปรียบเทียบ':'ผลจำลอง'} · ${stamp(r.created_at)} · ${(r.data.result?.input_sha256||r.data.evaluation?.input_sha256||'').slice(0,12)}`,r.id)));
      $('spreadSavedLabel').hidden=!savedRows.length;$('spreadSavedStatus').textContent=savedRows.length?`พบ ${savedRows.length} ผลใน 100 รายการล่าสุดที่บัญชีนี้มีสิทธิ์ดู`:'ยังไม่พบผลของเครื่องมือรุ่นนี้ในป่าที่เลือก';
    }catch(error){$('spreadSavedStatus').textContent='ยังอ่านผลไม่ได้: '+error.message;}finally{button.disabled=false;}});
  $('spreadSaved').addEventListener('change',async()=>{const selected=savedRows.find(r=>r.id===$('spreadSaved').value);if(!selected)return;invalidate();const seq=generation;let row=selected;
    try{if(selected.data.schema==='cme-spread-evaluation-v1'){const session=typeof sb!=='undefined'&&sb?(await sb.auth.getSession()).data.session:null;if(!session)throw new Error('เข้าสู่ระบบก่อนเปิดหลักฐาน');row=await request('/api/community/forests/'+encodeURIComponent(field('forest_id').value)+'/research/'+encodeURIComponent(selected.data.scenario_record_id),null,session.access_token);if(seq!==generation)return;if(row.data?.schema!=='cme-spread-scenario-v1'||row.data.result.input_sha256!==selected.data.evaluation.input_sha256)throw new Error('ผลเปรียบเทียบไม่ตรงกับผลจำลองที่อ้างถึง');}
    const result=row.data.result,r=result.inputs.request,f=r.fuel,t=r.terrain;
    const values={forest_id:r.forest_id,load:f.load_kg_m2,depth:f.depth_m,savr:f.savr_per_m,moisture:f.moisture_pct,extinction:f.extinction_moisture_pct,density:f.particle_density_kg_m3,heat:f.heat_kj_kg,mineral:f.total_mineral_pct,effective_mineral:f.effective_mineral_pct,material_basis:f.material_basis||'behave_reference',material_source:f.material_source||'',wind:r.wind.midflame_mps,wind_from:r.wind.from_deg,terrain_mode:t.mode,duration:r.duration_minutes,latitude:r.latitude??'',longitude:r.longitude??'',slope:t.slope_deg??'',upslope:t.upslope_to_deg??'',moisture_lo:r.moisture_range_pct?.[0]??'',moisture_hi:r.moisture_range_pct?.[1]??''};
    const localTime=value=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value)).replace(' ','T');
    Object.entries(values).forEach(([k,v])=>{field(k).value=String(v);});for(const [prefix,e] of [['fuel',f.evidence],['wind',r.wind.evidence],['terrain',t.evidence]]){if(!e)continue;field(prefix+'_basis').value=e.basis;field(prefix+'_source').value=e.source;field(prefix+'_time').value=localTime(e.observed_at);}
    field('start_at').value=localTime(r.start_at);terrainMode();materialMode();render(result);savingIds=null;savedModelId=row.id;$('spreadSave').disabled=true;
    if(selected.data.schema==='cme-spread-evaluation-v1'){observations=selected.data.observations;listObservations();showComparison(selected.data.evaluation);comparison=null;$('spreadCompareSave').disabled=true;$('spreadCompareSaveStatus').textContent='เปิดหลักฐานและผลเปรียบเทียบที่บันทึกไว้แล้ว · ไม่ได้คำนวณใหม่';$('spreadEvaluation').open=true;}
    $('spreadSaveStatus').textContent=`กำลังดูผลที่บันทึก ${stamp(row.created_at)} · กดจำลองเพื่อคำนวณชุดใหม่ตามข้อมูลปัจจุบัน`;
    status('เปิดผลเดิมแล้ว ใช้ข้อมูลและผลที่บันทึกไว้ ไม่ได้คำนวณใหม่');$('spreadOutput').focus({preventScroll:true});$('spreadOutput').scrollIntoView({block:'start',behavior:'auto'});
    }catch(error){if(seq===generation)$('spreadSavedStatus').textContent='เปิดหลักฐานไม่ได้: '+error.message;}
  });
  function listObservations(){clearComparison();$('spreadObservations').innerHTML=`<p>มี ${observations.length} จุดสำหรับเทียบ · จุดตรวจพบไม่ได้ยืนยันขอบเขตไฟทั้งหมด</p><div class="spread-table-wrap"><table><thead><tr><th>เวลา / ที่มา</th><th>ตำแหน่ง</th><th>แก้รายการ</th></tr></thead><tbody>${observations.map((o,i)=>`<tr><td>${esc(stamp(o.observed_at))}<br>${esc(o.source)}</td><td>${fmt(o.latitude,5)}, ${fmt(o.longitude,5)}</td><td><button type="button" data-remove-observation="${i}" aria-label="เอาจุดที่ ${i+1} ออกจากชุดเทียบ">เอาออก</button></td></tr>`).join('')}</tbody></table></div>`;$('spreadComparison').textContent='';}
  $('spreadObservations').addEventListener('click',event=>{const button=event.target.closest('[data-remove-observation]');if(button){observations.splice(Number(button.dataset.removeObservation),1);listObservations();}});
  $('spreadObservation').addEventListener('submit',event=>{event.preventDefault();if(!last)return;const d=Object.fromEntries(new FormData(event.target));
    if(observations.length>=500){$('spreadComparison').textContent='รองรับครั้งละไม่เกิน 500 จุด';return;}
    observations.push({latitude:Number(d.latitude),longitude:Number(d.longitude),observed_at:iso(d.observed_at),kind:d.kind,source:d.source});listObservations();});
  $('spreadImport').addEventListener('click',async()=>{if(!last)return;const snapshot=last,button=$('spreadImport');button.disabled=true;let collected=[],more=false;
    try{const req=snapshot.inputs.request,from=Date.parse(req.start_at),end=new Date(from+req.duration_minutes*60000),origin=snapshot.inputs.ignition;
      const radius=Math.max(...snapshot.cases.map(c=>c.frames.at(-1).head_distance_m))/1000+.5;
      for(let offset=0;offset<5000;offset+=1000){const doc=await fetchJson('/api/archive?'+new URLSearchParams({days:'1',kind:'hotspot',end:end.toISOString(),offset:String(offset),limit:'1000'}),20000);
        if(last!==snapshot)return;for(const row of doc.rows||[]){const t=Date.parse(row.observed_at);if(t<=from||t>end.getTime()||!/NASA|FIRMS|VIIRS|MODIS/i.test(row.source||'')||!Number.isFinite(row.latitude)||!Number.isFinite(row.longitude))continue;
          if(CmeEvidence.distanceKm({lat:origin.latitude,lon:origin.longitude},{lat:row.latitude,lon:row.longitude})>radius)continue;
          collected.push({latitude:row.latitude,longitude:row.longitude,observed_at:row.observed_at,kind:'firms_detection',source:row.source+' · คลัง '+row.id});}
        more=doc.next_offset!==null&&doc.next_offset!==undefined;if(!more||collected.length>=500)break;}
      const combined=new Map([...observations,...collected].map(o=>[[o.latitude,o.longitude,Date.parse(o.observed_at),o.kind].join('|'),o]));
      observations=[...combined.values()].slice(0,500);listObservations();$('spreadImportStatus').textContent=`อ่านได้ ${collected.length} จุดหลังเวลาเริ่ม ภายใน ${fmt(radius)} km จากจุดเริ่ม · เฉพาะข้อมูล NASA ที่มีในคลัง${more||combined.size>500?' · ถึงขีดจำกัดการอ่าน ยังไม่ครบทุกแถว':''}${collected.length?'':' · ไม่พบจุดไม่ได้แปลว่าไม่มีไฟ'} · เก็บจุดที่กรอกไว้เดิมร่วมด้วย`;
    }catch(error){$('spreadImportStatus').textContent='ยังอ่านคลังไม่ได้ ไม่มีการเติมจุดตัวอย่างแทน';}finally{button.disabled=false;}});
  function showComparison(result){
    const arrival=(n,within)=>n===null?'ไม่ลามถึงตามสมการ':`${fmt(n)} นาที${within===false?' · เกินช่วงจำลอง':''}`;
    $('spreadComparison').innerHTML=`<p class="evidence-note">เทียบกับผลเดิมรหัส ${esc(result.input_sha256.slice(0,12))} · ${esc(stamp(result.scenario_issued_at))}<br>หลักฐาน ${fmt(result.unique_observation_count,0)} จุด (เว้นซ้ำ ${fmt(result.duplicate_count,0)}) · จุดกลางที่อยู่ในวงรี ${fmt(result.nominal_point_coverage_percent,1)}% · ค่าฐานไม่มีลม/พื้นราบ ${fmt(result.baseline_point_coverage_percent,1)}% <b>ตัวเลขนี้ไม่ใช่ accuracy</b><br>เวลาไฟมาถึงที่เทียบได้ ${fmt(result.field_arrival_sample_count,0)} จุด · คลาดเคลื่อนสัมบูรณ์เฉลี่ย (MAE) ${fmt(result.mean_absolute_arrival_error_minutes)} นาที · ค่าฐาน ${fmt(result.baseline_mean_absolute_arrival_error_minutes)} นาที${result.field_arrival_no_model_arrival_count?`<br>อีก ${fmt(result.field_arrival_no_model_arrival_count,0)} จุดไม่มีเวลาไฟมาถึงจากแบบจำลอง จึงไม่รวมในค่าเฉลี่ยเวลา`:''}</p>
      <details><summary>ดูผลรายจุดและวิธีอ่าน</summary><p class="evidence-note">เวลาทั้งหมดนับจากเริ่มจำลอง · ค่าคลาดเคลื่อนติดลบ = โมเดลให้ไฟมาถึงเร็วกว่า บวก = ช้ากว่า · จุด FIRMS ไม่ใช้คำนวณความคลาดเคลื่อนเวลา</p><div class="spread-table-wrap" tabindex="0" role="region" aria-label="ผลเปรียบเทียบรายจุด เลื่อนแนวนอนได้"><table><thead><tr><th>หลักฐาน / ตำแหน่ง</th><th>เวลาที่สังเกต</th><th>แบบจำลอง</th><th>ค่าฐาน</th><th>คลาดเคลื่อน</th></tr></thead><tbody>${result.observations.map(o=>`<tr><td>${o.kind==='field_arrival'?'เห็นไฟมาถึงจริง':'FIRMS'}<br>${esc(o.source)}<br>${fmt(o.latitude,5)}, ${fmt(o.longitude,5)}</td><td>${fmt(o.elapsed_minutes)} นาที</td><td>${arrival(o.model_arrival_minutes,o.model_arrival_within_horizon)}</td><td>${arrival(o.baseline_arrival_minutes,o.baseline_arrival_within_horizon)}</td><td>${o.kind==='field_arrival'&&o.arrival_error_minutes!==null?fmt(o.arrival_error_minutes)+' นาที':'ไม่ใช้เทียบเวลา'}</td></tr>`).join('')}</tbody></table></div></details><details><summary>ข้อจำกัดของการเทียบ</summary><ul class="evidence-note">${result.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></details>`;
  }
  $('spreadCompare').addEventListener('click',async()=>{if(!last||!observations.length){$('spreadComparison').textContent='เพิ่มหลักฐานอย่างน้อยหนึ่งจุดก่อน';return;}const snapshot=last,revision=observationRevision,points=structuredClone(observations),button=$('spreadCompare');button.disabled=true;
    try{const result=await request('/api/spread/evaluate-snapshot',{snapshot,observations:points});if(last!==snapshot||revision!==observationRevision)return;
      if(result.input_sha256!==snapshot.input_sha256)throw new Error('รหัสผลที่เทียบไม่ตรงกับผลที่กำลังดู');
      comparison={evaluation:result,observations:points};comparisonId=crypto.randomUUID();showComparison(result);$('spreadCompareSave').disabled=!savedModelId;
      $('spreadCompareSaveStatus').textContent=savedModelId?'บันทึกผลเปรียบเทียบนี้ไว้กับผลจำลองเดิมได้':'บันทึกเชื้อเพลิงและผลจำลองก่อน แล้วบันทึกผลเปรียบเทียบได้';
    }catch(error){if(last===snapshot&&revision===observationRevision)$('spreadComparison').textContent='ยังเทียบไม่ได้: '+error.message;}finally{button.disabled=false;}});
  $('spreadCompareSave').addEventListener('click',async()=>{if(!comparison||!savedModelId||!last)return;const selected=comparison,recordId=comparisonId,modelId=savedModelId,forest=last.inputs.request.forest_id,button=$('spreadCompareSave');button.disabled=true;
    try{const session=typeof sb!=='undefined'&&sb?(await sb.auth.getSession()).data.session:null;if(!session)throw new Error('เข้าสู่ระบบก่อนบันทึก');
      await request('/api/community/forests/'+encodeURIComponent(forest)+'/research',{id:recordId,kind:'model',data:{schema:'cme-spread-evaluation-v1',scenario_record_id:modelId,...selected}},session.access_token);
      if(comparison!==selected)return;comparison=null;$('spreadCompareSaveStatus').textContent='บันทึกหลักฐานและผลเปรียบเทียบแล้ว เปิดดูได้จากรายการที่เคยบันทึก ไม่สร้างรายงานเหตุหรือส่งแจ้งเตือน';
    }catch(error){if(comparison===selected){$('spreadCompareSaveStatus').textContent='ยังบันทึกไม่ได้: '+error.message+' · ลองซ้ำได้โดยใช้รหัสเดิม';button.disabled=false;}}});
  host.addEventListener('toggle',()=>{if(host.open){initMap();if(field('forest_id').options.length<=1)catalog();}else stop();});document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  document.addEventListener('click',event=>{if(event.target.closest?.('[data-open-spread]')){window.CmeNavigation?.open('analytics');host.open=true;host.querySelector('summary').focus();host.scrollIntoView({block:'start',behavior:'auto'});}});
  for(const name of ['fuel_time','wind_time','terrain_time','start_at'])field(name).value=thaiNow();terrainMode();materialMode();
  window.CmeSpread={payload,render,stop};
})();
