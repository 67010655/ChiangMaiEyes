/* Plain-language public guidance: PM2.5 level words and "fire near me".
 * PM2.5 levels follow the Thai AQI announcement B.E. 2566 (Pollution Control
 * Department, published 5 July 2023): thresholds are 24-hour averages, so a
 * latest station reading is only compared against them, and says so. */
(function(root){
  'use strict';
  const PCD_AQI_URL='https://www.pcd.go.th/pcd_news/30028/';
  // Upper bounds (µg/m³, 24-h average) and general-public advice, paraphrased from the announcement;
  // `short` is the first-screen form of the same advice.
  const PM_LEVELS=[
    {max:15,label:'ดีมาก',tone:'good',short:'ออกนอกบ้านได้',advice:'ทำกิจกรรมกลางแจ้งได้ตามปกติ'},
    {max:25,label:'ดี',tone:'good',short:'ออกนอกบ้านได้',advice:'ทำกิจกรรมกลางแจ้งได้ กลุ่มเสี่ยงสังเกตอาการผิดปกติ'},
    {max:37.5,label:'ปานกลาง',tone:'warn',short:'ลดกิจกรรมหนักกลางแจ้ง',advice:'ลดกิจกรรมกลางแจ้งที่ใช้แรงมาก กลุ่มเสี่ยงใส่หน้ากากเมื่ออยู่นอกอาคาร'},
    {max:75,label:'เริ่มมีผลต่อสุขภาพ',tone:'bad',short:'ใส่หน้ากากกันฝุ่น',advice:'ใส่หน้ากากกันฝุ่นเมื่ออยู่นอกอาคาร ลดกิจกรรมกลางแจ้ง'},
    {max:Infinity,label:'มีผลต่อสุขภาพ',tone:'bad',short:'งดกิจกรรมกลางแจ้ง',advice:'งดกิจกรรมกลางแจ้ง ถ้ามีอาการให้พบแพทย์'},
  ];
  function pmLevel(value){
    const v=Number(value);
    if(value===null||value===undefined||value===''||!Number.isFinite(v)||v<0)return null;
    const level=PM_LEVELS.find(l=>v<=l.max);
    return {...level,source:'เกณฑ์ดัชนีคุณภาพอากาศ กรมควบคุมมลพิษ 2566 (ค่าเฉลี่ย 24 ชม.)',url:PCD_AQI_URL};
  }
  const rad=n=>n*Math.PI/180;
  function km(a,b){
    const dLat=rad(b.lat-a.lat),dLon=rad(b.lon-a.lon);
    const x=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(x),Math.sqrt(Math.max(0,1-x)));
  }
  function bearing(a,b){
    const p1=rad(a.lat),p2=rad(b.lat),dl=rad(b.lon-a.lon);
    return (Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl))*180/Math.PI+360)%360;
  }
  /** Nearest hotspots to the user; prefers detections within `freshHours`.
   * Location never leaves the browser. */
  function nearMe(me,hotspots,{now=Date.now(),freshHours=24,radiusKm=5}={}){
    const rows=(hotspots||[]).filter(h=>Number.isFinite(h.lat)&&Number.isFinite(h.lon)).map(h=>{
      const t=Date.parse(h.detected_at);
      return {h,km:km(me,{lat:h.lat,lon:h.lon}),deg:bearing(me,{lat:h.lat,lon:h.lon}),ageHours:Number.isFinite(t)?(now-t)/3600000:NaN};
    }).sort((a,b)=>a.km-b.km);
    const fresh=rows.filter(r=>r.ageHours<=freshHours);
    return {nearestFresh:fresh[0]||null,nearestAny:rows[0]||null,
            freshWithin:fresh.filter(r=>r.km<=radiusKm).length,radiusKm,freshHours,total:rows.length};
  }
  const RINGS_KM=[1,3,5,10];
  const angleGap=(a,b)=>{const d=Math.abs(((a-b)%360+360)%360);return d>180?360-d:d;};
  /** How close fire is to the user, in plain words. Not a measured fire risk: it uses only the
   * distance to satellite detections in the last 24 h, whether the wind blows from them toward
   * the user, and the nearest PM2.5 reading. `windFromDeg` is the direction the wind comes FROM. */
  function aroundMe(me,hotspots,{now=Date.now(),windFromDeg=null,windKmh=null,pm25=null}={}){
    const r=nearMe(me,hotspots,{now,radiusKm:10});
    const fresh=(hotspots||[]).filter(h=>Number.isFinite(h.lat)&&Number.isFinite(h.lon)).map(h=>{
      const t=Date.parse(h.detected_at);return {h,km:km(me,h),deg:bearing(me,h),ageHours:Number.isFinite(t)?(now-t)/3600000:NaN};
    }).filter(x=>x.ageHours<=24).sort((a,b)=>a.km-b.km);
    let prev=0;const rings=RINGS_KM.map(k=>{const n=fresh.filter(x=>x.km>prev&&x.km<=k||(prev===0&&x.km===0)).length;prev=k;return {km:k,n};});
    // Wind blows from the fire toward the user when the fire lies in the direction the wind comes from.
    const hasWind=Number.isFinite(windFromDeg)&&!(Number.isFinite(windKmh)&&windKmh<2);
    const upwind=hasWind?fresh.filter(x=>x.km<=10&&angleGap(x.deg,windFromDeg)<=45):[];
    const pm=pmLevel(pm25);
    const nearest=fresh[0]||null;
    let level='low';
    if(nearest&&(nearest.km<=3||(nearest.km<=5&&upwind.some(x=>x.km<=5))))level='high';
    else if(nearest&&nearest.km<=10||pm?.tone==='bad')level='watch';
    const LEVELS={
      high:{label:'ระวังมาก',head:'มีไฟใกล้คุณมาก',
        advice:['ปิดประตูหน้าต่าง ใส่หน้ากากกันฝุ่น','เตรียมของจำเป็นไว้ ถ้าเห็นไฟหรือควันเข้ามาใกล้ ให้ออกไปทางที่ไม่มีควัน','อย่าเข้าไปดับไฟคนเดียว โทร 1362']},
      watch:{label:'เฝ้าระวัง',head:'มีไฟในละแวกนี้',
        advice:['คอยดูควันและกลิ่นไหม้ เปิดแผนที่ดูซ้ำทุก 2–3 ชั่วโมง','เด็ก ผู้สูงอายุ และคนที่มีโรคปอดหรือหัวใจ อยู่ในบ้านให้มากขึ้น','เห็นไฟจริง โทร 1362']},
      low:{label:'ปกติ',head:'รอบตัวยังไม่พบไฟ',
        advice:['ใช้ชีวิตได้ตามปกติ','ดาวเทียมไม่เห็นไฟเล็กหรือไฟใต้ต้นไม้ ถ้าเห็นควันจริงให้เชื่อสิ่งที่เห็น']},
    };
    const reasons=[];
    if(nearest)reasons.push(`จุดความร้อนที่ใกล้ที่สุดห่าง ${nearest.km.toFixed(1)} กม.`);
    else reasons.push('ไม่มีจุดความร้อนใน 24 ชม. ที่ผ่านมา');
    if(upwind.length)reasons.push(`ลมพัดจากจุดความร้อน ${upwind.length} จุดมาทางคุณ ควันอาจมาถึง`);
    if(pm&&pm.tone!=='good')reasons.push(`ฝุ่นใกล้คุณ ${Math.round(pm25)} µg/m³ (${pm.label})`);
    return {level,...LEVELS[level],rings,nearest,upwind:upwind.length,pm,reasons,within10:fresh.filter(x=>x.km<=10).length,near:r};
  }
  root.CmePublicGuidance={pmLevel,nearMe,aroundMe,RINGS_KM,PM_LEVELS,PCD_AQI_URL};
})(window);
