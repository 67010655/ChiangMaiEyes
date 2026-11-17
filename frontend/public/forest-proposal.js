/* "ป่าของฉันยังไม่มีในระบบ": anyone can propose a community forest that is not on the map yet.
   It is sent to the team privately and appears on the map only after the team checks and adds it.
   No account is needed, so it also works during field training. */
(function(root){
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function validate(v){
    const lat=Number(v.latitude),lon=Number(v.longitude);
    if(String(v.name||'').trim().length<2)return 'ใส่ชื่อป่า';
    if(v.latitude===''||v.longitude===''||!Number.isFinite(lat)||!Number.isFinite(lon))return 'ใส่ตำแหน่งป่า: กด “ใช้ตำแหน่งฉัน” หรือ “เลือกบนแผนที่”';
    if(lat<17||lat>21||lon<97.3||lon>100)return 'ตำแหน่งนี้อยู่นอกจังหวัดเชียงใหม่และพื้นที่ใกล้เคียง';
    const phone=String(v.contact_phone||'').trim();
    if(phone&&!/^[0-9+() \-]{6,20}$/.test(phone))return 'เบอร์โทรใส่ได้เฉพาะตัวเลข เว้นวรรค และ + - ( ) ความยาว 6-20 ตัว';
    return '';
  }
  let ctx={},el=null,draft={},view='form',picking=false,sent=null;
  function areaOf(d){
    if(d.latitude===''||d.longitude===''||d.latitude==null)return null;
    const a=ctx.area?.(Number(d.latitude),Number(d.longitude));
    return a?.tambon?{tambon:a.tambon,district:String(a.district||'').replace(/^(อำเภอ|อ\.)\s*/,'')}:a?.district?{tambon:'',district:a.district}:null;
  }
  function form(){
    const d={name:'',village:'',latitude:'',longitude:'',details:'',proposer_name:'',contact_phone:'',...draft};draft=d;
    const a=areaOf(d);
    return `<h2>ป่าของฉันยังไม่มีในระบบ</h2>
      <p class="pr-safe">🌳 ส่งถึง<b>ทีมพัฒนา</b>โดยตรง ทีมจะตรวจสอบแล้วเพิ่มเข้าแผนที่ ป่าจะยังไม่ขึ้นทันที · ไม่ต้องสมัครสมาชิก</p>
      <form class="pr-form" id="fpForm" novalidate>
        <label>ชื่อป่าชุมชน<input name="name" maxlength="120" required value="${esc(d.name)}" placeholder="เช่น ป่าชุมชนบ้านห้วยทราย"></label>
        <label>หมู่บ้าน (ไม่บังคับ)<input name="village" maxlength="120" value="${esc(d.village)}" placeholder="เช่น บ้านห้วยทราย หมู่ 5"></label>
        <p class="pr-label">ตำแหน่งป่า (จุดไหนในป่าก็ได้)</p>
        <div class="pr-row"><button type="button" class="pr-btn" data-fp="gps">📍 ใช้ตำแหน่งฉันตอนนี้</button><button type="button" class="pr-btn" data-fp="pick">🗺 เลือกบนแผนที่</button></div>
        <div class="pr-row"><label>ละติจูด<input name="latitude" type="number" step="any" value="${esc(d.latitude)}" inputmode="decimal"></label><label>ลองจิจูด<input name="longitude" type="number" step="any" value="${esc(d.longitude)}" inputmode="decimal"></label></div>
        ${a?`<p class="pr-area">จุดนี้อยู่ ${a.tambon?'ต.'+esc(a.tambon)+' ':''}อ.${esc(a.district)}</p>`:''}
        <label>เล่าเพิ่ม (ไม่บังคับ)<textarea name="details" maxlength="1000" placeholder="เช่น ขนาดประมาณ 300 ไร่ ขึ้นทะเบียนแล้วหรือยัง ใครดูแล">${esc(d.details)}</textarea></label>
        <div class="pr-row"><label>ชื่อผู้เสนอ (ไม่บังคับ)<input name="proposer_name" maxlength="80" value="${esc(d.proposer_name)}"></label><label>เบอร์โทร (ไม่บังคับ)<input name="contact_phone" type="tel" inputmode="tel" maxlength="20" value="${esc(d.contact_phone)}"></label></div>
        <p class="pr-muted">เบอร์โทรใช้ให้ทีมติดต่อกลับเรื่องนี้เท่านั้น ไม่แสดงบนเว็บ</p>
        <p class="pr-err" id="fpErr" role="alert"></p>
        <div class="pr-row"><button class="pr-btn ok" type="submit">ส่งให้ทีมตรวจสอบ</button><button type="button" class="pr-btn" data-fp="close">ยกเลิก</button></div>
      </form>`;
  }
  function done(){
    return `<h2>ส่งแล้ว ขอบคุณครับ</h2>
      <p class="pr-what">ทีมได้รับข้อเสนอ <b>${esc(sent.name)}</b> แล้ว จะตรวจสอบกับข้อมูลป่าชุมชนและหน่วยงานในพื้นที่ แล้วเพิ่มเข้าแผนที่</p>
      <p class="pr-muted">เลขอ้างอิง ${esc(String(sent.id||'').slice(0,8))}</p>
      <div class="pr-row"><button type="button" class="pr-btn primary" data-fp="again">เสนอป่าอื่น</button><button type="button" class="pr-btn" data-fp="close">ปิด</button></div>`;
  }
  function render(){if(el)el.querySelector('.pr-body').innerHTML=view==='sending'?'<div class="pr-sending" role="status"><span class="pr-spin"></span>กำลังส่ง…</div>':view==='done'?done():form();}
  function ensure(){
    if(el)return el;
    el=root.document.createElement('div');el.id='forestProposal';el.className='pr-backdrop';
    el.innerHTML='<div class="pr-card" role="dialog" aria-modal="true" aria-label="เสนอป่าชุมชนที่ยังไม่มีในระบบ"><button type="button" class="pr-x" data-fp="close" aria-label="ปิด">✕</button><div class="pr-body"></div></div>';
    el.addEventListener('click',onClick);el.addEventListener('submit',onSubmit);
    el.addEventListener('input',e=>{if(e.target.closest('#fpForm')&&e.target.name)draft[e.target.name]=e.target.value;});
    root.document.body.appendChild(el);return el;
  }
  function open(opts={}){
    ensure();
    if(opts.lat!=null){draft.latitude=Number(opts.lat).toFixed(5);draft.longitude=Number(opts.lon).toFixed(5);view='form';}
    else if(view==='done')view='form';
    el.classList.add('open');render();
  }
  function close(){el?.classList.remove('open');}
  async function onSubmit(e){
    e.preventDefault();
    const values=Object.fromEntries(new FormData(e.target));Object.assign(draft,values);
    const err=validate(values);if(err){el.querySelector('#fpErr').textContent=err;return;}
    const a=areaOf(values)||{};
    const body={name:values.name.trim(),village:values.village.trim(),tambon:a.tambon||'',district:a.district||'',latitude:Number(values.latitude),longitude:Number(values.longitude),
      details:values.details.trim(),proposer_name:values.proposer_name.trim(),contact_phone:values.contact_phone.trim()||null};
    view='sending';render();
    try{
      const r=await root.fetch((ctx.apiBase||'')+'/api/community/forest-proposals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
      const data=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'ส่งไม่สำเร็จ ลองใหม่อีกครั้ง');
      sent={name:body.name,id:data.id};draft={};view='done';render();
    }catch(error){view='form';render();el.querySelector('#fpErr').textContent=error.message||'ส่งไม่สำเร็จ ลองใหม่อีกครั้ง';}
  }
  function onClick(e){
    if(e.target===el){close();return;}
    const a=e.target.closest('[data-fp]')?.dataset.fp;if(!a)return;
    if(a==='close')close();
    else if(a==='again'){sent=null;draft={};view='form';render();}
    else if(a==='pick'){picking=true;close();ctx.pick?.();}
    else if(a==='gps'){
      if(!root.navigator.geolocation){el.querySelector('#fpErr').textContent='เบราว์เซอร์นี้ไม่รองรับตำแหน่ง กรุณาเลือกบนแผนที่';return;}
      root.navigator.geolocation.getCurrentPosition(pos=>{draft.latitude=pos.coords.latitude.toFixed(5);draft.longitude=pos.coords.longitude.toFixed(5);render();},
        ()=>{const box=el.querySelector('#fpErr');if(box)box.textContent='ยังไม่ได้รับตำแหน่ง กรุณาเลือกบนแผนที่';},{timeout:8000});
    }
  }
  // The map hands a picked point here first; true means it was ours.
  function takePick(lat,lon){if(!picking)return false;picking=false;open({lat,lon});return true;}
  function init(context){ctx=context||{};}
  root.CmeForestProposal={init,open,close,takePick,validate};
})(window);
