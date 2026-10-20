/* Live dust sensors from the World Air Quality Index Project (WAQI).
 * Values are the PM2.5 AQI sub-index on the US EPA scale, NOT µg/m³, so they
 * never mix with the Air4Thai numbers or the PCD colours. Shown live only:
 * WAQI terms allow no archive, so nothing here is stored or charted over time.
 * A district value is the median of at least 2 sensors that reported in the
 * last 3 hours (the same rule as the LINE dust alerts). */
(function(root){
  'use strict';
  // US EPA AQI categories and their official colours.
  const LEVELS=[
    {top:50,label:'ดี',color:'#00e400',ink:'#0b2e0b'},
    {top:100,label:'ปานกลาง',color:'#ffff00',ink:'#3a3500'},
    {top:150,label:'เริ่มมีผลต่อกลุ่มเสี่ยง',color:'#ff7e00',ink:'#3d1d00'},
    {top:200,label:'มีผลต่อสุขภาพ',color:'#ff0000',ink:'#fff'},
    {top:300,label:'มีผลต่อสุขภาพมาก',color:'#8f3f97',ink:'#fff'},
    {top:Infinity,label:'อันตราย',color:'#7e0023',ink:'#fff'},
  ];
  const CREDIT_HTML='ข้อมูล: <a href="https://waqi.info/" target="_blank" rel="noopener">World Air Quality Index Project</a> และหน่วยงานเจ้าของสถานี';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function level(aqi){
    if(!Number.isFinite(aqi))return null;
    const i=LEVELS.findIndex(l=>aqi<=l.top);
    return {...LEVELS[i],n:i+1};
  }
  function chip(aqi){
    const l=level(aqi);if(!l)return '';
    return `<span class="aqi-chip" style="background:${l.color};color:${l.ink}">${esc(l.label)}</span>`;
  }
  function ago(iso,now=Date.now()){
    const m=(now-Date.parse(iso))/6e4;
    if(!Number.isFinite(m))return 'ไม่ทราบเวลา';
    return m<60?Math.max(1,Math.round(m))+' นาทีที่แล้ว':m<2880?Math.round(m/60)+' ชม.ที่แล้ว':Math.round(m/1440)+' วันที่แล้ว';
  }

  let cache=null,cacheAt=0;
  function load(fetcher=root.fetch?.bind(root)){
    if(cache&&Date.now()-cacheAt<600000)return cache;
    if(typeof fetcher!=='function')return Promise.reject(new Error('no fetch'));
    cacheAt=Date.now();
    cache=fetcher('/api/dust-sensors').then(r=>{if(!r.ok)throw Error('sensors '+r.status);return r.json();})
      .then(j=>{if(j?.status!=='ok')throw Error('sensors unavailable');return j;});
    cache.catch(()=>{cache=null;});
    return cache;
  }

  function popupHtml(s,{withTitle=true,now=Date.now()}={}){
    const l=level(s.aqi_pm25);
    return `<div class="hs-pop pm-pop aqi-pop">${withTitle?`<p class="ds-kicker">เซนเซอร์วัดฝุ่น (AQI)</p><h3 class="ds-title">${esc(s.name)}</h3>`:''}
      <p class="pm-pop-v"><b>${esc(s.aqi_pm25)}</b> AQI ${chip(s.aqi_pm25)}</p>
      <p class="fp-sub">${s.district?'อ.'+esc(s.district)+' · ':''}วัดเมื่อ ${esc(ago(s.time,now))}${s.fresh?'':' <span class="pm-old">ข้อมูลเก่า ไม่นับในค่าอำเภอ</span>'}</p>
      <p class="aqi-scale-note">ดัชนี AQI ของ PM2.5 ตามเกณฑ์ US EPA ไม่ใช่ค่า µg/m³ ของกรมควบคุมมลพิษ${l&&l.n>=3?' · ควรลดกิจกรรมกลางแจ้ง':''}</p>
      <div class="hs-actions"><a class="hs-nav" href="https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}" target="_blank" rel="noopener">นำทาง</a></div>
      <details class="land-context-details"><summary>ที่มาและข้อจำกัดของเซนเซอร์</summary>
        <p>${CREDIT_HTML} · ค่ารายชั่วโมง แสดงสดทุก 10 นาที ไม่มีการเก็บย้อนหลัง</p>
        <p>เซนเซอร์ส่วนใหญ่เป็นเซนเซอร์ราคาประหยัดที่ชุมชนหรือหน่วยงานติดตั้ง ต้นทางยังไม่ตรวจสอบค่า ความชื้นสูงอาจทำให้อ่านค่าสูงเกินจริง</p>
      </details></div>`;
  }

  // One line for the district summary: median of 2+ live sensors, or why not.
  function districtHtml(data,district){
    const d=data?.districts?.[district];
    const min=data?.min_sensors||2;
    if(d&&Number.isFinite(d.median)){
      return `<div class="ds-aqi"><span class="ds-aqi-v" style="--aqi:${level(d.median).color}"><b>${esc(d.median)}</b> AQI</span>
        <span class="ds-aqi-t">เซนเซอร์วัดฝุ่น · ค่ากลางจาก ${esc(d.n)} จุดในอำเภอ ${chip(d.median)}</span>
        <small>เกณฑ์ US EPA ไม่ใช่ µg/m³ · เซนเซอร์ราคาประหยัด ยังไม่ตรวจสอบ · ${CREDIT_HTML}</small></div>`;
    }
    const n=d?.n||0;
    return `<div class="ds-aqi none"><span class="ds-aqi-t">เซนเซอร์วัดฝุ่นที่ส่งข้อมูลใน 3 ชม. ${n?`มี ${esc(n)} จุด`:'ไม่มี'} ต้องมีอย่างน้อย ${esc(min)} จุดจึงแสดงค่าอำเภอ</span></div>`;
  }

  // Square number badge (never a round dot: round dots are fire hotspots).
  function badgeHtml(s){
    const l=level(s.aqi_pm25);
    return `<span class="aqi-badge${s.fresh?'':' stale'}" style="background:${l.color};color:${l.ink}">${esc(s.aqi_pm25)}</span>`;
  }
  function legendHtml(){
    return `<div class="aqi-legend" aria-label="ระดับ AQI">${LEVELS.map(l=>`<span><i class="sq" style="background:${l.color}"></i>${esc(l.label)}</span>`).join('')}</div>`;
  }

  root.CmeDustSensors={LEVELS,level,chip,badgeHtml,load,popupHtml,districtHtml,legendHtml,ago,
    _reset(){cache=null;cacheAt=0;}};
})(typeof window!=='undefined'?window:globalThis);
