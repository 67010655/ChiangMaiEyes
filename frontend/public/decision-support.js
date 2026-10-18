/* Shared, pure evidence helpers for the inline production dashboard. */
(function (root) {
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function distanceKm(a, b) {
    const rad = n => n * Math.PI / 180;
    const dLat = rad(b.lat-a.lat), dLon = rad(b.lon-a.lon);
    const x = Math.sin(dLat/2)**2 + Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
    return 6371 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0,1-x)));
  }
  function inRing(lat, lon, ring) {
    let inside = false;
    for (let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const [xi,yi]=ring[i], [xj,yj]=ring[j];
      if (((yi>lat)!==(yj>lat)) && lon<(xj-xi)*(lat-yi)/(yj-yi)+xi) inside=!inside;
    }
    return inside;
  }
  function inBoundary(lat, lon, geometry) {
    if (!geometry) return false;
    if (geometry.type==='Feature') return inBoundary(lat,lon,geometry.geometry);
    const polygons = geometry.type==='Polygon' ? [geometry.coordinates] : geometry.type==='MultiPolygon' ? geometry.coordinates : [];
    return polygons.some(rings => rings.length && inRing(lat,lon,rings[0]) && !rings.slice(1).some(r => inRing(lat,lon,r)));
  }
  function filterHotspots(items, {hours=24,now=Date.now(),forest=null,point=null,radiusKm=5}={}) {
    return items.filter(h => {
      const age = now-Date.parse(h.detected_at);
      if (!Number.isFinite(age) || age<0 || age>hours*3600000) return false;
      if (forest) return inBoundary(h.lat,h.lon,forest.boundary);
      if (point) return distanceKm(point,h)<=radiusKm;
      return true;
    });
  }
  function stamp(iso) {
    const date = new Date(iso);
    return iso && Number.isFinite(date.getTime()) ? date.toLocaleString('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})+' น.' : 'ยังไม่ระบุเวลา';
  }
  function observationTimeHtml(iso,source='ดาวเทียม',now=Date.now()){
    const time=iso?Date.parse(iso):NaN,age=now-time;
    let text='ยังไม่ทราบเวลาตรวจพบ';
    if(Number.isFinite(time)&&age>=0){
      const minutes=Math.floor(age/60000),hours=Math.floor(minutes/60),days=Math.floor(hours/24);
      const relative=days?days+' วันที่แล้ว':hours?hours+' ชั่วโมงที่แล้ว':minutes?minutes+' นาทีที่แล้ว':'เมื่อสักครู่';
      const exact=new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(time);
      text=`ตรวจพบ ${relative} (${exact})`;
    }else if(Number.isFinite(time))text='เวลาตรวจพบอยู่ในอนาคต โปรดตรวจสอบต้นทาง';
    return `<p class="hotspot-detected-time">${escapeHtml(text)} · ${escapeHtml(source)}</p>`;
  }
  function windTo(from) { return ((Number(from)+180)%360+360)%360; }
  function confidenceLevel(item) {
    return ['low','nominal','high','unknown'].includes(item.confidence_level)
      ? item.confidence_level : 'unknown';
  }
  function confidenceLabel(level) {
    return {low:'ต่ำ',nominal:'ปกติ (nominal)',high:'สูง',unknown:'ต้นทางไม่ระบุ'}[level] || 'ต้นทางไม่ระบุ';
  }
  function dailyStats(values) {
    const data=values.filter(Number.isFinite).sort((a,b)=>a-b), n=data.length;
    if(!n) return {n:0,total:null,mean:null,median:null,sd:null,max:null};
    const total=data.reduce((s,v)=>s+v,0), mean=total/n;
    return {n,total,mean,median:n%2?data[(n-1)/2]:(data[n/2-1]+data[n/2])/2,sd:Math.sqrt(data.reduce((s,v)=>s+(v-mean)**2,0)/n),max:data[n-1]};
  }
  const contacts = [{
    name:'สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่)', phone:'052-081758',
    source:'https://forestinfo.forest.go.th/telephone_region.aspx', checked:'2026-10-09',
    note:'ช่องทางหน่วยงานสำหรับสอบถามผู้ประสานงาน ไม่ใช่เบอร์หัวหน้าป่าชุมชนแห่งนี้'
  }];
  const sources = [
    {name:'NASA FIRMS',mark:'NASA',url:'https://firms.modaps.eosdis.nasa.gov/',kind:'จุดความร้อนจากดาวเทียม',note:'ข้อมูลใกล้เวลาจริงหลังดาวเทียมผ่าน ไม่ใช่ภาพไฟต่อเนื่อง จุดความร้อนยังต้องตรวจสอบภาคสนาม'},
    {name:'GISTDA',mark:'GISTDA',url:'https://dnp.gistda.or.th/',kind:'ข้อมูลดาวเทียมและพื้นที่เฝ้าระวัง',note:'ดูผลิตภัณฑ์และเวลาในแต่ละชุดข้อมูล ไม่ใช้เวลาที่เปิดเว็บแทนเวลาตรวจพบ'},
    {name:'RECOFTC',mark:'RECOFTC',url:'https://www.recoftc.org/',kind:'ขอบเขตป่าชุมชนเชียงใหม่ 677 แห่ง',note:'ชุดขอบเขตที่โครงการได้รับ ไม่ได้ยืนยันรายชื่อผู้ประสานงานหรืออำนาจสั่งการ'},
    {name:'กรมอุตุนิยมวิทยา',mark:'TMD',url:'https://www.tmd.go.th/',kind:'อากาศและลมจากสถานี',note:'ค่าของสถานี ไม่ใช่ลมทุกหุบเขา หาก feed ไม่ระบุความสูงต้องแสดงว่ายังไม่ระบุ'},
    {name:'Open-Meteo',mark:'Open-Meteo',url:'https://open-meteo.com/en/docs',kind:'แบบจำลองอากาศและลม 10 เมตร',note:'ลมที่ระดับ 10 เมตรเหนือพื้นดินจากแบบจำลอง ไม่ใช่การวัดในป่าทุกจุด'},
    {name:'Air4Thai / กรมควบคุมมลพิษ',mark:'PCD',url:'https://air4thai.pcd.go.th/services/getNewAQI_JSON.php',kind:'ความเข้มข้น PM2.5 จากสถานี',note:'อ่าน PM25.value และเวลาของสถานีจากบริการ Air4Thai เฉลี่ยเฉพาะสถานีเชียงใหม่ที่มีค่าในชุดนั้น ไม่ใช้แทนการวัดในทุกป่าหรือทุกบ้าน'},
    {name:'CAMS ผ่าน Open-Meteo',mark:'CAMS',url:'https://open-meteo.com/en/docs/air-quality-api',kind:'ฝุ่นจากแบบจำลองบรรยากาศ',note:'PM2.5 ตามจุดอ้างอิงและกริดของแบบจำลอง ใช้กับพยากรณ์และกราฟแบบจำลอง แสดงแยกจากค่าตรวจวัดสถานี'},
    {name:'AQICN',mark:'AQICN',url:'https://aqicn.org/api/',kind:'ดัชนีคุณภาพอากาศ AQI',note:'ดัชนีรวมจากต้นทาง ไม่ใช่ความเข้มข้น PM2.5 ไม่แปลงเป็น µg/m³ และไม่เก็บเป็นสถิติฝุ่นย้อนหลัง'},
    {name:'NASA GIBS',mark:'NASA',url:'https://nasa-gibs.github.io/gibs-api-docs/',kind:'บริการภาพดาวเทียม',note:'เอกสารการเรียกภาพและเวลาแต่ละผลิตภัณฑ์ ดัชนีพืชพรรณไม่ใช่มวลเชื้อเพลิงแห้ง ต้องสอบเทียบภาคสนามก่อนแบ่งระดับเชื้อเพลิง'},
    {name:'Copernicus GLO-30',mark:'DEM',url:'https://registry.opendata.aws/copernicus-dem/',kind:'ความสูงและความชันตามขอบเขตป่า',note:'แบบจำลองพื้นผิวประมาณ 30 m รวมต้นไม้และสิ่งปลูกสร้าง สรุปตามขอบเขต RECOFTC ไม่ใช่เชื้อเพลิงหรือค่าที่จุดไฟทุกจุด'},
    {name:'Mapzen / AWS Open Data',mark:'DEM',url:'https://registry.opendata.aws/terrain-tiles/',kind:'ข้อมูลความสูงภูมิประเทศ',note:'ภาพ 3D อาจขยายความสูงเพื่อช่วยอ่านภูเขา ระบุอัตราขยายไว้บนแผนที่'},
    {name:'US EPA',mark:'EPA',url:'https://www.epa.gov/air-sensor-toolbox/frequent-questions-about-air-sensors',kind:'ข้อจำกัดของเซนเซอร์ฝุ่น',note:'ความชื้นสูงอาจกระทบเซนเซอร์บางชนิด ต้องตรวจรุ่น การสอบเทียบ และการติดตั้ง'},
    {name:'NOAA GFS',mark:'NOAA',url:'https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f000.shtml',kind:'แบบจำลองที่เชื่อมแล้ว',note:'ดูในส่วนการระบายอากาศ: HPBL ลมในชั้น PBL และ VRATE จาก GRIB ของ NOAA กริด 0.25° ระบุรอบแบบจำลองและเวลาที่ข้อมูลแทนแยกกัน'},
    {name:'US Forest Service · Behave',mark:'USFS',url:'https://github.com/firelab/behave/tree/d4acc8a074646c754673b6725234fdf3a1e9c053/src/behave',kind:'สมการจำลองไฟผิวดิน',note:'เครื่องมือในหน้าวิเคราะห์ใช้ Rothermel–Albini เชื้อเพลิงแห้งชนิดเดียว ลมระดับใกล้เปลวไฟและทางลาดคงที่ วาดวงรีตามเวลา ไม่ใช่ผลพยากรณ์ไฟจริงที่สอบเทียบกับเชียงใหม่'}
  ];
  function fireHelpHtml(){
    return '<p class="fire-help">พบไฟป่าหรือควัน: <a href="tel:1362">โทร 1362 สายด่วนพิทักษ์ป่า</a><br><small>การบันทึกบนเว็บไม่ใช่การเรียกรถหรือเจ้าหน้าที่ฉุกเฉิน · <a href="https://news.dnp.go.th/news/36837" target="_blank" rel="noopener">ข้อมูลกรมอุทยานฯ</a></small></p>';
  }
  root.CmeEvidence = {fireHelpHtml,observationTimeHtml,escapeHtml,distanceKm,inBoundary,filterHotspots,stamp,windTo,confidenceLevel,confidenceLabel,dailyStats,contacts,sources};
})(typeof window!=='undefined' ? window : globalThis);
