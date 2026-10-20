/* Fire weather for Chiang Mai: the Canadian Forest Fire Weather Index (FWI)
 * System (Van Wagner 1987; the index GWIS/EFFIS publish worldwide), computed
 * from Open-Meteo noon weather at each district's centre, plus the ECMWF
 * weekly outlook. It says how much the WEATHER favours fire - it does not
 * predict where or whether a fire will start. */
(function(root){
  'use strict';
  // ---------- FWI system (Van Wagner 1987; day-length factors as in R cffdrs) ----------
  const LE_46N=[6.5,7.5,9,12.8,13.9,13.9,12.4,10.9,9.4,8,7,6];
  const LE_10_30N=[7.9,8.4,8.9,9.5,9.9,10.2,10.1,9.7,9.1,8.6,8.1,7.8];
  const LF_N=[-1.6,-1.6,-1.6,0.9,3.8,5.8,6.4,5,2.4,0.4,-1.6,-1.6];
  function dayLength(lat,m){ // m = 0..11
    if(lat>30)return LE_46N[m];
    if(lat>10)return LE_10_30N[m];
    if(lat>-10)return 9;
    return LE_46N[(m+6)%12];
  }
  const dryingFactor=(lat,m)=>lat>20?LF_N[m]:lat>-20?1.4:LF_N[(m+6)%12];
  function ffmcNext(f0,T,H,W,r){
    let mo=147.2*(101-f0)/(59.5+f0);
    if(r>0.5){
      const rf=r-0.5;
      let mr=mo+42.5*rf*Math.exp(-100/(251-mo))*(1-Math.exp(-6.93/rf));
      if(mo>150)mr+=0.0015*(mo-150)**2*Math.sqrt(rf);
      mo=Math.min(mr,250);
    }
    const ed=0.942*H**0.679+11*Math.exp((H-100)/10)+0.18*(21.1-T)*(1-Math.exp(-0.115*H));
    let m;
    if(mo>ed){
      const ko=0.424*(1-(H/100)**1.7)+0.0694*Math.sqrt(W)*(1-(H/100)**8);
      m=ed+(mo-ed)*10**(-(ko*0.581*Math.exp(0.0365*T)));
    }else{
      const ew=0.618*H**0.753+10*Math.exp((H-100)/10)+0.18*(21.1-T)*(1-Math.exp(-0.115*H));
      if(mo<ew){
        const k1=0.424*(1-((100-H)/100)**1.7)+0.0694*Math.sqrt(W)*(1-((100-H)/100)**8);
        m=ew-(ew-mo)*10**(-(k1*0.581*Math.exp(0.0365*T)));
      }else m=mo;
    }
    return Math.max(0,Math.min(101,59.5*(250-m)/(147.2+m)));
  }
  function dmcNext(d0,T,H,r,lat,month){
    const t=Math.max(T,-1.1), rk=1.894*(t+1.1)*(100-H)*dayLength(lat,month)*1e-4;
    let pr=d0;
    if(r>1.5){
      const rw=0.92*r-1.27, wmi=20+280/Math.exp(0.023*d0);
      const b=d0<=33?100/(0.5+0.3*d0):d0<=65?14-1.3*Math.log(d0):6.2*Math.log(d0)-17.2;
      const wmr=wmi+1000*rw/(48.77+b*rw);
      pr=43.43*(5.6348-Math.log(wmr-20));
    }
    return Math.max(pr,0)+rk;
  }
  function dcNext(c0,T,r,lat,month){
    const t=Math.max(T,-2.8), pe=Math.max(0,(0.36*(t+2.8)+dryingFactor(lat,month))/2);
    if(r>2.8){
      const rd=0.83*r-1.27, qr=800*Math.exp(-c0/400)+3.937*rd;
      return Math.max(400*Math.log(800/qr),0)+pe;
    }
    return c0+pe;
  }
  function isiOf(f,W){
    const m=147.2*(101-f)/(59.5+f);
    return 0.208*Math.exp(0.05039*W)*91.9*Math.exp(-0.1386*m)*(1+m**5.31/4.93e7);
  }
  function buiOf(p,d){
    const b=p<=0.4*d?0.8*p*d/(p+0.4*d):p-(1-0.8*d/(p+0.4*d))*(0.92+(0.0114*p)**1.7);
    return Math.max(b,0);
  }
  function fwiOf(isi,bui){
    const fd=bui<=80?0.626*bui**0.809+2:1000/(25+108.64*Math.exp(-0.023*bui));
    const B=0.1*isi*fd;
    return B>1?Math.exp(2.72*(0.434*Math.log(B))**0.647):B;
  }
  /** days: [{date:'YYYY-MM-DD', T, H, W (km/h), r (mm, 24 h to noon)}], oldest first. */
  function series(days,lat,start={ffmc:85,dmc:6,dc:15}){
    let {ffmc,dmc,dc}=start;const out=[];
    for(const d of days){
      if(![d.T,d.H,d.W,d.r].every(Number.isFinite)){out.push({date:d.date,fwi:null});continue;}
      const H=Math.min(100,Math.max(0,d.H)),W=Math.max(0,d.W),r=Math.max(0,d.r),m=Number(d.date.slice(5,7))-1;
      ffmc=ffmcNext(ffmc,d.T,H,W,r);dmc=dmcNext(dmc,d.T,H,r,lat,m);dc=dcNext(dc,d.T,r,lat,m);
      const isi=isiOf(ffmc,W),bui=buiOf(dmc,dc);
      out.push({date:d.date,ffmc,dmc,dc,isi,bui,fwi:fwiOf(isi,bui)});
    }
    return out;
  }
  // EFFIS fire-danger classes (European calibration; not yet tuned for Chiang Mai forests).
  const CLASSES=[
    {max:5.2,label:'ต่ำมาก',color:'#38bdf8'},{max:11.2,label:'ต่ำ',color:'#43b05f'},
    {max:21.3,label:'ปานกลาง',color:'#facc15'},{max:38,label:'สูง',color:'#f97316'},
    {max:50,label:'สูงมาก',color:'#ef4444'},{max:Infinity,label:'สูงสุด',color:'#7f1d1d'}];
  const classOf=v=>Number.isFinite(v)?CLASSES.findIndex(c=>v<c.max):-1;

  // ---------- data ----------
  const FC='https://api.open-meteo.com/v1/forecast', SEAS='https://seasonal-api.open-meteo.com/v1/seasonal';
  const SPIN_DAYS=60, AHEAD=16, cache={};
  // Noon (12:00 local) temperature, humidity and wind; rain = 24 h total ending at noon.
  function noonDays(h){
    const t=h.time||[],out=[];
    for(let i=0;i<t.length;i++){
      if(!t[i].endsWith('T12:00'))continue;
      let r=0,ok=true;for(let k=i-23;k<=i;k++){const v=h.precipitation?.[k];if(k<0||!Number.isFinite(v)){ok=false;break;}r+=v;}
      out.push({date:t[i].slice(0,10),T:h.temperature_2m?.[i],H:h.relative_humidity_2m?.[i],W:h.wind_speed_10m?.[i],r:ok?r:NaN});
    }
    return out;
  }
  async function loadDistricts(points,fetcher=root.fetch?.bind(root)){
    const key=points.map(p=>p.name).join('|');
    if(cache[key]&&Date.now()-cache[key].at<3600e3)return cache[key].data;
    const q=new URLSearchParams({latitude:points.map(p=>p.lat.toFixed(3)).join(','),longitude:points.map(p=>p.lon.toFixed(3)).join(','),
      hourly:'temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation',past_days:String(SPIN_DAYS),forecast_days:String(AHEAD),timezone:'Asia/Bangkok'});
    const r=await fetcher(FC+'?'+q);if(!r.ok)throw Error('forecast '+r.status);
    let j=await r.json();if(!Array.isArray(j))j=[j];
    const data=points.map((p,i)=>({name:p.name,lat:p.lat,days:series(noonDays(j[i]?.hourly||{}).filter(d=>Number.isFinite(d.r)),p.lat)}));
    cache[key]={at:Date.now(),data};return data;
  }
  async function loadOutlook(lat,lon,fetcher=root.fetch?.bind(root)){
    if(cache.outlook&&Date.now()-cache.outlook.at<6*3600e3)return cache.outlook.data;
    const q=new URLSearchParams({latitude:String(lat),longitude:String(lon),timezone:'Asia/Bangkok',forecast_days:'35',
      weekly:'precipitation_mean,precipitation_anomaly,temperature_2m_mean,temperature_2m_anomaly'});
    const r=await fetcher(SEAS+'?'+q);if(!r.ok)throw Error('seasonal '+r.status);
    const w=(await r.json()).weekly||{};
    const data=(w.time||[]).map((t,i)=>({week:t,rain:w.precipitation_mean?.[i],rainAnom:w.precipitation_anomaly?.[i],temp:w.temperature_2m_mean?.[i],tempAnom:w.temperature_2m_anomaly?.[i]}));
    cache.outlook={at:Date.now(),data};return data;
  }

  // ---------- views ----------
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok'}).format(new Date());
  const dLabel=d=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short'}).format(Date.parse(d+'T12:00:00+07:00'));
  const median=a=>{const s=a.filter(Number.isFinite).sort((x,y)=>x-y);if(!s.length)return null;const k=s.length>>1;return s.length%2?s[k]:(s[k-1]+s[k])/2;};
  // Province view: the median district each day, plus how many districts reach "สูง" or above.
  function combine(data,focus){
    if(focus){const one=data.find(d=>d.name===focus);return one?one.days.map(d=>({date:d.date,fwi:d.fwi,high:null})):[];}
    const dates=[...new Set(data.flatMap(d=>d.days.map(x=>x.date)))].sort();
    return dates.map(date=>{const v=data.map(d=>d.days.find(x=>x.date===date)?.fwi).filter(Number.isFinite);
      return {date,fwi:median(v),high:v.filter(x=>x>=CLASSES[2].max).length,of:v.length};});
  }
  function evidence(daily,hot){
    // Mean archive hotspot count on days in each FWI class (past days with both values).
    const byDate=Object.fromEntries((hot||[]).filter(h=>Number.isFinite(h.count)&&h.source_requests_complete&&!h.partial_day).map(h=>[h.date,h.count]));
    const rows=daily.filter(d=>d.date<today()&&Number.isFinite(d.fwi)&&Number.isFinite(byDate[d.date]));
    if(rows.length<14)return '';
    const lo=rows.filter(d=>d.fwi<CLASSES[1].max),hi=rows.filter(d=>d.fwi>=CLASSES[1].max);
    const mean=a=>a.reduce((t,d)=>t+byDate[d.date],0)/a.length;
    if(lo.length<5||hi.length<5)return `<p class="as-note">ช่วง ${rows.length} วันที่ผ่านมามีวันระดับต่างกันน้อยเกินไป ยังเทียบกับจุดความร้อนจริงไม่ได้</p>`;
    return `<p class="as-note fw-evidence">ตรวจย้อนหลัง ${rows.length} วัน: วันที่ระดับ "ปานกลาง" ขึ้นไปพบจุดความร้อนเฉลี่ย <b>${mean(hi).toFixed(1)}</b> จุด/วัน · วันที่ต่ำกว่าพบ <b>${mean(lo).toFixed(1)}</b> จุด/วัน</p>`;
  }
  function fwiCard(data,{focus=null,hot=[]}={}){
    const daily=combine(data,focus), t=today();
    if(!daily.length)return '<p class="as-s">ยังคำนวณดัชนีไม่ได้</p>';
    const view=daily.filter(d=>d.date>=addDays(t,-14));
    const max=Math.max(25,...view.map(d=>d.fwi||0)), n=view.length, w=100/n, ti=view.findIndex(d=>d.date===t);
    const bars=view.map((d,i)=>{const c=classOf(d.fwi),h=Number.isFinite(d.fwi)?Math.max(1.5,d.fwi/max*40):0;
      return `<rect class="fw-bar${d.date>t?' ahead':''}" style="--i:${i}" x="${i*w+w*.16}" y="${44-h}" width="${w*.68}" height="${h}" rx=".8" fill="${c>=0?CLASSES[c].color:'var(--line)'}" data-read="${esc(dLabel(d.date)+' · FWI '+(Number.isFinite(d.fwi)?d.fwi.toFixed(1)+' '+CLASSES[c].label:'ไม่มีข้อมูล')+(d.high!=null?` · ${d.high}/${d.of} อำเภอระดับสูงขึ้นไป`:''))}"><title>${esc(dLabel(d.date))}</title></rect>`;}).join('');
    const split=ti>=0?`<line x1="${(ti+1)*w}" x2="${(ti+1)*w}" y1="0" y2="44" class="fw-today"/>`:'';
    const ahead=daily.filter(d=>d.date>t&&Number.isFinite(d.fwi));
    const peak=ahead.reduce((m,d)=>!m||d.fwi>m.fwi?d:m,null);
    const now=daily.find(d=>d.date===t)||daily.filter(d=>d.date<=t).pop();
    const nc=classOf(now?.fwi), pc=classOf(peak?.fwi);
    // Ring fills to the share of the scale up to "สูงมาก" (50); higher values show a full ring.
    const off=Number.isFinite(now?.fwi)?(100-Math.min(100,now.fwi/50*100)).toFixed(1):'100';
    return `<div class="fw-now">${Number.isFinite(now?.fwi)?`<div class="fw-ring" style="--c:${CLASSES[nc].color};--off:${off}" role="img" aria-label="FWI วันนี้ ${esc(now.fwi.toFixed(0))} ระดับ${esc(CLASSES[nc].label)}"><svg viewBox="0 0 76 76" aria-hidden="true"><circle class="track" cx="38" cy="38" r="30" pathLength="100"/><circle class="val" cx="38" cy="38" r="30" pathLength="100"/></svg><b>${esc(now.fwi.toFixed(0))}</b></div>`:''}
      <p class="as-v">${Number.isFinite(now?.fwi)?`<span class="fw-chip" style="--c:${CLASSES[nc].color}">${esc(CLASSES[nc].label)}</span>`:'<b>—</b>'}<span>วันนี้${focus?'':' (ค่ากลางของอำเภอ)'}</span></p></div>
      ${peak?`<p class="as-s">16 วันข้างหน้า สูงสุดวันที่ <b>${esc(dLabel(peak.date))}</b> ระดับ <b style="color:${CLASSES[pc].color}">${esc(CLASSES[pc].label)}</b>${!focus&&peak.high?` · ${esc(peak.high)} จาก ${esc(peak.of)} อำเภอระดับสูงขึ้นไป`:''}</p>`:''}
      <svg class="as-bars fw-bars" viewBox="0 0 100 44" preserveAspectRatio="none" role="img" aria-label="ดัชนีอากาศเอื้อต่อไฟรายวัน 14 วันที่ผ่านมาและ 16 วันข้างหน้า">${bars}${split}</svg><p class="as-readout" aria-live="polite"></p>
      <div class="as-axis"><span>${esc(dLabel(view[0].date))}</span><span class="fw-axis-now">◀ ผ่านมา · วันนี้ · ข้างหน้า ▶</span><span>${esc(dLabel(view[n-1].date))}</span></div>
      <ul class="fw-key">${CLASSES.slice(0,5).map(c=>`<li><i style="background:${c.color}"></i>${esc(c.label)}</li>`).join('')}</ul>
      ${evidence(daily,hot)}
      <p class="as-note">ดัชนี FWI ระบบแคนาดา (Van Wagner 1987) ที่ GWIS/EFFIS ใช้ทั่วโลก คำนวณจากอุณหภูมิ ความชื้น ลม และฝนตอนเที่ยงจาก Open-Meteo ที่กลางอำเภอ · ระดับสีตามเกณฑ์ EFFIS (ยุโรป) ยังไม่ปรับกับป่าเชียงใหม่ · <b>บอกว่าอากาศเอื้อต่อไฟแค่ไหน ไม่ใช่การพยากรณ์ว่าไฟจะเกิดที่ไหน</b></p>
      <details class="fw-method"><summary>ที่มาและสูตรที่ใช้คำนวณ</summary>
        <ol>
          <li><b>ระบบดัชนี FWI</b> · Van Wagner, C.E. (1987) <i>Development and Structure of the Canadian Forest Fire Weather Index System</i>, Forestry Technical Report 35, Canadian Forestry Service. คำนวณ 3 รหัสความชื้นเชื้อเพลิง (FFMC เชื้อเพลิงละเอียดผิวดิน · DMC ชั้นอินทรีย์ · DC ชั้นลึก) แล้วรวมเป็น ISI การลามเริ่มต้น และ BUI เชื้อเพลิงสะสม ก่อนได้ FWI</li>
          <li><b>ความยาววันตามละติจูด</b> · ใช้ค่าสำหรับละติจูด 10–30°N ตามแพ็กเกจ R <i>cffdrs</i> (Wang, Wotton และคณะ 2017, <i>Ecological Processes</i>) แทนค่าเดิมของแคนาดา (46°N)</li>
          <li><b>ข้อมูลอากาศ</b> · Open-Meteo รายชั่วโมง เลือกเวลา 12:00 น. (อุณหภูมิ ความชื้นสัมพัทธ์ ลม 10 ม.) และฝนสะสม 24 ชม. ถึงเที่ยง ย้อนหลัง 60 วันเพื่อตั้งค่าเริ่มต้นของรหัส (FFMC 85 · DMC 6 · DC 15 ตามมาตรฐาน)</li>
          <li><b>ระดับสี</b> · เกณฑ์ชั้นอันตรายของ EFFIS (European Forest Fire Information System) ต่ำมาก &lt;5.2 · ต่ำ &lt;11.2 · ปานกลาง &lt;21.3 · สูง &lt;38 · สูงมาก &lt;50 · สูงสุด ≥50 ยังไม่ปรับกับป่าผลัดใบเชียงใหม่</li>
          <li><b>ทดสอบสูตร</b> · วันทดสอบมาตรฐาน (17°C, ความชื้น 42%, ลม 25 กม./ชม., ไม่มีฝน) ได้ FFMC 87.69 · DMC 8.55 · DC 19.01 · FWI 10.10 ตรงกับตัวอย่างใน Van Wagner &amp; Pickett (1985)</li>
        </ol>
      </details>`;
  }
  function addDays(d,n){const x=new Date(d+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10);}
  function outlookCard(weeks){
    const rows=(weeks||[]).filter(w=>w.week>today()).slice(0,4);
    if(!rows.length)return '<p class="as-s">ยังไม่มีแนวโน้มรายสัปดาห์</p>';
    const word=(a,dry)=>!Number.isFinite(a)?'—':Math.abs(a)<(dry?3:0.5)?'ใกล้เคียงปกติ':dry?(a<0?'แห้งกว่าปกติ':'ฝนมากกว่าปกติ'):(a>0?'ร้อนกว่าปกติ':'เย็นกว่าปกติ');
    return `<ol class="fw-weeks">${rows.map(w=>`<li><b>สัปดาห์ ${esc(dLabel(w.week))}</b>
        <span class="fw-wk ${Number.isFinite(w.rainAnom)&&w.rainAnom<=-3?'dry':Number.isFinite(w.rainAnom)&&w.rainAnom>=3?'wet':''}">🌧 ${esc(word(w.rainAnom,true))}<small>ฝนรวม ~${esc(Number.isFinite(w.rain)?Math.round(w.rain):'—')} มม. (${Number.isFinite(w.rainAnom)?(w.rainAnom>0?'+':'')+Math.round(w.rainAnom):'—'})</small></span>
        <span class="fw-wk">🌡 ${esc(word(w.tempAnom,false))}<small>${Number.isFinite(w.temp)?esc(w.temp.toFixed(1))+'°':'—'} (${Number.isFinite(w.tempAnom)?(w.tempAnom>0?'+':'')+w.tempAnom.toFixed(1):'—'}°)</small></span></li>`).join('')}</ol>
      <p class="as-note">แนวโน้ม ECMWF (EC46) จุดอ้างอิงเมืองเชียงใหม่ เทียบกับภูมิอากาศของแบบจำลอง · ยิ่งไกลยิ่งไม่แน่นอน · อากาศแห้งและร้อนกว่าปกติทำให้เชื้อเพลิงแห้งเร็ว แต่ไม่ได้บอกว่าจะเกิดไฟ</p>`;
  }
  root.CmeFireWeather={series,ffmcNext,dmcNext,dcNext,isiOf,buiOf,fwiOf,dayLength,noonDays,CLASSES,classOf,combine,evidence,loadDistricts,loadOutlook,fwiCard,outlookCard};
})(window);
