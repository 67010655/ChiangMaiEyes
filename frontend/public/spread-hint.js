/* Brief task 6: which way a detected fire could spread, from separate cited
 * factors. Not a fire-spread model: wind and daytime upslope are shown side by
 * side (no cited weighting combines them) and a distance appears only as a
 * published rate range for fresh detections, "if the fire is still burning". */
(function(root){
  'use strict';
  const CALM_KMH=3, FLAT_DEG=5, FRESH_HOURS=24, DAY_START=6, DAY_END=18, SAME_WAY_DEG=45;
  const words=['เหนือ','ตะวันออกเฉียงเหนือ','ตะวันออก','ตะวันออกเฉียงใต้','ใต้','ตะวันตกเฉียงใต้','ตะวันตก','ตะวันตกเฉียงเหนือ'];
  const compass=deg=>words[Math.round(((deg%360)+360)%360/45)%8];
  const diff=(a,b)=>{const d=Math.abs(((a-b)%360+360)%360);return d>180?360-d:d;};
  const fmt=n=>Number(n).toLocaleString('th-TH');
  function bangkokHour(now){
    return Number(new Intl.DateTimeFormat('en-GB',{hour:'2-digit',hourCycle:'h23',timeZone:'Asia/Bangkok'}).format(now));
  }
  /** Pure: inputs are plain data so tests can pin time, wind and terrain.
   * wind = {ready, toDeg, kmh, label}; terrain = {slope_deg, upslope_to_deg} | null;
   * rate = reference spread_rates[kind] | null; ageHours = hours since detection. */
  function build({wind,terrain,rate,ageHours,kind=null,now=new Date()}){
    const parts=[], details=[];
    // A water-body or aquaculture point is not evidence of a spreading fire.
    if(kind==='water')return {line:null,details:[],day:false,fresh:false,windTo:null};
    const day=(h=>h>=DAY_START&&h<DAY_END)(bangkokHour(now));
    let windTo=null;
    if(!wind?.ready){
      details.push('ยังไม่มีข้อมูลลมที่ใช้ได้ จึงยังบอกทิศตามลมไม่ได้');
    }else if(wind.kmh<CALM_KMH){
      parts.push(`ลมเบา (${wind.kmh} กม./ชม.) ทิศลามตามลมยังไม่แน่นอน`);
      details.push(`ลมเบากว่า ${CALM_KMH} กม./ชม. จึงไม่บอกทิศตามลม · ${wind.label}`);
    }else{
      windTo=wind.toDeg;
      parts.push(`ตามลมไปทาง${compass(windTo)}`);
      details.push(`ลมพัดไปทาง${compass(windTo)} ${wind.kmh} กม./ชม. · ${wind.label} · ลมจากสถานีอ้างอิงของจังหวัด ไม่ใช่ลม ณ จุดนี้`);
    }
    const sloped=terrain&&Number.isFinite(terrain.slope_deg)&&terrain.slope_deg>=FLAT_DEG;
    if(terrain&&!sloped){
      details.push(`พื้นที่ค่อนข้างราบ (ลาดราว ${terrain.slope_deg}°) ทางขึ้นเขาจึงไม่ใช่ปัจจัยหลัก`);
    }else if(sloped&&day){
      parts.push(`ขึ้นเขาไปทาง${compass(terrain.upslope_to_deg)}`);
      details.push(`กลางวันไฟมักลามขึ้นเขา · ทางลาดขึ้นไปทาง${compass(terrain.upslope_to_deg)} (ลาดราว ${terrain.slope_deg}°)`);
      if(windTo!==null&&diff(windTo,terrain.upslope_to_deg)<=SAME_WAY_DEG)details.push('ลมและทางขึ้นเขาไปทางเดียวกัน ไฟอาจลามเร็วขึ้นทางนั้น');
    }else if(sloped){
      details.push(`กลางคืนลมหุบเขามักพัดลง จึงไม่ใช้ทิศขึ้นเขา (ทางลาดขึ้นไปทาง${compass(terrain.upslope_to_deg)})`);
    }
    const fresh=Number.isFinite(ageHours)&&ageHours<=FRESH_HOURS;
    if(rate&&fresh){
      const one=rate.min_m_min===rate.max_m_min;
      // Unknown forest may be evergreen (~30% of Chiang Mai forest): keep the
      // deciduous condition on the line itself, not only in the details.
      const cond=kind==='unknown_forest'?'ถ้าเป็นป่าผลัดใบและยังไหม้อยู่':'ถ้ายังไหม้อยู่';
      if(rate.in_summary!==false)parts.push(one?`${cond} ราว ${fmt(rate.max_m_per_hour)} ม. ใน 1 ชม.`:`${cond} ราว ${fmt(rate.min_m_per_hour)}–${fmt(rate.max_m_per_hour)} ม. ใน 1 ชม.`);
      details.push(`${rate.site}: ความเร็วที่เคยวัด ${one?rate.max_m_min:rate.min_m_min+'–'+rate.max_m_min} ม./นาที · ${rate.condition} · ใช้กับ 1 ชั่วโมงข้างหน้าเท่านั้น ไม่ใช่การพยากรณ์ระยะลามของเหตุนี้`);
    }else if(Number.isFinite(ageHours)&&!fresh){
      details.push(`ตรวจพบเกิน ${FRESH_HOURS} ชม. ไฟอาจดับหรือย้ายไปแล้ว ใช้ทิศนี้เพื่อเฝ้าระวังเท่านั้น ไม่บอกระยะ`);
    }else if(!rate){
      details.push('ยังไม่มีความเร็วการลามที่ตรวจสอบได้สำหรับพื้นที่ชนิดนี้');
    }
    const old=Number.isFinite(ageHours)&&!fresh;
    const line=parts.length?(old?'ถ้ายังมีไฟ ให้เฝ้าระวัง: ':'ทิศที่ไฟอาจลาม: ')+parts.join(' · ')+' · ค่าประมาณ':null;
    return {line,details,day,fresh,windTo};
  }
  function windNow(){
    try{return typeof root.CmeWindNow==='function'?root.CmeWindNow():null;}catch{return null;}
  }
  function ageHours(detectedAt,now=new Date()){
    const t=Date.parse(detectedAt);return Number.isFinite(t)?(now-t)/3600000:NaN;
  }
  /** One-hour reach (km) of the widest published range, for the map cone. */
  function coneKm(rate){return rate?Number(rate.max_m_per_hour)/1000:0.54;}
  root.CmeSpreadHint={build,windNow,ageHours,coneKm,compass,CALM_KMH,FLAT_DEG,FRESH_HOURS};
})(window);
