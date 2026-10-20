/* Analytics for residents and community-forest reps (phase 5b).
 * A one-line summary, then cards: hotspots by day, dust by day on the PCD
 * scale, a district map, community forests with points inside, and the
 * weather outlook. Every number is from /api/history or /api/fire-predictions
 * as received: gaps stay gaps, and "no points" never means "no fire". */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tz={timeZone:'Asia/Bangkok'};
  const dayLabel=d=>new Intl.DateTimeFormat('th-TH',{...tz,day:'numeric',month:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const weekday=d=>new Intl.DateTimeFormat('th-TH',{...tz,weekday:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const fmt1=n=>Number(n).toLocaleString('th-TH',{maximumFractionDigits:1});
  const todayBkk=()=>new Intl.DateTimeFormat('sv-SE',tz).format(new Date());
  const reduced=()=>!!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const U=()=>root.CmeUx;
  const pmToken=v=>U()?.category(v)?.token||'--state-old';

  // ---------- small pieces ----------
  // Bars that grow in; each bar carries its own readout for tap/hover.
  function bars(items,{label='',color=()=> 'var(--as-bar)',unit=''}={}){
    const finite=items.map(i=>i.v).filter(Number.isFinite), max=Math.max(1,...finite), n=items.length||1, w=100/n, gap=n>40?0.08:0.18;
    return `<svg class="as-bars" viewBox="0 0 100 44" preserveAspectRatio="none" role="img" aria-label="${esc(label)}">`+
      items.map((it,i)=>{
        const read=`${it.label} · ${Number.isFinite(it.v)?fmt1(it.v)+(unit?' '+unit:''):'ไม่มีข้อมูล'}`;
        if(!Number.isFinite(it.v))return `<rect class="as-gap" x="${i*w+w*gap}" y="42" width="${w*(1-2*gap)}" height="2" data-read="${esc(read)}"><title>${esc(read)}</title></rect>`;
        const h=Math.max(2,it.v/max*40);
        return `<rect class="as-bar${it.hi?' hi':''}" style="--i:${(i*Math.min(1,30/n)).toFixed(1)}" x="${i*w+w*gap}" y="${44-h}" width="${w*(1-2*gap)}" height="${h}" rx="0.8" fill="${color(it,i)}" data-read="${esc(read)}"><title>${esc(read)}</title></rect>`;
      }).join('')+`</svg><p class="as-readout" aria-live="polite"></p>`;
  }
  function axis(labels){
    if(!labels.length)return '';
    const pick=labels.length<=2?labels:[labels[0],labels[Math.floor((labels.length-1)/2)],labels[labels.length-1]];
    return `<div class="as-axis">${pick.map(l=>`<span>${esc(l)}</span>`).join('')}</div>`;
  }
  const num=(v,d=0)=>`<b class="as-num" data-count-to="${Number(v)}" data-dec="${d}">${esc(d?fmt1(v):Number(v).toLocaleString('th-TH'))}</b>`;

  // ---------- data shaping ----------
  function pmSeries(a){
    let kind='measured', pms=(a.pm25||[]).filter(p=>p.measurement_kind==='measured');
    if(!pms.length){kind='model';pms=(a.pm25||[]).filter(p=>p.measurement_kind==='model');}
    pms=[...pms].sort((x,y)=>x.date<y.date?-1:1);
    // PCD levels are defined on 24-hour averages: use the latest full day, not today's partial.
    const full=pms.filter(p=>p.date<todayBkk());
    return {kind,pms,latest:full[full.length-1]||null,peak:pms.reduce((m,p)=>!m||p.value>m.value?p:m,null)};
  }
  function headline(h,a,pm){
    const top=(a.districts||[]).find(d=>d.count>0);
    const parts=[];
    if(!a.total)parts.push(`${h.days===1?'24 ชั่วโมง':h.days+' วัน'}ที่ผ่านมา ดาวเทียมไม่พบจุดความร้อนในเชียงใหม่`);
    else parts.push(`${h.days===1?'24 ชั่วโมง':h.days+' วัน'}ที่ผ่านมา พบจุดความร้อน <b>${esc(Number(a.total).toLocaleString('th-TH'))}</b> จุด${top?` มากที่สุดที่ <b>อ.${esc(top.name)}</b>`:''}`);
    if(pm.latest){const lv=root.CmePublicGuidance?.pmLevel(pm.latest.value);if(lv)parts.push(`ฝุ่นล่าสุดอยู่ระดับ <b style="color:var(${pmToken(pm.latest.value)})">${esc(lv.label)}</b>`);}
    return parts.join(' · ');
  }

  // ---------- cards ----------
  function hotspotCard(h,a,{mapDays}){
    const days=a.hotspots||[];
    let items, labels, title;
    if(h.days===1&&Array.isArray(a.hour_histogram)){
      title='จุดความร้อนตามชั่วโมง';
      items=a.hour_histogram.map((v,i)=>({v,label:`${String(i).padStart(2,'0')}:00 น.`}));
      labels=['00:00','12:00','23:00'];
    }else{
      title=`จุดความร้อนรายวัน`;
      const peakV=Math.max(0,...days.map(d=>d.count).filter(Number.isFinite));
      items=days.map(d=>({v:d.count,label:dayLabel(d.date),hi:Number.isFinite(d.count)&&d.count===peakV&&peakV>0,gap:!d.partial_day&&!d.source_requests_complete}));
      labels=days.map(d=>dayLabel(d.date));
    }
    const known=days.filter(d=>Number.isFinite(d.count));
    const peak=known.reduce((m,d)=>!m||d.count>m.count?d:m,null);
    const incomplete=days.some(d=>!d.partial_day&&!d.source_requests_complete);
    return `<article class="as-card as-hot" aria-labelledby="asHotT">
      <header class="as-head"><span class="as-ic hot" aria-hidden="true"><span class="hs-dot-pin age-new"></span></span><h3 id="asHotT" class="as-k">${title}</h3></header>
      <p class="as-v">${num(a.total)} <span>จุด</span></p>
      ${bars(items,{label:title,unit:'จุด',color:it=>it.hi?'#ef4444':it.gap?'#94a3b8':'#f59e0b'})}${axis(labels)}
      <p class="as-s">${!a.total?'ไม่พบจุด ไม่ได้แปลว่าไม่มีไฟ':peak?`วันที่พบมากที่สุด <b>${esc(dayLabel(peak.date))}</b> · ${esc(peak.count)} จุด`:''}</p>
      ${incomplete?'<p class="as-note">แท่งสีเทา = วันที่ดาวเทียมส่งข้อมูลไม่ครบ</p>':''}
      ${mapDays?`<button type="button" class="as-link" data-as-action="replay">▶ ย้อนดู ${esc(mapDays)} วันล่าสุดบนแผนที่</button>`:''}
    </article>`;
  }

  function gauge(v){
    // PCD 24-h bands 0-15-25-37.5-75-(cap 100 for drawing only).
    const stops=[15,25,37.5,75,100], tokens=['--pm-very-good','--pm-good','--pm-moderate','--pm-unhealthy','--pm-hazardous'];
    let prev=0;const seg=stops.map((s,i)=>{const w=(s-prev);prev=s;return `<i style="flex:${w};background:var(${tokens[i]})"></i>`;}).join('');
    const pos=Math.min(100,Math.max(0,v));
    return `<div class="as-gauge" aria-hidden="true"><div class="as-gauge-bar">${seg}</div><span class="as-gauge-pin" style="left:${pos}%"></span></div>
      <div class="as-gauge-scale" aria-hidden="true"><span>0</span><span style="left:15%">15</span><span style="left:25%">25</span><span style="left:37.5%">37.5</span><span style="left:75%">75</span></div>`;
  }
  function pmCard(h,a,pm){
    const dates=(a.hotspots||[]).map(d=>d.date);
    const byDate=Object.fromEntries(pm.pms.map(p=>[p.date,p.value]));
    const src=dates.length?dates:pm.pms.map(p=>p.date);
    const items=src.map(d=>({v:byDate[d],label:dayLabel(d)}));
    const lv=pm.latest?root.CmePublicGuidance?.pmLevel(pm.latest.value):null;
    return `<article class="as-card as-pm" aria-labelledby="asPmT">
      <header class="as-head"><span class="as-ic pm" aria-hidden="true">≋</span><h3 id="asPmT" class="as-k">ฝุ่น PM2.5 รายวัน${pm.kind==='model'?' · แบบจำลอง':''}</h3></header>
      ${pm.latest?`<p class="as-v">${num(pm.latest.value,1)} <span>µg/m³</span> ${U()?U().pmChipHtml(pm.latest.value):''}</p>
        <p class="as-sub">เฉลี่ย 24 ชม. วันที่ ${esc(dayLabel(pm.latest.date))}${lv?` · ${esc(lv.short)}`:''}</p>${gauge(pm.latest.value)}`
        :'<p class="as-v as-empty">ยังไม่มีค่าเฉลี่ยรายวัน</p>'}
      ${bars(items,{label:'ฝุ่น PM2.5 รายวัน',unit:'µg/m³',color:it=>`var(${pmToken(it.v)})`})}${axis(items.map(i=>i.label))}
      <p class="as-s">${pm.peak?`สูงสุด <b>${esc(fmt1(pm.peak.value))}</b> µg/m³ วันที่ ${esc(dayLabel(pm.peak.date))}`:''}</p>
      ${(()=>{const have=items.filter(i=>Number.isFinite(i.v)).length;return items.length>2&&have<items.length*.8?`<p class="as-note">มีค่าฝุ่น ${esc(have)} จาก ${esc(items.length)} วันในช่วงนี้ ค่าสูงสุดนับเฉพาะวันที่มีค่า</p>`:'';})()}
      <p class="as-note">${pm.kind==='model'?'ช่วงนี้ไม่มีค่าสถานีวัด ใช้แบบจำลอง CAMS แทน · ':''}สีตามเกณฑ์กรมควบคุมมลพิษ</p>
    </article>`;
  }

  // District choropleth from the map's own district outlines.
  function miniMap(shapes,counts){
    if(!shapes?.length)return '';
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    const k=Math.cos(18.8*Math.PI/180);
    const P=([lon,lat])=>[lon*k,-lat];
    shapes.forEach(s=>s.rings.forEach(r=>r.forEach(pt=>{const [x,y]=P(pt);minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);})));
    const W=200,H=Math.round(W*(maxY-minY)/(maxX-minX)), sx=W/(maxX-minX);
    const max=Math.max(1,...Object.values(counts));
    // Log scale: one very busy district should not wash every other one to "few".
    const rel=c=>Math.log(c+1)/Math.log(max+1);
    const fill=c=>!c?'var(--as-map-empty)':rel(c)>.8?'#ef4444':rel(c)>.55?'#f97316':'#fbbf24';
    const paths=shapes.map(s=>{
      const d=s.rings.map(r=>'M'+r.map(pt=>{const [x,y]=P(pt);return `${((x-minX)*sx).toFixed(1)},${((y-minY)*sx).toFixed(1)}`;}).join('L')+'Z').join('');
      const c=counts[s.name]||0;
      return `<path d="${d}" fill="${fill(c)}" data-as-district="${esc(s.name)}" tabindex="-1"><title>อ.${esc(s.name)} · ${c} จุด</title></path>`;
    }).join('');
    return `<svg class="as-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="แผนที่อำเภอ สีตามจำนวนจุดความร้อน">${paths}</svg>
      <div class="as-map-key" aria-hidden="true"><i style="background:var(--as-map-empty)"></i>ไม่พบ<i style="background:#fbbf24"></i>น้อย<i style="background:#f97316"></i><i style="background:#ef4444"></i>มาก</div>`;
  }
  function districtCard(a,{shapes,norm}){
    const rows=(a.districts||[]).filter(d=>d.count>0);
    const counts={};rows.forEach(r=>{counts[norm(r.name)]=(counts[norm(r.name)]||0)+r.count;});
    const top=rows.slice(0,5), max=Math.max(1,...top.map(r=>r.count));
    return `<article class="as-card as-dist" aria-labelledby="asDistT">
      <header class="as-head"><span class="as-ic dist" aria-hidden="true">⌖</span><h3 id="asDistT" class="as-k">อำเภอที่มีจุดความร้อน</h3></header>
      <div class="as-dist-body">${miniMap(shapes,counts)}
      ${top.length?`<ol class="as-rank">${top.map((r,i)=>`<li><button type="button" data-as-district="${esc(norm(r.name))}" aria-label="ดูอำเภอ${esc(r.name)} บนแผนที่ ${esc(r.count)} จุด">
        <span class="as-rank-n">${i+1}</span><span class="as-name">${esc(r.name)}</span><span class="as-track"><i style="--w:${(r.count/max*100).toFixed(1)}%"></i></span><b>${esc(r.count)}</b></button></li>`).join('')}</ol>`
        :'<p class="as-s">ไม่พบจุดที่ระบุอำเภอในช่วงนี้</p>'}</div>
      <p class="as-note">กดอำเภอเพื่อดูบนแผนที่ · ชื่ออำเภอในคลังบางจุดประมาณจากตำแหน่ง</p>
    </article>`;
  }
  function forestCard(a,{forestInfo}){
    const rows=(a.forests||[]).filter(f=>f.count>0).map(f=>({...f,info:forestInfo?.(f.forest_id)})).sort((x,y)=>y.count-x.count);
    const top=rows.slice(0,5);
    return `<article class="as-card as-forest" aria-labelledby="asForT">
      <header class="as-head"><span class="as-ic forest" aria-hidden="true">🌳</span><h3 id="asForT" class="as-k">ป่าชุมชนที่มีจุดความร้อนในเขต</h3></header>
      ${top.length?`<p class="as-v">${num(rows.length)} <span>ป่า</span></p><ul class="as-forests">${top.map(f=>`<li><button type="button" data-as-forest="${esc(f.forest_id)}">
          <span><b>${esc(f.info?.name||'ป่าชุมชน '+f.forest_id)}</b><small>${f.info?.amphoe?'อ.'+esc(f.info.amphoe):''}</small></span><em>${esc(f.count)} จุด</em></button></li>`).join('')}</ul>
        ${rows.length>top.length?`<p class="as-note">และอีก ${esc(rows.length-top.length)} ป่า</p>`:''}`
        :'<p class="as-s as-good">ไม่พบจุดความร้อนในขอบเขตป่าชุมชนช่วงนี้</p><p class="as-note">ไม่ได้แปลว่าไม่มีไฟ ดาวเทียมอาจมองไม่เห็นไฟเล็กหรือใต้เรือนยอด</p>'}
      <p class="as-note">นับเฉพาะจุดที่อยู่ในขอบเขตป่า RECOFTC · ยังไม่ใช่เหตุไฟที่ยืนยันแล้ว</p>
    </article>`;
  }
  function wxIcon(d){
    if(Number.isFinite(d.rain_mm)&&d.rain_mm>=5)return '🌧️';
    if(Number.isFinite(d.rain_mm)&&d.rain_mm>=0.5)return '🌦️';
    if(Number.isFinite(d.humidity_pct)&&d.humidity_pct>=75)return '⛅';
    return '☀️';
  }
  function forecastHtml(list){
    if(!list?.length)return '';
    return `<section class="as-card as-forecast" aria-labelledby="asFcT">
      <header class="as-head"><span class="as-ic wx" aria-hidden="true">☁</span><h3 id="asFcT" class="as-k">อากาศ ${esc(list.length)} วันข้างหน้า</h3></header>
      <ul>${list.map(d=>`<li><span class="as-wx" aria-hidden="true">${wxIcon(d)}</span><b>${esc(weekday(d.date))} ${esc(dayLabel(d.date))}</b>
        <span class="as-temp">${Number.isFinite(d.temp_max_c)?esc(Math.round(d.temp_max_c))+'°':'—'}<small>${Number.isFinite(d.temp_min_c)?' / '+esc(Math.round(d.temp_min_c))+'°':''}</small></span>
        <span>${Number.isFinite(d.rain_mm)?(d.rain_mm<0.5?'ไม่มีฝน':'ฝน '+esc(fmt1(d.rain_mm))+' มม.'):'ฝน —'}</span>
        <span>ลม ${Number.isFinite(d.wind_kmh)?esc(fmt1(d.wind_kmh)):'—'} กม./ชม.${Number.isFinite(d.humidity_pct)?` · ชื้น ${esc(Math.round(d.humidity_pct))}%`:''}</span></li>`).join('')}</ul>
      <p class="as-note">พยากรณ์ Open-Meteo จุดอ้างอิงเมืองเชียงใหม่ · ไม่ใช่การคาดการณ์ไฟ</p></section>`;
  }

  // ---------- motion ----------
  function countUp(el){
    if(reduced()||!root.requestAnimationFrame)return;
    el.querySelectorAll('[data-count-to]').forEach(b=>{
      const to=Number(b.dataset.countTo), dec=Number(b.dataset.dec)||0, final=b.textContent;
      if(!Number.isFinite(to)||to===0)return;
      const t0=performance.now(), dur=700;
      const step=now=>{const p=Math.min(1,(now-t0)/dur), e=1-Math.pow(1-p,3), v=to*e;
        b.textContent=p<1?(dec?fmt1(v):Math.round(v).toLocaleString('th-TH')):final;
        if(p<1)requestAnimationFrame(step);};
      requestAnimationFrame(step);
    });
  }
  function wire(el){
    if(el.dataset.asWired)return;el.dataset.asWired='1';
    // Tap or hover a bar to read it (title tooltips do not show on phones).
    const show=e=>{const r=e.target.closest?.('[data-read]');if(!r)return;const card=r.closest('.as-card');const out=card?.querySelector('.as-readout');if(out)out.textContent=r.dataset.read;
      card.querySelectorAll('.as-bars .on').forEach(x=>x.classList.remove('on'));r.classList.add('on');};
    el.addEventListener('click',show);el.addEventListener('mouseover',show);
  }

  function render(el,history,opts={}){
    if(!el)return;
    const {error='',forecast=null}=opts;
    if(error){el.innerHTML=`<p class="as-error" role="alert">${esc(error)}</p>`;return;}
    const a=history?.analytics;
    if(!a){el.innerHTML='<div class="as-skeleton" role="status" aria-label="กำลังโหลดข้อมูลย้อนหลัง"><i></i><i></i><i></i></div>';return;}
    const pm=pmSeries(a), norm=opts.norm||(s=>String(s||'').replace(/^อำเภอ|^อ\./,'').trim());
    el.innerHTML=`<p class="as-hero">${headline(history,a,pm)}</p>
      <div class="as-grid">${hotspotCard(history,a,opts)}${pmCard(history,a,pm)}${districtCard(a,{shapes:opts.shapes,norm})}${forestCard(a,opts)}</div>
      ${forecastHtml(forecast)}`;
    wire(el);countUp(el);
  }
  function renderForecast(el,forecast){
    if(!el||!el.querySelector('.as-grid'))return;const old=el.querySelector('.as-forecast');const html=forecastHtml(forecast);
    if(old)old.outerHTML=html;else if(html)el.insertAdjacentHTML('beforeend',html);
  }
  root.CmeAnalyticsSummary={render,renderForecast,bars,pmSeries,headline};
})(window);
