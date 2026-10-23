/* Shared form/export for real field observations and explicitly labelled exercises. */
(function(root){
  'use strict';
  const outcomes={fire_found:'ตรวจแล้วพบไฟ',no_fire_found:'ตรวจแล้วไม่พบไฟ',unverified:'ยังตรวจไม่ได้'};
  const methods={on_site:'ไปตรวจในพื้นที่',phone:'ยืนยันผ่านผู้ประสาน',photo:'ตรวจจากภาพและบริบท',unavailable:'ยังไม่มีหลักฐานตรวจ'};
  const matches={not_checked:'ยังไม่ได้เทียบ',matched:'มีจุดดาวเทียมที่นำมาเทียบ',not_found:'ค้นในข้อมูลแล้วไม่พบจุดที่ตรง'};
  const esc=s=>root.CmeEvidence.escapeHtml(s);
  const now=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()).replace(' ','T');
  const select=(name,title,values)=>`<label>${title}<select name="${name}">${Object.entries(values).map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label>`;
  const time=(name,title,required=false)=>`<label>${title}<input type="datetime-local" name="${name}" ${required?'required':''}></label>${required?'<button type="button" class="cw-btn" data-field-now>ใช้เวลาตอนนี้</button>':''}`;
  function form(id,correctable=[]){return `<form class="cw-form" id="${id}">
    ${select('outcome','ผลที่ตรวจได้',{unverified:outcomes.unverified,fire_found:outcomes.fire_found,no_fire_found:outcomes.no_fire_found})}
    ${select('method','ตรวจด้วยวิธีใด',{unavailable:methods.unavailable,on_site:methods.on_site,phone:methods.phone,photo:methods.photo})}
    ${time('checked_at','เวลาที่ตรวจ (ประเทศไทย)',true)}
    <label>หลักฐานและบริบทที่ใช้ตัดสิน<textarea name="note" required minlength="5" maxlength="2000" placeholder="เช่น ใครตรวจ วิธีตรวจ และพื้นที่ที่ตรวจครอบคลุม"></textarea></label>
    <details><summary>เพิ่มเติม (ไม่บังคับ): ตำแหน่งที่ตรวจและดาวเทียมที่นำมาเทียบ</summary><p class="cw-help">เว้นค่าที่ไม่ทราบได้ ไม่ใช้พิกัดเหตุแทนตำแหน่งที่ไปตรวจโดยอัตโนมัติ</p>
      <div class="cw-fields"><label>ละติจูดที่ตรวจ<input name="latitude" type="number" step="any" min="-90" max="90"></label><label>ลองจิจูดที่ตรวจ<input name="longitude" type="number" step="any" min="-180" max="180"></label></div>
      <label>ความคลาดเคลื่อนตำแหน่ง (เมตร ถ้าทราบ)<input name="position_accuracy_m" type="number" min="0" max="100000" step="any"></label>
      ${select('satellite_match','ผลการเทียบกับดาวเทียม',matches)}
      <label>แหล่งและรายการดาวเทียมที่ตรวจ<input name="satellite_source" maxlength="300" placeholder="ชื่อแหล่ง / ลิงก์ / ช่วงข้อมูลที่ค้น"></label>
      ${time('satellite_detected_at','เวลาที่ดาวเทียมตรวจพบจุดที่เทียบ')}
    </details>
    <details><summary>เวลาเว็บรับข้อมูล และเวลาที่คนเห็นข้อความ LINE</summary><p class="cw-help">กรอกเมื่อมีหลักฐานเวลาเท่านั้น “ส่งแล้ว” ไม่เท่ากับ “คนอ่านแล้ว”</p>
      ${time('web_received_at','เวลาที่เว็บได้รับข้อมูลดาวเทียม')}${time('message_seen_at','เวลาที่คนเห็นข้อความ LINE')}
    </details>
    ${correctable.length?`<label>รายการเดิมที่ต้องการแก้ไข (ถ้ามี)<select name="corrects_id"><option value="">เป็นผลตรวจเพิ่มเติม</option>${correctable.map(c=>`<option value="${esc(c.id)}">${esc(root.CmeEvidence.stamp(c.created_at||c.checked_at))} · ${esc(outcomes[(c.data||c).outcome])}</option>`).join('')}</select></label>`:''}
    <p class="cw-help">บันทึกนี้เก็บผลที่ผู้ตรวจระบุ การไม่พบไฟหลังเหตุสงบแล้ว ยังสรุปว่าดาวเทียมเตือนผิดไม่ได้</p>
    <button class="cw-btn primary">บันทึกผลตรวจ</button></form>`;}
  function payload(form,id){
    const v=Object.fromEntries(new root.FormData(form)),result={id,outcome:v.outcome,method:v.method,note:v.note,satellite_match:v.satellite_match,satellite_source:v.satellite_source||'',corrects_id:v.corrects_id||null};
    for(const k of ['latitude','longitude','position_accuracy_m'])result[k]=v[k]==null||v[k]===''?null:Number(v[k]);
    for(const k of ['checked_at','satellite_detected_at','web_received_at','email_delivered_at','message_seen_at'])result[k]=v[k]?(v[k].length===16?v[k]+':00':v[k])+'+07:00':null;
    return result;
  }
  function list(checks){return checks.length?checks.map(c=>{const d=c.data||c;return `<article class="cw-row"><div><strong>${esc(outcomes[d.outcome])}</strong><p>${esc(methods[d.method])} · ตรวจ ${esc(root.CmeEvidence.stamp(d.checked_at))}</p><p>${esc(matches[d.satellite_match])}${d.satellite_source?' · '+esc(d.satellite_source):''}</p><p class="cw-description">${esc(d.note)}</p>${d.corrects_id?'<p>เป็นการแก้ไขผลเดิม ประวัติเดิมยังอยู่</p>':''}</div></article>`;}).join(''):'<p class="cw-empty">ยังไม่มีผลตรวจที่บันทึก</p>';}
  function delay(a,b){const x=Date.parse(a),y=Date.parse(b);return Number.isFinite(x)&&Number.isFinite(y)&&y>=x?Math.round((y-x)/1000):'';}
  const safeCell=v=>{let s=v==null?'':String(v);if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  function csv(checks,incident={},mode='field_observation'){
    const keys=['mode','check_id','incident_id','corrects_id','outcome','method','checked_at','latitude','longitude','position_accuracy_m','satellite_match','satellite_source','satellite_detected_at','web_received_at','email_delivered_at','message_seen_at','satellite_to_web_seconds','delivery_to_seen_seconds','note','recorded_at'];
    const rows=checks.map(c=>{const d=c.data||c;return [mode,c.id,incident.id||c.incident_id,d.corrects_id,d.outcome,d.method,d.checked_at,d.latitude,d.longitude,d.position_accuracy_m,d.satellite_match,d.satellite_source,d.satellite_detected_at,d.web_received_at,d.email_delivered_at,d.message_seen_at,delay(d.satellite_detected_at,d.web_received_at),delay(d.email_delivered_at,d.message_seen_at),d.note,c.created_at];});
    return '\uFEFF'+[keys,...rows].map(r=>r.map(safeCell).join(',')).join('\r\n');
  }
  function download(text,filename,type='text/csv;charset=utf-8'){const url=root.URL.createObjectURL(new root.Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>root.URL.revokeObjectURL(url),1000);}
  root.CmeField={form,payload,list,csv,download,outcomes,methods,delay};
  document.addEventListener('click',event=>{const button=event.target.closest('[data-field-now]');if(button&&!button.disabled){const input=button.closest('form')?.elements.checked_at;if(input){input.value=now();input.dispatchEvent(new Event('input',{bubbles:true}));}}});
})(window);
