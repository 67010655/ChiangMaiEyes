/* Historical diagnostics never replace current conditions or dispatch alerts. */
(() => {
  'use strict';
  const host = document.getElementById('hindcastWorkspace');
  if (!host) return;
  const content = document.getElementById('hindcastContent');
  const esc = value => CmeEvidence.escapeHtml(value);
  const fmt = (n, d = 2) => Number.isFinite(n) ? n.toLocaleString('th-TH', {maximumFractionDigits:d}) : 'ยังประเมินไม่ได้';
  let report, loading = false, map, layers, generation = 0;
  async function get(path, body) {
    const response = await fetch(path, {method:body ? 'POST' : 'GET', headers:body ? {'Content-Type':'application/json'} : {},
      body:body ? JSON.stringify(body) : undefined, signal:AbortSignal.timeout(30000)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'การเชื่อมต่อไม่สำเร็จ');
    return data;
  }
  function chart(key, label, color) {
    const vals = report.daily.map(r => r[key]);
    const max = Math.max(1, ...vals.filter(Number.isFinite));
    return `<figure style="margin:12px 0"><figcaption>${esc(label)} · ค่าสูงสุด ${fmt(max,1)}</figcaption>
      <svg viewBox="0 0 720 110" role="img" aria-label="${esc(label)} มกราคมถึงเมษายน 2569" style="width:100%;max-height:150px">
      <line x1="0" y1="88" x2="720" y2="88" stroke="currentColor" opacity=".3"/>
      ${vals.map((v,i) => Number.isFinite(v) ? `<rect x="${i*6}" y="${88-v/max*80}" width="5" height="${v/max*80}" fill="${color}"><title>${esc(report.daily[i].date)}: ${fmt(v,1)}</title></rect>` : '').join('')}
      ${[['ม.ค.',0],['ก.พ.',186],['มี.ค.',354],['เม.ย.',540]].map(([m,x]) => `<text x="${x}" y="106" fill="currentColor" font-size="13">${m}</text>`).join('')}</svg></figure>`;
  }
  function selected() {
    const row = report.cases.find(c => c.id === document.getElementById('hindcastCase').value);
    const index = Number(document.getElementById('hindcastVariant').value);
    return [row, row.scenarios[index]];
  }
  function draw(row, scenario) {
    if (typeof L === 'undefined') return;
    if (!map) {
      map = L.map('hindcastMap', {scrollWheelZoom:false,zoomAnimation:false}).setView([18.79,98.99],9);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
      layers = L.featureGroup().addTo(map);
    }
    map.invalidateSize({pan:false}); layers.clearLayers();
    if (scenario.final_frame.geometry) L.geoJSON(scenario.final_frame.geometry, {style:{color:'#cf730d',weight:2,fillOpacity:.15}}).addTo(layers);
    L.circleMarker([row.seed.latitude,row.seed.longitude], {radius:7,color:'#d33453',fillOpacity:1}).bindTooltip('จุดตรวจพบเริ่มต้นแทนเวลาเกิดไฟ · ไม่ใช่จุดจุดไฟที่ยืนยัน').addTo(layers);
    row.observations.forEach(o => L.circleMarker([o.latitude,o.longitude], {radius:4,color:'#2ba6b2',fillOpacity:.8}).bindTooltip(CmeEvidence.stamp(o.observed_at)).addTo(layers));
    map.fitBounds(layers.getBounds(), {padding:[25,25],maxZoom:14,animate:false});
  }
  function showCase() {
    generation++;
    const [row,s] = selected();
    document.getElementById('hindcastCaseResult').innerHTML = `<p>จุดเริ่มแทนจากดาวเทียม ${esc(CmeEvidence.stamp(row.seed.detected_at))} · ${fmt(row.seed.latitude,5)}, ${fmt(row.seed.longitude,5)}<br>
      จุดตรวจพบภายหลังในระยะ 5 km / 6 ชั่วโมง: <b>${fmt(row.observation_count,0)} จุด</b> · ลม ERA5 ที่ 10 m: ${fmt(row.era5_wind_10m_mps)} m/s จาก ${fmt(row.wind_from_deg,0)}°</p>
      <p>สมมติ FM1 · ความชื้น ${fmt(s.moisture_pct,0)}% · ลมใกล้เปลวไฟ = ลม 10 m × ${fmt(s.factor,1)} · ทางราบ 0°</p>
      <div class="spread-table-wrap"><table><thead><tr><th>ผลตามสมมติฐาน</th><th>ค่า</th></tr></thead><tbody>
      <tr><td>อัตราลามด้านหัวไฟ</td><td>${fmt(s.head_m_min)} m/min</td></tr>
      <tr><td>พื้นที่วงรีหลัง 6 ชั่วโมง</td><td>${fmt(s.final_frame.scenario_area_ha)} ha</td></tr>
      <tr><td>จุดภายหลังที่วงรีครอบ ณ เวลาตรวจพบ</td><td>${fmt(s.coverage_percent)}%</td></tr>
      <tr><td>ค่าฐานเชื้อเพลิงเดิม ไม่มีลม ทางราบ</td><td>${fmt(s.baseline_coverage_percent)}%</td></tr></tbody></table></div>
      <p class="evidence-note">เปอร์เซ็นต์ข้างต้นเป็นสัดส่วนจุดตรวจพบที่ครอบได้ ไม่ใช่ accuracy และอาจสูงขึ้นเมื่อวงรีใหญ่เกินจริง จุดเหล่านี้ยังไม่ยืนยันว่าเป็นไฟเหตุเดียวกัน</p>`;
    document.getElementById('hindcastRunStatus').textContent = 'เลือกกรณีและสมมติฐาน แล้วรันผ่านเครื่องคำนวณของเว็บซ้ำได้';
    draw(row,s);
  }
  function render() {
    const w=report.wind;
    const cases=report.cases.filter(c => c.scenarios?.length);
    const central=report.fire.coverage_grid?.find(s=>s.factor===.2&&s.moisture_pct===8);
    content.innerHTML = `<p><strong>ผลทดลองชุดแรก · สมมติจุดเริ่มเดียว</strong><br>มีผลเทียบสถานีจริงและการเริ่มจากจุดที่ตรวจพบทั้งกลุ่มในหัวข้อ “ความแม่นยำที่วัดได้” ด้านบน<br>1 มกราคม–30 เมษายน 2569 · ข้อมูลครบ ${fmt(report.complete_days,0)}/${fmt(report.requested_days,0)} วัน · NASA VIIRS ${fmt(report.detections,0)} การตรวจพบในขอบเขตจังหวัด</p>
      <p class="evidence-note">ใช้ข้อมูลที่เรียกย้อนหลังในปัจจุบัน เลือกวันพีคและจุดเริ่มด้วยข้อมูลที่รู้ภายหลัง เชื้อเพลิง ความชื้น ทางลาด และตัวคูณลมยังเป็นสมมติฐาน ไม่ใช่ผลสำรวจของเหตุจริง</p>
      ${chart('detections','จุดความร้อน · การตรวจพบ/วัน','#c88332')}${chart('pm25_cams_mean','PM2.5 CAMS ณ กริดเมือง · µg/m³ (แบบจำลอง)','#369da6')}
      <div class="spread-table-wrap"><table><thead><tr><th>ส่วนที่ตรวจ</th><th>ผล</th><th>ขอบเขตหลักฐาน</th></tr></thead><tbody>
      <tr><td>ไฟลาม</td><td>ยังให้ accuracy / IoU ไม่ได้</td><td>ขาดกรอบไฟและเวลาไฟมาถึงอิสระ</td></tr>
      <tr><td>ลม GFS ล่วงหน้า 24 ชั่วโมง</td><td>MAE ${fmt(w.speed.mae)} m/s · RMSE ${fmt(w.speed.rmse)} m/s · ${fmt(w.speed.n,0)} คู่</td><td>เทียบ ERA5 ที่พิกัดเมือง ไม่ใช่สถานีหรือกลางเปลวไฟ</td></tr>
      <tr><td>ลมค่าฐานใช้ค่าเมื่อ 24 ชั่วโมงก่อน</td><td>MAE ${fmt(w.persistence_24h.mae)} m/s · ${fmt(w.persistence_24h.n,0)} คู่</td><td>ดูจำนวนคู่และช่วงเวลาที่ใช้ประกอบ</td></tr>
      <tr><td>PM2.5</td><td>ดูผลเทียบ Air4Thai ในชุดประเมินล่าสุดด้านบน</td><td>ชุดแรกนี้ยังไม่ได้จับคู่สถานี จึงไม่ใช่คะแนนฝุ่นล่าสุด</td></tr></tbody></table></div>
      <p class="evidence-note">CAMS เป็นแบบจำลองฝุ่นแยกจากไฟวงรีนี้ ยังไม่มีระบบคำนวณการปล่อยและการพัดพาควันจากไฟไปยังสถานี</p>
      ${central?`<p>สมมติฐานกลางที่กำหนดไว้ (ความชื้น 8% · ตัวคูณลม 0.2): วงรีครอบ <strong>${fmt(central.covered_count,0)}/${fmt(central.point_count,0)} จุด (${fmt(central.coverage_percent)}%)</strong> ใน ${fmt(report.fire.diagnostic_case_count,0)} กรณีวันพีค · ตัวเลขนี้ไม่ใช่ความแม่นยำของพื้นที่ไฟไหม้ และกรณีต่างวันอาจมีไฟซ้ำกัน</p>`:''}
      ${report.pm25_catalog?`<p class="evidence-note">ไฟล์รายวันจากบัญชีข้อมูลจังหวัด: 6 พื้นที่ · ${fmt(report.pm25_catalog.numeric_nonnegative_rows,0)}/${fmt(report.pm25_catalog.rows_2026,0)} แถวมีตัวเลขในปี 2569 แต่ครอบคลุมเพียง ม.ค.–ก.พ. และยังไม่ยืนยันช่วงเฉลี่ย/รหัสสถานี จึงไม่นำมาคิดคะแนนฝุ่นช่วง ม.ค.–เม.ย.</p>`:''}
      <label>กรณีวันพีค<select id="hindcastCase">${cases.map(c => `<option value="${esc(c.id)}">${esc(c.id)} · ${fmt(c.observation_count,0)} จุดภายหลัง</option>`).join('')}</select></label>
      <label>ลองเปลี่ยนสมมติฐาน<select id="hindcastVariant">${(cases[0]?.scenarios||[]).map((s,i) => `<option value="${i}" ${s.factor===.2&&s.moisture_pct===8?'selected':''}>ความชื้น ${s.moisture_pct}% · ตัวคูณลม ${s.factor}</option>`).join('')}</select></label>
      <div id="hindcastMap" class="spread-map" role="region" aria-label="จุดความร้อนจริงและวงรีตามสมมติฐานย้อนหลัง"></div><div id="hindcastCaseResult"></div>
      <button type="button" id="hindcastRun" ${cases.length?'':'disabled'}>รันกรณีนี้ผ่าน API ของเว็บ</button><p role="status" aria-live="polite" id="hindcastRunStatus"></p>
      <details><summary>ข้อจำกัดและแหล่งข้อมูล</summary><ul>${report.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>
      <p>${Object.entries(report.sources).map(([k,v]) => `<a target="_blank" rel="noopener noreferrer" href="${esc(v)}">${esc(k)}</a>`).join(' · ')}</p>
      <a href="/api/hindcast/2026" target="_blank" rel="noopener noreferrer">เปิดชุดข้อมูลและผล JSON สำหรับตรวจซ้ำ</a></details>`;
    if (!cases.length) {document.getElementById('hindcastRunStatus').textContent='ไม่มีกรณีที่มีจุดตรวจพบภายหลังในหน้าต่างที่กำหนด';return;}
    document.getElementById('hindcastCase').addEventListener('change',showCase);
    document.getElementById('hindcastVariant').addEventListener('change',showCase);
    document.getElementById('hindcastRun').addEventListener('click',async event => {
      const button=event.currentTarget,seq=++generation,[row,s]=selected();button.disabled=true;
      const status=document.getElementById('hindcastRunStatus');status.textContent='กำลังจำลองและเทียบจุดจริงผ่าน API…';
      try {
        const snapshot=await get('/api/spread/simulate',s.request);
        const evaluation=await get('/api/spread/evaluate-snapshot',{snapshot,observations:row.observations});
        if(seq!==generation)return;
        const same=Math.abs(evaluation.nominal_point_coverage_percent-s.coverage_percent)<1e-8;
        status.textContent=`รันซ้ำแล้ว · ${same?'ตรงกับผลที่บันทึก':'ผลต่างจากชุดที่บันทึก ต้องตรวจรุ่นโมเดล'} · ครอบ ${fmt(evaluation.nominal_point_coverage_percent)}% ของ ${fmt(evaluation.unique_observation_count,0)} จุด · ยังไม่ใช่ accuracy · คำนวณเมื่อ ${CmeEvidence.stamp(snapshot.issued_at)}`;
      } catch(error) {if(seq===generation)status.textContent='รันไม่ได้: '+error.message;}
      finally {button.disabled=false;}
    });
    showCase();
  }
  host.addEventListener('toggle',async () => {
    if (!host.open) return;
    if (report) {map?.invalidateSize({pan:false});return;}
    if (loading) return;
    loading=true;content.innerHTML='<p role="status">กำลังอ่านชุดทดลองย้อนหลัง…</p>';
    try {report=await get('/api/hindcast/2026');render();}
    catch(error) {report=null;content.innerHTML=`<p role="status">อ่านข้อมูลไม่ได้: ${esc(error.message)}</p><button type="button" id="hindcastRetry">ลองอ่านอีกครั้ง</button>`;
      document.getElementById('hindcastRetry').addEventListener('click',()=>{host.open=false;host.open=true;});}
    finally {loading=false;}
  });
})();
