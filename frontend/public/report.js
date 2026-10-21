/* The exported situation report (PDF via print, or PNG). A4, Sarabun, plain
 * Thai: a summary a resident can read in one go, then the figures, a map,
 * the areas, who to call, and where every number came from. Fire and dust
 * stay in separate lines; dust is PCD µg/m³ only (WAQI AQI may not be
 * redistributed, so it never goes into an exported file). */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tz='Asia/Bangkok';
  const longDate=t=>new Intl.DateTimeFormat('th-TH',{timeZone:tz,day:'numeric',month:'long',year:'numeric'}).format(t);
  const clock=t=>new Intl.DateTimeFormat('th-TH',{timeZone:tz,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(t)+' น.';
  const shortStamp=t=>new Intl.DateTimeFormat('th-TH',{timeZone:tz,day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(t)+' น.';
  const num=n=>Number(n).toLocaleString('th-TH');
  const AGE=[{max:6,label:'ไม่เกิน 6 ชม.',color:'#dc2626'},{max:24,label:'6–24 ชม.',color:'#f59e0b'},{max:Infinity,label:'เก่ากว่า 24 ชม.',color:'#94a3b8'}];
  const ageOf=(h,now)=>{const a=(now-Date.parse(h.detected_at))/36e5;return AGE.find(x=>a<x.max)||AGE[2];};
  const PM_COLORS=['#3b82f6','#22c55e','#eab308','#f97316','#dc2626'];

  // Counts by district (whole province) or by tambon (one forest or one point).
  function byArea(rows,scope,now){
    const key=h=>scope==='province'?(h.district||'ไม่ระบุอำเภอ'):(h.tambon||h.subdistrict||'ไม่ระบุตำบล')+(h.district?' อ.'+h.district:'');
    const m=new Map();
    rows.forEach(h=>{const k=key(h),t=Date.parse(h.detected_at);const r=m.get(k)||{name:k,n:0,last:0};r.n++;if(t>r.last)r.last=t;m.set(k,r);});
    return [...m.values()].sort((a,b)=>b.n-a.n||b.last-a.last);
  }

  function centre(ring){let x=0,y=0;ring.forEach(p=>{x+=p[0];y+=p[1];});return [x/ring.length,y/ring.length];}
  // A plain location map: district outlines, the forest or the 5 km circle,
  // hotspots coloured by age, north arrow and a scale bar. No base tiles, so
  // it prints the same everywhere and needs no outside images.
  function mapSvg({rows,shapes=[],forest,point,radiusKm=5,now,scope}){
    const W=700,pad=22;
    const geometry=forest?.boundary?.type==='Feature'?forest.boundary.geometry:forest?.boundary;
    const polys=geometry?.type==='Polygon'?[geometry.coordinates]:geometry?.type==='MultiPolygon'?geometry.coordinates:[];
    let pts=[...polys.flat(2),...rows.map(h=>[h.lon,h.lat])];
    if(point){const d=radiusKm/111.32;pts.push([point.lon-d/Math.cos(point.lat*Math.PI/180),point.lat-d],[point.lon+d/Math.cos(point.lat*Math.PI/180),point.lat+d]);}
    if(scope==='province'||!pts.length)pts=shapes.flatMap(s=>s.rings.flat());
    if(!pts.length)return '';
    let lo=Math.min(...pts.map(p=>p[0])),hi=Math.max(...pts.map(p=>p[0])),s=Math.min(...pts.map(p=>p[1])),n=Math.max(...pts.map(p=>p[1]));
    // Never zoom in past ~3 km across, so a single point still has context.
    const minSpan=0.03;if(hi-lo<minSpan){const c=(hi+lo)/2;lo=c-minSpan/2;hi=c+minSpan/2;}if(n-s<minSpan){const c=(n+s)/2;s=c-minSpan/2;n=c+minSpan/2;}
    const k=Math.cos((s+n)/2*Math.PI/180);
    // Height follows the shape (the province is tall), within half to ~0.9 of the width.
    const H=Math.round(Math.min(640,Math.max(340,(W-2*pad)*(n-s)/((hi-lo)*k)+2*pad+30)));
    const scale=Math.min((W-2*pad)/((hi-lo)*k),(H-2*pad-30)/(n-s));
    const ox=(W-(hi-lo)*k*scale)/2, oy=(H-30-(n-s)*scale)/2;
    const X=x=>ox+(x-lo)*k*scale, Y=y=>oy+(n-y)*scale;
    const path=rings=>rings.map(r=>r.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('')+'Z').join('');
    const hot=new Set(rows.map(h=>h.district).filter(Boolean));
    const districts=shapes.map(d=>`<path d="${path(d.rings)}" class="rm-d${hot.has(d.name)?' hot':''}"/>`).join('');
    const top=new Set(byArea(rows,'province',now).slice(0,8).map(a=>a.name));
    const labels=scope==='province'?shapes.filter(d=>top.has(d.name)).map(d=>{const big=[...d.rings].sort((a,b)=>b.length-a.length)[0];const [cx,cy]=centre(big);return `<text x="${X(cx).toFixed(1)}" y="${Y(cy).toFixed(1)}" class="rm-l">${esc(d.name)}</text>`;}).join(''):'';
    const forestPath=polys.length?`<path d="${polys.map(p=>path(p)).join('')}" class="rm-f" fill-rule="evenodd"/>`:'';
    const circle=point?`<circle cx="${X(point.lon).toFixed(1)}" cy="${Y(point.lat).toFixed(1)}" r="${(radiusKm/111.32*scale).toFixed(1)}" class="rm-c"/>`:'';
    const dots=[...rows].sort((a,b)=>Date.parse(a.detected_at)-Date.parse(b.detected_at)).map(h=>`<circle cx="${X(h.lon).toFixed(1)}" cy="${Y(h.lat).toFixed(1)}" r="${scope==='province'?4.5:6}" fill="${ageOf(h,now).color}" class="rm-h"/>`).join('');
    // Scale bar: a round number of km close to a fifth of the width.
    const kmPerPx=111.32/scale, target=(W/5)*kmPerPx, step=[0.5,1,2,5,10,20,50].find(v=>v>=target*0.6)||50, barPx=step/kmPerPx;
    const usedAges=AGE.filter(a=>rows.some(h=>ageOf(h,now)===a));
    const legend=[...usedAges.map(a=>`<span><i style="background:${a.color}"></i>${a.label}</span>`),polys.length?'<span><i class="sq f"></i>ขอบเขตป่าชุมชน</span>':'',point?'<span><i class="ring"></i>รัศมี 5 กม.</span>':'','<span><i class="sq d"></i>เขตอำเภอ</span>'].join('');
    return `<figure class="rp-map"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="แผนที่ตำแหน่งจุดความร้อน ${rows.length} จุด">
      <defs><clipPath id="rpClip"><rect width="${W}" height="${H-30}"/></clipPath></defs>
      <rect width="${W}" height="${H}" class="rm-bg"/><g clip-path="url(#rpClip)">${districts}${forestPath}${circle}${dots}${labels}</g>
      <g transform="translate(${W-34},20)"><path d="M0,-12 L7,8 L0,4 L-7,8Z" class="rm-n"/><text y="22" class="rm-nt">N</text></g>
      <g transform="translate(16,${H-14})"><rect width="${barPx.toFixed(1)}" height="5" class="rm-sb"/><text x="${(barPx+6).toFixed(1)}" y="6" class="rm-st">${step} กม.</text></g>
    </svg><figcaption>${legend}</figcaption></figure>`;
  }

  function html(o){
    const now=o.now||Date.now(), rows=o.rows||[], area=o.scope==='province'?'จังหวัดเชียงใหม่':o.name;
    const areas=byArea(rows,o.scope,now), newest=rows.reduce((m,h)=>Math.max(m,Date.parse(h.detected_at)||0),0);
    const pm=o.air?o.pm:null, lvIdx=pm?.level?(root.CmePublicGuidance?.PM_LEVELS||[]).findIndex(l=>l.label===pm.level.label):-1;
    const pmColor=lvIdx>=0?PM_COLORS[lvIdx]:'#64748b';
    const fireLine=rows.length
      ?`ดาวเทียมตรวจพบจุดความร้อน <b>${num(rows.length)} จุด</b> ใน${esc(area)} ช่วง ${o.hours} ชั่วโมงล่าสุด${o.scope==='province'&&areas[0]?` พบมากที่สุดที่ <b>อ.${esc(areas[0].name)}</b> ${num(areas[0].n)} จุด`:''} จุดล่าสุดตรวจพบเมื่อ ${esc(shortStamp(newest))}`
      :`ช่วง ${o.hours} ชั่วโมงล่าสุด ดาวเทียมไม่พบจุดความร้อนใน${esc(area)} ทั้งนี้ไม่ได้ยืนยันว่าไม่มีไฟ`;
    const dustLine=!o.air?'':pm?`ฝุ่น PM2.5 รอบล่าสุด <b>${esc(pm.value)} ไมโครกรัมต่อลูกบาศก์เมตร</b> อยู่ในระดับ <b style="color:${pmColor}">${esc(pm.level?.label||'')}</b> ${pm.level?.advice?esc(pm.level.advice):''}`:'ยังไม่มีค่าฝุ่นที่ใช้ได้จากสถานีวัดในพื้นที่ที่เลือก';
    const windLine=!o.air?'':o.wind?`ลมพัดไปทางทิศ${esc(o.wind.dir)} ความเร็ว ${esc(o.wind.kmh)} กม./ชม. ไฟมักลามตามทิศที่ลมพัดไป`:'';
    const fig=(k,v,u,sub,color)=>`<div class="rp-fig"${color?` style="--c:${color}"`:''}><div class="k">${k}</div><div class="v">${v}<small>${u}</small></div><div class="s">${sub}</div></div>`;
    let n=0;const h2=t=>`<h2><span>${++n}</span>${t}</h2>`;
    const areaTable=areas.length?`<table class="rp-t"><thead><tr><th class="c">ลำดับ</th><th>${o.scope==='province'?'อำเภอ':'ตำบล'}</th><th class="r">จำนวนจุด</th><th>ตรวจพบล่าสุด</th></tr></thead><tbody>${areas.slice(0,12).map((a,i)=>`<tr><td class="c">${i+1}</td><td>${o.scope==='province'?'อ.':'ต.'}${esc(a.name)}</td><td class="r"><b>${num(a.n)}</b></td><td>${esc(shortStamp(a.last))}</td></tr>`).join('')}</tbody></table>${areas.length>12?`<p class="rp-note">และอีก ${areas.length-12} พื้นที่</p>`:''}`:'<p>ไม่พบจุดความร้อนในพื้นที่และช่วงเวลาที่เลือก</p>';
    const detail=()=>o.showTable?`${h2('รายละเอียดจุดความร้อน')}<table class="rp-t rp-small"><thead><tr><th class="c">ลำดับ</th><th>ตำบล / อำเภอ</th><th>พิกัด (ละติจูด, ลองจิจูด)</th><th>เวลาตรวจพบ</th><th>ลักษณะพื้นที่</th></tr></thead><tbody>${[...rows].sort((a,b)=>Date.parse(b.detected_at)-Date.parse(a.detected_at)).map((h,i)=>`<tr><td class="c">${i+1}</td><td>${h.tambon?'ต.'+esc(h.tambon)+' ':''}${h.district?'อ.'+esc(h.district):''}</td><td>${h.lat.toFixed(4)}, ${h.lon.toFixed(4)}</td><td>${esc(shortStamp(Date.parse(h.detected_at)))}</td><td>${esc(h.landuse_name||'—')}</td></tr>`).join('')||'<tr><td colspan="5">ไม่พบจุดความร้อน</td></tr>'}</tbody></table>`:'';
    const c=o.contact;
    return `<header class="rp-head">
        <img src="${esc(o.logo||'/logo-mark.png')}" alt="" class="rp-logo" width="76" height="54">
        <div class="rp-org"><b>ChiangMaiEyes</b><span>ระบบติดตามไฟป่า ฝุ่น และลม จังหวัดเชียงใหม่</span></div>
        <div class="rp-date"><span>ออกรายงาน</span><b>${esc(longDate(now))}</b><span>เวลา ${esc(clock(now))}</span></div>
      </header>
      <h1 class="rp-title">รายงานสถานการณ์จุดความร้อนและคุณภาพอากาศ</h1>
      <p class="rp-scope"><span>พื้นที่ <b>${esc(area)}</b></span><span>ช่วงข้อมูล <b>${o.hours} ชั่วโมงล่าสุด</b></span></p>
      ${h2('สรุปสถานการณ์')}
      <div class="rp-summary"><p><i class="ic fire" aria-hidden="true"></i>${fireLine}</p>${dustLine?`<p><i class="ic dust" aria-hidden="true"></i>${dustLine}</p>`:''}${windLine?`<p><i class="ic wind" aria-hidden="true"></i>${windLine}</p>`:''}<p class="rp-call"><b>พบเห็นไฟหรือควัน โทรสายด่วน 1362</b> อย่าเข้าไปดับไฟเพียงลำพัง</p></div>
      ${h2('ตัวเลขสำคัญ')}
      <div class="rp-figs">${fig('จุดความร้อน',num(rows.length),' จุด',`ใน ${o.hours} ชั่วโมงล่าสุด`,'#dc2626')}${o.air?fig('ฝุ่น PM2.5',pm?esc(pm.value):'—',' µg/m³',pm?`ระดับ${esc(pm.level?.label||'')} · ${esc(pm.stations)} สถานี`:'ไม่มีสถานีในพื้นที่',pmColor):''}${o.air?fig('ลม',o.wind?esc(o.wind.kmh):'—',' กม./ชม.',o.wind?`พัดไปทางทิศ${esc(o.wind.dir)}`:'ยังไม่มีข้อมูลลม','#0284c7'):''}</div>
      ${o.showMap?`${h2('แผนที่ตำแหน่งจุดความร้อน')}${mapSvg({rows,shapes:o.shapes,forest:o.forest,point:o.point,now,scope:o.scope})}`:''}
      ${h2(o.scope==='province'?'จุดความร้อนรายอำเภอ':'จุดความร้อนรายตำบล')}${areaTable}
      ${detail()}
      ${h2('ช่องทางติดต่อ')}
      <table class="rp-t"><tbody>
        <tr><th>พบเห็นไฟป่าหรือควัน</th><td><b>สายด่วน 1362</b> กรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช</td></tr>
        ${c?`<tr><th>หน่วยงานป่าไม้ในพื้นที่</th><td>${esc(c.name)} โทร <b>${esc(c.phone)}</b><br><small>จากเว็บไซต์กรมป่าไม้ ตรวจเมื่อ ${esc(c.checked)}</small></td></tr>`:''}
        ${o.forest?`<tr><th>ป่าชุมชน</th><td>${esc(o.forest.name)}${o.forest.amphoe?' อ.'+esc(o.forest.amphoe):''} · ยังไม่มีช่องทางผู้ประสานงานป่าที่ยืนยันแล้ว</td></tr>`:''}
      </tbody></table>
      ${h2('ที่มาของข้อมูลและข้อควรทราบ')}
      <table class="rp-t rp-small"><thead><tr><th>ข้อมูล</th><th>แหล่งข้อมูล</th><th>เวลาของข้อมูล</th></tr></thead><tbody>${(o.sources||[]).map(s=>`<tr><td>${esc(s.what)}</td><td>${esc(s.label)}</td><td>${esc(s.time)}</td></tr>`).join('')}</tbody></table>
      <ul class="rp-limits">
        <li>จุดความร้อนคือตำแหน่งที่ดาวเทียมวัดความร้อนได้สูงผิดปกติ อาจเป็นไฟป่า การเผาในไร่ หรือแหล่งความร้อนอื่น ต้องมีผู้ตรวจสอบในพื้นที่ก่อนสรุปว่าเป็นเหตุไฟ</li>
        <li>ดาวเทียมอาจตรวจไม่พบไฟขนาดเล็ก ไฟใต้เรือนยอด หรือช่วงที่มีเมฆ การไม่พบจุดไม่ได้ยืนยันว่าไม่มีไฟ</li>
        ${o.air?'<li>ค่าฝุ่นเป็นค่ารอบล่าสุดของสถานีวัด ใช้เกณฑ์ระดับของกรมควบคุมมลพิษ ค่าลมเป็นค่าอ้างอิงระดับจังหวัด ไม่ใช่การวัดในป่าแต่ละแห่ง</li>':''}
      </ul>
      <footer class="rp-foot"><span>จัดทำจาก ChiangMaiEyes · chiangmaieyes.vercel.app · ขอบเขตป่าชุมชนจาก RECOFTC</span><span>รายงานนี้สรุปจากข้อมูลเปิด ไม่ใช่เอกสารทางราชการ</span></footer>`;
  }
  root.CmeReport={html,mapSvg,byArea};
})(typeof window!=='undefined'?window:globalThis);
