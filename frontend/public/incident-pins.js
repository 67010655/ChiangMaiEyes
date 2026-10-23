/* Incident pins: a fire or smoke that a community-forest rep reported. Approved reps and admins see it
   on the map until the reporter ends it (or 3 days pass). The site only informs; people call each other.
   Every value comes from the signed-in API (/api/community/pins) and is escaped here. */
(function(root){
  'use strict';
  const HOUR=36e5,DAY=864e5,RISK_KM=5;
  const esc=value=>root.CmeEvidence.escapeHtml(value);
  const ms=value=>Date.parse(value);
  const ageMs=(pin,now=Date.now())=>Math.max(0,now-ms(pin.created_at));
  // Fresh pins pulse; older ones fade so a forgotten pin is easy to tell from a new report.
  const tone=(pin,now)=>ageMs(pin,now)<DAY?'fresh':ageMs(pin,now)<2*DAY?'mid':'old';
  function agoText(pin,now=Date.now()){
    const minutes=Math.round((now-ms(pin.created_at))/6e4);
    return minutes<1?'เมื่อสักครู่':minutes<60?minutes+' นาทีที่แล้ว':minutes<1440?Math.round(minutes/60)+' ชม.ที่แล้ว':Math.floor(minutes/1440)+' วันที่แล้ว';
  }
  function leftText(pin,now=Date.now()){
    const left=ms(pin.expires_at)-now;
    if(!(left>0))return 'ใกล้ปิดอัตโนมัติ';
    const days=Math.floor(left/DAY),hours=Math.floor(left%DAY/HOUR);
    return days?`${days} วัน ${hours} ชม.`:`${Math.max(1,hours)} ชม.`;
  }
  const what=pin=>pin.observation==='fire'?'เปลวไฟ':'ควัน';
  const clock=value=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
  const phoneHref=phone=>'tel:'+String(phone||'').replace(/[^0-9+]/g,'');
  // Same eye as the earlier manual-report pin, in violet so it never reads as a satellite point.
  function iconHtml(pin,now){
    const t=tone(pin,now);
    return `<div class="pulse-wrap pin-eye ${t}" style="width:26px;height:26px">${t==='fresh'?'<div class="ring"></div>':''}`+
      `<span class="pin-eye-body"><svg style="transform:rotate(45deg)" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg></span></div>`;
  }
  // The stored list is worked out once by the server; without it fall back to the map's own nearest-forest search.
  function nearbyRows(pin,fallback){
    if(Array.isArray(pin.nearby)&&pin.nearby.length)return pin.nearby;
    return (fallback||[]).map(r=>({forest_id:r.forest.forest_id,name:r.forest.name||'ป่าชุมชน',km:Number(r.km.toFixed(1)),risk:r.forest.forest_id!==pin.forest_id&&r.km<=RISK_KM,reporter:r.forest.forest_id===pin.forest_id}));
  }
  const kmText=km=>km===0?'อยู่ในขอบเขตป่า':km<.1?'น้อยกว่า 0.1 กม.':Number(km).toFixed(1)+' กม.';
  function nearbyHtml(pin,fallback){
    const rows=nearbyRows(pin,fallback);
    if(!rows.length)return '';
    const items=rows.map(r=>`<li class="${r.risk?'risk':''}"><strong>${esc(r.name)}</strong> <span>${esc(kmText(r.km))}</span> ${r.reporter?'<em>ป่าของผู้แจ้ง</em>':r.risk?'<em class="warn">เสี่ยง · ใกล้ไม่เกิน 5 กม.</em>':''}</li>`).join('');
    return `<h4>ป่าชุมชนใกล้จุดนี้</h4><ul class="pin-near">${items}</ul>`;
  }
  // The newest progress note from the reporter's forest ("fire spreading", "mostly out"), cut short by the server.
  function latestNoteHtml(pin){
    const n=pin.latest_note,text=n&&String(n.text||'').trim();
    if(!text)return '';
    const when=n.at&&Number.isFinite(ms(n.at))?clock(n.at):'';
    return `<p class="pin-latest"><b>ความคืบหน้าล่าสุด</b> <small>${esc([when,n.by].filter(Boolean).join(' · '))}</small></p><blockquote class="pin-latest-q">${esc(text)}</blockquote>`;
  }
  function popupHtml(pin,{now=Date.now(),fallback=null,coordination=''}={}){
    const desc=String(pin.description||'').trim();
    const phone=pin.contact_phone?`<p class="pin-phone">☎️ <a href="${esc(phoneHref(pin.contact_phone))}">${esc(pin.contact_phone)}</a> <small>(ผู้แจ้งให้ติดต่อ)</small></p>`:'';
    const actions=[
      pin.can_open?`<button type="button" class="pin-btn" data-pin-open="${esc(pin.id)}" onclick="pinOpenIncident(this)">เปิดใบเหตุ</button>`:'',
      pin.can_close?`<button type="button" class="pin-btn ok" data-pin-close="${esc(pin.id)}" data-outcome="closed" onclick="pinCloseIncident(this)">✅ จบงาน</button><button type="button" class="pin-btn" data-pin-close="${esc(pin.id)}" data-outcome="cancelled" onclick="pinCloseIncident(this)">❌ ไม่ใช่ไฟ</button>`:'',
    ].join('');
    return `<div class="pin-pop" data-pin="${esc(pin.id)}">
      <p class="pin-kicker">👁 ตัวแทนป่าชุมชนแจ้ง · ยังไม่ใช่การยืนยันจากหน่วยงาน</p>
      <h3>เห็น${what(pin)}ที่ ${esc(pin.forest_name)}${pin.amphoe?` <small>อ.${esc(String(pin.amphoe).replace(/^(อำเภอ|อ\.)\s*/,''))}</small>`:''}</h3>
      <p class="pin-who">แจ้งโดย <b>${esc(pin.reporter_name)}</b>${pin.mine?' (คุณ)':''} · พบเมื่อ ${esc(clock(pin.observed_at))} · แจ้ง${esc(agoText(pin,now))}</p>
      ${desc?`<blockquote>${esc(desc)}</blockquote>`:'<p class="pin-none">ผู้แจ้งไม่ได้เขียนรายละเอียดเพิ่ม</p>'}
      ${latestNoteHtml(pin)}
      ${phone}
      ${nearbyHtml(pin,fallback)}
      <p class="pin-note">ประสานงานกันเองได้เลย หมุดจะหายเมื่อผู้แจ้งกดจบงาน หรืออีก ${esc(leftText(pin,now))} · ถ้าเห็นไฟจริง โทร <a href="tel:1362">1362</a></p>
      ${actions?`<div class="pin-actions">${actions}</div>`:''}
      ${coordination?`<details class="pin-more"><summary>📞 ติดต่อป่าและหน่วยงานใกล้จุดนี้</summary>${coordination}</details>`:''}
    </div>`;
  }
  root.CmeIncidentPins={latestNoteHtml,tone,agoText,leftText,iconHtml,nearbyRows,nearbyHtml,popupHtml,RISK_KM};
})(window);
