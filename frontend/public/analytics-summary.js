/* Analytics for residents and community-forest reps (phase 5b).
 * A one-line summary, then cards: hotspots by day, dust by day on the PCD
 * scale, a district map, community forests with points inside, and the
 * weather outlook. Every number is from /api/history or /api/fire-predictions
 * as received: gaps stay gaps, and "no points" never means "no fire". */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tz={timeZone:'Asia/Bangkok'};
  // Long ranges cross a year end, so their dates carry a short Buddhist-era year ("24 ต.ค. 68").
  let withYear=false;
  const dayLabel=d=>new Intl.DateTimeFormat('th-TH',{...tz,day:'numeric',month:'short',...(withYear?{year:'2-digit'}:{})}).format(Date.parse(d+'T12:00:00+07:00'));
  const weekday=d=>new Intl.DateTimeFormat('th-TH',{...tz,weekday:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const fmt1=n=>Number(n).toLocaleString('th-TH',{maximumFractionDigits:1});
  const todayBkk=()=>new Intl.DateTimeFormat('sv-SE',tz).format(new Date());
  const hourBkk=()=>Number(new Intl.DateTimeFormat('en-GB',{...tz,hour:'2-digit',hourCycle:'h23'}).format(new Date()));
  const dayBefore=d=>new Date(Date.parse(d+'T12:00:00+07:00')-864e5).toISOString().slice(0,10);
  // Readout name for one day: today is still filling up, so say so.
  const dayRead=d=>d===todayBkk()?`วันนี้ ${dayLabel(d)} (ถึงตอนนี้)`:`${weekday(d)} ${dayLabel(d)}`;
  const reduced=()=>!!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const U=()=>root.CmeUx;
  // Chiang Mai open-burning control period, from the province announcement
  // "กำหนดเขตการบริหารจัดการเชื้อเพลิงและเขตควบคุมการเผา ประจำปีงบประมาณ 2569".
  // Add the next year only when the province publishes it.
  const BURN_BANS=[{start:'2026-01-01',end:'2026-05-31',label:'ช่วงควบคุมการเผา 1 ม.ค.–31 พ.ค. 2569',
    sources:[{name:'เทศบาลตำบลป่าเมี่ยง (อ้างประกาศจังหวัด)',url:'https://www.pamiang.go.th/catalog/activity/1304'},
             {name:'เชียงใหม่นิวส์',url:'https://www.chiangmainews.co.th/news/chiangmai/3855620/'}]}];
  const inBan=d=>BURN_BANS.find(b=>d>=b.start&&d<=b.end)||null;
  function banNote(dates){
    const hit=BURN_BANS.filter(b=>dates.some(d=>d>=b.start&&d<=b.end));
    if(!hit.length)return '';
    return `<p class="as-note as-ban-note"><i aria-hidden="true"></i>แถบสีส้มจาง = ${hit.map(b=>esc(b.label)).join(', ')} จังหวัดเชียงใหม่ · มีการอนุญาตเผาบางพื้นที่ผ่านระบบ Fire-D/Burn Check จุดในช่วงนี้จึงไม่ได้แปลว่าฝ่าฝืนทุกจุด · ที่มา ${hit[0].sources.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>`).join(', ')}</p>`;
  }
  function banStatus(){
    const today=todayBkk(), now=inBan(today);
    if(now)return `<p class="as-ban-status on">ตอนนี้อยู่ใน${esc(now.label)}</p>`;
    const next=BURN_BANS.find(b=>b.start>today);
    return `<p class="as-ban-status">ตอนนี้ไม่อยู่ในช่วงควบคุมการเผา · ${next?esc(next.label):'ช่วงปี 2570 รอประกาศจังหวัด'}</p>`;
  }
  const pmToken=v=>U()?.category(v)?.token||'--state-old';

  let focusArea=null; // the forest the page is narrowed to, if any
  let focusDistrict=null; // or the district
  // ---------- small pieces ----------
  // Bars that grow in; each bar carries its own readout for tap/hover.
  function bars(items,{label='',color=()=> 'var(--as-bar)',unit=''}={}){
    const finite=items.map(i=>i.v).filter(Number.isFinite), max=Math.max(1,...finite), n=items.length||1, w=100/n, gap=n>40?0.08:0.18;
    const bands=items.map((it,i)=>it.ban?`<rect class="as-band" x="${i*w}" y="0" width="${w+0.02}" height="44"/>`:'').join('');
    return `<svg class="as-bars" viewBox="0 0 100 44" preserveAspectRatio="none" role="img" aria-label="${esc(label)}">`+bands+
      items.map((it,i)=>{
        const read=`${it.label} · ${Number.isFinite(it.v)?fmt1(it.v)+(unit?' '+unit:''):'ไม่มีข้อมูล'}`;
        if(!Number.isFinite(it.v))return `<rect class="as-gap" x="${i*w+w*gap}" y="42" width="${w*(1-2*gap)}" height="2" data-read="${esc(read)}"><title>${esc(read)}</title></rect>`;
        const h=Math.max(2,it.v/max*40);
        return `<rect class="as-bar${it.hi?' hi':''}${it.model?' model':''}" style="--i:${(i*Math.min(1,30/n)).toFixed(1)}" x="${i*w+w*gap}" y="${44-h}" width="${w*(1-2*gap)}" height="${h}" rx="0.8" fill="${color(it,i)}" data-read="${esc(read)}"><title>${esc(read)}</title></rect>`;
      }).join('')+`</svg><p class="as-readout" aria-live="polite">แตะแท่งกราฟเพื่อดูวันและค่า</p>`;
  }
  function axis(labels,dates){
    if(!labels.length)return '';
    if(labels.length===3&&!dates)return `<div class="as-axis">${labels.map(l=>`<span>${esc(l)}</span>`).join('')}</div>`;
    if(dates&&dates[dates.length-1]===todayBkk())labels=[...labels.slice(0,-1),'วันนี้'];
    const n=labels.length>120?5:3;
    const pick=labels.length<=2?labels:Array.from({length:n},(_,k)=>labels[Math.round(k*(labels.length-1)/(n-1))]);
    return `<div class="as-axis">${pick.map(l=>`<span>${esc(l)}</span>`).join('')}</div>`;
  }
  const num=(v,d=0)=>`<b class="as-num" data-count-to="${Number(v)}" data-dec="${d}">${esc(d?fmt1(v):Number(v).toLocaleString('th-TH'))}</b>`;

  // ---------- data shaping ----------
  // One value per day: the station mean when there is one, otherwise the CAMS
  // model value for that day (kept apart and drawn faded). The range average
  // and the count of days per PCD level follow the chosen range.
  function pmSeries(a,dates=[]){
    const of=k=>Object.fromEntries((a.pm25||[]).filter(p=>p.measurement_kind===k).map(p=>[p.date,p.value]));
    const st=of('measured'), md=of('model');
    const days=(dates.length?dates:[...new Set((a.pm25||[]).map(p=>p.date))].sort());
    const series=days.map(d=>Number.isFinite(st[d])?{date:d,v:st[d],kind:'measured'}:Number.isFinite(md[d])?{date:d,v:md[d],kind:'model'}:{date:d,v:null,kind:null});
    const have=series.filter(x=>Number.isFinite(x.v));
    const full=have.filter(x=>x.date<todayBkk());
    const avg=full.length?full.reduce((t,x)=>t+x.v,0)/full.length:null;
    const levels=(root.CmePublicGuidance?.PM_LEVELS||[]).map((l,i)=>({label:l.label,token:['--pm-very-good','--pm-good','--pm-moderate','--pm-unhealthy','--pm-hazardous'][i],n:0}));
    full.forEach(x=>{const lv=root.CmePublicGuidance?.pmLevel(x.v);const L=levels.find(l=>l.label===lv?.label);if(L)L.n++;});
    const stationDays=full.filter(x=>x.kind==='measured').length;
    return {series,avg,fullDays:full.length,levels,stationDays,modelDays:full.length-stationDays,
      latest:[...full].reverse().find(x=>x.kind==='measured')||full[full.length-1]||null,
      peak:full.reduce((m,x)=>!m||x.v>m.v?x:m,null),
      // kept for callers and tests that read the station rows
      kind:stationDays?'measured':'model',pms:(a.pm25||[]).filter(p=>p.measurement_kind===(Object.keys(st).length?'measured':'model'))};
  }
  function headlineParts(h,a,pm){
    const top=focusArea||focusDistrict?null:(a.districts||[]).find(d=>d.count>0);
    const where=focusArea?'ในขอบเขตป่านี้':focusDistrict?'ในอ.'+focusDistrict:'ในเชียงใหม่';
    const fire=!a.total?`${h.days===1?'24 ชั่วโมง':h.days+' วัน'}ที่ผ่านมา ดาวเทียมไม่พบจุดความร้อน${where}`
      :`${h.days===1?'24 ชั่วโมง':h.days+' วัน'}ที่ผ่านมา พบจุดความร้อน${focusArea?'ในขอบเขตป่า':focusDistrict?'ใน อ.'+esc(focusDistrict):''} <b>${esc(Number(a.total).toLocaleString('th-TH'))}</b> จุด${top?` มากที่สุดที่ <b>อ.${esc(top.name)}</b>`:''}`;
    const lv=pm.avg!==null?root.CmePublicGuidance?.pmLevel(pm.avg):null;
    const dust=lv?`ฝุ่นเฉลี่ยช่วงนี้ระดับ <b class="as-lv" style="--lv:var(${pmToken(pm.avg)})">${esc(lv.label)}</b> <span class="as-hl-num">${esc(fmt1(pm.avg))} µg/m³</span>`:'';
    return {fire,dust};
  }
  function headline(h,a,pm){const p=headlineParts(h,a,pm);return [p.fire,p.dust].filter(Boolean).join(' · ');}
  const monthLabel=ym=>new Intl.DateTimeFormat('th-TH',{...tz,month:'short',year:'numeric'}).format(Date.parse(ym+'-15T12:00:00+07:00'));
  // The month with the most hotspots, for ranges of a month or more.
  function busiestMonth(h,a){
    if(h.days<30||!a.total)return null;
    const m={};(a.hotspots||[]).forEach(d=>{if(Number.isFinite(d.count)&&d.count>0)m[d.date.slice(0,7)]=(m[d.date.slice(0,7)]||0)+d.count;});
    const best=Object.entries(m).sort((x,y)=>y[1]-x[1])[0];
    return best?{ym:best[0],n:best[1]}:null;
  }
  // Fire and dust as two separate readings. A long average folds the rainy
  // months in with the burning ones, so the dust line also gives the worst
  // day and how many days reached the health-effect levels.
  // The archive started on a known day. On long ranges say so, so empty early months are not read as "no fire".
  function archiveStartNote(h,a){
    const days=a.hotspots||[];if(h.days<90||!days.length)return '';
    const first=days.find(d=>Number(d.count)>0||d.source_requests_complete);
    if(!first||first===days[0])return '';
    const gap=(Date.parse(first.date)-Date.parse(days[0].date))/864e5;if(!(gap>7))return '';
    const day=new Intl.DateTimeFormat('th-TH',{day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Bangkok'}).format(new Date(first.date+'T12:00:00+07:00'));
    return `<p class="as-archive-start" role="note">📦 คลังข้อมูลเริ่มเก็บตั้งแต่ <b>${esc(day)}</b> ช่วงก่อนหน้านั้นยังไม่มีข้อมูล (แท่งสีเทา) ไม่ได้แปลว่าไม่มีไฟ</p>`;
  }
  function heroHtml(h,a,pm){
    const p=headlineParts(h,a,pm), month=busiestMonth(h,a), span=h.days===1?'24 ชม.':h.days+' วัน';
    const badDays=pm.levels.slice(3).reduce((t,l)=>t+l.n,0);
    const source=pm.stationDays>=pm.modelDays?'สถานีกรมควบคุมมลพิษ':'แบบจำลอง CAMS';
    // Only explain when the two lines seem to disagree: many hotspots, a clean
    // average, yet some days in the health-effect range. Point at the dustiest
    // day and count the hotspots received in the same week (±3 days).
    const peakLv=pm.peak?root.CmePublicGuidance?.pmLevel(pm.peak.v):null;
    const near=pm.peak?(a.hotspots||[]).filter(d=>Number.isFinite(d.count)&&Math.abs(Date.parse(d.date)-Date.parse(pm.peak.date))<=3*864e5).reduce((t,d)=>t+d.count,0):0;
    const why=h.days>=30&&a.total>=50&&pm.avg!==null&&pm.avg<=25&&pm.peak&&pm.peak.v>37.5
      ?`<p class="as-why"><b>ทำไมไฟเยอะ แต่ฝุ่นเฉลี่ยดี?</b> ค่าเฉลี่ย ${esc(span)} รวมวันที่อากาศดีจำนวนมาก วันที่ฝุ่นสูงสุด ${esc(dayLabel(pm.peak.date))} วัดได้ <b class="as-lv" style="--lv:var(${pmToken(pm.peak.v)})">${esc(fmt1(pm.peak.v))} µg/m³ (${esc(peakLv?.label||'')})</b> สัปดาห์นั้นพบจุดความร้อน <b>${esc(near.toLocaleString('th-TH'))}</b> จุด · จุดความร้อนนับทั้งพื้นที่ ส่วนฝุ่นมาจาก${esc(source)} สองค่านี้วัดคนละที่</p>`
      :'';
    return `<div class="as-hero as-hero2">
      <div class="as-hl fire"><span class="as-hl-ic" aria-hidden="true"><span class="hs-dot-pin age-new"></span></span><div>
        <h3 class="as-hl-k">จุดความร้อน · ดาวเทียม</h3>
        <p class="as-hl-v">${focusArea?`<b>${esc(focusArea.name||'ป่าชุมชน')}</b> · `:focusDistrict?`<b>อ.${esc(focusDistrict)}</b> · `:''}${p.fire}</p>
        ${month?`<p class="as-hl-s">พบมากที่สุดช่วง <b>${esc(monthLabel(month.ym))}</b> ${esc(month.n.toLocaleString('th-TH'))} จุด</p>`:''}</div></div>
      <div class="as-hl pm"><span class="as-hl-ic" aria-hidden="true">≋</span><div>
        <h3 class="as-hl-k">ฝุ่น PM2.5 · ${esc(source)}${focusArea||focusDistrict?' · ภาพรวมจังหวัด':''}</h3>
        <p class="as-hl-v">${p.dust||'ยังไม่มีค่าเฉลี่ยฝุ่นรายวันในช่วงนี้'}</p>
        ${pm.peak?`<p class="as-hl-s">วันที่สูงสุด <b>${esc(dayLabel(pm.peak.date))}</b> ${esc(fmt1(pm.peak.v))} µg/m³${pm.fullDays>1?` · ระดับเริ่มมีผลต่อสุขภาพขึ้นไป <b>${esc(badDays)}</b> จาก ${esc(pm.fullDays)} วัน`:''}</p>`:''}</div></div>
      ${why}</div>`;
  }

  // ---------- cards ----------
  function hotspotCard(h,a,{mapDays,liveCount}){
    // New detections reach the home tile first; say so instead of leaving two numbers that disagree.
    const behind=h.days===1&&!focusArea&&!focusDistrict&&Number.isFinite(liveCount)&&liveCount>(a.total||0)
      ?`<p class="as-note as-lag" role="note">หน้าแรกนับได้ <b>${esc(liveCount)}</b> จุด เพราะอ่านข้อมูลสดล่าสุด ส่วนกราฟนี้มาจากคลังที่บันทึกทุก 10 นาที อีก ${esc(liveCount-(a.total||0))} จุดใหม่จะขึ้นในรอบบันทึกถัดไป</p>`:'';
    const days=a.hotspots||[];
    let items, labels, title;
    if(h.days===1&&Array.isArray(a.hour_histogram)){
      title='จุดความร้อนตามชั่วโมง · 24 ชม. ล่าสุด';
      // The archive bins the last 24 h by Bangkok hour of day, so an hour after
      // the current one belongs to yesterday.
      const today=todayBkk(), now=hourBkk(), yday=dayBefore(today);
      const order=Array.from({length:24},(_,k)=>(now+1+k)%24);
      const hh=n=>String(n).padStart(2,'0');
      items=order.map(hr=>{const d=hr>now?yday:today;return {v:a.hour_histogram[hr],label:`${dayLabel(d)} ${hh(hr)}:00–${hh(hr)}:59 น.`};});
      const tag=hr=>`${dayLabel(hr>now?yday:today)} ${hh(hr)}:00`;
      labels=[tag(order[0]),tag(order[12]),'ตอนนี้'];
    }else{
      title=`จุดความร้อนรายวัน`;
      const peakV=Math.max(0,...days.map(d=>d.count).filter(Number.isFinite));
      items=days.map(d=>({v:d.count,label:dayRead(d.date),hi:Number.isFinite(d.count)&&d.count===peakV&&peakV>0,gap:!d.partial_day&&!d.source_requests_complete,ban:!!inBan(d.date)}));
      labels=days.map(d=>dayLabel(d.date));
    }
    const known=days.filter(d=>Number.isFinite(d.count));
    const peak=known.reduce((m,d)=>!m||d.count>m.count?d:m,null);
    const incomplete=days.some(d=>!d.partial_day&&!d.source_requests_complete);
    return `<article class="as-card as-hot" aria-labelledby="asHotT">
      <header class="as-head"><span class="as-ic hot" aria-hidden="true"><span class="hs-dot-pin age-new"></span></span><h3 id="asHotT" class="as-k">${title}</h3></header>
      <p class="as-v">${num(a.total)} <span>จุด</span></p>
      ${bars(items,{label:title,unit:'จุด',color:it=>it.hi?'#ef4444':it.gap?'#94a3b8':'#f59e0b'})}${axis(labels,h.days===1?null:days.map(d=>d.date))}
      <p class="as-s">${!a.total?'ไม่พบจุด ไม่ได้แปลว่าไม่มีไฟ':peak?`วันที่พบมากที่สุด <b>${esc(dayLabel(peak.date))}</b> · ${esc(peak.count)} จุด`:''}</p>
      <p class="as-compare" data-compare="hot" aria-live="polite"></p>${behind}
      ${incomplete?'<p class="as-note">แท่งสีเทา = วันที่ดาวเทียมส่งข้อมูลไม่ครบ</p>':''}${h.days===1?'':banNote(days.map(d=>d.date))}
      ${mapDays?`<button type="button" class="as-link" data-as-action="replay">▶ ย้อนดู ${esc(mapDays)} วันล่าสุดบนแผนที่</button>`:''}
    </article>`;
  }

  function levelStrip(pm){
    const total=pm.levels.reduce((t,l)=>t+l.n,0);if(!total)return '';
    return `<div class="as-levels" role="img" aria-label="${esc(pm.levels.filter(l=>l.n).map(l=>l.label+' '+l.n+' วัน').join(' · '))}">
      <div class="as-levels-bar">${pm.levels.filter(l=>l.n).map(l=>`<i style="flex:${l.n};background:var(${l.token})"></i>`).join('')}</div>
      <ul>${pm.levels.filter(l=>l.n).map(l=>`<li><i style="background:var(${l.token})"></i>${esc(l.label)} <b>${esc(l.n)}</b> วัน</li>`).join('')}</ul></div>`;
  }
  function pmCard(h,a,pm){
    const items=pm.series.map(x=>({v:x.v,label:dayRead(x.date)+(x.kind==='model'?' · แบบจำลอง CAMS':x.kind==='measured'?' · เฉลี่ยสถานี':''),model:x.kind==='model',ban:!!inBan(x.date)}));
    const span=h.days===1?'24 ชม.':h.days+' วัน';
    return `<article class="as-card as-pm" aria-labelledby="asPmT">
      <header class="as-head"><span class="as-ic pm" aria-hidden="true">≋</span><h3 id="asPmT" class="as-k">ฝุ่น PM2.5 ย้อนหลัง ${esc(span)}${focusArea||focusDistrict?'<small class="as-scope">ภาพรวมจังหวัด</small>':''}</h3></header>
      ${pm.avg!==null?`<p class="as-v">${num(pm.avg,1)} <span>µg/m³</span> ${U()?U().pmChipHtml(pm.avg):''}</p>
        <p class="as-sub">เฉลี่ยรายวัน ${esc(pm.fullDays)} วันเต็มในช่วงนี้${pm.modelDays>pm.stationDays?' (ส่วนใหญ่จากแบบจำลอง)':''}${pm.latest?` · ล่าสุด ${esc(fmt1(pm.latest.v))} (${esc(dayLabel(pm.latest.date))})`:''}</p>${levelStrip(pm)}`
        :'<p class="as-v as-empty">ยังไม่มีค่าเฉลี่ยรายวันในช่วงนี้</p>'}
      ${bars(items,{label:'ฝุ่น PM2.5 รายวัน',unit:'µg/m³',color:it=>`var(${pmToken(it.v)})`})}${axis(pm.series.map(x=>dayLabel(x.date)),pm.series.map(x=>x.date))}
      <p class="as-s">${pm.peak?`วันที่ฝุ่นสูงสุด <b>${esc(dayLabel(pm.peak.date))}</b> · ${esc(fmt1(pm.peak.v))} µg/m³`:''}</p>
      <p class="as-compare" data-compare="pm" aria-live="polite"></p>
      <p class="as-note">${pm.modelDays?`แท่งจาง = แบบจำลอง CAMS (${esc(pm.modelDays)} วันที่ไม่มีค่าสถานี) · `:''}สีตามเกณฑ์ค่าเฉลี่ย 24 ชม. กรมควบคุมมลพิษ</p>
    </article>`;
  }

  // ---------- wind over the chosen range ----------
  // Hourly 10 m wind at the city reference point from Open-Meteo (the same
  // provider as the map's streamlines); ERA5 archive beyond 92 days.
  const REF={lat:18.79,lon:98.98}, windCache=new Map();
  const DIR8=['เหนือ','ตะวันออกเฉียงเหนือ','ตะวันออก','ตะวันออกเฉียงใต้','ใต้','ตะวันตกเฉียงใต้','ตะวันตก','ตะวันตกเฉียงเหนือ'];
  function loadWind(days,fetcher=root.fetch?.bind(root)){
    const key=String(days);if(windCache.has(key))return windCache.get(key);
    if(typeof fetcher!=='function')return Promise.reject(new Error('no fetch'));
    const q=`latitude=${REF.lat}&longitude=${REF.lon}&hourly=wind_speed_10m,wind_direction_10m&timezone=Asia%2FBangkok`;
    let url,source;
    if(days<=92){url=`https://api.open-meteo.com/v1/forecast?${q}&past_days=${Math.max(1,days)}&forecast_days=0`;source='Open-Meteo';}
    else{const end=new Date(Date.now()-6*864e5),start=new Date(end-days*864e5),d=x=>x.toISOString().slice(0,10);
      url=`https://archive-api.open-meteo.com/v1/archive?${q}&start_date=${d(start)}&end_date=${d(end)}`;source='Open-Meteo ERA5';}
    const pr=fetcher(url).then(r=>{if(!r.ok)throw Error('wind '+r.status);return r.json();}).then(j=>{
      const sp=j.hourly?.wind_speed_10m||[],dr=j.hourly?.wind_direction_10m||[],t=j.hourly?.time||[];
      const hours=sp.map((v,i)=>({spd:v,dir:dr[i],t:t[i]})).filter(x=>Number.isFinite(x.spd)&&Number.isFinite(x.dir));
      return {hours,source,first:hours[0]?.t,last:hours[hours.length-1]?.t};
    });
    pr.catch(()=>windCache.delete(key));windCache.set(key,pr);return pr;
  }
  function windStats(w){
    const n=w.hours.length;if(!n)return null;
    const bins=new Array(8).fill(0);let sum=0,calm=0;
    w.hours.forEach(x=>{sum+=x.spd;if(x.spd<5){calm++;return;}bins[Math.round(((x.dir+180)%360)/45)%8]++;}); // "blows toward"
    const moving=n-calm, top=bins.indexOf(Math.max(...bins));
    return {n,avg:sum/n,calmPct:calm/n*100,bins,moving,top,topPct:moving?bins[top]/moving*100:0};
  }
  function rose(st){
    const max=Math.max(1,...st.bins);
    const petals=st.bins.map((c,i)=>{const r=10+c/max*36,a=(i*45-90)*Math.PI/180,w=0.33;
      const p=(ang,rad)=>`${(50+Math.cos(ang)*rad).toFixed(1)},${(50+Math.sin(ang)*rad).toFixed(1)}`;
      return `<path class="as-petal${i===st.top&&c?' top':''}" style="--i:${i}" d="M50,50 L${p(a-w,r)} A${r},${r} 0 0 1 ${p(a+w,r)} Z"><title>พัดไปทาง${DIR8[i]} ${(st.moving?c/st.moving*100:0).toFixed(0)}%</title></path>`;}).join('');
    return `<svg class="as-rose" viewBox="0 0 100 100" role="img" aria-label="ทิศที่ลมพัดไป">
      <circle cx="50" cy="50" r="46" class="as-rose-ring"/><circle cx="50" cy="50" r="28" class="as-rose-ring"/>${petals}
      <text x="50" y="8" class="as-rose-n">N</text><circle cx="50" cy="50" r="9" class="as-rose-hub"/></svg>`;
  }
  // When in the day the wind is strongest (local hour) and how strong it usually is: fire spreads fastest then.
  function windHours(w){
    const sum=new Array(24).fill(0),n=new Array(24).fill(0);
    w.hours.forEach(x=>{const hh=Number(String(x.t||'').slice(11,13));if(Number.isInteger(hh)&&hh>=0&&hh<24){sum[hh]+=x.spd;n[hh]++;}});
    const avg=sum.map((s,i)=>n[i]?s/n[i]:null);
    if(avg.filter(v=>v!==null).length<12)return null;
    let best=0,bestV=-1;for(let i=0;i<24;i++){const v=[0,1,2].map(k=>avg[(i+k)%24]).filter(x=>x!==null);const m=v.length?v.reduce((a,b)=>a+b,0)/v.length:-1;if(m>bestV){bestV=m;best=i;}}
    return {avg,best,bestV};
  }
  function windClasses(w){
    const c=[0,0,0,0];w.hours.forEach(x=>{c[x.spd<5?0:x.spd<12?1:x.spd<20?2:3]++;});
    const n=w.hours.length||1;return c.map(v=>v/n*100);
  }
  function windExtra(w){
    const hrs=windHours(w),cls=windClasses(w);
    const max=hrs?Math.max(1,...hrs.avg.filter(v=>v!==null)):1;
    const bars=hrs?hrs.avg.map((v,i)=>{const hgt=v===null?0:Math.max(2,v/max*40);const hot=i>=hrs.best&&i<hrs.best+3||i+24<hrs.best+3;
      return `<rect x="${i*10+1}" y="${44-hgt}" width="8" height="${hgt}" rx="2" class="as-wh${hot?' hot':''}"><title>${String(i).padStart(2,'0')}:00 น. เฉลี่ย ${v===null?'-':v.toFixed(1)} กม./ชม.</title></rect>`;}).join(''):'';
    const pad=x=>String(x%24).padStart(2,'0')+':00';
    const names=['เบามาก','เบา','ปานกลาง','แรง'],tips=['ต่ำกว่า 5','5–12','12–20','20 ขึ้นไป'];
    return `<div class="as-wind-extra">
      ${hrs?`<div class="as-wind-part"><p class="as-k2">ลมแรงช่วงไหนของวัน</p>
        <svg class="as-wind-hours" viewBox="0 0 240 46" preserveAspectRatio="none" role="img" aria-label="ความเร็วลมเฉลี่ยรายชั่วโมงของวัน">${bars}</svg>
        <div class="as-wind-axis" aria-hidden="true"><span>00</span><span>06</span><span>12</span><span>18</span><span>23 น.</span></div>
        <p class="as-sub">แรงสุดราว <b>${pad(hrs.best)}–${pad(hrs.best+3)} น.</b> เฉลี่ย ${esc(hrs.bestV.toFixed(1))} กม./ชม. · ไฟมักลามเร็วกว่าช่วงอื่นของวัน</p></div>`:''}
      <div class="as-wind-part"><p class="as-k2">ความแรงของลมตลอดช่วง</p>
        <div class="as-wind-cls" role="img" aria-label="${names.map((x,i)=>x+' '+cls[i].toFixed(0)+'%').join(' ')}">${cls.map((p,i)=>p>0?`<i class="c${i}" style="flex:${p.toFixed(2)}"></i>`:'').join('')}</div>
        <ul class="as-wind-key">${names.map((x,i)=>`<li><i class="c${i}"></i>${x} <small>${tips[i]} กม./ชม.</small> <b>${cls[i].toFixed(0)}%</b></li>`).join('')}</ul></div>
    </div>`;
  }
  function windCard(h,w,err){
    const span=h.days===1?'24 ชม.':h.days+' วัน';
    const head=`<header class="as-head"><span class="as-ic wind" aria-hidden="true">➶</span><h3 id="asWindT" class="as-k">ลมย้อนหลัง ${esc(span)}${focusArea||focusDistrict?'<small class="as-scope">ภาพรวมจังหวัด</small>':''}</h3></header>`;
    if(err)return `${head}<p class="as-s">อ่านข้อมูลลมย้อนหลังไม่ได้ตอนนี้</p>`;
    if(!w)return `${head}<div class="as-wind-skel" aria-label="กำลังโหลดลม"></div>`;
    const st=windStats(w);if(!st)return `${head}<p class="as-s">ยังไม่มีข้อมูลลมในช่วงนี้</p>`;
    return `${head}<div class="as-wind-body">${rose(st)}<div>
        <p class="as-v">${num(st.avg,1)} <span>กม./ชม. เฉลี่ย</span></p>
        <p class="as-s">${st.moving?`ส่วนใหญ่ลมพัดไปทาง<b>${esc(DIR8[st.top])}</b> (${esc(st.topPct.toFixed(0))}% ของเวลาที่มีลม)`:'ลมเบามากเกือบตลอดช่วง'}</p>
        <p class="as-sub">ลมเบามาก (ต่ำกว่า 5 กม./ชม.) ${esc(st.calmPct.toFixed(0))}% ของเวลา</p></div></div>
      ${windExtra(w)}
      <p class="as-note">ไฟมักลามตามทิศที่ลมพัดไป · ${esc(w.source)} ลม 10 เมตร รายชั่วโมง ${esc(st.n.toLocaleString('th-TH'))} ชม. ที่จุดอ้างอิงเมืองเชียงใหม่ ไม่ใช่ลมในป่าแต่ละแห่ง</p>`;
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
      return `<path d="${d}" fill="${s.dim?'var(--as-map-empty)':fill(c)}" class="${s.dim?'dim':''}" data-as-district="${esc(s.name)}" tabindex="-1"><title>อ.${esc(s.name)}${s.dim?'':' · '+c+' จุด'}</title></path>`;
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
  function forestCard(a,{forestInfo},h){
    const rows=(a.forests||[]).filter(f=>f.count>0).map(f=>({...f,info:forestInfo?.(f.forest_id)})).sort((x,y)=>y.count-x.count);
    const top=rows.slice(0,5);
    return `<article class="as-card as-forest" aria-labelledby="asForT">
      <header class="as-head"><span class="as-ic forest" aria-hidden="true">🌳</span><h3 id="asForT" class="as-k">ป่าชุมชนที่มีจุดความร้อนในเขต</h3></header>
      ${top.length?`<p class="as-v">${num(rows.length)} <span>ป่า</span></p><ul class="as-forests">${top.map(f=>`<li><button type="button" data-as-forest="${esc(f.forest_id)}">
          <span><b>${esc(f.info?.name||'ป่าชุมชน '+f.forest_id)}</b><small>${f.info?.amphoe?'อ.'+esc(f.info.amphoe):''}</small></span><em>${esc(f.count)} จุด</em></button></li>`).join('')}</ul>
        ${rows.length>top.length?`<p class="as-note">และอีก ${esc(rows.length-top.length)} ป่า</p>`:''}`
        :`<p class="as-s as-good">ช่วง${h&&h.days===1?' 24 ชม.':h?` ${esc(h.days)} วัน`:'นี้'}นี้ ไม่มีจุดความร้อนตกในขอบเขตป่าชุมชน</p>
          <p class="as-note">การ์ดนี้นับเฉพาะจุดจากดาวเทียมที่อยู่ <b>ในเขต</b> ป่าชุมชน 677 แห่ง ${a.total?`(ช่วงนี้มี ${esc(a.total)} จุดทั้งจังหวัด แต่อยู่นอกป่าทั้งหมด)`:''} · ไม่พบจุด ไม่ได้แปลว่าไม่มีไฟ ดาวเทียมอาจมองไม่เห็นไฟเล็กหรือไฟใต้เรือนยอด</p>
          ${h&&h.days<180?`<button type="button" class="as-more" data-as-range="${h.days<90?'90d':'180d'}">ดูช่วง ${h.days<90?'90':'180'} วันแทน</button>`:''}`}
      <p class="as-note">นับเฉพาะจุดที่อยู่ในขอบเขตป่า RECOFTC · ยังไม่ใช่เหตุไฟที่ยืนยันแล้ว</p>
    </article>`;
  }
  function districtFocusCard(a,shapes,name){
    const rows=(a.tambons||[]).filter(t=>t.count>0).slice(0,6), max=Math.max(1,...rows.map(r=>r.count));
    const counts={[name]:a.total||0};
    return `<article class="as-card as-dist as-focus" aria-labelledby="asDistT">
      <header class="as-head"><span class="as-ic dist" aria-hidden="true">⌖</span><h3 id="asDistT" class="as-k">ตำบลใน อ.${esc(name)} ที่มีจุดความร้อน</h3></header>
      <div class="as-dist-body">${miniMap((shapes||[]).map(x=>({...x,dim:x.name!==name})),counts)}
      ${rows.length?`<ol class="as-rank">${rows.map((r,i)=>`<li><button type="button" data-as-district="${esc(name)}" aria-label="ต.${esc(r.name)} ${esc(r.count)} จุด">
        <span class="as-rank-n">${i+1}</span><span class="as-name">ต.${esc(r.name)}</span><span class="as-track"><i style="--w:${(r.count/max*100).toFixed(1)}%"></i></span><b>${esc(r.count)}</b></button></li>`).join('')}</ol>`
        :'<p class="as-s">ไม่พบจุดที่ระบุตำบลในช่วงนี้</p>'}</div>
      <p class="as-note">กดเพื่อดูอำเภอนี้บนแผนที่ · ชื่อตำบลในคลังบางจุดประมาณจากตำแหน่ง</p>
    </article>`;
  }
  function forestFocusCard(f,a){
    const area=f.area_rai?Number(f.area_rai).toLocaleString('th-TH')+' ไร่':'';
    return `<article class="as-card as-forest as-focus" aria-labelledby="asFocT">
      <header class="as-head"><span class="as-ic forest" aria-hidden="true">🌳</span><h3 id="asFocT" class="as-k">${esc(f.name||'ป่าชุมชน')}</h3></header>
      <p class="as-sub">${[f.amphoe?'อ.'+esc(f.amphoe):'',f.tambon?'ต.'+esc(f.tambon):'',area].filter(Boolean).join(' · ')}</p>
      <p class="as-v">${num(a.total)} <span>จุดความร้อนในขอบเขตป่า</span></p>
      <p class="as-note">นับเฉพาะจุดที่อยู่ในขอบเขตป่า RECOFTC · ฝุ่นและลมด้านบนเป็นภาพรวมจังหวัด ยังไม่มีสถานีวัดในป่า</p>
      <button type="button" class="as-link ghost" data-as-forest="${esc(f.forest_id)}">ดูป่านี้บนแผนที่</button>
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
    const pm=pmSeries(a,(a.hotspots||[]).map(d=>d.date)), norm=opts.norm||(s=>String(s||'').replace(/^อำเภอ|^อ\./,'').trim());
    const span=history.days===1?'24 ชั่วโมง':history.days+' วัน';
    withYear=history.days>=180;
    focusArea=opts.forest||null; focusDistrict=focusArea?null:(opts.district||null);
    const tail=focusArea?forestFocusCard(focusArea,a)
      :focusDistrict?`${districtFocusCard(a,opts.shapes,focusDistrict)}${forestCard(a,opts,history)}`
      :`${districtCard(a,{shapes:opts.shapes,norm})}${forestCard(a,opts,history)}`;
    el.innerHTML=`<h2 class="as-section past"><span class="as-badge">ย้อนหลัง</span>${esc(span)}ที่ผ่านมา · ข้อมูลที่เกิดขึ้นแล้ว</h2>
      ${archiveStartNote(history,a)}${heroHtml(history,a,pm)}
      ${banStatus()}
      <div class="as-grid">${hotspotCard(history,a,opts)}${pmCard(history,a,pm)}<article class="as-card as-wind" aria-labelledby="asWindT">${windCard(history,null)}</article>${tail}</div>
      <h2 class="as-section future"><span class="as-badge">พยากรณ์</span>ข้างหน้า · สิ่งที่คาดว่าจะเกิด ยังไม่เกิดขึ้น</h2>
      <div class="as-future">
        <section class="as-card as-fwi" aria-labelledby="asFwiT"><header class="as-head"><span class="as-ic fwi" aria-hidden="true">🔥</span><h3 id="asFwiT" class="as-k">อากาศเอื้อต่อไฟแค่ไหน · 16 วันข้างหน้า${focusDistrict?` · อ.${esc(focusDistrict)}`:focusArea?.amphoe?` · อ.${esc(String(focusArea.amphoe).replace(/^อำเภอ|^อ\./,'').trim())}`:''}</h3></header><div class="fw-body"><div class="as-wind-skel" aria-label="กำลังคำนวณ"></div></div></section>
        <section class="as-card as-outlook" aria-labelledby="asOutT"><header class="as-head"><span class="as-ic wx" aria-hidden="true">📅</span><h3 id="asOutT" class="as-k">แนวโน้ม 4 สัปดาห์ · ฝนและอุณหภูมิเทียบกับปกติ</h3></header><div class="fw-body"><div class="as-wind-skel" aria-label="กำลังโหลด"></div></div></section>
        ${forecastHtml(forecast)}
      </div>
      <div data-line-slot></div>`;
    wire(el);wireLine(el);countUp(el);
    el.querySelectorAll('[data-as-range]').forEach(b=>b.addEventListener('click',()=>root.document?.querySelector(`#anRange [data-r="${b.dataset.asRange}"]`)?.click()));
    fillLine(el,focusDistrict||String(focusArea?.amphoe||'').replace(/^อำเภอ|^อ\./,'').trim(),opts.fetcher||root.fetch?.bind(root));
    loadFuture(el,history,opts);
    const want=history.days, card=el.querySelector('.as-wind');
    loadWind(want,opts.fetcher||root.fetch?.bind(root)).then(w=>{if(card.isConnected){card.innerHTML=windCard(history,w);countUp(card);}})
      .catch(()=>{if(card.isConnected)card.innerHTML=windCard(history,null,true);});
  }
  // Only compare when the earlier window was actually received (>= 80 % of its
  // full days have complete satellite requests). Before the archive began the
  // API returns 0, which must never read as "no fires back then".
  function covered(prior){
    const d=(prior?.analytics?.hotspots||[]).filter(x=>!x.partial_day);
    return d.length>0&&d.filter(x=>x.source_requests_complete).length/d.length>=0.8;
  }
  function renderCompare(el,history,prior){
    if(!el)return;
    const span=history.days===1?'24 ชม.':history.days+' วัน';
    const hot=el.querySelector('[data-compare="hot"]'), pmEl=el.querySelector('[data-compare="pm"]');
    if(!prior||!covered(prior)){
      if(hot)hot.innerHTML=`<span class="as-cmp none">ยังไม่มีข้อมูลครบของ ${esc(span)}ก่อนหน้า จึงยังเทียบไม่ได้</span>`;
      if(pmEl)pmEl.innerHTML='';
      return;
    }
    const a=history.analytics,b=prior.analytics,d=a.total-b.total;
    if(hot){
      const pct=b.total>0?Math.round(Math.abs(d)/b.total*100):null;
      hot.innerHTML=d===0?`<span class="as-cmp same">เท่ากับ ${esc(span)}ก่อนหน้า (${esc(b.total)} จุด)</span>`
        :`<span class="as-cmp ${d>0?'up':'down'}">${d>0?'▲ มากกว่า':'▼ น้อยกว่า'} ${esc(span)}ก่อนหน้า ${esc(Math.abs(d))} จุด${pct!==null?` (${d>0?'+':'−'}${esc(pct)}%)`:''}</span><small>ก่อนหน้า ${esc(b.total)} จุด</small>`;
    }
    if(pmEl){
      const cur=pmSeries(a,(a.hotspots||[]).map(x=>x.date)),old=pmSeries(b,(b.hotspots||[]).map(x=>x.date));
      if(cur.avg!==null&&old.avg!==null&&old.fullDays>=Math.max(1,Math.round(history.days*0.8))){
        const dv=cur.avg-old.avg;
        pmEl.innerHTML=Math.abs(dv)<0.5?`<span class="as-cmp same">ฝุ่นเฉลี่ยใกล้เคียง ${esc(span)}ก่อนหน้า (${esc(fmt1(old.avg))})</span>`
          :`<span class="as-cmp ${dv>0?'up':'down'}">${dv>0?'▲ สูงกว่า':'▼ ต่ำกว่า'} ${esc(span)}ก่อนหน้า ${esc(fmt1(Math.abs(dv)))} µg/m³</span><small>ก่อนหน้าเฉลี่ย ${esc(fmt1(old.avg))}</small>`;
      }else pmEl.innerHTML='';
    }
  }
  // Public dust alerts: no account, just the LINE Official Account.
  const LINE_OA='@241mevgs';
  // Open only for districts where at least two live WAQI sensors report now;
  // the backend sends counts only, never readings.
  let coverageP=null,coverageAt=0;
  function loadCoverage(fetcher){
    if(coverageP&&Date.now()-coverageAt<600000)return coverageP;
    if(typeof fetcher!=='function')return Promise.reject(new Error('no fetch'));
    coverageAt=Date.now();
    coverageP=fetcher('/api/dust-alerts/coverage').then(r=>{if(!r.ok)throw Error('coverage '+r.status);return r.json();});
    coverageP.catch(()=>{coverageP=null;});
    return coverageP;
  }
  function fillLine(el,selected,fetcher){
    const slot=el.querySelector('[data-line-slot]');if(!slot)return;
    loadCoverage(fetcher).then(c=>{
      if(!slot.isConnected||!c?.enabled)return;
      const min=c.min_sensors||2;
      const ok=Object.entries(c.districts||{}).filter(([,n])=>n>=min).map(([d])=>d);
      slot.outerHTML=lineCard(ok,selected,min);
    }).catch(()=>{});
  }
  function lineCard(names,selected,min=2){
    if(!names?.length)return '';
    const list=[...names].sort((a,b)=>a.localeCompare(b,'th'));
    const pick=selected&&list.includes(selected)?selected:'';
    const missing=selected&&!pick?`<p class="as-s">อ.${esc(selected)} ยังมีเซนเซอร์ที่ส่งข้อมูลไม่ถึง ${min} จุด จึงยังรับแจ้งเตือนไม่ได้</p>`:'';
    return `<section class="as-card as-line" aria-labelledby="asLineT">
      <header class="as-head"><span class="as-ic line" aria-hidden="true">💬</span><h3 id="asLineT" class="as-k">รับแจ้งเตือนฝุ่นทาง LINE</h3></header>
      <p class="as-s">แจ้งเมื่อเซนเซอร์วัดฝุ่นในอำเภอของคุณวัดดัชนี AQI ของ PM2.5 ได้ระดับ <b class="as-lv" style="--lv:var(--pm-unhealthy)">เริ่มมีผลต่อกลุ่มเสี่ยง</b> (101) ขึ้นไป ต่อเนื่องอย่างน้อย 1 ชม. ไม่ต้องสมัครสมาชิก</p>
      ${missing}<p class="as-s">ตอนนี้เปิดให้ ${list.length} อำเภอที่มีเซนเซอร์ส่งข้อมูลอย่างน้อย ${min} จุด</p>
      <div class="as-line-row"><label class="as-line-pick"><span>อำเภอ</span>
        <select data-line-district aria-label="เลือกอำเภอที่ต้องการรับแจ้งเตือน"><option value="">เลือกอำเภอ</option>${list.map(n=>`<option value="${esc(n)}"${n===pick?' selected':''}>อ.${esc(n)}</option>`).join('')}</select></label>
        <a class="as-line-go" data-line-go href="${pick?lineHref(pick):'#'}" target="_blank" rel="noopener" aria-disabled="${pick?'false':'true'}">เปิด LINE เพื่อรับแจ้งเตือน</a></div>
      <ol class="as-line-steps"><li>กดปุ่ม แล้วกดส่งข้อความที่พิมพ์ไว้ให้</li><li>ยังไม่ได้เพิ่มเพื่อน? <a href="https://line.me/R/ti/p/${encodeURIComponent(LINE_OA)}" target="_blank" rel="noopener">เพิ่มเพื่อน ChiangMaiEyes</a> ก่อน</li><li>หยุดเมื่อไรก็ได้ พิมพ์ “หยุด” ในแชท</li></ol>
      <p class="as-note">ใช้ค่ากลางจากเซนเซอร์อย่างน้อย 2 จุดในอำเภอ ส่วนใหญ่เป็นเซนเซอร์ราคาประหยัด ค่าอาจคลาดเคลื่อน · เกณฑ์ AQI ของ US EPA · ไม่เกินวันละครั้งต่อระดับ · เก็บเพียงรหัสผู้ใช้ LINE กับอำเภอที่เลือก · ข้อมูล: <a href="https://waqi.info/" target="_blank" rel="noopener">World Air Quality Index Project</a> และหน่วยงานเจ้าของสถานี</p>
    </section>`;
  }
  const lineHref=d=>`https://line.me/R/oaMessage/${encodeURIComponent(LINE_OA)}/?${encodeURIComponent('แจ้งเตือนฝุ่น '+d)}`;
  function wireLine(el){
    if(el.dataset.lineWired)return;el.dataset.lineWired='1';
    el.addEventListener('change',e=>{
      const sel=e.target.closest?.('[data-line-district]');if(!sel)return;
      const a=el.querySelector('[data-line-go]');
      a.href=sel.value?lineHref(sel.value):'#';a.setAttribute('aria-disabled',sel.value?'false':'true');
    });
    el.addEventListener('click',e=>{const a=e.target.closest?.('[data-line-go]');if(a&&a.getAttribute('aria-disabled')==='true'){e.preventDefault();el.querySelector('[data-line-district]')?.focus();}});
  }
  // Centre of each district outline (largest ring), for the fire-weather points.
  function centre(rings){
    const area=r=>{let a=0;for(let i=0,j=r.length-1;i<r.length;j=i++)a+=r[j][0]*r[i][1]-r[i][0]*r[j][1];return a/2;};
    const r=[...rings].sort((x,y)=>Math.abs(area(y))-Math.abs(area(x)))[0];if(!r)return null;
    let a=0,cx=0,cy=0;for(let i=0,j=r.length-1;i<r.length;j=i++){const f=r[j][0]*r[i][1]-r[i][0]*r[j][1];a+=f;cx+=(r[j][0]+r[i][0])*f;cy+=(r[j][1]+r[i][1])*f;}
    return a?{lon:cx/(3*a),lat:cy/(3*a)}:null;
  }
  function loadFuture(el,history,opts){
    const F=root.CmeFireWeather;if(!F)return;
    const fwiBox=el.querySelector('.as-fwi .fw-body'), outBox=el.querySelector('.as-outlook .fw-body');
    const points=(opts.shapes||[]).map(x=>({name:x.name,...(centre(x.rings)||{})})).filter(p=>Number.isFinite(p.lat));
    const focus=focusDistrict||(focusArea?.amphoe?String(focusArea.amphoe).replace(/^อำเภอ|^อ\./,'').trim():null);
    const fetcher=opts.fetcher||root.fetch?.bind(root);
    if(points.length&&fetcher)F.loadDistricts(points,fetcher).then(data=>{
      if(!fwiBox.isConnected)return;
      fwiBox.innerHTML=F.fwiCard(data,{focus:focus&&points.some(p=>p.name===focus)?focus:null,hot:focusArea||focusDistrict?[]:(history.analytics?.hotspots||[])});
    }).catch(()=>{if(fwiBox.isConnected)fwiBox.innerHTML='<p class="as-s">ยังคำนวณดัชนีไม่ได้ตอนนี้ ลองใหม่ภายหลัง</p>';});
    else fwiBox.innerHTML='<p class="as-s">ยังคำนวณดัชนีไม่ได้ตอนนี้</p>';
    if(fetcher)F.loadOutlook(18.79,98.98,fetcher).then(w=>{if(outBox.isConnected)outBox.innerHTML=F.outlookCard(w);})
      .catch(()=>{if(outBox.isConnected)outBox.innerHTML='<p class="as-s">โหลดแนวโน้มรายสัปดาห์ไม่ได้ตอนนี้</p>';});
    else outBox.innerHTML='';
  }
  function renderForecast(el,forecast){
    const box=el?.querySelector('.as-future');if(!box)return;
    const old=box.querySelector('.as-forecast');const html=forecastHtml(forecast);
    if(old)old.outerHTML=html;else if(html)box.insertAdjacentHTML('beforeend',html);
  }
  root.CmeAnalyticsSummary={lineHref,lineCard,render,renderForecast,renderCompare,covered,bars,pmSeries,headline,windStats,loadWind,BURN_BANS,inBan};
})(window);
