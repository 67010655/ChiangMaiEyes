/* Public, read-only measured performance. No test result changes live forecasts. */
(() => {
  'use strict';
  const host=document.getElementById('validationWorkspace');if(!host)return;
  const content=document.getElementById('validationContent');
  const esc=value=>CmeEvidence.escapeHtml(value);
  const fmt=(n,d=2)=>Number.isFinite(n)?n.toLocaleString('th-TH',{maximumFractionDigits:d}):'—';
  const metric=(m,key='mae')=>fmt(m?.[key]);
  const variants={single_seed_flat:'จุดเริ่มเดียว · ทางราบ',all_initial_flat:'จุดเริ่มทั้งกลุ่ม · ทางราบ',all_initial_dem:'จุดเริ่มทั้งกลุ่ม + DSM ณ จุดจริง'};
  let report,loading=false,map,layers;
  function table(headers,rows){return `<div class="spread-table-wrap"><table><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
  function pmChart(sid){
    const rows=report.pm25_daily.rows.filter(r=>r.station_id===sid),max=Math.max(1,...rows.flatMap(r=>[r.observed,r.cams]).filter(Number.isFinite));
    const line=key=>rows.map((r,i)=>Number.isFinite(r[key])?`${i*680/Math.max(1,rows.length-1)+35},${170-r[key]/max*145}`:null);
    // Split paths at real observation gaps rather than drawing fabricated values.
    const paths=key=>{const segments=[];let segment=[];for(const p of line(key)){if(p)segment.push(p);else if(segment.length){segments.push(segment);segment=[];}}if(segment.length)segments.push(segment);return segments;};
    document.getElementById('validationPmChart').innerHTML=`<div class="validation-legend"><span><i style="background:#28b9bc"></i>สถานี ${esc(sid)}</span><span><i style="background:#dc9c4b"></i>CAMS เฉลี่ยตามวันไทย</span></div>
      <svg viewBox="0 0 735 202" role="img" aria-label="เทียบ PM2.5 สถานี ${esc(sid)} กับ CAMS มกราคมถึงเมษายน 2569 หน่วยไมโครกรัมต่อลูกบาศก์เมตร">
      <text x="0" y="20" fill="currentColor" font-size="12">${fmt(max,0)}</text><text x="12" y="174" fill="currentColor" font-size="12">0</text>
      <line x1="35" y1="170" x2="720" y2="170" stroke="currentColor" opacity=".25"/>
      ${['cams','observed'].map(key=>paths(key).map(s=>`<polyline points="${s.join(' ')}" fill="none" stroke="${key==='observed'?'#28b9bc':'#dc9c4b'}" stroke-width="2"/>`).join('')).join('')}
      ${[['ม.ค.',35],['ก.พ.',212],['มี.ค.',372],['เม.ย.',550]].map(([m,x])=>`<text x="${x}" y="197" fill="currentColor" font-size="13">${m}</text>`).join('')}</svg>`;
  }
  function fireCase(){
    const row=report.fire_followup.cases.find(r=>r.id===document.getElementById('validationFireCase').value);
    const name=document.getElementById('validationFireVariant').value,v=row.variants[name];
    const score=v.scores.find(s=>s.tolerance_m===375);
    document.getElementById('validationFireReadout').innerHTML=`<p>เวลาเริ่มเทียบ ${esc(CmeEvidence.stamp(row.as_of))} · รู้จุดเริ่ม ${fmt(row.initial.length,0)} จุด · ตรวจพบภายหลัง ${fmt(row.later.length,0)} จุด</p>
      ${table(['ตัวชี้วัด','ผล'],[
        ['จุดภายหลังที่ครอบได้',`${fmt(score.covered,0)}/${fmt(score.points,0)} (${fmt(score.coverage_percent)}%)`],
        ['ค่าฐานคงตำแหน่งจุดเดิม',`${fmt(score.baseline_covered,0)}/${fmt(score.points,0)} (${fmt(score.baseline_coverage_percent)}%)`],
        ['จุดนอกค่าฐานที่แบบจำลองครอบเพิ่ม',`${fmt(score.new_covered,0)}/${fmt(score.new_points,0)}`],
        ['พื้นที่ครอบ ณ จุดตรวจภายหลังสุดท้าย',`${fmt(score.search_envelope_area_ha)} ha ที่ ${fmt(score.area_at_minutes,0)} นาที`],
        ['พื้นที่ครอบของค่าฐาน',`${fmt(score.stationary_envelope_area_ha)} ha`]
      ])}
      <p class="evidence-note">ใช้ระยะจับคู่ 375 m เท่ากันทุกวิธี เป็นการลองเผื่อขนาดพิกเซล ไม่ใช่รัศมีความเชื่อมั่น ยังไม่ทราบพื้นที่ที่คาดเกินจากการทดสอบจุดบวกอย่างเดียว</p>
      ${v.legacy_slope_clamp_omitted_count?'<p class="evidence-note">บางจุดมีผลของทางลาดสูงในสมการรุ่นนี้ ควรอ่านพื้นที่ครอบควบคู่กับเปอร์เซ็นต์จุดที่ครอบได้</p>':''}`;
    if(typeof L==='undefined')return;
    if(!map){map=L.map('validationFireMap',{scrollWheelZoom:false,zoomAnimation:false}).setView([18.79,98.99],9);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map);layers=L.featureGroup().addTo(map);}
    map.invalidateSize({pan:false});layers.clearLayers();
    L.geoJSON(v.evaluation_geometry_375m,{style:{color:'#dc9c4b',weight:2,fillOpacity:.13}}).addTo(layers);
    row.initial.forEach(p=>L.circleMarker([p.latitude,p.longitude],{radius:5,color:'#ee785c',fillOpacity:1}).bindTooltip('จุดที่ทราบก่อนเริ่มเทียบ').addTo(layers));
    row.later.forEach(p=>L.circleMarker([p.latitude,p.longitude],{radius:4,color:'#28b9bc',fillOpacity:.8}).bindTooltip(CmeEvidence.stamp(p.detected_at)).addTo(layers));
    map.fitBounds(layers.getBounds(),{padding:[22,22],maxZoom:14,animate:false});
  }
  function render(){
    const pm=report.pm25_daily,wind=report.wind_station.by_lead['24'],fire=report.fire_followup;
    const firePrimary=fire.summary.find(s=>s.variant==='all_initial_dem'&&s.tolerance_m===375);
    const correction=pm.matched_comparison,recent=report.pm25_recent;
    content.innerHTML=`<p><strong>ผลประเมินสำหรับ Dashboard ช่วยตัดสินใจ</strong><br>แสดงค่าคลาดเคลื่อนพร้อมแหล่งอ้างอิงและจำนวนคู่ข้อมูล ประมวลผลเมื่อ ${esc(CmeEvidence.stamp(report.generated_at))}</p>
      <div class="validation-summary">
        <article><h3>PM2.5 เทียบสถานี · ม.ค.–เม.ย. 2569</h3><strong>${metric(pm.all_valid_pairs.cams)} µg/m³</strong><p>ต่างเฉลี่ย (MAE) · ${fmt(pm.valid_station_days,0)}/${fmt(pm.expected_station_days,0)} คู่สถานี–วัน · CAMS ย้อนหลังกับ Air4Thai</p></article>
        <article><h3>ลม GFS ล่วงหน้า 24 ชั่วโมง</h3><strong>${metric(wind.metrics.gfs)} m/s</strong><p>MAE เทียบสนามบินเชียงใหม่ · ${fmt(wind.metrics.gfs.n,0)} ชั่วโมง · ดีกว่าค่าฐาน ${fmt(wind.skill_vs_persistence_percent,1)}%</p></article>
        <article><h3>จุดความร้อนภายหลังที่ครอบได้</h3><strong>${fmt(firePrimary.coverage_percent)}%</strong><p>${fmt(firePrimary.covered,0)}/${fmt(firePrimary.points,0)} จุด · ค่าฐาน ${fmt(firePrimary.baseline_coverage_percent)}% · ไม่ใช่ accuracy ของพื้นที่ไหม้</p></article>
      </div>
      <div class="validation-verdict">อ่านอย่างไร: <b>MAE ยิ่งต่ำยิ่งใกล้ข้อมูลวัด</b> ตัวเลขของไฟเป็นสัดส่วนจุดตรวจพบที่ครอบได้ ต้องดูพื้นที่ครอบด้วย ทั้งสามส่วนเป็นคนละตัวชี้วัด จึงไม่มีเปอร์เซ็นต์ความแม่นยำรวมตัวเดียว</div>
      <h3>ฝุ่นช่วงฤดูไฟ: เทียบกับค่าที่วัดจริง</h3>
      <p class="evidence-note">Air4Thai สถานี 35T/36T ระบุค่าเฉลี่ย 24 ชั่วโมงและ QC เบื้องต้น ช่วงสิ้นสุด 24 ชั่วโมงไม่ได้ระบุชัด จึงใช้ค่า CAMS เฉลี่ย 00:00–24:00 น. ไทยเป็นสมมติฐานหลัก ข้อมูล CAMS ชุดนี้เป็น archive ไม่ใช่ผลที่แช่แข็งไว้ ณ lead 24 ชั่วโมง</p>
      ${table(['วิธี · ใช้คู่ครบเท่ากัน','MAE (µg/m³)','RMSE (µg/m³)','จำนวนคู่'],[
        ['CAMS ย้อนหลัง',metric(correction.cams),metric(correction.cams,'rmse'),fmt(correction.cams.n,0)],
        ['CAMS ปรับ bias จาก ม.ค.–เม.ย. 2568',metric(correction.cams_bias_2025),metric(correction.cams_bias_2025,'rmse'),fmt(correction.cams_bias_2025.n,0)],
        ['ค่าฐานใช้ค่าที่สถานีวันก่อน',metric(correction.persistence),metric(correction.persistence,'rmse'),fmt(correction.persistence.n,0)]
      ])}
      <p class="evidence-note">ค่าฐานวันก่อนเป็นเกณฑ์เปรียบเทียบตามวันที่ในไฟล์ ไม่ได้รับรองว่ามีข้อมูลส่งถึงระบบทันเวลาจริง การปรับ bias ยังไม่เปิดแทนผลพยากรณ์หลัก: ผลดีขึ้นเล็กน้อยเมื่อรวมสถานี แต่บางสถานีแย่ลง</p>
      <label>ดูกราฟเทียบรายสถานี<select id="validationPmStation"><option value="35T">35T · ศูนย์ราชการจังหวัดเชียงใหม่</option><option value="36T">36T · โรงเรียนยุพราชวิทยาลัย</option></select></label>
      <figure id="validationPmChart" class="validation-chart"></figure>
      <h3>ลองพยากรณ์ฝุ่นล่วงหน้า 6 / 12 / 24 ชั่วโมง</h3>
      <p class="evidence-note">ใช้ข้อมูลรายชั่วโมงสองสถานี ฝึกผ่าน 30 ก.ย. แล้วทดสอบต้นทาง 1–15 ต.ค. / ผลจริงถึง 16 ต.ค. 2569 โมเดลทดลองใช้ค่าอดีตเท่านั้น ไม่มีค่าฝุ่นอนาคตใน input ช่วงนี้อยู่นอกฤดูไฟพีค และเป็นคนละโมเดลกับ CAMS ที่เว็บใช้อยู่</p>
      ${table(['ล่วงหน้า','โมเดลทดลอง MAE','ใช้ค่าล่าสุด MAE','ใช้ชั่วโมงเดียวกันวันก่อน MAE','จำนวนคู่'],Object.entries(recent.by_lead).map(([h,v])=>[
        `${esc(h)} ชั่วโมง`,metric(v.metrics.ridge),metric(v.metrics.persistence),metric(v.metrics.same_hour_previous_day),fmt(v.metrics.ridge.n,0)
      ]))}
      <p class="evidence-note">ทุกค่าตารางนี้เป็น µg/m³ โมเดลสถิติที่ลองยังไม่ชนะค่าฐาน จึงคงผลนี้เป็นการทดลองและแสดงผลตรงตามที่วัดได้</p>
      <h3>ลม: พยากรณ์เทียบรายงานสนามบินจริง</h3>
      ${table(['ล่วงหน้า','GFS MAE (m/s)','ค่าฐาน MAE (m/s)','ทิศลมคลาดเฉลี่ย','จำนวนคู่'],Object.entries(report.wind_station.by_lead).map(([h,v])=>[
        `${esc(h)} ชั่วโมง`,metric(v.metrics.gfs),metric(v.metrics.persistence),`${fmt(v.direction_mae_degrees,1)}°`,fmt(v.metrics.gfs.n,0)
      ]))}
      <p class="evidence-note">VTCC METAR จากคลัง IEM ใช้รายงานตรงชั่วโมงและแปลง knots เป็น m/s ทิศลมเทียบเฉพาะทั้งสองฝั่ง ≥1 m/s เป็นหลักฐานสถานีสนามบินแห่งเดียว ยังไม่ใช่ลมใกล้เปลวไฟในป่าทุกแห่ง</p>
      <h3>ไฟ: ทราบจุดเริ่มทั้งกลุ่มแล้ว ครอบจุดภายหลังได้แค่ไหน</h3>
      ${table(['วิธี · เผื่อ 375 m เท่ากัน','จุดที่ครอบได้','เพิ่มจากค่าฐาน','พื้นที่ครอบรวม ณ เวลาตรวจ'],fire.summary.filter(s=>s.tolerance_m===375).map(s=>[
        esc(variants[s.variant]),`${fmt(s.covered,0)}/${fmt(s.points,0)} (${fmt(s.coverage_percent)}%)`,`${fmt(s.coverage_percent-s.baseline_coverage_percent)} จุดเปอร์เซ็นต์`,`${fmt(s.area_ha)} ha`
      ]))}
      <p class="evidence-note">8 หน้าต่างพื้นที่วันพีค เริ่มจากข้อมูลใน 5 นาทีแรกเท่านั้น แล้วเทียบ 305 จุดที่ตรวจภายหลัง เงื่อนไขกลางใช้ FM1/ความชื้น 8% และลม ERA5 ×0.2 ที่ใกล้เปลวไฟเป็นค่าทดลอง กรณี DSM อ่านทางลาด ณ จุดตรวจพบจริง คะแนนเพิ่มพร้อมพื้นที่ครอบที่ใหญ่ขึ้น ยังไม่ได้วัด false alarms หรือขอบไฟจริง</p>
      <label>เลือกกรณี<select id="validationFireCase">${fire.cases.map(c=>`<option value="${esc(c.id)}">${esc(c.id)} · รู้ ${c.initial.length} จุด / เทียบ ${c.later.length} จุด</option>`).join('')}</select></label>
      <label>วิธีเริ่มและทางลาด<select id="validationFireVariant">${Object.entries(variants).map(([k,v])=>`<option value="${k}" ${k==='all_initial_dem'?'selected':''}>${esc(v)}</option>`).join('')}</select></label>
      <div class="validation-legend"><span><i style="background:#ee785c"></i>ทราบก่อนเริ่ม</span><span><i style="background:#28b9bc"></i>ตรวจพบภายหลัง</span><span><i style="background:#dc9c4b"></i>พื้นที่ครอบ + ระยะจับคู่</span></div>
      <div id="validationFireMap" class="validation-map" role="region" aria-label="เทียบพื้นที่ครอบกับจุดความร้อนที่ทราบก่อนเริ่มและตรวจพบภายหลัง"></div><div id="validationFireReadout"></div>
      <details><summary>วิธีประเมิน ข้อมูลที่ขาด และข้อมูลสำหรับตรวจซ้ำ</summary>
      <p>สมมติฐานช่วงเฉลี่ยฝุ่น: ${pm.aggregation_sensitivity.map(s=>`สิ้นสุด ${s.window_end_hour_ict===24?'24':s.window_end_hour_ict}:00 น. → MAE ${fmt(s.mae)} (${s.n} คู่)`).join(' · ')} ใช้เป็น sensitivity ไม่เลือกค่าที่ให้คะแนนดีที่สุดมาแทนสมมติฐานหลัก</p>
      <p>ไฟ: ${fire.summary.filter(s=>s.variant==='all_initial_dem').map(s=>`ระยะจับคู่ ${s.tolerance_m} m → ครอบ ${fmt(s.coverage_percent)}%`).join(' · ')} ระยะเหล่านี้ไม่ใช่ confidence interval</p>
      <ul class="evidence-note">${[...pm.notes,...recent.notes,...fire.notes].map(s=>`<li>${esc(s)}</li>`).join('')}</ul>
      <p><a href="https://air4thai.net/daily_download/PM2.5/2026.xlsx" target="_blank" rel="noopener noreferrer">Air4Thai ข้อมูลรายวัน 2026</a> · <a href="https://mesonet.agron.iastate.edu/request/download.phtml" target="_blank" rel="noopener noreferrer">IEM METAR archive</a> · <a href="https://open-meteo.com/en/docs/previous-runs-api" target="_blank" rel="noopener noreferrer">Open-Meteo Previous Runs</a></p>
      <a href="/api/hindcast/2026/validation?include_rows=true" target="_blank" rel="noopener noreferrer">เปิดข้อมูลคู่เทียบ ผล และ provenance JSON</a></details>`;
    document.getElementById('validationPmStation').addEventListener('change',e=>pmChart(e.target.value));pmChart('35T');
    document.getElementById('validationFireCase').addEventListener('change',fireCase);
    document.getElementById('validationFireVariant').addEventListener('change',fireCase);fireCase();
  }
  async function load(){
    if(loading)return;if(report){map?.invalidateSize({pan:false});return;}
    loading=true;content.innerHTML='<p role="status">กำลังอ่านผลประเมินกับข้อมูลจริง…</p>';
    try{const response=await fetch('/api/hindcast/2026/validation',{cache:'no-store',signal:AbortSignal.timeout(30000)});const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'อ่านผลไม่สำเร็จ');
      if(data.schema!=='cme-dashboard-validation-v1')throw new Error('รูปแบบผลประเมินไม่ตรงรุ่น');report=data;render();}
    catch(error){report=null;content.innerHTML=`<p role="status">อ่านผลประเมินไม่ได้: ${esc(error.message)}</p><button type="button" id="validationRetry">ลองอีกครั้ง</button>`;
      document.getElementById('validationRetry').addEventListener('click',load);}
    finally{loading=false;}
  }
  host.addEventListener('toggle',()=>{if(host.open)load();});
})();
