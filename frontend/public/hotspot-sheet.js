/* Phase 4: phone bottom sheet for a tapped hotspot. Same content as the
 * desktop popup (hotspotPopupHtml), with the place as a large title and a
 * facts grid with copyable coordinates (lat/lon and UTM). */
(function(root){
  'use strict';
  // WGS84 -> UTM (Snyder 1987, Transverse Mercator series). Accurate to well
  // under a metre inside a zone, enough to read a position off a field map.
  function utm(lat,lon){
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<-80||lat>84)return null;
    const a=6378137,f=1/298.257223563,k0=0.9996,e2=f*(2-f),ep2=e2/(1-e2);
    const zone=Math.floor((lon+180)/6)+1,lon0=((zone-1)*6-180+3)*Math.PI/180;
    const phi=lat*Math.PI/180,lam=lon*Math.PI/180;
    const N=a/Math.sqrt(1-e2*Math.sin(phi)**2),T=Math.tan(phi)**2,C=ep2*Math.cos(phi)**2,A=Math.cos(phi)*(lam-lon0);
    const M=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*phi-(3*e2/8+3*e2**2/32+45*e2**3/1024)*Math.sin(2*phi)
      +(15*e2**2/256+45*e2**3/1024)*Math.sin(4*phi)-(35*e2**3/3072)*Math.sin(6*phi));
    const E=k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T**2+72*C-58*ep2)*A**5/120)+500000;
    let Nn=k0*(M+N*Math.tan(phi)*(A**2/2+(5-T+9*C+4*C**2)*A**4/24+(61-58*T+T**2+600*C-330*ep2)*A**6/720));
    if(lat<0)Nn+=10000000;
    return {zone,hemisphere:lat<0?'S':'N',easting:Math.round(E),northing:Math.round(Nn)};
  }
  const fmt=n=>Number(n).toLocaleString('en-US');
  // FIRMS satellite codes to readable names (VIIRS: N = Suomi NPP, N20 = NOAA-20, N21 = NOAA-21; MODIS: T = Terra, A = Aqua).
  const SAT={N:'Suomi NPP (VIIRS)',N20:'NOAA-20 (VIIRS)',N21:'NOAA-21 (VIIRS)',S:'Suomi NPP (VIIRS)',SNPP:'Suomi NPP (VIIRS)',T:'Terra (MODIS)',A:'Aqua (MODIS)',TERRA:'Terra (MODIS)',AQUA:'Aqua (MODIS)'};
  const satName=v=>SAT[String(v||'').trim().toUpperCase()]||v||'ไม่ระบุ';
  const esc=v=>root.CmeEvidence?root.CmeEvidence.escapeHtml(v):String(v);
  let sheet,body,title,lastFocus=null,onClose=null;
  function ensure(){
    if(sheet)return;
    sheet=document.createElement('section');
    sheet.className='hs-sheet';sheet.id='hotspotSheet';sheet.hidden=true;
    sheet.setAttribute('role','dialog');sheet.setAttribute('aria-modal','false');sheet.setAttribute('aria-labelledby','hotspotSheetTitle');sheet.tabIndex=-1;
    sheet.innerHTML=`<button type="button" class="hs-sheet-handle" aria-label="ลากขึ้นเพื่อขยาย ลากลงเพื่อย่อ"><span></span></button>
      <header class="hs-sheet-head"><div><p class="hs-sheet-kicker">จุดความร้อนจากดาวเทียม</p><h2 id="hotspotSheetTitle"></h2></div>
      <button type="button" class="hs-sheet-close" aria-label="ปิดรายละเอียด">✕</button></header>
      <div class="hs-sheet-body"></div>`;
    document.body.appendChild(sheet);
    body=sheet.querySelector('.hs-sheet-body');title=sheet.querySelector('#hotspotSheetTitle');
    sheet.querySelector('.hs-sheet-close').onclick=close;
    drag(sheet);
    sheet.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close();}});
    sheet.addEventListener('click',e=>{
      const b=e.target.closest('[data-copy]');if(!b)return;
      const text=b.dataset.copy,done=()=>{b.dataset.copied='1';b.textContent='คัดลอกแล้ว';setTimeout(()=>{b.textContent='คัดลอก';delete b.dataset.copied;},1600);};
      if(navigator.clipboard?.writeText)navigator.clipboard.writeText(text).then(done,()=>{});else done();
    });
  }
  // Drag the handle or title row like a window: up to expand, down to shrink.
  // Dragging down stops at the title row (✕ stays reachable); only ✕ closes.
  const vh=()=>root.innerHeight||800;
  function stops(){
    const head=sheet.querySelector('.hs-sheet-head'),handle=sheet.querySelector('.hs-sheet-handle');
    const peek=Math.ceil((handle?.offsetHeight||24)+(head?.offsetHeight||56)+18);
    return {peek,half:Math.min(vh()*0.5,440),full:Math.round(vh()*0.86)};
  }
  function setStop(name){
    if(!sheet)return;const st=stops();sheet.dataset.stop=name;
    sheet.style.height=st[name]+'px';sheet.style.maxHeight='none';
    sheet.classList.toggle('peek',name==='peek');
  }
  function drag(el){
    const grips=[el.querySelector('.hs-sheet-handle'),el.querySelector('.hs-sheet-head')];
    let y0=0,h0=0,moved=false,active=false,lastY=0,lastT=0,v=0;
    const down=e=>{
      if(e.target.closest('.hs-sheet-close'))return;
      active=true;moved=false;y0=lastY=e.clientY;lastT=e.timeStamp;h0=el.getBoundingClientRect().height;v=0;
      el.classList.add('dragging');e.currentTarget.setPointerCapture?.(e.pointerId);
    };
    const move=e=>{
      if(!active)return;const dy=e.clientY-y0;if(Math.abs(dy)>6)moved=true;
      const st=stops();el.style.maxHeight='none';el.style.height=Math.max(st.peek,Math.min(st.full,h0-dy))+'px';
      const dt=Math.max(1,e.timeStamp-lastT);v=(e.clientY-lastY)/dt;lastY=e.clientY;lastT=e.timeStamp;
    };
    const up=e=>{
      if(!active)return;active=false;el.classList.remove('dragging');
      if(!moved){if(e.currentTarget.classList.contains('hs-sheet-handle'))setStop(el.dataset.stop==='full'?'half':'full');return;}
      const st=stops(),h=el.getBoundingClientRect().height;
      // A quick flick decides the direction; otherwise snap to the nearest stop.
      if(v>0.6)setStop(h>st.half?'half':'peek');
      else if(v<-0.6)setStop(h<st.half?'half':'full');
      else setStop(['peek','half','full'].reduce((a,b)=>Math.abs(st[b]-h)<Math.abs(st[a]-h)?b:a));
    };
    for(const g of grips){if(!g)continue;g.addEventListener('pointerdown',down);g.addEventListener('pointermove',move);g.addEventListener('pointerup',up);g.addEventListener('pointercancel',up);}
  }
  function factsHtml(h){
    const u=utm(Number(h.lat),Number(h.lon));
    const ll=`${Number(h.lat).toFixed(5)}, ${Number(h.lon).toFixed(5)}`;
    const utmText=u?`${u.zone}${u.hemisphere} E ${fmt(u.easting)} N ${fmt(u.northing)}`:'';
    const when=h.detected_at?new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(Date.parse(h.detected_at))+' น.':'ไม่ทราบเวลา';
    return `<dl class="hs-facts">
      <div><dt>เวลาที่ตรวจพบ</dt><dd>${esc(when)}</dd></div>
      <div><dt>ดาวเทียม</dt><dd>${esc(satName(h.sat))}</dd></div>
      <div><dt>พิกัด</dt><dd>${esc(ll)} <button type="button" class="hs-copy" data-copy="${esc(ll)}">คัดลอก</button></dd></div>
      ${u?`<div><dt>UTM</dt><dd>${esc(utmText)} <button type="button" class="hs-copy" data-copy="${esc(utmText)}">คัดลอก</button></dd></div>`:''}
    </dl>`;
  }
  // Generic panel: same sheet for districts and other map places.
  function openPanel({kicker='',title:t='',html='',onClose:cb}={}){
    ensure();
    if(onClose&&onClose!==cb)onClose();
    onClose=cb||null;
    lastFocus=document.activeElement;
    sheet.querySelector('.hs-sheet-kicker').textContent=kicker;
    title.textContent=t;
    body.innerHTML=html;
    sheet.hidden=false;document.body.classList.add('hs-sheet-open');setStop('half');sheet.scrollTop=0;
    requestAnimationFrame(()=>sheet.focus({preventScroll:true}));
  }
  function open(h,html,opts={}){
    const place=[h.subdistrict||h.tambon?'ต.'+(h.subdistrict||h.tambon):'',h.district?'อ.'+h.district:''].filter(Boolean).join(' ');
    openPanel({kicker:'จุดความร้อนจากดาวเทียม',title:place||'จุดความร้อน',html:html+factsHtml(h),onClose:opts.onClose});
  }
  function close(){
    if(!sheet||sheet.hidden)return;
    sheet.hidden=true;document.body.classList.remove('hs-sheet-open');body.replaceChildren();
    const cb=onClose;onClose=null;cb?.();
    if(lastFocus?.isConnected)lastFocus.focus({preventScroll:true});
  }
  root.CmeHotspotSheet={open,openPanel,close,utm,satName,setStop,isOpen:()=>!!sheet&&!sheet.hidden};
})(window);
