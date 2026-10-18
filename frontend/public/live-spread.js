/* Uses the same API calculation replayed by backtest_live_spread.py. */
(() => {
  'use strict';
  const style=document.createElement('style');
  style.textContent='#liveSpreadPanel{color:var(--txt);scroll-margin-top:130px;margin:14px 0}#liveSpreadPanel a{color:var(--green)}#liveSpreadPanel .leaflet-bottom.leaflet-right{margin-bottom:0}#liveSpreadPanel .leaflet-control-attribution{position:static!important;right:auto!important;left:auto!important;top:auto!important;bottom:auto!important;max-width:none;white-space:normal;z-index:auto}';
  document.head.append(style);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mount(){
    const anchor=document.getElementById('spreadWorkspace');
    if(!anchor || document.getElementById('liveSpreadPanel'))return;
    const panel=document.createElement('section');panel.id='liveSpreadPanel';panel.className='ph-card';panel.style.gridColumn='1/-1';
    panel.innerHTML=`<h3>แนวลามจากจุดดาวเทียมล่าสุด · ทดลอง</h3><p class="evidence-note">ใช้จุดที่ตรวจพบใน 24 ชั่วโมง ลม GFS รายชั่วโมง และทางลาดประมาณ 110 เมตร โดยสมมติเชื้อเพลิง FM1 ความชื้น 8% และตัวคูณลม 0.2</p><p class="evidence-note">ทดสอบ 8 กรณีช่วงมีนาคม–เมษายน 2026: กรอบครอบคลุมจุดภายหลัง 36/305 จุด (11.8%) หรือ 165/305 จุด (54.1%) เมื่อขยายกรอบ 375 เมตร เทียบกับบริเวณจุดเดิม 131/305 จุด (43.0%) แต่พื้นที่กรอบเพิ่ม 2.17 เท่า ตัวเลขนี้ยังไม่ใช่ความแม่นยำของขอบเขตไฟจริง</p><button type="button" class="evidence-action" data-live-spread>คำนวณจากข้อมูลล่าสุด</button> <a href="/api/forecast/archive" target="_blank" rel="noopener">คลังคำพยากรณ์ที่บันทึกจริง</a><div data-live-output role="status"></div>`;
    anchor.before(panel);
    panel.querySelector('button').addEventListener('click',async e=>{
      const button=e.currentTarget, out=panel.querySelector('[data-live-output]');button.disabled=true;out.textContent='กำลังอ่านจุดดาวเทียมและลม…';
      try{
        const response=await fetch('/api/spread/live');if(!response.ok)throw Error('โหลดข้อมูลไม่ได้ กรุณาลองใหม่');
        const data=await response.json();if(!panel.isConnected)return;
        out.innerHTML=`<p>คำนวณ ${esc(new Date(data.as_of).toLocaleString('th-TH'))} · ใช้ ${esc(data.used_points)}/${esc(data.eligible_points)} จุด · เว้นเพราะข้อมูลไม่ครบ ${esc(data.excluded.length)} จุด · เกินขีดจำกัด ${esc(data.omitted_by_limit)} จุด</p><p class="evidence-note">${data.used_points?'สีส้ม = กรอบทดลอง 3 ชั่วโมง · สีแดง = 6 ชั่วโมง · จุดดำ = จุดเริ่ม':'ไม่มีจุดพร้อมข้อมูลเพียงพอสำหรับคำนวณรอบนี้ ไม่ได้หมายความว่าไม่มีไฟ'}</p><div data-live-map style="height:340px;position:relative;z-index:0"></div><details><summary>สมมติฐานและข้อจำกัด</summary><ul>${data.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details><a href="/api/forecast/archive?kind=spread" target="_blank" rel="noopener">ตรวจรายการผลลามที่บันทึกแล้ว</a>`;
        if(!data.used_points){out.querySelector('[data-live-map]').remove();return;}
        const map=L.map(out.querySelector('[data-live-map]')).setView([18.8,98.9],10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(map);
        const layers=[];
        [...data.frames].reverse().forEach(f=>layers.push(L.geoJSON(f.geometry,{style:{color:f.hours===3?'#e99a15':'#d94b4b',weight:2,fillOpacity:.12}}).addTo(map)));
        data.inputs.forEach(i=>L.circleMarker([i.point.latitude,i.point.longitude],{radius:3,color:'#222'}).addTo(map));
        const bounds=L.featureGroup(layers).getBounds();if(bounds.isValid())map.fitBounds(bounds.pad(.2),{maxZoom:14});
        const attribution=out.querySelector('.leaflet-control-attribution');if(attribution)attribution.style.setProperty('position','static','important');
        requestAnimationFrame(()=>map.invalidateSize());
      }catch(error){out.textContent=error.message||'คำนวณไม่ได้ กรุณาลองใหม่';}
      finally{button.disabled=false;}
    });
  }
  new MutationObserver(mount).observe(document.body,{childList:true,subtree:true});mount();
})();
