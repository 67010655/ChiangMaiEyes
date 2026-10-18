/* Approved representative workspace. Private data comes only from the authenticated API. */
(function(root){
  'use strict';
  const statusNames={pending:'รอตรวจสอบ',confirmed:'ยืนยันเหตุ',coordinating:'กำลังประสาน',controlled:'ควบคุมได้',closed:'ปิดเหตุ',cancelled:'ยกเลิกเหตุ',approved:'อนุมัติแล้ว',rejected:'ไม่อนุมัติ',revoked:'ยกเลิกสิทธิ์',invited:'รอรับคำขอ',accepted:'ร่วมประสาน',declined:'ไม่รับคำขอ'};
  const transitions={pending:['confirmed','cancelled'],confirmed:['coordinating','controlled','cancelled'],coordinating:['controlled','cancelled'],controlled:['coordinating','closed'],closed:['pending'],cancelled:['pending']};
  const eventNames={created:'แจ้งเหตุ',status:'เปลี่ยนสถานะ',note:'บันทึกเพิ่มเติม',photo:'เพิ่มภาพประกอบ',field_check:'เพิ่มผลตรวจภาคสนาม',merged:'เชื่อมกับเหตุหลัก',linked_report:'เชื่อมรายงานเพิ่มเติม',coordination:'รับเป็นผู้ประสาน',partner_invited:'ขอร่วมประสาน',partner_accepted:'รับร่วมประสาน',partner_declined:'ไม่รับคำขอ',publication:'เปลี่ยนการเผยแพร่'};
  let context,container,body,miniMap,loading=null,sequence=0;
  let photoUrls=[],renderVersion=0;
  const checkRequests=new Map(),detailsOpen=new Map();
  const fieldChecks=new Map();
  const formDrafts=new Map();
  const state={tab:'forest',me:null,session:null,catalog:[],incidents:[],publicIncidents:[],detail:null,forestId:'',error:'',notice:'',busy:false,ready:null,emailMode:'unavailable',create:false,scope:'active',draft:null};
  const E=()=>root.CmeEvidence;
  const esc=value=>E().escapeHtml(value);
  const date=value=>E().stamp(value);
  const badge=status=>`<span class="cw-status ${esc(status)}">${esc(statusNames[status]||status)}</span>`;
  const button=(label,action,extra='',primary=false)=>`<button type="button" class="cw-btn${primary?' primary':''}" data-cw="${action}" ${extra}>${label}</button>`;
  const options=(forests,selected='')=>forests.map(f=>{const duplicated=state.catalog.filter(x=>x.name===f.name&&x.amphoe===f.amphoe).length>1;return `<option value="${esc(f.forest_id)}" ${f.forest_id===selected?'selected':''}>${esc(f.name)} · ${esc(f.amphoe)}${duplicated?' · '+esc(f.tambon||'')+' · '+esc(f.forest_id):''}</option>`;}).join('');
  const isOpen=()=>container&&container.classList.contains('open');
  const allowedForests=()=>state.me?.is_admin?state.catalog:state.catalog.filter(f=>state.me?.memberships.some(m=>m.status==='approved'&&m.forest_id===f.forest_id));
  const forest=()=>state.catalog.find(f=>f.forest_id===state.forestId);
  const draftKey=()=>state.session?'cme-incident-draft-v1/'+state.session.user.id:null;
  function localTime(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()).replace(' ','T');}
  function newDraft(point={}){return {id:root.crypto.randomUUID(),forest_id:state.forestId,observation:'smoke',observed_local:localTime(),latitude:point.lat??'',longitude:point.lon??'',description:''};}
  function readDraft(){try{return JSON.parse(root.localStorage.getItem(draftKey()))||null;}catch{return null;}}
  function saveDraft(){const key=draftKey();if(!key||!state.draft)return;try{root.localStorage.setItem(key,JSON.stringify({...state.draft,saved_at:new Date().toISOString()}));const text=document.getElementById('cwDraftSaved');if(text)text.textContent='ร่างเก็บในเครื่องนี้แล้ว · '+date(new Date().toISOString());}catch{const text=document.getElementById('cwDraftSaved');if(text)text.textContent='เก็บร่างในเครื่องไม่ได้ โปรดเปิดหน้านี้ไว้ก่อนส่ง';}}
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
      [...new Set([...inside,...across])].forEach(h=>L.circleMarker([h.lat,h.lon],{radius:6,color:'#b9480b',fillColor:'#ed8d3c',fillOpacity:.9,weight:1}).bindPopup(()=>`${root.CmeCoordination?.html(h.lat,h.lon,{myForestId:selected.forest_id})||''}จุดความร้อน · ${date(h.detected_at)}`,{maxWidth:320,maxHeight:300}).addTo(miniMap));
    }
  }
  function tabs(){
    const entries=[['forest','ป่าของฉัน'],['incidents','ติดตามเหตุ'],['preferences','การแจ้งเตือน'],['practice','ซ้อมใช้งาน']];
    if(state.me?.is_admin)entries.push(['review','ตรวจคำขอ']);
    return `<div class="cw-tabs" role="tablist" aria-label="พื้นที่ชุมชน">${entries.map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" data-cw="tab" data-tab="${id}">${label}</button>`).join('')}</div>`;
  }
  function loginView(){return `<div class="cw-empty"><h2>พื้นที่สำหรับตัวแทนป่าชุมชน</h2><p>เข้าสู่ระบบเพื่อขอสิทธิ์พื้นที่ เมื่อผู้ดูแลยืนยันแล้ว คุณจะบันทึกเหตุ ร่วมประสานงาน และตั้งค่าอีเมลของป่าที่รับผิดชอบได้</p><p>ยังไม่มีบัญชี? เลือกสมัครสมาชิกในหน้าบัญชี แล้วจึงขอสิทธิ์พื้นที่</p>${button('เข้าสู่ระบบ / สมัครสมาชิก','signin','',true)} ${button('ดูเหตุที่เผยแพร่','public')}${E().fireHelpHtml()}</div>`;}
  function membershipView(){
    const requests=state.me?.memberships||[];
    return `<section class="cw-section"><h2>ขอสิทธิ์ตัวแทนป่าชุมชน</h2><p class="cw-help">เลือกป่าจากขอบเขตที่ได้รับจาก RECOFTC และระบุหน้าที่หรือช่องทางให้ผู้ดูแลตรวจสอบ การเลือกชื่อป่ายังไม่ถือว่าได้รับสิทธิ์</p>
      <form class="cw-form" id="cwMembershipForm"><label>ค้นหาชื่อป่าหรืออำเภอ<input type="search" id="cwForestSearch" placeholder="พิมพ์ชื่อป่าหรืออำเภอ" autocomplete="off"></label><label>ป่าที่ขอสิทธิ์<select id="cwRequestForest" required>${options(state.catalog)}</select></label><label>หน้าที่และข้อมูลสำหรับตรวจสอบ<textarea name="note" maxlength="1000" required placeholder="เช่น หน้าที่ในชุมชน และช่องทางตรวจสอบกับหน่วยงาน"></textarea></label><button class="cw-btn primary">ส่งคำขอให้ผู้ดูแล</button></form>
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
  function incidentRows(rows,publicView=false){return rows.length?rows.map(i=>`<article class="cw-row"><div><h3>${esc(i.forest_name||state.catalog.find(f=>f.forest_id===i.forest_id)?.name||'ป่าชุมชน')}</h3>${badge(i.status)}<p>พบเหตุ ${date(i.observed_at)} · อัปเดต ${date(i.updated_at)}</p>${!publicView?`<p>${i.coordinator_id?'ผู้รับประสาน: '+esc(i.coordinator_name||'ตัวแทนที่รับเรื่อง'):'ยังไม่มีผู้รับประสานในระบบ'}</p>`:''}</div>${!publicView?button('ดูประวัติเหตุ','detail',`data-id="${esc(i.id)}"`):''}</article>`).join(''):`<div class="cw-empty"><h3>${publicView?'ยังไม่มีเหตุที่อนุมัติให้เผยแพร่':'ยังไม่มีเหตุในรายการนี้'}</h3><p>การไม่มีรายการในระบบไม่ได้ยืนยันว่าไม่มีไฟในพื้นที่</p></div>`;}
  function createForm(){
    const d=state.draft||newDraft(),allowed=allowedForests();state.draft=d;
    return `<section class="cw-section"><h2>แจ้งสิ่งที่พบ</h2><p class="cw-help">เริ่มจากตำแหน่ง เวลา และสิ่งที่เห็น รายละเอียดเพิ่มหลังส่งได้ เหตุใหม่จะอยู่ในสถานะรอตรวจสอบ</p><form class="cw-form" id="cwIncidentForm">
      <label>พื้นที่ที่ประสาน<select name="forest_id" required>${options(allowed,d.forest_id)}</select></label>
      <label>สิ่งที่พบ<select name="observation"><option value="smoke" ${d.observation==='smoke'?'selected':''}>เห็นควัน</option><option value="fire" ${d.observation==='fire'?'selected':''}>เห็นเปลวไฟ</option></select></label>
      <label>เวลาที่พบ (เวลาประเทศไทย)<input name="observed_local" type="datetime-local" value="${esc(d.observed_local)}" required></label>
      <div class="cw-fields"><label>ละติจูด<input name="latitude" type="number" step="any" min="-90" max="90" value="${esc(d.latitude)}" required></label><label>ลองจิจูด<input name="longitude" type="number" step="any" min="-180" max="180" value="${esc(d.longitude)}" required></label></div>
      <div class="cw-actions">${button('เลือกตำแหน่งบนแผนที่','pick')} ${button('ใช้ตำแหน่งฉัน','gps')}</div>
      <label>รายละเอียด (เติมภายหลังได้)<textarea name="description" maxlength="2000" placeholder="สิ่งที่เห็นหรือข้อมูลให้ผู้รับประสานตรวจสอบ">${esc(d.description)}</textarea></label>
      <p class="cw-help" id="cwDraftSaved">${d.saved_at?'ร่างเก็บในเครื่องนี้ · '+date(d.saved_at):'ร่างจะเก็บในเครื่องนี้ระหว่างกรอก ยังไม่ใช่รายงานที่ส่งแล้ว'}</p>
      <div class="cw-actions"><button class="cw-btn primary">ส่งเหตุให้ตรวจสอบ</button>${button('กลับรายการ','cancel-create')}</div></form></section>`;
  }
  function forestView(){
    const allowed=allowedForests();
    if(!allowed.length)return membershipView();
    if(state.create)return createForm();
    const selected=forest()||allowed[0];state.forestId=selected.forest_id;
    const related=state.incidents.filter(i=>i.forest_id===selected.forest_id||i.partner_forest_ids?.includes(selected.forest_id));
    return `<div class="cw-layout"><section class="cw-section"><label class="cw-help" for="cwActiveForest">${state.me.is_admin?'เลือกพื้นที่ดูแลระบบ':'พื้นที่ที่ได้รับอนุมัติ'}</label><select class="cw-select" id="cwActiveForest">${options(allowed,selected.forest_id)}</select>${summary(selected)}${crossDistrictView(selected)}<div id="cwMap" class="cw-map" aria-label="ขอบเขตป่าที่เลือกและจุดความร้อน 24 ชั่วโมง"></div><p class="cw-help">ขอบเขตจาก RECOFTC · ดาวเทียมยังไม่ยืนยันเหตุภาคสนาม · ลมอ้างอิงจังหวัดยังไม่ใช่ลมที่วัดในป่าแห่งนี้</p><div class="cw-actions">${button('แจ้งสิ่งที่พบ','create','',true)}${button('ส่งออกรายงานพื้นที่นี้','export')}</div></section>
      <section class="cw-section"><h2>งานที่ต้องดู</h2>${incidentRows(related.filter(i=>!['closed','cancelled'].includes(i.status)))}<div class="cw-actions">${button('ดูประวัติเหตุทั้งหมด','all-incidents')}</div><h3>ช่องทางประสานหน่วยงาน</h3><p class="cw-help"><a href="tel:052081758">052-081758</a> สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่)<br><a href="https://forestinfo.forest.go.th/telephone_region.aspx" target="_blank" rel="noopener">บัญชีโทรศัพท์กรมป่าไม้</a> · ตรวจ 9 ต.ค. 2026<br>เป็นช่องทางสอบถามผู้ประสาน ยังไม่มีรายชื่อหัวหน้าป่าแห่งนี้ที่ยืนยันแล้ว</p>${state.me.is_admin?'':`<details><summary>ขอสิทธิ์พื้นที่เพิ่มเติม</summary>${membershipView()}</details>`}</section></div>`;
  }
  function crossDistrictView(selected){
    const dash=context.dashboard(),q=dash?.data_quality?.hotspots;
    if(!root.CmeCoordination||!q||q.is_stale||q.source_mode==='UNAVAILABLE')return '';
    const rows=root.CmeCoordination.nearbyCrossDistrict(dash.hotspots?.items||[],selected).sort((a,b)=>Date.parse(b.detected_at)-Date.parse(a.detected_at));
    if(!rows.length)return '';
    return `<section class="cw-cross-border"><h3>อยู่นอกเขตอำเภอ แต่ป่าเราใกล้ที่สุด</h3><p class="cw-help">${rows.length} จุดใน 24 ชม. · ภายในระยะเส้นตรง 5 กม. จากป่า · ยังไม่ยืนยันเหตุไฟ${rows.length>10?' · แสดง 10 จุดล่าสุด':''}</p>${rows.slice(0,10).map(h=>`<details><summary>จุดใกล้ป่าข้ามเขตอำเภอ · ${date(h.detected_at)}</summary>${root.CmeCoordination.html(h.lat,h.lon,{myForestId:selected.forest_id})}${button('ดูจุดนี้บนแผนที่','locate',`data-lat="${Number(h.lat)}" data-lon="${Number(h.lon)}"`)}</details>`).join('')}</section>`;
  }
  function detailView(){
    const d=state.detail,i=d.incident,name=state.catalog.find(f=>f.forest_id===i.forest_id)?.name||'ป่าชุมชน';
    const invites=d.partners.filter(p=>p.status==='invited'&&(state.me.is_admin||allowedForests().some(f=>f.forest_id===p.forest_id)));
    const coor=state.incidents.find(x=>x.id===i.id)?.coordinator_name;
    return `<div class="cw-actions">${button('กลับรายการเหตุ','back-list')}${button('ดูตำแหน่งบนแผนที่','locate',`data-lat="${i.latitude}" data-lon="${i.longitude}"`)}</div><div class="cw-layout"><section class="cw-section">${root.CmeCoordination?.html(i.latitude,i.longitude,{myForestId:state.forestId})||''}<h2>${esc(name)}</h2>${badge(i.status)}<p class="cw-help">พบ${i.observation==='fire'?'เปลวไฟ':'ควัน'} ${date(i.observed_at)} · รับรายงาน ${date(i.created_at)}<br>พิกัด ${i.latitude.toFixed(5)}, ${i.longitude.toFixed(5)}</p><p class="cw-description">${esc(i.description||'ยังไม่มีรายละเอียดเพิ่มเติม')}</p><p>ผู้รับประสาน: ${i.coordinator_id?esc(i.coordinator_id===state.session.user.id?'คุณ':coor||'ตัวแทนที่รับเรื่อง'):'ยังไม่มีผู้รับประสานในระบบ'}</p>
      <p class="cw-next">ขั้นตอนถัดไป: ${esc({pending:'ผู้รับผิดชอบตรวจสอบรายงานและบันทึกผล',confirmed:'ระบุผู้รับประสานและอัปเดตการดำเนินงาน',coordinating:'บันทึกความคืบหน้าและชุมชนที่ร่วมประสาน',controlled:'ตรวจผลและบันทึกเหตุผลก่อนปิดเหตุ',closed:'เหตุปิดแล้ว เปิดใหม่เมื่อมีหลักฐานเพิ่มเติม',cancelled:'อ่านเหตุผลที่ยกเลิกในประวัติ'}[i.status]||'อ่านประวัติเพื่อติดตามความคืบหน้า')}</p>
      ${d.can_manage&&!i.coordinator_id?button('รับเป็นผู้ประสานเหตุ','claim','',true):''}
      ${invites.map(p=>`<div class="cw-alert">คำขอร่วมประสานสำหรับ ${esc(p.name)}<div class="cw-actions">${button('รับร่วมประสาน','accept',`data-forest="${esc(p.forest_id)}"`,true)}${button('ไม่รับคำขอ','decline',`data-forest="${esc(p.forest_id)}"`)}</div></div>`).join('')}
      ${i.linked_incident_id?`<div class="cw-alert">รายงานนี้เชื่อมกับเหตุหลักแล้ว ประวัติเดิมยังอยู่ ${button('เปิดเหตุหลัก','detail',`data-id="${esc(i.linked_incident_id)}"`)}</div>`:''}<h3>ชุมชนที่ขอร่วมประสาน</h3>${d.partners.length?d.partners.map(p=>`<div class="cw-row"><span>${esc(p.name)}</span>${badge(p.status)}</div>`).join(''):'<p class="cw-help">ยังไม่มีคำขอร่วมประสาน</p>'}
      ${d.can_manage&&!i.linked_incident_id?`<details><summary>ขอชุมชนอื่นร่วมประสาน</summary><form class="cw-form" id="cwPartnerForm"><label>ขอร่วมประสานจาก<select name="forest_id" required>${options(state.catalog.filter(f=>f.forest_id!==i.forest_id))}</select></label><p class="cw-help">ตัวแทนที่ได้รับอนุมัติของป่าที่เชิญจะดูพิกัด รูป และประวัติเหตุนี้ได้ เมื่อรับคำขอแล้วจึงเพิ่มบันทึกได้</p><button class="cw-btn">ส่งคำขอร่วมประสาน</button></form></details><form class="cw-form" id="cwStatusForm"><label>เปลี่ยนสถานะ<select name="status">${transitions[i.status].map(s=>`<option value="${s}">${statusNames[s]}</option>`).join('')}</select></label><label>ผลการตรวจสอบหรือเหตุผล<textarea name="note" required maxlength="2000"></textarea></label><button class="cw-btn primary">บันทึกสถานะ</button></form>${i.status!=='pending'?button(i.published?'หยุดเผยแพร่สรุป':'เผยแพร่สรุปชื่อป่าและสถานะ','publish'):''}<p class="cw-help">สรุปสาธารณะแสดงชื่อป่า สถานะ และเวลา ไม่เผยชื่อผู้แจ้ง พิกัดละเอียด หรือบันทึกภายใน</p>`:''}
      ${d.can_manage&&i.status==='pending'&&!i.linked_incident_id?`<details><summary>รายงานนี้เป็นเหตุเดียวกับรายการเดิม</summary><form class="cw-form" id="cwMergeForm"><label>เหตุหลัก<select name="target_id" required><option value="">เลือกเหตุที่ยังเปิดในป่าเดียวกัน</option>${state.incidents.filter(t=>t.id!==i.id&&t.forest_id===i.forest_id&&!t.linked_incident_id&&!['closed','cancelled'].includes(t.status)).map(t=>`<option value="${esc(t.id)}">${esc(statusNames[t.status])} · ${date(t.observed_at)} · ${esc(t.description.slice(0,60))}</option>`).join('')}</select></label><label>เหตุผลที่เป็นเหตุเดียวกัน<textarea name="note" required maxlength="2000"></textarea></label><p class="cw-help">รายการนี้จะยกเลิกการนับเป็นเหตุแยก และเชื่อมไปยังเหตุหลัก ประวัติและรูปต้นทางยังคงอยู่</p><button class="cw-btn">เชื่อมรายงานกับเหตุหลัก</button></form></details>`:''}${fieldChecksView(d)}${photosView(d)}<p class="cw-help">การรับประสานในเว็บไม่ใช่การแต่งตั้งผู้สั่งการตามกฎหมาย</p></section><section class="cw-section"><h2>ประวัติเหตุ</h2><ol class="cw-timeline">${d.events.map(e=>`<li><strong>${esc(eventNames[e.kind]||'อัปเดตเหตุ')}${e.status_to?' · '+esc(statusNames[e.status_to]):''}</strong><p>${esc(e.note)}</p><small>${esc(e.actor_name)} · ${date(e.created_at)}</small></li>`).join('')}</ol>${state.eventMore!==false&&d.events.length>=200?button('โหลดประวัติเก่ากว่านี้','older-events'):''}${d.can_note?'<form class="cw-form" id="cwNoteForm"><label>เติมรายละเอียดภายหลัง<textarea name="note" required maxlength="2000"></textarea></label><button class="cw-btn">เพิ่มบันทึก</button></form>':''}</section></div>`;
  }
  function fieldChecksView(d){
    const checks=fieldChecks.get(d.incident.id);
    return `<details class="cw-field-checks"><summary>ผลตรวจภาคสนามและเวลาแจ้งเตือน</summary><p class="cw-help">เก็บหลักฐานเพื่อเทียบข้อมูลภายหลัง ยังไม่มีการคำนวณเปอร์เซ็นต์ความแม่นยำ</p><div class="cw-actions">${button('โหลดผลตรวจภาคสนาม','load-checks')}${checks?.length?button('ส่งออกผลตรวจ CSV','export-checks'):''}</div>${checks?root.CmeField.list(checks):'<p class="cw-help">กดโหลดผลตรวจเพื่อดูรายการที่บันทึกไว้</p>'}${d.can_note?root.CmeField.form('cwFieldCheckForm',checks||[]):'<p class="cw-help">รับร่วมประสานก่อนเพิ่มผลตรวจ</p>'}</details>`;
  }
  function mailRow(m){
    return `<article class="cw-row"><div><strong>${esc({test:'อีเมลทดสอบ',daily:'สรุปรายวัน',incident:'การประสานเหตุ',hotspot:'จุดความร้อนใหม่'}[m.category]||m.category)}</strong><p>${date(m.created_at)} · ${esc({pending:'รอส่ง',processing:'กำลังส่ง',sent:'ผู้ให้บริการรับแล้ว',failed:'ส่งไม่สำเร็จ',suppressed:'ระงับการส่ง'}[m.status]||m.status)} · ${esc({provider_accepted:'รอยืนยันการนำส่ง',delivered:'ส่งถึงระบบอีเมลผู้รับแล้ว',bounced:'อีเมลตีกลับ',complained:'ผู้รับแจ้งร้องเรียน',failed:'นำส่งไม่สำเร็จ'}[m.delivery_status]||m.delivery_status||'ยังไม่มีผลนำส่ง')}</p>${m.last_error?`<small>${esc(m.last_error)}</small>`:''}</div></article>`;
  }
  function preferencesView(){
    const p=state.me.preferences,admin=state.me.is_admin,mail=state.mailStatus||[];
    const hours=value=>Array.from({length:24},(_,h)=>`<option value="${h}" ${h===value?'selected':''}>${h.toString().padStart(2,'0')}:00 น.</option>`).join('');
    return `<section class="cw-section">${admin?'<div class="cw-layout cw-preferences-layout"><div>':''}
      <h2>อีเมลของพื้นที่ที่คุณติดตาม</h2><p class="cw-help">ส่งถึงอีเมลที่ยืนยันของบัญชีนี้ เฉพาะป่าที่ได้รับอนุมัติ เมื่อข้อมูลใหม่เข้ามาหรือมีการประสานเหตุ</p>
      ${state.emailMode!=='live'?'<div class="cw-alert">ยังไม่ส่งถึงสมาชิกทั่วไป ขณะนี้ส่งได้เฉพาะอีเมลทดสอบที่กำหนด จะเปิดรับจริงหลังยืนยันโดเมนผู้ส่ง</div>':''}
      <form class="cw-form" id="cwPreferencesForm">
        <label class="cw-checkbox"><input type="checkbox" name="events_enabled" ${p.events_enabled?'checked':''}><span>รับข้อมูลจุดความร้อนใหม่และการประสานเหตุ</span></label>
        <label class="cw-checkbox"><input type="checkbox" name="daily_enabled" ${p.daily_enabled?'checked':''}><span>รับสรุปประจำวัน ตั้งแต่ 08:00 น. ตามรอบตรวจข้อมูล</span></label>
        <label class="cw-checkbox"><input type="checkbox" name="quiet_enabled" ${p.quiet_enabled?'checked':''}><span>พักการส่งในช่วงเวลาที่เลือก</span></label>
        <div class="cw-fields"><label>เริ่มพัก<select name="quiet_start">${hours(p.quiet_start)}</select></label><label>กลับมาส่ง<select name="quiet_end">${hours(p.quiet_end)}</select></label></div>
        <button class="cw-btn primary">บันทึกการรับอีเมล</button>
      </form><p class="cw-help">ยกเลิกรับได้โดยเอาเครื่องหมายออกและบันทึก อีเมลเป็นข้อมูลสำหรับตรวจสอบ ไม่ใช่ช่องทางฉุกเฉิน ข้อมูลดาวเทียมอัปเดตเป็นรอบ</p>
      ${admin?`</div><div>${jobsView()}<p class="cw-help">ผู้รับทดสอบ: ${esc(state.me.test_recipient||'ยังไม่กำหนด')}</p>
        <div class="cw-actions">${button('ส่งอีเมลทดสอบ','test-email')}${button('ตรวจข้อมูลและคิวตอนนี้','run-alerts')}</div>
        <h3>ผลการส่งล่าสุด</h3>${button('อัปเดตผลการส่ง','refresh-mail')}
        ${mail.length?mailRow(mail[0]):state.mailStatus?'<p class="cw-help">ยังไม่มีรายการส่ง</p>':'<p class="cw-help" role="status">กำลังโหลดผลการส่ง…</p>'}
        ${mail.length>1?`<details><summary>ประวัติการส่งก่อนหน้านี้ (${mail.length-1} รายการที่โหลด)</summary>${mail.slice(1).map(mailRow).join('')}</details>`:''}
      </div></div>`:''}</section>`;
  }
  function jobsView(){
    const job=state.jobsStatus;if(!job)return '<p class="cw-help">กำลังตรวจรอบงาน…</p>';
    const runs=job.runs||[],latest=runs.find(r=>r.completed_at),old=!latest||Date.now()-Date.parse(latest.completed_at)>30*60000;
    return `<section class="cw-jobs"><h3>รอบตรวจข้อมูลและคิวอีเมล</h3><p>${job.scheduler_enabled?'ตั้งงานอัตโนมัติทุก '+job.interval_minutes+' นาทีผ่าน '+esc(job.scheduler_provider):'ยังไม่ได้เปิดงานอัตโนมัติตามรอบ'}</p><p class="cw-help">ตรวจเสร็จล่าสุด: ${latest?date(latest.completed_at):'ยังไม่มีรอบที่ตรวจเสร็จ'}${old?' · ควรตรวจการทำงาน':''}<br>รอบเรียกตรวจไม่ใช่ความถี่ที่ดาวเทียมหรือสถานีส่งข้อมูลใหม่</p><details><summary>ดูผลรอบล่าสุด</summary>${runs.slice(0,5).map(r=>`<p class="cw-help">${date(r.started_at)} · ${r.completed_at?'ตรวจเสร็จ':r.run_status==='failed'?'รอบนี้ไม่สำเร็จ จะตรวจซ้ำ':r.lease_until&&Date.parse(r.lease_until)<Date.now()?'รอบนี้หยุดก่อนเสร็จ รอตรวจซ้ำ':'กำลังตรวจ'}${r.summary?' · เข้าคิว '+Number(r.summary.queued||0)+' · ผู้ให้บริการรับ '+Number(r.summary.provider_accepted||0):''}</p>`).join('')||'<p class="cw-help">ยังไม่มีผลรอบงาน</p>'}</details></section>`;
  }
  function reviewView(){return `<section class="cw-section"><h2>ตรวจคำขอตัวแทน</h2><p class="cw-help">ตรวจตัวตนและหน้าที่กับผู้ประสานที่เชื่อถือได้ก่อนอนุมัติ การยืนยันอีเมลอย่างเดียวไม่รับรองว่าเป็นตัวแทนป่า</p>${(state.reviewQueue||[]).map(m=>`<article class="cw-row"><div><h3>${esc(m.name)} · ${esc(m.amphoe)}</h3><p>${esc(m.display_name||'ยังไม่ระบุชื่อ')} · ${esc(m.email)}</p><p>${esc(m.request_note)}</p>${badge(m.status)}<div class="cw-actions">${m.status==='pending'?button('อนุมัติพื้นที่','approve',`data-id="${esc(m.id)}"`,true)+button('ไม่อนุมัติ','reject',`data-id="${esc(m.id)}"`):button('ยกเลิกสิทธิ์พื้นที่','revoke',`data-id="${esc(m.id)}"`)}</div></div></article>`).join('')||'<p class="cw-empty">ไม่มีคำขอในรายการนี้</p>'}</section>`;}
  function render(){
    if(!isOpen())return;
    const priorView=body.dataset.viewKey;
    if(priorView)body.querySelectorAll('details').forEach((d,n)=>detailsOpen.set(priorView+'/'+n,d.open));
    destroyMap();clearPhotos();
    const notices=(state.error?`<div class="cw-alert error" role="alert">${esc(state.error)} ${button('โหลดอีกครั้ง','reload')}</div>`:'')+(state.notice?`<div class="cw-alert" role="status">${esc(state.notice)}</div>`:'');
    let content;
    if(state.ready===false)content='<div class="cw-empty"><h2>ระบบข้อมูลชุมชนยังไม่พร้อม</h2><p>ยังไม่ได้โหลดรายการเหตุหรือสิทธิ์ของคุณ กรุณาลองใหม่ภายหลัง</p></div>';
    else if(state.ready===null)content='<div class="cw-loading" role="status">กำลังโหลดข้อมูลพื้นที่…</div>';
    else if(state.tab==='incidents'&&!state.session)content=`<section class="cw-section"><h2>เหตุที่อนุมัติให้เผยแพร่</h2><p class="cw-help">แสดงสรุปที่ผู้รับผิดชอบเลือกเผยแพร่ รายละเอียดสำหรับประสานอยู่ในพื้นที่ตัวแทน</p>${incidentRows(state.publicIncidents,true)}<div class="cw-actions">${button('เข้าสู่พื้นที่ตัวแทน','signin')}${button('ดูการวิเคราะห์รายอำเภอ (ทดลอง)','legacy-phase')}</div></section>`;
    else if(!state.session)content=loginView();
    else if(!state.me)content='<div class="cw-loading">กำลังตรวจสิทธิ์พื้นที่…</div>';
    else if(state.detail?.incident?.status)content=detailView();
    else if(state.detail)content='<div class="cw-loading">กำลังโหลดประวัติเหตุ…</div>';
    else if(state.tab==='practice')content='<section id="cwPractice"><p class="cw-loading">กำลังโหลดพื้นที่ซ้อม…</p></section>';
    else if(state.tab==='review')content=reviewView();
    else if(state.tab==='preferences')content=preferencesView();
    else if(state.tab==='incidents')content=`<section class="cw-section"><h2>ติดตามและประสานเหตุ</h2><div class="cw-actions">${button(state.scope==='active'?'ดูทุกสถานะ':'ดูเฉพาะเหตุที่ยังไม่ปิด','scope')}${allowedForests().length?button('แจ้งสิ่งที่พบ','create','',true):''}${button('การวิเคราะห์รายอำเภอ (ทดลอง)','legacy-phase')}</div>${incidentRows(state.incidents.filter(i=>state.scope==='all'||!['closed','cancelled'].includes(i.status)))}${state.incidentMore?button('โหลดเหตุเก่ากว่านี้','older-incidents'):''}</section>`;
    else content=forestView();
    body.innerHTML=tabs()+notices+content;
    body.dataset.viewKey=state.tab+'/'+(state.detail?.incident?.id||'')+'/'+state.create;
    body.querySelectorAll('details').forEach((d,n)=>{const open=detailsOpen.get(body.dataset.viewKey+'/'+n);if(open!==undefined)d.open=open;});
    restoreForms();
    if(state.tab==='practice'&&state.session&&state.me&&root.CmePractice)root.CmePractice.attach(document.getElementById('cwPractice'),{api});
    if(state.tab==='forest'&&state.me&&!state.detail&&!state.create)renderMap(forest());
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
          if(state.tab==='review'&&me.is_admin)state.reviewQueue=await api('/review-queue');
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
    if(a==='scope'){state.scope=state.scope==='active'?'all':'active';render();return;}
    if(a==='all-incidents'){state.tab='incidents';state.scope='all';render();return;}
    if(a==='back-list'){state.detail=null;state.tab='incidents';render();return;}
    if(a==='create'){state.create=true;state.tab='forest';state.detail=null;state.draft=state.draft||readDraft()||newDraft();render();return;}
    if(a==='cancel-create'){state.create=false;render();return;}
    if(a==='pick'){saveDraft();context.pick();return;}
    if(a==='gps'){if(!navigator.geolocation){state.error='เบราว์เซอร์นี้ไม่รองรับตำแหน่ง';render();return;}navigator.geolocation.getCurrentPosition(p=>{state.draft.latitude=p.coords.latitude.toFixed(5);state.draft.longitude=p.coords.longitude.toFixed(5);saveDraft();render();},()=>{state.error='ยังไม่ได้รับตำแหน่ง กรุณาเลือกบนแผนที่';render();},{timeout:8000});return;}
    if(a==='locate'){context.locate(Number(b.dataset.lat),Number(b.dataset.lon));return;}
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
        const result=await api('/incidents',{method:'POST',data:{id:state.draft.id,forest_id:values.forest_id,observation:values.observation,latitude:Number(values.latitude),longitude:Number(values.longitude),observed_at:observed,description:values.description}});
        dropDraft();state.create=false;state.tab='incidents';state.notice='บันทึกเหตุสำเร็จแล้ว · รอตรวจสอบ';
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
      else if(form.id==='cwStatusForm')await updateIncident('change_status',{status:values.status,note:values.note});
      else if(form.id==='cwNoteForm')await updateIncident('add_note',{note:values.note});
      else if(form.id==='cwPartnerForm')await updateIncident('invite_partner',{forest_id:values.forest_id});
      else if(form.id==='cwPreferencesForm'){await api('/preferences',{method:'PUT',data:{events_enabled:form.elements.events_enabled.checked,daily_enabled:form.elements.daily_enabled.checked,quiet_enabled:form.elements.quiet_enabled.checked,quiet_start:Number(values.quiet_start),quiet_end:Number(values.quiet_end)}});state.notice='บันทึกการรับอีเมลแล้ว';await load();}
      formDrafts.delete(snapshotKey);
    });
  }
  function input(event){
    const activeForm=event.target.closest('.cw-form');if(activeForm&&activeForm.id!=='cwIncidentForm')rememberForm(activeForm);
    if(event.target.id==='cwForestSearch'){const q=event.target.value.trim();document.getElementById('cwRequestForest').innerHTML=options(state.catalog.filter(f=>(f.name+' '+f.amphoe).includes(q)));}
    if(event.target.closest('#cwIncidentForm')&&event.target.name){if(!state.draft)state.draft=newDraft();state.draft[event.target.name]=event.target.value;saveDraft();}
    if(event.target.id==='cwActiveForest'){state.forestId=event.target.value;render();}
  }
  function authChanged(){sequence++;loading=null;formDrafts.clear();checkRequests.clear();fieldChecks.clear();detailsOpen.clear();root.CmePractice?.reset();clearPhotos();destroyMap();if(body)body.replaceChildren();state.me=null;state.session=null;state.incidents=[];state.detail=null;state.reviewQueue=[];state.mailStatus=[];state.jobsStatus=null;state.draft=null;state.create=false;state.notice='';render();if(isOpen())load();}
  function init(adapter){context=adapter;container=document.getElementById('communityview');body=document.getElementById('communityContent');container.addEventListener('click',click);container.addEventListener('submit',submit);container.addEventListener('input',input);container.addEventListener('change',input);document.getElementById('communityClose').onclick=close;
    const match=location.hash.match(/^#community(?:\/incident\/([a-f0-9-]{36}))?$/i),requested=new URLSearchParams(location.search).get('incident'),fromEmail=/^[a-f0-9-]{36}$/i.test(requested||'')?requested:null;if(location.hash==='#community/practice'&&!fromEmail)open('practice');else if(match||fromEmail)open(fromEmail||match?.[1]?'incidents':'forest',fromEmail||match?.[1]||null);
  }
  root.CmeCommunity={init,open,close,hide,authChanged,api,statusNames,transitions,
    dataChanged:()=>{if(isOpen()&&state.tab==='forest'&&!state.create&&!state.detail&&allowedForests().length)render();},
    newIncident:async(point)=>{await open('forest');if(!state.session){state.notice='เข้าสู่ระบบและรับอนุมัติพื้นที่ก่อนแจ้งเหตุ';render();return;}if(!allowedForests().length){state.notice='ขอสิทธิ์ตัวแทนพื้นที่ก่อนบันทึกเหตุ';render();return;}state.draft=state.draft||readDraft()||newDraft(point);if(point){state.draft.latitude=point.lat;state.draft.longitude=point.lon;}state.create=true;state.detail=null;saveDraft();render();},
    myReports:()=>api('/my-reports'),cancelLegacy:id=>api('/my-reports/'+id+'/cancel',{method:'POST'})};
})(window);
