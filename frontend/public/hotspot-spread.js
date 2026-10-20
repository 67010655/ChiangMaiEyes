/* Experimental spread outline for one tapped hotspot, from /api/spread/live
 * (the backend's hourly ellipse model, same calculation as its backtest).
 * Shown only when asked, animated 0 → 3 → 6 hours, always labelled as a
 * "what if it is still burning and nobody puts it out" experiment. */
(function(root){
  'use strict';
  const WINDOW_H=24, CACHE_MS=10*60000, MATCH_DEG=1e-4;
  let cache=null, cacheAt=0, pending=null;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ageH=h=>(Date.now()-Date.parse(h.detected_at))/3600000;
  // The model only takes points detected in the last 24 hours.
  const eligible=h=>Number.isFinite(ageH(h))&&ageH(h)<=WINDOW_H;
  function buttonHtml(h){
    if(!eligible(h))return '';
    return `<div class="hs-spread"><button type="button" class="hs-spread-btn" data-spread-lat="${Number(h.lat)}" data-spread-lon="${Number(h.lon)}">▶ ดูแนวลามทดลอง 6 ชม.</button><p class="hs-spread-msg" role="status" hidden></p></div>`;
  }
  function load(fetcher=root.fetch?.bind(root)){
    if(cache&&Date.now()-cacheAt<CACHE_MS)return Promise.resolve(cache);
    if(pending)return pending;
    pending=fetcher('/api/spread/live').then(r=>{if(!r.ok)throw Error('http '+r.status);return r.json();})
      .then(d=>{cache=d;cacheAt=Date.now();return d;}).finally(()=>{pending=null;});
    return pending;
  }
  // Frames (3 h, 6 h …) for the input that started at this point, smallest first.
  function framesFor(data,lat,lon){
    const idx=(data?.inputs||[]).findIndex(i=>Math.abs(i.point.latitude-lat)<MATCH_DEG&&Math.abs(i.point.longitude-lon)<MATCH_DEG);
    if(idx<0)return null;
    const frames=(data.frames||[]).map(f=>({hours:f.hours,validAt:f.valid_at,feature:(f.geometry?.features||[]).find(ft=>ft.properties?.origin_index===idx)}))
      .filter(f=>f.feature).sort((a,b)=>a.hours-b.hours);
    return frames.length?{frames,input:data.inputs[idx],asOf:data.as_of}:null;
  }
  // Scale a polygon ring about the origin; t=0 is the point, t=1 the full outline.
  function scaleRing(ring,lon0,lat0,t){return ring.map(([x,y])=>[lon0+(x-lon0)*t,lat0+(y-lat0)*t]);}
  function scaleGeometry(g,lon0,lat0,t){
    if(g.type==='Polygon')return {type:'Polygon',coordinates:g.coordinates.map(r=>scaleRing(r,lon0,lat0,t))};
    if(g.type==='MultiPolygon')return {type:'MultiPolygon',coordinates:g.coordinates.map(p=>p.map(r=>scaleRing(r,lon0,lat0,t)))};
    return g;
  }
  // Drives the growth animation. draw(list) gets [{hours, geometry}] each frame.
  function animate(result,lat,lon,draw,{reduced=false,msPerFrame=1100}={}){
    const fr=result.frames, finals=fr.map(f=>({hours:f.hours,geometry:f.feature.geometry}));
    if(reduced||!root.requestAnimationFrame){draw(finals);return ()=>{};}
    let stop=false;const t0=performance.now(), total=msPerFrame*fr.length;
    const tick=now=>{
      if(stop)return;
      const p=Math.min(1,(now-t0)/total), seg=Math.min(fr.length-1,Math.floor(p*fr.length));
      const local=p>=1?1:(p*fr.length-seg), ease=1-Math.pow(1-local,3);
      const list=finals.slice(0,seg);
      // Grow the current frame from the previous one (or from the point).
      list.push({hours:fr[seg].hours,geometry:scaleGeometry(fr[seg].feature.geometry,lon,lat,ease),growing:p<1});
      draw(list);
      if(p<1)requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return ()=>{stop=true;};
  }
  function caption(result){
    const hrs=result.frames.map(f=>f.hours).join(' และ ');
    return `แนวลามทดลอง ${esc(hrs)} ชม. ถ้าจุดนี้ยังไหม้และไม่มีการดับ · เชื้อเพลิงหญ้าแห้งสมมติ ลมพยากรณ์ GFS รายชั่วโมง (อาจต่างจากลมสถานีด้านบน) และทางลาด · ยังไม่สอบเทียบกับไฟจริง`;
  }
  root.CmeHotspotSpread={buttonHtml,load,framesFor,animate,scaleGeometry,caption,eligible,_reset:()=>{cache=null;cacheAt=0;}};
})(window);
