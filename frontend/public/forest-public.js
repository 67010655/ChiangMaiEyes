/* Community-forest tab for everyone (no login). Pick a forest by name or
 * "near me" and see its situation from data the site already has:
 * satellite hotspots in the forest and within 5 km of its boundary (24 h),
 * the province reference wind, the nearest live dust sensor, fire weather at
 * the forest, and who to call. Nothing here ranks forests; the "near
 * hotspots" list is ordered by the latest detection, not by a score. */
(function(root){
  'use strict';
  const NEAR_KM=5, SENSOR_KM=15, LIST_MAX=8;
  const KEY='cme-public-forest-v1';
  const E=()=>root.CmeEvidence, C=()=>root.CmeCoordination;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const DIRS=['เหนือ','ตะวันออกเฉียงเหนือ','ตะวันออก','ตะวันออกเฉียงใต้','ใต้','ตะวันตกเฉียงใต้','ตะวันตก','ตะวันตกเฉียงเหนือ'];
  const dirName=deg=>DIRS[Math.round((((deg%360)+360)%360)/45)%8];
  const kmText=km=>km<1?'น้อยกว่า 1 กม.':km.toFixed(km<10?1:0)+' กม.';

  // ---------- geometry ----------
  const rings=g=>!g?[]:g.type==='Feature'?rings(g.geometry):g.type==='Polygon'?[g.coordinates[0]]:g.type==='MultiPolygon'?g.coordinates.map(p=>p[0]):[];
  const bboxCache=new WeakMap();
  function bbox(f){
    if(bboxCache.has(f))return bboxCache.get(f);
    let b=null;
    for(const r of rings(f.boundary))for(const [x,y] of r){if(!b)b=[x,y,x,y];else{b[0]=Math.min(b[0],x);b[1]=Math.min(b[1],y);b[2]=Math.max(b[2],x);b[3]=Math.max(b[3],y);}}
    if(!b&&Number.isFinite(f.longitude))b=[f.longitude,f.latitude,f.longitude,f.latitude];
    bboxCache.set(f,b);return b;
  }
  function centre(f){
    if(Number.isFinite(f.latitude)&&Number.isFinite(f.longitude))return {lat:f.latitude,lon:f.longitude};
    const b=bbox(f);return b?{lat:(b[1]+b[3])/2,lon:(b[0]+b[2])/2}:null;
  }
  function bearing(a,b){
    const r=Math.PI/180,y=Math.sin((b.lon-a.lon)*r)*Math.cos(b.lat*r),x=Math.cos(a.lat*r)*Math.sin(b.lat*r)-Math.sin(a.lat*r)*Math.cos(b.lat*r)*Math.cos((b.lon-a.lon)*r);
    return (Math.atan2(y,x)/r+360)%360;
  }
  // Straight-line km from a point to the forest boundary (0 inside). A
  // boundary flagged for review falls back to the forest reference point.
  function distanceToForest(p,f){
    if(f.boundary&&f.boundary_quality!=='needs_review'){
      if(E().inBoundary(p.lat,p.lon,f.boundary))return 0;
      if(C()?.boundaryDistance)return C().boundaryDistance(p,f.boundary);
    }
    const c=centre(f);return c?E().distanceKm(p,c):Infinity;
  }

  // ---------- data ----------
  function ready(dash,k){const q=dash?.data_quality?.[k];return !!q&&!q.is_stale&&q.source_mode!=='UNAVAILABLE';}
  function recentHotspots(dash,now=Date.now()){
    if(!ready(dash,'hotspots'))return null;
    return E().filterHotspots((dash.hotspots?.items||[]).map(h=>({...h,lat:h.latitude??h.lat,lon:h.longitude??h.lon})),{hours:24,now});
  }
  // Hotspots in the forest and within NEAR_KM of it, nearest first.
  function around(f,hot){
    const b=bbox(f);if(!b)return [];
    const pad=NEAR_KM/111+0.01, padX=pad/Math.max(0.3,Math.cos(b[1]*Math.PI/180));
    return hot.filter(h=>h.lon>=b[0]-padX&&h.lon<=b[2]+padX&&h.lat>=b[1]-pad&&h.lat<=b[3]+pad)
      .map(h=>({h,km:distanceToForest(h,f)})).filter(x=>x.km<=NEAR_KM).sort((a,b)=>a.km-b.km);
  }
  function situation(f,dash,now=Date.now()){
    const hot=recentHotspots(dash,now);
    if(hot===null)return {status:'unknown',inside:0,near:0,rows:[],hotTime:dash?.data_quality?.hotspots?.latest_update};
    const rows=around(f,hot);
    const inside=rows.filter(r=>r.km===0).length, near=rows.length-inside;
    const w=ready(dash,'weather')?dash.weather:null;
    let wind=null;
    if(w&&Number.isFinite(w.wind_direction_deg)){
      const to=E().windTo(w.wind_direction_deg), c=centre(f);
      const outside=rows.find(r=>r.km>0);
      // "Toward the forest": the wind carries air from the nearest outside hotspot roughly at the forest (±45°).
      let toward=null;
      if(outside&&c){const d=Math.abs(((bearing(outside.h,c)-to)+540)%360-180);toward=d<=45;}
      wind={to,dir:dirName(to),kmh:Number.isFinite(w.wind_speed_kmh)?Math.round(w.wind_speed_kmh):null,toward,source:w.source,time:dash.data_quality?.weather?.latest_update};
    }
    return {status:inside?'alert':near?'watch':'calm',inside,near,rows,wind,hotTime:dash.data_quality?.hotspots?.latest_update};
  }
  // Forests with any hotspot inside or within NEAR_KM in 24 h, latest detection first.
  function forestsNearHotspots(forests,dash,now=Date.now()){
    const hot=recentHotspots(dash,now);if(!hot?.length)return hot===null?null:[];
    const out=[];
    for(const f of forests){
      const rows=around(f,hot);if(!rows.length)continue;
      out.push({forest:f,inside:rows.filter(r=>r.km===0).length,near:rows.filter(r=>r.km>0).length,latest:Math.max(...rows.map(r=>Date.parse(r.h.detected_at)))});
    }
    return out.sort((a,b)=>b.latest-a.latest);
  }
  function nearestSensor(f,data){
    const c=centre(f);if(!c||!data?.sensors)return null;
    return data.sensors.filter(s=>s.fresh).map(s=>({s,km:E().distanceKm(c,{lat:s.lat,lon:s.lon})})).filter(x=>x.km<=SENSOR_KM).sort((a,b)=>a.km-b.km)[0]||null;
  }

  // ---------- views ----------
  // Short lines in the card; every caveat lives once in "ที่มาและข้อจำกัด".
  const STATUS={
    calm:{cls:'calm',icon:'🌿',title:'ไม่พบจุดความร้อนในป่าและรอบ 5 กม.'},
    watch:{cls:'watch',icon:'👀',title:n=>`พบ ${n} จุดรอบป่าในระยะ 5 กม.`},
    alert:{cls:'alert',icon:'🔥',title:n=>`พบ ${n} จุดในขอบเขตป่า`},
    unknown:{cls:'unknown',icon:'⏳',title:'ยังไม่มีข้อมูลจุดความร้อนรอบล่าสุด',sub:'ยังสรุปไม่ได้ว่าปลอดภัย'},
  };
  function statusHtml(sit){
    const s=STATUS[sit.status], n=sit.status==='alert'?sit.inside:sit.near;
    const title=typeof s.title==='function'?s.title(n):s.title;
    const extra=sit.status==='alert'&&sit.near?` และอีก ${sit.near} จุดรอบป่า`:'';
    const sub=s.sub||('24 ชม. ล่าสุด'+(sit.hotTime?' · ข้อมูล '+E().stamp(sit.hotTime):''));
    return `<div class="fp-status ${s.cls}" role="status"><span class="fp-status-ic" aria-hidden="true">${s.icon}</span><div><b>${esc(title)}${esc(extra)}</b><small>${esc(sub)}</small></div></div>`;
  }
  function nearestHtml(sit){
    const n=sit.rows[0];if(!n)return '';
    return `<div class="fp-fact"><span class="fp-k">จุดใกล้ที่สุด</span><b>${n.km===0?'อยู่ในขอบเขตป่า':esc(kmText(n.km))+' จากขอบป่า'}</b><small>${esc(E().stamp(n.h.detected_at))}</small></div>`;
  }
  function windHtml(sit){
    const w=sit.wind;
    if(!w)return `<div class="fp-fact"><span class="fp-k">ลม</span><b>ยังไม่มีข้อมูล</b></div>`;
    const lead=w.toward===true?'<em class="fp-warn">พัดจากจุดความร้อนเข้าหาป่า</em>':w.toward===false?'<em>ไม่ได้พัดเข้าหาป่า</em>':'';
    return `<div class="fp-fact"><span class="fp-k">ลม</span><b><span class="fp-arrow" style="transform:rotate(${Math.round(w.to)}deg)" aria-hidden="true">↑</span> พัดไปทาง${esc(w.dir)}${w.kmh!==null?' · '+esc(w.kmh)+' กม./ชม.':''}</b>${lead}</div>`;
  }
  function factsHtml(sit){
    return `<div class="fp-facts">${nearestHtml(sit)}${windHtml(sit)}
        <div class="fp-fact" data-fp-dust><span class="fp-k">ฝุ่นใกล้ป่า</span><b class="fp-wait">กำลังดูเซนเซอร์…</b></div>
        <div class="fp-fact" data-fp-fwi><span class="fp-k">อากาศเอื้อต่อไฟวันนี้</span><b class="fp-wait">กำลังคำนวณ…</b></div>
      </div>`;
  }
  const LIMITS=['ขอบเขตป่าจาก RECOFTC · จุดความร้อนจากดาวเทียม NASA FIRMS (VIIRS/MODIS) ยังไม่ยืนยันเหตุภาคสนาม ดาวเทียมอาจไม่เห็นไฟเล็กหรือไฟใต้เรือนยอด',
    'ระยะทั้งหมดเป็นเส้นตรงโดยประมาณถึงขอบป่า ไม่ใช่ระยะเดินทาง',
    'ลมเป็นลมอ้างอิงระดับจังหวัด ไม่ใช่ลมที่วัดในป่านี้',
    'ฝุ่นเป็นดัชนี AQI ของ PM2.5 เกณฑ์ US EPA จากเซนเซอร์ใกล้ที่สุดในระยะ 15 กม. (World Air Quality Index Project) ส่วนใหญ่เป็นเซนเซอร์ราคาประหยัด',
    'อากาศเอื้อต่อไฟคำนวณจากอากาศ Open-Meteo ด้วยระบบ FWI ของแคนาดา ไม่ใช่การพยากรณ์ว่าไฟจะเกิดที่ไหน'];
  const limitsHtml=()=>`<details class="fp-limits"><summary>ที่มาและข้อจำกัดของข้อมูล</summary><ul>${LIMITS.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`;
  // Contacts: the office phone first (CSS moves the agency block up), details after.
  const whoHtml=(f,c)=>c&&C()?`<details class="fp-who"><summary>📞 ติดต่อใคร · หน่วยงานในพื้นที่</summary>${C().html(c.lat,c.lon,{myForestId:f.forest_id})}</details>`:'';
  // Small map: forest outline, hotspots, the 5 km band when there is one, wind.
  function mapSvg(f,sit){
    const b=bbox(f);if(!b)return '';
    // Fit the forest and any nearby hotspots (not the whole 5 km band, which would shrink a small forest to a dot).
    const lat0=(b[1]+b[3])/2, kx=Math.cos(lat0*Math.PI/180);
    let e=[...b];for(const r of sit.rows){e=[Math.min(e[0],r.h.lon),Math.min(e[1],r.h.lat),Math.max(e[2],r.h.lon),Math.max(e[3],r.h.lat)];}
    const span=Math.max((e[2]-e[0])*kx,e[3]-e[1],0.02), pad=span*0.18;
    const cx=(e[0]+e[2])/2, cy=(e[1]+e[3])/2, hw=Math.max((e[2]-e[0])*kx,0.02)/2+pad, hh=Math.max(e[3]-e[1],0.02)/2+pad;
    const x0=cx-hw/kx,x1=cx+hw/kx,y0=cy-hh,y1=cy+hh;
    const W=320,H=Math.max(150,Math.min(220,Math.round(W*(y1-y0)/((x1-x0)*kx))));
    const sx=Math.min(W/((x1-x0)*kx),H/(y1-y0));
    const ox=(W-(x1-x0)*kx*sx)/2, oy=(H-(y1-y0)*sx)/2;
    const P=(lon,lat)=>[(ox+(lon-x0)*kx*sx).toFixed(1),(oy+(y1-lat)*sx).toFixed(1)];
    const path=rings(f.boundary).map(r=>'M'+r.map(([x,y])=>P(x,y).join(',')).join('L')+'Z').join('');
    const c=centre(f), cp=c?P(c.lon,c.lat):[W/2,H/2], ring=NEAR_KM/111*sx;
    const inside=sit.rows.some(r=>r.km===0), near=sit.rows.some(r=>r.km>0);
    const dots=sit.rows.map(r=>{const [x,y]=P(r.h.lon,r.h.lat);return `<circle cx="${x}" cy="${y}" r="5" class="${r.km===0?'in':'near'}"/>`;}).join('');
    const kmPx=sx/111, step=[0.5,1,2,5].find(k=>k*kmPx>=40)||5;
    const scale=`<g class="fp-map-scale" transform="translate(12,${H-14})"><path d="M0 0H${(step*kmPx).toFixed(1)}M0 -4V0M${(step*kmPx).toFixed(1)} -4V0"/><text x="0" y="-7">${step} กม.</text></g><text class="fp-map-n" x="12" y="18">↑ ทิศเหนือ</text>`;
    const arrow=sit.wind?`<g class="fp-map-wind" transform="translate(${W-26},26)"><circle r="16"/><g transform="rotate(${Math.round(sit.wind.to)})"><path d="M0 9V-9M0 -9l-5 6M0 -9l5 6"/></g><text y="30" text-anchor="middle">ลม</text></g>`:'';
    const band=near?`<circle cx="${cp[0]}" cy="${cp[1]}" r="${(ring+Math.max((b[2]-b[0])*kx,(b[3]-b[1]))*sx/2).toFixed(1)}" class="band"/>`:'';
    const key=[`<span><i class="k-forest"></i>ขอบเขตป่า</span>`,near?`<span><i class="k-band"></i>รอบ 5 กม.</span>`:'',inside?`<span><i class="k-in"></i>จุดในป่า</span>`:'',near?`<span><i class="k-near"></i>จุดรอบป่า</span>`:''].join('');
    return `<svg class="fp-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="ขอบเขตป่าและจุดความร้อน 24 ชม.">
      ${band}${path?`<path d="${path}" class="forest"/>`:`<circle cx="${cp[0]}" cy="${cp[1]}" r="6" class="forest"/>`}${dots}${arrow}${scale}</svg>
      <p class="fp-map-key">${key}</p>`;
  }
  // A link that opens this forest's card; LINE's own share screen picks the chat.
  const shareUrl=f=>(root.location?.origin||'https://chiangmaieyes.vercel.app')+'/#community/forest/'+encodeURIComponent(f.forest_id);
  const shareText=f=>`${f.name||'ป่าชุมชน'}${f.amphoe?' อ.'+f.amphoe:''} · ดูจุดไฟ ลม และฝุ่นรอบป่า
${shareUrl(f)}`;
  const lineShareHref=f=>'https://line.me/R/share?text='+encodeURIComponent(shareText(f));
  const shareHtml=f=>`<div class="fp-share"><a class="cw-btn fp-line-btn" href="${esc(lineShareHref(f))}" target="_blank" rel="noopener">💬 แชร์ทาง LINE</a><button type="button" class="cw-btn" data-fp="copy" data-url="${esc(shareUrl(f))}">🔗 คัดลอกลิงก์</button></div>`;
  function forestCard(f,dash,now=Date.now(),labelText=''){
    const sit=situation(f,dash,now), c=centre(f);
    const meta=[f.village&&!String(f.name||'').includes(f.village)?'บ้าน'+f.village:'',f.tambon?'ต.'+f.tambon:'',f.amphoe?'อ.'+f.amphoe:'',Number.isFinite(f.area_rai)?Math.round(f.area_rai).toLocaleString('th-TH')+' ไร่':''].filter(Boolean).join(' · ');
    return `<article class="as-card fp-card" aria-labelledby="fpName">
      <header class="fp-card-head"><div><p class="fp-kicker">ป่าชุมชน</p><h2 id="fpName">${esc(f.name||'ป่าชุมชน')}</h2><p class="fp-meta">${esc(meta)}${f.fire_management_active?' · <span class="fp-tag">มีการจัดการไฟในทะเบียน</span>':''}</p></div></header>
      ${statusHtml(sit)}
      ${mapSvg(f,sit)}
      ${factsHtml(sit)}
      <div class="fp-actions">${c?`<button type="button" class="cw-btn primary" data-fp="map" data-lat="${c.lat}" data-lon="${c.lon}">ดูป่านี้บนแผนที่</button>`:''}<a class="cw-btn fp-call" href="tel:1362">📞 เห็นไฟ โทร 1362</a></div>
      ${shareHtml(f)}
      ${whoHtml(f,c)}
      ${limitsHtml()}
    </article>`;
  }
  // Rep view: the same status and facts, without the public card's map and actions.
  function repSummaryHtml(f,dash,now=Date.now()){
    const sit=situation(f,dash,now);
    return {sit,html:statusHtml(sit)+factsHtml(sit)};
  }
  function dustHtml(f,data){
    const n=nearestSensor(f,data);
    if(!n)return `<span class="fp-k">ฝุ่นใกล้ป่า</span><b>ไม่มีเซนเซอร์ในระยะ ${SENSOR_KM} กม.</b>`;
    const D=root.CmeDustSensors;
    return `<span class="fp-k">ฝุ่นใกล้ป่า</span><b>${esc(n.s.aqi_pm25)} AQI ${D.chip(n.s.aqi_pm25)}</b><small>ห่าง ${esc(kmText(n.km))} · ${esc(D.ago(n.s.time))} · ดัชนี US ไม่ใช่ µg/m³</small>`;
  }
  function fwiHtml(days,today){
    const F=root.CmeFireWeather, d=(days||[]).find(x=>x.date===today);
    if(!F||!d||!Number.isFinite(d.fwi))return `<span class="fp-k">อากาศเอื้อต่อไฟวันนี้</span><b>คำนวณไม่ได้ในตอนนี้</b>`;
    const k=F.CLASSES[F.classOf(d.fwi)];
    const ahead=(days||[]).filter(x=>x.date>today).slice(0,7), hi=ahead.filter(x=>F.classOf(x.fwi)>=3).length;
    return `<span class="fp-k">อากาศเอื้อต่อไฟวันนี้</span><b><span class="fp-dot" style="background:${k.color}"></span>${esc(k.label)} <small class="fp-num">FWI ${esc(d.fwi.toFixed(1))}</small></b>${hi?`<small>7 วันข้างหน้ามี ${hi} วันระดับสูงขึ้นไป</small>`:''}`;
  }
  function listHtml(rows,selectedId,label=f=>f.name){
    if(rows===null)return `<p class="fp-line">ข้อมูลจุดความร้อนยังไม่พร้อม</p>`;
    if(!rows.length)return `<p class="fp-line">🌿 ไม่พบจุดความร้อนในหรือรอบป่าชุมชนใดใน 24 ชม. ล่าสุด <small>(ไม่ได้แปลว่าไม่มีไฟ)</small></p>`;
    return `<ul class="fp-list">${rows.slice(0,LIST_MAX).map(r=>`<li><button type="button" data-fp="pick" data-id="${esc(r.forest.forest_id)}" class="${r.forest.forest_id===selectedId?'on':''}"><span class="fp-li-ic ${r.inside?'alert':'watch'}" aria-hidden="true">${r.inside?'🔥':'👀'}</span><span class="fp-li-t"><b>${esc(label(r.forest))}</b><small>อ.${esc(r.forest.amphoe||'')} · ${r.inside?`${r.inside} จุดในป่า`:''}${r.inside&&r.near?' · ':''}${r.near?`${r.near} จุดรอบป่า`:''}</small></span><span class="fp-li-time">${esc(E().stamp(new Date(r.latest).toISOString()))}</span></button></li>`).join('')}</ul>
      ${rows.length>LIST_MAX?`<p class="cw-help">และอีก ${rows.length-LIST_MAX} ป่า · ค้นหาชื่อป่าด้านบนเพื่อดู</p>`:''}<p class="as-note">เรียงตามเวลาที่ตรวจพบล่าสุด ไม่ใช่การจัดอันดับ</p>`;
  }
  const repHtml=()=>`<section class="fp-rep" aria-label="สำหรับตัวแทนป่าชุมชน"><span aria-hidden="true">🌳</span><p><b>เป็นตัวแทนป่าชุมชน?</b><small>รับแจ้งเตือน LINE/อีเมล บันทึกเหตุ และประสานป่าข้างเคียง</small></p><button type="button" class="cw-btn primary" data-cw="signin">เข้าสู่ระบบ</button></section>`;

  // Names repeat (same name and district several times): add tambon, then
  // area, so each choice can be told apart without an internal ID.
  const labelCache=new WeakMap();
  function labeller(forests){
    if(labelCache.has(forests))return labelCache.get(forests);
    const count=k=>forests.filter(k).length;
    const map=new Map();
    for(const f of forests){
      let t=f.name||'ป่าชุมชน';
      if(count(x=>x.name===f.name&&x.amphoe===f.amphoe)>1){
        t+=f.tambon?' · ต.'+f.tambon:'';
        if(count(x=>x.name===f.name&&x.amphoe===f.amphoe&&x.tambon===f.tambon)>1&&Number.isFinite(f.area_rai))t+=' · '+Math.round(f.area_rai).toLocaleString('th-TH')+' ไร่';
      }
      map.set(f.forest_id,t);
    }
    const fn=f=>map.get(f.forest_id)||f.name;labelCache.set(forests,fn);return fn;
  }
  const norm=s=>String(s||'').toLowerCase().replace(/ป่าชุมชน|อำเภอ|อ\.|ต\.|บ้าน/g,'').replace(/\s+/g,'');
  function searchHtml(forests,q){
    const label=labeller(forests), n=norm(q);
    if(!n)return '';
    const hits=forests.filter(f=>norm(label(f)+' '+f.amphoe+' '+(f.tambon||'')+' '+(f.village||'')).includes(n)).slice(0,8);
    if(!hits.length)return `<p class="fp-line">ไม่พบป่าชื่อ "${esc(q)}" ลองพิมพ์ชื่อบ้านหรืออำเภอ</p>`;
    return `<ul class="fp-list compact" role="listbox" aria-label="ผลค้นหาป่าชุมชน">${hits.map(f=>`<li><button type="button" role="option" data-fp="pick" data-id="${esc(f.forest_id)}"><span class="fp-li-t"><b>${esc(label(f))}</b><small>${f.tambon&&!label(f).includes('ต.')?'ต.'+esc(f.tambon)+' · ':''}อ.${esc(f.amphoe||'')}</small></span></button></li>`).join('')}</ul>`;
  }
  function html({forests=[],dashboard=null,selectedId='',incidentsHtml='',hasIncidents=false,showRep=true,showList=true,now=Date.now()}={}){
    const f=forests.find(x=>x.forest_id===selectedId)||null, label=labeller(forests);
    const rows=forestsNearHotspots(forests,dashboard,now);
    return `<div class="fp">
      <section class="fp-hero"><h2>ป่าชุมชนในเชียงใหม่ <span>${esc(forests.length.toLocaleString('th-TH'))} แห่ง</span></h2>
        <div class="fp-pick"><input type="search" id="fpSearch" class="fp-search" placeholder="พิมพ์ชื่อป่าหรืออำเภอ" aria-label="ค้นหาป่าชุมชน" autocomplete="off" aria-controls="fpResults"><button type="button" class="cw-btn" data-fp="near">📍 ใกล้ฉัน</button></div>
        <div id="fpResults" aria-live="polite"></div>
        ${f?`<p class="fp-current">กำลังดู <b>${esc(label(f))}</b> <button type="button" class="fp-link" data-fp="clear">เปลี่ยนป่า</button></p>`:''}</section>
      <div id="fpCard" data-id="${f?esc(f.forest_id):''}">${f?forestCard(f,dashboard,now):''}</div>
      ${showList?`<section class="fp-section"><h2>ป่าที่มีจุดความร้อนใกล้ · 24 ชม.</h2>${listHtml(rows,selectedId,label)}</section>`:''}
      ${hasIncidents?`<section class="fp-section"><h2>เหตุที่ชุมชนยืนยันแล้ว</h2>${incidentsHtml}</section>`:''}
      ${showRep?repHtml():''}
      ${!showRep||f?'':`<p class="fp-line fp-call-line">🔥 เห็นไฟหรือควัน <a href="tel:1362">โทร 1362</a> ได้เลย ไม่ต้องสมัคร</p>`}
    </div>`;
  }
  function nearMeHtml(rows,label){
    if(!rows.length)return '<p class="fp-line">ไม่พบป่าชุมชนใกล้ตำแหน่งนี้</p>';
    return `<ul class="fp-list compact">${rows.map(r=>`<li><button type="button" data-fp="pick" data-id="${esc(r.forest.forest_id)}"><span class="fp-li-t"><b>${esc(label(r.forest))}</b><small>อ.${esc(r.forest.amphoe||'')}</small></span><span class="fp-li-time">${esc(kmText(r.km))}</span></button></li>`).join('')}</ul><p class="as-note">ระยะเส้นตรงถึงขอบป่า · ตำแหน่งของคุณไม่ถูกส่งออกจากเครื่อง</p>`;
  }

  // ---------- behaviour ----------
  const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok'}).format(new Date());
  function remember(id){try{id?root.localStorage.setItem(KEY,id):root.localStorage.removeItem(KEY);}catch{}}
  function recall(){try{return root.localStorage.getItem(KEY)||'';}catch{return '';}}
  function fillAsync(el,f,fetcher){
    const dust=el.querySelector('[data-fp-dust]'), fwi=el.querySelector('[data-fp-fwi]'), c=centre(f);
    if(dust&&root.CmeDustSensors)root.CmeDustSensors.load(fetcher).then(d=>{if(dust.isConnected)dust.innerHTML=dustHtml(f,d);}).catch(()=>{if(dust.isConnected)dust.innerHTML='<span class="fp-k">ฝุ่นใกล้ป่า</span><b>โหลดเซนเซอร์ไม่สำเร็จ</b>';});
    else if(dust)dust.remove();
    if(fwi&&c&&root.CmeFireWeather)root.CmeFireWeather.loadDistricts([{name:'forest:'+f.forest_id,lat:c.lat,lon:c.lon}]).then(d=>{if(fwi.isConnected)fwi.innerHTML=fwiHtml(d[0]?.days,today());}).catch(()=>{if(fwi.isConnected)fwi.innerHTML=fwiHtml(null,today());});
    else if(fwi)fwi.remove();
    C()?.hydrate?.(el);
  }
  // ctx: {forests(), dashboard(), locate(lat,lon), fetcher, onPick(id), rerender()}
  function attach(el,ctx){
    el._fpCtx=ctx;
    if(!el.dataset.fpWired){el.dataset.fpWired='1';wire(el);}
    const box=el.querySelector('#fpCard'), id=box?.dataset.id;
    const f=id&&ctx.forests().find(x=>x.forest_id===id);
    if(f&&box?.firstElementChild)fillAsync(box,f,ctx.fetcher);
  }
  // Listeners go on the long-lived container once; each render reads the latest ctx.
  function wire(el){
    const pick=id=>{
      const ctx=el._fpCtx;
      const f=ctx.forests().find(x=>x.forest_id===id);remember(f?id:'');ctx.onPick?.(f?id:'');
      try{root.history?.replaceState(null,'',f?'#community/forest/'+encodeURIComponent(id):'#community');}catch{}
      ctx.rerender?.();
      if(f)el.querySelector('#fpCard')?.scrollIntoView?.({block:'start',behavior:'smooth'});
    };
    el.addEventListener('input',e=>{
      if(e.target.id!=='fpSearch')return;
      const out=el.querySelector('#fpResults');if(out)out.innerHTML=searchHtml(el._fpCtx.forests(),e.target.value);
    });
    el.addEventListener('click',e=>{
      const b=e.target.closest?.('[data-fp]');if(!b)return;
      if(b.dataset.fp==='pick')pick(b.dataset.id);
      else if(b.dataset.fp==='clear'){pick('');el.querySelector('#fpSearch')?.focus();}
      else if(b.dataset.fp==='copy'){
        const url=b.dataset.url, done=t=>{const old=b.textContent;b.textContent=t;setTimeout(()=>{if(b.isConnected)b.textContent=old;},2200);};
        const fallback=()=>{const box=document.createElement('input');box.className='fp-url';box.readOnly=true;box.value=url;box.setAttribute('aria-label','ลิงก์ป่านี้');b.replaceWith(box);box.select();};
        if(root.navigator?.clipboard?.writeText)root.navigator.clipboard.writeText(url).then(()=>done('✓ คัดลอกแล้ว'),fallback);else fallback();
      }
      else if(b.dataset.fp==='map')el._fpCtx.locate(Number(b.dataset.lat),Number(b.dataset.lon));
      else if(b.dataset.fp==='near'){
        const out=el.querySelector('#fpResults');
        if(!root.navigator?.geolocation){out.innerHTML='<p class="fp-line">เบราว์เซอร์นี้หาตำแหน่งไม่ได้ ลองพิมพ์ชื่อป่าแทน</p>';return;}
        out.innerHTML='<p class="fp-line">กำลังหาตำแหน่งของคุณ…</p>';
        root.navigator.geolocation.getCurrentPosition(p=>{
          const all=el._fpCtx.forests();
          out.innerHTML=nearMeHtml((C()?.nearest?.(p.coords.latitude,p.coords.longitude,all,5))||[],labeller(all));
        },()=>{out.innerHTML='<p class="fp-line">ไม่ได้รับอนุญาตให้ใช้ตำแหน่ง ลองพิมพ์ชื่อป่าแทน</p>';},{enableHighAccuracy:false,timeout:10000,maximumAge:300000});
      }
    });
  }

  root.CmeForestPublic={html,attach,recall,shareUrl,lineShareHref,repSummaryHtml,fillAsync,centre,searchHtml,labeller,limitsHtml,situation,forestsNearHotspots,nearestSensor,forestCard,listHtml,fwiHtml,dustHtml,mapSvg,NEAR_KM};
})(typeof window!=='undefined'?window:globalThis);
