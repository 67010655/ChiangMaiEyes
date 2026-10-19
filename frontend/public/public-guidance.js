/* Plain-language public guidance: PM2.5 level words and "fire near me".
 * PM2.5 levels follow the Thai AQI announcement B.E. 2566 (Pollution Control
 * Department, published 5 July 2023): thresholds are 24-hour averages, so a
 * latest station reading is only compared against them, and says so. */
(function(root){
  'use strict';
  const PCD_AQI_URL='https://www.pcd.go.th/pcd_news/30028/';
  // Upper bounds (µg/m³, 24-h average) and general-public advice, paraphrased from the announcement.
  const PM_LEVELS=[
    {max:15,label:'ดีมาก',tone:'good',advice:'ทำกิจกรรมกลางแจ้งได้ตามปกติ'},
    {max:25,label:'ดี',tone:'good',advice:'ทำกิจกรรมกลางแจ้งได้ กลุ่มเสี่ยงสังเกตอาการผิดปกติ'},
    {max:37.5,label:'ปานกลาง',tone:'warn',advice:'ลดกิจกรรมกลางแจ้งที่ใช้แรงมาก กลุ่มเสี่ยงใส่หน้ากากเมื่ออยู่นอกอาคาร'},
    {max:75,label:'เริ่มมีผลต่อสุขภาพ',tone:'bad',advice:'ใส่หน้ากากกันฝุ่นเมื่ออยู่นอกอาคาร ลดกิจกรรมกลางแจ้ง'},
    {max:Infinity,label:'มีผลต่อสุขภาพ',tone:'bad',advice:'งดกิจกรรมกลางแจ้ง ถ้ามีอาการให้พบแพทย์'},
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
  root.CmePublicGuidance={pmLevel,nearMe,PM_LEVELS,PCD_AQI_URL};
})(window);
