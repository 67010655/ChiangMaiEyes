/* Approved representative workspace. Private data comes only from the authenticated API. */
(function(root){
  'use strict';
  const statusNames={pending:'รอตรวจสอบ',confirmed:'ยืนยันเหตุ',coordinating:'กำลังประสาน',controlled:'ควบคุมได้',closed:'ปิดเหตุ',cancelled:'ยกเลิกเหตุ',approved:'อนุมัติแล้ว',rejected:'ไม่อนุมัติ',revoked:'ยกเลิกสิทธิ์',invited:'รอรับคำขอ',accepted:'ร่วมประสาน',declined:'ไม่รับคำขอ'};
  const transitions={pending:['confirmed','cancelled'],confirmed:['coordinating','controlled','cancelled'],coordinating:['controlled','cancelled'],controlled:['coordinating','closed'],closed:['pending'],cancelled:['pending']};
  const eventNames={created:'แจ้งเหตุ',expired:'ปิดอัตโนมัติ',status:'เปลี่ยนสถานะ',note:'บันทึกเพิ่มเติม',photo:'เพิ่มภาพประกอบ',field_check:'เพิ่มผลตรวจภาคสนาม',merged:'เชื่อมกับเหตุหลัก',linked_report:'เชื่อมรายงานเพิ่มเติม',coordination:'รับเป็นผู้ประสาน',partner_invited:'ขอร่วมประสาน',partner_accepted:'รับร่วมประสาน',partner_declined:'ไม่รับคำขอ',publication:'เปลี่ยนการเผยแพร่'};
  let context,container,body,miniMap,loading=null,sequence=0;
  let photoUrls=[],renderVersion=0;
  const checkRequests=new Map(),detailsOpen=new Map();
  const fieldChecks=new Map();
  const formDrafts=new Map();
  const state={tab:'forest',me:null,session:null,catalog:[],incidents:[],publicIncidents:[],detail:null,forestId:'',error:'',notice:'',busy:false,ready:null,emailMode:'unavailable',create:false,scope:'active',draft:null};
  const E=()=>root.CmeEvidence;
  const pinsChanged=()=>{try{root.dispatchEvent(new CustomEvent('cme:pins-changed'));}catch{}};
  const esc=value=>E().escapeHtml(value);
  const date=value=>E().stamp(value);
  const OPEN_WORDS={pending:'เปิดอยู่',confirmed:'เปิดอยู่',coordinating:'เปิดอยู่',controlled:'เปิดอยู่',closed:'จบงานแล้ว',cancelled:'ไม่ใช่ไฟ'};
  const badge=status=>`<span class="cw-status ${esc(status)}">${esc(OPEN_WORDS[status]||statusNames[status]||status)}</span>`;
  const ago=value=>{const t=Date.parse(value);if(!Number.isFinite(t))return '';const m=Math.max(0,Math.round((Date.now()-t)/60000));return m<1?'เมื่อสักครู่':m<60?m+' นาทีที่แล้ว':m<1440?Math.round(m/60)+' ชม.ที่แล้ว':Math.round(m/1440)+' วันที่แล้ว';};
  const nextStep={pending:'หมุดยังอยู่บนแผนที่ ผู้แจ้งกด "จบงาน" เมื่อไฟดับ',confirmed:'หมุดยังอยู่บนแผนที่ ผู้แจ้งกด "จบงาน" เมื่อไฟดับ',coordinating:'หมุดยังอยู่บนแผนที่ ผู้แจ้งกด "จบงาน" เมื่อไฟดับ',controlled:'หมุดยังอยู่บนแผนที่ ผู้แจ้งกด "จบงาน" เมื่อไฟดับ',closed:'จบงานแล้ว เก็บไว้ในประวัติ',cancelled:'บันทึกว่าไม่ใช่ไฟ เก็บไว้ในประวัติ'};
  const STEPS=['pending','confirmed','coordinating','controlled','closed'];
  const stepper=status=>{if(status==='cancelled')return '<div class="cw-steps cancelled"><span class="on">ยกเลิกเหตุ</span></div>';const at=STEPS.indexOf(status);return `<ol class="cw-steps" aria-label="ขั้นของเหตุ">${STEPS.map((st,n)=>`<li class="${n<at?'done':n===at?'on':''}"${n===at?' aria-current="step"':''}><span>${esc(statusNames[st])}</span></li>`).join('')}</ol>`;};
  const obsLabel=o=>o==='fire'?'🔥 เห็นเปลวไฟ':o==='smoke'?'💨 เห็นควัน':'';
  const button=(label,action,extra='',primary=false)=>`<button type="button" class="cw-btn${primary?' primary':''}" data-cw="${action}" ${extra}>${label}</button>`;
  const options=(forests,selected='')=>forests.map(f=>{const duplicated=state.catalog.filter(x=>x.name===f.name&&x.amphoe===f.amphoe).length>1;return `<option value="${esc(f.forest_id)}" ${f.forest_id===selected?'selected':''}>${esc(f.name)} · ${esc(f.amphoe)}${duplicated?' · '+esc(f.tambon||'')+' · '+esc(f.forest_id):''}</option>`;}).join('');
  const isOpen=()=>container&&container.classList.contains('open');
  const allowedForests=()=>state.me?.is_admin?state.catalog:state.catalog.filter(f=>state.me?.memberships.some(m=>m.status==='approved'&&m.forest_id===f.forest_id));
  const forest=()=>state.catalog.find(f=>f.forest_id===state.forestId);
  // Forests this person represents. An admin with none gets an overview, not "my forest".
  const myForests=()=>state.catalog.filter(f=>state.me?.memberships.some(m=>m.status==='approved'&&m.forest_id===f.forest_id));
  const adminOverview=()=>!!state.me?.is_admin&&!myForests().length;
  const pendingRequests=()=>(state.reviewQueue||[]).filter(m=>m.status==='pending');
  const draftKey=()=>state.session?'cme-incident-draft-v1/'+state.session.user.id:null;
  function localTime(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()).replace(' ','T');}
  function newDraft(point={}){return {id:root.crypto.randomUUID(),started_at:new Date().toISOString(),forest_id:state.forestId,observation:'smoke',observed_local:localTime(),latitude:point.lat??'',longitude:point.lon??'',description:''};}
  function readDraft(){try{return JSON.parse(root.localStorage.getItem(draftKey()))||null;}catch{return null;}}
  function saveDraft(){const key=draftKey();if(!key||!state.draft)return;try{root.localStorage.setItem(key,JSON.stringify({...state.draft,saved_at:new Date().toISOString()}));const text=document.getElementById('cwDraftSaved');if(text)text.textContent='ร่างเก็บในเครื่องนี้แล้ว · '+date(new Date().toISOString());}catch{const text=document.getElementById('cwDraftSaved');if(text)text.textContent='เก็บร่างในเครื่องไม่ได้ โปรดเปิดหน้านี้ไว้ก่อนส่ง';}}
  // A draft older than 3 h is not reused silently: the form starts fresh and
  // offers the old one (its time and place are usually wrong by then).
  function startDraft(point){
    const old=state.draft||readDraft(),at=Date.parse(old?.saved_at||old?.started_at||'');
    if(old&&Date.now()-at<3*36e5){state.draft=old;state.oldDraft=null;}
    else{state.oldDraft=old&&(old.description||old.latitude)?old:null;state.draft=newDraft(point);}
    if(point){state.draft.latitude=point.lat;state.draft.longitude=point.lon;}
  }
  function dropDraft(){try{root.localStorage.removeItem(draftKey());}catch{}state.draft=null;}
  async function api(path,{method='GET',data,raw,publicOnly=false,binary=false}={}){
    if(root.navigator.onLine===false)throw new Error('ขณะนี้ออฟไลน์ ยังโหลดข้อมูลหรือยืนยันผลการส่งไม่ได้ กรุณาเชื่อมต่ออินเทอร์เน็ตแล้วลองอีกครั้ง');
    const headers={},uid=context.user()?.id;
    if(!publicOnly){const session=await context.session();if(!session)throw new Error('เข้าสู่ระบบก่อนใช้พื้นที่ชุมชน');headers.Authorization='Bearer '+session.access_token;}
    if(data)headers['Content-Type']='application/json';
    if(raw)headers['Content-Type']='application/octet-stream';
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),20000);
    try{
      const response=await fetch(context.apiBase+'/api/community'+path,{method,headers,body:raw||(data?JSON.stringify(data):undefined),signal:abort.signal,cache:'no-store'});
      const result=binary&&response.ok?await response.blob():await response.json();
      if(!publicOnly&&uid!==context.user()?.id)throw new Error('บัญชีเปลี่ยนระหว่างโหลดข้อมูล กรุณาเปิดพื้นที่อีกครั้ง');
      if(!response.ok){const error=new Error(typeof result.detail==='string'?result.detail:Array.isArray(result.detail)?result.detail.slice(0,2).map(d=>String(d.msg||'ตรวจข้อมูลที่กรอก').replace(/^Value error, /,'')).join(' · '):'ตรวจข้อมูลที่กรอกและลองใหม่');error.status=response.status;throw error;}
      return result;
    }catch(error){if(error.name==='AbortError')throw new Error('การเชื่อมต่อใช้เวลานาน ยังไม่ได้ยืนยันผลการส่ง กรุณาลองอีกครั้ง');throw error;}
    finally{clearTimeout(timer);}
  }
  function destroyMap(){if(miniMap){miniMap.remove();miniMap=null;}}
  function clearPhotos(){renderVersion++;photoUrls.forEach(url=>URL.revokeObjectURL(url));photoUrls=[];}
  async function loadPhotos(){
    const version=renderVersion,photos=state.detail?.photos||[],session=await context.session();if(!session)return;
    for(const p of photos){
      try{
        const response=await fetch(context.apiBase+'/api/community/photos/'+p.id,{headers:{Authorization:'Bearer '+session.access_token},cache:'no-store',signal:AbortSignal.timeout(20000)});
        if(!response.ok)throw new Error();const blob=await response.blob();if(version!==renderVersion)return;
        const url=URL.createObjectURL(blob);photoUrls.push(url);const host=document.getElementById('cwPhoto-'+p.id);
        if(host){host.replaceChildren();const img=document.createElement('img');img.src=url;img.alt='ภาพประกอบเหตุ · '+date(p.created_at);img.loading='lazy';host.append(img);}
      }catch{if(version===renderVersion){const host=document.getElementById('cwPhoto-'+p.id);if(host)host.textContent='โหลดรูปไม่ได้ กดโหลดอีกครั้งเพื่อทดลองใหม่';}}
    }
  }
  function photosView(d){return `<h3>ภาพประกอบเหตุ</h3><p class="cw-help">เห็นได้เฉพาะผู้มีสิทธิ์ดูเหตุนี้ รูปไม่เผยแพร่พร้อมสรุปสาธารณะ</p><div class="cw-photos">${(d.photos||[]).map(p=>`<figure><div id="cwPhoto-${esc(p.id)}" class="cw-photo">กำลังโหลดรูป…</div><figcaption>แนบ ${date(p.created_at)}</figcaption></figure>`).join('')||'<p class="cw-help">ยังไม่มีรูปแนบ</p>'}</div>${d.can_note?'<form class="cw-form" id="cwPhotoForm"><label>เพิ่มภาพประกอบ<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label><p class="cw-help">JPEG / PNG / WebP ไม่เกิน 4 MB และ 12 ล้านพิกเซล · สูงสุด 10 รูปต่อเหตุ · ลบข้อมูล EXIF ก่อนเก็บ</p><button class="cw-btn">แนบรูป</button></form>':''}`;}
  function renderMap(selected){
    const host=document.getElementById('cwMap');
    if(!host||!selected?.boundary||!context.leaflet)return;
    const L=context.leaflet;
    // This map is rebuilt when changing workspace tabs. Leaflet's delayed
    // zoom-transition callback can outlive remove() and access a deleted pane.
    miniMap=L.map(host,{scrollWheelZoom:false,zoomAnimation:false}).setView([selected.latitude,selected.longitude],12);
    miniMap.on('popupopen',event=>root.CmeCoordination?.popupOpened(event.popup));
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri',maxZoom:18}).addTo(miniMap);
    const geometry=L.geoJSON(selected.boundary,{style:{color:'#29965a',weight:2,fillOpacity:.12}}).addTo(miniMap);
    if(geometry.getBounds().isValid())miniMap.fitBounds(geometry.getBounds(),{padding:[20,20],maxZoom:15,animate:false});
    const dash=context.dashboard();
    if(dash?.data_quality?.hotspots&&!dash.data_quality.hotspots.is_stale&&dash.data_quality.hotspots.source_mode!=='UNAVAILABLE'){
      const items=(dash.hotspots?.items||[]).map(h=>({...h,lat:h.latitude,lon:h.longitude}));
      const inside=E().filterHotspots(items,{forest:selected}),across=root.CmeCoordination?.nearbyCrossDistrict(items,selected)||[];
      const protectedPoints=(root.CmeProtectedAreas?.nearby(items,selected)||[]).map(r=>r.hotspot);
      const points=new Map([...inside,...across,...protectedPoints].map(h=>[h.id||h.lat+','+h.lon+','+h.detected_at,h]));
      [...points.values()].forEach(h=>L.circleMarker([h.lat,h.lon],{radius:6,color:'#b9480b',fillColor:'#ed8d3c',fillOpacity:.9,weight:1}).bindPopup(()=>`${E().observationTimeHtml(h.detected_at,'ดาวเทียม')}${root.CmeLandContext?.summary(h)||''}${root.CmeCoordination?.html(h.lat,h.lon,{myForestId:selected.forest_id})||''}<details class="land-context-details"><summary>รายละเอียดเพิ่มเติม</summary>${root.CmeLandContext?.details(h)||''}</details>`,{maxWidth:320,maxHeight:300}).addTo(miniMap));
    }
  }
  function tabs(){
    if(!state.session)return '';
    const n=pendingRequests().length;
    const entries=[['forest',adminOverview()?'ภาพรวม':'ป่าของฉัน'],['incidents','เหตุทั้งหมด']];
    if(state.me?.is_admin)entries.push(['review','ตรวจคำขอ'+(n?`<span class="cw-tab-n">${n}</span>`:'')]);
    entries.push(['preferences','การแจ้งเตือน']);
    if(state.tab==='practice')entries.push(['practice','ซ้อมใช้งาน']);
    return `<div class="cw-tabs" role="tablist" aria-label="พื้นที่ชุมชน">${entries.map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" data-cw="tab" data-tab="${id}">${label}</button>`).join('')}</div>`;
  }
  // Everyone can look up a forest; the representative sign-in sits below.
  function publicView(){
    const P=root.CmeForestPublic;if(!P)return loginView();
    const id=state.publicForest??P.recall();state.publicForest=id;
    return P.html({forests:state.catalog,dashboard:context.dashboard(),selectedId:id,hasIncidents:!!state.publicIncidents?.length,incidentsHtml:state.publicIncidents?.length?incidentRows(state.publicIncidents,true):''});
  }
  function loginView(){return `<div class="cw-empty"><h2>พื้นที่สำหรับตัวแทนป่าชุมชน</h2><p>เข้าสู่ระบบเพื่อขอสิทธิ์พื้นที่ เมื่อผู้ดูแลยืนยันแล้ว คุณจะบันทึกเหตุ ร่วมประสานงาน และตั้งค่าอีเมลของป่าที่รับผิดชอบได้</p><p>ยังไม่มีบัญชี? เลือกสมัครสมาชิกในหน้าบัญชี แล้วจึงขอสิทธิ์พื้นที่</p>${button('เข้าสู่ระบบ / สมัครสมาชิก','signin','',true)} ${button('ดูเหตุที่เผยแพร่','public')}${E().fireHelpHtml()}</div>`;}
  function membershipView(){
    const requests=state.me?.memberships||[];
    return `<section class="cw-section"><h2>ขอสิทธิ์ตัวแทนป่าชุมชน</h2><p class="cw-help">เลือกป่าจากขอบเขตที่ได้รับจาก RECOFTC และระบุหน้าที่หรือช่องทางให้ผู้ดูแลตรวจสอบ การเลือกชื่อป่ายังไม่ถือว่าได้รับสิทธิ์</p>
      <form class="cw-form" id="cwMembershipForm"><label>ค้นหาชื่อป่าหรืออำเภอ<input type="search" id="cwForestSearch" placeholder="พิมพ์ชื่อป่าหรืออำเภอ" autocomplete="off"></label><label>ป่าที่ขอสิทธิ์<select id="cwRequestForest" required data-required-message="เลือกป่าชุมชนก่อน">${options(state.catalog)}</select></label><label>หน้าที่และข้อมูลสำหรับตรวจสอบ<textarea name="note" maxlength="1000" required placeholder="เช่น หน้าที่ในชุมชน และช่องทางตรวจสอบกับหน่วยงาน"></textarea></label><button class="cw-btn primary">ส่งคำขอให้ผู้ดูแล</button></form>
      ${requests.length?`<h3>คำขอของคุณ</h3>${requests.map(m=>`<div class="cw-row"><div><h3>${esc(m.name)}</h3><p>${date(m.created_at)}</p>${m.review_note?`<p>${esc(m.review_note)}</p>`:''}</div>${badge(m.status)}</div>`).join('')}`:''}</section>`;
  }
  function summary(selected){
    if(selected.boundary_quality==='needs_review')return `<p class="cw-help" role="status"><b>ขอบเขตนี้ต้องตรวจทบทวน</b><br>${esc(selected.boundary_note)} · ยังไม่สรุปยอดภายในขอบเขตที่มีส่วนผิดปกติ</p>`;
    const dash=context.dashboard(),q=dash?.data_quality||{};
    const ready=k=>q[k]&&!q[k].is_stale&&q[k].source_mode!=='UNAVAILABLE';
    const rows=ready('hotspots')?E().filterHotspots((dash.hotspots?.items||[]).map(h=>({...h,lat:h.latitude,lon:h.longitude})),{forest:selected}):null;
    const stations=ready('pm25')?(dash.pm25?.stations||[]).filter(s=>Number.isFinite(s.pm25)&&E().inBoundary(s.latitude,s.longitude,selected.boundary)):[];
    const pm=stations.length?Math.round(stations.reduce((sum,s)=>sum+s.pm25,0)/stations.length):null;
    const wind=ready('weather')?dash.weather:null;
    const directions=['เหนือ','ตะวันออกเฉียงเหนือ','ตะวันออก','ตะวันออกเฉียงใต้','ใต้','ตะวันตกเฉียงใต้','ตะวันตก','ตะวันตกเฉียงเหนือ'];
    const windTo=wind?.wind_direction_deg!=null?directions[Math.round(((wind.wind_direction_deg+180)%360)/45)%8]:null;
    return `<div class="cw-summary"><div><small>จุดความร้อนในขอบเขตป่า</small><strong>${rows===null?'รอข้อมูล':rows.length+' จุด'}</strong><small>24 ชม. · ${date(q.hotspots?.latest_update)}</small></div><div><small>ฝุ่นจากสถานีในขอบเขตป่า</small><strong>${pm===null?'ไม่มีสถานีที่ใช้ได้':pm+' µg/m³'}</strong><small>${stations.length?'ค่ารอบปัจจุบัน · '+date(q.pm25?.latest_update):'ไม่ใช้ค่าเฉลี่ยจังหวัดแทน'}</small></div><div><small>ลมอ้างอิงระดับจังหวัด</small><strong>${wind?Math.round(wind.wind_speed_kmh)+' กม./ชม.':'รอข้อมูล'}</strong><small>${windTo?'พัดไป'+windTo+' · ':''}${wind?esc(wind.source)+' · '+date(q.weather?.latest_update):'ยังไม่มีข้อมูลที่ใช้ได้'}</small></div></div>`;
  }
  function incidentRows(rows,publicView=false){
    if(!rows.length)return `<div class="cw-empty cw-empty-card"><span class="cw-empty-ic" aria-hidden="true">🌿</span><h3>${publicView?'ยังไม่มีเหตุที่อนุมัติให้เผยแพร่':'ยังไม่มีเหตุในรายการนี้'}</h3><p>การไม่มีรายการในระบบไม่ได้ยืนยันว่าไม่มีไฟในพื้นที่</p></div>`;
    return `<div class="cw-incs">${rows.map(i=>{
      const name=i.forest_name||state.catalog.find(f=>f.forest_id===i.forest_id)?.name||'ป่าชุมชน';
      const who=publicView?'':i.coordinator_id?`<p class="cw-inc-who">👤 คนตามเรื่องนี้: <b>${esc(i.coordinator_name||'ตัวแทนที่รับเรื่อง')}</b></p>`:'';
      return `<article class="cw-inc s-${esc(i.status)}"><div class="cw-inc-main">
        <div class="cw-inc-top">${badge(i.status)}${obsLabel(i.observation)?`<span class="cw-inc-obs">${obsLabel(i.observation)}</span>`:''}</div>
        <h3>${esc(name)}</h3>
        <p class="cw-inc-meta">พบเหตุ ${date(i.observed_at)} <span>· ${esc(ago(i.observed_at))}</span> · อัปเดต ${date(i.updated_at)}</p>
        ${who}${publicView?'':`<p class="cw-inc-next">ต่อไป: ${esc(nextStep[i.status]||'อ่านประวัติเพื่อติดตาม')}</p>`}
      </div>${publicView?'':button('เปิดดูเหตุ →','detail',`data-id="${esc(i.id)}"`)}</article>`;}).join('')}</div>`;
  }
  function createForm(){
    const d=state.draft||newDraft(),allowed=state.me?.is_admin&&!adminOverview()?myForests():allowedForests();state.draft=d;
    const chosen=allowed.find(f=>f.forest_id===d.forest_id);
    const select=`<select name="forest_id" required data-required-message="เลือกป่าชุมชนก่อน">${chosen?'':'<option value="">เลือกป่าที่จะบันทึก</option>'}${options(allowed,d.forest_id)}</select>`;
    const forestField=allowed.length===1?`<input type="hidden" name="forest_id" value="${esc(allowed[0].forest_id)}"><p class="cw-for">บันทึกให้ <b>${esc(allowed[0].name)}</b></p>`
      :chosen?`<p class="cw-for">บันทึกให้ <b>${esc(chosen.name)}</b></p><details class="cw-change"><summary>เปลี่ยนป่า</summary><label>ป่าที่จะบันทึก${select}</label></details>`
      :`<label>ป่าที่จะบันทึก${select}</label>`;
    const old=state.oldDraft?`<div class="cw-alert" role="status">มีร่างที่ยังไม่ได้ส่งจาก ${date(state.oldDraft.saved_at||state.oldDraft.started_at)} <div class="cw-actions">${button('ใช้ร่างนั้นต่อ','old-draft-use')}${button('ทิ้งร่างนั้น','old-draft-drop')}</div></div>`:'';
    return `<section class="cw-section"><h2>บันทึกเหตุ</h2><p class="cw-help">ใส่สิ่งที่เห็น เวลา และตำแหน่ง แล้วส่งได้เลย รูปและผลการดับไฟเพิ่มทีหลังในหน้าเหตุนั้น</p>${old}<form class="cw-form" id="cwIncidentForm">
      ${forestField}
      <label>สิ่งที่พบ<select name="observation"><option value="smoke" ${d.observation==='smoke'?'selected':''}>เห็นควัน</option><option value="fire" ${d.observation==='fire'?'selected':''}>เห็นเปลวไฟ</option></select></label>
      <label>เวลาที่พบ (เวลาประเทศไทย)<input name="observed_local" type="datetime-local" value="${esc(d.observed_local)}" required></label>
      <p class="cw-label">ตำแหน่งที่พบ</p>
      <div class="cw-actions">${button('📍 ใช้ตำแหน่งฉันตอนนี้','gps','',!d.latitude)} ${button('เลือกบนแผนที่','pick')}</div>
      <div class="cw-fields"><label>ละติจูด<input name="latitude" type="number" step="any" min="-90" max="90" value="${esc(d.latitude)}" required></label><label>ลองจิจูด<input name="longitude" type="number" step="any" min="-180" max="180" value="${esc(d.longitude)}" required></label></div>
      <label>เล่าสั้นๆ ว่าเห็นอะไร (เติมภายหลังได้)<textarea name="description" maxlength="2000" placeholder="เช่น ไฟกำลังไหม้ใกล้ลำห้วย มีควันหนา">${esc(d.description)}</textarea></label>
      <label>เบอร์โทรให้ตัวแทนป่าอื่นติดต่อ (ไม่บังคับ)<input name="contact_phone" type="tel" inputmode="tel" maxlength="20" placeholder="เช่น 081-234-5678" value="${esc(d.contact_phone||'')}"></label>
      <div class="cw-alert warn" id="cwNearPins" role="status" hidden></div>
      <div class="cw-consent"><b>👁 ก่อนกดส่ง</b> จะมีหมุดตาบนแผนที่ ตัวแทนป่าที่ได้รับอนุมัติทุกคนจะเห็น <b>ชื่อของคุณ ชื่อป่า ตำแหน่ง สิ่งที่เล่า และเบอร์ที่ใส่</b> ระบบจะส่ง LINE แจ้งป่าที่อยู่ห่างไม่เกิน 5 กม. หมุดหายเมื่อคุณกด "จบงาน" หรือครบ 3 วัน (ส่งได้ไม่เกิน 3 หมุดต่อวัน) คนทั่วไปไม่เห็น</div>
      <p class="cw-help" id="cwDraftSaved">${d.saved_at?'ร่างเก็บในเครื่องนี้ · '+date(d.saved_at):'ร่างจะเก็บในเครื่องนี้ระหว่างกรอก ยังไม่ใช่รายงานที่ส่งแล้ว'}</p>
      <div class="cw-actions"><button class="cw-btn primary">ส่งบันทึกเหตุ</button>${button('ยกเลิก','cancel-create')}</div></form></section>`;
  }
  // Before sending: warn when someone already pinned a fire close to this point in the last day.
  async function loadNearPins(){
    if(state.nearPins!==undefined)return;
    state.nearPins=[];
    try{state.nearPins=await api('/pins');}catch{state.nearPins=[];}
    updateNearPins();
  }
  function updateNearPins(){
    const box=document.getElementById('cwNearPins'),form=document.getElementById('cwIncidentForm');
    if(!box||!form)return;
    const lat=Number(form.elements.latitude.value),lon=Number(form.elements.longitude.value);
    if(form.elements.latitude.value===''||form.elements.longitude.value===''||!Number.isFinite(lat)||!Number.isFinite(lon)||!state.nearPins?.length){box.hidden=true;return;}
    const now=Date.now();
    const near=state.nearPins.filter(p=>now-Date.parse(p.created_at)<864e5&&p.id!==state.draft?.id)
      .map(p=>({p,km:E().distanceKm({lat,lon},{lat:p.latitude,lon:p.longitude})})).filter(r=>r.km<=2).sort((a,b)=>a.km-b.km).slice(0,3);
    if(!near.length){box.hidden=true;return;}
    box.hidden=false;
    box.innerHTML='⚠️ <b>มีหมุดใกล้จุดนี้แล้ว</b><ul>'+near.map(({p,km})=>`<li>${esc(p.forest_name)} ห่างประมาณ ${km.toFixed(1)} กม. · แจ้งโดย ${esc(p.reporter_name)} ${esc(ago(p.created_at))}${p.contact_phone?' · ☎️ '+esc(p.contact_phone):''}</li>`).join('')+'</ul><small>ถ้าเป็นไฟเดียวกัน ลองติดต่อผู้แจ้งก่อน จะได้ไม่แจ้งซ้ำ ถ้าเป็นคนละจุด ส่งต่อได้เลย</small>';
  }
  function forestView(){
    if(state.create)return createForm();
    if(adminOverview())return adminView();
    const allowed=state.me?.is_admin?myForests():allowedForests();
    if(!allowed.length)return membershipView();
    const selected=forest()||allowed[0];state.forestId=selected.forest_id;
    const related=state.incidents.filter(i=>i.forest_id===selected.forest_id||i.partner_forest_ids?.includes(selected.forest_id));
    if(root.CmeForestPublic)return repForestView(selected,allowed,related);
    return `<div class="cw-layout"><section class="cw-section"><label class="cw-help" for="cwActiveForest">${state.me.is_admin?'เลือกพื้นที่ดูแลระบบ':'พื้นที่ที่ได้รับอนุมัติ'}</label><select class="cw-select" id="cwActiveForest">${options(allowed,selected.forest_id)}</select>${summary(selected)}${protectedNearbyView(selected)}${crossDistrictView(selected)}<div id="cwMap" class="cw-map" aria-label="ขอบเขตป่าที่เลือกและจุดความร้อน 24 ชั่วโมง"></div><p class="cw-help">ขอบเขตจาก RECOFTC · ดาวเทียมยังไม่ยืนยันเหตุภาคสนาม · ลมอ้างอิงจังหวัดยังไม่ใช่ลมที่วัดในป่าแห่งนี้</p><div class="cw-actions">${button('แจ้งสิ่งที่พบ','create','',true)}${button('ส่งออกรายงานพื้นที่นี้','export')}</div></section>
      <section class="cw-section"><h2>งานที่ต้องดู</h2>${incidentRows(related.filter(i=>!['closed','cancelled'].includes(i.status)))}<div class="cw-actions">${button('ดูประวัติเหตุทั้งหมด','all-incidents')}</div><h3>ช่องทางประสานหน่วยงาน</h3><p class="cw-help"><a href="tel:052081758">052-081758</a> สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่)<br><a href="https://forestinfo.forest.go.th/telephone_region.aspx" target="_blank" rel="noopener">บัญชีโทรศัพท์กรมป่าไม้</a> · ตรวจ 9 ต.ค. 2026<br>เป็นช่องทางสอบถามผู้ประสาน ยังไม่มีรายชื่อหัวหน้าป่าแห่งนี้ที่ยืนยันแล้ว</p>${state.me.is_admin?'':`<details><summary>ดูแลป่าอื่นด้วย? ส่งคำขอ (รอผู้ดูแลอนุมัติ)</summary>${membershipView()}</details>`}</section></div>`;
  }
  // What to do now, by the forest's 24 h situation. Plain steps, no score.
  function todoHtml(sit){
    const toward=sit.wind?.toward===true;
    const steps={
      alert:['ดูตำแหน่งจุดบนแผนที่ด้านล่างว่าอยู่ตรงไหนของป่า','ถ้าเห็นไฟจริง โทร <a href="tel:1362">1362</a> และแจ้งหน่วยงานในพื้นที่ (ดู "ใครดูแลพื้นที่นี้")','อย่าเข้าพื้นที่คนเดียว ประสานทีมและป่าข้างเคียงก่อน','กลับมาแล้ว กด "บันทึกเหตุ" ใส่ตำแหน่ง รูป และผล'],
      watch:[toward?'<b>ลมพัดจากจุดความร้อนเข้าหาป่า</b> เฝ้าระวังเป็นพิเศษ':'ดูทิศลม ตอนนี้ไม่ได้พัดจากจุดความร้อนเข้าหาป่า','ถามป่าข้างเคียงหรือหน่วยงานว่ามีคนไปตรวจจุดนี้แล้วหรือยัง','ถ้าเห็นควันในป่า กด "บันทึกเหตุ"'],
      calm:['ไม่มีจุดความร้อนในหรือรอบป่าใน 24 ชม. ล่าสุด','ตรวจว่าเปิดรับแจ้งเตือน LINE หรืออีเมลไว้แล้ว '+button('ตั้งค่าแจ้งเตือน','tab','data-tab="preferences"')],
      unknown:['ข้อมูลดาวเทียมยังไม่พร้อม ยังสรุปไม่ได้ว่าปลอดภัย','ถ้าเห็นควันหรือไฟ โทร <a href="tel:1362">1362</a> แล้วกด "บันทึกเหตุ"'],
    }[sit.status]||[];
    return `<section class="rp-todo"><h2>ต้องทำอะไรตอนนี้</h2><ol>${steps.map(x=>`<li>${x}</li>`).join('')}</ol></section>`;
  }
  function repForestView(selected,allowed,related){
    const P=root.CmeForestPublic,{sit,html}=P.repSummaryHtml(selected,context.dashboard()),c=P.centre(selected);
    const open=related.filter(i=>!['closed','cancelled'].includes(i.status));
    const meta=[selected.tambon?'ต.'+selected.tambon:'',selected.amphoe?'อ.'+selected.amphoe:''].filter(Boolean).join(' · ');
    return `<div class="rp">
      <section class="rp-head"><p class="fp-kicker">${state.me.is_admin?'ผู้ดูแลระบบ · เลือกพื้นที่':'ป่าที่คุณดูแล'}</p>
        ${allowed.length>1?`<label class="sr-only" for="cwActiveForest">เลือกป่า</label><select class="cw-select" id="cwActiveForest">${options(allowed,selected.forest_id)}</select>`:`<h2>${esc(selected.name)}</h2>`}
        <p class="fp-meta">${esc(meta)}</p></section>
      ${selected.boundary_quality==='needs_review'?`<p class="cw-help" role="status"><b>ขอบเขตนี้ต้องตรวจทบทวน</b><br>${esc(selected.boundary_note)} · ระยะใช้จุดอ้างอิงป่าแทน</p>`:''}
      <section class="rp-now" data-rp-now>${html}</section>
      <div class="rp-cta">${button('📝 บันทึกเหตุ','create','',true)}${c?`${button('ดูบนแผนที่หลัก','locate',`data-lat="${c.lat}" data-lon="${c.lon}"`)}`:''}${button('ประวัติเหตุ','all-incidents')}</div>
      ${todoHtml(sit)}
      ${open.length?`<section class="rp-section"><h2>เหตุที่ยังไม่ปิด <span class="rp-count">${open.length}</span></h2>${incidentRows(open)}</section>`:''}
      <section class="rp-section"><h2>แผนที่ป่า</h2><div id="cwMap" class="cw-map" aria-label="ขอบเขตป่าที่เลือกและจุดความร้อน 24 ชั่วโมง"></div><p class="cw-help">กดจุดบนแผนที่เพื่อดูว่าใครควรดูแล</p>${protectedNearbyView(selected)}${crossDistrictView(selected)}<div class="cw-actions">${button('ส่งออกรายงานพื้นที่นี้','export')}</div></section>
      <details class="rp-section rp-who fp-who"><summary>📞 ติดต่อใคร · หน่วยงานในพื้นที่ · ป่าข้างเคียง</summary>${c&&root.CmeCoordination?root.CmeCoordination.html(c.lat,c.lon,{myForestId:selected.forest_id}):''}<p class="cw-help"><a href="tel:052081758">052-081758</a> สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่) · <a href="https://forestinfo.forest.go.th/telephone_region.aspx" target="_blank" rel="noopener">บัญชีโทรศัพท์กรมป่าไม้</a> · ตรวจ 9 ต.ค. 2026</p></details>
      ${root.CmeForestPublic.limitsHtml()}
      ${state.me.is_admin?'':`<details class="rp-section"><summary>ดูแลป่าอื่นด้วย? ส่งคำขอ (รอผู้ดูแลอนุมัติ)</summary>${membershipView()}</details>`}
    </div>`;
  }
  function adminView(){
    const pend=pendingRequests(),open=state.incidents.filter(i=>!['closed','cancelled'].includes(i.status));
    const noCoord=open.filter(i=>!i.coordinator_id).length;
    const P=root.CmeForestPublic;
    const headline=pend.length||open.length?`มีงานรอคุณ ${[pend.length?pend.length+' คำขอ':'',open.length?open.length+' เหตุที่ยังไม่ปิด':''].filter(Boolean).join(' และ ')}`:'ตอนนี้ไม่มีงานค้าง 🎉';
    return `<div class="rp">
      <section class="rp-head adm-head"><p class="fp-kicker">ผู้ดูแลระบบ</p><h2>ภาพรวมทุกป่า</h2><p class="adm-headline">${esc(headline)}</p><p class="fp-meta">คุณไม่ได้เป็นตัวแทนของป่าใด หน้านี้สรุปงานที่รอคุณ</p></section>
      <div class="adm-stats">
        <button type="button" class="adm-stat${pend.length?' warn':''}" data-cw="tab" data-tab="review"><span class="adm-ic" aria-hidden="true">📝</span><b>${pend.length}</b><span>คำขอรอตรวจ</span><small>${pend.length?'กดเพื่อตรวจ':'ไม่มีค้าง'}</small></button>
        <button type="button" class="adm-stat${open.length?' alert':''}" data-cw="all-incidents"><span class="adm-ic" aria-hidden="true">🔥</span><b>${open.length}</b><span>เหตุที่ยังไม่ปิด</span><small>${noCoord?noCoord+' เหตุยังไม่มีผู้รับประสาน':open.length?'มีผู้รับประสานครบ':'ไม่มีเหตุเปิดอยู่'}</small></button>
        <div class="adm-stat"><span class="adm-ic" aria-hidden="true">🌳</span><b>${state.catalog.length.toLocaleString('th-TH')}</b><span>ป่าในระบบ</span><small>ขอบเขตจาก RECOFTC</small></div>
      </div>
      ${open.length?`<section class="rp-section"><h2>เหตุที่ยังไม่ปิด</h2>${incidentRows(open.slice(0,5))}${open.length>5?`<div class="cw-actions">${button('ดูทั้งหมด','all-incidents')}</div>`:''}</section>`:''}
      ${P?`<section class="rp-section"><h2>ดูป่าใดก็ได้</h2><p class="cw-help">ค้นหาชื่อป่าเพื่อดูสถานการณ์แบบเดียวกับที่คนทั่วไปเห็น</p>${P.html({forests:state.catalog,dashboard:context.dashboard(),selectedId:state.publicForest??P.recall(),showRep:false,showList:false})}</section>`:''}
    </div>`;
  }
  function protectedNearbyView(selected){
    const dash=context.dashboard(),q=dash?.data_quality?.hotspots;
    if(!q||q.is_stale||q.source_mode==='UNAVAILABLE')return '';
    const rows=root.CmeProtectedAreas?.nearby(dash.hotspots?.items||[],selected)||[];
    if(!rows.length)return '';
    const areas=new Map(rows.flatMap(r=>r.protection.rows).map(r=>[r.area.id,r]));
    const warning=root.CmeProtectedAreas.warningHtml({status:'inside',rows:[...areas.values()]});
    return `<section class="cw-cross-border cw-protected-nearby"><h3>จุดดาวเทียมในพื้นที่อนุรักษ์ใกล้ป่าเรา</h3>${warning}<p class="cw-help">${rows.length} จุดใน 24 ชม. · ระยะเส้นตรงถึงขอบป่าเราไม่เกิน 5 กม. ไม่ใช่ระยะเดินทาง · ยังไม่ยืนยันเหตุไฟ</p>${rows.slice(0,10).map(r=>`<details><summary>${esc(root.CmeProtectedAreas.name(r.protection.rows[0].area))} · ${date(r.hotspot.detected_at)}</summary>${root.CmeCoordination.html(r.hotspot.lat,r.hotspot.lon,{myForestId:selected.forest_id})}${button('ดูจุดนี้บนแผนที่','locate',`data-lat="${Number(r.hotspot.lat)}" data-lon="${Number(r.hotspot.lon)}"`)}</details>`).join('')}</section>`;
  }
  function crossDistrictView(selected){
    const dash=context.dashboard(),q=dash?.data_quality?.hotspots;
    if(!root.CmeCoordination||!q||q.is_stale||q.source_mode==='UNAVAILABLE')return '';
    const rows=root.CmeCoordination.nearbyCrossDistrict(dash.hotspots?.items||[],selected).sort((a,b)=>Date.parse(b.detected_at)-Date.parse(a.detected_at));
    if(!rows.length)return '';
    return `<section class="cw-cross-border"><h3>อยู่นอกเขตอำเภอ แต่ป่าเราใกล้ที่สุด</h3><p class="cw-help">${rows.length} จุดใน 24 ชม. · ภายในระยะเส้นตรง 5 กม. จากป่า · ยังไม่ยืนยันเหตุไฟ${rows.length>10?' · แสดง 10 จุดล่าสุด':''}</p>${rows.slice(0,10).map(h=>`<details><summary>จุดใกล้ป่าข้ามเขตอำเภอ · ${date(h.detected_at)}</summary>${root.CmeCoordination.html(h.lat,h.lon,{myForestId:selected.forest_id})}${button('ดูจุดนี้บนแผนที่','locate',`data-lat="${Number(h.lat)}" data-lon="${Number(h.lon)}"`)}</details>`).join('')}</section>`;
  }
  // The incident page for the pin flow. The site only informs; people coordinate by themselves.
  // An incident is open until its reporter (or an admin) ends it, or until it expires after 3 days.
  const OPEN_STATES=['pending','confirmed','coordinating','controlled'];
  const stateLabel=status=>OPEN_STATES.includes(status)?'เปิดอยู่':status==='closed'?'จบงานแล้ว':status==='cancelled'?'ไม่ใช่ไฟ':(statusNames[status]||status);
  const PICK={
    closed:{icon:'✅',label:'จบงาน',ask:'สรุปสั้นๆ (ไม่บังคับ)',ph:'เช่น ไฟดับสนิทแล้ว เสียหายประมาณ 2 ไร่',go:'จบงาน หมุดจะหายจากแผนที่'},
    cancelled:{icon:'❌',label:'ไม่ใช่ไฟ',ask:'ทำไมถึงไม่ใช่ไฟ? (ไม่บังคับ)',ph:'เช่น เป็นการเผาขยะที่ดับแล้ว',go:'บันทึกว่าไม่ใช่ไฟ'},
  };
  const eventTitle=e=>e.kind==='expired'?'ปิดอัตโนมัติ (ครบ 3 วัน)':e.kind==='status'&&e.status_to==='closed'?'จบงาน':e.kind==='status'&&e.status_to==='cancelled'?'บันทึกว่าไม่ใช่ไฟ':(eventNames[e.kind]||'อัปเดตเหตุ');
  const leftText=i=>root.CmeIncidentPins?.leftText({expires_at:new Date(Date.parse(i.created_at)+3*864e5).toISOString()})||'';
  function detailView(){
    const d=state.detail,i=d.incident,name=state.catalog.find(f=>f.forest_id===i.forest_id)?.name||'ป่าชุมชน';
    const created=d.events.find(e=>e.kind==='created');
    const mine=!!i.created_by&&i.created_by===state.session.user.id;
    const reporter=mine?'คุณ':esc(created?.actor_name||'ตัวแทนชุมชน');
    const isOpen_=OPEN_STATES.includes(i.status);
    const canClose=isOpen_&&(mine||state.me.is_admin);
    const picks=canClose?['closed','cancelled'].map((k,n)=>{const c=PICK[k];return `<button type="button" class="cw-pick${n===0?' is-main':''}" aria-pressed="false" data-cw="pick-status" data-status="${k}" data-ask="${esc(c.ask)}" data-ph="${esc(c.ph)}" data-go="${esc(c.go)}" data-title="${esc(c.icon+' '+c.label)}"><span aria-hidden="true">${c.icon}</span>${esc(c.label)}</button>`;}).join(''):'';
    const lead=isOpen_?(canClose?'หมุดนี้ยังอยู่บนแผนที่ของตัวแทนป่าทุกคน':'หมุดนี้ยังเปิดอยู่ ผู้แจ้งเป็นคนกดจบงาน'):i.status==='closed'?'จบงานแล้ว หมุดหายจากแผนที่แล้ว':'บันทึกแล้วว่าไม่ใช่ไฟ หมุดหายจากแผนที่แล้ว';
    const hint=isOpen_?`<p class="cw-sos">🔥 ถ้าเห็นไฟจริง <a href="tel:1362">โทร 1362</a> ก่อนเสมอ · หมุดจะหายเองในอีก ${esc(leftText(i))}</p>`:'';
    const act=canClose?`<div class="cw-picks" role="group" aria-label="จบเหตุนี้">${picks}</div>
        <form class="cw-form cw-pick-form" id="cwStatusForm" hidden><input type="hidden" name="status"><p class="cw-pick-title" id="cwPickTitle" aria-live="polite"></p>
          <label><span id="cwPickAsk">สรุปสั้นๆ</span><textarea name="note" maxlength="2000"></textarea></label>
          <div class="cw-actions"><button class="cw-btn primary" id="cwPickGo">บันทึก</button>${button('เปลี่ยนใจ','unpick-status')}</div></form>`:'';
    const nearby=Array.isArray(i.nearby)&&i.nearby.length?`<h3>ป่าใกล้จุดนี้</h3><ul class="pin-near">${i.nearby.map(r=>`<li class="${r.risk?'risk':''}"><strong>${esc(r.name)}</strong> <span>${esc(r.km===0?'อยู่ในขอบเขตป่า':Number(r.km).toFixed(1)+' กม.')}</span> ${r.reporter?'<em>ป่าของผู้แจ้ง</em>':r.risk?'<em class="warn">เสี่ยง · ใกล้ไม่เกิน 5 กม.</em>':''}</li>`).join('')}</ul>`:'';
    return `<div class="cw-detail">
      <div class="cw-actions cw-detail-nav">${button('← กลับรายการเหตุ','back-list')}${button('📍 ดูหมุดบนแผนที่','locate',`data-lat="${i.latitude}" data-lon="${i.longitude}"`)}</div>
      <header class="cw-detail-head s-${esc(isOpen_?'pending':i.status)}"><div class="cw-inc-top"><span class="cw-status ${isOpen_?'pending':esc(i.status)}">${esc(stateLabel(i.status))}</span></div>
        <h2>${i.observation==='smoke'?'💨 ควัน':'🔥 ไฟ'}ที่${esc(name)}</h2>
        <p class="cw-seen">${i.observation==='smoke'?'เห็นควัน':'เห็นเปลวไฟ'} เมื่อ ${date(i.observed_at)} <span>(${esc(ago(i.observed_at))})</span></p></header>
      <section class="cw-todo s-${esc(isOpen_?'pending':i.status)}" aria-labelledby="cwNowT"><p class="cw-todo-k">ตอนนี้</p><h3 id="cwNowT">${esc(lead)}</h3>${hint}${act}</section>
      <section class="cw-section"><h3>รายละเอียด</h3>
        <dl class="cw-info"><div><dt>👤 ผู้แจ้ง</dt><dd>${reporter}</dd></div>
          <div><dt>📍 ที่ไหน</dt><dd>${i.latitude.toFixed(5)}, ${i.longitude.toFixed(5)}<span class="cw-inline">${button('ดูบนแผนที่','locate',`data-lat="${i.latitude}" data-lon="${i.longitude}"`)}</span></dd></div>
          <div><dt>📝 ผู้แจ้งเล่าว่า</dt><dd>${esc(i.description||'ไม่ได้เล่ารายละเอียดเพิ่ม')}</dd></div>
          ${i.contact_phone?`<div><dt>☎️ เบอร์ติดต่อ</dt><dd><a href="tel:${esc(String(i.contact_phone).replace(/[^0-9+]/g,''))}">${esc(i.contact_phone)}</a></dd></div>`:''}</dl>
        ${nearby}
        <details class="fp-who cw-who"><summary>📞 เบอร์หน่วยงานในพื้นที่</summary>${root.CmeCoordination?.html(i.latitude,i.longitude,{myForestId:state.forestId})||''}</details></section>
      <section class="cw-section"><h3>สิ่งที่เกิดขึ้นแล้ว</h3>
        <ol class="cw-timeline">${d.events.map(e=>`<li><strong>${esc(eventTitle(e))}</strong><p>${esc(e.note)}</p><small>${esc(e.actor_name)} · ${date(e.created_at)}</small></li>`).join('')}</ol>${state.eventMore!==false&&d.events.length>=200?button('โหลดประวัติเก่ากว่านี้','older-events'):''}
        ${d.can_note&&isOpen_?'<form class="cw-form" id="cwNoteForm"><label>เพิ่มความคืบหน้า หรือเล่าเพิ่ม<textarea name="note" required maxlength="2000"></textarea></label><button class="cw-btn">เพิ่มบันทึก</button></form>':''}</section>
      <details class="cw-more"><summary>รูปภาพและผลตรวจภาคสนาม</summary><div class="cw-more-body">${fieldChecksView(d)}${photosView(d)}</div></details>
    </div>`;
  }
  function fieldChecksView(d){
    const checks=fieldChecks.get(d.incident.id);
    return `<details class="cw-field-checks"><summary>ผลตรวจภาคสนามและเวลาแจ้งเตือน</summary><p class="cw-help">เก็บหลักฐานเพื่อเทียบข้อมูลภายหลัง ยังไม่มีการคำนวณเปอร์เซ็นต์ความแม่นยำ</p><div class="cw-actions">${button('โหลดผลตรวจภาคสนาม','load-checks')}${checks?.length?button('ส่งออกผลตรวจ CSV','export-checks'):''}</div>${checks?root.CmeField.list(checks):'<p class="cw-help">กดโหลดผลตรวจเพื่อดูรายการที่บันทึกไว้</p>'}${d.can_note?root.CmeField.form('cwFieldCheckForm',checks||[]):'<p class="cw-help">รับร่วมประสานก่อนเพิ่มผลตรวจ</p>'}</details>`;
  }
  function mailRow(m){
    return `<article class="cw-row"><div><strong>${esc({test:'อีเมลทดสอบ',daily:'สรุปรายวัน',incident:'การประสานเหตุ',hotspot:'จุดความร้อนใหม่'}[m.category]||m.category)}</strong><p>${date(m.created_at)} · ${esc({pending:'รอส่ง',processing:'กำลังส่ง',sent:'ผู้ให้บริการรับแล้ว',failed:'ส่งไม่สำเร็จ',suppressed:'ระงับการส่ง'}[m.status]||m.status)} · ${esc({provider_accepted:'รอยืนยันการนำส่ง',delivered:'ส่งถึงระบบอีเมลผู้รับแล้ว',bounced:'อีเมลตีกลับ',complained:'ผู้รับแจ้งร้องเรียน',failed:'นำส่งไม่สำเร็จ'}[m.delivery_status]||m.delivery_status||'ยังไม่มีผลนำส่ง')}</p>${m.last_error?`<small>${esc(m.last_error)}</small>`:''}</div></article>`;
  }
  function lineView(){
    const l=state.line,admin=state.me.is_admin,code=state.lineCode,link=(href,label,primary)=>`<a class="cw-btn${primary?' primary':''}" href="${esc(href)}" target="_blank" rel="noopener">${label}</a>`;
    if(!l)return '<section class="cw-line"><h2>แจ้งเตือนทาง LINE</h2><p class="cw-help" role="status">กำลังตรวจการเชื่อม LINE…</p></section>';
    if(!l.available)return '<section class="cw-line"><h2>แจ้งเตือนทาง LINE</h2><p class="cw-help">ยังไม่ได้เปิดใช้การแจ้งเตือนทาง LINE ในระบบนี้</p></section>';
    const scope=state.me.memberships?.some(m=>m.status==='approved')?'':'<div class="cw-alert">จะเริ่มได้รับแจ้งเตือนหลังผู้ดูแลอนุมัติคุณเป็นตัวแทนป่า</div>';
    if(l.linked)return `<section class="cw-line"><h2>💬 แจ้งเตือนทาง LINE</h2><p class="cw-chip ok"><strong>ผูก LINE แล้ว</strong> · ตั้งแต่ ${date(l.linked_at)}</p>${scope}
      <p class="cw-help">ส่งเมื่อพบจุดความร้อนใหม่ในป่าที่ได้รับอนุมัติ หรือมีการอัปเดตการประสานเหตุ ช่วงพักการส่งด้านล่างใช้กับ LINE ด้วย สรุปรายวันส่งทางอีเมลเท่านั้น</p>
      <div class="cw-actions">${admin?button('ส่ง LINE ทดสอบ','line-test'):''}${button('ยกเลิกการผูก LINE','line-unlink')}</div></section>`;
    return `<section class="cw-line"><h2>💬 แจ้งเตือนทาง LINE</h2><p class="cw-chip">ยังไม่ได้ผูก</p><p class="cw-help">รับแจ้งเมื่อพบจุดความร้อนใหม่ในป่าที่คุณดูแล ผ่านบัญชี LINE ทางการ ${esc(l.basic_id)} ไม่ต้องสมัครบัญชีใหม่</p>${scope}
      ${code?`<ol class="cw-line-steps"><li>${link(code.add_friend_url,'1. เพิ่มเพื่อน '+esc(l.basic_id))}</li><li>${link(code.chat_url,'2. เปิดแชทแล้วกดส่งรหัส',true)}</li></ol>
        <p class="cw-help">รหัส <strong>${esc(code.code)}</strong> ใช้ได้ครั้งเดียว ถึง ${date(code.expires_at)} ถ้าเปิดลิงก์ไม่ได้ ให้พิมพ์รหัสนี้ส่งในแชทเอง</p>
        <div class="cw-actions">${button('ส่งรหัสแล้ว ตรวจสถานะ','line-refresh',  '',true)}${button('ขอรหัสใหม่','line-link')}</div>`
      :`<div class="cw-actions">${button('รับแจ้งเตือนทาง LINE','line-link','',true)}</div>`}</section>`;
  }
  function preferencesView(){
    const p=state.me.preferences,admin=state.me.is_admin,mail=state.mailStatus||[];
    const hours=value=>Array.from({length:24},(_,h)=>`<option value="${h}" ${h===value?'selected':''}>${h.toString().padStart(2,'0')}:00 น.</option>`).join('');
    return `<section class="cw-section cw-prefs"><h2>การแจ้งเตือน</h2><p class="cw-help">เลือกช่องทางที่สะดวก ส่งเฉพาะป่าที่คุณได้รับอนุมัติ</p>
      <div class="cw-pref-card">${lineView()}</div>
      <div class="cw-pref-card"><h2>📧 อีเมลของพื้นที่ที่คุณติดตาม</h2><p class="cw-help">ส่งถึงอีเมลที่ยืนยันของบัญชีนี้ เฉพาะป่าที่ได้รับอนุมัติ เมื่อข้อมูลใหม่เข้ามาหรือมีการประสานเหตุ</p>
      ${state.emailMode!=='live'?'<div class="cw-alert">ยังไม่ส่งถึงสมาชิกทั่วไป ขณะนี้ส่งได้เฉพาะอีเมลทดสอบที่กำหนด จะเปิดรับจริงหลังยืนยันโดเมนผู้ส่ง</div>':''}
      <form class="cw-form" id="cwPreferencesForm">
        <label class="cw-checkbox"><input type="checkbox" name="events_enabled" ${p.events_enabled?'checked':''}><span>รับข้อมูลจุดความร้อนใหม่และการประสานเหตุ</span></label>
        <label class="cw-checkbox"><input type="checkbox" name="daily_enabled" ${p.daily_enabled?'checked':''}><span>รับสรุปประจำวัน ตั้งแต่ 08:00 น. ตามรอบตรวจข้อมูล</span></label>
        <label class="cw-checkbox"><input type="checkbox" name="quiet_enabled" ${p.quiet_enabled?'checked':''}><span>พักการส่งในช่วงเวลาที่เลือก</span></label>
        <div class="cw-fields"><label>เริ่มพัก<select name="quiet_start">${hours(p.quiet_start)}</select></label><label>กลับมาส่ง<select name="quiet_end">${hours(p.quiet_end)}</select></label></div>
        <button class="cw-btn primary">บันทึกการรับอีเมล</button>
      </form><p class="cw-help">ยกเลิกรับได้โดยเอาเครื่องหมายออกและบันทึก อีเมลเป็นข้อมูลสำหรับตรวจสอบ ไม่ใช่ช่องทางฉุกเฉิน ข้อมูลดาวเทียมอัปเดตเป็นรอบ</p></div>
      ${admin?`<details class="cw-pref-card cw-admin-tools"><summary><b>🛠 เครื่องมือผู้ดูแลระบบ</b><small>ทดสอบการส่ง · รอบตรวจข้อมูล · ผลการส่งล่าสุด</small></summary>${jobsView()}<p class="cw-help">ผู้รับทดสอบ: ${esc(state.me.test_recipient||'ยังไม่กำหนด')}</p>
        <div class="cw-actions">${button('ส่งอีเมลทดสอบ','test-email')}${button('ตรวจข้อมูลและคิวตอนนี้','run-alerts')}</div>
        <h3>ผลการส่งล่าสุด</h3>${button('อัปเดตผลการส่ง','refresh-mail')}
        ${mail.length?mailRow(mail[0]):state.mailStatus?'<p class="cw-help">ยังไม่มีรายการส่ง</p>':'<p class="cw-help" role="status">กำลังโหลดผลการส่ง…</p>'}
        ${mail.length>1?`<details><summary>ประวัติการส่งก่อนหน้านี้ (${mail.length-1} รายการที่โหลด)</summary>${mail.slice(1).map(mailRow).join('')}</details>`:''}
      </details>`:''}</section>`;
  }
  function jobsView(){
    const job=state.jobsStatus;if(!job)return '<p class="cw-help">กำลังตรวจรอบงาน…</p>';
    const runs=job.runs||[],latest=runs.find(r=>r.completed_at),old=!latest||Date.now()-Date.parse(latest.completed_at)>30*60000;
    return `<section class="cw-jobs"><h3>รอบตรวจข้อมูลและคิวอีเมล</h3><p>${job.scheduler_enabled?'ตั้งงานอัตโนมัติทุก '+job.interval_minutes+' นาทีผ่าน '+esc(job.scheduler_provider):'ยังไม่ได้เปิดงานอัตโนมัติตามรอบ'}</p><p class="cw-help">ตรวจเสร็จล่าสุด: ${latest?date(latest.completed_at):'ยังไม่มีรอบที่ตรวจเสร็จ'}${old?' · ควรตรวจการทำงาน':''}<br>รอบเรียกตรวจไม่ใช่ความถี่ที่ดาวเทียมหรือสถานีส่งข้อมูลใหม่</p><details><summary>ดูผลรอบล่าสุด</summary>${runs.slice(0,5).map(r=>`<p class="cw-help">${date(r.started_at)} · ${r.completed_at?'ตรวจเสร็จ':r.run_status==='failed'?'รอบนี้ไม่สำเร็จ จะตรวจซ้ำ':r.lease_until&&Date.parse(r.lease_until)<Date.now()?'รอบนี้หยุดก่อนเสร็จ รอตรวจซ้ำ':'กำลังตรวจ'}${r.summary?' · เข้าคิว '+Number(r.summary.queued||0)+' · ผู้ให้บริการรับ '+Number(r.summary.provider_accepted||0):''}</p>`).join('')||'<p class="cw-help">ยังไม่มีผลรอบงาน</p>'}</details></section>`;
  }
  function reviewCard(m){
    return `<article class="cw-req s-${esc(m.status)}"><div class="cw-req-top">${badge(m.status)}${m.created_at?`<small>ส่งคำขอ ${date(m.created_at)} · ${esc(ago(m.created_at))}</small>`:''}</div>
      <h3>🌳 ${esc(m.name)} <span>อ.${esc(String(m.amphoe||'').replace(/^อำเภอ|^อ\./,''))}</span></h3>
      <p class="cw-req-who">👤 ${esc(m.display_name||'ยังไม่ระบุชื่อ')} · ${esc(m.email)}</p>
      <blockquote class="cw-req-note">${esc(m.request_note||'ไม่ได้เขียนรายละเอียด')}</blockquote>
      <div class="cw-actions">${m.status==='pending'?button('✓ อนุมัติพื้นที่','approve',`data-id="${esc(m.id)}"`,true)+button('ไม่อนุมัติ','reject',`data-id="${esc(m.id)}"`):button('ยกเลิกสิทธิ์พื้นที่','revoke',`data-id="${esc(m.id)}"`)}</div></article>`;
  }
  function reviewView(){
    const all=state.reviewQueue||[],pend=all.filter(m=>m.status==='pending'),done=all.filter(m=>m.status!=='pending');
    return `<section class="cw-section"><h2>ตรวจคำขอตัวแทน</h2>
      <div class="cw-check"><b>ก่อนกดอนุมัติ เช็ก 3 ข้อนี้</b><ol><li>เป็นคนในชุมชนหรือคณะกรรมการป่านั้นจริง</li><li>โทรหรือถามผู้นำชุมชน / หน่วยงานในพื้นที่ยืนยันแล้ว</li><li>เลือกป่าถูกแห่ง (ดูอำเภอและตำบลให้ตรง)</li></ol><small>การยืนยันอีเมลอย่างเดียวไม่รับรองว่าเป็นตัวแทนป่า</small></div>
      <h3 class="cw-sub">รอคุณตรวจ <span class="cw-tab-n">${pend.length}</span></h3>
      ${pend.length?`<div class="cw-reqs">${pend.map(reviewCard).join('')}</div>`:'<div class="cw-empty cw-empty-card"><span class="cw-empty-ic" aria-hidden="true">✅</span><h3>ไม่มีคำขอค้าง</h3><p>คำขอใหม่จะขึ้นที่นี่ และนับในแท็บด้านบน</p></div>'}
      ${done.length?`<details class="cw-done"><summary>ตัดสินแล้ว (${done.length})</summary><div class="cw-reqs">${done.map(reviewCard).join('')}</div></details>`:''}
    </section>`;
  }
  function render(){
    if(!isOpen())return;
    const priorView=body.dataset.viewKey;
    if(priorView)body.querySelectorAll('details').forEach((d,n)=>detailsOpen.set(priorView+'/'+n,d.open));
    destroyMap();clearPhotos();
    const notices=(state.error?`<div class="cw-alert error" role="alert">${esc(state.error)} ${button('โหลดอีกครั้ง','reload')}</div>`:'')+(state.notice?`<div class="cw-alert" role="status">${esc(state.notice)}</div>`:'');
    let content;
    if(state.ready===false)content='<div class="cw-empty"><h2>ระบบข้อมูลชุมชนยังไม่พร้อม</h2><p>ยังไม่ได้โหลดรายการเหตุหรือสิทธิ์ของคุณ กรุณาลองใหม่ภายหลัง</p></div>';
    else if(state.ready===null)content='<div class="cw-loading" role="status">กำลังโหลดข้อมูลพื้นที่…</div>';
    else if(state.tab==='incidents'&&!state.session)content=`<section class="cw-section"><h2>เหตุที่อนุมัติให้เผยแพร่</h2><p class="cw-help">แสดงสรุปที่ผู้รับผิดชอบเลือกเผยแพร่ รายละเอียดสำหรับประสานอยู่ในพื้นที่ตัวแทน</p>${incidentRows(state.publicIncidents,true)}<div class="cw-actions">${button('เข้าสู่พื้นที่ตัวแทน','signin')}</div></section>`;
    else if(!state.session)content=publicView();
    else if(!state.me)content='<div class="cw-loading">กำลังตรวจสิทธิ์พื้นที่…</div>';
    else if(state.detail?.incident?.status)content=detailView();
    else if(state.detail)content='<div class="cw-loading">กำลังโหลดประวัติเหตุ…</div>';
    else if(state.tab==='practice')content='<section id="cwPractice"><p class="cw-loading">กำลังโหลดพื้นที่ซ้อม…</p></section>';
    else if(state.tab==='review')content=reviewView();
    else if(state.tab==='preferences')content=preferencesView();
    else if(state.tab==='incidents'){const openN=state.incidents.filter(i=>!['closed','cancelled'].includes(i.status)).length;const seg=(id,label,n)=>`<button type="button" class="cw-seg-btn" data-cw="scope" data-scope="${id}" aria-pressed="${state.scope===id}">${label} <span>${n}</span></button>`;content=`<section class="cw-section"><h2>เหตุทั้งหมด</h2><p class="cw-help">เหตุที่ตัวแทนบันทึกไว้ในป่าที่คุณเห็นได้ เรียงจากล่าสุด กดเปิดดูเพื่ออัปเดตสถานะหรือเพิ่มบันทึก</p><div class="cw-actions"><div class="cw-seg" role="group" aria-label="กรองเหตุ">${seg('active','ยังไม่ปิด',openN)}${seg('all','ทั้งหมด',state.incidents.length)}</div>${allowedForests().length?button('📝 บันทึกเหตุ','create','',true):''}</div>${incidentRows(state.incidents.filter(i=>state.scope==='all'||!['closed','cancelled'].includes(i.status)))}${state.incidentMore?button('โหลดเหตุเก่ากว่านี้','older-incidents'):''}</section>`;}
    else content=forestView();
    const head=container.querySelector('.cw-header');
    if(head){const signedIn=!!state.session;head.querySelector('h1').textContent=signedIn?'พื้นที่ป่าชุมชน':'ป่าชุมชน';head.querySelector('p').textContent=signedIn?'สถานการณ์ · บันทึกเหตุ · ประสานงาน':'ดูไฟ ลม และฝุ่นรอบป่า ไม่ต้องสมัคร';}
    body.innerHTML=tabs()+notices+content;
    // On phones the tab row scrolls; keep the open tab in sight.
    const tabRow=body.querySelector('.cw-tabs'),on=tabRow?.querySelector('[aria-selected="true"]');if(tabRow&&on)tabRow.scrollLeft=Math.max(0,on.offsetLeft-(tabRow.clientWidth-on.offsetWidth)/2);
    body.dataset.viewKey=state.tab+'/'+(state.detail?.incident?.id||'')+'/'+state.create;
    body.querySelectorAll('details').forEach((d,n)=>{const open=detailsOpen.get(body.dataset.viewKey+'/'+n);if(open!==undefined)d.open=open;});
    restoreForms();
    if(state.create&&state.session&&state.me){loadNearPins();updateNearPins();}
    const pick=body.querySelector('#cwIncidentForm select[name="forest_id"]');if(pick&&pick.options.length>30)root.CmeForestPicker?.enhance(pick);
    if(state.ready&&root.CmeForestPublic&&body.querySelector('.fp')){
      body.dataset.fpDash=context.dashboard()?'1':'';
      root.CmeForestPublic.attach(body,{forests:()=>state.catalog,dashboard:()=>context.dashboard(),locate:(lat,lon)=>context.locate(lat,lon),fetcher:path=>root.fetch((context.apiBase||'')+path),onPick:id=>{state.publicForest=id;},rerender:()=>render()});
    }
    if(state.tab==='practice'&&state.session&&state.me&&root.CmePractice)root.CmePractice.attach(document.getElementById('cwPractice'),{api});
    if(state.tab==='forest'&&state.me&&!state.detail&&!state.create){renderMap(forest());const now=body.querySelector('[data-rp-now]');if(now&&root.CmeForestPublic){root.CmeForestPublic.fillAsync(now,forest(),path=>root.fetch((context.apiBase||'')+path));root.CmeCoordination?.hydrate?.(body);}}
    if(state.detail?.photos?.length)loadPhotos();
    if(state.busy)body.querySelectorAll('button').forEach(b=>b.disabled=true);
  }
  async function load(){
    if(loading)return loading;
    const version=sequence,uid=context.user()?.id;
    loading=(async()=>{
      try{
        const [status,session]=await Promise.all([api('/status',{publicOnly:true}),context.session()]);
        if(version!==sequence)return;
        state.ready=status.ready;state.emailMode=status.email_mode;state.session=session;
        if(!state.catalog.length){state.catalog=context.forests();if(!state.catalog.length){const result=await context.catalog();state.catalog=result.forests||[];}}
        if(!session){state.me=null;state.incidents=[];state.publicIncidents=await api('/public-incidents',{publicOnly:true});}
        else{
          const [me,incidents]=await Promise.all([api('/me'),api('/incidents')]);
          if(version!==sequence||uid!==context.user()?.id)return;
          state.me=me;state.incidents=incidents;state.incidentMore=incidents.length===200;
          if(!state.forestId||!allowedForests().some(f=>f.forest_id===state.forestId))state.forestId=allowedForests()[0]?.forest_id||'';
          state.draft=state.draft||readDraft();
          if((state.tab==='review'||state.tab==='forest')&&me.is_admin)state.reviewQueue=await api('/review-queue');
          if(state.tab==='preferences'){state.line=await api('/line').catch(()=>({available:false}));if(state.line.linked)state.lineCode=null;}
          if(state.tab==='preferences'&&me.is_admin)[state.mailStatus,state.jobsStatus]=await Promise.all([api('/mail-status'),api('/jobs-status')]);
          if(state.detail?.incident?.id){state.eventMore=true;state.detail=await api('/incidents/'+state.detail.incident.id);}
        }
        if(version!==sequence)return;
        state.error='';render();
      }catch(error){if(version===sequence){state.error=error.message;if(state.ready===null)state.ready=false;render();}}
      finally{loading=null;}
    })();return loading;
  }
  function open(tab='forest',incidentId=null){context.closeOthers();container.classList.add('open');state.tab=tab;state.detail=incidentId?{incident:{id:incidentId}}:null;context.activate(tab==='incidents'?'phase':'community');render();container.scrollTop=0;return load();}
  function hide(){if(container)container.classList.remove('open');destroyMap();clearPhotos();if(body)body.replaceChildren();}
  function close(){hide();context.home();}
  function formKey(form){return (state.detail?.incident?.id||'workspace')+'/'+form.id;}
  function restoreForms(){for(const form of body.querySelectorAll('.cw-form')){const values=formDrafts.get(formKey(form));if(values)for(const input of form.elements){if(input.name&&input.type!=='file'&&values[input.name]!==undefined){if(input.type==='checkbox')input.checked=values[input.name];else input.value=values[input.name];}}}}
  function rememberForm(form){const values={};for(const input of form.elements)if(input.name&&input.type!=='file')values[input.name]=input.type==='checkbox'?input.checked:input.value;formDrafts.set(formKey(form),values);}
  async function perform(task){if(state.busy)return;state.busy=true;state.error='';body.querySelectorAll('button').forEach(b=>b.disabled=true);const progress=document.createElement('p');progress.className='cw-progress';progress.setAttribute('role','status');progress.textContent='กำลังดำเนินการ กรุณารอผลยืนยัน…';body.prepend(progress);try{await task();}catch(error){state.error=error.message;if(error.status===409&&state.detail?.incident?.id){try{state.detail=await api('/incidents/'+state.detail.incident.id);state.error='เหตุนี้มีคนอัปเดตแล้ว โหลดสถานะล่าสุดให้แล้ว ตรวจข้อมูลและส่งอีกครั้ง ข้อความที่กรอกยังอยู่';}catch{}}}finally{state.busy=false;render();}}
  async function updateIncident(action,extra={}){const i=state.detail.incident;await api('/incidents/'+i.id,{method:'PATCH',data:{action,version:i.version,...extra}});state.notice='บันทึกความเปลี่ยนแปลงแล้ว';await load();}
  async function click(event){
    const b=event.target.closest('[data-cw]');if(!b||state.busy)return;const a=b.dataset.cw;
    if(['tab','public','all-incidents','back-list','create','cancel-create','detail'].includes(a))container.scrollTop=0;
    if(a==='signin'){context.signin();return;}
    if(a==='tab'){if(b.dataset.tab==='practice')history.replaceState(null,'','#community/practice');else if(location.hash==='#community/practice')history.replaceState(null,'','#community');state.tab=b.dataset.tab;state.detail=null;state.create=false;state.notice='';render();await load();return;}
    if(a==='public'){state.tab='incidents';render();return;}
    if(a==='reload'){await load();return;}
    if(a==='legacy-phase'){context.closeOthers();context.legacyPhase();return;}
    if(a==='scope'){state.scope=b.dataset.scope||(state.scope==='active'?'all':'active');render();return;}
    if(a==='all-incidents'){state.tab='incidents';state.scope='all';render();return;}
    if(a==='back-list'){state.detail=null;state.tab='incidents';render();return;}
    if(a==='create'){state.nearPins=undefined;if(!b.closest('.rp-cta')&&myForests().length!==1)state.forestId='';state.create=true;state.tab='forest';state.detail=null;startDraft();render();return;}
    if(a==='old-draft-use'){state.draft=state.oldDraft;state.oldDraft=null;saveDraft();render();return;}
    if(a==='old-draft-drop'){state.oldDraft=null;render();return;}
    if(a==='cancel-create'){state.create=false;render();return;}
    if(a==='pick'){saveDraft();context.pick();return;}
    if(a==='gps'){if(!navigator.geolocation){state.error='เบราว์เซอร์นี้ไม่รองรับตำแหน่ง';render();return;}navigator.geolocation.getCurrentPosition(p=>{state.draft.latitude=p.coords.latitude.toFixed(5);state.draft.longitude=p.coords.longitude.toFixed(5);saveDraft();render();},()=>{state.error='ยังไม่ได้รับตำแหน่ง กรุณาเลือกบนแผนที่';render();},{timeout:8000});return;}
    if(a==='locate'){context.locate(Number(b.dataset.lat),Number(b.dataset.lon));return;}
    if(a==='pick-status'||a==='unpick-status'){
      const f=document.getElementById('cwStatusForm');if(!f)return;
      if(a==='unpick-status'){f.hidden=true;body.querySelectorAll('.cw-pick').forEach(x=>x.setAttribute('aria-pressed','false'));return;}
      f.elements.status.value=b.dataset.status;f.hidden=false;
      document.getElementById('cwPickTitle').textContent=b.dataset.title;
      document.getElementById('cwPickAsk').textContent=b.dataset.ask;
      f.elements.note.placeholder=b.dataset.ph;document.getElementById('cwPickGo').textContent=b.dataset.go;
      body.querySelectorAll('.cw-pick').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      f.elements.note.focus();f.scrollIntoView({block:'nearest',behavior:'smooth'});return;
    }
    if(a==='export'){context.exportForest(state.forestId);return;}
    await perform(async()=>{
      if(a==='detail'){state.eventMore=true;state.detail=await api('/incidents/'+b.dataset.id);history.replaceState(null,'','#community/incident/'+b.dataset.id);}
      else if(a==='older-incidents'){const rows=await api('/incidents?offset='+state.incidents.length);const ids=new Set(state.incidents.map(i=>i.id));state.incidents.push(...rows.filter(i=>!ids.has(i.id)));state.incidentMore=rows.length===200;}
      else if(a==='older-events'){const rows=await api('/incidents/'+state.detail.incident.id+'/events?offset='+state.detail.events.length);const ids=new Set(state.detail.events.map(e=>e.id));state.detail.events.push(...rows.filter(e=>!ids.has(e.id)));state.eventMore=rows.length===200;if(!state.eventMore)state.notice='โหลดประวัติครบแล้ว';}
      else if(a==='claim')await updateIncident('claim_coordination');
      else if(a==='publish')await updateIncident('publish_summary',{published:!state.detail.incident.published});
      else if(a==='accept'||a==='decline')await updateIncident('respond_partner',{forest_id:b.dataset.forest,status:a==='accept'?'accepted':'declined'});
      else if(['approve','reject','revoke'].includes(a)){await api('/memberships/'+b.dataset.id,{method:'PATCH',data:{status:{approve:'approved',reject:'rejected',revoke:'revoked'}[a]}});state.notice='บันทึกผลตรวจสิทธิ์แล้ว';await load();}
      else if(a==='test-email'){const result=await api('/test-email',{method:'POST'});state.notice=result.provider_accepted?'Resend รับอีเมลทดสอบแล้ว กรุณาตรวจกล่องจดหมายและจดหมายขยะ':result.failed?'ยังส่งไม่สำเร็จ ตรวจผลการส่งล่าสุด':'เก็บอีเมลเข้าคิวแล้ว';await load();}
      else if(a==='run-alerts'){const result=await api('/request-alert-check',{method:'POST'});state.notice=result.already_checked?'ตรวจในรอบนี้แล้ว หรือมีงานกำลังตรวจอยู่ จะตรวจอีกครั้งในรอบถัดไป':result.accepted?'รับคำขอตรวจแล้ว งานจะทำต่อเบื้องหลัง กดอัปเดตผลการส่งเพื่อดูผลล่าสุด':`ตรวจข้อมูลและคิวแล้ว · Resend รับ ${result.provider_accepted||0} ข้อความ`;[state.mailStatus,state.jobsStatus]=await Promise.all([api('/mail-status'),api('/jobs-status')]);}
      else if(a==='line-link'){state.lineCode=await api('/line/link-code',{method:'POST'});state.notice='เพิ่มเพื่อนแล้วกดส่งรหัสในแชท LINE จากนั้นกลับมากดตรวจสถานะ';}
      else if(a==='line-refresh'){state.line=await api('/line');if(state.line.linked){state.lineCode=null;state.notice='ผูก LINE สำเร็จแล้ว';}else state.notice='ยังไม่พบการผูก ตรวจว่ากดส่งรหัสในแชทแล้ว และรหัสยังไม่หมดอายุ';}
      else if(a==='line-unlink'){if(!root.confirm('ยกเลิกการผูก LINE? จะไม่ได้รับแจ้งเตือนทาง LINE อีก'))return;await api('/line/link',{method:'DELETE'});state.line=await api('/line');state.notice='ยกเลิกการผูก LINE แล้ว';}
      else if(a==='line-test'){const result=await api('/line/test',{method:'POST'});state.notice=result.line_accepted?'LINE รับข้อความทดสอบแล้ว ตรวจในแชท LINE ของคุณ':result.line_quota_reached?'โควตาข้อความ LINE ของเดือนนี้หมดแล้ว':'ยังส่งไม่สำเร็จ ลองอีกครั้งภายหลัง';}
      else if(a==='refresh-mail')[state.mailStatus,state.jobsStatus]=await Promise.all([api('/mail-status'),api('/jobs-status')]);
      else if(a==='load-checks')fieldChecks.set(state.detail.incident.id,await api('/incidents/'+state.detail.incident.id+'/field-checks'));
      else if(a==='export-checks')root.CmeField.download(root.CmeField.csv(fieldChecks.get(state.detail.incident.id)||[],state.detail.incident),'chiangmaieyes-field-checks-'+state.detail.incident.id+'.csv');
    });
  }
  async function submit(event){
    if(!event.target.matches('.cw-form'))return;event.preventDefault();const form=event.target,values=Object.fromEntries(new FormData(form));
    const snapshotKey=formKey(form);rememberForm(form);
    await perform(async()=>{
      if(form.id==='cwMembershipForm'){await api('/memberships',{method:'POST',data:{forest_id:document.getElementById('cwRequestForest').value,note:values.note}});state.notice='ส่งคำขอแล้ว รอผู้ดูแลตรวจสอบ';await load();}
      else if(form.id==='cwIncidentForm'){
        Object.assign(state.draft,values);saveDraft();const observed=values.observed_local+':00+07:00';
        const phone=String(values.contact_phone||'').trim();if(phone&&!/^[0-9+() \-]{6,20}$/.test(phone))throw new Error('เบอร์โทรใส่ได้เฉพาะตัวเลข เว้นวรรค และ + - ( ) ความยาว 6-20 ตัว');const result=await api('/incidents',{method:'POST',data:{id:state.draft.id,forest_id:values.forest_id,observation:values.observation,latitude:Number(values.latitude),longitude:Number(values.longitude),observed_at:observed,description:values.description,...(String(values.contact_phone||'').trim()?{contact_phone:String(values.contact_phone).trim()}:{})}});
        dropDraft();state.create=false;state.tab='incidents';state.notice='ส่งแล้ว หมุดขึ้นบนแผนที่ และแจ้ง LINE ถึงป่าที่อยู่ใกล้ (ไม่เกิน 5 กม.) แล้ว';pinsChanged();
        try{state.detail=await api('/incidents/'+result.id);await load();}catch(error){state.detail=null;state.error='บันทึกเหตุสำเร็จ แต่โหลดรายละเอียดไม่สำเร็จ กรุณาโหลดอีกครั้ง';}
      }else if(form.id==='cwPhotoForm'){const file=form.elements.photo.files[0];if(!file||file.size>4*1024*1024)throw new Error('เลือกรูปขนาดไม่เกิน 4 MB');await api('/incidents/'+state.detail.incident.id+'/photo',{method:'POST',raw:file});state.notice='แนบรูปสำเร็จแล้ว';await load();}
      else if(form.id==='cwFieldCheckForm'){
        const id=state.detail.incident.id,signature=id+'/'+JSON.stringify(values);let requestId=checkRequests.get(signature);if(!requestId){requestId=root.crypto.randomUUID();checkRequests.set(signature,requestId);}
        const saved=await api('/incidents/'+id+'/field-checks',{method:'POST',data:root.CmeField.payload(form,requestId)});
        const rows=fieldChecks.get(id)||[];if(!rows.some(c=>c.id===saved.id))rows.push(saved);fieldChecks.set(id,rows);
        checkRequests.delete(signature);formDrafts.delete(snapshotKey);state.notice='บันทึกผลตรวจแล้ว ประวัติเดิมยังอยู่';
        try{fieldChecks.set(id,await api('/incidents/'+id+'/field-checks'));await load();}catch{state.error='บันทึกผลตรวจสำเร็จ แต่โหลดรายการล่าสุดไม่ได้ กดโหลดผลตรวจอีกครั้งได้';}
      }
      else if(form.id==='cwMergeForm')await updateIncident('merge_incident',{target_id:values.target_id,note:values.note});
      else if(form.id==='cwStatusForm'){await api('/incidents/'+state.detail.incident.id+'/close',{method:'POST',data:{outcome:values.status,note:values.note||''}});state.notice='บันทึกแล้ว หมุดหายจากแผนที่';await load();pinsChanged();}
      else if(form.id==='cwNoteForm')await updateIncident('add_note',{note:values.note});
      else if(form.id==='cwPartnerForm')await updateIncident('invite_partner',{forest_id:values.forest_id});
      else if(form.id==='cwPreferencesForm'){await api('/preferences',{method:'PUT',data:{events_enabled:form.elements.events_enabled.checked,daily_enabled:form.elements.daily_enabled.checked,quiet_enabled:form.elements.quiet_enabled.checked,quiet_start:Number(values.quiet_start),quiet_end:Number(values.quiet_end)}});state.notice='บันทึกการรับอีเมลแล้ว';await load();}
      formDrafts.delete(snapshotKey);
    });
  }
  function input(event){
    const activeForm=event.target.closest('.cw-form');if(activeForm&&activeForm.id!=='cwIncidentForm')rememberForm(activeForm);
    if(event.target.closest('#cwIncidentForm')&&['latitude','longitude'].includes(event.target.name))updateNearPins();
    if(event.target.id==='cwForestSearch'){const q=event.target.value.trim();document.getElementById('cwRequestForest').innerHTML=options(state.catalog.filter(f=>(f.name+' '+f.amphoe).includes(q)));}
    if(event.target.closest('#cwIncidentForm')&&event.target.name){if(!state.draft)state.draft=newDraft();state.draft[event.target.name]=event.target.value;saveDraft();}
    if(event.target.id==='cwActiveForest'){state.forestId=event.target.value;render();}
  }
  function authChanged(){sequence++;loading=null;formDrafts.clear();checkRequests.clear();fieldChecks.clear();detailsOpen.clear();root.CmePractice?.reset();clearPhotos();destroyMap();if(body)body.replaceChildren();state.me=null;state.session=null;state.incidents=[];state.detail=null;state.reviewQueue=[];state.mailStatus=[];state.jobsStatus=null;state.draft=null;state.create=false;state.notice='';render();if(isOpen())load();}
  // Shared forest links: #community/forest/<forest_id> opens that forest's card.
  function forestLink(){const m=location.hash.match(/^#community\/forest\/([A-Za-z0-9_-]{1,64})$/);return m?m[1]:null;}
  async function openForestLink(id){
    state.publicForest=id;try{root.localStorage.setItem('cme-public-forest-v1',id);}catch{}
    await open('forest');
    if(state.session&&state.me){
      if(allowedForests().some(f=>f.forest_id===id)){state.forestId=id;render();}
      else{const f=state.catalog.find(x=>x.forest_id===id);if(f){state.notice='ลิงก์ที่เปิดเป็นของ '+f.name+' ซึ่งไม่ใช่ป่าที่คุณดูแล ออกจากระบบเพื่อดูการ์ดสาธารณะของป่านั้น';render();}}
    }
    body?.querySelector('#fpCard')?.scrollIntoView?.({block:'start'});
  }
  function init(adapter){context=adapter;container=document.getElementById('communityview');body=document.getElementById('communityContent');container.addEventListener('click',click);container.addEventListener('submit',submit);container.addEventListener('input',input);container.addEventListener('change',input);document.getElementById('communityClose').onclick=close;
    root.addEventListener('hashchange',()=>{const id=forestLink();if(id)openForestLink(id);});
    const linked=forestLink();if(linked){openForestLink(linked);return;}
    const match=location.hash.match(/^#community(?:\/incident\/([a-f0-9-]{36}))?$/i),requested=new URLSearchParams(location.search).get('incident'),fromEmail=/^[a-f0-9-]{36}$/i.test(requested||'')?requested:null;if(location.hash==='#community/practice'&&!fromEmail)open('practice');else if(match||fromEmail)open(fromEmail||match?.[1]?'incidents':'forest',fromEmail||match?.[1]||null);
  }
  root.CmeCommunity={init,open,close,hide,authChanged,api,statusNames,transitions,
    dataChanged:()=>{if(!isOpen())return;if(!state.session&&state.ready&&body?.dataset.fpDash==='')render();else if(state.tab==='forest'&&!state.create&&!state.detail&&allowedForests().length)render();},
    newIncident:async(point)=>{await open('forest');if(!state.session){state.notice='เข้าสู่ระบบและรับอนุมัติพื้นที่ก่อนแจ้งเหตุ';render();return;}if(!allowedForests().length){state.notice='ขอสิทธิ์ตัวแทนพื้นที่ก่อนบันทึกเหตุ';render();return;}startDraft(point);state.create=true;state.detail=null;saveDraft();render();},
    myReports:()=>api('/my-reports'),cancelLegacy:id=>api('/my-reports/'+id+'/cancel',{method:'POST'})};
})(window);
