/* Historical maps and a cited reference table. No EVI/fuel/spread model. */
(function(root){
  'use strict';
  const qualifier='ประเมินจากแผนที่ ไม่ใช่การสำรวจในพื้นที่';
  const lddUrl='https://service.ldd.go.th/lpd/node_modules/img/Landusedistrict/2567/r04_ssk_11.pdf';
  const cache=new Map();let reference=null;
  const esc=v=>root.CmeEvidence.escapeHtml(v);
  const selector='[data-land-context-point]';
  const labels={deciduous:'ป่าผลัดใบ (เช่น เต็งรัง/เบญจพรรณ)',evergreen:'ป่าไม่ผลัดใบ',dipterocarp:'ป่าเต็งรัง',mixed_deciduous:'ป่าเบญจพรรณ',unknown_forest:'พื้นที่ป่า/ต้นไม้ (จุดนี้ยังระบุชนิดป่าไม่ได้)',plantation:'ป่าปลูก',built:'ชุมชนและสิ่งปลูกสร้าง',water:'แหล่งน้ำ'};
  function direct(code,name){
    code=String(code||'').trim().toUpperCase();name=String(name||'').trim();
    const namedForest=['','OTHER','O000'].includes(code)&&['เต็งรัง','เบญจพรรณ','ผสมผลัดใบ','ผลัดใบ','ป่าดิบ','ป่าปลูก'].some(word=>name.includes(word));
    if(!/^[AFUW]\d{3}$/.test(code)&&!namedForest)return null;
    if(code.startsWith('A')){
      if(code.startsWith('A9'))return {kind:'water',label:'พื้นที่เพาะเลี้ยงสัตว์น้ำ'};
      return {kind:'crop',label:'พื้นที่เกษตร'+(code==='A101'?' (นาข้าว)':name&&!/[A-Za-z<>]/.test(name)?' ('+name+')':'')};
    }
    if(code.startsWith('U'))return {kind:'built',label:labels.built};
    if(code.startsWith('W'))return {kind:'water',label:labels.water};
    const dd=name.includes('เต็งรัง'),md=name.includes('เบญจพรรณ')||name.includes('ผสมผลัดใบ'),eg=name.includes('ไม่ผลัดใบ')||name.includes('ป่าดิบ');
    const kind=eg&&(dd||md)?'unknown_forest':dd&&md?'deciduous':dd?'dipterocarp':md?'mixed_deciduous':eg?'evergreen':name.includes('ผลัดใบ')||['F200','F201'].includes(code)?'deciduous':['F100','F101'].includes(code)?'evergreen':code.startsWith('F5')||name.includes('ป่าปลูก')?'plantation':'unknown_forest';
    return {kind,label:labels[kind]};
  }
  function point(h){return {latitude:h.lat??h.latitude,longitude:h.lon??h.longitude,landuse_type:h.landuse_type||'',landuse_name:h.landuse_name||''};}
  const headline=d=>d.label+(d.kind==='crop'?' · น่าจะเป็นการเผาในแปลง ไม่ใช่ไฟป่า':'');
  function quick(p){
    const d=direct(p.landuse_type,p.landuse_name);
    return d?{...d,headline:headline(d),sources:[{name:'GISTDA · การใช้ที่ดินกรมพัฒนาที่ดิน',url:lddUrl,year:null,note:'ต้นทางไม่ระบุปีสำรวจการใช้ที่ดิน'}],qualifier,note:'จุดความร้อนยังไม่ยืนยันชนิดไฟหรือสาเหตุ; ไฟในแปลงอาจลามเข้าป่าได้'}:null;
  }
  const detectedAttr=h=>{const t=h.detected_at||h.observed_at||h.reported_at;return t?` data-detected-at="${esc(t)}"`:'';};
  function summary(h){
    const p=point(h),initial=quick(p);
    return `<section class="land-context-summary" data-land-context-point="${esc(JSON.stringify(p))}"${detectedAttr(h)}><p>${esc(initial?initial.headline:'กำลังอ่านชนิดพื้นที่จากแผนที่…')}</p><small>${qualifier}</small></section>`;
  }
  function details(h){return `<div class="land-context-reference" data-land-context-point="${esc(JSON.stringify(point(h)))}"${detectedAttr(h)}><p>กำลังอ่านข้อมูลอ้างอิงชนิดไฟและเชื้อเพลิง…</p><small>${qualifier}</small></div>`;}
  function safeUrl(url){return typeof url==='string'&&url.startsWith('https://')?url:'#';}
  function sourceLinks(sources){return (sources||[]).map(s=>`<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.name)}${s.year?' · ปี '+s.year:''}</a>${s.year?'':' · ปีสำรวจต้นทางไม่ระบุ'}`).join(' · ');}
  function provinceHtml(d){
    const p=d.kind==='unknown_forest'?(d.province_context||reference?.province_context):null;
    return p?`<small class="land-context-provincial">${esc(p.context_text)}</small><small>สถิติระดับจังหวัดในอดีต ไม่ใช่การจำแนกรายจุดหรือสัดส่วนป่าปัจจุบัน · <a href="${esc(safeUrl(p.source_url)+'#page='+p.source_page)}" target="_blank" rel="noopener">กรมป่าไม้ · ตารางที่ ${esc(p.table)} · หน้า ${esc(p.source_page)}</a></small>`:'';
  }
  function paint(node,p,result){
    const d=result||quick(p)||{kind:'unknown',headline:'ยังระบุชนิดพื้นที่ไม่ได้',sources:[],note:'ยังอ่านแผนที่ของจุดนี้ไม่ได้'};
    const profile=d.reference||reference?.profiles?.[d.kind]||reference?.profiles?.unknown;
    const H=root.CmeSpreadHint;
    const rate=d.spread_rate!==undefined?d.spread_rate:(reference?.spread_rates?.[d.kind]||null);
    const sp=H?H.build({wind:H.windNow(),terrain:d.terrain||null,rate,kind:d.kind,ageHours:H.ageHours(node.dataset.detectedAt)}):null;
    if(node.classList.contains('land-context-summary')){
      // Published site measurement, never a value at this hotspot.
      const fuel=profile?.fuel_level?.status==='measured_reference'&&profile.fuel_level.brief?`<small class="land-context-fuel">${esc(profile.fuel_level.brief)} · ค่าจากพื้นที่ศึกษา ไม่ใช่ ณ จุดนี้</small>`:'';
      const spread=sp?.line?`<p class="spread-hint-line">${esc(sp.line)}</p>`:'';
      node.innerHTML=`<p>${esc(d.headline)}</p>${spread}<small>${qualifier}</small>${fuel}${d.sources.length?`<small class="land-context-source">${sourceLinks(d.sources)}</small>`:''}${provinceHtml(d)}`;
    }else{
      const refs=d.reference_sources||reference?.sources||{};
      const fields=[['fire_type','ชนิดไฟที่พบบ่อยในเอกสาร'],['season','ช่วงที่มักเกิดไฟ'],['fuel','เชื้อเพลิงหลักตามเอกสาร'],['fuel_level','ปริมาณเชื้อเพลิง']];
      const rows=profile?fields.map(([key,base])=>{
        const f=profile[key];if(!f)return '';
        const label=key==='fuel_level'&&f.status==='measured_reference'?'ปริมาณเชื้อเพลิงที่เคยวัด (ข้อมูลอ้างอิง)':base;
        const links=(f.refs||[]).map(r=>{const s=refs[r.id];return s?`<a href="${esc(safeUrl(s.url)+(r.page?'#page='+r.page:''))}" target="_blank" rel="noopener">${esc(s.title)}${r.page?' · หน้า '+r.page:''}</a>`:'';}).filter(Boolean).join(' · ');
        return `<div class="land-context-fact"><b>${label}</b><p>${esc(f.text)}</p><small>${qualifier}</small><small>${links}</small></div>`;
      }).join(''):'<p>ยังไม่มีข้อมูลอ้างอิงที่ตรวจสอบได้</p>';
      const factors=d.spread_factors||reference?.spread_factors;
      const spreadRefs=[...(factors?.refs||[]),...(rate?.refs||[])].map(r=>{const s=refs[r.id];return s?`<a href="${esc(safeUrl(s.url)+(r.page?'#page='+r.page:''))}" target="_blank" rel="noopener">${esc(s.title)}${r.page?' · หน้า '+r.page:''}</a>`:'';}).filter(Boolean).join(' · ');
      const spreadHtml=sp?`<div class="land-context-fact spread-hint"><b>ทิศทางที่ไฟอาจลาม (ค่าประมาณ)</b>${sp.details.map(t=>`<p>${esc(t)}</p>`).join('')}<small>${esc(factors?.text||'')}</small><small>ไม่ใช่การพยากรณ์ขอบเขตไฟ ต้องยืนยันในพื้นที่ก่อนตัดสินใจเข้าพื้นที่</small><small>${spreadRefs}</small></div>`:'';
      node.innerHTML=`${spreadHtml}<p>${esc(d.note||'ข้อมูลชนิดพื้นที่ไม่ยืนยันชนิดไฟของเหตุนี้')}</p>${d.sources.map(s=>`<p class="land-context-note">${esc(s.note||'')} · ${qualifier}</p>`).join('')}${rows}<p class="land-context-note">ข้อมูลอ้างอิงทั่วไป ไม่ใช่ค่าที่วัด ณ จุดไฟ ไม่ใช้ EVI ความรุนแรงไฟ หรือคาร์บอนที่สูญเสียแทนน้ำหนักเชื้อเพลิง</p>`;
    }
    node.dispatchEvent(new CustomEvent('cme:coordination-updated',{bubbles:true}));
  }
  async function read(p){
    const key=JSON.stringify(p);if(cache.has(key))return cache.get(key);
    const task=(async()=>{
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
      try{
        if(p.latitude===null||p.longitude===null||!Number.isFinite(Number(p.latitude))||!Number.isFinite(Number(p.longitude)))return null;
        const query=new URLSearchParams(p),response=await fetch('/api/land-context?'+query,{signal:controller.signal,cache:'no-store'});
        if(!response.ok)return null;
        const data=await response.json();
        // Reject a response from an older backend during a staggered release.
        // The withdrawn map must not restore a subtype/profile in this popup.
        if(Array.isArray(data.sources)&&data.sources.some(s=>/CGLS|3939050/i.test((s.name||'')+' '+(s.url||''))))return null;
        return typeof data.headline==='string'&&Array.isArray(data.sources)?data:null;
      }catch{return null;}finally{clearTimeout(timer);}
    })();
    if(cache.size>100)cache.clear();cache.set(key,task);return task;
  }
  async function hydrate(scope=document){
    const nodes=[...(scope.matches?.(selector)?[scope]:[]),...scope.querySelectorAll(selector)];
    await Promise.all(nodes.map(async node=>{
      let p;try{p=JSON.parse(node.dataset.landContextPoint);}catch{return;}
      const result=await read(p);if(node.isConnected)paint(node,p,result);
    }));
  }
  function init(){
    fetch('/land-context-reference.json').then(r=>r.ok?r.json():null).then(data=>{reference=data;return hydrate();}).catch(()=>{});
    new MutationObserver(changes=>changes.forEach(c=>c.addedNodes.forEach(node=>{
      if(node.nodeType===1&&(node.matches(selector)||node.querySelector(selector)))hydrate(node);
    }))).observe(document.body,{childList:true,subtree:true});
  }
  root.CmeLandContext={init,summary,details,hydrate,direct,spreadRate:kind=>reference?.spread_rates?.[kind]||null};
})(window);
