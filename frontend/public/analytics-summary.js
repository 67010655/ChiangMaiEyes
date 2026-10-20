/* Analytics top (phase 5): three cards a resident can read in seconds —
 * hotspots by day, dust by day (PCD 24-h levels), districts with the most
 * points — plus a short weather outlook. Every number comes from
 * /api/history or /api/fire-predictions as received; gaps stay gaps. */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dayLabel=d=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const weekday=d=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',weekday:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const fmt1=n=>Number(n).toLocaleString('th-TH',{maximumFractionDigits:1});

  // Tiny bar chart. Missing values draw nothing (not zero); the last bar is today.
  function bars(values,{colors=[],label=''}={}){
    const finite=values.filter(Number.isFinite), max=Math.max(1,...finite), n=values.length||1, w=100/n;
    return `<svg class="as-bars" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="${esc(label)}">`+
      values.map((v,i)=>{
        if(!Number.isFinite(v))return `<rect x="${i*w+w*.2}" y="38" width="${w*.6}" height="2" fill="var(--line)"/>`;
        const h=Math.max(2,v/max*36);
        return `<rect x="${i*w+w*.15}" y="${40-h}" width="${w*.7}" height="${h}" rx="1" fill="${colors[i]||'var(--as-bar)'}"/>`;
      }).join('')+`</svg>`;
  }
  function axis(dates){
    if(!dates.length)return '';
    const pick=dates.length<=2?dates:[dates[0],dates[Math.floor((dates.length-1)/2)],dates[dates.length-1]];
    return `<div class="as-axis">${pick.map(d=>`<span>${esc(dayLabel(d))}</span>`).join('')}</div>`;
  }

  function hotspotCard(a,daysN){
    const days=a.hotspots||[];
    const known=days.filter(d=>Number.isFinite(d.count));
    const peak=known.reduce((m,d)=>!m||d.count>m.count?d:m,null);
    const incomplete=days.some(d=>!d.partial_day&&!d.source_requests_complete);
    const colors=days.map((d,i)=>i===days.length-1?'#ef4444':(d.source_requests_complete||d.partial_day?'#f59e0b':'#94a3b8'));
    const sentence=!a.total?'ไม่พบจุดความร้อนในช่วงนี้ (ไม่ได้แปลว่าไม่มีไฟ)':
      peak?`มากที่สุด ${esc(dayLabel(peak.date))} · ${esc(peak.count)} จุด`:'';
    return `<article class="as-card" aria-labelledby="asHotT">
      <h3 id="asHotT" class="as-k">จุดความร้อน ${esc(daysN)} วัน</h3>
      <p class="as-v"><b>${esc(a.total)}</b> จุด</p>
      ${bars(days.map(d=>d.count),{colors,label:'จุดความร้อนรายวัน'})}${axis(days.map(d=>d.date))}
      <p class="as-s">${sentence}</p>
      ${incomplete?'<p class="as-note">บางวันดาวเทียมส่งข้อมูลไม่ครบ (แท่งสีเทา)</p>':''}
      <button type="button" class="as-link" data-as-action="replay">▶ ดูบนแผนที่ตามเวลา</button>
    </article>`;
  }

  function pmCard(a,kind){
    const pms=(a.pm25||[]).filter(p=>p.measurement_kind===kind).sort((x,y)=>x.date<y.date?-1:1);
    const dates=(a.hotspots||[]).map(d=>d.date);
    const byDate=Object.fromEntries(pms.map(p=>[p.date,p]));
    const series=dates.length?dates.map(d=>byDate[d]?.value):pms.map(p=>p.value);
    const axisDates=dates.length?dates:pms.map(p=>p.date);
    const U=root.CmeUx;
    const colors=series.map(v=>Number.isFinite(v)&&U?`var(${U.category(v)?.token||'--state-old'})`:'');
    // PCD levels are defined on 24-hour averages: use the latest full day (enough samples), not today's partial.
    const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok'}).format(new Date());
    const fullDays=pms.filter(p=>p.date<today);
    const latest=fullDays[fullDays.length-1]||null;
    const peak=pms.reduce((m,p)=>!m||p.value>m.value?p:m,null);
    const chip=latest&&U?U.pmChipHtml(latest.value):'';
    return `<article class="as-card" aria-labelledby="asPmT">
      <h3 id="asPmT" class="as-k">ฝุ่น PM2.5 รายวัน · ${kind==='model'?'แบบจำลอง':'สถานีวัด'}</h3>
      ${latest?`<p class="as-v"><b>${esc(fmt1(latest.value))}</b> µg/m³ ${chip}</p><p class="as-sub">เฉลี่ย 24 ชม. วันที่ ${esc(dayLabel(latest.date))}</p>`:'<p class="as-v as-empty">ยังไม่มีค่าเฉลี่ยรายวัน</p>'}
      ${bars(series,{colors,label:'ฝุ่น PM2.5 รายวัน'})}${axis(axisDates)}
      <p class="as-s">${peak?`สูงสุด ${esc(fmt1(peak.value))} µg/m³ วันที่ ${esc(dayLabel(peak.date))}`:''}</p>
      <p class="as-note">สีตามเกณฑ์กรมควบคุมมลพิษ (ค่าเฉลี่ย 24 ชม.)</p>
    </article>`;
  }

  function districtCard(a){
    const rows=(a.districts||[]).filter(d=>d.count>0).slice(0,5), max=Math.max(1,...rows.map(r=>r.count));
    return `<article class="as-card" aria-labelledby="asDistT">
      <h3 id="asDistT" class="as-k">อำเภอที่มีจุดมากที่สุด</h3>
      ${rows.length?`<ol class="as-rank">${rows.map(r=>`<li><button type="button" data-as-district="${esc(r.name)}" aria-label="ดูอำเภอ${esc(r.name)} บนแผนที่ ${esc(r.count)} จุด">
        <span class="as-name">${esc(r.name)}</span><span class="as-track"><i style="width:${(r.count/max*100).toFixed(1)}%"></i></span><b>${esc(r.count)}</b></button></li>`).join('')}</ol>
      <p class="as-note">กดชื่ออำเภอเพื่อดูบนแผนที่</p>`:'<p class="as-s">ยังไม่มีจุดที่ระบุอำเภอในช่วงนี้</p>'}
    </article>`;
  }

  function forecastHtml(list){
    if(!list?.length)return '';
    return `<section class="as-forecast" aria-labelledby="asFcT"><h3 id="asFcT" class="as-k">อากาศ ${esc(list.length)} วันข้างหน้า · พยากรณ์</h3>
      <ul>${list.map(d=>`<li><b>${esc(weekday(d.date))} ${esc(dayLabel(d.date))}</b>
        <span>${Number.isFinite(d.temp_max_c)?esc(fmt1(d.temp_max_c))+'°':'—'}</span>
        <span>${Number.isFinite(d.rain_mm)?(d.rain_mm<0.5?'ไม่มีฝน':'ฝน '+esc(fmt1(d.rain_mm))+' มม.'):'ฝน —'}</span>
        <span>ลม ${Number.isFinite(d.wind_kmh)?esc(fmt1(d.wind_kmh)):'—'} กม./ชม.</span></li>`).join('')}</ul>
      <p class="as-note">Open-Meteo จุดอ้างอิงเมืองเชียงใหม่ · ไม่ใช่การคาดการณ์ไฟ</p></section>`;
  }

  function render(el,history,{pmKind='measured',forecast=null,error=''}={}){
    if(!el)return;
    if(error){el.innerHTML=`<p class="as-error" role="alert">${esc(error)}</p>`;return;}
    const a=history?.analytics;
    if(!a){el.innerHTML='<p class="as-loading" role="status">กำลังโหลดข้อมูลย้อนหลัง…</p>';return;}
    el.innerHTML=`<div class="as-grid">${hotspotCard(a,history.days)}${pmCard(a,pmKind)}${districtCard(a)}</div>${forecastHtml(forecast)}`;
  }
  function renderForecast(el,forecast){
    if(!el)return;const old=el.querySelector('.as-forecast');const html=forecastHtml(forecast);
    if(old)old.outerHTML=html;else if(html)el.insertAdjacentHTML('beforeend',html);
  }
  root.CmeAnalyticsSummary={render,renderForecast,bars};
})(window);
