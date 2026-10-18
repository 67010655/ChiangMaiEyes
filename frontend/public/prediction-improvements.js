(() => {
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=v=>Number.isFinite(v)?v.toFixed(2):'—';
  const date=v=>new Date(v).toLocaleString('th-TH');
  function mount(){
    const anchor=document.getElementById('liveSpreadPanel');if(!anchor||document.getElementById('predictionImprovements'))return;
    const box=document.createElement('section');box.id='predictionImprovements';box.className='ph-card';box.style.cssText='margin:14px 0;color:var(--txt);scroll-margin-top:130px';
    box.innerHTML='<h3>ผลปรับโมเดล · ไฟ ลม และฝุ่นรายสถานี</h3><p class="evidence-note">แยกช่วงปรับค่า เลือกรุ่น และทดสอบตามเวลา เปรียบเทียบไฟโดยให้วิธีฐานใช้พื้นที่เท่ากัน พยากรณ์ฝุ่นรายสถานีเป็นรุ่นทดลองแยกจาก CAMS</p><button class="evidence-action" type="button">ดูผลเปรียบเทียบและพยากรณ์ล่าสุด</button><div data-improvement-result role="status"></div>';
    anchor.after(box);
    box.querySelector('button').addEventListener('click',async e=>{
      const button=e.currentTarget,out=box.querySelector('[data-improvement-result]');button.disabled=true;out.textContent='กำลังอ่านผลทดสอบและข้อมูลสถานี…';
      try{
        const responses=await Promise.all([fetch('/api/hindcast/2026/optimization'),fetch('/api/forecast/stations')]);
        if(responses.some(r=>!r.ok))throw Error('ยังอ่านข้อมูลไม่ได้ กรุณาลองใหม่');
        const [report,live]=await Promise.all(responses.map(r=>r.json()));
        const fire=report.fire,selected=fire.test_selected,current=fire.test_current;
        out.innerHTML=`<h4>ไฟลาม · ${esc(selected.cases)} วันทดสอบ / ${esc(selected.points)} จุดภายหลัง</h4><p>ค้นหา 27 ชุดค่า: รุ่นที่เลือกครอบคลุม ${esc(selected.covered)}/${esc(selected.points)} จุด เทียบกับวงรอบจุดเดิมที่ใช้พื้นที่เท่ากัน ${esc(selected.equal_area_covered)}/${esc(selected.points)} จุด จึงยังไม่เปลี่ยนค่าบนเว็บ</p><p class="evidence-note">รุ่นเดิมครอบคลุม ${esc(current.covered)}/${esc(current.points)} จุด เทียบวิธีพื้นที่เท่ากัน ${esc(current.equal_area_covered)}/${esc(current.points)} จุด ยังไม่พบข้อได้เปรียบทิศทางชัดเจน ทั้งสองกรอบลามเผื่อระยะ 375 เมตร ไม่มีข้อมูลขอบเขตไฟจริงครบเพื่อวัดพื้นที่เตือนเกิน</p><h4>PM2.5 · ความคลาดเคลื่อนเฉลี่ยในชุดทดสอบ (µg/m³)</h4><ul>${Object.entries(report.pm.by_lead).map(([h,b])=>`<li>${esc(h)} ชม.: รุ่นที่เลือก ${fmt(b.test_mae.selected)} · ค่าล่าสุด ${fmt(b.test_mae.now)} · เวลาเดียวกันวันก่อน ${fmt(b.test_mae.previous_day)} (${esc(b.test_pairs)} คู่)</li>`).join('')}</ul><p class="evidence-note">ทดสอบต้นตุลาคม 2 สถานี ไม่ใช่ฤดูเผา ม.ค.–เม.ย. คะแนนนี้ใช้กับพยากรณ์รายชั่วโมงด้านล่าง ไม่ใช่ค่า CAMS รายวัน</p><h4>พยากรณ์รายสถานีล่าสุด · ทดลอง</h4>${live.stations.map(s=>`<div style="border-top:1px solid var(--line);padding:10px 0"><strong>${esc(s.station)}</strong>${s.observation_at?`<p class="evidence-note">ข้อมูลวัด ${esc(date(s.observation_at))} · ${fmt(s.observation_pm25_ug_m3)} µg/m³</p>`:''}${s.forecasts.length?`<ul>${s.forecasts.map(f=>`<li>${esc(date(f.valid_at))}: <strong>${fmt(f.pm25_ug_m3)} µg/m³</strong> (${esc(f.lead_hours_from_observation)} ชม. จากข้อมูลวัด)</li>`).join('')}</ul>`:'<p>ข้อมูลรายชั่วโมงยังไม่ครบหรือเก่าเกิน 6 ชั่วโมง จึงยังไม่ออกค่าพยากรณ์</p>'}${s.status==='partial'?'<p class="evidence-note">แสดงเฉพาะระยะที่ข้อมูลครบ</p>':''}</div>`).join('')}<p class="evidence-note">ลมที่สนามบิน: ปรับค่าแล้ว MAE ระยะ 24 ชั่วโมง ${fmt(report.wind.by_lead['24'].test_mae.linear)} เทียบเดิม ${fmt(report.wind.by_lead['24'].test_mae.raw)} m/s ยังไม่นำสูตรนี้ไปแทนลมภูเขา</p><details><summary>ขอบเขตของผลนี้</summary><ul>${live.notes.map(n=>`<li>${esc(n)}</li>`).join('')}<li>เลือกกรณีไฟจากข้อมูลก่อนเวลาเริ่ม แต่เวลาได้รับข้อมูลดาวเทียมย้อนหลังยังยืนยันไม่ได้</li><li>ดีที่สุดเฉพาะชุดค่าที่ลอง ยังไม่ใช่ข้อพิสูจน์ว่าดีที่สุดทุกสภาพ</li></ul></details><p><a style="color:var(--green)" href="/api/forecast/archive?kind=station" target="_blank" rel="noopener">ตรวจคลังพยากรณ์รายสถานี</a></p>`;
      }catch(error){out.textContent=error.message;}
      finally{button.disabled=false;}
    });
  }
  new MutationObserver(mount).observe(document.body,{childList:true,subtree:true});mount();
})();
