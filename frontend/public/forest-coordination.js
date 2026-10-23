/* PRODUCT_BRIEF #7. Public geography; approved personal contacts fetched only
   with a confirmed session, never bundled in the forest catalog or persisted. */
(function(root){
  'use strict';
  let context={},epoch=0,agencies=[],agencyState='loading';
  const requests=new Map(),controllers=new Set();
  const boundPopups=new WeakSet();
  const esc=value=>root.CmeEvidence.escapeHtml(value);
  const coord=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value));
  const valid=(lat,lon)=>coord(lat)&&coord(lon)&&Math.abs(Number(lat))<=90&&Math.abs(Number(lon))<=180;
  const point=(lat,lon)=>({lat:Number(lat),lon:Number(lon)});
  const distance=(a,b)=>root.CmeEvidence.distanceKm(a,b);
  const polygons=g=>g?.type==='Feature'?polygons(g.geometry):g?.type==='Polygon'?[g.coordinates]:g?.type==='MultiPolygon'?g.coordinates:[];
  function onSegment(p,a,b){
    const cross=(p.lon-a[0])*(b[1]-a[1])-(p.lat-a[1])*(b[0]-a[0]);
    return Math.abs(cross)<1e-10&&p.lon>=Math.min(a[0],b[0])-1e-10&&p.lon<=Math.max(a[0],b[0])+1e-10&&p.lat>=Math.min(a[1],b[1])-1e-10&&p.lat<=Math.max(a[1],b[1])+1e-10;
  }
  function ringState(p,ring){
    let inside=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const a=ring[j],b=ring[i];
      if(onSegment(p,a,b))return 2;
      if((a[1]>p.lat)!==(b[1]>p.lat)&&p.lon<(b[0]-a[0])*(p.lat-a[1])/(b[1]-a[1])+a[0])inside=!inside;
    }
    return inside?1:0;
  }
  function covers(p,g){
    return polygons(g).some(rings=>{
      if(!rings.length||!ringState(p,rings[0]))return false;
      return !rings.slice(1).some(r=>ringState(p,r)===1);
    });
  }
  // Local tangent-plane projection locates the closest point on each edge;
  // the final point-to-edge distance is in kilometres on WGS84 lon/lat.
  function boundaryDistance(p,g){
    if(covers(p,g))return 0;
    let best=Infinity;
    const cos=Math.cos(p.lat*Math.PI/180);
    for(const rings of polygons(g))for(const ring of rings)for(let i=1;i<ring.length;i++){
      const a=ring[i-1],b=ring[i],dx=(b[0]-a[0])*cos,dy=b[1]-a[1],len=dx*dx+dy*dy;
      const t=len?Math.max(0,Math.min(1,((p.lon-a[0])*cos*dx+(p.lat-a[1])*dy)/len)):0;
      best=Math.min(best,distance(p,{lat:a[1]+t*(b[1]-a[1]),lon:a[0]+t*(b[0]-a[0])}));
    }
    return best;
  }
  const districtName=v=>String(v||'').replace(/^(อำเภอ|อ\.)\s*/,'').trim();
  function administrativeArea(lat,lon){
    if(!valid(lat,lon))return {status:'invalid'};
    const p=point(lat,lon),tambons=context.tambons?.()||[],districts=context.districts?.()||[];
    const matches=tambons.filter(f=>covers(p,f.geometry));
    if(matches.length===1){const f=matches[0].properties;return {status:'matched',tambon:f.tambon_th||f.T_NAME_T,district:f.amphoe_th||f.A_NAME_T};}
    const ds=[...new Set(districts.filter(f=>covers(p,f.geometry)).map(f=>f.properties.amp_th||f.properties.nameTh))];
    return {status:matches.length>1?'ambiguous':!tambons.length?'loading':'unmatched',district:ds.length===1?ds[0]:null};
  }
  function nearest(lat,lon,forests=context.forests?.()||[],count=3){
    if(!valid(lat,lon))return [];
    const p=point(lat,lon);
    return forests.map(f=>{
      let km=f.boundary_quality!=='needs_review'?boundaryDistance(p,f.boundary):Infinity,method='boundary';
      if(!Number.isFinite(km)&&valid(f.latitude,f.longitude)){km=distance(p,point(f.latitude,f.longitude));method='reference';}
      return {forest:f,km,method};
    }).filter(r=>Number.isFinite(r.km)).sort((a,b)=>a.km-b.km||String(a.forest.forest_id).localeCompare(String(b.forest.forest_id))).slice(0,count);
  }
  function areaText(area){
    if(area.status==='matched')return `จุดนี้อยู่ ต.${esc(area.tambon||'ยังไม่ทราบ')} อ.${esc(area.district||'ยังไม่ทราบ')}`;
    const suffix=area.status==='ambiguous'?'จุดทับขอบเขตหลายตำบล รอตรวจสอบ':area.status==='loading'?'กำลังโหลดขอบเขตตำบล':area.status==='invalid'?'พิกัดไม่ถูกต้อง':'ไม่พบตำบลในชุดขอบเขตที่มี';
    return `${area.district?'จุดนี้อยู่ อ.'+esc(area.district)+' · ':''}${suffix}`;
  }
  const kmText=km=>km===0?'อยู่ในขอบเขต':km<.1?'น้อยกว่า 0.1 กม.':km.toFixed(1)+' กม.';
  const districtKey=v=>{const name=districtName(v);return name==='เมือง'?'เมืองเชียงใหม่':name==='ดอยสะเก็ต'?'ดอยสะเก็ด':name;};
  const tambonKey=v=>String(v||'').replace(/^(ต\.|ตำบล)\s*/,'').trim();
  function geometryReference(g){
    let weight=0,x=0,y=0;
    for(const rings of polygons(g))rings.forEach((ring,index)=>{
      let area2=0,cx=0,cy=0;
      for(let i=0,j=ring.length-1;i<ring.length;j=i++){
        const a=ring[j],b=ring[i],cross=a[0]*b[1]-b[0]*a[1];
        area2+=cross;cx+=(a[0]+b[0])*cross;cy+=(a[1]+b[1])*cross;
      }
      if(Math.abs(area2)<1e-12)return;
      const w=Math.abs(area2)*(index===0?1:-1);
      weight+=w;x+=w*cx/(3*area2);y+=w*cy/(3*area2);
    });
    return weight>0?{lat:y/weight,lon:x/weight}:null;
  }
  function agencyReference(a){
    const t=(context.tambons?.()||[]).find(f=>districtKey(f.properties.amphoe_th||f.properties.A_NAME_T)===districtKey(a.district)&&tambonKey(f.properties.tambon_th||f.properties.T_NAME_T)===tambonKey(a.tambon));
    if(t){const p=geometryReference(t.geometry);if(p)return {...p,scope:'ตำบล'};}
    const d=(context.districts?.()||[]).find(f=>districtKey(f.properties.amp_th||f.properties.nameTh)===districtKey(a.district));
    const p=d?geometryReference(d.geometry):null;
    return p?{...p,scope:'อำเภอ'}:null;
  }
  function selectAgencies(lat,lon){
    const list=context.agencies?.()||agencies,area=administrativeArea(lat,lon);
    if(!valid(lat,lon))return {method:'unavailable',rows:[]};
    const sameDistrict=area.district?list.filter(a=>districtKey(a.district)===districtKey(area.district)):[];
    const sameTambon=area.status==='matched'?sameDistrict.filter(a=>a.tambon&&tambonKey(a.tambon)===tambonKey(area.tambon)):[];
    if(sameTambon.length)return {method:'tambon',rows:sameTambon.map(agency=>({agency}))};
    if(sameDistrict.length)return {method:'district',rows:sameDistrict.map(agency=>({agency}))};
    const rows=list.map(agency=>{
      const reference=agencyReference(agency);
      return reference?{agency,reference,km:distance(point(lat,lon),reference)}:null;
    }).filter(Boolean).sort((a,b)=>a.km-b.km||a.agency.name.localeCompare(b.agency.name)).slice(0,1);
    return {method:rows.length?'nearest':'unavailable',rows};
  }
  function agencyHtml(lat,lon,{includeEmergency=true}={}){
    const selected=selectAgencies(lat,lon),labels={tambon:'หน่วยงานในตำบลเดียวกัน',district:'หน่วยงานในอำเภอเดียวกัน',nearest:'หน่วยงานใกล้ที่สุดโดยประมาณ'};
    const rows=selected.rows.map(({agency:a,reference})=>`<div class="coordination-office"><strong>${esc(a.name)}</strong><br>ที่ตั้ง ${a.tambon?'ต.'+esc(a.tambon)+' ':''}อ.${esc(a.district)}<br>${a.phones.map(p=>`<a href="tel:${esc(p)}">${esc(p.slice(0,3)+'-'+p.slice(3))}</a>`).join(' · ')}<small class="cf-src"><a href="${esc(a.source)}" target="_blank" rel="noopener">ต้นทางกรมป่าไม้</a> · ตรวจ ${esc(a.checked_on)}</small>${reference?`<p class="coordination-note">ประมาณจากจุดกึ่งกลางขอบเขต${reference.scope}ที่ตั้ง ไม่ใช่พิกัดจริงของหน่วยงาน</p>`:''}</div>`).join('');
    const hasFallback=selected.rows.some(r=>r.agency.phones.includes('052081758'));
    return `${rows?`<h4 class="coordination-sub">${labels[selected.method]}</h4>${rows}<p class="coordination-note">หน่วยงานในพื้นที่ ไม่ใช่การมอบหมายผู้รับผิดชอบ</p>`:`<p>${agencyState==='loading'?'กำลังโหลดเบอร์หน่วยงานในพื้นที่…':'ยังเลือกหน่วยงานในพื้นที่จากข้อมูลที่มีไม่ได้'}</p>`}<p>${hasFallback?'':`ช่องทางสำรอง: <a href="tel:052081758">สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่) · 052-081758</a> · <a href="https://forestinfo.forest.go.th/telephone_region.aspx" target="_blank" rel="noopener">บัญชีโทรศัพท์กรมป่าไม้</a><br>`}${includeEmergency?'พบไฟ แจ้งสายด่วนกรมอุทยานฯ <a href="tel:1362">1362</a>':''}</p>`;
  }
  async function loadAgencies(){
    if(context.agencies){agencyState='ready';return;}
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch('/forest-agency-contacts.json',{signal:controller.signal});
      if(!response.ok)throw new Error('agency_directory_unavailable');
      const data=await response.json();
      if(!Array.isArray(data.agencies))throw new Error('agency_directory_invalid');
      agencies=data.agencies.filter(a=>typeof a.name==='string'&&typeof a.district==='string'&&a.source==='https://forestinfo.forest.go.th/telephone_region.aspx'&&/^\d{4}-\d{2}-\d{2}$/.test(a.checked_on)&&Array.isArray(a.phones)&&a.phones.length&&a.phones.every(p=>/^0\d{8,9}$/.test(p)));
      agencyState='ready';
    }catch{agencyState='unavailable';}finally{clearTimeout(timer);}
    document.querySelectorAll('[data-agency-slot]').forEach(slot=>{
      const card=slot.closest('.coordination-card');
      if(card){const result=root.CmeProtectedAreas?.query(Number(card.dataset.coordinationLat),Number(card.dataset.coordinationLon));slot.innerHTML=agencyHtml(Number(card.dataset.coordinationLat),Number(card.dataset.coordinationLon),{includeEmergency:!['inside','near'].includes(result?.status)});card.dispatchEvent(new CustomEvent('cme:coordination-updated',{bubbles:true}));}
    });
  }
  function forestDistrict(f){
    // Some legacy catalog district labels disagree with the admin polygons.
    // Prefer the administrative area at the forest reference point.
    return administrativeArea(f.latitude,f.longitude).district||f.amphoe;
  }
  function crossDistrict(lat,lon,myForestId,rows=nearest(lat,lon)){
    const mine=(context.forests?.()||[]).find(f=>f.forest_id===myForestId),area=administrativeArea(lat,lon);
    return !!(mine&&rows[0]?.forest.forest_id===myForestId&&area.district&&districtName(area.district)!==districtName(forestDistrict(mine)));
  }
  // Two registrations can share a name and district; list that forest once, at its nearer distance.
  function distinctByName(rows){const seen=new Set();return rows.filter(r=>{const key=(r.forest.name||'')+'|'+forestDistrict(r.forest);if(seen.has(key))return false;seen.add(key);return true;});}
  // Who looks after this point, in reading order: where it is, the 3 nearest forests (one line each),
  // the office to call. Caveats sit in a closed "ข้อควรรู้" so the card stays short.
  function content(lat,lon,myForestId){
    const rows=distinctByName(nearest(lat,lon,context.forests?.()||[],6)).slice(0,3),area=administrativeArea(lat,lon);
    const protectedResult=root.CmeProtectedAreas?.query(lat,lon),protectedLead=protectedResult&&root.CmeProtectedAreas.leadHtml(protectedResult,areaText(area));
    const forestRows=rows.map(r=>`<li class="coordination-forest"><span class="cf-top"><strong>${esc(r.forest.name)}</strong><b class="cf-km">${kmText(r.km)}${r.method==='reference'?' (จุดอ้างอิงป่า)':''}</b></span><span class="cf-sub">อ.${esc(forestDistrict(r.forest)||'ยังไม่ทราบ')} · <span data-contact-forest="${esc(r.forest.forest_id)}" aria-live="polite">กำลังตรวจสอบผู้ประสานงาน…</span></span></li>`).join('');
    const caveats=(protectedResult?root.CmeProtectedAreas.detailsHtml(protectedResult):'')+
      '<p class="coordination-note">ระยะเส้นตรง ไม่ใช่ระยะเดินทาง วัดถึงขอบเขตป่า · ถ้าขอบเขตรอตรวจ ใช้จุดอ้างอิงป่า · ความใกล้ไม่ใช่การมอบหมายผู้รับผิดชอบ</p>';
    return `<h3>ใครดูแลจุดนี้</h3><p class="coordination-lead">📍 ${protectedLead||areaText(area)}</p>`+
      (protectedResult&&myForestId?root.CmeProtectedAreas.warningHtml(protectedResult):'')+
      (crossDistrict(lat,lon,myForestId,rows)?`<p class="coordination-cross">อยู่นอกเขตอำเภอ แต่ป่าเราใกล้ที่สุด · ป่าข้างเคียง: ${rows.slice(1).map(r=>esc(r.forest.name)).join(', ')||'ยังไม่มีข้อมูล'}</p>`:'')+
      `<h4 class="coordination-sub">${protectedLead?'ป่าชุมชนใกล้เคียง:':'ป่าชุมชนที่ใกล้ที่สุด:'}</h4>`+
      (rows.length?`<ul class="coordination-forests">${forestRows}</ul>`:'<p class="coordination-note">กำลังรอข้อมูลป่าชุมชน</p>')+
      `<div class="coordination-agency" data-agency-slot>${agencyHtml(lat,lon,{includeEmergency:!protectedLead})}</div>`+
      `<details class="coordination-more"><summary>ข้อควรรู้และที่มา</summary>${caveats}</details>`;
  }

  function html(lat,lon,{myForestId=''}={}){
    if(!valid(lat,lon))return '<section class="coordination-card"><h3>ใครดูแลจุดนี้</h3><p>ยังไม่มีพิกัดที่ใช้ระบุพื้นที่ได้ · พบไฟ โทร <a href="tel:1362">1362</a> <small class="hotline-what">(สายด่วนกรมอุทยานฯ แจ้งไฟป่า)</small></p></section>';
    return `<section class="coordination-card" data-coordination-lat="${Number(lat)}" data-coordination-lon="${Number(lon)}" data-my-forest="${esc(myForestId)}">${content(lat,lon,myForestId)}</section>`;
  }
  function cards(scope){return [...(scope.matches?.('.coordination-card')?[scope]:[]),...scope.querySelectorAll('.coordination-card[data-coordination-lat]')];}
  function contactHtml(row,signedIn,access){
    if(access==='approval_required')return 'รออนุมัติสิทธิ์ตัวแทนก่อนจึงจะดูผู้ประสานงานได้';
    if(!row)return 'ยังตรวจสอบผู้ประสานงานไม่ได้';
    if(signedIn){
      if(!Array.isArray(row.representatives))return 'ยังตรวจสอบผู้ประสานงานไม่ได้';
      if(!row.representatives.length)return 'ยังไม่มีผู้ประสานงานของป่านี้';
      return row.representatives.map(r=>`${esc(r.name)} · <a class="coordination-contact" href="mailto:${esc(encodeURIComponent(r.email))}">ติดต่อทางอีเมล</a>`).join('<br>');
    }
    return row.has_representative===true?'มีตัวแทนแล้ว · เข้าสู่ระบบเพื่อดูชื่อและปุ่มติดต่อ':row.has_representative===false?'ยังไม่มีผู้ประสานงานของป่านี้':'ยังตรวจสอบผู้ประสานงานไม่ได้';
  }
  async function fetchContacts(ids,uid,version){
    const key=JSON.stringify([uid,ids]),cached=requests.get(key);
    if(cached&&cached.until>Date.now())return cached.promise;
    const promise=(async()=>{
      const session=uid?await context.session?.():null;
      if(version!==epoch||uid!==(context.user?.()?.id||''))return null;
      if(uid&&(!session||session.user.id!==uid))return null;
      const controller=new AbortController();controllers.add(controller);
      const timer=setTimeout(()=>controller.abort(),12000);
      try{
        const query=new URLSearchParams();ids.forEach(id=>query.append('forest_ids',id));
        const response=await fetch((context.apiBase||'')+'/api/community/'+(uid?'forest-contacts':'contact-status')+'?'+query,{headers:uid?{Authorization:'Bearer '+session.access_token}:{},cache:'no-store',signal:controller.signal});
        if(uid&&response.status===403)return {access:'approval_required'};
        if(!response.ok)throw new Error('contacts_unavailable');
        const result=await response.json();return Array.isArray(result)?result:null;
      }catch{return null;}finally{clearTimeout(timer);controllers.delete(controller);}
    })();
    // Memory only. Sign-out aborts requests and invalidates every response.
    if(requests.size>100)requests.clear();
    requests.set(key,{promise,until:Date.now()+20000});return promise;
  }
  async function hydrate(scope=document){
    const version=epoch,uid=context.user?.()?.id||'';
    await Promise.all(cards(scope).map(async card=>{
      const slots=[...card.querySelectorAll('[data-contact-forest]')],ids=slots.map(s=>s.dataset.contactForest);
      if(!ids.length)return;
      const result=await fetchContacts(ids,uid,version);
      if(version!==epoch||uid!==(context.user?.()?.id||'')||!card.isConnected)return;
      slots.forEach(slot=>{if(slot.isConnected)slot.innerHTML=contactHtml(Array.isArray(result)?result.find(r=>r.forest_id===slot.dataset.contactForest):null,!!uid,result?.access);});
      card.dispatchEvent(new CustomEvent('cme:coordination-updated',{bubbles:true}));
    }));
  }
  function refresh(scope=document){
    cards(scope).forEach(card=>{if(card.dataset.coordinationLat!==undefined)card.innerHTML=content(Number(card.dataset.coordinationLat),Number(card.dataset.coordinationLon),card.dataset.myForest);});
    return hydrate(scope);
  }
  function authChanged(){epoch++;controllers.forEach(c=>c.abort());controllers.clear();requests.clear();return refresh();}
  function popupOpened(popup){
    const el=popup.getElement();
    if(el&&!boundPopups.has(el)){
      boundPopups.add(el);
      el.addEventListener('cme:coordination-updated',()=>{
        if(!popup.isOpen())return;
        // Leaflet 1.9.4 update() also re-runs function content, replacing the
        // hydrated card and starting another fetch/render cycle. Reflow the
        // existing DOM only, preserving the contact response and scroll state.
        popup._updateLayout();popup._updatePosition();popup._adjustPan();
      });
    }
  }
  function nearbyCrossDistrict(items,mine,{radiusKm=5}={}){
    return root.CmeEvidence.filterHotspots(items.map(h=>({...h,lat:h.lat??h.latitude,lon:h.lon??h.longitude}))).filter(h=>{
      const rows=nearest(h.lat,h.lon);
      return rows[0]?.km<=radiusKm&&crossDistrict(h.lat,h.lon,mine.forest_id,rows);
    });
  }
  function init(adapter){
    context=adapter;
    loadAgencies();
    new MutationObserver(changes=>changes.forEach(change=>change.addedNodes.forEach(node=>{
      if(node.nodeType===1&&(node.matches('.coordination-card')||node.querySelector('.coordination-card')))hydrate(node);
    }))).observe(document.body,{childList:true,subtree:true});
  }
  root.CmeCoordination={init,html,hydrate,refresh,authChanged,popupOpened,nearest,administrativeArea,boundaryDistance,covers,crossDistrict,nearbyCrossDistrict,selectAgencies,geometryReference};
})(window);
