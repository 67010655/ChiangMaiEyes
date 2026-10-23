// When the satellites behind our hotspot feed next look at Chiang Mai.
// Bangkok local times, read from the detections NASA FIRMS delivered in
// October 2026: VIIRS (S-NPP, NOAA-20, NOAA-21) twice a day, MODIS Terra
// twice and Aqua once. Terra and Aqua are old and drifting, so their times
// slowly move; recheck them against real detection times now and then.
// A pass then takes about 2-5 hours to reach the map: in our archive (30 days
// to 23 Oct 2026) NASA FIRMS points arrived 1 h 45 min at the earliest and
// 5 h after the satellite saw them at the median. Between
// windows nothing new can appear, which is easy to mistake for "no fire".
(function(root){
  // minutes after midnight
  const WINDOWS=[
    {from:50,to:150,sat:'VIIRS'},     // 00:50–02:30
    {from:530,to:580,sat:'MODIS'},    // 08:50–09:40 Terra
    {from:770,to:860,sat:'VIIRS'},    // 12:50–14:20
    {from:910,to:980,sat:'MODIS'},    // 15:10–16:20 Aqua
    {from:1220,to:1270,sat:'MODIS'},  // 20:20–21:10 Terra
  ];
  const DELAY_MIN=300; // median satellite-to-site delay, counted from the middle of a window
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
    const onMap=w=>hhmm((w.from+w.to)/2+DELAY_MIN);
    if(cur)return {passing:true,from:hhmm(cur.from),onMap:onMap(cur)};
    const w=WINDOWS.find(x=>x.from>m)||WINDOWS[0];
    return {passing:false,from:hhmm(w.from),onMap:onMap(w)};
  }
  function short(now){
    const n=next(now);
    return n.passing?`ดาวเทียมกำลังผ่าน · ขึ้นแผนที่ราว ${n.onMap} น.`:`ดาวเทียมรอบหน้าราว ${n.from} น.`;
  }
  const list=()=>{const t=WINDOWS.map(w=>`${hhmm(w.from)}–${hhmm(w.to)}`);return t.slice(0,-1).join(', ')+' และ '+t.at(-1);};
  function long(now){
    const n=next(now);
    return `ดาวเทียมที่ใช้ (VIIRS และ MODIS) ผ่านเชียงใหม่วันละ ${WINDOWS.length} ช่วง ราว ${list()} น. แล้วขึ้นแผนที่ช้าอีกราว 2–5 ชม. `+
      `ไฟที่เริ่มหลังรอบล่าสุดจะยังไม่ขึ้น${n.passing?` จนถึงราว ${n.onMap} น.`:` จนกว่าดาวเทียมรอบหน้าราว ${n.from} น. และขึ้นแผนที่ราว ${n.onMap} น.`} ถ้าเห็นควันจริง เชื่อสิ่งที่เห็นก่อน`;
  }
  const starts=()=>WINDOWS.map(w=>hhmm(w.from));
  root.CmeSatPasses={next,short,long,starts,WINDOWS};
})(globalThis);
