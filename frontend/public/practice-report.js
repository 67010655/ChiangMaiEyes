/* Practice fire report ("โหมดฝึก"): the same steps as a real report, run entirely in this browser.
   Nothing is sent to the server, no pin reaches other reps and no LINE message goes out, so a
   training group can press "แจ้งไฟ" as often as they like without using the LINE quota or alarming
   real forests. Anyone can practise, with or without an account. The practice pin is kept in this
   browser only and clears itself after a day. */
(function(root){
  'use strict';
  const KEY='cme_practice_pins',DAY=864e5,RISK_KM=5,MAX_ALERTED=10;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const what=p=>p.observation==='fire'?'เปลวไฟ':'ควัน';
  const clock=value=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
  const kmText=km=>km===0?'อยู่ในขอบเขตป่า':km<.1?'น้อยกว่า 0.1 กม.':Number(km).toFixed(1)+' กม.';
  const DIRS=['เหนือ','ตะวันออกเฉียงเหนือ','ตะวันออก','ตะวันออกเฉียงใต้','ใต้','ตะวันตกเฉียงใต้','ตะวันตก','ตะวันตกเฉียงเหนือ'];
  function bearingText(fromLat,fromLon,toLat,toLon){
    const r=Math.PI/180,y=Math.sin((toLon-fromLon)*r)*Math.cos(toLat*r);
    const x=Math.cos(fromLat*r)*Math.sin(toLat*r)-Math.sin(fromLat*r)*Math.cos(toLat*r)*Math.cos((toLon-fromLon)*r);
    return DIRS[Math.round(((Math.atan2(y,x)/r+360)%360)/45)%8];
  }

  // Which forests a real report here would reach: the reporter's own forest (the one the point is in)
  // is never alerted; every other forest within 5 km is, nearest first, at most 10.
  function nearby(lat,lon,nearestFn){
    const rows=(nearestFn?.(lat,lon,30)||[]).filter(r=>Number.isFinite(r.km));
    const own=rows.find(r=>r.km===0)?.forest?.forest_id||null;
    return rows.map(r=>({forest_id:r.forest.forest_id,name:r.forest.name||'ป่าชุมชน',km:Number(r.km.toFixed(1)),
      lat:Number(r.forest.latitude),lon:Number(r.forest.longitude),own:r.forest.forest_id===own}))
      .map(r=>({...r,risk:!r.own&&r.km<=RISK_KM}));
  }
  const alerted=rows=>rows.filter(r=>r.risk).slice(0,MAX_ALERTED);

  // Mirrors the server's pin_alert_text and pin_closed_text, so people practise on the real wording.
  function alertText(p,row){
    const from=p.own_forest||'ป่าชุมชน';
    const dir=Number.isFinite(row.lat)&&Number.isFinite(row.lon)?bearingText(row.lat,row.lon,p.latitude,p.longitude):'';
    const lines=['🚨 มีรายงานไฟใกล้ป่าชุมชนของคุณ',`👁️ ตัวแทน${from} เห็น${what(p)}`,
      row.km===0?`📏 อยู่ภายในขอบเขต${row.name}`:`📏 อยู่ห่างขอบเขต${row.name} ประมาณ ${Number(row.km).toFixed(1)} กม.${dir?` ทางทิศ${dir}ของป่านั้น`:''}`,
      `👤 แจ้งโดย ${p.reporter||'ผู้ฝึก'} · 🕒 พบเมื่อ ${clock(p.observed_at)} น.`];
    if(p.contact_phone)lines.push('☎️ ติดต่อผู้แจ้ง '+p.contact_phone);
    lines.push('','💡 ควรทำ','1. เปิดดูตำแหน่งและรายละเอียดบนแผนที่ (ลิงก์ด้านล่าง)','2. คุยกับผู้แจ้งหรือป่าข้างเคียงเอง ว่าต้องช่วยอะไร',
      '3. ถ้าเห็นไฟหรือควันใกล้ป่าคุณ โทร 1362 (สายด่วนกรมอุทยานฯ แจ้งไฟป่า) ได้เลย','','📍 (ของจริงจะมีลิงก์ไปที่หมุดตรงนี้)','ℹ️ เป็นรายงานจากตัวแทนป่า ยังไม่ใช่การยืนยันจากหน่วยงาน');
    return lines.join('\n');
  }
  const CLOSED={closed:['✅ หมุดไฟใกล้ป่าคุณ จบงานแล้ว','หมุดนี้ถูกปิดว่าจบงานแล้ว และหายจากแผนที่แล้ว'],
    cancelled:['❌ หมุดไฟใกล้ป่าคุณ ถูกบันทึกว่าไม่ใช่ไฟ','หมุดนี้ถูกปิดว่าไม่ใช่ไฟ และหายจากแผนที่แล้ว']};
  function closedText(p,outcome){
    const [head,body]=CLOSED[outcome]||CLOSED.closed;
    return [head,`👁️ รายงานของตัวแทน${p.own_forest||'ป่าชุมชน'} (${what(p)} พบเมื่อ ${clock(p.observed_at)} น.)`,body,'',
      'ℹ️ ถ้ายังเห็นไฟหรือควันใกล้ป่าคุณ โทร 1362 (สายด่วนกรมอุทยานฯ แจ้งไฟป่า) ได้เลย'].join('\n');
  }

  // Drill ("สถานการณ์จำลอง"): a facilitator link (?practice=1&drill=lat,lon) puts one practice satellite
  // hotspot on everyone's map. Pressing "เริ่ม" plays what a rep sees in a real fire: the LINE alert
  // first, then the dot on the map, already about two hours old because satellite data arrives late.
  const DRILL_KEY='cme_practice_drill',LAG_MIN=130;
  function parseDrill(value){
    const m=String(value||'').match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);if(!m)return null;
    const lat=Number(m[1]),lon=Number(m[2]);
    return lat>=17&&lat<=21&&lon>=97.3&&lon<=100?{lat,lon,started_at:null}:null;
  }
  const forestPhrase=name=>(String(name).startsWith('ป่า')?'ใน':'ในป่า ')+name;
  // Mirrors the server's hotspot_text (sent only for hotspots inside a rep's forest boundary).
  function hotspotText(forestName,detectedAt){
    return [`🔥 ดาวเทียมพบจุดความร้อน 1 จุด ${forestPhrase(forestName)}`,`🕒 ตรวจพบล่าสุด ${clock(detectedAt)} น.`,'',
      '💡 ควรทำต่อ','1. ตรวจในพื้นที่ หรือโทรถามคนที่อยู่ใกล้ป่า',
      '2. ถ้าเป็นไฟจริง โทร 1362 (สายด่วนกรมอุทยานฯ แจ้งไฟป่า) และแจ้งหน่วยงานในพื้นที่ อย่าเข้าไปดับคนเดียว',
      '3. ตรวจแล้วบันทึกเหตุในเว็บ คนอื่นจะได้ช่วยติดตาม','','📍 (ของจริงจะมีลิงก์เปิดดูบนแผนที่)',
      'ℹ️ จุดความร้อนยังไม่ใช่เหตุไฟที่ยืนยันแล้ว · ที่มา NASA FIRMS'].join('\n');
  }
  const drillDetected=d=>new Date(Date.parse(d.started_at)-LAG_MIN*6e4).toISOString();

  // Storage: this browser only, a day at most. Broken or blocked storage just means no saved pin.
  function load(now=Date.now()){
    try{const rows=JSON.parse(root.localStorage.getItem(KEY)||'[]');return Array.isArray(rows)?rows.filter(p=>p&&now-Date.parse(p.created_at)<DAY):[];}catch{return [];}
  }
  function save(rows){try{root.localStorage.setItem(KEY,JSON.stringify(rows.slice(-20)));}catch{}}
  function validate(v){
    const lat=Number(v.latitude),lon=Number(v.longitude);
    if(v.latitude===''||v.longitude===''||!Number.isFinite(lat)||!Number.isFinite(lon))return 'ใส่ตำแหน่งก่อน: กด “ใช้ตำแหน่งฉัน” หรือ “เลือกบนแผนที่”';
    if(lat<17||lat>21||lon<97.3||lon>100)return 'ตำแหน่งนี้อยู่นอกจังหวัดเชียงใหม่และพื้นที่ใกล้เคียง';
    const phone=String(v.contact_phone||'').trim();
    if(phone&&!/^[0-9+() \-]{6,20}$/.test(phone))return 'เบอร์โทรใส่ได้เฉพาะตัวเลข เว้นวรรค และ + - ( ) ความยาว 6-20 ตัว';
    if(!v.observed_local)return 'ใส่เวลาที่พบ';
    return '';
  }
  function steps(p){
    const done={1:true,2:true,3:(p.notes||[]).length>0||!!p.closed,4:!!p.closed};
    const cur=!done[3]?3:!done[4]?4:0;
    const items=[[1,'แจ้งเหตุ',clock(p.created_at)+' น.'],[2,'หมุดขึ้น + LINE ป่าใกล้',`จำลอง: แจ้ง ${p.alerted.length} ป่าที่อยู่ใกล้ไม่เกิน 5 กม.`],
      [3,'ติดตาม / อัปเดต',(p.notes||[]).length?`มีบันทึก ${(p.notes||[]).length} ครั้ง`:'ยังไม่มีบันทึกเพิ่ม'],[4,'จบงาน',p.closed?(p.closed==='cancelled'?'ปิดว่าไม่ใช่ไฟ':'จบงานแล้ว'):'กด “จบงาน” เมื่อไฟสงบ']];
    return `<ol class="pr-steps">${items.map(([n,t,s])=>`<li class="${done[n]?'done':n===cur?'now':''}"><b>${done[n]?'✓':n}</b><span>${esc(t)}<small>${esc(s)}</small></span></li>`).join('')}</ol>`;
  }

  let ctx={},el=null,view='form',current=null,draft={},layer=null,picking=false,drill=null;
  function saveDrill(){try{drill?root.sessionStorage.setItem(DRILL_KEY,JSON.stringify(drill)):root.sessionStorage.removeItem(DRILL_KEY);}catch{}}
  function loadDrill(){try{const d=JSON.parse(root.sessionStorage.getItem(DRILL_KEY)||'null');return d&&Number.isFinite(d.lat)&&Number.isFinite(d.lon)?d:null;}catch{return null;}}
  // The forest the drill point is in (only that forest's reps get a real hotspot alert), else the nearest one.
  function drillPlace(){
    const rows=nearby(drill.lat,drill.lon,ctx.nearest),inside=rows.find(r=>r.own);
    const a=ctx.area?.(drill.lat,drill.lon);
    const area=a?.tambon?`ต.${a.tambon} อ.${String(a.district||'-').replace(/^(อำเภอ|อ\.)\s*/,'')}`:a?.district?`อ.${a.district}`:'';
    return {inside,nearest:rows[0]||null,area};
  }
  const nowLocal=()=>{const d=new Date(Date.now()+7*36e5);return d.toISOString().slice(0,16);};
  function active(){return root.document.body.classList.contains('practice-mode');}
  function setActive(on){
    root.document.body.classList.toggle('practice-mode',!!on);
    try{on?root.sessionStorage.setItem('cme_practice','1'):root.sessionStorage.removeItem('cme_practice');}catch{}
    banner();drawPins();
  }
  function banner(){
    let b=root.document.getElementById('practiceBanner');
    if(!active()){b?.remove();return;}
    if(!b){b=root.document.createElement('div');b.id='practiceBanner';b.className='pr-banner';b.setAttribute('role','status');root.document.body.appendChild(b);}
    b.classList.toggle('has-drill',!!drill);
    const drillBtn=!drill?'':drill.started_at?'<button type="button" data-pr="drill-show">🔥 ดูจุดจำลอง</button>':'<button type="button" class="pr-go" data-pr="drill-start">▶ เริ่มสถานการณ์</button>';
    b.innerHTML='<span>🧪 <b>โหมดฝึก</b> <span class="pr-long">กด “แจ้งไฟ” ได้เลย ไม่ส่งข้อมูลจริง ไม่ส่ง LINE</span><span class="pr-short">ไม่ส่งข้อมูลจริง ไม่ส่ง LINE</span></span>'+drillBtn+'<button type="button" data-pr="exit">ออก</button>';
  }
  function drillView(){
    const {inside,nearest,area}=drillPlace(),name=inside?.name||nearest?.name||'ป่าชุมชน';
    return `<h2>ข้อความ LINE (ฝึก)</h2>
      <p class="pr-safe">🧪 ${inside?`ของจริง ตัวแทน${esc(name)}ที่ผูก LINE ไว้จะได้ข้อความนี้`:`จุดนี้อยู่นอกขอบเขตป่าชุมชน ของจริงระบบจะไม่ส่ง LINE เตือน ข้อความนี้คือตัวอย่างถ้าจุดอยู่ใน${esc(name)}`} <b>รอบนี้เป็นการฝึก</b></p>
      ${area?`<p class="pr-what">จุดความร้อนจำลองอยู่ ${esc(area)}</p>`:''}
      <div class="pr-line"><pre>${esc(hotspotText(name,drillDetected(drill)))}</pre></div>
      <h3>ลองคิดก่อนกด</h3>
      <ul class="pr-notes"><li>ได้ข้อความนี้แล้ว จะทำอะไรเป็นอย่างแรก</li><li>จะบอกใคร ทางไหน</li><li>ใครจะออกไปดูที่จุดนั้น</li></ul>
      <div class="pr-row"><button type="button" class="pr-btn primary" data-pr="drill-show">ดูจุดบนแผนที่</button><button type="button" class="pr-btn" data-pr="drill-report">ไปดูแล้ว ฝึกแจ้งไฟที่จุดนี้</button></div>`;
  }
  function startDrill(){
    if(!drill||drill.started_at)return;
    drill.started_at=new Date().toISOString();saveDrill();banner();
    root.setTimeout(()=>{drawPins();toast();},4000);
  }
  function toast(){
    if(!drill)return;
    const {inside,nearest}=drillPlace(),name=inside?.name||nearest?.name||'ป่าชุมชน';
    root.document.getElementById('practiceToast')?.remove();
    const t=root.document.createElement('button');t.type='button';t.id='practiceToast';t.className='pr-toast';t.setAttribute('role','alert');
    t.innerHTML=`<span class="pr-toast-app">LINE</span><span><b>ChiangMaiEyes</b> <small>ตอนนี้ · ฝึก</small><span class="pr-toast-msg">🔥 ดาวเทียมพบจุดความร้อน 1 จุด ${esc(forestPhrase(name))}</span></span>`;
    t.addEventListener('click',()=>{t.remove();view='drill';open({keep:true});});
    root.document.body.appendChild(t);
    try{root.navigator.vibrate?.([200,100,200]);}catch{}
    root.setTimeout(()=>t.remove(),20000);
  }
  function showDrill(){close();ctx.flyTo?.(drill.lat,drill.lon);afterMove(()=>drillMarker?.openPopup());}
  function drillReport(){ctx.map?.()?.closePopup();view='form';draft={latitude:drill.lat.toFixed(5),longitude:drill.lon.toFixed(5)};open({keep:true});}
  function form(){
    const d={observation:'smoke',observed_local:nowLocal(),latitude:'',longitude:'',description:'',contact_phone:'',reporter:'',...draft};draft=d;
    const a=d.latitude!==''&&d.longitude!==''?ctx.area?.(Number(d.latitude),Number(d.longitude)):null;
    const area=a?.status==='matched'?`จุดนี้อยู่ ต.${esc(a.tambon||'-')} อ.${esc(String(a.district||'-').replace(/^(อำเภอ|อ\.)\s*/,''))}`:a?.district?`จุดนี้อยู่ อ.${esc(a.district)}`:'';
    return `<h2>ฝึกแจ้งไฟหรือควัน</h2>
      <p class="pr-safe">🧪 <b>โหมดฝึก</b> ขั้นตอนเหมือนของจริงทุกอย่าง แต่ข้อมูลอยู่ในเครื่องนี้เท่านั้น ไม่มีใครได้รับ LINE</p>
      <form class="pr-form" id="prForm" novalidate>
        <label>ชื่อผู้แจ้ง (ไม่บังคับ)<input name="reporter" maxlength="60" value="${esc(d.reporter)}" placeholder="เช่น สมชาย"></label>
        <label>สิ่งที่พบ<select name="observation"><option value="smoke" ${d.observation==='smoke'?'selected':''}>เห็นควัน</option><option value="fire" ${d.observation==='fire'?'selected':''}>เห็นเปลวไฟ</option></select></label>
        <label>เวลาที่พบ (เวลาประเทศไทย)<input name="observed_local" type="datetime-local" value="${esc(d.observed_local)}"></label>
        <p class="pr-label">ตำแหน่งที่พบ</p>
        <div class="pr-row"><button type="button" class="pr-btn" data-pr="gps">📍 ใช้ตำแหน่งฉันตอนนี้</button><button type="button" class="pr-btn" data-pr="pick">🗺 เลือกบนแผนที่</button></div>
        <div class="pr-row"><label>ละติจูด<input name="latitude" type="number" step="any" value="${esc(d.latitude)}" inputmode="decimal"></label><label>ลองจิจูด<input name="longitude" type="number" step="any" value="${esc(d.longitude)}" inputmode="decimal"></label></div>
        ${area?`<p class="pr-area">${area}</p>`:''}
        <label>เล่าสั้นๆ ว่าเห็นอะไร (ไม่บังคับ)<textarea name="description" maxlength="2000" placeholder="เช่น ควันขึ้นหลังดอย ใกล้ลำห้วย">${esc(d.description)}</textarea></label>
        <label>เบอร์โทรให้ตัวแทนป่าอื่นติดต่อ (ไม่บังคับ)<input name="contact_phone" type="tel" inputmode="tel" maxlength="20" value="${esc(d.contact_phone)}" placeholder="เช่น 081-234-5678"></label>
        <p class="pr-err" id="prErr" role="alert"></p>
        <div class="pr-row"><button class="pr-btn primary" type="submit">ส่งบันทึกเหตุ (ฝึก)</button><button type="button" class="pr-btn" data-pr="close">ยกเลิก</button></div>
      </form>`;
  }
  function result(p){
    const rows=p.alerted,first=rows[0];
    const list=rows.length?`<ul class="pr-near">${rows.map(r=>`<li><b>${esc(r.name)}</b> <span>${esc(kmText(r.km))}</span></li>`).join('')}</ul>`
      :'<p class="pr-muted">ไม่มีป่าชุมชนอื่นในระยะ 5 กม. ถ้าเป็นของจริง จะไม่มีใครได้รับ LINE</p>';
    const notes=(p.notes||[]).map(n=>`<li><small>${esc(clock(n.at))} น.</small> ${esc(n.text)}</li>`).join('');
    return `<h2>${p.closed?'จบงานแล้ว (ฝึก)':'ส่งแล้ว (ฝึก)'}</h2>
      <p class="pr-safe">🧪 ของจริงจะมีหมุดขึ้นให้ตัวแทนป่าทุกคนเห็น และส่ง LINE ไปตามรายชื่อด้านล่าง <b>รอบนี้เป็นการฝึก ไม่มีใครได้รับจริง</b></p>
      <p class="pr-what">เห็น${what(p)} · พบเมื่อ ${esc(clock(p.observed_at))} น.${p.own_forest?` · ในเขต ${esc(p.own_forest)}`:''}</p>
      ${steps(p)}
      <h3>ป่าที่จะได้รับ LINE (${rows.length} ป่า)</h3>${list}
      ${first?`<details class="pr-line" open><summary>ตัวอย่างข้อความ LINE ที่${esc(first.name)}จะได้รับ</summary><pre>${esc(alertText(p,first))}</pre></details>`:''}
      ${p.closed&&rows.length?`<details class="pr-line"><summary>ข้อความ LINE ตอนจบงาน</summary><pre>${esc(closedText(p,p.closed))}</pre></details>`:''}
      ${notes?`<h3>บันทึกความคืบหน้า</h3><ul class="pr-notes">${notes}</ul>`:''}
      ${p.closed?'':`<form class="pr-form" id="prNote"><label>เพิ่มความคืบหน้า<textarea name="note" maxlength="500" placeholder="เช่น ไฟลามขึ้นสันเขา กำลังทำแนวกันไฟ"></textarea></label><div class="pr-row"><button class="pr-btn" type="submit">บันทึก</button></div></form>`}
      <div class="pr-row">${p.closed?'':'<button type="button" class="pr-btn ok" data-pr="done">✅ จบงาน</button><button type="button" class="pr-btn" data-pr="notfire">ไม่ใช่ไฟ</button>'}
        <button type="button" class="pr-btn" data-pr="show">ดูหมุดฝึกบนแผนที่</button></div>
      <div class="pr-row"><button type="button" class="pr-btn primary" data-pr="again">ฝึกแจ้งอีกครั้ง</button><button type="button" class="pr-btn" data-pr="remove">ลบหมุดฝึก</button></div>`;
  }
  function render(){
    if(!el)return;
    el.querySelector('.pr-body').innerHTML=view==='sending'?'<div class="pr-sending" role="status"><span class="pr-spin"></span>กำลังส่ง… <small>(ฝึก)</small></div>':view==='result'&&current?result(current):view==='drill'&&drill?drillView():form();
  }
  function ensure(){
    if(el)return el;
    el=root.document.createElement('div');el.id='practiceReport';el.className='pr-backdrop';
    el.innerHTML='<div class="pr-card" role="dialog" aria-modal="true" aria-label="ฝึกแจ้งไฟ"><button type="button" class="pr-x" data-pr="close" aria-label="ปิด">✕</button><div class="pr-body"></div></div>';
    el.addEventListener('click',onClick);el.addEventListener('submit',onSubmit);el.addEventListener('input',onInput);
    root.document.body.appendChild(el);return el;
  }
  function open(opts={}){
    if(!active())setActive(true);
    ensure();if(opts.lat!=null){draft.latitude=Number(opts.lat).toFixed(5);draft.longitude=Number(opts.lon).toFixed(5);view='form';}
    else if(!opts.keep){view='form';}
    el.classList.add('open');render();
  }
  function close(){el?.classList.remove('open');}
  function onInput(e){const f=e.target.closest('#prForm');if(f&&e.target.name)draft[e.target.name]=e.target.value;}
  function onSubmit(e){
    e.preventDefault();
    if(e.target.id==='prNote'){const t=String(new FormData(e.target).get('note')||'').trim();if(!t)return;
      current.notes=[...(current.notes||[]),{at:new Date().toISOString(),text:t}];persist();render();return;}
    const values=Object.fromEntries(new FormData(e.target));Object.assign(draft,values);
    const err=validate(values);if(err){el.querySelector('#prErr').textContent=err;return;}
    const lat=Number(values.latitude),lon=Number(values.longitude);
    const rows=nearby(lat,lon,ctx.nearest);
    current={id:'practice-'+Date.now().toString(36),practice:true,created_at:new Date().toISOString(),observed_at:values.observed_local+':00+07:00',
      observation:values.observation==='fire'?'fire':'smoke',latitude:lat,longitude:lon,description:String(values.description||'').trim(),
      contact_phone:String(values.contact_phone||'').trim(),reporter:String(values.reporter||'').trim(),
      own_forest:rows.find(r=>r.own)?.name||'',alerted:alerted(rows),notes:[],closed:''};
    view='sending';render();
    root.setTimeout(()=>{persist();draft={};view='result';render();drawPins();},1200);
  }
  function persist(){const rows=load().filter(p=>p.id!==current.id);rows.push(current);save(rows);}
  function onClick(e){
    if(e.target===el){close();return;}
    const a=e.target.closest('[data-pr]')?.dataset.pr;if(!a)return;
    if(a==='close')close();
    else if(a==='gps'){
      if(!root.navigator.geolocation){el.querySelector('#prErr').textContent='เบราว์เซอร์นี้ไม่รองรับตำแหน่ง กรุณาเลือกบนแผนที่';return;}
      root.navigator.geolocation.getCurrentPosition(pos=>{draft.latitude=pos.coords.latitude.toFixed(5);draft.longitude=pos.coords.longitude.toFixed(5);render();},
        ()=>{const box=el.querySelector('#prErr');if(box)box.textContent='ยังไม่ได้รับตำแหน่ง กรุณาเลือกบนแผนที่';},{timeout:8000});
    }
    else if(a==='pick'){picking=true;close();ctx.pick?.();}
    else if(a==='done'||a==='notfire'){current.closed=a==='done'?'closed':'cancelled';persist();render();drawPins();}
    else if(a==='show'){close();ctx.flyTo?.(current.latitude,current.longitude);openPinPopup(current.id);}
    else if(a==='drill-show')showDrill();
    else if(a==='drill-report')drillReport();
    else if(a==='again'){current=null;draft={};view='form';render();}
    else if(a==='remove'){save(load().filter(p=>p.id!==current.id));current=null;draft={};view='form';render();drawPins();}
  }
  // The map hands a picked point here first; true means it was ours.
  function takePick(lat,lon){if(!picking)return false;picking=false;open({lat,lon});return true;}

  function pinIcon(p){
    return `<div class="pr-pin${p.closed?' closed':''}"><span>🧪</span><em>ฝึก</em></div>`;
  }
  function popupHtml(p){
    return `<div class="pr-pop"><p class="pr-kicker">🧪 หมุดฝึก · ไม่มีใครเห็นนอกจากเครื่องนี้</p>
      <h3>เห็น${what(p)}${p.own_forest?' ที่ '+esc(p.own_forest):''}</h3>
      <p>${p.reporter?'แจ้งโดย '+esc(p.reporter)+' · ':''}พบเมื่อ ${esc(clock(p.observed_at))} น.${p.closed?' · '+(p.closed==='cancelled'?'ปิดว่าไม่ใช่ไฟ':'จบงานแล้ว'):''}</p>
      ${root.CmeCoords?.html(p.latitude,p.longitude)||''}
      ${p.description?`<blockquote>${esc(p.description)}</blockquote>`:''}
      <p>ของจริงจะแจ้ง LINE ถึง ${p.alerted.length} ป่า</p>
      <button type="button" class="pr-btn" onclick="CmePracticeReport.reopen('${esc(p.id)}')">เปิดใบเหตุฝึก</button></div>`;
  }
  function drillPopupHtml(){
    const {inside,nearest,area}=drillPlace();
    return `<div class="pr-pop"><p class="pr-kicker">🧪 จุดความร้อนจำลอง · ไม่ใช่ข้อมูลจริง</p>
      <h3>จุดความร้อนจากดาวเทียม${area?' · '+esc(area):''}</h3>
      <p>ตรวจพบ ${esc(clock(drillDetected(drill)))} น. (ข้อมูลดาวเทียมมาช้าราว 2 ชั่วโมง)</p>
      <p>${inside?`อยู่ในเขต${esc(inside.name)}`:nearest?`ห่าง${esc(nearest.name)} ${esc(kmText(nearest.km))}`:''}</p>
      ${root.CmeCoords?.html(drill.lat,drill.lon)||''}
      <p>ยังไม่ใช่ไฟที่ยืนยันแล้ว ต้องมีคนไปดู</p>
      <button type="button" class="pr-btn pr-spread" onclick="CmePracticeReport.drillSpread()">${spreadOn?'ซ่อนแนวลาม':'▶ ดูแนวลามทดลอง 6 ชม.'}</button>
      ${spreadOn?'<p class="pr-spread-key"><i style="background:#ef4444"></i>3 ชม. <i style="background:#f97316"></i>6 ชม. · ถ้ายังไหม้และไม่มีการดับ (โมเดลเดียวกับจุดจริง)</p>':''}
      <button type="button" class="pr-btn" onclick="CmePracticeReport.drillLine()">ข้อความ LINE</button>
      <button type="button" class="pr-btn" onclick="CmePracticeReport.drillReport()">ฝึกแจ้งไฟที่จุดนี้</button></div>`;
  }
  // Spread outline for the drill point: the same model and live wind as a real point, from the server.
  let spreadFrames=null,spreadOn=false;
  async function drillSpread(){
    const L=ctx.leaflet,map=ctx.map?.();if(!drill||!L||!map)return;
    if(spreadOn){spreadOn=false;drawPins();return;}
    try{
      if(!spreadFrames||spreadFrames.key!==drill.lat+','+drill.lon){
        const r=await root.fetch((ctx.apiBase||'')+`/api/spread/practice?lat=${drill.lat}&lon=${drill.lon}`,{cache:'no-store'});
        const data=await r.json().catch(()=>({}));
        const frames=(data.frames||[]).map(f=>({hours:f.hours,geometry:f.geometry?.features?.[0]?.geometry})).filter(f=>f.geometry);
        if(!r.ok||!frames.length)throw new Error(typeof data.detail==='string'?data.detail:'คำนวณแนวลามไม่ได้ตอนนี้ ลองใหม่อีกครั้ง');
        spreadFrames={key:drill.lat+','+drill.lon,frames};
      }
      spreadOn=true;map.closePopup();drawPins();
      const last=spreadFrames.frames[spreadFrames.frames.length-1];
      map.fitBounds(L.geoJSON(last.geometry).getBounds(),{padding:[40,40],maxZoom:15});
      root.setTimeout(()=>drillMarker?.openPopup(),900);
    }catch(error){root.alert?.(error.message||'คำนวณแนวลามไม่ได้ตอนนี้');}
  }
  const POP={maxWidth:300,className:'pr-popup'};
  const markers=new Map();let drillMarker=null;
  function drawPins(){
    const L=ctx.leaflet,map=ctx.map?.();if(!L||!map)return;
    if(!layer)layer=L.layerGroup().addTo(map);
    layer.clearLayers();markers.clear();drillMarker=null;
    if(!active())return;
    if(drill?.started_at&&spreadOn&&spreadFrames)[...spreadFrames.frames].reverse().forEach(f=>{const c=f.hours<=3?'#ef4444':'#f97316';
      L.geoJSON(f.geometry,{interactive:false,style:{color:c,weight:2,dashArray:'5 4',fillColor:c,fillOpacity:f.hours<=3?.2:.1}}).addTo(layer);});
    if(drill?.started_at)drillMarker=L.marker([drill.lat,drill.lon],{icon:L.divIcon({className:'pr-pin-wrap cme-hit',html:'<div class="pr-hot"><span></span><em>ฝึก</em></div>',iconSize:[30,30],iconAnchor:[15,15]}),zIndexOffset:950,title:'จุดความร้อนจำลอง'})
      .bindPopup(drillPopupHtml,POP).addTo(layer);
    load().forEach(p=>{
      const m=L.marker([p.latitude,p.longitude],{icon:L.divIcon({className:'pr-pin-wrap cme-hit',html:pinIcon(p),iconSize:[34,34],iconAnchor:[17,30]}),zIndexOffset:900,title:'หมุดฝึก'})
        .bindPopup(()=>popupHtml(p),POP).addTo(layer);
      markers.set(p.id,m);
    });
  }
  // Open a popup once the fly-to has landed, so it can pan clear of the banner.
  function afterMove(fn){
    const map=ctx.map?.();let done=false;const go=()=>{if(!done){done=true;fn();}};
    map?.once?.('moveend',()=>root.setTimeout(go,50));root.setTimeout(go,2500);
  }
  function openPinPopup(id){afterMove(()=>markers.get(id)?.openPopup());}
  function reopen(id){const p=load().find(x=>x.id===id);if(!p)return;current=p;view='result';ctx.map?.()?.closePopup();open({keep:true});}

  function init(context){
    ctx=context||{};
    let on=false;try{on=root.sessionStorage.getItem('cme_practice')==='1';}catch{}
    drill=on?loadDrill():null;
    const params=new URLSearchParams(root.location.search),linkDrill=parseDrill(params.get('drill'));
    if(linkDrill){drill=linkDrill;saveDrill();}
    if(/^#practice$/i.test(root.location.hash)||params.get('practice')==='1'||linkDrill){on=true;root.history.replaceState(null,'',root.location.pathname);}
    root.document.addEventListener('click',e=>{
      const a=e.target.closest('#practiceBanner [data-pr]')?.dataset.pr;
      if(a==='exit'){close();drill=null;spreadOn=false;spreadFrames=null;saveDrill();root.document.getElementById('practiceToast')?.remove();setActive(false);}
      else if(a==='drill-start')startDrill();
      else if(a==='drill-show')showDrill();
    });
    if(on)setActive(true);
  }
  const drillLine=()=>{ctx.map?.()?.closePopup();view='drill';open({keep:true});};
  root.CmePracticeReport={init,open,close,active,setActive,takePick,reopen,drawPins,nearby,alerted,alertText,closedText,validate,load,save,steps,KEY,
    parseDrill,hotspotText,drillReport,drillLine,drillSpread};
})(window);
