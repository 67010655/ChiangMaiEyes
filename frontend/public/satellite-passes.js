// When the satellites behind our hotspot feed next look at Chiang Mai.
// VIIRS (S-NPP, NOAA-20, NOAA-21) crosses the province in two windows a day;
// the times below are Bangkok local, read from the detection times we received
// in October 2026. NASA FIRMS then needs about 3 hours before a pass reaches
// the map. Between windows nothing new can appear, which is easy to mistake
// for "no fire".
(function(root){
  const WINDOWS=[{from:50,to:150},{from:770,to:860}]; // minutes after midnight: 00:50–02:30, 12:50–14:20
  const DELAY_MIN=180;
  const DAY=1440;
  const hhmm=m=>{const v=((Math.round(m/30)*30)%DAY+DAY)%DAY;return String(Math.floor(v/60)).padStart(2,'0')+':'+String(v%60).padStart(2,'0');};
  function bkkMinutes(now){
    const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now);
    const get=t=>Number(p.find(x=>x.type===t)?.value||0);
    return get('hour')*60+get('minute');
  }
  // {passing, from, onMap}: the window now in progress, or the next one to start.
  function next(now=new Date()){
    const m=bkkMinutes(now);
    const cur=WINDOWS.find(w=>m>=w.from&&m<w.to);
    if(cur)return {passing:true,from:hhmm(cur.from),onMap:hhmm(cur.to+DELAY_MIN)};
    const w=WINDOWS.find(x=>x.from>m)||WINDOWS[0];
    return {passing:false,from:hhmm(w.from),onMap:hhmm(w.to+DELAY_MIN)};
  }
  function short(now){
    const n=next(now);
    return n.passing?`ดาวเทียมกำลังผ่าน · ขึ้นแผนที่ราว ${n.onMap} น.`:`ดาวเทียมรอบหน้าราว ${n.from} น.`;
  }
  function long(now){
    const n=next(now);
    return `ดาวเทียมที่ใช้ผ่านเชียงใหม่วันละ 2 ช่วง ราว ${hhmm(WINDOWS[0].from)}–${hhmm(WINDOWS[0].to)} และ ${hhmm(WINDOWS[1].from)}–${hhmm(WINDOWS[1].to)} น. แล้วขึ้นแผนที่ช้าอีกราว 3 ชม. `+
      `ไฟที่เริ่มหลังรอบล่าสุดจะยังไม่ขึ้น${n.passing?` จนถึงราว ${n.onMap} น.`:` จนกว่าดาวเทียมรอบหน้าราว ${n.from} น. และขึ้นแผนที่ราว ${n.onMap} น.`} ถ้าเห็นควันจริง เชื่อสิ่งที่เห็นก่อน`;
  }
  root.CmeSatPasses={next,short,long,WINDOWS};
})(globalThis);
