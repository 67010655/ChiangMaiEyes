/* PRODUCT_BRIEF #7: historical public boundaries, never a legal/dispatch decision. */
(function(root){
  'use strict';
  let data=null,state='loading';
  const cache=new Map();
  const esc=v=>root.CmeEvidence.escapeHtml(v);
  const valid=(lat,lon)=>lat!==null&&lon!==null&&lat!==''&&lon!==''&&Number.isFinite(Number(lat))&&Number.isFinite(Number(lon))&&Math.abs(lat)<=90&&Math.abs(lon)<=180;
  const labels={national_park:'อุทยานแห่งชาติ',wildlife_sanctuary:'เขตรักษาพันธุ์สัตว์ป่า',non_hunting_area:'เขตห้ามล่าสัตว์ป่า',forest_park:'วนอุทยาน'};
  const disclaimer='ขอบเขตจาก GISTDA 2017 ใช้อ้างอิง ไม่ใช่แนวเขตทางกฎหมาย';
  function name(feature){
    const p=feature.properties;
    return (labels[p.area_type]||'พื้นที่อนุรักษ์')+(p.name_th||'ไม่ทราบชื่อ');
  }
  function query(lat,lon){
    if(!valid(lat,lon))return {status:'invalid',rows:[]};
    if(state!=='ready')return {status:state,rows:[]};
    const key=Number(lat)+','+Number(lon);if(cache.has(key))return cache.get(key);
    const p={lat:Number(lat),lon:Number(lon)},marginLat=3/110,marginLon=3/(110*Math.cos(p.lat*Math.PI/180));
    const rows=data.features.filter(f=>{
      const [w,s,e,n]=f.bbox;return p.lon>=w-marginLon&&p.lon<=e+marginLon&&p.lat>=s-marginLat&&p.lat<=n+marginLat;
    }).map(area=>({area,km:root.CmeCoordination.boundaryDistance(p,area.geometry)}))
      .filter(r=>r.km<=3).sort((a,b)=>a.km-b.km||String(a.area.id).localeCompare(String(b.area.id)));
    const inside=rows.filter(r=>r.km===0);
    const result={status:inside.length?'inside':rows.length?'near':'outside',rows:inside.length?inside:rows.slice(0,1)};
    if(cache.size>=200)cache.clear();cache.set(key,result);return result;
  }
  function leadHtml(result,administrativeText){
    const suffix=administrativeText.replace(/^จุดนี้อยู่ /,'');
    if(result.status==='inside')return `จุดนี้อยู่ในเขต${result.rows.map(r=>esc(name(r.area))).join(' / ')} (กรมอุทยานฯ) · ${suffix}`;
    if(result.status==='near'){
      const r=result.rows[0],km=r.km<.1?'น้อยกว่า 0.1':r.km.toFixed(1);
      return `ห่างเขต${esc(name(r.area))} ประมาณ ${km} กม. · ${suffix}`;
    }
    return null;
  }
  function warningHtml(result){
    if(result.status!=='inside')return '';
    return result.rows.map(r=>`<p class="coordination-protected-warning">อยู่ในเขต${esc(name(r.area))} — ประสานเจ้าหน้าที่${r.area.properties.area_type==='national_park'?'อุทยาน':'พื้นที่อนุรักษ์'}ก่อนเข้าพื้นที่</p>`).join('');
  }
  function detailsHtml(result){
    if(result.status==='invalid')return '';
    if(result.status==='loading')return '<p class="coordination-note">กำลังอ่านขอบเขตพื้นที่อนุรักษ์…</p>';
    if(result.status==='unavailable')return '<p class="coordination-note">ยังอ่านขอบเขตพื้นที่อนุรักษ์ไม่ได้ ไม่ได้ยืนยันว่าจุดนี้อยู่นอกเขต · ใช้ช่องทางหน่วยงานรัฐด้านล่าง</p>';
    if(result.status==='outside')return '<p class="coordination-note">ไม่พบพื้นที่อนุรักษ์ในชุดปี 2017 ภายในระยะ 3 กม. ไม่ได้ยืนยันว่าอยู่นอกพื้นที่อนุรักษ์ทุกแห่ง</p>';
    const types=[...new Set(result.rows.map(r=>r.area.properties.type_source).filter(u=>typeof u==='string'&&u.startsWith('https://')))];
    return `<div class="coordination-protected"><p><a href="tel:1362">สายด่วนกรมอุทยานฯ · 1362</a></p><small>${disclaimer}</small><small>ระยะเส้นตรงถึงขอบเขต ไม่ใช่ระยะเดินทาง · รูปร่างย่อสำหรับเว็บประมาณ 20 ม.</small><small><a href="${esc(data.metadata.source)}" target="_blank" rel="noopener">ต้นทางข้อมูลเปิด</a> · อ้างอิง 12 มิ.ย. 2017 · ตรวจ ${esc(data.metadata.checked_on)}</small>${types.length?`<small>ประเภทในชุดปี 2017 เทียบจากชื่อที่ยืนยันแล้ว · ${types.map(u=>`<a href="${esc(u)}" target="_blank" rel="noopener">หลักฐานประเภทพื้นที่</a>`).join(' · ')}</small>`:''}${result.rows.length>1?'<small>ชุดข้อมูลมีขอบเขตซ้อนกัน แสดงทุกพื้นที่ที่ตรง ไม่เลือกมอบหมายผู้รับผิดชอบ</small>':''}</div>`;
  }
  function nearby(items,forest,{radiusKm=5}={}){
    if(state!=='ready'||!forest?.boundary||forest.boundary_quality==='needs_review')return [];
    return root.CmeEvidence.filterHotspots(items.map(h=>({...h,lat:h.lat??h.latitude,lon:h.lon??h.longitude}))).flatMap(h=>{
      const result=query(h.lat,h.lon);
      if(result.status!=='inside')return [];
      const km=root.CmeCoordination.boundaryDistance({lat:h.lat,lon:h.lon},forest.boundary);
      return km<=radiusKm?[{hotspot:h,protection:result,km}]:[];
    });
  }
  function install(doc){
    if(doc?.type!=='FeatureCollection'||doc.metadata?.output_crs!=='EPSG:4326'||!Array.isArray(doc.features)||!doc.features.length)throw new Error('Invalid protected-area reference');
    for(const f of doc.features){
      if(!['Polygon','MultiPolygon'].includes(f.geometry?.type)||!Array.isArray(f.bbox)||f.bbox.length!==4||!f.bbox.every(Number.isFinite)||Math.abs(f.bbox[0])>180||Math.abs(f.bbox[1])>90||Math.abs(f.bbox[2])>180||Math.abs(f.bbox[3])>90||typeof f.properties?.name_th!=='string')throw new Error('Invalid protected-area geometry');
      const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;
      if(!Array.isArray(polygons)||!polygons.length||!polygons.every(rings=>Array.isArray(rings)&&rings.length&&rings.every(ring=>Array.isArray(ring)&&ring.length>=4&&ring.every(p=>Array.isArray(p)&&p.length===2&&valid(p[1],p[0]))&&ring[0][0]===ring[ring.length-1][0]&&ring[0][1]===ring[ring.length-1][1])))throw new Error('Invalid protected-area coordinates');
    }
    data=doc;state='ready';cache.clear();
  }
  async function init({data:fixture,onReady=()=>{}}={}){
    state='loading';data=null;cache.clear();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      if(fixture)install(fixture);
      else{
        const response=await fetch('/protected-areas-chiangmai.geojson',{signal:controller.signal});
        if(!response.ok)throw new Error('Protected-area reference unavailable');install(await response.json());
      }
    }catch{state='unavailable';}finally{clearTimeout(timer);}
    onReady();return state;
  }
  root.CmeProtectedAreas={init,query,leadHtml,detailsHtml,warningHtml,nearby,name,disclaimer,features:()=>data?.features||[],status:()=>state};
})(window);
