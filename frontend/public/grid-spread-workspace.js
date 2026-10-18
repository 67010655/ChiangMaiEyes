(() => {
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const percent=(n,d)=>d?`${(100*n/d).toFixed(1)}%`:'ไม่มีข้อมูล';
  const names={current_wavelet:'วงรีรายชั่วโมงเดิม',grid_terrain:'กริดทางลาด',grid_terrain_landcover:'กริดทางลาด + สิ่งปกคลุมดิน'};
  const style=document.createElement('style');style.textContent='#gridSpreadWorkspace{color:var(--txt);margin:14px 0;scroll-margin-top:130px}#gridSpreadWorkspace .grid-result{padding:14px}#gridSpreadWorkspace .grid-map{height:340px;position:relative;z-index:0;margin:14px 0}#gridSpreadWorkspace .leaflet-bottom.leaflet-right{margin-bottom:0}#gridSpreadWorkspace .leaflet-control-attribution{position:static!important;inset:auto!important;max-width:none;white-space:normal;z-index:auto}#gridSpreadWorkspace a{color:var(--green)}#gridSpreadWorkspace li{margin:8px 0}';document.head.append(style);
  function mount(){
    const anchor=document.getElementById('predictionImprovements');if(!anchor||document.getElementById('gridSpreadWorkspace'))return;
    const panel=document.createElement('details');panel.id='gridSpreadWorkspace';panel.className='spread-workspace';
    panel.innerHTML='<summary>รุ่นกริด · ลามตามภูมิประเทศและเทียบรอยเผา Sentinel‑2</summary><div class="grid-result"><p>ทางลาดเปลี่ยนตามช่องประมาณ 110 เมตร ใช้สิ่งปกคลุมดิน WorldCover ปี 2021 กั้นบางพื้นที่ ลมเปลี่ยนรายชั่วโมง เชื้อเพลิงยังเป็นค่าทดลอง</p><button type="button" class="evidence-action" data-grid-validation>ดูผลทดสอบและแผนที่ย้อนหลัง</button> <button type="button" class="evidence-action" data-grid-live>คำนวณกริดจากจุดล่าสุด</button><div data-grid-validation-output role="status"></div><div data-grid-live-output role="status"></div></div>';
    anchor.after(panel);const maps=new Map();
    function map(host,key){if(maps.has(key))maps.get(key).remove();const instance=L.map(host).setView([18.8,98.9],10);maps.set(key,instance);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(instance);requestAnimationFrame(()=>instance.invalidateSize());return instance;}
    panel.querySelector('[data-grid-validation]').addEventListener('click',async event=>{
      const button=event.currentTarget,out=panel.querySelector('[data-grid-validation-output]');button.disabled=true;out.textContent='กำลังอ่านผลทดสอบและรอยเผา…';
      try{
        const response=await fetch('/api/hindcast/2026/grid-validation');if(!response.ok)throw Error('ยังอ่านผลทดสอบไม่ได้ กรุณาลองใหม่');const data=await response.json();
        const test=data.test;
        out.innerHTML=`<h4>ทดสอบปลายมีนาคม–เมษายน · ${esc(test.cases)} วัน / ${esc(test.points)} จุดภายหลัง</h4><p>${esc(data.decision_th)}</p><ul>${Object.entries(test.models).map(([name,m])=>`<li><strong>${esc(names[name]||name)}</strong>: กรอบไม่เผื่อระยะครอบคลุม ${esc(m.covered)}/${esc(test.points)} จุด; เมื่อเผื่อ 375 เมตร ${esc(m.covered_375m)}/${esc(test.points)} เทียบวิธีวงรอบจุดเดิมที่มีพื้นที่เท่ากัน ${esc(m.equal_area_covered_375m)}/${esc(test.points)}</li>`).join('')}</ul><h4>ความสอดคล้องกับรอยเผารายสัปดาห์</h4><ul>${Object.entries(test.models).map(([name,m])=>`<li>${esc(names[name]||name)}: ${percent(m.weekly_reference.intersection_ha,m.weekly_reference.evaluated_predicted_area_ha)} ของพื้นที่คาดการณ์ที่มีภาพอ้างอิง พบซ้อนรอยเผา (${esc(m.weekly_reference.cases)} กรณีที่มีข้อมูล)</li>`).join('')}</ul><p class="evidence-note">นี่ไม่ใช่ accuracy ของไฟ 6 ชั่วโมง รอยเผาเป็นผลรวม 7 วัน แถบจำนวนภาพไม่ยืนยันว่าไร้เมฆ การไม่พบรอยเผาจึงยังเรียกว่าเตือนผิดไม่ได้ และพื้นที่กรณีซ้อนกันได้</p><p class="evidence-note">ตัวอย่าง ${esc(data.example.id)} · เริ่ม ${esc(new Date(data.example.as_of).toLocaleString('th-TH'))} · ผลจำลอง 6 ชั่วโมง เทียบรอยเผาของสัปดาห์ที่ครอบวันนั้น</p><div class="grid-map" data-grid-example-map></div><p class="evidence-note">น้ำเงิน = วงรีเดิม · ม่วง = รุ่นกริด · ส้ม = รอยเผารายสัปดาห์<br>รอยเผาอ้างอิง: TamRoyPao / HII / Kasetsart University · สิ่งปกคลุมดิน: © ESA WorldCover project 2021 · ความสูง: Copernicus DEM</p><details><summary>วิธีทดสอบและข้อจำกัด</summary><ul>${data.notes_th.map(n=>`<li>${esc(n)}</li>`).join('')}</ul><a href="https://tamroypao.hii.or.th/" target="_blank" rel="noopener">ข้อมูลตามรอยเผาต้นทาง</a></details>`;
        const instance=map(out.querySelector('[data-grid-example-map]'),'reference');const layers={};
        layers['รอยเผาอ้างอิงรายสัปดาห์']=L.geoJSON(data.example.weekly_reference,{style:{color:'#f0a331',weight:1,fillOpacity:.25}}).addTo(instance);
        Object.entries(data.example.geometry).forEach(([name,geometry])=>{const layer=L.geoJSON(geometry,{style:{color:name==='current_wavelet'?'#53a8ed':name==='grid_terrain'?'#aaa':'#df58e5',weight:2,fillOpacity:.07}});layers[names[name]]=layer;if(name!=='grid_terrain')layer.addTo(instance);});
        L.control.layers(null,layers,{collapsed:true}).addTo(instance);
        data.example.initial.forEach(p=>L.circleMarker([p.latitude,p.longitude],{radius:3,color:'#202020'}).addTo(instance));
        const bounds=L.featureGroup(Object.values(layers)).getBounds();if(bounds.isValid())instance.fitBounds(bounds.pad(.1),{maxZoom:14});
      }catch(error){out.textContent=error.message;}
      finally{button.disabled=false;}
    });
    panel.querySelector('[data-grid-live]').addEventListener('click',async event=>{
      const button=event.currentTarget,out=panel.querySelector('[data-grid-live-output]');button.disabled=true;out.textContent='กำลังคำนวณลามบนกริด…';
      try{
        const response=await fetch('/api/spread/grid');if(!response.ok)throw Error('ยังคำนวณกริดไม่ได้ กรุณาลองใหม่');const data=await response.json();
        out.innerHTML=`<h4>กริดทดลองล่าสุด</h4><p>${esc(new Date(data.as_of).toLocaleString('th-TH'))} · ใช้ ${esc(data.used_origins)}/${esc(data.inputs.length)} จุด · ${esc(data.processed_cells)} ช่อง ${data.truncated?'· ผลบางส่วนเพราะถึงขีดจำกัด':''}</p>${data.used_origins?'<div class="grid-map" data-grid-live-map></div>':'<p>ไม่มีจุดที่พร้อมคำนวณในรอบนี้ ไม่ได้หมายความว่าไม่มีไฟ</p>'}<p class="evidence-note">ส้ม = 3 ชั่วโมง · ม่วง = 6 ชั่วโมง</p><details><summary>สมมติฐานและข้อจำกัด</summary><ul>${data.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details><p><a href="/api/forecast/archive?kind=grid" target="_blank" rel="noopener">ตรวจผลกริดที่บันทึกแล้ว</a></p>`;
        if(data.used_origins){const instance=map(out.querySelector('[data-grid-live-map]'),'live');const layers=[...data.frames].reverse().map(f=>L.geoJSON(f.geometry,{style:{color:f.hours===3?'#e79b25':'#df58e5',weight:1,fillOpacity:.15}}).addTo(instance));data.inputs.forEach(i=>L.circleMarker([i.point.latitude,i.point.longitude],{radius:3,color:'#222'}).addTo(instance));const bounds=L.featureGroup(layers).getBounds();if(bounds.isValid())instance.fitBounds(bounds.pad(.15),{maxZoom:14});}
      }catch(error){out.textContent=error.message;}
      finally{button.disabled=false;}
    });
  }
  new MutationObserver(mount).observe(document.body,{childList:true,subtree:true});mount();
})();


