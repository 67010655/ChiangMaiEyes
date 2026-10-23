import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it, vi } from 'vitest';

const read=(file:string)=>readFileSync(resolve(__dirname,'../public',file),'utf8');
const doc=JSON.parse(read('protected-areas-chiangmai.geojson'));
const tambons=JSON.parse(read('chiangmai-tambons.geojson')).features;
const rectangle=(w:number,s:number,e:number,n:number)=>({type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]});
const point={lat:18.7985022,lon:98.87560547145418}; // Native map intersected with Ban Pong, Hang Dong.
const mine={forest_id:'fixture-mine',name:'ป่าของตัวแทนทดสอบ',amphoe:'หางดง',latitude:18.79,longitude:98.87,boundary:rectangle(98.868,18.788,98.872,18.792)};
async function setup(data:any=doc){
  const dom=new JSDOM('<main id="host"></main>',{url:'http://localhost/',runScripts:'outside-only'}),w=dom.window as any;
  for(const f of ['decision-support.js','forest-coordination.js','protected-areas.js'])w.eval(read(f));
  w.fetch=vi.fn(async()=>({ok:true,json:async()=>[]}));
  w.CmeCoordination.init({agencies:()=>[],forests:()=>[mine],tambons:()=>tambons,districts:()=>[]});
  await w.CmeProtectedAreas.init({data});
  return {dom,w,c:w.CmeCoordination,p:w.CmeProtectedAreas};
}
it('identifies the real Hang Dong side of Doi Suthep-Pui and puts the park before nearby community forests',async()=>{
  const {dom,c,p}=await setup();
  expect(p.query(point.lat,point.lon).rows.map((r:any)=>r.area.id)).toContain('1024');
  const host=dom.window.document.getElementById('host')!;host.innerHTML=c.html(point.lat,point.lon);
  expect(host.querySelector('.coordination-lead')!.textContent).toBe('📍 จุดนี้อยู่ในเขตอุทยานแห่งชาติดอยสุเทพ-ปุย (กรมอุทยานฯ) · ต.บ้านปง อ.หางดง');
  expect(host.textContent).toContain('ป่าชุมชนใกล้เคียง:');
  expect(host.textContent).toContain('ขอบเขตจาก GISTDA 2017 ใช้อ้างอิง ไม่ใช่แนวเขตทางกฎหมาย');
  expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);
  expect(host.querySelector('.coordination-protected a[href="tel:1362"]')).not.toBeNull();
  expect(host.querySelector('a[href^="mailto:"]')).toBeNull();dom.window.close();
});
it('measures distance to the actual park edge for a point outside within 3 km, not to a centroid',async()=>{
  const {dom,c,p}=await setup();const result=p.query(18.75,98.96);
  expect(result.status).toBe('near');expect(result.rows[0].area.id).toBe('1024');expect(result.rows[0].km).toBeGreaterThan(2.3);expect(result.rows[0].km).toBeLessThan(2.5);
  const host=dom.window.document.getElementById('host')!;host.innerHTML=c.html(18.75,98.96);
  expect(host.querySelector('.coordination-lead')!.textContent).toContain('ห่างเขตอุทยานแห่งชาติดอยสุเทพ-ปุย ประมาณ 2.4 กม.');
  expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);dom.window.close();
});
it('includes the non-hunting area 3003 as well as national parks, using actual polygon interiors',async()=>{
  const {dom,c,p}=await setup();
  const inside=p.query(18.792941,98.93570775597769);
  expect(inside.status).toBe('inside');expect(inside.rows.map((r:any)=>r.area.id)).toContain('3003');
  expect(c.html(18.792941,98.93570775597769)).toContain('เขตห้ามล่าสัตว์ป่าดอยสุเทพ');
  // The temple-adjacent coordinate is inside 3003's bounding box, but outside
  // its actual polygon. A bounding box alone must not make it an inside match.
  const near=p.query(18.805,98.921);expect(near.status).toBe('near');expect(near.rows[0].area.id).toBe('1024');
  expect(c.covers({lat:18.805,lon:98.921},doc.features.find((f:any)=>f.id==='3003').geometry)).toBe(false);
  dom.window.close();
});
it.each([[18.75,98.97],[18.78,99.03]])('does not claim a park match more than 3 km away (%s,%s)',async(lat,lon)=>{
  const {dom,c,p}=await setup();expect(p.query(lat,lon).status).toBe('outside');
  const host=dom.window.document.getElementById('host')!;host.innerHTML=c.html(lat,lon);
  expect(host.querySelector('.coordination-sub')!.textContent).toBe('ป่าชุมชนที่ใกล้ที่สุด:');
  expect(host.textContent).toContain('ไม่ได้ยืนยันว่าอยู่นอกพื้นที่อนุรักษ์ทุกแห่ง');expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);dom.window.close();
});
it('shows the representative warning and includes same-district park detections near the selected forest',async()=>{
  const {dom,c,p}=await setup();
  expect(c.administrativeArea(point.lat,point.lon).district).toBe('หางดง');
  expect(c.html(point.lat,point.lon,{myForestId:mine.forest_id})).toContain('อยู่ในเขตอุทยานแห่งชาติดอยสุเทพ-ปุย — ประสานเจ้าหน้าที่อุทยานก่อนเข้าพื้นที่');
  const recent={id:'recent',...point,detected_at:new Date().toISOString()};
  const old={...recent,id:'old',detected_at:new Date(Date.now()-48*3600000).toISOString()};
  expect(p.nearby([recent,old],mine).map((r:any)=>r.hotspot.id)).toEqual(['recent']);
  expect(p.nearby([recent],{...mine,boundary_quality:'needs_review'})).toEqual([]);dom.window.close();
});
it('preserves holes and overlaps and uses a generic label for an unconfirmed type',async()=>{
  const shell=rectangle(98,18,99,19);shell.coordinates.push(rectangle(98.4,18.4,98.6,18.6).coordinates[0]);
  const feature=(id:string,geometry:any)=>({type:'Feature',id,bbox:[98,18,99,19],properties:{name_th:'ทดสอบ <img>',area_type:'unconfirmed'},geometry});
  const {dom,p}=await setup({...doc,features:[feature('A',shell),feature('B',{type:'MultiPolygon',coordinates:[rectangle(98.1,18.1,98.3,18.3).coordinates]})]});
  expect(p.query(18.5,98.5).status).toBe('outside');
  const result=p.query(18.2,98.2);expect(result.status).toBe('inside');expect(result.rows).toHaveLength(2);
  expect(p.leadHtml(result,'จุดนี้อยู่ ต.ทดสอบ')).toContain('พื้นที่อนุรักษ์ทดสอบ &lt;img&gt;');
  expect(p.detailsHtml(result)).toContain('ขอบเขตซ้อนกัน');dom.window.close();
});
it('keeps public geography and government fallback when the static file is missing; never calls WFS at runtime',async()=>{
  const {dom,w,c,p}=await setup();w.fetch.mockResolvedValue({ok:false,status:404});await p.init();
  const host=dom.window.document.getElementById('host')!;host.innerHTML=c.html(point.lat,point.lon);
  expect(p.query(point.lat,point.lon).status).toBe('unavailable');
  expect(host.textContent).toContain('ยังอ่านขอบเขตพื้นที่อนุรักษ์ไม่ได้');expect(host.textContent).toContain('ป่าชุมชนที่ใกล้ที่สุด:');
  expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);
  expect(w.fetch.mock.calls.every(([url]:any)=>!url.includes('geoserver')&&!url.includes('GetFeature'))).toBe(true);dom.window.close();
});
it('rejects projected coordinates mislabeled as web data instead of silently accepting them',async()=>{
  const {dom,p}=await setup({...doc,metadata:{...doc.metadata,output_crs:'EPSG:3857'}});
  expect(p.status()).toBe('unavailable');dom.window.close();
});
it('handles malformed geometry as unavailable without breaking the government contact card',async()=>{
  const bad={...doc,features:[{...doc.features[0],geometry:{type:'Polygon',coordinates:null}}]};
  const {dom,p,c}=await setup(bad);expect(p.status()).toBe('unavailable');
  expect(c.html(point.lat,point.lon)).toContain('ยังอ่านขอบเขตพื้นที่อนุรักษ์ไม่ได้');dom.window.close();
});
it('keeps same-name areas separate by ID and records historical provenance and type evidence',()=>{
  expect(doc.features).toHaveLength(21);expect(doc.metadata.reference_date).toBe('2017-06-12');expect(doc.metadata.license_id).toBe('other-open');
  expect(doc.features.find((f:any)=>f.id==='1024').properties.area_type).toBe('national_park');
  expect(doc.features.find((f:any)=>f.id==='3003').properties.area_type).toBe('non_hunting_area');
  expect(doc.features.filter((f:any)=>f.properties.name_th==='แม่เลา-แม่แสะ')).toHaveLength(2);
  for(const f of doc.features)expect(f.properties.type_source).toMatch(/^https:\/\/.+\.go\.th\//);
});
